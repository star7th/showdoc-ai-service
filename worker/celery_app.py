"""
Celery 应用配置
"""
from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

# 创建 Celery 应用
celery_app = Celery(
    "showdoc_ai_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"]
)

# Celery 配置（内存优化版）
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 默认 5 分钟超时（用于普通任务）
    
    # 内存优化配置
    worker_max_tasks_per_child=10,  # 每个子进程处理 10 个任务后重启，确保空闲时释放内存
    worker_prefetch_multiplier=1,  # 每次只预取 1 个任务，减少内存占用
    worker_disable_rate_limits=True,  # 禁用速率限制，减少开销
    task_acks_late=True,  # 任务完成后才确认，避免任务丢失
    task_reject_on_worker_lost=True,  # worker 丢失时拒绝任务
    # 空闲时自动回收子进程（如果长时间无任务，子进程会自动退出释放内存）
    worker_max_memory_per_child=200000,  # 每个子进程最大内存 200MB，超过后重启
    
    # 结果存储优化
    result_expires=1800,  # 从 3600 降到 1800（30分钟），更快清理结果
    
    # 定时任务配置
    beat_schedule={
        'cleanup-unused-indexes': {
            'task': 'cleanup_unused_indexes',
            'schedule': crontab(hour=2, minute=0),  # 每天凌晨2点执行
            'args': (365,)  # 清理超过365天未访问的索引
        },
    },
    
    # 为特定任务设置更长的超时时间
    task_annotations={
        'rebuild_index': {
            'time_limit': 3600,  # 重建索引任务：60 分钟超时（大项目需要更长时间）
            'soft_time_limit': 3300,  # 软超时：55 分钟（提前 5 分钟警告）
        },
    },
)

