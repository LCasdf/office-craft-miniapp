"""Quota / idempotency / inflight — skipped when MySQL unreachable."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from oc_api.main import create_app
from oc_core.db import get_engine, session_scope
from oc_core.quota import (
    cancel_task,
    count_inflight,
    get_or_create_quota,
    settle_unsettled_for_user,
)
from oc_core.tasks_repo import (
    DEV_USER_ID,
    apply_succeeded,
    create_task_row,
    get_by_public_id,
    list_for_user,
)
from sqlalchemy import text


def _db_ready() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="MySQL not reachable")

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_inflight():
    with session_scope() as session:
        get_or_create_quota(session, DEV_USER_ID)
        for t in list_for_user(session, DEV_USER_ID, limit=100):
            cancel_task(session, t)
    yield


def _headers():
    return {"Idempotency-Key": str(uuid.uuid4())}


def test_me_quota_returns_real_row():
    r = client.get("/v1/me/quota")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0
    assert "available" in body["data"]
    assert body["data"]["dailyQuotaLimit"] >= 1


def test_create_idempotent_replay_same_body():
    key = str(uuid.uuid4())
    payload = {
        "type": "character_card",
        "inputs": [],
        "uploadId": "upl_quota_idem",
    }
    r1 = client.post("/v1/tasks", json=payload, headers={"Idempotency-Key": key})
    assert r1.json()["code"] == 0, r1.json()
    tid = r1.json()["data"]["taskId"]

    r2 = client.post("/v1/tasks", json=payload, headers={"Idempotency-Key": key})
    assert r2.json()["code"] == 0
    assert r2.json()["data"]["taskId"] == tid
    assert r2.headers.get("Idempotent-Replayed") == "true"


def test_idempotency_conflict_different_body():
    key = str(uuid.uuid4())
    r1 = client.post(
        "/v1/tasks",
        json={"type": "character_card", "inputs": [], "uploadId": "a"},
        headers={"Idempotency-Key": key},
    )
    assert r1.json()["code"] == 0, r1.json()
    r2 = client.post(
        "/v1/tasks",
        json={"type": "character_card", "inputs": [], "uploadId": "b"},
        headers={"Idempotency-Key": key},
    )
    assert r2.json()["code"] == 40007


def test_inflight_limit():
    with session_scope() as session:
        assert count_inflight(session, DEV_USER_ID) == 0
        for _ in range(3):
            create_task_row(
                session,
                public_id=uuid.uuid4().hex[:26],
                user_id=DEV_USER_ID,
                task_type="character_card",
                idempotency_key=str(uuid.uuid4()),
                timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
                cost_quota=0,
            )
        assert count_inflight(session, DEV_USER_ID) == 3
    r = client.post(
        "/v1/tasks",
        json={"type": "character_card", "inputs": []},
        headers=_headers(),
    )
    assert r.json()["code"] == 40005


def test_cancel_refunds():
    public_id = uuid.uuid4().hex[:26]
    with session_scope() as session:
        q = get_or_create_quota(session, DEV_USER_ID)
        before_frozen = q.frozen_quota
        q.frozen_quota += 3
        create_task_row(
            session,
            public_id=public_id,
            user_id=DEV_USER_ID,
            task_type="character_card",
            idempotency_key=str(uuid.uuid4()),
            timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
            cost_quota=3,
        )
    r = client.post(f"/v1/tasks/{public_id}/cancel")
    assert r.json()["code"] == 0
    assert r.json()["data"]["status"] == "cancelled"
    with session_scope() as session:
        q = get_or_create_quota(session, DEV_USER_ID)
        task = get_by_public_id(session, public_id)
        assert task is not None
        assert task.quota_settled == 2
        assert q.frozen_quota == before_frozen


def test_list_settles_succeeded():
    public_id = uuid.uuid4().hex[:26]
    with session_scope() as session:
        q = get_or_create_quota(session, DEV_USER_ID)
        q.frozen_quota += 1
        create_task_row(
            session,
            public_id=public_id,
            user_id=DEV_USER_ID,
            task_type="pdf_compress",
            idempotency_key=str(uuid.uuid4()),
            timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
            cost_quota=1,
        )
        task = get_by_public_id(session, public_id)
        assert task is not None
        apply_succeeded(task, output_meta={"cosKey": "x", "filename": "r.pdf"})

    r = client.get("/v1/tasks")
    assert r.json()["code"] == 0
    with session_scope() as session:
        settle_unsettled_for_user(session, DEV_USER_ID)
        task = get_by_public_id(session, public_id)
        assert task is not None
        assert task.quota_settled == 1
