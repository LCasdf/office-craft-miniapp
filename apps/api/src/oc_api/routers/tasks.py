"""Task routes — create / list / detail; quota + idempotency + inflight."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Header, Request, Response
from oc_core.config import get_settings
from oc_core.db import session_scope
from oc_core.quota import (
    QuotaError,
    assert_inflight_ok,
    cancel_task,
    reserve_for_user,
    settle_task_for_user,
    settle_unsettled_for_user,
)
from oc_core.storage import presign_get
from oc_core.tasks_repo import (
    DEV_USER_ID,
    create_task_row,
    delete_all_for_user,
    delete_for_user,
    get_by_idempotency,
    get_by_public_id,
    is_retryable,
    list_for_user,
    prepare_retry,
    sweep_timed_out_tasks,
    task_to_detail,
    task_to_list_item,
)
from oc_shared.constants import (
    DEFAULT_TASK_TIMEOUT_SECONDS,
    IMAGE_TO_PDF_EXTS,
    IMAGE_TO_PDF_MAX_COUNT,
    OFFICE_TO_PDF_EXTS,
    PDF_COMPRESS_MAX_BYTES,
    PDF_COMPRESS_QUALITIES,
    PDF_EXTS,
    PDF_MERGE_MAX_COUNT,
    PDF_MERGE_MAX_FILE_BYTES,
    PDF_MERGE_MAX_TOTAL_BYTES,
    PDF_MERGE_MIN_COUNT,
    TASK_COST_QUOTA,
    TASK_TIMEOUTS,
)
from oc_shared.enums import TaskType
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import envelope_err, envelope_ok
from pydantic import BaseModel, Field

router = APIRouter(prefix="/tasks", tags=["tasks"])


class CreateTaskBody(BaseModel):
    type: TaskType
    upload_id: str | None = Field(default=None, alias="uploadId")
    inputs: list[dict] = Field(default_factory=list)
    params: dict | None = None

    model_config = {"populate_by_name": True}


def _item_name(item: dict) -> str:
    return str(item.get("filename") or item.get("cosKey") or item.get("cos_key") or "")


def _item_size(item: dict) -> int | None:
    raw = item.get("sizeBytes") if "sizeBytes" in item else item.get("size_bytes")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _request_fingerprint(body: CreateTaskBody) -> str:
    inputs = []
    for item in body.inputs or []:
        if not isinstance(item, dict):
            continue
        inputs.append(
            {
                "cosKey": item.get("cosKey") or item.get("cos_key"),
                "filename": item.get("filename"),
                "sizeBytes": item.get("sizeBytes", item.get("size_bytes")),
            }
        )
    payload = {
        "type": body.type.value,
        "uploadId": body.upload_id,
        "inputs": inputs,
        "params": body.params or {},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_inputs(body: CreateTaskBody) -> str | None:
    """Return user_msg on validation failure."""
    inputs = body.inputs or []
    if body.type == TaskType.IMAGE_TO_PDF:
        if not (1 <= len(inputs) <= IMAGE_TO_PDF_MAX_COUNT):
            return f"图片数量须为 1–{IMAGE_TO_PDF_MAX_COUNT}"
        for item in inputs:
            key = item.get("cosKey") or item.get("cos_key")
            if not key:
                return "缺少 cosKey"
            if Path(_item_name(item) or key).suffix.lower() not in IMAGE_TO_PDF_EXTS:
                return "仅支持 jpg/png/webp"
        return None
    if body.type == TaskType.OFFICE_TO_PDF:
        if len(inputs) != 1:
            return "Word 转 PDF 每次仅支持 1 个文件"
        item = inputs[0]
        if not (item.get("cosKey") or item.get("cos_key")):
            return "缺少 cosKey"
        if Path(_item_name(item)).suffix.lower() not in OFFICE_TO_PDF_EXTS:
            return "仅支持 doc/docx"
        return None
    if body.type == TaskType.PDF_COMPRESS:
        if len(inputs) != 1:
            return "PDF 压缩每次仅支持 1 个文件"
        item = inputs[0]
        if not (item.get("cosKey") or item.get("cos_key")):
            return "缺少 cosKey"
        if Path(_item_name(item)).suffix.lower() not in PDF_EXTS:
            return "仅支持 PDF"
        size = _item_size(item)
        if size is not None and size > PDF_COMPRESS_MAX_BYTES:
            return "单个 PDF 不能超过 50MB"
        quality = (body.params or {}).get("quality")
        if quality not in PDF_COMPRESS_QUALITIES:
            return "请选择压缩档位：高质量 / 标准 / 极限"
        return None
    if body.type == TaskType.PDF_MERGE:
        if not (PDF_MERGE_MIN_COUNT <= len(inputs) <= PDF_MERGE_MAX_COUNT):
            return f"合并须选择 {PDF_MERGE_MIN_COUNT}–{PDF_MERGE_MAX_COUNT} 个 PDF"
        total = 0
        for item in inputs:
            if not (item.get("cosKey") or item.get("cos_key")):
                return "缺少 cosKey"
            if Path(_item_name(item)).suffix.lower() not in PDF_EXTS:
                return "仅支持 PDF"
            size = _item_size(item)
            if size is not None:
                if size > PDF_MERGE_MAX_FILE_BYTES:
                    return "单个 PDF 不能超过 30MB"
                total += size
        if total > PDF_MERGE_MAX_TOTAL_BYTES:
            return "合计大小不能超过 50MB"
        return None
    return None


def _enqueue(task_type: TaskType, task_id: str, request_id: str) -> None:
    if task_type == TaskType.IMAGE_TO_PDF:
        from oc_worker.tasks.tools.pdf_convert import image_to_pdf_task

        image_to_pdf_task.apply_async(
            kwargs={"task_id": task_id, "request_id": request_id},
            queue="q.tools",
        )
        return
    if task_type == TaskType.OFFICE_TO_PDF:
        from oc_worker.tasks.tools.pdf_convert import office_to_pdf_task

        office_to_pdf_task.apply_async(
            kwargs={"task_id": task_id, "request_id": request_id},
            queue="q.tools",
        )
        return
    if task_type == TaskType.PDF_COMPRESS:
        from oc_worker.tasks.tools.pdf_convert import pdf_compress_task

        pdf_compress_task.apply_async(
            kwargs={"task_id": task_id, "request_id": request_id},
            queue="q.tools",
        )
        return
    if task_type == TaskType.PDF_MERGE:
        from oc_worker.tasks.tools.pdf_convert import pdf_merge_task

        pdf_merge_task.apply_async(
            kwargs={"task_id": task_id, "request_id": request_id},
            queue="q.tools",
        )
        return
    if task_type == TaskType.CHARACTER_CARD:
        from oc_worker.tasks.ai.character_card import character_card_task

        character_card_task.apply_async(
            kwargs={"task_id": task_id, "request_id": request_id},
            queue="q.ai",
        )
        return
    if task_type == TaskType.PPT_GENERATE:
        from oc_worker.tasks.ai.ppt_generate import ppt_generate_task

        ppt_generate_task.apply_async(
            kwargs={"task_id": task_id, "request_id": request_id},
            queue="q.ai",
        )
        return
    from oc_worker.tasks.ping import ping_task

    ping_task.apply_async(
        kwargs={"task_id": task_id, "request_id": request_id},
        queue="q.tools",
    )


def _queue_overloaded() -> bool:
    """Reject create when tools queue depth hits configured max (G1 overload)."""
    from oc_core.alerts import queue_depth

    settings = get_settings()
    max_depth = int(settings.alert_queue_depth_max or 100)
    depth = queue_depth("q.tools")
    return depth >= 0 and depth >= max_depth


@router.post("")
def create_task(
    body: CreateTaskBody,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    if not idempotency_key:
        err = ErrorCode.IDEMPOTENCY_REQUIRED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    if _queue_overloaded():
        err = ErrorCode.QUEUE_OVERLOADED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    bad = _validate_inputs(body)
    if bad:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, bad, request_id)

    if body.type in (
        TaskType.IMAGE_TO_PDF,
        TaskType.OFFICE_TO_PDF,
        TaskType.PDF_COMPRESS,
        TaskType.PDF_MERGE,
    ) and not body.inputs:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "请先上传文件", request_id)

    fingerprint = _request_fingerprint(body)
    public_id = uuid.uuid4().hex[:26]
    timeout_sec = TASK_TIMEOUTS.get(body.type.value, DEFAULT_TASK_TIMEOUT_SECONDS)
    timeout_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=timeout_sec)
    cost = TASK_COST_QUOTA.get(body.type.value, 0)
    input_meta = {
        "uploadId": body.upload_id,
        "inputs": body.inputs,
        "params": body.params,
        "fingerprint": fingerprint,
    }
    settings = get_settings()

    try:
        with session_scope() as session:
            existing = get_by_idempotency(
                session, user_id=DEV_USER_ID, key=idempotency_key
            )
            if existing is not None:
                old_fp = None
                if isinstance(existing.input_meta, dict):
                    old_fp = existing.input_meta.get("fingerprint")
                if old_fp and old_fp != fingerprint:
                    err = ErrorCode.IDEMPOTENCY_CONFLICT.defn
                    return envelope_err(err.code, err.message, err.user_msg, request_id)
                settle_task_for_user(session, existing)
                data = task_to_list_item(existing)
                response.headers["Idempotent-Replayed"] = "true"
                return envelope_ok(
                    data, request_id, user_msg="任务已提交", task_id=existing.public_id
                )

            assert_inflight_ok(
                session, DEV_USER_ID, limit=settings.max_inflight_tasks_per_user
            )
            reserve_for_user(session, DEV_USER_ID, cost)
            task, created_new = create_task_row(
                session,
                public_id=public_id,
                user_id=DEV_USER_ID,
                task_type=body.type.value,
                idempotency_key=idempotency_key,
                timeout_at=timeout_at,
                input_meta=input_meta,
                cost_quota=cost,
            )
            data = task_to_list_item(task)
            task_public_id = task.public_id
            task_type = TaskType(task.type)
    except QuotaError as e:
        if e.code == "exhausted":
            err = ErrorCode.QUOTA_EXHAUSTED.defn
        else:
            err = ErrorCode.TOO_MANY_INFLIGHT.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    if created_new:
        try:
            _enqueue(task_type, task_public_id, request_id)
        except Exception:
            pass

    return envelope_ok(data, request_id, user_msg="任务已提交", task_id=task_public_id)


@router.get("")
def list_tasks(request: Request, cursor: str | None = None, limit: int = 20):
    request_id = getattr(request.state, "request_id", "unknown")
    limit = max(1, min(limit, 50))
    try:
        with session_scope() as session:
            # Fail stuck tasks on poll so UI doesn't wait for Beat
            sweep_timed_out_tasks(session)
            settle_unsettled_for_user(session, DEV_USER_ID)
            items = [
                task_to_list_item(t)
                for t in list_for_user(
                    session,
                    DEV_USER_ID,
                    limit=limit,
                    exclude_types=("character_card",),
                )
            ]
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok({"items": items, "nextCursor": None, "hasMore": False}, request_id)


@router.get("/{task_id}")
def get_task(task_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            task = get_by_public_id(session, task_id, user_id=DEV_USER_ID)
            if task is None:
                err = ErrorCode.TASK_NOT_FOUND.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            settle_task_for_user(session, task)
            download_url = None
            meta = task.output_meta if isinstance(task.output_meta, dict) else {}
            cos_key = meta.get("cosKey")
            now = datetime.now(UTC).replace(tzinfo=None)
            expired = bool(task.result_expires_at and task.result_expires_at < now)
            if cos_key and task.status == "succeeded" and not expired:
                try:
                    download_url = presign_get(cos_key)
                except Exception:
                    download_url = None
            data = task_to_detail(task, download_url=download_url)
            if expired and task.status == "succeeded":
                data["userMsg"] = ErrorCode.RESULT_EXPIRED.defn.user_msg
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(data, request_id, task_id=task_id)


@router.post("/{task_id}/cancel")
def cancel_task_route(task_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            task = get_by_public_id(session, task_id, user_id=DEV_USER_ID)
            if task is None:
                err = ErrorCode.TASK_NOT_FOUND.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            if not cancel_task(session, task):
                err = ErrorCode.TASK_NOT_CANCELLABLE.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            data = task_to_list_item(task)
            data["quotaRefunded"] = True
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(
        data, request_id, user_msg="任务已取消，额度已返还", task_id=task_id
    )


@router.post("/{task_id}/retry")
def retry_task(
    task_id: str,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    if not idempotency_key:
        err = ErrorCode.IDEMPOTENCY_REQUIRED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    settings = get_settings()
    try:
        with session_scope() as session:
            existing = get_by_idempotency(
                session, user_id=DEV_USER_ID, key=idempotency_key
            )
            if existing is not None:
                settle_task_for_user(session, existing)
                response.headers["Idempotent-Replayed"] = "true"
                return envelope_ok(
                    task_to_list_item(existing),
                    request_id,
                    user_msg="任务已提交",
                    task_id=existing.public_id,
                )

            task = get_by_public_id(session, task_id, user_id=DEV_USER_ID)
            if task is None:
                err = ErrorCode.TASK_NOT_FOUND.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            settle_task_for_user(session, task)
            if not is_retryable(task):
                err = ErrorCode.TASK_NOT_RETRYABLE.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)

            assert_inflight_ok(
                session, DEV_USER_ID, limit=settings.max_inflight_tasks_per_user
            )
            cost = int(task.cost_quota or TASK_COST_QUOTA.get(task.type, 0))
            reserve_for_user(session, DEV_USER_ID, cost)
            timeout_sec = TASK_TIMEOUTS.get(task.type, DEFAULT_TASK_TIMEOUT_SECONDS)
            timeout_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                seconds=timeout_sec
            )
            prepare_retry(task, timeout_at=timeout_at)
            task.idempotency_key = idempotency_key
            data = task_to_list_item(task)
            task_type = TaskType(task.type)
            task_public_id = task.public_id
    except QuotaError as e:
        if e.code == "exhausted":
            err = ErrorCode.QUOTA_EXHAUSTED.defn
        else:
            err = ErrorCode.TOO_MANY_INFLIGHT.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        _enqueue(task_type, task_public_id, request_id)
    except Exception:
        pass
    return envelope_ok(data, request_id, user_msg="已重新提交", task_id=task_public_id)


@router.get("/{task_id}/download")
def download_task(task_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            task = get_by_public_id(session, task_id, user_id=DEV_USER_ID)
            if task is None:
                err = ErrorCode.TASK_NOT_FOUND.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            settle_task_for_user(session, task)
            if task.status != "succeeded":
                err = ErrorCode.RESULT_NOT_READY.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            now = datetime.now(UTC).replace(tzinfo=None)
            if task.result_expires_at and task.result_expires_at < now:
                err = ErrorCode.RESULT_EXPIRED.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            meta = task.output_meta if isinstance(task.output_meta, dict) else {}
            cos_key = meta.get("cosKey")
            if not cos_key:
                err = ErrorCode.RESULT_EXPIRED.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            url = presign_get(str(cos_key))
            data = {
                "taskId": task.public_id,
                "filename": meta.get("filename") or "result.pdf",
                "sizeBytes": meta.get("sizeBytes"),
                "downloadUrl": url,
            }
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(data, request_id, task_id=task_id)


@router.delete("")
def clear_tasks(request: Request):
    """Clear all tasks for current user (hard delete; refunds unsettled freezes)."""
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            deleted = delete_all_for_user(session, DEV_USER_ID)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(
        {"deleted": deleted},
        request_id,
        user_msg="已清空任务" if deleted else "暂无任务",
    )


@router.delete("/{task_id}")
def delete_task(task_id: str, request: Request):
    """Remove task from user's list (hard delete row; refunds unsettled freeze)."""
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            ok = delete_for_user(session, task_id, user_id=DEV_USER_ID)
            if not ok:
                err = ErrorCode.TASK_NOT_FOUND.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok({"taskId": task_id, "deleted": True}, request_id, task_id=task_id)
