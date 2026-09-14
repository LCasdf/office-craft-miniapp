"""Celery AI task — PPT generate via python-pptx."""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from oc_core.config import get_settings
from oc_core.converters.pptx_fill import PptxError, render_outline_pptx
from oc_core.db import session_scope
from oc_core.storage import put_bytes, result_object_key
from oc_core.tasks_repo import bump_progress, mark_failed, mark_running, mark_succeeded
from oc_shared.constants import TASK_TIMEOUTS
from oc_shared.enums import ErrorClass
from oc_shared.error_codes import ErrorCode
from oc_worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

_TIMEOUT = TASK_TIMEOUTS.get("ppt_generate", 120)


def bump_progress_safe(task_id: str, progress: int) -> None:
    try:
        with session_scope() as session:
            bump_progress(session, task_id, progress)
    except Exception:
        pass


@celery_app.task(
    name="oc_worker.tasks.ai.ppt_generate.ppt_generate_task",
    bind=True,
    soft_time_limit=max(_TIMEOUT - 10, 30),
    time_limit=_TIMEOUT,
)
def ppt_generate_task(self, task_id: str, request_id: str = "") -> dict:
    structlog.contextvars.bind_contextvars(task_id=task_id, request_id=request_id)

    with session_scope() as session:
        task = mark_running(session, task_id)
        if task is None:
            return {"taskId": task_id, "status": "missing"}
        if task.status in ("succeeded", "failed", "cancelled"):
            return {"taskId": task_id, "status": task.status, "skipped": True}
        input_meta = dict(task.input_meta or {})
        user_id = str(task.user_id)

    pages = input_meta.get("pages") or []
    if not pages:
        err = ErrorCode.PARAM_INVALID.defn
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=err.code,
                error_class=ErrorClass.USER.value,
                error_detail="missing pages",
                user_msg=err.user_msg,
            )
        return {"taskId": task_id, "status": "failed"}

    try:
        bump_progress_safe(task_id, 25)
        with tempfile.TemporaryDirectory(prefix="oc_ppt_") as tmp:
            out = Path(tmp) / "deck.pptx"
            render_outline_pptx(pages, out)
            data = out.read_bytes()

        bump_progress_safe(task_id, 75)
        settings = get_settings()
        env = settings.cos_env_prefix or settings.app_env
        filename = "deck.pptx"
        cos_key = result_object_key(
            env=env, user_id=user_id, task_id=task_id, filename=filename
        )
        put_bytes(
            cos_key,
            data,
            content_type=(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
        )
        output_meta = {
            "cosKey": cos_key,
            "filename": filename,
            "sizeBytes": len(data),
            "outlineId": input_meta.get("outlineId"),
            "templateId": input_meta.get("templateId"),
            "pageCount": len(pages),
        }
        with session_scope() as session:
            mark_succeeded(session, task_id, output_meta=output_meta)
        return {"taskId": task_id, "status": "succeeded", "cosKey": cos_key}
    except SoftTimeLimitExceeded:
        err = ErrorCode.TASK_TIMEOUT.defn
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=err.code,
                error_class=ErrorClass.TIMEOUT.value,
                error_detail="soft time limit",
                user_msg=err.user_msg,
            )
        return {"taskId": task_id, "status": "failed"}
    except PptxError as e:
        err = ErrorCode.PARAM_INVALID.defn
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=err.code,
                error_class=ErrorClass.USER.value,
                error_detail=str(e),
                user_msg="PPT 内容无效，请检查大纲后重试",
            )
        return {"taskId": task_id, "status": "failed"}
    except Exception as e:
        logger.exception("ppt_generate_failed", error=str(e))
        err = ErrorCode.INTERNAL_ERROR.defn
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=err.code,
                error_class=ErrorClass.SYSTEM.value,
                error_detail=str(e)[:200],
                user_msg=err.user_msg,
            )
        return {"taskId": task_id, "status": "failed"}
