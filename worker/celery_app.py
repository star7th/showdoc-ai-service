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

# Celery 配置
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 分钟超时
    worker_max_tasks_per_child=50,  # 防止内存泄漏
    result_expires=3600,  # 任务结果过期时间（秒），1 小时后自动清理，避免死键值
    # 定时任务配置
    beat_schedule={
        'cleanup-unused-indexes': {
            'task': 'cleanup_unused_indexes',
            'schedule': crontab(hour=2, minute=0),  # 每天凌晨2点执行
            'args': (365,)  # 清理超过365天未访问的索引
        },
    },
)

