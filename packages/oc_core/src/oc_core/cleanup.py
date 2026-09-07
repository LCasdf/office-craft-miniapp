"""Object TTL + orphan upload cleanup (API/Worker shared)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from oc_shared.constants import INPUT_TTL_SECONDS
from oc_shared.enums import TaskStatus
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from oc_core.config import get_settings
from oc_core.models import Task
from oc_core.storage import delete_object, delete_prefix, list_objects

logger = structlog.get_logger(__name__)

TERMINAL = (
    TaskStatus.SUCCEEDED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def collect_bound_upload_ids(session: Session, *, lookback_days: int = 14) -> set[str]:
    """uploadId values referenced by recent tasks."""
    since = _now().replace(tzinfo=None) - timedelta(days=lookback_days)
    tasks = session.scalars(select(Task).where(Task.created_at >= since).limit(5000))
    ids: set[str] = set()
    for t in tasks:
        meta = t.input_meta if isinstance(t.input_meta, dict) else {}
        uid = meta.get("uploadId")
        if uid:
            ids.add(str(uid))
    return ids


def group_upload_prefixes(env: str, objects: list[dict]) -> dict[str, dict[str, Any]]:
    """
    Group S3 objects under {env}/{user}/uploads/{uploadId}/...
    Returns uploadId -> {prefix, last_modified, keys}.
    """
    groups: dict[str, dict[str, Any]] = {}
    for obj in objects:
        key = str(obj["key"])
        parts = key.split("/")
        # env / userId / uploads / uploadId / file
        if len(parts) < 5 or parts[2] != "uploads":
            continue
        if parts[0] != env:
            continue
        upload_id = parts[3]
        prefix = f"{parts[0]}/{parts[1]}/uploads/{upload_id}/"
        lm = _aware(obj["last_modified"])
        g = groups.get(upload_id)
        if g is None:
            groups[upload_id] = {"prefix": prefix, "last_modified": lm, "keys": [key]}
        else:
            g["keys"].append(key)
            if lm > g["last_modified"]:
                g["last_modified"] = lm
    return groups


def cleanup_orphan_uploads(
    session: Session,
    *,
    env: str | None = None,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Delete upload prefixes older than TTL and not bound to any task."""
    settings = get_settings()
    env = env or settings.cos_env_prefix or settings.app_env
    ttl = ttl_seconds if ttl_seconds is not None else (
        settings.input_ttl_seconds or INPUT_TTL_SECONDS
    )
    now = now or _now()
    cutoff = now - timedelta(seconds=ttl)

    objects = list_objects(f"{env}/", max_keys=5000)
    groups = group_upload_prefixes(env, objects)
    bound = collect_bound_upload_ids(session)
    deleted_prefixes = 0
    deleted_objects = 0
    for upload_id, info in groups.items():
        if upload_id in bound:
            continue
        if info["last_modified"] > cutoff:
            continue
        n = delete_prefix(info["prefix"])
        deleted_prefixes += 1
        deleted_objects += n
        logger.info(
            "orphan_upload_cleaned",
            upload_id=upload_id,
            prefix=info["prefix"],
            deleted=n,
            alert_metric="upload_orphan_cleanup_total",
        )
    return {"orphan_prefixes": deleted_prefixes, "orphan_objects": deleted_objects}


def cleanup_expired_outputs(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 200,
) -> dict[str, int]:
    """Delete result objects past result_expires_at."""
    now_naive = (now or _now()).replace(tzinfo=None)
    tasks = list(
        session.scalars(
            select(Task)
            .where(
                Task.status == TaskStatus.SUCCEEDED.value,
                Task.result_expires_at.is_not(None),
                Task.result_expires_at < now_naive,
            )
            .order_by(Task.id.asc())
            .limit(limit)
        )
    )
    deleted = 0
    for task in tasks:
        meta = dict(task.output_meta or {}) if isinstance(task.output_meta, dict) else {}
        key = meta.get("cosKey")
        if not key:
            continue
        if delete_object(str(key)):
            deleted += 1
        meta["cosKey"] = None
        meta["cleanedAt"] = now_naive.isoformat()
        task.output_meta = meta
        logger.info("expired_output_cleaned", task_id=task.public_id, cos_key=key)
    return {"expired_outputs": deleted}


def cleanup_expired_inputs(
    session: Session,
    *,
    ttl_seconds: int | None = None,
    now: datetime | None = None,
    limit: int = 200,
) -> dict[str, int]:
    """Delete input objects for terminal tasks older than input TTL."""
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else (
        settings.input_ttl_seconds or INPUT_TTL_SECONDS
    )
    now_naive = (now or _now()).replace(tzinfo=None)
    cutoff = now_naive - timedelta(seconds=ttl)
    tasks = list(
        session.scalars(
            select(Task)
            .where(
                Task.status.in_(TERMINAL),
                or_(Task.finished_at <= cutoff, Task.created_at <= cutoff),
            )
            .order_by(Task.id.asc())
            .limit(limit)
        )
    )
    deleted = 0
    for task in tasks:
        meta = dict(task.input_meta or {}) if isinstance(task.input_meta, dict) else {}
        if meta.get("inputsCleaned"):
            continue
        for item in meta.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            key = item.get("cosKey") or item.get("cos_key")
            if key and delete_object(str(key)):
                deleted += 1
        meta["inputsCleaned"] = True
        task.input_meta = meta
        logger.info("expired_inputs_cleaned", task_id=task.public_id)
    return {"expired_inputs": deleted}


def delete_task_input_objects(input_meta: dict | None) -> int:
    """Best-effort delete input cosKeys right after task finishes."""
    if not isinstance(input_meta, dict):
        return 0
    n = 0
    for item in input_meta.get("inputs") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("cosKey") or item.get("cos_key")
        if key and delete_object(str(key)):
            n += 1
    return n


def run_all_cleanups(session: Session) -> dict[str, int]:
    stats: dict[str, int] = {}
    for part in (
        cleanup_orphan_uploads(session),
        cleanup_expired_outputs(session),
        cleanup_expired_inputs(session),
    ):
        stats.update(part)
    logger.info("cleanup_done", **stats)
    return stats
