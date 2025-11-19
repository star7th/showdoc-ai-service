"""
模型服务主应用 - 提供 Embedding 模型 HTTP API
"""
import sys
import traceback
import logging
import signal
import os
import time
import gc
import threading
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# 配置日志
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

# 信号处理器
def signal_handler(signum, frame):
    """信号处理器"""
    logger.error(f"收到信号 {signum}，准备退出...")
    logger.error(f"堆栈跟踪：")
    traceback.print_stack(frame)
    sys.stdout.flush()
    sys.exit(1)

try:
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGSEGV'):
        signal.signal(signal.SIGSEGV, signal_handler)
except Exception as e:
    logger.warning(f"无法注册某些信号处理器: {e}")

sys.stdout.flush()
sys.stderr.flush()

# 创建 FastAPI 应用
app = FastAPI(
    title="ShowDoc Model Service",
    version="1.0.0",
    description="ShowDoc AI 模型服务 - 提供 Embedding 模型 API",
)

# CORS 配置（仅允许内部调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 内部服务，允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局模型实例
_model_instance = None
_model_loaded = False
_model_name = 'BAAI/bge-base-zh-v1.5'
_model_dimension = 768
_last_used_time = None
_idle_timeout = 3600  # 空闲超时时间（秒），默认1小时
_model_lock = threading.Lock()  # 模型加载/卸载锁


class EmbedRequest(BaseModel):
    """Embedding 请求"""
    text: str


class EmbedResponse(BaseModel):
    """Embedding 响应"""
    embedding: List[float]
    dimension: int


class DimensionResponse(BaseModel):
    """向量维度响应"""
    dimension: int


def load_model():
    """加载模型（单例模式，带线程锁保护）"""
    global _model_instance, _model_loaded, _model_dimension, _last_used_time
    
    with _model_lock:
        if _model_loaded and _model_instance is not None:
            logger.info("模型已加载，复用现有实例")
            _last_used_time = time.time()
            return
    
    try:
        # 禁用所有可能的多线程操作
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
        os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'
        os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '300'
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['TQDM_DISABLE'] = '1'
        
        try:
            import tqdm
            tqdm.tqdm.monitor_interval = 0
        except (ImportError, AttributeError):
            pass
        
        from sentence_transformers import SentenceTransformer
        
        logger.info(f"正在加载本地 Embedding 模型: {_model_name}")
        
        # 获取项目根目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_file_dir)
        
        # 尝试从模型名称推断本地路径
        model_dir_name = _model_name.split('/')[-1]
        possible_local_paths = [
            os.path.join(project_root, 'models', model_dir_name),
            os.path.join(project_root, 'models', _model_name.replace('/', '_')),
            os.path.join(project_root, 'models', _model_name),
        ]
        
        # 检查是否存在本地模型目录
        local_model_path = None
        for path in possible_local_paths:
            if os.path.exists(path) and os.path.isdir(path):
                required_files = ['config.json', 'pytorch_model.bin']
                if all(os.path.exists(os.path.join(path, f)) for f in required_files):
                    local_model_path = path
                    logger.info(f"✅ 找到本地模型目录: {local_model_path}")
                    break
        
        if not local_model_path:
            error_msg = f"本地模型文件不存在。请手动下载模型到 models/{model_dir_name}/ 目录。\n"
            error_msg += f"下载指引请参考: docs/manual-model-download.md\n"
            error_msg += f"模型名称: {_model_name}\n"
            error_msg += f"已检查的路径:\n"
            for path in possible_local_paths:
                error_msg += f"  - {path}\n"
            raise FileNotFoundError(error_msg)
        
        # 使用本地路径加载模型
        logger.info(f"从本地路径加载模型: {local_model_path}")
        try:
            _model_instance = SentenceTransformer(
                local_model_path,
                local_files_only=True
            )
            logger.info("✅ 从本地路径成功加载模型")
        except TypeError:
            _model_instance = SentenceTransformer(local_model_path)
            logger.info("✅ 从本地路径成功加载模型（普通方式）")
        
        # 获取向量维度
        try:
            if hasattr(_model_instance, 'get_sentence_embedding_dimension'):
                _model_dimension = _model_instance.get_sentence_embedding_dimension()
            else:
                # 根据模型名称推断
                if 'bge-large' in _model_name.lower():
                    _model_dimension = 1024
                elif 'bge-base' in _model_name.lower():
                    _model_dimension = 768
                elif 'bge-small' in _model_name.lower() or 'bge-m3' in _model_name.lower():
                    _model_dimension = 512
                else:
                    _model_dimension = 768  # 默认值
        except Exception as e:
            logger.warning(f"无法获取模型维度，使用默认值: {e}")
            _model_dimension = 768
        
        _model_loaded = True
        _last_used_time = time.time()
        logger.info(f"✅ 模型加载成功: {_model_name}, 维度: {_model_dimension}")
        
    except Exception as e:
        logger.error(f"❌ 加载模型失败: {e}")
        traceback.print_exc()
        raise


def unload_model():
    """卸载模型，释放内存"""
    global _model_instance, _model_loaded, _last_used_time
    
    with _model_lock:
        if _model_instance is not None:
            logger.info("正在卸载模型以释放内存...")
            try:
                del _model_instance
                _model_instance = None
                gc.collect()
                logger.info("模型已卸载，内存已释放")
            except Exception as e:
                logger.error(f"卸载模型时出错: {e}")
                traceback.print_exc()


