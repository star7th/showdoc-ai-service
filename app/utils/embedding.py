"""
Embedding 服务
"""
from typing import List, Optional
import yaml
import os
import time
import gc
import threading

# 延迟加载配置，避免模块导入时初始化
_settings = None

def _get_settings():
    """延迟获取配置"""
    global _settings
    if _settings is None:
        from app.config import get_settings
        _settings = get_settings()
    return _settings


def normalize_base_url(base_url: Optional[str]) -> Optional[str]:
    """
    规范化 OpenAI API 的 base_url，自动补全 /v1 路径
    
    注意：此函数仅用于 OpenAI API（或兼容格式），其他提供商不需要
    
    Args:
        base_url: 原始 base_url
        
    Returns:
        规范化后的 base_url，如果输入为 None 则返回 None
        
    Examples:
        normalize_base_url('https://api.openai.com') -> 'https://api.openai.com/v1'
        normalize_base_url('https://api.openai.com/') -> 'https://api.openai.com/v1'
        normalize_base_url('https://api.openai.com/v1') -> 'https://api.openai.com/v1'
        normalize_base_url('https://api.example.com/v1') -> 'https://api.example.com/v1'
    """
    if not base_url:
        return None
    
    # 移除末尾的斜杠
    base_url = base_url.rstrip('/')
    
    # 如果已经以 /v1 结尾，直接返回
    if base_url.endswith('/v1'):
        return base_url
    
    # 否则添加 /v1
    return base_url + '/v1'


