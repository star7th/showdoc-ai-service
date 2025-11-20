"""
RAG 检索引擎
"""
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# 延迟加载配置和 EmbeddingService，避免模块导入时初始化
_settings = None
def _get_settings():
    """延迟获取配置"""
    global _settings
    if _settings is None:
        from app.config import get_settings
        _settings = get_settings()
    return _settings


class HybridRetriever:
    """混合检索引擎（向量 + 关键词）"""
    
    def __init__(self):
        settings = _get_settings()
        self.client = QdrantClient(url=settings.qdrant_url)
        # 延迟导入 EmbeddingService，避免循环导入和启动时初始化
        from app.utils.embedding import EmbeddingService
        self.embedding_service = EmbeddingService()
        self.collection_prefix = settings.qdrant_collection_prefix
    
    def _get_collection_name(self, item_id: int) -> str:
        """获取 Collection 名称"""
        return f"{self.collection_prefix}{item_id}"
    
    async def retrieve(
        self,
        query: str,
        item_id: int,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        通用的混合检索策略
        适用于所有类型的 Markdown 文档
        支持标题匹配：如果查询与页面标题相关，会优先返回该页面的内容
        """
        collection_name = self._get_collection_name(item_id)
        
        # 检测查询是否可能是标题相关的查询
        is_title_query = self._is_title_query(query)
        
        try:
            # 1. 向量检索（语义相似度）
            # 如果可能是标题查询，增强查询文本，包含标题信息提示
            enhanced_query = query
            if is_title_query:
                # 增强查询，提示模型关注标题匹配
                enhanced_query = f"标题或页面名称：{query}"
            
            print(f"[Retriever] 开始检索，item_id: {item_id}, collection: {collection_name}, query: {query[:50]}...")
            query_vector = await self.embedding_service.embed(enhanced_query)
            print(f"[Retriever] Embedding 生成成功，向量维度: {len(query_vector)}")
        except Exception as e:
            error_msg = f"生成查询向量失败: {str(e)}"
            print(f"[Retriever] {error_msg}")
            import traceback
            print(f"[Retriever] 错误详情: {traceback.format_exc()}")
            raise RuntimeError(error_msg) from e
        
        # 搜索向量
        query_response = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k * 2,  # 多取一些，后续融合排序
            with_payload=True
        )
        # query_points 返回 QueryResponse 对象，需要访问 .points 属性
        search_results = query_response.points if hasattr(query_response, 'points') else query_response
        
        # 2. 关键词检索（简单实现：在向量结果基础上进行关键词匹配）
        # 注意：完整实现应该使用 BM25，这里简化处理
        # 关键词检索会同时检查标题和内容
        keyword_results = self._keyword_search(query, item_id, top_k * 2)
        
        # 3. 结果融合与重排序
        merged_results = self._merge_and_rerank(
            vector_results=search_results,
            keyword_results=keyword_results,
            query=query
        )
        
        # 转换为标准格式
        results = []
        for result in merged_results[:top_k]:
            payload = result.payload if hasattr(result, 'payload') else result
            results.append({
                "page_id": payload.get("page_id"),
                "page_title": payload.get("page_title"),
                "content": payload.get("chunk_content", ""),
                "relevance": result.score if hasattr(result, 'score') else 0.0,
                "metadata": payload
            })
        
        return results
    
    def _keyword_search(self, query: str, item_id: int, top_k: int) -> List:
        """
        关键词检索（简化实现，优化内存使用）
        同时检查标题和内容，标题匹配给予更高权重
        """
        # 注意：完整实现应该使用 BM25 算法
        # 这里简化处理，使用 Qdrant 的 scroll 和过滤
        collection_name = self._get_collection_name(item_id)
        
        # 提取关键词（简单分词，支持中文）
        import re
        # 简单的中英文分词
        keywords = re.findall(r'\w+|[^\w\s]', query)
        keywords = [k for k in keywords if len(k) > 1][:3]  # 限制关键词数量
        
        if not keywords:
            return []
        
        try:
            # 使用 scroll 分页获取所有点，然后过滤
            # 注意：对于大数据集，应该使用 BM25 或全文索引
            from qdrant_client.models import ScrollRequest
            
            # 在内存中过滤包含关键词的点（流式处理，避免一次性加载所有数据）
            results = []
            keywords_lower = [k.lower() for k in keywords]  # 预处理关键词，避免重复转换
            query_lower = query.lower()  # 完整查询文本（用于标题匹配）
            
            # 分页滚动获取所有点，避免内存问题
            scroll_limit = 1000  # 每次滚动获取 1000 个点
            next_page_offset = None
            max_scroll_pages = 100  # 最多滚动 100 页，避免无限循环（10万条数据）
            scroll_page_count = 0
            
            while scroll_page_count < max_scroll_pages:
                # 滚动获取一批点
                scroll_result = self.client.scroll(
                    collection_name=collection_name,
                    limit=scroll_limit,
                    offset=next_page_offset,
                    with_payload=True,
                    with_vectors=False  # 不需要向量，节省内存
                )
                
                points, next_page_offset = scroll_result
                
                # 如果没有更多数据，退出循环
                if not points:
                    break
                
                # 处理这一批点
                for point in points:
                    payload = point.payload
                    content = payload.get("chunk_content", "").lower()
                    page_title = payload.get("page_title", "").lower()
                    
                    score = 0.0
                    matched_in_title = False
                    matched_in_content = False
                    
                    # 检查标题匹配（给予更高权重）
                    if page_title:
                        # 完整标题匹配（最高权重）
                        if query_lower in page_title or page_title in query_lower:
                            score += 100.0  # 标题完全匹配，给予很高分数
                            matched_in_title = True
                        # 标题包含关键词
                        elif any(keyword in page_title for keyword in keywords_lower):
                            score += 50.0  # 标题关键词匹配，给予较高分数
                            matched_in_title = True
                    
                    # 检查内容匹配
                    if any(keyword in content for keyword in keywords_lower):
                        # 计算内容匹配度（关键词出现次数）
                        content_score = sum(content.count(keyword) for keyword in keywords_lower)
                        score += content_score
                        matched_in_content = True
                    
                    # 如果标题或内容有匹配，添加到结果中
                    if matched_in_title or matched_in_content:
                        # 创建类似 search 结果的对象
                        class SimpleResult:
                            def __init__(self, point, score):
                                self.id = point.id
                                self.payload = point.payload
                                self.score = float(score) / 100.0  # 归一化分数
                        
                        results.append(SimpleResult(point, score))
                        
                        # 如果结果已经足够，提前退出（优化内存）
                        if len(results) >= top_k * 10:  # 多收集一些，后续排序筛选
                            break
                
                # 如果已经收集到足够的结果，提前退出
                if len(results) >= top_k * 10:
                    break
                
                # 如果没有更多页面，退出循环
                if next_page_offset is None:
                    break
                
                scroll_page_count += 1
            
            # 按分数排序
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]
        except Exception as e:
            print(f"关键词检索失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _merge_and_rerank(
        self,
        vector_results: List,
        keyword_results: List,
        query: str
    ) -> List:
        """
        结果融合与重排序
        如果标题匹配，会提升相关度分数
        """
        # 简单的融合策略：优先向量结果，关键词结果作为补充
        merged = {}
        query_lower = query.lower()
        
        # 添加向量结果
        for result in vector_results:
            payload = result.payload
            page_id = payload.get("page_id")
            chunk_id = payload.get("chunk_id", 0)
            key = f"{page_id}_{chunk_id}"
            
            if key not in merged:
                # 检查标题匹配，如果匹配则提升分数
                page_title = payload.get("page_title", "").lower()
                if page_title and (query_lower in page_title or page_title in query_lower):
                    # 标题完全匹配，大幅提升分数
                    if hasattr(result, 'score'):
                        result.score = min(result.score * 1.5, 1.0)  # 提升50%，但不超过1.0
                    else:
                        result.score = 0.9
                elif page_title and any(kw in page_title for kw in query_lower.split() if len(kw) > 1):
                    # 标题部分匹配，适度提升分数
                    if hasattr(result, 'score'):
                        result.score = min(result.score * 1.2, 1.0)  # 提升20%，但不超过1.0
                
                merged[key] = result
        
        # 添加关键词结果（如果不在向量结果中）
        for result in keyword_results:
            payload = result.payload
            page_id = payload.get("page_id")
            chunk_id = payload.get("chunk_id", 0)
            key = f"{page_id}_{chunk_id}"
            
            if key not in merged:
                # 关键词结果如果标题匹配，给予更高权重
                page_title = payload.get("page_title", "").lower()
                if page_title and (query_lower in page_title or page_title in query_lower):
                    # 标题完全匹配，给予较高分数
                    result.score = 0.8 if hasattr(result, 'score') else 0.8
                else:
                    # 降低关键词结果的权重
                    result.score = result.score * 0.7 if hasattr(result, 'score') else 0.5
                merged[key] = result
        
        # 按分数排序
        sorted_results = sorted(
            merged.values(),
            key=lambda x: x.score if hasattr(x, 'score') else 0.0,
            reverse=True
        )
        
        return sorted_results
    
    def _is_title_query(self, query: str) -> bool:
        """
        检测查询是否可能是标题相关的查询
        
        判断标准：
        1. 查询较短（通常标题不会太长）
        2. 不包含问句关键词（如"如何"、"什么"、"为什么"等）
        3. 不包含明显的描述性词汇
        """
        query = query.strip()
        
        # 如果查询太长，不太可能是标题查询
        if len(query) > 50:
            return False
        
        # 问句关键词
        question_keywords = ["如何", "怎么", "什么", "为什么", "怎样", "哪个", "哪些", 
                            "how", "what", "why", "when", "where", "which", "who"]
        query_lower = query.lower()
        if any(kw in query_lower for kw in question_keywords):
            return False
        
        # 描述性词汇（通常用于内容查询）
        descriptive_keywords = ["说明", "介绍", "详细", "步骤", "方法", "流程", 
                               "explain", "describe", "detail", "step", "method"]
        if any(kw in query_lower for kw in descriptive_keywords):
            return False
        
        # 如果查询较短且不包含问句和描述性词汇，可能是标题查询
        if len(query) <= 30:
            return True
        
        return False

