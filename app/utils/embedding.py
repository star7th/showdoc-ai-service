"""
Embedding 服务（通过模型服务 API 调用）
"""
from typing import List, Optional
import yaml
import os
import httpx
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
    
    # 单例模式：确保整个应用只有一个实例
    _instance = None
    _singleton_lock = threading.Lock()  # 单例创建锁
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super(EmbeddingService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 如果已经初始化过，直接返回（避免重复初始化）
        if hasattr(self, '_initialized'):
            return
        
        self.provider = "model_service"  # 使用模型服务 API
        self.model_service_url = None  # 模型服务地址
        self._model_dimension = None  # 缓存的向量维度
        self._config = {}  # 保存配置
        self.model_name = 'BAAI/bge-base-zh-v1.5'  # 默认模型名称
        self._lock = threading.Lock()  # 线程锁
        self._load_config()
        
        # 标记已初始化
        self._initialized = True
    
    def _load_config(self):
        """加载配置"""
        settings = _get_settings()
        config_path = settings.llm_config_path
        
        # 从环境变量或配置获取模型服务地址
        self.model_service_url = os.getenv("MODEL_SERVICE_URL", "http://model-service:7126")
        # 移除末尾的斜杠
        self.model_service_url = self.model_service_url.rstrip('/')
        
        self.provider = 'model_service'
        self.model_name = 'BAAI/bge-base-zh-v1.5'
        print(f"[Embedding] 使用模型服务: url={self.model_service_url}, model={self.model_name}")
        
        # 仍然加载配置文件，用于 LLM 配置（OpenAI API key 等）
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # 保存配置供后续使用（LLM 配置等）
                self._config = config
        else:
            print(f"[Embedding] ⚠️ 配置文件不存在: {config_path}")
            self._config = {}
    
    
    async def embed(self, text: str) -> List[float]:
        """生成 Embedding"""
        if self.provider == 'model_service':
            return await self._model_service_embed(text)
        elif self.provider == 'openai':
            return await self._openai_embed(text)
        elif self.provider == 'qwen':
            return await self._qwen_embed(text)
        else:
            raise ValueError(f"不支持的 Embedding 提供商: {self.provider}")
    
    async def _model_service_embed(self, text: str) -> List[float]:
        """通过模型服务 API 生成 Embedding"""
        if not self.model_service_url:
            raise RuntimeError("模型服务地址未配置，请设置 MODEL_SERVICE_URL 环境变量")
        
        # 在 Celery worker 的 fork 进程中，直接使用同步调用避免线程创建问题
        # 使用同步的 httpx.Client，不创建新线程
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.model_service_url}/embed",
                    json={"text": text}
                )
                response.raise_for_status()
                result = response.json()
                return result["embedding"]
        except httpx.HTTPStatusError as e:
            error_msg = f"模型服务 API 调用失败 (HTTP {e.response.status_code}): {e.response.text}"
            print(f"[Embedding] {error_msg}")
            raise RuntimeError(error_msg) from e
        except httpx.RequestError as e:
            error_msg = f"模型服务连接失败: {str(e)}"
            print(f"[Embedding] {error_msg}")
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = f"模型服务调用失败: {str(e)}"
            print(f"[Embedding] {error_msg}")
            raise RuntimeError(error_msg) from e
    
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
        if self.provider == 'model_service':
            # 如果已缓存，直接返回
            if self._model_dimension is not None:
                return self._model_dimension
            
            # 从模型服务获取维度（同步调用）
            if not self.model_service_url:
                raise RuntimeError("模型服务地址未配置，请设置 MODEL_SERVICE_URL 环境变量")
            
            try:
                import httpx
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(f"{self.model_service_url}/dimension")
                    response.raise_for_status()
                    result = response.json()
                    self._model_dimension = result["dimension"]
                    return self._model_dimension
            except Exception as e:
                print(f"[Embedding] 获取向量维度失败: {e}，使用默认值 768")
                self._model_dimension = 768  # 默认值
                return self._model_dimension
        elif self.provider == 'openai':
            return 1536  # text-embedding-3-small
        elif self.provider == 'qwen':
            return 1536  # text-embedding-v2
        else:
            return 384  # 默认值
    