def check_and_unload_if_idle():
    """检查是否空闲超时，如果是则自动卸载模型"""
    global _model_instance, _last_used_time
    
    if _model_instance is None:
        return False
    
    if _last_used_time is None:
        return False
    
    current_time = time.time()
    idle_time = current_time - _last_used_time
    
    if idle_time > _idle_timeout:
        logger.info(f"模型已空闲 {idle_time:.1f} 秒（超过 {_idle_timeout} 秒），自动卸载以释放内存")
        unload_model()
        return True
    
    return False


async def periodic_memory_cleanup():
    """定期检查并卸载空闲模型（后台任务）"""
    while True:
        try:
            await asyncio.sleep(60)  # 每 60 秒检查一次
            check_and_unload_if_idle()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"内存清理任务出错: {e}")
            await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    """启动事件 - 自动加载模型"""
    try:
        logger.info("ShowDoc Model Service v1.0.0 启动中...")
        load_model()
        logger.info("✅ 模型服务启动成功")
        
        # 启动后台任务：定期检查并卸载空闲模型
        asyncio.create_task(periodic_memory_cleanup())
        
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"启动失败: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        # 不抛出异常，允许服务继续启动（但 API 调用会失败）


@app.on_event("shutdown")
async def shutdown_event():
    """关闭事件"""
    try:
        logger.info("模型服务正在关闭...")
        unload_model()
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"关闭事件执行失败: {e}")
        traceback.print_exc()
        sys.stdout.flush()


@app.get("/health")
async def health():
    """健康检查"""
    idle_time = None
    if _last_used_time is not None:
        idle_time = time.time() - _last_used_time
    
    return {
        "status": "healthy" if _model_loaded and _model_instance is not None else "unhealthy",
        "model_loaded": _model_loaded and _model_instance is not None,
        "model_name": _model_name,
        "dimension": _model_dimension,
        "last_used_time": _last_used_time,
        "idle_time_seconds": round(idle_time, 2) if idle_time is not None else None,
        "idle_timeout_seconds": _idle_timeout
    }


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """生成 Embedding"""
    global _last_used_time
    
    # 如果模型未加载，尝试加载
    if not _model_loaded or _model_instance is None:
        try:
            load_model()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"模型未加载且加载失败: {str(e)}")
    
    # 更新最后使用时间
    _last_used_time = time.time()
    
    try:
        # 确保禁用 tokenizers 的并行处理
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        
        # 生成向量
        embedding = _model_instance.encode(
            request.text,
            convert_to_numpy=True,
            show_progress_bar=False,
            device='cpu'
        )
        
        return EmbedResponse(
            embedding=embedding.tolist(),
            dimension=_model_dimension
        )
    except Exception as e:
        logger.error(f"生成 Embedding 失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成 Embedding 失败: {str(e)}")


@app.post("/embed_batch", response_model=List[EmbedResponse])
async def embed_batch(texts: List[str]):
    """批量生成 Embedding"""
    global _last_used_time
    
    # 如果模型未加载，尝试加载
    if not _model_loaded or _model_instance is None:
        try:
            load_model()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"模型未加载且加载失败: {str(e)}")
    
    # 更新最后使用时间
    _last_used_time = time.time()
    
    try:
        # 确保禁用 tokenizers 的并行处理
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        
        # 批量生成向量
        embeddings = _model_instance.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            device='cpu',
            batch_size=32  # 批量处理，提高效率
        )
        
        return [
            EmbedResponse(
                embedding=emb.tolist(),
                dimension=_model_dimension
            )
            for emb in embeddings
        ]
    except Exception as e:
        logger.error(f"批量生成 Embedding 失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"批量生成 Embedding 失败: {str(e)}")


@app.get("/dimension", response_model=DimensionResponse)
async def get_dimension():
    """获取向量维度"""
    # 如果模型未加载，尝试加载
    if not _model_loaded or _model_instance is None:
        try:
            load_model()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"模型未加载且加载失败: {str(e)}")
    
    return DimensionResponse(dimension=_model_dimension)


@app.post("/warmup")
async def warmup():
    """预热模型（重新加载模型）"""
    global _model_loaded
    import time
    start_time = time.time()
    
    try:
        # 如果模型已加载，先卸载
        if _model_loaded and _model_instance is not None:
            logger.info("模型已加载，先卸载再重新加载")
            unload_model()
            # 重置状态
            _model_loaded = False
        
        # 加载模型
        logger.info("开始加载模型...")
        load_model()
        
        elapsed = time.time() - start_time
        logger.info(f"✅ 模型预热成功 (耗时: {elapsed:.2f}秒)")
        
        return {
            "status": "success",
            "message": "模型已成功加载到内存",
            "model_loaded": _model_loaded,
            "model_name": _model_name,
            "dimension": _model_dimension,
            "elapsed_seconds": round(elapsed, 2)
        }
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ 模型预热失败: {str(e)} (耗时: {elapsed:.2f}秒)")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"模型预热失败: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run(app, host="0.0.0.0", port=7126)
    except Exception as e:
        logger.error(f"uvicorn 启动失败: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        sys.exit(1)

