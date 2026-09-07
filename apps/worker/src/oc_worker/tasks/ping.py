from __future__ import annotations

import structlog
from oc_core.db import session_scope
from oc_core.tasks_repo import mark_succeeded

from oc_worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="oc_worker.tasks.ping.ping_task", bind=True, max_retries=2)
def ping_task(self, *, task_id: str, request_id: str = "") -> dict:
    """M0 smoke task — proves queue + worker path and DB writeback."""
    structlog.contextvars.bind_contextvars(task_id=task_id, request_id=request_id)
    logger.info("ping_task_start", celery_id=self.request.id)

    with session_scope() as session:
        ok = mark_succeeded(session, task_id, output_meta={"note": "pong"})
    if not ok:
        logger.warning("ping_task_missing_row", task_id=task_id)

    result = {"taskId": task_id, "status": "succeeded", "message": "pong", "written": ok}
    logger.info("ping_task_done", result=result)
    return result
