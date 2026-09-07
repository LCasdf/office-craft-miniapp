"""Task persistence helpers — create → worker writeback."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from oc_shared.constants import OUTPUT_TTL_SECONDS
from oc_shared.enums import ErrorClass, TaskStatus
from oc_shared.error_codes import ErrorCode
from sqlalchemy import select
from sqlalchemy.orm import Session

from oc_core.models import Task

# Stub auth user id
DEV_USER_ID = 0
MAX_USER_RETRIES = 2


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_by_idempotency(session: Session, *, user_id: int, key: str) -> Task | None:
    return session.scalar(
        select(Task).where(Task.user_id == user_id, Task.idempotency_key == key)
    )


def get_by_public_id(
    session: Session, public_id: str, *, user_id: int | None = None
) -> Task | None:
    stmt = select(Task).where(Task.public_id == public_id)
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    return session.scalar(stmt)


def list_for_user(session: Session, user_id: int, *, limit: int = 20) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.user_id == user_id)
        .order_by(Task.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def delete_for_user(session: Session, public_id: str, *, user_id: int) -> bool:
    """Hard-delete task row owned by user. Refunds unsettled freeze first."""
    from oc_core.quota import SETTLED_FROZEN, apply_refund, get_or_create_quota

    task = get_by_public_id(session, public_id, user_id=user_id)
    if task is None:
        return False
    if task.quota_settled == SETTLED_FROZEN and (task.cost_quota or 0) > 0:
        q = get_or_create_quota(session, user_id)
        apply_refund(q, task)
    session.delete(task)
    return True


def create_task_row(
    session: Session,
    *,
    public_id: str,
    user_id: int,
    task_type: str,
    idempotency_key: str,
    timeout_at: datetime,
    input_meta: dict | None = None,
    cost_quota: int = 0,
) -> tuple[Task, bool]:
    """Insert queued task. Returns (task, created_new). Idempotent on (user_id, key)."""
    existing = get_by_idempotency(session, user_id=user_id, key=idempotency_key)
    if existing is not None:
        return existing, False

    task = Task(
        public_id=public_id,
        user_id=user_id,
        type=task_type,
        status=TaskStatus.QUEUED.value,
        progress=10,
        idempotency_key=idempotency_key,
        timeout_at=timeout_at,
        input_meta=input_meta,
        cost_quota=cost_quota,
    )
    session.add(task)
    session.flush()
    return task, True


def apply_running(task: Task) -> None:
    if task.status in (
        TaskStatus.SUCCEEDED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    ):
        return
    task.status = TaskStatus.RUNNING.value
    task.progress = max(task.progress, 20)
    task.started_at = task.started_at or _now()


def apply_succeeded(task: Task, *, output_meta: dict | None = None) -> None:
    """Mutate task to succeeded — no session I/O (unit-testable)."""
    now = _now()
    task.status = TaskStatus.SUCCEEDED.value
    task.progress = 100
    task.started_at = task.started_at or now
    task.finished_at = now
    task.result_expires_at = now + timedelta(seconds=OUTPUT_TTL_SECONDS)
    task.output_meta = output_meta if output_meta is not None else {"note": "pong"}
    task.error_code = None
    task.error_class = None
    task.error_detail = None


def apply_failed(
    task: Task,
    *,
    error_code: int,
    error_class: str,
    error_detail: str | None = None,
    user_msg: str | None = None,
) -> None:
    now = _now()
    task.status = TaskStatus.FAILED.value
    task.progress = max(task.progress, 0)
    task.started_at = task.started_at or now
    task.finished_at = now
    task.error_code = error_code
    task.error_class = error_class
    task.error_detail = (error_detail or "")[:2000] or None
    meta = dict(task.output_meta or {})
    if user_msg:
        meta["userMsg"] = user_msg
    task.output_meta = meta or None


def mark_running(session: Session, public_id: str) -> Task | None:
    task = get_by_public_id(session, public_id)
    if task is None:
        return None
    if task.status in (
        TaskStatus.SUCCEEDED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    ):
        return task
    apply_running(task)
    return task


def mark_succeeded(session: Session, public_id: str, *, output_meta: dict | None = None) -> bool:
    task = get_by_public_id(session, public_id)
    if task is None:
        return False
    apply_succeeded(task, output_meta=output_meta)
    return True


def mark_failed(
    session: Session,
    public_id: str,
    *,
    error_code: int,
    error_class: str,
    error_detail: str | None = None,
    user_msg: str | None = None,
) -> bool:
    task = get_by_public_id(session, public_id)
    if task is None:
        return False
    apply_failed(
        task,
        error_code=error_code,
        error_class=error_class,
        error_detail=error_detail,
        user_msg=user_msg,
    )
    return True


def is_retryable(task: Task) -> bool:
    if task.status != TaskStatus.FAILED.value:
        return False
    if task.error_class == ErrorClass.SAFETY.value:
        return False
    if int(task.retry_count or 0) >= MAX_USER_RETRIES:
        return False
    return True


def prepare_retry(task: Task, *, timeout_at: datetime) -> None:
    """Reset task to queued for another attempt (quota reserved separately)."""
    task.status = TaskStatus.QUEUED.value
    task.progress = 10
    task.retry_count = int(task.retry_count or 0) + 1
    task.timeout_at = timeout_at
    task.started_at = None
    task.finished_at = None
    task.result_expires_at = None
    task.error_code = None
    task.error_class = None
    task.error_detail = None
    task.quota_settled = 0
    # keep input_meta; clear previous output / userMsg
    task.output_meta = None


def sweep_timed_out_tasks(session: Session, *, limit: int = 100) -> int:
    """
    Mark overdue queued/running tasks as timeout failed.
    Caller should settle quota (refund) after.
    """
    now = _now()
    tasks = list(
        session.scalars(
            select(Task)
            .where(
                Task.status.in_(
                    (
                        TaskStatus.PENDING.value,
                        TaskStatus.QUEUED.value,
                        TaskStatus.RUNNING.value,
                    )
                ),
                Task.timeout_at.is_not(None),
                Task.timeout_at < now,
            )
            .order_by(Task.id.asc())
            .limit(limit)
        )
    )
    n = 0
    err = ErrorCode.TASK_TIMEOUT.defn
    for task in tasks:
        apply_failed(
            task,
            error_code=err.code,
            error_class=ErrorClass.TIMEOUT.value,
            error_detail="timeout_at exceeded",
            user_msg=err.user_msg,
        )
        n += 1
    return n


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _input_file_summary(task: Task) -> tuple[str | None, int | None, str | None]:
    """First input filename + total size from input_meta.inputs (list UI)."""
    meta = task.input_meta if isinstance(task.input_meta, dict) else {}
    inputs = [i for i in (meta.get("inputs") or []) if isinstance(i, dict)]
    if not inputs:
        return None, None, None
    first = inputs[0]
    raw_name = first.get("filename") or first.get("cosKey") or first.get("cos_key")
    filename = Path(str(raw_name)).name if raw_name else None
    total = 0
    has_size = False
    for item in inputs:
        raw_size = item.get("sizeBytes", item.get("size_bytes"))
        if raw_size is None:
            continue
        try:
            total += int(raw_size)
            has_size = True
        except (TypeError, ValueError):
            pass
    size_bytes = total if has_size else None
    size_label = _format_size(size_bytes) if size_bytes is not None else None
    return filename, size_bytes, size_label


def task_to_list_item(task: Task) -> dict:
    user_msg = None
    if task.output_meta and isinstance(task.output_meta, dict):
        user_msg = task.output_meta.get("userMsg")
    if user_msg is None and task.error_code:
        from oc_shared.error_codes import get_error

        e = get_error(task.error_code)
        user_msg = e.defn.user_msg if e else None
    filename, size_bytes, size_label = _input_file_summary(task)
    return {
        "taskId": task.public_id,
        "type": task.type,
        "status": task.status,
        "progress": task.progress,
        "filename": filename,
        "sizeBytes": size_bytes,
        "sizeLabel": size_label,
        "costQuota": task.cost_quota,
        "timeoutAt": task.timeout_at.isoformat() if task.timeout_at else None,
        "resultExpiresAt": task.result_expires_at.isoformat() if task.result_expires_at else None,
        "resultExpired": bool(
            task.result_expires_at and task.result_expires_at < _now()
        ),
        "retryCount": task.retry_count,
        "errorCode": task.error_code,
        "errorClass": task.error_class,
        "userMsg": user_msg,
        "createdAt": task.created_at.isoformat() if task.created_at else None,
    }


def task_to_detail(task: Task, *, download_url: str | None = None) -> dict:
    data = task_to_list_item(task)
    outputs: list[dict] = []
    meta = task.output_meta if isinstance(task.output_meta, dict) else {}
    if (
        task.status == TaskStatus.SUCCEEDED.value
        and meta.get("cosKey")
        and not data["resultExpired"]
    ):
        outputs.append(
            {
                "filename": meta.get("filename") or "result.pdf",
                "sizeBytes": meta.get("sizeBytes"),
                "downloadUrl": download_url,
                "cosKey": meta.get("cosKey"),
            }
        )
    data.update(
        {
            "inputMeta": task.input_meta,
            "outputMeta": task.output_meta,
            "outputs": outputs,
            "startedAt": task.started_at.isoformat() if task.started_at else None,
            "finishedAt": task.finished_at.isoformat() if task.finished_at else None,
        }
    )
    return data
