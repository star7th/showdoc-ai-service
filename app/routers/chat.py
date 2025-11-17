"""
对话接口
"""
import json
import sys
import traceback
from fastapi import APIRouter, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from typing import Optional

print("[chat.py] 开始加载对话路由模块...")

try:
    from app.models.schemas import ChatRequest, ChatResponse, StreamChatResponse
    print("[chat.py] ✓ 数据模型加载成功")
except Exception as e:
    print(f"[chat.py] ✗ 数据模型加载失败: {e}")
    traceback.print_exc()
    raise

try:
    from app.config import get_settings
    settings = get_settings()
    print("[chat.py] ✓ 配置加载成功")
except Exception as e:
    print(f"[chat.py] ✗ 配置加载失败: {e}")
    traceback.print_exc()
    raise

# 延迟导入 ConversationManager，避免启动时初始化
# from app.services.conversation import ConversationManager

router = APIRouter()
print("[chat.py] ✓ 路由创建成功")


async def verify_token(authorization: str = Header(None)):
    """验证服务 Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization 头")
    
    token = authorization.replace("Bearer ", "").strip()
    if token != settings.service_token:
        raise HTTPException(status_code=403, detail="Token 无效")
    return token


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    token: str = Depends(verify_token)
):
    """对话接口（非流式）"""
    try:
        # 记录访问时间
        try:
            from app.services.indexer import Indexer
            indexer = Indexer()
            indexer.record_access_time(request.item_id)
        except Exception as e:
            print(f"记录访问时间失败: {e}")
        
        # 延迟导入，避免启动时初始化
        from app.services.conversation import ConversationManager
        manager = ConversationManager()
        result = await manager.chat(
            item_id=request.item_id,
            user_id=request.user_id,
            question=request.question,
            conversation_id=request.conversation_id,
            stream=False
        )
        # 使用 JSONResponse 确保 UTF-8 编码
        return JSONResponse(
            content=result.model_dump() if hasattr(result, 'model_dump') else result.dict(),
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    token: str = Depends(verify_token)
):
    """对话接口（流式）"""
    from fastapi.responses import StreamingResponse
    
    async def generate():
        try:
            # 记录访问时间
            try:
                from app.services.indexer import Indexer
                indexer = Indexer()
                indexer.record_access_time(request.item_id)
            except Exception as e:
                print(f"记录访问时间失败: {e}")
            
            # 延迟导入，避免启动时初始化
            from app.services.conversation import ConversationManager
            manager = ConversationManager()
            first_chunk = True
            async for chunk in manager.chat_stream(
                item_id=request.item_id,
                user_id=request.user_id,
                question=request.question,
                conversation_id=request.conversation_id
            ):
                # 使用 model_dump_json 或 json() 方法序列化
                chunk_dict = chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk.dict()
                json_str = json.dumps(chunk_dict, ensure_ascii=False)
                
                # 第一个 chunk 标记
                if first_chunk and chunk_dict.get('type') == 'token' and chunk_dict.get('content'):
                    first_chunk = False
                
                yield f"data: {json_str}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
        except Exception as e:
            error_msg = json.dumps({
                "type": "error",
                "message": str(e)
            }, ensure_ascii=False)
            yield f"data: {error_msg}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

