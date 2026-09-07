"""Optional MySQL-backed smoke — skipped when DB unreachable (local unit CI still green)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from oc_api.main import create_app
from oc_core.db import get_engine, session_scope
from oc_core.tasks_repo import apply_failed, apply_succeeded, create_task_row, get_by_public_id
from oc_shared.enums import TaskStatus
from sqlalchemy import text


def _db_ready() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_ready(), reason="MySQL not reachable")


def test_create_task_persists_and_idempotent():
    client = TestClient(create_app())
    key = str(uuid.uuid4())
    r1 = client.post(
        "/v1/tasks",
        json={"type": "character_card", "inputs": [], "uploadId": "upl_test"},
        headers={"Idempotency-Key": key},
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["code"] == 0
    tid = body1["data"]["taskId"]
    assert body1["data"]["status"] == "queued"

    r2 = client.post(
        "/v1/tasks",
        json={"type": "character_card", "inputs": [], "uploadId": "upl_test"},
        headers={"Idempotency-Key": key},
    )
    assert r2.json()["data"]["taskId"] == tid

    r3 = client.get(f"/v1/tasks/{tid}")
    assert r3.json()["data"]["taskId"] == tid

    r4 = client.get("/v1/tasks")
    ids = [i["taskId"] for i in r4.json()["data"]["items"]]
    assert tid in ids


def test_mark_succeeded_writeback_visible():
    public_id = uuid.uuid4().hex[:26]
    with session_scope() as session:
        create_task_row(
            session,
            public_id=public_id,
            user_id=0,
            task_type="pdf_compress",
            idempotency_key=str(uuid.uuid4()),
            timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
        )
        task = get_by_public_id(session, public_id)
        assert task is not None
        apply_succeeded(task)

    client = TestClient(create_app())
    body = client.get(f"/v1/tasks/{public_id}").json()
    assert body["data"]["status"] == TaskStatus.SUCCEEDED.value
    assert body["data"]["progress"] == 100


def test_download_expired_returns_40016():
    public_id = uuid.uuid4().hex[:26]
    with session_scope() as session:
        create_task_row(
            session,
            public_id=public_id,
            user_id=0,
            task_type="pdf_compress",
            idempotency_key=str(uuid.uuid4()),
            timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
            cost_quota=0,
        )
        task = get_by_public_id(session, public_id)
        assert task is not None
        apply_succeeded(
            task,
            output_meta={"cosKey": "local/0/results/x/result.pdf", "filename": "r.pdf"},
        )
        task.result_expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)

    client = TestClient(create_app())
    body = client.get(f"/v1/tasks/{public_id}/download").json()
    assert body["code"] == 40016

    detail = client.get(f"/v1/tasks/{public_id}").json()
    assert detail["data"]["resultExpired"] is True
    assert detail["data"]["outputs"] == []


def test_retry_failed_task():
    public_id = uuid.uuid4().hex[:26]
    with session_scope() as session:
        create_task_row(
            session,
            public_id=public_id,
            user_id=0,
            task_type="pdf_compress",
            idempotency_key=str(uuid.uuid4()),
            timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
            cost_quota=0,
            input_meta={"inputs": [{"cosKey": "k", "filename": "a.pdf"}], "params": {}},
        )
        task = get_by_public_id(session, public_id)
        assert task is not None
        apply_failed(
            task,
            error_code=50001,
            error_class="system",
            error_detail="boom",
            user_msg="系统繁忙",
        )
        task.quota_settled = 2

    client = TestClient(create_app())
    key = str(uuid.uuid4())
    body = client.post(
        f"/v1/tasks/{public_id}/retry",
        headers={"Idempotency-Key": key},
    ).json()
    assert body["code"] == 0
    assert body["data"]["status"] == "queued"
    assert body["data"]["retryCount"] == 1

    body2 = client.post(
        f"/v1/tasks/{public_id}/retry",
        headers={"Idempotency-Key": key},
    ).json()
    assert body2["data"]["taskId"] == public_id
    assert body2["data"]["retryCount"] == 1


def test_retry_rejects_non_failed():
    public_id = uuid.uuid4().hex[:26]
    with session_scope() as session:
        create_task_row(
            session,
            public_id=public_id,
            user_id=0,
            task_type="pdf_compress",
            idempotency_key=str(uuid.uuid4()),
            timeout_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=60),
            cost_quota=0,
        )

    client = TestClient(create_app())
    body = client.post(
        f"/v1/tasks/{public_id}/retry",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    ).json()
    assert body["code"] == 40010
