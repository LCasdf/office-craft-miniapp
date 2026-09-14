"""API: PPT outline / version mismatch / generate quota."""

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
            conn.execute(text("SELECT 1 FROM ppt_outlines LIMIT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="MySQL/ppt_outlines not ready")

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_inflight():
    with session_scope() as session:
        get_or_create_quota(session, DEV_USER_ID)
        for t in list_for_user(session, DEV_USER_ID, limit=100):
            cancel_task(session, t)
    yield


def test_outline_put_version_then_generate():
    r = client.post(
        "/v1/ai/ppt/outline",
        json={
            "topic": "季度业务复盘",
            "pageCount": 6,
            "templateId": "tpl_basic_01",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0, body
    assert body["data"]["costQuota"] == 0
    assert len(body["data"]["pages"]) == 6
    oid = body["data"]["outlineId"]
    ver = body["data"]["outlineVersion"]
    pages = body["data"]["pages"]

    bad = client.put(
        f"/v1/ai/ppt/outline/{oid}",
        json={"version": ver + 9, "pages": pages},
        headers={"If-Match": str(ver + 9)},
    )
    assert bad.json()["code"] == 40012

    pages[1]["title"] = "目录（已改）"
    ok = client.put(
        f"/v1/ai/ppt/outline/{oid}",
        json={"version": ver, "pages": pages, "templateId": "tpl_basic_01"},
        headers={"If-Match": str(ver)},
    )
    assert ok.json()["code"] == 0, ok.json()
    assert ok.json()["data"]["outlineVersion"] == ver + 1
    ver2 = ok.json()["data"]["outlineVersion"]
    pages2 = ok.json()["data"]["pages"]

    # stale version on generate
    stale = client.post(
        "/v1/ai/ppt/generate",
        json={
            "outlineId": oid,
            "outlineVersion": ver,
            "templateId": "tpl_basic_01",
            "pages": pages2,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert stale.json()["code"] == 40012

    q0 = client.get("/v1/me/quota").json()["data"]["available"]
    gen = client.post(
        "/v1/ai/ppt/generate",
        json={
            "outlineId": oid,
            "outlineVersion": ver2,
            "templateId": "tpl_basic_01",
            "pages": pages2,
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert gen.json()["code"] == 0, gen.json()
    assert gen.json()["data"]["costQuota"] == 5
    assert gen.json()["data"]["taskId"]
    q1 = client.get("/v1/me/quota").json()["data"]["available"]
    assert q1 == q0 - 5


def test_outline_page_count_rejected():
    r = client.post(
        "/v1/ai/ppt/outline",
        json={"topic": "x", "pageCount": 3, "templateId": "tpl_basic_01"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    # pydantic ge=5 → 40001 via validation handler
    assert r.json()["code"] == 40001


def test_outline_blocked():
    q0 = client.get("/v1/me/quota").json()["data"]["available"]
    r = client.post(
        "/v1/ai/ppt/outline",
        json={
            "topic": "内容含违禁词请拦截",
            "pageCount": 5,
            "templateId": "tpl_basic_01",
        },
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.json()["code"] == 42001
    assert client.get("/v1/me/quota").json()["data"]["available"] == q0
