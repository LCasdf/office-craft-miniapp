"""Periodic cleanup + alert checks + timeout sweep."""

from __future__ import annotations

import structlog
from oc_core.alerts import evaluate_alerts, incr
from oc_core.cleanup import run_all_cleanups
from oc_core.db import session_scope
from oc_core.models import Task
from oc_core.quota import settle_unsettled_for_user
from oc_core.tasks_repo import sweep_timed_out_tasks
from sqlalchemy import select

from oc_worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="oc_worker.tasks.maintenance.cleanup_ttl")
def cleanup_ttl_task() -> dict:
    with session_scope() as session:
        stats = run_all_cleanups(session)
    incr("upload_orphan_cleanup_total", stats.get("orphan_objects", 0))
    incr("expired_output_cleanup_total", stats.get("expired_outputs", 0))
    incr("expired_input_cleanup_total", stats.get("expired_inputs", 0))
    logger.info("cleanup_ttl_task_done", **stats)
    return stats


@celery_app.task(name="oc_worker.tasks.maintenance.check_alerts")
def check_alerts_task() -> dict:
    with session_scope() as session:
        fired = evaluate_alerts(session)
    if fired:
        incr("alert_fired_total", len(fired))
    return {"fired": len(fired), "alerts": [a.get("name") for a in fired]}


@celery_app.task(name="oc_worker.tasks.maintenance.sweep_timeouts")
def sweep_timeouts_task() -> dict:
    with session_scope() as session:
        n = sweep_timed_out_tasks(session)
        if n:
            user_ids = session.scalars(select(Task.user_id).distinct()).all()
            for uid in user_ids:
                settle_unsettled_for_user(session, int(uid))
    logger.info("sweep_timeouts_done", timed_out=n)
    return {"timedOut": n}
