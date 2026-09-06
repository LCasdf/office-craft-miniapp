from __future__ import annotations

import structlog

from oc_worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="oc_worker.tasks.ping.ping_task", bind=True, max_retries=2)
def ping_task(self, *, task_id: str, request_id: str = "") -> dict:
    """M0 smoke task — proves queue + worker path."""
    structlog.contextvars.bind_contextvars(task_id=task_id, request_id=request_id)
    logger.info("ping_task_start", celery_id=self.request.id)
    result = {"taskId": task_id, "status": "succeeded", "message": "pong"}
    logger.info("ping_task_done", result=result)
    return result