class EmbeddingService:
    """Embedding 服务（支持本地和 API）"""
    
    def __init__(self):
        self.provider = "local"  # 默认使用本地模型
        self.model = None
        self._model_loaded = False
        self._config = {}  # 保存配置
        self.model_name = 'BAAI/bge-base-zh-v1.5'  # 默认模型名称
        self._last_used_time = None  # 最后使用时间
        self._idle_timeout = 3600  # 空闲超时时间（秒），默认1小时
        self._lock = threading.Lock()  # 线程锁，保护模型加载/卸载
        self._load_config()
        # 延迟加载模型，避免启动时崩溃
        # self._init_model()  # 注释掉，改为延迟加载
    
    def _load_config(self):
        """加载配置"""
        settings = _get_settings()
        config_path = settings.llm_config_path
        
        # Embedding 使用内部默认配置，不从用户配置文件读取
        # 默认使用本地模型 BAAI/bge-base-zh-v1.5（准确度与性能平衡，适合中英文混合 API 文档）
        self.provider = 'local'
        self.model_name = 'BAAI/bge-base-zh-v1.5'
        print(f"[Embedding] 使用内部默认配置: provider={self.provider}, model={self.model_name}")
        
        # 仍然加载配置文件，用于 LLM 配置（OpenAI API key 等）
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # 保存配置供后续使用（LLM 配置等）
                self._config = config
        else:
            print(f"[Embedding] ⚠️ 配置文件不存在: {config_path}")
            self._config = {}
    
    def _init_model(self):
        """初始化模型（延迟加载，带线程锁保护）"""
        with self._lock:
            if self._model_loaded and self.model is not None:
                return
            
            if self.provider == 'local':
                # 使用本地模型（必须手动下载）
                try:
                    # 禁用所有可能的多线程操作（CentOS 7 等受限环境需要）
                    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
                    os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
                    os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'
                    # 禁用 transformers 内部的多线程下载和检查
                    os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '300'
                    # 强制离线模式，禁止在线下载
                    os.environ['HF_HUB_OFFLINE'] = '1'
                    os.environ['TRANSFORMERS_OFFLINE'] = '1'
                    
                    # 禁用 tqdm 的监控线程（避免在 Celery fork 进程中创建线程失败）
                    # 必须在导入 sentence_transformers 之前设置
                    os.environ['TQDM_DISABLE'] = '1'
                    try:
                        # 尝试直接禁用 tqdm 的监控功能
                        import tqdm
                        # 禁用 tqdm 的监控线程，避免在 fork 进程中创建线程失败
                        tqdm.tqdm.monitor_interval = 0
                    except (ImportError, AttributeError):
                        # 如果 tqdm 未安装或版本不支持，忽略错误
                        pass
                    
                    from sentence_transformers import SentenceTransformer
                    print(f"[Embedding] 正在加载本地 Embedding 模型: {self.model_name}")
                    
                    # 获取项目根目录（假设当前文件在 app/utils/ 下）
                    current_file_dir = os.path.dirname(os.path.abspath(__file__))
                    project_root = os.path.dirname(os.path.dirname(current_file_dir))
                    
                    # 尝试从模型名称推断本地路径
                    # 例如: BAAI/bge-base-zh-v1.5 -> models/bge-base-zh-v1.5
                    model_dir_name = self.model_name.split('/')[-1]  # 获取最后一部分
                    possible_local_paths = [
                        os.path.join(project_root, 'models', model_dir_name),
                        os.path.join(project_root, 'models', self.model_name.replace('/', '_')),
                        os.path.join(project_root, 'models', self.model_name),
                    ]
                    
                    # 检查是否存在本地模型目录
                    local_model_path = None
                    for path in possible_local_paths:
                        if os.path.exists(path) and os.path.isdir(path):
                            # 检查是否包含模型文件
                            required_files = ['config.json', 'pytorch_model.bin']
                            if all(os.path.exists(os.path.join(path, f)) for f in required_files):
                                local_model_path = path
                                print(f"[Embedding] ✅ 找到本地模型目录: {local_model_path}")
                                break
                    
                    # 如果找不到本地模型，直接报错
                    if not local_model_path:
                        error_msg = f"本地模型文件不存在。请手动下载模型到 models/{model_dir_name}/ 目录。\n"
                        error_msg += f"下载指引请参考: docs/manual-model-download.md\n"
                        error_msg += f"模型名称: {self.model_name}\n"
                        error_msg += f"已检查的路径:\n"
                        for path in possible_local_paths:
                            error_msg += f"  - {path}\n"
                        raise FileNotFoundError(error_msg)
                    
                    # 使用本地路径加载模型
                    print(f"[Embedding] 从本地路径加载模型: {local_model_path}")
                    try:
                        # 优先使用 local_files_only=True（如果支持）
                        self.model = SentenceTransformer(
                            local_model_path,
                            local_files_only=True
                        )
                        print(f"[Embedding] ✅ 从本地路径成功加载模型")
                    except TypeError:
                        # 如果不支持 local_files_only 参数，使用普通方式
                        # 由于已经设置了离线环境变量，不会尝试在线下载
                        self.model = SentenceTransformer(local_model_path)
                        print(f"[Embedding] ✅ 从本地路径成功加载模型（普通方式）")
                    except (OSError, FileNotFoundError) as e:
                        # 如果加载失败，提供详细的错误信息
                        print(f"[Embedding] ❌ 加载模型失败: {e}")
                        print(f"[Embedding] 请检查模型文件是否完整，特别是以下文件:")
                        required_files = ['config.json', 'pytorch_model.bin', 'tokenizer.json']
                        for f in required_files:
                            file_path = os.path.join(local_model_path, f)
                            if os.path.exists(file_path):
                                size = os.path.getsize(file_path) / 1024 / 1024
                                print(f"[Embedding]   ✅ {f} ({size:.2f} MB)")
                            else:
                                print(f"[Embedding]   ❌ {f} 不存在")
                        raise RuntimeError(f"本地模型文件不完整或无法加载，请检查模型文件: {e}") from e
                    
                    self._model_loaded = True
                    self._last_used_time = time.time()
                    print(f"[Embedding] 本地 Embedding 模型加载成功: {self.model_name}")
                except Exception as e:
                    import traceback
                    # 记录详细的错误信息
                    error_traceback = traceback.format_exc()
                    error_type = type(e).__name__
                    error_message = str(e)
                    
                    print(f"[Embedding] ❌ 加载本地 Embedding 模型失败")
                    print(f"[Embedding] 错误类型: {error_type}")
                    print(f"[Embedding] 错误信息: {error_message}")
                    print(f"[Embedding] 错误堆栈:")
                    print(error_traceback)
                    print(f"[Embedding] 排查建议:")
                    print(f"  1. 检查 sentence-transformers 是否已安装: pip install sentence-transformers")
                    print(f"  2. 检查模型文件是否已下载（首次运行需要下载模型）")
                    print(f"  3. 检查网络连接是否正常（下载模型需要网络）")
                    print(f"  4. 检查磁盘空间是否充足")
                    print(f"  5. 检查 Python 环境是否正确")
                    print(f"  6. 检查内存是否充足（模型加载需要约 500MB 内存）")
                    
                    # 用户明确配置为 local，加载失败必须报错，不允许自动切换
                    error_msg = f"本地 Embedding 模型加载失败 ({error_type}): {error_message}"
                    self.model = None
                    self._model_loaded = True  # 标记为已尝试加载
                    raise RuntimeError(error_msg) from e
            elif self.provider == 'openai':
                # 使用 OpenAI Embedding API
                print("[Embedding] 使用 OpenAI API 模式")
                self._model_loaded = True
            elif self.provider == 'qwen':
                # 使用通义千问 Embedding API
                print("[Embedding] 使用通义千问 API 模式")
                self._model_loaded = True
    
    async def embed(self, text: str) -> List[float]:
        """生成 Embedding"""
        # 检查是否需要重新加载模型（如果已卸载）
        if self.provider == 'local' and self._model_loaded and self.model is None:
            # 模型已被卸载，需要重新加载
            self._model_loaded = False
        
        # 确保配置已加载
        if not self._model_loaded:
            self._init_model()
        
        # 更新最后使用时间
        self._last_used_time = time.time()
            
        if self.provider == 'local':
            return await self._local_embed(text)
        elif self.provider == 'openai':
            return await self._openai_embed(text)
        elif self.provider == 'qwen':
            return await self._qwen_embed(text)
        else:
            raise ValueError(f"不支持的 Embedding 提供商: {self.provider}")
    
    async def _local_embed(self, text: str) -> List[float]:
        """本地模型 Embedding"""
        # 延迟加载模型
        if not self._model_loaded or self.model is None:
            self._init_model()
        
        if not self.model:
            # 用户明确配置为 local，模型未初始化必须报错，不允许自动切换
            print("[Embedding] ❌ 本地 Embedding 模型未初始化")
            print("[Embedding] 请查看启动日志中的详细错误信息")
            raise RuntimeError("本地 Embedding 模型未初始化。请查看启动日志中的详细错误信息，检查：1) sentence-transformers 是否已安装；2) 模型文件是否已下载；3) 网络连接是否正常；4) 内存是否充足；5) 是否因为线程限制导致加载失败")
        
        # 直接同步调用（不使用 executor，避免在受限环境中创建线程失败）
        # 我们已经禁用了所有多线程，embedding 操作很快，直接调用即可
        # 确保禁用 tokenizers 的并行处理
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        # 直接同步调用，不使用 run_in_executor（避免创建新线程）
        # 注意：encode 方法本身是同步的，不会创建线程
        embedding = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False, device='cpu')
        return embedding.tolist()
    
    async def _openai_embed(self, text: str) -> List[float]:
        """OpenAI Embedding"""
        from openai import OpenAI
        import traceback
        
        try:
            # 从配置文件读取 API key
            llm_config = self._config.get('llm', {})
            openai_config = llm_config.get('openai', {})
            api_key = openai_config.get('api_key') or os.getenv("OPENAI_API_KEY")
            base_url = openai_config.get('base_url')
            
            if not api_key:
                raise ValueError("OpenAI API Key 未配置，请在 config/llm.yaml 中设置 llm.openai.api_key")
            
            # 规范化 base_url，自动补全 /v1 路径
            base_url = normalize_base_url(base_url)
            
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            
            print(f"[Embedding] 调用 OpenAI Embedding API, base_url: {base_url}, model: text-embedding-3-small")
            client = OpenAI(**client_kwargs)
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            
            # 检查响应类型
            if isinstance(response, str):
                raise ValueError(f"OpenAI API 返回了错误字符串: {response}")
            
            if not hasattr(response, 'data') or not response.data:
                raise ValueError(f"OpenAI API 响应格式错误: {type(response)}, 响应内容: {response}")
            
            return response.data[0].embedding
        except Exception as e:
            error_msg = f"OpenAI Embedding 调用失败: {str(e)}"
            print(f"[Embedding] {error_msg}")
            print(f"[Embedding] 错误详情: {traceback.format_exc()}")
            raise RuntimeError(error_msg) from e
    
    async def _qwen_embed(self, text: str) -> List[float]:
        """通义千问 Embedding"""
        import dashscope
        from dashscope import TextEmbedding
        
        response = TextEmbedding.call(
            model="text-embedding-v2",
            input=text
        )
        
        if response.status_code == 200:
            return response.output['embeddings'][0]['embedding']
        else:
            raise Exception(f"Embedding 调用失败: {response.message}")
    
    def get_dimension(self) -> int:
        """获取向量维度"""
        if self.provider == 'local':
            # 根据模型名称返回对应的维度
            # BGE 系列模型通常是 512 或 1024
            if 'bge-large' in self.model_name.lower():
                return 1024
            elif 'bge-base' in self.model_name.lower():
                return 768
            elif 'bge-small' in self.model_name.lower() or 'bge-m3' in self.model_name.lower():
                return 512
            elif 'm3e' in self.model_name.lower():
                return 768
            elif 'text2vec' in self.model_name.lower():
                return 768
            else:
                # 默认尝试从模型获取，如果失败则返回常见值
                try:
                    if self.model and hasattr(self.model, 'get_sentence_embedding_dimension'):
                        return self.model.get_sentence_embedding_dimension()
                except:
                    pass
                return 512  # 默认值
        elif self.provider == 'openai':
            return 1536  # text-embedding-3-small
        elif self.provider == 'qwen':
            return 1536  # text-embedding-v2
        else:
            return 384  # 默认值
    
    def unload_model(self):
        """
        卸载模型，释放内存
        
        注意：卸载后下次使用时会自动重新加载
        """
        with self._lock:
            if self.provider == 'local' and self.model is not None:
                print("[Embedding] 正在卸载本地模型以释放内存...")
                try:
                    # 删除模型引用
                    del self.model
                    self.model = None
                    # 强制垃圾回收
                    gc.collect()
                    print("[Embedding] 模型已卸载，内存已释放")
                except Exception as e:
                    print(f"[Embedding] 卸载模型时出错: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # 标记为已卸载，但保留 _model_loaded 状态，以便下次自动重新加载
                    pass
    
    def check_and_unload_if_idle(self):
        """
        检查是否空闲超时，如果是则自动卸载模型
        
        返回: True 如果模型被卸载，False 如果模型仍在内存中
        """
        if self.provider != 'local' or self.model is None:
            return False
        
        if self._last_used_time is None:
            return False
        
        current_time = time.time()
        idle_time = current_time - self._last_used_time
        
        if idle_time > self._idle_timeout:
            print(f"[Embedding] 模型已空闲 {idle_time:.1f} 秒（超过 {self._idle_timeout} 秒），自动卸载以释放内存")
            self.unload_model()
            return True
        
        return False
    
    def set_idle_timeout(self, timeout_seconds: int):
        """
        设置空闲超时时间（秒）
        
        Args:
            timeout_seconds: 空闲超时时间，默认 3600 秒（1小时）
        """
        self._idle_timeout = timeout_seconds
        print(f"[Embedding] 空闲超时时间已设置为 {timeout_seconds} 秒")
    
    def get_memory_info(self) -> dict:
        """
        获取内存使用信息
        
        返回: 包含内存使用信息的字典
        """
        try:
            import psutil
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,  # 物理内存（MB）
                "vms_mb": memory_info.vms / 1024 / 1024,  # 虚拟内存（MB）
                "model_loaded": self._model_loaded and self.model is not None,
                "last_used_time": self._last_used_time,
                "idle_time": time.time() - self._last_used_time if self._last_used_time else None
            }
        except ImportError:
            return {
                "error": "psutil 未安装，无法获取内存信息",
                "model_loaded": self._model_loaded and self.model is not None,
                "last_used_time": self._last_used_time
            }
        except Exception as e:
            return {
                "error": str(e),
                "model_loaded": self._model_loaded and self.model is not None,
                "last_used_time": self._last_used_time
            }

