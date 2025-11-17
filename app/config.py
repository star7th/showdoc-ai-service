"""
配置管理模块
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""
    
    # 服务配置
    service_token: str = os.getenv("SERVICE_TOKEN", "your-secret-token-here")
    service_name: str = "ShowDoc AI Service"
    version: str = "1.0.0"
    
    # Qdrant 配置
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection_prefix: str = os.getenv("QDRANT_COLLECTION_PREFIX", "showdoc_item_")
    
    # Redis 配置
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # LLM 配置路径
    llm_config_path: str = os.getenv("LLM_CONFIG_PATH", "config/llm.yaml")
    
    # 日志配置
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """获取配置（单例）"""
    return Settings()

