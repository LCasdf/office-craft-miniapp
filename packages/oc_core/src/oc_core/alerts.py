"""Lightweight metrics + threshold alerts (MVP, no Prometheus client dep)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

import structlog
from oc_shared.enums import TaskStatus
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from oc_core.config import get_settings
from oc_core.models import Task

logger = structlog.get_logger(__name__)

_lock = Lock()
_counters: dict[str, float] = {}


def incr(name: str, value: float = 1.0) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0.0) + value


def get_counter(name: str) -> float:
    with _lock:
        return float(_counters.get(name, 0.0))


def snapshot_counters() -> dict[str, float]:
    with _lock:
        return dict(_counters)


def queue_depth(queue: str) -> int:
    """Best-effort Redis list length for Celery classic redis broker."""
    try:
        from redis import Redis

        settings = get_settings()
        r = Redis.from_url(settings.celery_broker_url)
        return int(r.llen(queue) or 0)
    except Exception:
        return -1


def task_stats_window(session: Session, *, window_seconds: int) -> dict[str, int]:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=window_seconds)
    rows = session.execute(
        select(Task.status, func.count())
        .where(Task.finished_at.is_not(None), Task.finished_at >= since)
        .group_by(Task.status)
    ).all()
    counts = {str(status): int(n) for status, n in rows}
    succeeded = counts.get(TaskStatus.SUCCEEDED.value, 0)
    failed = counts.get(TaskStatus.FAILED.value, 0)
    cancelled = counts.get(TaskStatus.CANCELLED.value, 0)
    total = succeeded + failed + cancelled
    return {
        "succeeded": succeeded,
        "failed": failed,
        "cancelled": cancelled,
        "total": total,
    }


def evaluate_alerts(session: Session) -> list[dict]:
    """
    Emit structured alert logs when thresholds breach.
    Returns list of fired alerts (for /metrics & tests).
    """
    settings = get_settings()
    window = settings.alert_window_seconds
    stats = task_stats_window(session, window_seconds=window)
    fired: list[dict] = []

    total = stats["total"]
    if total >= 5:
        rate = stats["succeeded"] / total
        if rate < settings.alert_success_rate_min:
            alert = {
                "name": "task_success_rate_low",
                "success_rate": round(rate, 4),
                "window_seconds": window,
                "total": total,
            }
            fired.append(alert)
            logger.warning("alert_fired", alert=True, **alert)

    for q in ("q.tools", "q.ai"):
        depth = queue_depth(q)
        if depth > settings.alert_queue_depth_max:
            alert = {
                "name": "queue_depth_high",
                "queue": q,
                "depth": depth,
                "threshold": settings.alert_queue_depth_max,
            }
            fired.append(alert)
            logger.warning("alert_fired", alert=True, **alert)

    return fired


def render_prometheus() -> str:
    """Plain-text Prometheus exposition (MVP)."""
    lines = [
        "# HELP oc_upload_orphan_cleanup_total Orphan upload objects deleted",
        "# TYPE oc_upload_orphan_cleanup_total counter",
        f"oc_upload_orphan_cleanup_total {get_counter('upload_orphan_cleanup_total')}",
        "# HELP oc_expired_output_cleanup_total Expired result objects deleted",
        "# TYPE oc_expired_output_cleanup_total counter",
        f"oc_expired_output_cleanup_total {get_counter('expired_output_cleanup_total')}",
        "# HELP oc_expired_input_cleanup_total Expired input objects deleted",
        "# TYPE oc_expired_input_cleanup_total counter",
        f"oc_expired_input_cleanup_total {get_counter('expired_input_cleanup_total')}",
        "# HELP oc_alert_fired_total Alerts fired",
        "# TYPE oc_alert_fired_total counter",
        f"oc_alert_fired_total {get_counter('alert_fired_total')}",
        "# HELP oc_queue_depth Celery queue depth",
        "# TYPE oc_queue_depth gauge",
    ]
    for qname in ("q.tools", "q.ai"):
        depth = queue_depth(qname)
        lines.append(f'oc_queue_depth{{queue="{qname}"}} {max(depth, 0)}')
    return "\n".join(lines) + "\n"
