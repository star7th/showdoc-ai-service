"""
Pydantic 数据模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class ChatRequest(BaseModel):
    """对话请求"""
    item_id: int = Field(..., description="项目ID")
    user_id: Optional[int] = Field(None, description="用户ID")
    conversation_id: Optional[str] = Field(None, description="对话ID")
    question: str = Field(..., description="用户问题")
    stream: bool = Field(False, description="是否流式返回")


class SourceInfo(BaseModel):
    """引用来源信息"""
    page_id: int
    page_title: str
    relevance: float
    snippet: str
    url: Optional[str] = None


class UsageInfo(BaseModel):
    """Token 使用信息"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """对话响应"""
    conversation_id: str
    answer: str
    sources: List[SourceInfo] = []
    usage: Optional[UsageInfo] = None


class StreamChatChunk(BaseModel):
    """流式对话数据块"""
    type: str = Field(..., description="类型: token/sources/done/error")
    content: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    message: Optional[str] = None


class StreamChatResponse(BaseModel):
    """流式对话响应（用于序列化）"""
    type: str
    content: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    message: Optional[str] = None


# 索引相关模型
class IndexUpsertRequest(BaseModel):
    """创建/更新索引请求"""
    item_id: int
    page_id: int
    page_title: str
    page_content: str
    page_type: str = "regular"  # regular/api/table/...
    metadata: Dict[str, Any] = {}


class IndexDeleteRequest(BaseModel):
    """删除索引请求"""
    item_id: int
    page_id: int


class IndexDeleteItemRequest(BaseModel):
    """删除整个项目索引请求"""
    item_id: int


class IndexRebuildRequest(BaseModel):
    """重建索引请求"""
    item_id: int
    pages: List[Dict[str, Any]]  # 页面列表


class IndexStatusResponse(BaseModel):
    """索引状态响应"""
    item_id: int
    indexed: bool
    status: str = "not_indexed"  # 'indexed'/'indexing'/'not_indexed'
    document_count: int = 0
    last_update_time: Optional[str] = None


class IndexCleanupRequest(BaseModel):
    """清理孤立索引请求"""
    valid_item_ids: List[int] = Field(..., description="有效的 item_id 列表")

