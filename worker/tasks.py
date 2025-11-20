"""
Celery 异步任务
"""
import asyncio
from worker.celery_app import celery_app
from celery.schedules import crontab

# 延迟导入 Indexer，避免启动时初始化 EmbeddingService
# from app.services.indexer import Indexer


@celery_app.task(name="index_document")
def index_document_task(
    item_id: int,
    page_id: int,
    page_title: str,
    page_content: str,
    page_type: str = "regular",
    metadata: dict = None
):
    """索引文档任务（异步）"""
    # 延迟导入，避免启动时初始化
    from app.services.indexer import Indexer
    indexer = Indexer()
    
    # 运行异步函数
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            indexer.upsert_document(
                item_id=item_id,
                page_id=page_id,
                page_title=page_title,
                page_content=page_content,
                page_type=page_type,
                metadata=metadata or {}
            )
        )
    finally:
        loop.close()
        # 显式触发垃圾回收，释放内存
        import gc
        gc.collect()
    
    return {"status": "success", "item_id": item_id, "page_id": page_id}


@celery_app.task(name="rebuild_index")
def rebuild_index_task(item_id: int, pages: list):
    """批量重建索引任务"""
    import gc
    import time
    
    # 延迟导入，避免启动时初始化
    from app.services.indexer import Indexer
    indexer = Indexer()
    
    # 获取任务标记的 Redis 键名
    task_key = f"ai_indexing_task:{item_id}"
    redis_client = indexer.redis_client
    
    print(f"[RebuildIndex] 开始重建索引: item_id={item_id}, 页面总数={len(pages)}")
    
    # 在 Redis 中设置任务标记（TTL 设置为 2 小时，防止任务异常退出导致标记残留）
    try:
        redis_client.set(task_key, int(time.time()), ttl=2 * 60 * 60)
        print(f"[RebuildIndex] 已设置任务标记: {task_key}")
    except Exception as e:
        print(f"[RebuildIndex] 设置任务标记失败: {str(e)}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 确保 Collection 存在（会自动记录访问时间）
        loop.run_until_complete(indexer.ensure_collection(item_id))
        # 重建索引时也记录访问时间
        indexer.record_access_time(item_id)
        
        # 批量索引
        success_count = 0
        skip_count = 0
        error_count = 0
        error_pages = []  # 记录失败的页面
        
        for idx, page in enumerate(pages):
            page_id = page.get("page_id")
            page_title = page.get("page_title", "")
            page_content = page.get("page_content")
            
            # 每处理 100 个页面输出一次进度
            if (idx + 1) % 100 == 0:
                print(f"[RebuildIndex] 进度: {idx + 1}/{len(pages)}, 成功={success_count}, 跳过={skip_count}, 失败={error_count}")
            
            # 跳过空内容的页面
            if not page_content or not isinstance(page_content, str) or not page_content.strip():
                print(f"[RebuildIndex] 跳过空内容页面: page_id={page_id}, title={page_title}")
                skip_count += 1
                continue
            
            try:
                loop.run_until_complete(
                    indexer.upsert_document(
                        item_id=item_id,
                        page_id=page_id,
                        page_title=page_title,
                        page_content=page_content,
                        page_type=page.get("page_type", "regular"),
                        metadata=page.get("metadata", {})
                    )
                )
                success_count += 1
            except Exception as e:
                error_count += 1
                error_pages.append({
                    "page_id": page_id,
                    "page_title": page_title,
                    "error": str(e)
                })
                print(f"[RebuildIndex] 索引页面失败: page_id={page_id}, title={page_title}, error={str(e)}")
                import traceback
                traceback.print_exc()
        
        print(f"[RebuildIndex] 完成: 成功={success_count}, 跳过={skip_count}, 失败={error_count}, 总计={len(pages)}")
        if error_pages:
            print(f"[RebuildIndex] 失败的页面列表（前10个）: {error_pages[:10]}")
    finally:
        loop.close()
        # 显式触发垃圾回收，释放内存
        import gc
        gc.collect()
        
        # 任务完成，删除 Redis 中的任务标记
        try:
            redis_client.delete(task_key)
            print(f"[RebuildIndex] 已删除任务标记: {task_key}")
        except Exception as e:
            print(f"[RebuildIndex] 删除任务标记失败: {str(e)}")
    
    return {
        "status": "success", 
        "item_id": item_id, 
        "total": len(pages),
        "success": success_count,
        "skipped": skip_count,
        "error": error_count,
        "error_pages": error_pages[:20]  # 返回前20个失败的页面信息
    }


@celery_app.task(name="cleanup_unused_indexes")
def cleanup_unused_indexes_task(days: int = 365):
    """清理超过指定天数未访问的项目索引（定时任务）"""
    # 延迟导入，避免启动时初始化
    from app.services.indexer import Indexer
    indexer = Indexer()
    
    print(f"[CleanupUnusedIndexes] 开始清理超过 {days} 天未访问的索引...")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(indexer.cleanup_unused_indexes(days=days))
        print(f"[CleanupUnusedIndexes] 清理完成: {result}")
        return result
    finally:
        loop.close()
    
    return {"status": "success", "message": "清理任务已完成"}

