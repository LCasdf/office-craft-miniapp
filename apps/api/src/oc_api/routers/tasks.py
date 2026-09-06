"""Task routes — M0 empty pipeline enqueue."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from oc_shared.constants import DEFAULT_TASK_TIMEOUT_SECONDS, TASK_TIMEOUTS
from oc_shared.enums import TaskStatus, TaskType
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import envelope_err, envelope_ok

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskBody(BaseModel):
    type: TaskType
    upload_id: str | None = Field(default=None, alias="uploadId")
    inputs: list[dict] = Field(default_factory=list)
    params: dict | None = None

    model_config = {"populate_by_name": True}


@router.post("")
def create_task(
    body: CreateTaskBody,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    if not idempotency_key:
        err = ErrorCode.IDEMPOTENCY_REQUIRED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    public_id = uuid.uuid4().hex[:26]
    timeout_sec = TASK_TIMEOUTS.get(body.type.value, DEFAULT_TASK_TIMEOUT_SECONDS)
    timeout_at = datetime.now(UTC) + timedelta(seconds=timeout_sec)

    # Enqueue empty Celery ping for M0 smoke (ignore failures if broker down)
    try:
        from oc_worker.tasks.ping import ping_task

        ping_task.apply_async(
            kwargs={"task_id": public_id, "request_id": request_id},
            queue="q.tools",
        )
        status = TaskStatus.QUEUED.value
        progress = 10
    except Exception:
        status = TaskStatus.PENDING.value
        progress = 0

    data = {
        "taskId": public_id,
        "type": body.type.value,
        "status": status,
        "progress": progress,
        "costQuota": 0,
        "timeoutAt": timeout_at.isoformat(),
        "resultExpiresAt": None,
        "resultExpired": False,
        "retryCount": 0,
        "errorCode": None,
        "errorClass": None,
        "userMsg": None,
        "createdAt": datetime.now(UTC).isoformat(),
    }
    return envelope_ok(data, request_id, user_msg="任务已提交", task_id=public_id)


@router.get("")
def list_tasks(request: Request, cursor: str | None = None, limit: int = 20):
    request_id = getattr(request.state, "request_id", "unknown")
    return envelope_ok({"items": [], "nextCursor": None, "hasMore": False}, request_id)


@router.get("/{task_id}")
def get_task(task_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    return envelope_ok(
        {
            "taskId": task_id,
            "type": "pdf_compress",
            "status": TaskStatus.SUCCEEDED.value,
            "progress": 100,
            "costQuota": 0,
            "timeoutAt": None,
            "resultExpiresAt": None,
            "resultExpired": False,
            "retryCount": 0,
            "errorCode": None,
            "errorClass": None,
            "userMsg": None,
            "inputMeta": None,
            "outputMeta": {"note": "M0 stub"},
            "outputs": [],
            "createdAt": None,
            "startedAt": None,
            "finishedAt": None,
        },
        request_id,
        task_id=task_id,
    )
