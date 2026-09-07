from __future__ import annotations

from celery import Celery
from oc_core.config import get_settings
from oc_shared.constants import DEFAULT_TASK_TIMEOUT_SECONDS, QUEUE_AI, QUEUE_TOOLS

settings = get_settings()

celery_app = Celery(
    "office_craft",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "oc_worker.tasks.ping",
        "oc_worker.tasks.tools.pdf_convert",
        "oc_worker.tasks.maintenance",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=DEFAULT_TASK_TIMEOUT_SECONDS,
    task_soft_time_limit=max(DEFAULT_TASK_TIMEOUT_SECONDS - 10, 30),
    task_default_queue=QUEUE_TOOLS,
    task_create_missing_queues=True,
    task_routes={
        "oc_worker.tasks.ping.*": {"queue": QUEUE_TOOLS},
        "oc_worker.tasks.tools.*": {"queue": QUEUE_TOOLS},
        "oc_worker.tasks.maintenance.*": {"queue": QUEUE_TOOLS},
        "oc_worker.tasks.ai.*": {"queue": QUEUE_AI},
    },
    beat_schedule={
        "cleanup-ttl-hourly": {
            "task": "oc_worker.tasks.maintenance.cleanup_ttl",
            "schedule": float(settings.cleanup_interval_seconds or 3600),
        },
        "check-alerts": {
            "task": "oc_worker.tasks.maintenance.check_alerts",
            "schedule": float(settings.alert_interval_seconds or 300),
        },
        "sweep-timeouts": {
            "task": "oc_worker.tasks.maintenance.sweep_timeouts",
            "schedule": 60.0,
        },
    },
    timezone="Asia/Shanghai",
)
