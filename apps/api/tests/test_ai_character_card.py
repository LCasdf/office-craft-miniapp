"""API: character-card generate / put conflict / render quota."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from oc_api.main import create_app
from oc_core.db import get_engine, session_scope
from oc_core.quota import cancel_task, get_or_create_quota
from oc_core.tasks_repo import DEV_USER_ID, list_for_user
from sqlalchemy import text


def _db_ready() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT 1 FROM character_cards LIMIT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="MySQL/character_cards not ready")

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_inflight():
    with session_scope() as session:
        get_or_create_quota(session, DEV_USER_ID)
        for t in list_for_user(session, DEV_USER_ID, limit=100):
            cancel_task(session, t)
    yield


def test_generate_free_then_put_conflict_then_render():
    key = str(uuid.uuid4())
    r = client.post(
        "/v1/ai/character-card/generate",
        json={"premise": "一位在江南雨巷卖纸鸢的少年"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0, body
    assert body["data"]["costQuota"] == 0
    card_id = body["data"]["cardId"]
    version = body["data"]["version"]
    payload = body["data"]["payload"]

    # conflict: stale version
    bad = client.put(
        f"/v1/ai/character-card/{card_id}",
        json={"version": version + 99, "payload": payload},
        headers={"If-Match": str(version + 99)},
    )
    assert bad.json()["code"] == 40015

    ok = client.put(
        f"/v1/ai/character-card/{card_id}",
        json={
            "version": version,
            "payload": {**payload, "name": "纸鸢少年"},
        },
        headers={"If-Match": str(version)},
    )
    assert ok.json()["code"] == 0
    assert ok.json()["data"]["version"] == version + 1
    assert ok.json()["data"]["payload"]["name"] == "纸鸢少年"

    q0 = client.get("/v1/me/quota").json()["data"]["available"]
    render = client.post(
        f"/v1/ai/character-card/{card_id}/render",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert render.json()["code"] == 0, render.json()
    assert render.json()["data"]["costQuota"] == 3
    assert render.json()["data"]["renderTaskId"]
    q1 = client.get("/v1/me/quota").json()["data"]["available"]
    assert q1 == q0 - 3


def test_generate_blocked_no_charge():
    q0 = client.get("/v1/me/quota").json()["data"]["available"]
    r = client.post(
        "/v1/ai/character-card/generate",
        json={"premise": "内容含违禁词请拦截"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.json()["code"] == 42001
    assert "安全审核" in (r.json().get("user_msg") or "")
    q1 = client.get("/v1/me/quota").json()["data"]["available"]
    assert q1 == q0


def test_imagine_ok_and_blocked():
    ok = client.post(
        "/v1/ai/character-card/imagine",
        json={"prompt": "银发法师，月下图书馆", "name": "埃兰", "title": "馆主"},
    )
    body = ok.json()
    assert body["code"] == 0, body
    assert body["data"]["imageUrl"]
    assert body["data"]["sizeBytes"] > 1000

    q0 = client.get("/v1/me/quota").json()["data"]["available"]
    blocked = client.post(
        "/v1/ai/character-card/imagine",
        json={"prompt": "内容含违禁词请拦截"},
    )
    assert blocked.json()["code"] == 42001
    assert "安全审核" in (blocked.json().get("user_msg") or "")
    q1 = client.get("/v1/me/quota").json()["data"]["available"]
    assert q1 == q0


def test_render_blocked_no_charge():
    """安全拒绝发生在预扣之前 → 额度不变（G2a）。"""
    from oc_core.character_cards import get_by_public_id
    from sqlalchemy.orm.attributes import flag_modified

    key = str(uuid.uuid4())
    r = client.post(
        "/v1/ai/character-card/generate",
        json={"premise": "一位在江南雨巷卖纸鸢的少年"},
        headers={"Idempotency-Key": key},
    )
    assert r.json()["code"] == 0, r.json()
    card_id = r.json()["data"]["cardId"]

    with session_scope() as session:
        card = get_by_public_id(session, card_id, user_id=DEV_USER_ID)
        assert card is not None
        payload = dict(card.payload_json or {})
        payload["story"] = "此处插入违禁词以触发出图审核"
        card.payload_json = payload
        flag_modified(card, "payload_json")

    q0 = client.get("/v1/me/quota").json()["data"]["available"]
    render = client.post(
        f"/v1/ai/character-card/{card_id}/render",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert render.json()["code"] == 42001
    assert "安全审核" in (render.json().get("user_msg") or "")
    q1 = client.get("/v1/me/quota").json()["data"]["available"]
    assert q1 == q0
