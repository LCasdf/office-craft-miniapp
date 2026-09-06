from __future__ import annotations

from celery import Celery

from oc_core.config import get_settings
from oc_shared.constants import DEFAULT_TASK_TIMEOUT_SECONDS, QUEUE_AI, QUEUE_TOOLS

settings = get_settings()

celery_app = Celery(
    "office_craft",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["oc_worker.tasks.ping"],
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
        "oc_worker.tasks.ai.*": {"queue": QUEUE_AI},
    },
)
