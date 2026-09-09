"""AI character-card routes — generate / get / put / render."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, Request, Response
from oc_core.ai.character_card_schema import SchemaError, validate_and_normalize
from oc_core.ai.client import build_ai_client, parse_character_card_content
from oc_core.ai.prompts import CHARACTER_CARD_PROMPT_VERSION, character_card_messages
from oc_core.character_cards import (
    VersionConflict,
    card_to_dict,
    create_card,
    delete_card_for_user,
    get_by_idempotency,
    get_by_public_id,
    list_for_user as list_cards_for_user,
    update_payload,
)
from oc_core.ai.image_gen import build_image_client, build_image_prompt
from oc_core.config import get_settings
from oc_core.db import session_scope
from oc_core.moderation import ContentBlocked, moderate_payload, moderate_text
from oc_core.quota import QuotaError, assert_inflight_ok, reserve_for_user
from oc_core.storage import put_bytes, presign_get
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

router = APIRouter(prefix="/ai/character-card", tags=["ai"])

CARD_COST = TASK_COST_QUOTA.get("character_card", 3)


class GenerateBody(BaseModel):
    premise: str = Field(..., min_length=1)
    name: str | None = None

    model_config = {"populate_by_name": True}


class ImagineBody(BaseModel):
    """文字描述 → 角色立绘图片。"""

    prompt: str = Field(default="", description="综合描述；可与字段拼装")
    name: str | None = None
    title: str | None = None
    avatarDesc: str | None = None
    personality: str | None = None
    story: str | None = None

    model_config = {"populate_by_name": True}


class PutBody(BaseModel):
    version: int | None = None
    payload: dict

    model_config = {"populate_by_name": True}


def _fingerprint_premise(premise: str, name: str | None) -> str:
    payload = {"premise": premise.strip(), "name": (name or "").strip()}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _enqueue_render(task_id: str, request_id: str) -> None:
    from oc_worker.tasks.ai.character_card import character_card_task

    character_card_task.apply_async(
        kwargs={"task_id": task_id, "request_id": request_id},
        queue="q.ai",
    )


def _cover_url(cos_key: str | None) -> str | None:
    if not cos_key:
        return None
    try:
        return presign_get(str(cos_key))
    except Exception:
        return None


@router.get("")
def list_cards(request: Request, limit: int = 50):
    """角色卡集 — not shown in task center."""
    request_id = getattr(request.state, "request_id", "unknown")
    limit = max(1, min(limit, 100))
    try:
        with session_scope() as session:
            cards = list_cards_for_user(session, DEV_USER_ID, limit=limit)
            items = [
                card_to_dict(c, cover_url=_cover_url(c.cover_cos_key)) for c in cards
            ]
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok({"items": items, "hasMore": False}, request_id)


@router.post("/imagine")
def imagine_character(body: ImagineBody, request: Request):
    """文生图：根据文字描述生成角色立绘 PNG（当前为 Mock 风格化立绘）。"""
    request_id = getattr(request.state, "request_id", "unknown")
    fields = {
        "prompt": (body.prompt or "").strip(),
        "name": (body.name or "").strip(),
        "title": (body.title or "").strip(),
        "avatarDesc": (body.avatarDesc or "").strip(),
        "personality": (body.personality or "").strip(),
        "story": (body.story or "").strip(),
    }
    prompt = build_image_prompt(fields)
    if not prompt:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "请填写角色描述", request_id)
    if len(prompt) > AI_TEXT_MAX_CHARS:
        err = ErrorCode.INPUT_TOO_LONG.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        moderate_text(prompt)
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    settings = get_settings()
    try:
        client = build_image_client(getattr(settings, "ai_provider", "mock"))
        png = client.imagine_character(
            prompt=prompt,
            name=fields["name"] or "未命名角色",
            title=fields["title"],
        )
        env = settings.cos_env_prefix or settings.app_env
        key = f"{env}/{DEV_USER_ID}/rolecards/{uuid.uuid4().hex}.png"
        put_bytes(key, png, content_type="image/png")
        url = presign_get(key)
        data = {
            "imageUrl": url,
            "cosKey": key,
            "filename": "character.png",
            "sizeBytes": len(png),
            "prompt": prompt[:200],
            "provider": "mock",
        }
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.AI_UPSTREAM_FAILED.defn
        return envelope_err(err.code, err.message, "角色图片生成失败，请稍后重试", request_id)

    return envelope_ok(data, request_id, user_msg="角色图片已生成")


@router.post("/generate")
def generate(
    body: GenerateBody,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    if not idempotency_key:
        err = ErrorCode.IDEMPOTENCY_REQUIRED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    premise = (body.premise or "").strip()
    if not premise:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "请填写角色设定", request_id)
    if len(premise) > AI_TEXT_MAX_CHARS:
        err = ErrorCode.INPUT_TOO_LONG.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        moderate_text(premise)
        if body.name:
            moderate_text(body.name)
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    fp = _fingerprint_premise(premise, body.name)
    settings = get_settings()

    try:
        with session_scope() as session:
            existing = get_by_idempotency(
                session, user_id=DEV_USER_ID, key=idempotency_key
            )
            if existing is not None:
                # Replay: same key must same premise fingerprint (stored in payload._meta)
                meta = (existing.payload_json or {}).get("_meta") or {}
                if meta.get("fingerprint") and meta["fingerprint"] != fp:
                    err = ErrorCode.IDEMPOTENCY_CONFLICT.defn
                    return envelope_err(err.code, err.message, err.user_msg, request_id)
                response.headers["Idempotent-Replayed"] = "true"
                data = card_to_dict(existing)
                data["costQuota"] = 0
                return envelope_ok(
                    data,
                    request_id,
                    user_msg="角色卡草稿已生成，请确认后保存",
                )

            client = build_ai_client(settings.ai_provider)
            result = client.complete(
                messages=character_card_messages(premise),
                extra={"purpose": "character_card"},
            )
            payload = parse_character_card_content(result.content)
            if body.name and body.name.strip():
                payload["name"] = body.name.strip()[:32]
            payload["_meta"] = {"fingerprint": fp, "premise": premise[:200]}
            moderate_payload(payload)

            card = create_card(
                session,
                public_id=uuid.uuid4().hex[:26],
                user_id=DEV_USER_ID,
                title=payload["name"],
                payload=payload,
                idempotency_key=idempotency_key,
                prompt_version=CHARACTER_CARD_PROMPT_VERSION,
            )
            data = card_to_dict(card)
            data["costQuota"] = 0
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except (SchemaError, json.JSONDecodeError, ValueError):
        err = ErrorCode.AI_UPSTREAM_FAILED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    return envelope_ok(
        data, request_id, user_msg="角色卡草稿已生成，请确认后保存"
    )


@router.get("/{card_id}")
def get_card(card_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            card = get_by_public_id(session, card_id, user_id=DEV_USER_ID)
            if card is None:
                err = ErrorCode.TASK_NOT_FOUND.defn
                return envelope_err(
                    err.code, "card_not_found", "角色卡不存在或无权访问", request_id
                )
            data = card_to_dict(card, cover_url=_cover_url(card.cover_cos_key))
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(data, request_id)


@router.put("/{card_id}")
def put_card(
    card_id: str,
    body: PutBody,
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
        payload = validate_and_normalize(body.payload)
        moderate_payload(payload)
    except SchemaError:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "角色卡字段不合法", request_id)
    except ContentBlocked:
        err = ErrorCode.CONTENT_BLOCKED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    try:
        with session_scope() as session:
            card = get_by_public_id(session, card_id, user_id=DEV_USER_ID)
            if card is None:
                return envelope_err(
                    ErrorCode.TASK_NOT_FOUND.defn.code,
                    "card_not_found",
                    "角色卡不存在或无权访问",
                    request_id,
                )
            # Preserve generate meta fingerprint
            old_meta = (card.payload_json or {}).get("_meta")
            if old_meta:
                payload["_meta"] = old_meta
            update_payload(
                session,
                card,
                payload=payload,
                expected_version=expected,
                title=payload.get("name"),
            )
            data = card_to_dict(card)
    except VersionConflict:
        err = ErrorCode.PROJECT_VERSION_MISMATCH.defn
        return envelope_err(
            err.code,
            err.message,
            "角色卡已更新，请刷新后重试",
            request_id,
        )
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    return envelope_ok(data, request_id, user_msg="已保存")


@router.delete("/{card_id}")
def delete_card(card_id: str, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            ok = delete_card_for_user(session, card_id, user_id=DEV_USER_ID)
            if not ok:
                return envelope_err(
                    ErrorCode.TASK_NOT_FOUND.defn.code,
                    "card_not_found",
                    "角色卡不存在或无权访问",
                    request_id,
                )
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(
        {"cardId": card_id, "deleted": True},
        request_id,
        user_msg="已从角色卡集移除",
    )


@router.post("/{card_id}/render")
def render_card(
    card_id: str,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    request_id = getattr(request.state, "request_id", "unknown")
    if not idempotency_key:
        err = ErrorCode.IDEMPOTENCY_REQUIRED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    settings = get_settings()
    timeout_sec = TASK_TIMEOUTS.get("character_card", DEFAULT_TASK_TIMEOUT_SECONDS)
    timeout_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=timeout_sec)
    public_id = uuid.uuid4().hex[:26]
    fp = hashlib.sha256(f"render:{card_id}".encode()).hexdigest()

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
                return envelope_ok(
                    {
                        "cardId": card_id,
                        "renderTaskId": existing.public_id,
                        "costQuota": CARD_COST,
                        "task": task_to_list_item(existing),
                    },
                    request_id,
                    user_msg="出图任务已提交",
                    task_id=existing.public_id,
                )

            card = get_by_public_id(session, card_id, user_id=DEV_USER_ID)
            if card is None:
                return envelope_err(
                    ErrorCode.TASK_NOT_FOUND.defn.code,
                    "card_not_found",
                    "角色卡不存在或无权访问",
                    request_id,
                )
            try:
                moderate_payload(card.payload_json or {})
            except ContentBlocked:
                err = ErrorCode.CONTENT_BLOCKED.defn
                return envelope_err(err.code, err.message, err.user_msg, request_id)

            assert_inflight_ok(
                session, DEV_USER_ID, limit=settings.max_inflight_tasks_per_user
            )
            reserve_for_user(session, DEV_USER_ID, CARD_COST)
            input_meta = {
                "cardId": card.public_id,
                "cardVersion": card.version,
                "fingerprint": fp,
                "inputs": [],
                "params": {},
            }
            task, created_new = create_task_row(
                session,
                public_id=public_id,
                user_id=DEV_USER_ID,
                task_type=TaskType.CHARACTER_CARD.value,
                idempotency_key=idempotency_key,
                timeout_at=timeout_at,
                input_meta=input_meta,
                cost_quota=CARD_COST,
            )
            task_public_id = task.public_id
            data = {
                "cardId": card.public_id,
                "renderTaskId": task.public_id,
                "costQuota": CARD_COST,
                "task": task_to_list_item(task),
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
            _enqueue_render(task_public_id, request_id)
        except Exception:
            pass

    return envelope_ok(
        data, request_id, user_msg="出图任务已提交", task_id=task_public_id
    )
