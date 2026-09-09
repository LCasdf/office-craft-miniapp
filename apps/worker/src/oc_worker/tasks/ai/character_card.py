"""Celery AI task — character card PNG via Pillow."""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from celery.exceptions import SoftTimeLimitExceeded
from oc_core.character_cards import get_by_public_id, set_cover_key
from oc_core.config import get_settings
from oc_core.converters.character_card_image import render_character_card_png
from oc_core.db import session_scope
from oc_core.storage import put_bytes, result_object_key
from oc_core.tasks_repo import bump_progress, mark_failed, mark_running, mark_succeeded
from oc_shared.constants import TASK_TIMEOUTS
from oc_shared.enums import ErrorClass
from oc_shared.error_codes import ErrorCode
from oc_worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

_TIMEOUT = TASK_TIMEOUTS.get("character_card", 120)


@celery_app.task(
    name="oc_worker.tasks.ai.character_card.character_card_task",
    bind=True,
    soft_time_limit=max(_TIMEOUT - 10, 30),
    time_limit=_TIMEOUT,
)
def character_card_task(self, task_id: str, request_id: str = "") -> dict:
    structlog.contextvars.bind_contextvars(task_id=task_id, request_id=request_id)

    with session_scope() as session:
        task = mark_running(session, task_id)
        if task is None:
            return {"taskId": task_id, "status": "missing"}
        if task.status in ("succeeded", "failed", "cancelled"):
            return {"taskId": task_id, "status": task.status, "skipped": True}
        input_meta = dict(task.input_meta or {})
        user_id = str(task.user_id)

    card_id = input_meta.get("cardId")
    if not card_id:
        err = ErrorCode.PARAM_INVALID.defn
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=err.code,
                error_class=ErrorClass.USER.value,
                error_detail="missing cardId",
                user_msg=err.user_msg,
            )
        return {"taskId": task_id, "status": "failed"}

    try:
        with session_scope() as session:
            card = get_by_public_id(session, str(card_id), user_id=int(user_id))
            if card is None:
                raise RuntimeError("card not found")
            payload = dict(card.payload_json or {})

        bump_progress_safe(task_id, 30)
        with tempfile.TemporaryDirectory(prefix="oc_card_") as tmp:
            out = Path(tmp) / "character_card.png"
            render_character_card_png(payload, out)
            data = out.read_bytes()

        bump_progress_safe(task_id, 70)
        settings = get_settings()
        env = settings.cos_env_prefix or settings.app_env
        filename = "character_card.png"
        cos_key = result_object_key(
            env=env, user_id=user_id, task_id=task_id, filename=filename
        )
        put_bytes(cos_key, data, content_type="image/png")

        output_meta = {
            "cosKey": cos_key,
            "filename": filename,
            "sizeBytes": len(data),
            "cardId": card_id,
            "contentType": "image/png",
        }
        with session_scope() as session:
            mark_succeeded(session, task_id, output_meta=output_meta)
            card = get_by_public_id(session, str(card_id), user_id=int(user_id))
            if card is not None:
                set_cover_key(session, card, cos_key)

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
        return {"taskId": task_id, "status": "failed", "errorCode": err.code}
    except Exception as e:
        logger.exception("character_card_failed", error=str(e))
        err = ErrorCode.INTERNAL_ERROR.defn
        with session_scope() as session:
            mark_failed(
                session,
                task_id,
                error_code=err.code,
                error_class=ErrorClass.SYSTEM.value,
                error_detail=str(e)[:2000],
                user_msg=err.user_msg,
            )
        return {"taskId": task_id, "status": "failed", "errorCode": err.code}


def bump_progress_safe(task_id: str, progress: int) -> None:
    with session_scope() as session:
        bump_progress(session, task_id, progress)
