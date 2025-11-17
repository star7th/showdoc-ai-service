"""
健康检查接口
"""
from fastapi import APIRouter
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """健康检查"""
    # 尝试获取内存信息（如果 EmbeddingService 已初始化）
    memory_info = None
    try:
        # 延迟导入，避免启动时初始化
        from app.utils.embedding import EmbeddingService
        # 创建一个临时实例来获取内存信息（不会加载模型）
        embedding_service = EmbeddingService()
        memory_info = embedding_service.get_memory_info()
    except Exception as e:
        memory_info = {"error": str(e)}
    
    return {
        "status": "ok",
        "version": settings.version,
        "service": settings.service_name,
        "vector_db": "qdrant",
        "llm_provider": "configured",  # 实际应从 LLM 配置读取
        "memory": memory_info
    }

