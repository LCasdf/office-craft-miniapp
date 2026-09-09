"""G1: storage / cleanup / user-error refund / queue overload — mostly mocked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from oc_api.main import create_app
from oc_core.cleanup import (
    cleanup_expired_inputs,
    cleanup_expired_outputs,
    cleanup_orphan_uploads,
    collect_bound_upload_ids,
    delete_task_input_objects,
    run_all_cleanups,
)
from oc_core.models import Quota, Task
from oc_core.quota import SETTLED_FROZEN, settle_terminal_task
from oc_core.storage import (
    bucket_name,
    delete_object,
    delete_prefix,
    list_objects,
    result_object_key,
    upload_path_prefix,
)
from oc_core.tasks_repo import apply_failed
from oc_shared.enums import ErrorClass, TaskStatus
from oc_shared.error_codes import ErrorCode


def test_storage_key_helpers():
    assert upload_path_prefix(env="local", user_id="0", upload_id="upl_1").endswith(
        "uploads/upl_1/"
    )
    assert "results/tid/result.pdf" in result_object_key(
        env="local", user_id="0", task_id="tid"
    )
    assert bucket_name()


def test_storage_delete_and_list(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("oc_core.storage.get_s3_client", lambda: client)
    monkeypatch.setattr("oc_core.storage.ensure_bucket", lambda: None)
    client.delete_object.return_value = {}
    assert delete_object("k") is True
    from botocore.exceptions import ClientError

    client.delete_object.side_effect = ClientError({"Error": {"Code": "x"}}, "Delete")
    assert delete_object("k") is False

    client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "local/0/uploads/u/a.pdf",
                "LastModified": datetime.now(UTC),
                "Size": 3,
            }
        ],
        "IsTruncated": False,
    }
    objs = list_objects("local/")
    assert len(objs) == 1
    assert objs[0]["key"].endswith("a.pdf")

    client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "local/0/uploads/u/a.pdf",
                "LastModified": datetime.now(UTC),
                "Size": 1,
            }
        ],
        "IsTruncated": False,
    }
    monkeypatch.setattr("oc_core.storage.delete_object", lambda k: True)
    assert delete_prefix("local/0/uploads/u/") == 1


def test_cleanup_orphan_and_expired(monkeypatch):
    now = datetime.now(UTC)
    session = MagicMock()
    session.scalars.return_value = []

    monkeypatch.setattr(
        "oc_core.cleanup.list_objects",
        lambda prefix, max_keys=5000: [
            {
                "key": "local/0/uploads/upl_old/0.pdf",
                "last_modified": now - timedelta(hours=8),
                "size": 1,
            }
        ],
    )
    monkeypatch.setattr("oc_core.cleanup.collect_bound_upload_ids", lambda s, **k: set())
    monkeypatch.setattr("oc_core.cleanup.delete_prefix", lambda p: 2)
    stats = cleanup_orphan_uploads(session, env="local", ttl_seconds=3600, now=now)
    assert stats["orphan_prefixes"] == 1
    assert stats["orphan_objects"] == 2

    task = Task(
        public_id="out1",
        user_id=0,
        type="pdf_compress",
        status=TaskStatus.SUCCEEDED.value,
        result_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
        output_meta={"cosKey": "local/0/results/x/result.pdf"},
    )
    session.scalars.return_value = [task]
    monkeypatch.setattr("oc_core.cleanup.delete_object", lambda k: True)
    assert cleanup_expired_outputs(session)["expired_outputs"] == 1
    assert task.output_meta.get("cosKey") is None

    task2 = Task(
        public_id="in1",
        user_id=0,
        type="pdf_merge",
        status=TaskStatus.FAILED.value,
        finished_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=10),
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=10),
        input_meta={"inputs": [{"cosKey": "k1"}]},
    )
    session.scalars.return_value = [task2]
    assert cleanup_expired_inputs(session, ttl_seconds=3600)["expired_inputs"] == 1
    assert task2.input_meta.get("inputsCleaned") is True

    assert delete_task_input_objects({"inputs": [{"cosKey": "a"}, {"cos_key": "b"}]}) == 2
    assert delete_task_input_objects(None) == 0

    monkeypatch.setattr(
        "oc_core.cleanup.cleanup_orphan_uploads", lambda s: {"orphan_objects": 0}
    )
    monkeypatch.setattr(
        "oc_core.cleanup.cleanup_expired_outputs", lambda s: {"expired_outputs": 0}
    )
    monkeypatch.setattr(
        "oc_core.cleanup.cleanup_expired_inputs", lambda s: {"expired_inputs": 1}
    )
    assert run_all_cleanups(session)["expired_inputs"] == 1


def test_collect_bound_upload_ids():
    session = MagicMock()
    t = Task(
        public_id="t",
        user_id=0,
        type="pdf_compress",
        status="queued",
        created_at=datetime.now(UTC).replace(tzinfo=None),
        input_meta={"uploadId": "upl_x"},
    )
    session.scalars.return_value = [t]
    assert "upl_x" in collect_bound_upload_ids(session)


def test_user_error_failed_refunds_quota():
    q = Quota(
        user_id=0,
        daily_quota_limit=20,
        daily_used=0,
        daily_used_date=datetime.now(UTC).date(),
        total_used=0,
        frozen_quota=2,
        vip_balance=0,
    )
    task = Task(
        public_id="fail1",
        user_id=0,
        type="pdf_merge",
        status=TaskStatus.RUNNING.value,
        progress=20,
        cost_quota=2,
        quota_settled=SETTLED_FROZEN,
    )
    apply_failed(
        task,
        error_code=ErrorCode.PDF_ENCRYPTED.defn.code,
        error_class=ErrorClass.USER.value,
        user_msg=ErrorCode.PDF_ENCRYPTED.defn.user_msg,
    )
    assert settle_terminal_task(q, task) == "refunded"
    assert q.frozen_quota == 0
    assert task.quota_settled == 2


def test_queue_overloaded_rejects_create(monkeypatch):
    monkeypatch.setattr("oc_api.routers.tasks._queue_overloaded", lambda: True)
    client = TestClient(create_app())
    body = client.post(
        "/v1/tasks",
        json={"type": "character_card", "inputs": []},
        headers={"Idempotency-Key": "k-overload"},
    ).json()
    assert body["code"] == 40018
