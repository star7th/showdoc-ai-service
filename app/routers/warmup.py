"""
模型预热接口
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from app.config import get_settings

router = APIRouter()
settings = get_settings()


async def verify_token(authorization: str = Header(None)):
    """验证服务 Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization 头")
    
    token = authorization.replace("Bearer ", "").strip()
    if token != settings.service_token:
        raise HTTPException(status_code=403, detail="Token 无效")
    return token


@router.post("/warmup")
async def warmup_model(token: str = Depends(verify_token)):
    """
    预热模型接口
    
    如果模型已经加载到内存中，则直接返回成功。
    如果模型未加载，则加载模型到内存中。
    
    这样可以提前加载模型，避免用户首次对话时的延迟。
    """
    try:
        from app.utils.embedding import EmbeddingService
        
        embedding_service = EmbeddingService()
        
        # 如果使用 API 模式（openai/qwen），模型不需要本地加载，直接返回成功
        if embedding_service.provider in ['openai', 'qwen']:
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "使用 API 模式，无需加载本地模型",
                    "model_loaded": True,
                    "provider": embedding_service.provider
                },
                media_type="application/json; charset=utf-8"
            )
        
        # 检查本地模型是否已加载
        if embedding_service._model_loaded and embedding_service.model is not None:
            return JSONResponse(
                content={
                    "status": "success",
                    "message": "模型已在内存中",
                    "model_loaded": True,
                    "model_name": embedding_service.model_name
                },
                media_type="application/json; charset=utf-8"
            )
        
        # 如果模型未加载，则加载模型
        try:
            embedding_service._init_model()
            
            # 再次检查模型是否成功加载
            if embedding_service._model_loaded and embedding_service.model is not None:
                return JSONResponse(
                    content={
                        "status": "success",
                        "message": "模型已成功加载到内存",
                        "model_loaded": True,
                        "model_name": embedding_service.model_name
                    },
                    media_type="application/json; charset=utf-8"
                )
            else:
                return JSONResponse(
                    content={
                        "status": "error",
                        "message": "模型加载失败",
                        "model_loaded": False
                    },
                    media_type="application/json; charset=utf-8"
                )
        except Exception as e:
            return JSONResponse(
                content={
                    "status": "error",
                    "message": f"模型加载失败: {str(e)}",
                    "model_loaded": False
                },
                media_type="application/json; charset=utf-8"
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预热失败: {str(e)}")

