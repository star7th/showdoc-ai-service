"""
Redis 客户端工具类
提供带 TTL 和自动刷新的键管理功能，避免死键值
"""
import redis
from typing import Optional, Any, Union
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

# 默认 TTL（秒）：1 小时
DEFAULT_TTL = 3600


class RedisClient:
    """
    Redis 客户端封装
    特性：
    1. 所有键自动设置 TTL（过期时间）
    2. 每次操作时自动刷新 TTL（延长过期时间）
    3. 避免服务崩溃后产生死键值
    """
    
    def __init__(self, default_ttl: int = DEFAULT_TTL):
        """
        初始化 Redis 客户端
        
        Args:
            default_ttl: 默认 TTL（秒），默认 1 小时
        """
        settings = get_settings()
        self.redis_url = settings.redis_url
        self.default_ttl = default_ttl
        
        # 解析 Redis URL
        try:
            # 使用 redis.from_url 自动解析 URL
            # 支持格式：redis://localhost:6379/0 或 redis://:password@localhost:6379/0
            if self.redis_url.startswith('redis://') or self.redis_url.startswith('rediss://'):
                self.client = redis.from_url(
                    self.redis_url,
                    decode_responses=True
                )
            else:
                # 默认配置
                self.client = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    decode_responses=True
                )
            
            # 测试连接
            self.client.ping()
            # 连接成功不输出日志，减少冗余信息
        except Exception as e:
            logger.error(f"✗ Redis 连接失败: {e}")
            raise
    
    def _refresh_ttl(self, key: str, ttl: Optional[int] = None):
        """
        刷新键的 TTL（延长过期时间）
        
        Args:
            key: 键名
            ttl: TTL（秒），如果为 None 则使用默认 TTL
        """
        try:
            if self.client.exists(key):
                ttl = ttl or self.default_ttl
                self.client.expire(key, ttl)
        except Exception as e:
            logger.warning(f"刷新 TTL 失败 {key}: {e}")
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        refresh_on_access: bool = True
    ) -> bool:
        """
        设置键值，自动设置 TTL
        
        Args:
            key: 键名
            value: 值（会自动序列化为字符串）
            ttl: TTL（秒），如果为 None 则使用默认 TTL
            refresh_on_access: 是否在访问时自动刷新 TTL（默认 True）
        
        Returns:
            是否设置成功
        """
        try:
            ttl = ttl or self.default_ttl
            
            # 将值转换为字符串
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value, ensure_ascii=False)
            else:
                value = str(value)
            
            # 设置键值并 TTL
            result = self.client.setex(key, ttl, value)
            
            # 如果启用自动刷新，在元数据中标记
            if refresh_on_access:
                # 使用一个辅助键来标记需要自动刷新
                self.client.setex(f"{key}:__refresh__", ttl, "1")
            
            return result
        except Exception as e:
            logger.error(f"设置 Redis 键失败 {key}: {e}")
            return False
    
    def get(
        self,
        key: str,
        refresh_ttl: bool = True,
        ttl: Optional[int] = None
    ) -> Optional[str]:
        """
        获取键值，自动刷新 TTL
        
        Args:
            key: 键名
            refresh_ttl: 是否刷新 TTL（默认 True）
            ttl: 刷新时的 TTL（秒），如果为 None 则使用默认 TTL
        
        Returns:
            键值，如果不存在则返回 None
        """
        try:
            value = self.client.get(key)
            
            # 如果键存在且需要刷新 TTL
            if value is not None and refresh_ttl:
                self._refresh_ttl(key, ttl)
                # 同时刷新标记键
                if self.client.exists(f"{key}:__refresh__"):
                    self._refresh_ttl(f"{key}:__refresh__", ttl)
            
            return value
        except Exception as e:
            logger.error(f"获取 Redis 键失败 {key}: {e}")
            return None
    
    def get_json(self, key: str, refresh_ttl: bool = True, ttl: Optional[int] = None) -> Optional[Union[dict, list]]:
        """
        获取 JSON 格式的键值，自动刷新 TTL
        
        Args:
            key: 键名
            refresh_ttl: 是否刷新 TTL（默认 True）
            ttl: 刷新时的 TTL（秒），如果为 None 则使用默认 TTL
        
        Returns:
            解析后的 JSON 对象（dict 或 list），如果不存在或解析失败则返回 None
        """
        value = self.get(key, refresh_ttl=refresh_ttl, ttl=ttl)
        if value is None:
            return None
        
        try:
            import json
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败 {key}")
            return None
    
    def delete(self, key: str) -> bool:
        """
        删除键（包括辅助键）
        
        Args:
            key: 键名
        
        Returns:
            是否删除成功
        """
        try:
            # 删除主键和辅助键
            deleted = self.client.delete(key)
            self.client.delete(f"{key}:__refresh__")
            return deleted > 0
        except Exception as e:
            logger.error(f"删除 Redis 键失败 {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 键名
        
        Returns:
            是否存在
        """
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"检查 Redis 键失败 {key}: {e}")
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """
        设置键的过期时间
        
        Args:
            key: 键名
            ttl: TTL（秒）
        
        Returns:
            是否设置成功
        """
        try:
            return self.client.expire(key, ttl)
        except Exception as e:
            logger.error(f"设置 Redis 键过期时间失败 {key}: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """
        获取键的剩余过期时间（秒）
        
        Args:
            key: 键名
        
        Returns:
            剩余秒数，-1 表示永不过期，-2 表示键不存在
        """
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"获取 Redis 键 TTL 失败 {key}: {e}")
            return -2
    
    def keys(self, pattern: str = "*") -> list:
        """
        获取匹配模式的键列表（注意：生产环境慎用，可能影响性能）
        
        Args:
            pattern: 匹配模式，默认 "*"
        
        Returns:
            键列表
        """
        try:
            return self.client.keys(pattern)
        except Exception as e:
            logger.error(f"获取 Redis 键列表失败 {pattern}: {e}")
            return []
    
    def clear_expired_keys(self, pattern: str = "*") -> int:
        """
        清理过期键（通过检查 TTL）
        注意：这只是辅助方法，Redis 会自动清理过期键
        
        Args:
            pattern: 匹配模式，默认 "*"
        
        Returns:
            清理的键数量
        """
        try:
            keys = self.keys(pattern)
            count = 0
            for key in keys:
                # 跳过辅助键
                if key.endswith(":__refresh__"):
                    continue
                ttl = self.ttl(key)
                if ttl == -2:  # 键不存在
                    count += 1
            return count
        except Exception as e:
            logger.error(f"清理过期键失败: {e}")
            return 0


# 全局单例实例
_redis_client: Optional[RedisClient] = None


def get_redis_client(default_ttl: int = DEFAULT_TTL) -> RedisClient:
    """
    获取 Redis 客户端单例
    
    Args:
        default_ttl: 默认 TTL（秒）
    
    Returns:
        RedisClient 实例
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(default_ttl=default_ttl)
    return _redis_client

