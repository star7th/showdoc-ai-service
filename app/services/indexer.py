"""
文档索引管理器
"""
from typing import Dict, Any, Optional, List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.config import get_settings
from app.utils.chunker import MarkdownChunker
from app.utils.embedding import EmbeddingService
from app.utils.redis_client import get_redis_client
import uuid
import json
import time

settings = get_settings()


class Indexer:
    """文档索引管理器"""
    
    def __init__(self):
        self.client = QdrantClient(url=settings.qdrant_url)
        self.chunker = MarkdownChunker()
        self.embedding_service = EmbeddingService()
        self.collection_prefix = settings.qdrant_collection_prefix
        self.redis_client = get_redis_client(default_ttl=365 * 24 * 60 * 60)  # 1年TTL
    
    def _get_collection_name(self, item_id: int) -> str:
        """获取 Collection 名称"""
        return f"{self.collection_prefix}{item_id}"
    
    def _get_access_time_key(self, item_id: int) -> str:
        """获取访问时间 Redis 键名"""
        return f"ai_index_access_time:{item_id}"
    
    def record_access_time(self, item_id: int):
        """记录项目索引的访问时间"""
        try:
            key = self._get_access_time_key(item_id)
            current_time = int(time.time())
            # 使用 set 方法，TTL 为 1 年（365天），每次访问会自动刷新
            self.redis_client.set(key, current_time, ttl=365 * 24 * 60 * 60, refresh_on_access=True)
        except Exception as e:
            print(f"记录访问时间失败: item_id={item_id}, error={str(e)}")
    
    def get_access_time(self, item_id: int) -> Optional[int]:
        """获取项目索引的最后访问时间"""
        try:
            key = self._get_access_time_key(item_id)
            value = self.redis_client.get(key, refresh_ttl=False)
            if value:
                return int(value)
            return None
        except Exception as e:
            print(f"获取访问时间失败: item_id={item_id}, error={str(e)}")
            return None
    
    async def ensure_collection(self, item_id: int):
        """确保 Collection 存在"""
        collection_name = self._get_collection_name(item_id)
        
        # 检查 Collection 是否存在
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if collection_name not in collection_names:
            # 创建新的 Collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.embedding_service.get_dimension(),
                    distance=Distance.COSINE
                )
            )
            # 创建 Collection 时记录访问时间
            self.record_access_time(item_id)
    
    async def upsert_document(
        self,
        item_id: int,
        page_id: int,
        page_title: str,
        page_content: str,
        page_type: str = "regular",
        metadata: Dict[str, Any] = None
    ):
        """创建/更新文档索引"""
        # 确保 Collection 存在
        await self.ensure_collection(item_id)
        
        # 删除旧索引（如果存在）
        await self.delete_document(item_id, page_id)
        
        # 检查页面内容是否为空
        if not page_content or not isinstance(page_content, str) or not page_content.strip():
            print(f"[Indexer] 警告: 页面 {page_id} 内容为空，跳过索引")
            return
        
        # 文档分块（根据页面类型选择分块策略）
        chunks = self.chunker.chunk(page_content, page_type=page_type)
        
        # 生成向量并存储（分批处理，避免内存占用过大）
        collection_name = self._get_collection_name(item_id)
        batch_size = 50  # 每批处理 50 个 chunk，降低内存峰值
        
        for batch_start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_start:batch_start + batch_size]
            points = []
            
            for idx, chunk in enumerate(batch_chunks):
                # 生成向量
                vector = await self.embedding_service.embed(chunk.content)
                
                # 构建 Point
                point_id = str(uuid.uuid4())
                # 处理 metadata，确保不为 None
                metadata_dict = metadata or {}
                point = PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "item_id": item_id,
                        "page_id": page_id,
                        "page_title": page_title,
                        "page_type": page_type,
                        "chunk_id": batch_start + idx,  # 使用全局索引
                        "chunk_content": chunk.content,
                        "chunk_metadata": chunk.metadata,
                        **metadata_dict
                    }
                )
                points.append(point)
            
            # 批量插入（分批插入，降低内存占用）
            self.client.upsert(
                collection_name=collection_name,
                points=points
            )
            
            # 清理临时变量，释放内存
            del points
            import gc
            gc.collect()
    
    async def delete_document(self, item_id: int, page_id: int):
        """删除文档索引"""
        collection_name = self._get_collection_name(item_id)
        
        # 检查 Collection 是否存在
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            if collection_name not in collection_names:
                # Collection 不存在，无需删除
                return
        except Exception as e:
            print(f"[Indexer] 检查 Collection 失败: {e}")
            return
        
        # 查找并删除该文档的所有 chunks
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # 使用 Filter 对象正确删除
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="page_id",
                        match=MatchValue(value=page_id)
                    )
                ]
            )
            
            # Qdrant 的 delete 方法：points_selector 可以是 Filter 对象或点 ID 列表
            # 根据 Qdrant 1.7.0 版本，可以直接使用 Filter 对象
            self.client.delete(
                collection_name=collection_name,
                points_selector=filter_condition
            )
            # 等待删除操作完成（Qdrant 的 delete 是同步的，但为了确保一致性，稍作延迟）
            import asyncio
            await asyncio.sleep(0.1)  # 延迟 0.1 秒，确保删除操作完成
        except Exception as e:
            # 如果删除失败，记录日志但不抛出异常（避免影响后续的索引创建）
            print(f"[Indexer] 删除索引失败: item_id={item_id}, page_id={page_id}, error={e}")
    
    async def delete_item(self, item_id: int):
        """删除整个项目的索引（删除整个 Collection）"""
        collection_name = self._get_collection_name(item_id)
        
        try:
            # 检查 Collection 是否存在
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if collection_name in collection_names:
                # 删除整个 Collection
                self.client.delete_collection(collection_name)
                return True
            return False
        except Exception as e:
            print(f"删除项目索引失败: {e}")
            return False
    
    async def list_collections(self) -> List[str]:
        """列出所有 Collection 名称"""
        try:
            collections = self.client.get_collections().collections
            return [c.name for c in collections]
        except Exception as e:
            print(f"列出 Collection 失败: {e}")
            return []
    
    async def cleanup_orphaned_collections(self, valid_item_ids: List[int]) -> Dict[str, Any]:
        """
        清理孤立的 Collection（对应的 item 已不存在）
        
        Args:
            valid_item_ids: 有效的 item_id 列表
        
        Returns:
            清理结果统计
        """
        try:
            # 获取所有 Collection
            all_collections = await self.list_collections()
            
            # 构建有效的 Collection 名称集合
            valid_collection_names = {
                self._get_collection_name(item_id) 
                for item_id in valid_item_ids
            }
            
            # 找出孤立的 Collection（不在有效列表中的）
            orphaned_collections = []
            for collection_name in all_collections:
                # 检查是否匹配 collection 前缀
                if collection_name.startswith(self.collection_prefix):
                    if collection_name not in valid_collection_names:
                        orphaned_collections.append(collection_name)
            
            # 删除孤立的 Collection
            deleted_count = 0
            for collection_name in orphaned_collections:
                try:
                    self.client.delete_collection(collection_name)
                    deleted_count += 1
                except Exception as e:
                    print(f"删除孤立 Collection 失败 {collection_name}: {e}")
            
            return {
                "total_collections": len(all_collections),
                "valid_collections": len(valid_collection_names),
                "orphaned_collections": len(orphaned_collections),
                "deleted_count": deleted_count
            }
        except Exception as e:
            print(f"清理孤立 Collection 失败: {e}")
            return {
                "total_collections": 0,
                "valid_collections": 0,
                "orphaned_collections": 0,
                "deleted_count": 0,
                "error": str(e)
            }
    
    def _get_indexing_task_key(self, item_id: int) -> str:
        """获取索引任务 Redis 键名"""
        return f"ai_indexing_task:{item_id}"
    
    def _check_indexing_task(self, item_id: int) -> bool:
        """检查是否有正在进行的索引任务"""
        try:
            # 方法1：检查 Redis 中的任务标记（最可靠）
            task_key = self._get_indexing_task_key(item_id)
            task_exists = self.redis_client.exists(task_key)
            if task_exists:
                print(f"[Indexer] Redis 中发现索引任务标记: item_id={item_id}")
                return True
            
            # 方法2：使用 Celery inspect API 检查活跃任务（备用方案）
            try:
                from worker.celery_app import celery_app
                
                # 使用 Celery inspect API 检查活跃任务
                inspect = celery_app.control.inspect()
                
                # 获取所有活跃任务（正在执行的任务）
                active_tasks = inspect.active()
                if active_tasks:
                    # active_tasks 是一个字典，key 是 worker 名称，value 是任务列表
                    for worker_name, tasks in active_tasks.items():
                        for task in tasks:
                            # 检查是否是 rebuild_index 任务
                            task_name = task.get('name', '')
                            if task_name == 'rebuild_index' or task_name.endswith('.rebuild_index'):
                                # 从任务参数中提取 item_id
                                # Celery 任务参数可能存储在 args 或 kwargs 中
                                args = task.get('args', [])
                                kwargs = task.get('kwargs', {})
                                
                                # 检查 args 中的第一个参数（item_id）
                                if args and len(args) > 0 and args[0] == item_id:
                                    print(f"[Indexer] Celery 中发现正在进行的索引任务: item_id={item_id}, worker={worker_name}")
                                    return True
                                
                                # 检查 kwargs 中的 item_id
                                if kwargs.get('item_id') == item_id:
                                    print(f"[Indexer] Celery 中发现正在进行的索引任务: item_id={item_id}, worker={worker_name}")
                                    return True
                
                # 检查保留任务（已接收但未开始执行的任务）
                reserved_tasks = inspect.reserved()
                if reserved_tasks:
                    for worker_name, tasks in reserved_tasks.items():
                        for task in tasks:
                            task_name = task.get('name', '')
                            if task_name == 'rebuild_index' or task_name.endswith('.rebuild_index'):
                                args = task.get('args', [])
                                kwargs = task.get('kwargs', {})
                                
                                if args and len(args) > 0 and args[0] == item_id:
                                    print(f"[Indexer] Celery 中发现等待执行的索引任务: item_id={item_id}, worker={worker_name}")
                                    return True
                                
                                if kwargs.get('item_id') == item_id:
                                    print(f"[Indexer] Celery 中发现等待执行的索引任务: item_id={item_id}, worker={worker_name}")
                                    return True
            except Exception as celery_error:
                # Celery 检查失败不影响主流程
                print(f"[Indexer] Celery 检查失败（可能 worker 未运行）: {str(celery_error)}")
            
            return False
        except Exception as e:
            # 如果检查失败，不影响主流程
            print(f"[Indexer] 检查索引任务状态失败: {str(e)}")
            return False
    
    async def get_status(self, item_id: int) -> Dict[str, Any]:
        """获取索引状态"""
        collection_name = self._get_collection_name(item_id)
        
        # 先检查是否有正在进行的索引任务
        is_indexing = self._check_indexing_task(item_id)
        
        try:
            # 先列出所有 collection，检查是否存在
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            print(f"[Indexer] 查询索引状态: item_id={item_id}, collection={collection_name}, is_indexing={is_indexing}")
            print(f"[Indexer] 所有 collection: {collection_names}")
            
            if collection_name not in collection_names:
                print(f"[Indexer] Collection 不存在: {collection_name}")
                # 如果有正在进行的任务，返回 indexing 状态
                if is_indexing:
                    return {
                        "item_id": item_id,
                        "indexed": False,
                        "status": "indexing",
                        "document_count": 0,
                        "last_update_time": None
                    }
                return {
                    "item_id": item_id,
                    "indexed": False,
                    "status": "not_indexed",
                    "document_count": 0,
                    "last_update_time": None
                }
            
            # Collection 存在，使用 scroll 方法获取文档数量（避免 get_collection 的版本兼容问题）
            try:
                # 尝试使用 get_collection（如果版本兼容）
                collection_info = self.client.get_collection(collection_name)
                points_count = collection_info.points_count
            except Exception as e:
                # 如果 get_collection 失败（版本不兼容），使用 scroll 方法统计
                print(f"[Indexer] get_collection 失败，使用 scroll 方法统计: {str(e)}")
                # 使用 scroll 方法获取所有点，统计数量
                scroll_result = self.client.scroll(
                    collection_name=collection_name,
                    limit=0,  # limit=0 只返回总数，不返回实际数据
                    with_payload=False,
                    with_vectors=False
                )
                # scroll 方法返回 (points, next_page_offset)
                # 如果 next_page_offset 为 None，说明没有更多数据
                # 但我们需要统计总数，所以使用 count 方法
                count_result = self.client.count(
                    collection_name=collection_name
                )
                points_count = count_result.count
            
            print(f"[Indexer] 获取索引状态成功: item_id={item_id}, collection={collection_name}, points_count={points_count}, is_indexing={is_indexing}")
            
            # 如果有正在进行的任务，返回 indexing 状态（即使 collection 已存在）
            if is_indexing:
                return {
                    "item_id": item_id,
                    "indexed": True,  # collection 存在，但还在索引中
                    "status": "indexing",
                    "document_count": points_count,
                    "last_update_time": None
                }
            
            return {
                "item_id": item_id,
                "indexed": True,
                "status": "indexed",
                "document_count": points_count,
                "last_update_time": None  # Qdrant 不直接提供，需要额外记录
            }
        except Exception as e:
            print(f"[Indexer] 获取索引状态失败: item_id={item_id}, collection={collection_name}, error={str(e)}")
            import traceback
            traceback.print_exc()
            # 如果有正在进行的任务，即使出错也返回 indexing 状态
            if is_indexing:
                return {
                    "item_id": item_id,
                    "indexed": False,
                    "status": "indexing",
                    "document_count": 0,
                    "last_update_time": None
                }
            return {
                "item_id": item_id,
                "indexed": False,
                "status": "not_indexed",
                "document_count": 0,
                "last_update_time": None
            }
    
    async def cleanup_unused_indexes(self, days: int = 365) -> Dict[str, Any]:
        """
        清理超过指定天数未访问的项目索引
        
        Args:
            days: 未访问天数，默认 365 天（1年）
        
        Returns:
            清理结果统计
        """
        try:
            # 获取所有 Collection
            all_collections = await self.list_collections()
            
            # 计算过期时间戳
            expire_timestamp = int(time.time()) - (days * 24 * 60 * 60)
            
            deleted_count = 0
            skipped_count = 0
            error_count = 0
            deleted_items = []
            
            for collection_name in all_collections:
                # 只处理匹配前缀的 Collection
                if not collection_name.startswith(self.collection_prefix):
                    continue
                
                # 从 Collection 名称中提取 item_id
                try:
                    item_id_str = collection_name.replace(self.collection_prefix, "")
                    item_id = int(item_id_str)
                except (ValueError, AttributeError):
                    # 如果无法解析 item_id，跳过
                    continue
                
                # 获取最后访问时间
                access_time = self.get_access_time(item_id)
                
                if access_time is None:
                    # 如果没有访问记录，检查 Collection 的创建时间（如果可能）
                    # 由于 Qdrant 不直接提供创建时间，我们假设没有访问记录的就是过期了
                    # 但为了安全，我们跳过没有访问记录的项目（可能是新创建的）
                    print(f"[Cleanup] 跳过没有访问记录的项目: item_id={item_id}")
                    skipped_count += 1
                    continue
                
                # 检查是否过期
                if access_time < expire_timestamp:
                    try:
                        # 删除 Collection
                        self.client.delete_collection(collection_name)
                        # 删除 Redis 中的访问时间记录
                        self.redis_client.delete(self._get_access_time_key(item_id))
                        deleted_count += 1
                        deleted_items.append(item_id)
                        print(f"[Cleanup] 删除过期索引: item_id={item_id}, collection={collection_name}, 最后访问时间={access_time}")
                    except Exception as e:
                        error_count += 1
                        print(f"[Cleanup] 删除索引失败: item_id={item_id}, collection={collection_name}, error={str(e)}")
            
            return {
                "status": "success",
                "total_collections": len(all_collections),
                "deleted_count": deleted_count,
                "skipped_count": skipped_count,
                "error_count": error_count,
                "deleted_items": deleted_items[:50],  # 只返回前50个，避免响应过大
                "expire_days": days,
                "expire_timestamp": expire_timestamp
            }
        except Exception as e:
            print(f"[Cleanup] 清理过期索引失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "deleted_count": 0,
                "skipped_count": 0,
                "error_count": 0
            }

