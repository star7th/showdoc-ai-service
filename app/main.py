"""
FastAPI 主应用入口
"""
import sys
import traceback
import logging
import signal
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 配置日志，确保输出到标准输出（必须在 signal_handler 之前）
# 精简日志格式，只显示关键信息
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 过滤第三方库的冗余日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# 捕获段错误信号，输出调试信息
def signal_handler(signum, frame):
    """信号处理器"""
    logger.error(f"收到信号 {signum}，准备退出...")
    logger.error(f"堆栈跟踪：")
    traceback.print_stack(frame)
    sys.stdout.flush()
    sys.exit(1)

# 注册信号处理器（捕获 SIGSEGV）
# 注意：SIGSEGV 在某些系统上可能无法捕获，但尝试捕获它
try:
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    # SIGSEGV 在某些系统上可能无法捕获
    if hasattr(signal, 'SIGSEGV'):
        signal.signal(signal.SIGSEGV, signal_handler)
except Exception as e:
    logger.warning(f"无法注册某些信号处理器: {e}")

# 强制刷新输出
sys.stdout.flush()
sys.stderr.flush()

# 精简启动日志，只显示关键信息
try:
    from app.config import get_settings
    settings = get_settings()
except Exception as e:
    logger.error(f"配置加载失败: {e}")
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)

try:
    from app.routers import chat, index, health, warmup
except Exception as e:
    logger.error(f"路由模块加载失败: {e}")
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)

try:
    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        description="ShowDoc AI 知识库服务",
    )
except Exception as e:
    logger.error(f"FastAPI 应用创建失败: {e}")
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)

try:
    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception as e:
    logger.error(f"CORS 中间件配置失败: {e}")
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)

try:
    # 注册路由
    app.include_router(health.router, prefix="/api", tags=["健康检查"])
    app.include_router(chat.router, prefix="/api", tags=["对话"])
    app.include_router(index.router, prefix="/api", tags=["索引管理"])
    app.include_router(warmup.router, prefix="/api", tags=["模型预热"])
except Exception as e:
    logger.error(f"路由注册失败: {e}")
    traceback.print_exc()
    sys.stdout.flush()
    sys.exit(1)


@app.on_event("startup")
async def startup_event():
    """启动事件（精简日志版本）"""
    try:
        logger.info(f"{settings.service_name} v{settings.version} 启动成功")
        
        # 启动后台任务：定期检查并卸载空闲模型
        import asyncio
        asyncio.create_task(periodic_memory_cleanup())
        
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"启动事件执行失败: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        # 不抛出异常，允许服务继续启动
        logger.warning("启动事件有错误，但服务将继续启动...")
        sys.stdout.flush()


async def periodic_memory_cleanup():
    """
    定期检查并卸载空闲模型（后台任务）
    每 60 秒检查一次
    """
    import asyncio
    while True:
        try:
            await asyncio.sleep(60)  # 每 60 秒检查一次
            
            # 触发垃圾回收（静默执行，不输出日志）
            try:
                import gc
                gc.collect()
            except Exception:
                pass  # 静默处理错误
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"内存清理任务出错: {e}")
            await asyncio.sleep(60)  # 出错后等待 60 秒再重试


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    try:
        logger.info(f"{settings.service_name} 正在关闭...")
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"关闭事件执行失败: {e}")
        traceback.print_exc()
        sys.stdout.flush()


if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except Exception as e:
        logger.error(f"uvicorn 启动失败: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)

