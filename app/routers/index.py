"""
索引管理接口
"""
import sys
import traceback
from fastapi import APIRouter, HTTPException, Header, Depends

print("[index.py] 开始加载索引管理路由模块...")

try:
    from app.models.schemas import (
        IndexUpsertRequest,
        IndexDeleteRequest,
        IndexDeleteItemRequest,
        IndexRebuildRequest,
        IndexStatusResponse,
        IndexCleanupRequest
    )
    print("[index.py] ✓ 数据模型加载成功")
except Exception as e:
    print(f"[index.py] ✗ 数据模型加载失败: {e}")
    traceback.print_exc()
    raise

try:
    from app.config import get_settings
    settings = get_settings()
    print("[index.py] ✓ 配置加载成功")
except Exception as e:
    print(f"[index.py] ✗ 配置加载失败: {e}")
    traceback.print_exc()
    raise

try:
    from worker.tasks import index_document_task, rebuild_index_task
    print("[index.py] ✓ Celery 任务加载成功")
except Exception as e:
    print(f"[index.py] ✗ Celery 任务加载失败: {e}")
    traceback.print_exc()
    raise

# 延迟导入 Indexer，避免启动时初始化
# from app.services.indexer import Indexer

router = APIRouter()
print("[index.py] ✓ 路由创建成功")


async def verify_token(authorization: str = Header(None)):
    """验证服务 Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization 头")
    
    token = authorization.replace("Bearer ", "").strip()
    if token != settings.service_token:
        raise HTTPException(status_code=403, detail="Token 无效")
    return token


@router.post("/index/upsert")
async def upsert_index(
    request: IndexUpsertRequest,
    token: str = Depends(verify_token)
):
    """创建/更新文档索引"""
    try:
        # 异步任务处理
        task = index_document_task.delay(
            item_id=request.item_id,
            page_id=request.page_id,
            page_title=request.page_title,
            page_content=request.page_content,
            page_type=request.page_type,
            metadata=request.metadata
        )
        return {
            "status": "success",
            "message": "索引任务已提交",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/index/delete")
async def delete_index(
    request: IndexDeleteRequest,
    token: str = Depends(verify_token)
):
    """删除文档索引"""
    try:
        # 延迟导入，避免启动时初始化
        from app.services.indexer import Indexer
        indexer = Indexer()
        await indexer.delete_document(
            item_id=request.item_id,
            page_id=request.page_id
        )
        return {"status": "success", "message": "索引已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/rebuild")
async def rebuild_index(
    request: IndexRebuildRequest,
    token: str = Depends(verify_token)
):
    """批量重建索引"""
    try:
        task = rebuild_index_task.delay(
            item_id=request.item_id,
            pages=request.pages
        )
        return {
            "status": "success",
            "message": "重建索引任务已提交",
            "task_id": task.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/index/delete-item")
async def delete_item_index(
    request: IndexDeleteItemRequest,
    token: str = Depends(verify_token)
):
    """删除整个项目的索引"""
    try:
        # 延迟导入，避免启动时初始化
        from app.services.indexer import Indexer
        indexer = Indexer()
        result = await indexer.delete_item(request.item_id)
        if result:
            return {"status": "success", "message": "项目索引已删除"}
        else:
            return {"status": "success", "message": "项目索引不存在或已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/cleanup")
async def cleanup_orphaned_indexes(
    request: IndexCleanupRequest,
    token: str = Depends(verify_token)
):
    """清理孤立的索引（对应的 item 已不存在）"""
    try:
        # 延迟导入，避免启动时初始化
        from app.services.indexer import Indexer
        indexer = Indexer()
        result = await indexer.cleanup_orphaned_collections(request.valid_item_ids)
        return {
            "status": "success",
            "message": "清理完成",
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/status", response_model=IndexStatusResponse)
async def get_index_status(
    item_id: int,
    token: str = Depends(verify_token)
):
    """查询索引状态"""
    try:
        # 延迟导入，避免启动时初始化
        from app.services.indexer import Indexer
        indexer = Indexer()
        # 记录访问时间
        indexer.record_access_time(item_id)
        status = await indexer.get_status(item_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/cleanup-unused")
async def cleanup_unused_indexes(
    days: int = 365,
    token: str = Depends(verify_token)
):
    """清理超过指定天数未访问的项目索引"""
    try:
        # 延迟导入，避免启动时初始化
        from app.services.indexer import Indexer
        indexer = Indexer()
        result = await indexer.cleanup_unused_indexes(days=days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

