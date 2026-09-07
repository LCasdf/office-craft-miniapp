"""Shared tool-task runner: download → convert → upload → writeback."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import structlog
from oc_core.config import get_settings
from oc_core.db import session_scope
from oc_core.storage import get_bytes, put_bytes, result_object_key
from oc_core.tasks_repo import mark_failed, mark_running, mark_succeeded
from oc_core.cleanup import delete_task_input_objects
from oc_shared.enums import ErrorClass, TaskStatus
from oc_shared.error_codes import ErrorCode

logger = structlog.get_logger(__name__)


class UserFacingError(Exception):
    def __init__(self, code: ErrorCode, detail: str = "", *, user_msg: str | None = None):
        super().__init__(detail or code.defn.user_msg)
        self.code = code
        self.detail = detail
        self.user_msg = user_msg or code.defn.user_msg


ConvertFn = Callable[[Path, dict], Path]


def _mark_timeout(task_id: str, detail: str) -> dict:
    err = ErrorCode.TASK_TIMEOUT.defn
    with session_scope() as session:
        mark_failed(
            session,
            task_id,
            error_code=err.code,
            error_class=ErrorClass.TIMEOUT.value,
            error_detail=detail[:2000],
            user_msg=err.user_msg,
        )
    return {"taskId": task_id, "status": "failed", "errorCode": err.code}


def run_file_tool(
    *,
    task_id: str,
    request_id: str,
    convert: ConvertFn,
    result_filename: str = "result.pdf",
    content_type: str = "application/pdf",
) -> dict:
    structlog.contextvars.bind_contextvars(task_id=task_id, request_id=request_id)

    with session_scope() as session:
        task = mark_running(session, task_id)
        if task is None:
            logger.warning("tool_task_missing", task_id=task_id)
            return {"taskId": task_id, "status": "missing"}
        if task.status in (
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        ):
            return {"taskId": task_id, "status": task.status, "skipped": True}
        input_meta = dict(task.input_meta or {})
        user_id = str(task.user_id)

    settings = get_settings()
    env = settings.cos_env_prefix or settings.app_env
    inputs = list(input_meta.get("inputs") or [])
    params = dict(input_meta.get("params") or {})

    try:
        if not inputs:
            raise UserFacingError(ErrorCode.PARAM_INVALID, "missing inputs")

        with tempfile.TemporaryDirectory(prefix="oc_tool_") as tmp:
            tmp_path = Path(tmp)
            local_files: list[Path] = []
            for i, item in enumerate(inputs):
                key = item.get("cosKey") or item.get("cos_key")
                if not key:
                    raise UserFacingError(ErrorCode.PARAM_INVALID, f"input[{i}] missing cosKey")
                name = Path(item.get("filename") or f"in_{i}").name
                dest = tmp_path / f"{i}_{name}"
                dest.write_bytes(get_bytes(key))
                local_files.append(dest)

            out_pdf = convert(tmp_path, {"files": local_files, "params": params})
            if not out_pdf.is_file():
                raise RuntimeError("converter produced no file")
            data = out_pdf.read_bytes()
            cos_key = result_object_key(
                env=env, user_id=user_id, task_id=task_id, filename=result_filename
            )
            put_bytes(cos_key, data, content_type=content_type)
            size = len(data)
            input_bytes = sum(p.stat().st_size for p in local_files)

        output_meta = {
            "cosKey": cos_key,
            "filename": result_filename,
            "sizeBytes": size,
            "inputBytes": input_bytes,
            "outputBytes": size,
            "ratio": round(size / input_bytes, 4) if input_bytes else None,
        }
        with session_scope() as session:
            mark_succeeded(session, task_id, output_meta=output_meta)
        # Active input cleanup after success (TTL still backs orphan/missed paths)
        n = delete_task_input_objects(input_meta)
        if n:
            logger.info("task_inputs_deleted", deleted=n)
        logger.info("tool_task_done", size=size)
        return {"taskId": task_id, "status": "succeeded", "cosKey": cos_key}

    except UserFacingError as e:
        logger.info("tool_task_user_error", code=e.code.defn.code, detail=e.detail)
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=e.code.defn.code,
                error_class=ErrorClass.USER.value,
                error_detail=e.detail,
                user_msg=e.user_msg,
            )
        delete_task_input_objects(input_meta)
        return {"taskId": task_id, "status": "failed", "errorCode": e.code.defn.code}
    except Exception as e:
        # Celery soft/hard time limit
        name = type(e).__name__
        if "TimeLimit" in name or "SoftTimeLimit" in name:
            logger.warning("tool_task_timeout", error=str(e))
            delete_task_input_objects(input_meta)
            return _mark_timeout(task_id, str(e))
        logger.exception("tool_task_system_error", error=str(e))
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=ErrorCode.INTERNAL_ERROR.defn.code,
                error_class=ErrorClass.SYSTEM.value,
                error_detail=str(e)[:2000],
                user_msg=ErrorCode.INTERNAL_ERROR.defn.user_msg,
            )
        delete_task_input_objects(input_meta)
        return {"taskId": task_id, "status": "failed", "errorCode": 50001}
