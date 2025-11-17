"""
LLM 调用适配器
"""
from typing import List, Dict, Any, AsyncIterator, Optional
import yaml
import os
from app.config import get_settings


def normalize_base_url(base_url: Optional[str], default: Optional[str] = None) -> Optional[str]:
    """
    规范化 OpenAI API 的 base_url，自动补全 /v1 路径
    
    注意：此函数仅用于 OpenAI API（或兼容格式），其他提供商（qwen、wenxin、zhipu）不需要
    
    Args:
        base_url: 原始 base_url
        default: 如果 base_url 为 None 时使用的默认值
        
    Returns:
        规范化后的 base_url，如果输入为 None 且没有 default 则返回 None
        
    Examples:
        normalize_base_url('https://api.openai.com') -> 'https://api.openai.com/v1'
        normalize_base_url('https://api.openai.com/') -> 'https://api.openai.com/v1'
        normalize_base_url('https://api.openai.com/v1') -> 'https://api.openai.com/v1'
    """
    if not base_url:
        base_url = default
    
    if not base_url:
        return None
    
    # 移除末尾的斜杠
    base_url = base_url.rstrip('/')
    
    # 如果已经以 /v1 结尾，直接返回
    if base_url.endswith('/v1'):
        return base_url
    
    # 否则添加 /v1
    return base_url + '/v1'

settings = get_settings()


class LLMAdapter:
    """LLM 调用适配器（统一接口）"""
    
    def __init__(self):
        self.provider = None
        self.config = {}
        self.client = None
        self._load_config()
        self._init_client()
    
    def _load_config(self):
        """加载 LLM 配置"""
        config_path = settings.llm_config_path
        if not os.path.exists(config_path):
            # 配置文件不存在时，使用默认配置（延迟初始化）
            print(f"⚠️ 警告: LLM 配置文件不存在: {config_path}，将使用默认配置")
            self.provider = 'qwen'
            self.config = {}
            return
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        self.provider = config.get('llm', {}).get('provider', 'qwen')
        self.config = config.get('llm', {}).get(self.provider, {})
    
    def _init_client(self):
        """初始化 LLM 客户端"""
        # 如果配置为空，延迟初始化（不立即创建客户端）
        if not self.config:
            self.client = None
            return
            
        if self.provider == 'openai':
            from openai import OpenAI
            base_url = normalize_base_url(
                self.config.get('base_url'),
                default='https://api.openai.com/v1'
            )
            self.client = OpenAI(
                api_key=self.config.get('api_key'),
                base_url=base_url
            )
        elif self.provider == 'qwen':
            import dashscope
            dashscope.api_key = self.config.get('api_key')
            self.client = dashscope
        elif self.provider == 'custom':
            # 自定义 API（假设兼容 OpenAI 格式）
            from openai import OpenAI
            base_url = normalize_base_url(self.config.get('base_url'))
            self.client = OpenAI(
                api_key=self.config.get('api_key', ''),
                base_url=base_url
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.provider}")
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ) -> Any:
        """统一的对话接口"""
        if self.client is None:
            raise RuntimeError("LLM 客户端未初始化，请检查配置文件 config/llm.yaml 是否存在并正确配置")
            
        if self.provider == 'openai':
            return await self._openai_chat(messages, stream)
        elif self.provider == 'qwen':
            return await self._qwen_chat(messages, stream)
        elif self.provider == 'custom':
            return await self._openai_chat(messages, stream)
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.provider}")
    
    async def _openai_chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ):
        """OpenAI 格式的对话"""
        model = self.config.get('model', 'gpt-4o')
        
        if stream:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True
            )
            return response
        else:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages
            )
            return response
    
    async def _qwen_chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False
    ):
        """通义千问对话"""
        import dashscope
        from dashscope import Generation
        
        model = self.config.get('model', 'qwen-plus')
        
        # 转换消息格式
        qwen_messages = []
        for msg in messages:
            qwen_messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
        
        if stream:
            response = Generation.call(
                model=model,
                messages=qwen_messages,
                stream=True
            )
            return response
        else:
            response = Generation.call(
                model=model,
                messages=qwen_messages
            )
            return response
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """统一的 Embedding 接口"""
        if self.provider == 'openai':
            return await self._openai_embed(texts)
        elif self.provider == 'qwen':
            return await self._qwen_embed(texts)
        else:
            raise ValueError(f"不支持的 Embedding 提供商: {self.provider}")
    
    async def _openai_embed(self, texts: List[str]) -> List[List[float]]:
        """OpenAI Embedding"""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [item.embedding for item in response.data]
    
    async def _qwen_embed(self, texts: List[str]) -> List[List[float]]:
        """通义千问 Embedding"""
        import dashscope
        from dashscope import TextEmbedding
        
        response = TextEmbedding.call(
            model="text-embedding-v2",
            input=texts
        )
        
        if response.status_code == 200:
            return [item['embedding'] for item in response.output['embeddings']]
        else:
            raise Exception(f"Embedding 调用失败: {response.message}")

