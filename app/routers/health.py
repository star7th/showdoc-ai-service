"""
健康检查接口
"""
from fastapi import APIRouter
from app.config import get_settings
import httpx
import os

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """健康检查"""
    # 检查模型服务健康状态
    model_service_status = None
    try:
        model_service_url = os.getenv("MODEL_SERVICE_URL", "http://model-service:7126")
        model_service_url = model_service_url.rstrip('/')
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{model_service_url}/health")
            response.raise_for_status()
            model_service_status = response.json()
    except Exception as e:
        model_service_status = {"error": str(e), "status": "unhealthy"}
    
    return {
        "status": "ok",
        "version": settings.version,
        "service": settings.service_name,
        "vector_db": "qdrant",
        "llm_provider": "configured",  # 实际应从 LLM 配置读取
        "model_service": model_service_status
    }

