"""AI PPT routes — outline / put / generate."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, Request, Response
from oc_core.ai.client import build_ai_client, parse_ppt_outline_content
from oc_core.ai.ppt_outline_schema import (
    OutlineSchemaError,
    normalize_pages,
    validate_page_count,
    validate_template_id,
)
from oc_core.ai.prompts import PPT_OUTLINE_PROMPT_VERSION, ppt_outline_messages
from oc_core.config import get_settings
from oc_core.db import session_scope
from oc_core.moderation import ContentBlocked, moderate_text
from oc_core.ppt_outlines import (
    VersionConflict,
    create_outline,
    get_by_idempotency,
    get_by_public_id,
    outline_to_dict,
    update_pages,
)
from oc_core.quota import QuotaError, assert_inflight_ok, reserve_for_user
from oc_core.tasks_repo import DEV_USER_ID, create_task_row, get_by_idempotency as get_task_by_idem
from oc_core.tasks_repo import task_to_list_item
from oc_shared.constants import (
    AI_TEXT_MAX_CHARS,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    TASK_COST_QUOTA,
    TASK_TIMEOUTS,
)
from oc_shared.enums import TaskType
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import envelope_err, envelope_ok
from pydantic import BaseModel, Field

router = APIRouter(prefix="/ai/ppt", tags=["ai"])

PPT_COST = TASK_COST_QUOTA.get("ppt_generate", 5)


class OutlineBody(BaseModel):
    topic: str = Field(..., min_length=1)
    pageCount: int = Field(..., ge=5, le=15)
    templateId: str = Field(default="tpl_basic_01")
    audience: str | None = None
    language: str | None = "zh-CN"

    model_config = {"populate_by_name": True}


class PutOutlineBody(BaseModel):
    version: int | None = None
    pages: list[dict]
    templateId: str | None = None

    model_config = {"populate_by_name": True}


class GenerateBody(BaseModel):
    outlineId: str
    outlineVersion: int
    templateId: str
    pages: list[dict]

    model_config = {"populate_by_name": True}


def _fingerprint_outline(topic: str, page_count: int, template_id: str) -> str:
    payload = {
        "topic": topic.strip(),
        "pageCount": page_count,
        "templateId": template_id,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _enqueue_ppt(task_id: str, request_id: str) -> None:
    from oc_worker.tasks.ai.ppt_generate import ppt_generate_task

    ppt_generate_task.apply_async(
        kwargs={"task_id": task_id, "request_id": request_id},
        queue="q.ai",
    )


@router.post("/outline")
def create_ppt_outline(
    body: OutlineBody,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    topic = (body.topic or "").strip()
    if not topic:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "请填写主题", request_id)
    if len(topic) > AI_TEXT_MAX_CHARS:
        err = ErrorCode.INPUT_TOO_LONG.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        page_count = validate_page_count(body.pageCount)
        template_id = validate_template_id(body.templateId or "tpl_basic_01")
        moderate_text(topic)
        if body.audience:
            moderate_text(body.audience)
    except OutlineSchemaError as e:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, str(e) or err.user_msg, request_id)
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    fp = _fingerprint_outline(topic, page_count, template_id)
    settings = get_settings()

    try:
        with session_scope() as session:
            if idempotency_key:
                existing = get_by_idempotency(
                    session, user_id=DEV_USER_ID, key=idempotency_key
                )
                if existing is not None:
                    response.headers["Idempotent-Replayed"] = "true"
                    data = outline_to_dict(existing)
                    data["costQuota"] = 0
                    return envelope_ok(
                        data,
                        request_id,
                        user_msg="大纲已生成，请编辑确认后再导出 PPT",
                    )

            client = build_ai_client(settings.ai_provider)
            result = client.complete(
                messages=ppt_outline_messages(
                    topic, page_count=page_count, audience=body.audience or ""
                ),
                extra={"purpose": "ppt_outline", "fingerprint": fp},
            )
            pages = parse_ppt_outline_content(result.content)
            # Clamp to requested count if mock/model drifts
            if len(pages) != page_count:
                from oc_core.ai.ppt_outline_schema import mock_outline_pages

                pages = mock_outline_pages(topic, page_count)

            row = create_outline(
                session,
                public_id=uuid.uuid4().hex[:26],
                user_id=DEV_USER_ID,
                topic=topic,
                template_id=template_id,
                pages=pages,
                idempotency_key=idempotency_key,
                prompt_version=PPT_OUTLINE_PROMPT_VERSION,
            )
            data = outline_to_dict(row)
            data["costQuota"] = 0
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except (OutlineSchemaError, json.JSONDecodeError, ValueError):
        err = ErrorCode.AI_UPSTREAM_FAILED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    return envelope_ok(
        data, request_id, user_msg="大纲已生成，请编辑确认后再导出 PPT"
    )


@router.get("/outline/{outline_id}")
def get_outline(outline_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            row = get_by_public_id(session, outline_id, user_id=DEV_USER_ID)
            if row is None:
                return envelope_err(
                    ErrorCode.TASK_NOT_FOUND.defn.code,
                    "outline_not_found",
                    "大纲不存在或无权访问",
                    request_id,
                )
            data = outline_to_dict(row)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(data, request_id)


@router.put("/outline/{outline_id}")
def put_outline(
    outline_id: str,
    body: PutOutlineBody,
    request: Request,
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    expected: int | None = body.version
    if if_match is not None and if_match.strip():
        try:
            expected = int(if_match.strip().strip('"'))
        except ValueError:
            err = ErrorCode.PARAM_INVALID.defn
            return envelope_err(err.code, err.message, "If-Match 无效", request_id)
    if expected is None:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "缺少 version / If-Match", request_id)

    try:
        pages = normalize_pages(body.pages)
        for p in pages:
            moderate_text(p.get("title") or "")
            for b in p.get("bullets") or []:
                moderate_text(str(b))
        template_id = None
        if body.templateId:
            template_id = validate_template_id(body.templateId)
    except OutlineSchemaError as e:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, str(e) or err.user_msg, request_id)
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        with session_scope() as session:
            row = get_by_public_id(session, outline_id, user_id=DEV_USER_ID)
            if row is None:
                return envelope_err(
                    ErrorCode.TASK_NOT_FOUND.defn.code,
                    "outline_not_found",
                    "大纲不存在或无权访问",
                    request_id,
                )
            update_pages(
                session,
                row,
                pages=pages,
                expected_version=expected,
                template_id=template_id,
            )
            data = outline_to_dict(row)
            data["costQuota"] = 0
    except VersionConflict:
        err = ErrorCode.OUTLINE_VERSION_MISMATCH.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    return envelope_ok(data, request_id, user_msg="大纲已保存")


@router.post("/generate")
def generate_ppt(
    body: GenerateBody,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    if not idempotency_key:
        err = ErrorCode.IDEMPOTENCY_REQUIRED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    settings = get_settings()
    timeout_sec = TASK_TIMEOUTS.get("ppt_generate", DEFAULT_TASK_TIMEOUT_SECONDS)
    timeout_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=timeout_sec)
    public_id = uuid.uuid4().hex[:26]
    fp = hashlib.sha256(
        f"ppt:{body.outlineId}:{body.outlineVersion}".encode()
    ).hexdigest()

    try:
        pages = normalize_pages(body.pages)
        template_id = validate_template_id(body.templateId)
        for p in pages:
            moderate_text(p.get("title") or "")
            for b in p.get("bullets") or []:
                moderate_text(str(b))
    except OutlineSchemaError as e:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, str(e) or err.user_msg, request_id)
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        with session_scope() as session:
            existing = get_task_by_idem(
                session, user_id=DEV_USER_ID, key=idempotency_key
            )
            if existing is not None:
                old_fp = (existing.input_meta or {}).get("fingerprint")
                if old_fp and old_fp != fp:
                    err = ErrorCode.IDEMPOTENCY_CONFLICT.defn
                    return envelope_err(err.code, err.message, err.user_msg, request_id)
                response.headers["Idempotent-Replayed"] = "true"
                item = task_to_list_item(existing)
                return envelope_ok(
                    {
                        **item,
                        "taskId": existing.public_id,
                        "costQuota": PPT_COST,
                    },
                    request_id,
                    user_msg="PPT 生成任务已提交",
                    task_id=existing.public_id,
                )

            row = get_by_public_id(session, body.outlineId, user_id=DEV_USER_ID)
            if row is None:
                return envelope_err(
                    ErrorCode.TASK_NOT_FOUND.defn.code,
                    "outline_not_found",
                    "大纲不存在或无权访问",
                    request_id,
                )
            if int(row.version) != int(body.outlineVersion):
                err = ErrorCode.OUTLINE_VERSION_MISMATCH.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)
            if row.template_id != template_id:
                err = ErrorCode.PARAM_INVALID.defn
                return envelope_err(
                    err.code, err.message, "模板与大纲不一致", request_id
                )

            assert_inflight_ok(
                session, DEV_USER_ID, limit=settings.max_inflight_tasks_per_user
            )
            reserve_for_user(session, DEV_USER_ID, PPT_COST)
            input_meta = {
                "outlineId": row.public_id,
                "outlineVersion": row.version,
                "templateId": template_id,
                "topic": row.topic,
                "pages": pages,
                "fingerprint": fp,
                "inputs": [],
                "params": {},
            }
            task, created_new = create_task_row(
                session,
                public_id=public_id,
                user_id=DEV_USER_ID,
                task_type=TaskType.PPT_GENERATE.value,
                idempotency_key=idempotency_key,
                timeout_at=timeout_at,
                input_meta=input_meta,
                cost_quota=PPT_COST,
            )
            task_public_id = task.public_id
            item = task_to_list_item(task)
            data = {
                **item,
                "taskId": task.public_id,
                "costQuota": PPT_COST,
            }
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
            _enqueue_ppt(task_public_id, request_id)
        except Exception:
            pass

    return envelope_ok(
        data, request_id, user_msg="PPT 生成任务已提交", task_id=task_public_id
    )
