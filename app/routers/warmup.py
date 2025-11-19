"""
模型服务健康检查接口
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
import httpx
import os

router = APIRouter()


async def verify_token(authorization: str = Header(None)):
    """验证服务 Token"""
    from app.config import get_settings
    settings = get_settings()
    
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
    
    调用模型服务的预热接口，重新加载模型到内存中。
    如果模型已经加载，会先卸载再重新加载。
    """
    import time
    start_time = time.time()
    
    try:
        # 获取模型服务地址
        model_service_url = os.getenv("MODEL_SERVICE_URL", "http://model-service:7126")
        model_service_url = model_service_url.rstrip('/')
        
        # 调用模型服务的预热接口
        # 使用同步客户端并通过 asyncio.to_thread 运行，避免阻塞事件循环
        def _sync_warmup():
            with httpx.Client(timeout=300.0) as client:  # 5分钟超时，模型加载可能需要时间
                response = client.post(f"{model_service_url}/warmup")
                response.raise_for_status()
                return response.json()
        
        try:
            import asyncio
            # 使用 asyncio.to_thread 在异步上下文中运行同步调用
            try:
                warmup_data = await asyncio.to_thread(_sync_warmup)
            except AttributeError:
                # Python < 3.9 兼容
                loop = asyncio.get_event_loop()
                warmup_data = await loop.run_in_executor(None, _sync_warmup)
                
                elapsed = time.time() - start_time
                print(f"[Warmup] 模型预热成功 (耗时: {elapsed:.2f}秒)")
                
                return JSONResponse(
                    content={
                        "status": "success",
                        "message": warmup_data.get("message", "模型已成功加载到内存"),
                        "model_loaded": warmup_data.get("model_loaded", False),
                        "model_name": warmup_data.get("model_name"),
                        "dimension": warmup_data.get("dimension"),
                        "elapsed_seconds": round(elapsed, 2)
                    },
                    media_type="application/json; charset=utf-8"
                )
        except httpx.RequestError as e:
            elapsed = time.time() - start_time
            print(f"[Warmup] ❌ 模型服务连接失败: {str(e)} (耗时: {elapsed:.2f}秒)")
            return JSONResponse(
                content={
                    "status": "error",
                    "message": f"模型服务连接失败: {str(e)}",
                    "model_service_url": model_service_url,
                    "elapsed_seconds": round(elapsed, 2)
                },
                media_type="application/json; charset=utf-8",
                status_code=503
            )
        except httpx.HTTPStatusError as e:
            elapsed = time.time() - start_time
            print(f"[Warmup] ❌ 模型预热失败 (HTTP {e.response.status_code}): {e.response.text} (耗时: {elapsed:.2f}秒)")
            return JSONResponse(
                content={
                    "status": "error",
                    "message": f"模型预热失败: HTTP {e.response.status_code}",
                    "model_service_url": model_service_url,
                    "elapsed_seconds": round(elapsed, 2)
                },
                media_type="application/json; charset=utf-8",
                status_code=503
            )
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[Warmup] ❌ 预热失败: {str(e)} (耗时: {elapsed:.2f}秒)")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"预热失败: {str(e)}")

