from datetime import datetime, timedelta
from unittest.mock import MagicMock

from oc_core.models import Task
from oc_core.tasks_repo import (
    MAX_USER_RETRIES,
    apply_succeeded,
    is_retryable,
    prepare_retry,
    sweep_timed_out_tasks,
    task_to_list_item,
)
from oc_shared.enums import ErrorClass, TaskStatus
from oc_shared.error_codes import ErrorCode


def test_apply_succeeded_sets_terminal_fields():
    task = Task(
        public_id="abc",
        user_id=0,
        type="pdf_compress",
        status=TaskStatus.QUEUED.value,
        progress=10,
    )
    apply_succeeded(task, output_meta={"note": "pong"})
    assert task.status == TaskStatus.SUCCEEDED.value
    assert task.progress == 100
    assert task.finished_at is not None
    assert task.result_expires_at is not None
    assert task.output_meta == {"note": "pong"}


def test_task_to_list_item_shape():
    task = Task(
        public_id="pid123",
        user_id=0,
        type="pdf_compress",
        status=TaskStatus.QUEUED.value,
        progress=10,
        cost_quota=0,
        retry_count=0,
        timeout_at=datetime(2026, 1, 1, 12, 0, 0),
        created_at=datetime(2026, 1, 1, 11, 0, 0),
        input_meta={
            "inputs": [
                {"filename": "a.pdf", "sizeBytes": 1536},
                {"filename": "b.pdf", "sizeBytes": 512},
            ]
        },
    )
    item = task_to_list_item(task)
    assert item["taskId"] == "pid123"
    assert item["status"] == "queued"
    assert item["timeoutAt"] == "2026-01-01T12:00:00"
    assert item["filename"] == "a.pdf"
    assert item["sizeBytes"] == 2048
    assert item["sizeLabel"] == "2.0 KB"


def test_delete_for_user():
    from oc_core.tasks_repo import delete_for_user

    session = MagicMock()
    task = Task(public_id="del1", user_id=0, type="pdf_compress", status="failed")
    session.scalar.return_value = task
    assert delete_for_user(session, "del1", user_id=0) is True
    session.delete.assert_called_once_with(task)
    session.scalar.return_value = None
    assert delete_for_user(session, "missing", user_id=0) is False


def test_is_retryable_rules():
    base = dict(public_id="r1", user_id=0, type="pdf_compress")
    ok = Task(
        **base,
        status=TaskStatus.FAILED.value,
        error_class=ErrorClass.SYSTEM.value,
        retry_count=0,
    )
    assert is_retryable(ok) is True

    assert is_retryable(Task(**base, status=TaskStatus.SUCCEEDED.value, retry_count=0)) is False
    assert (
        is_retryable(
            Task(
                **base,
                status=TaskStatus.FAILED.value,
                error_class=ErrorClass.SAFETY.value,
                retry_count=0,
            )
        )
        is False
    )
    assert (
        is_retryable(
            Task(
                **base,
                status=TaskStatus.FAILED.value,
                error_class=ErrorClass.USER.value,
                retry_count=MAX_USER_RETRIES,
            )
        )
        is False
    )


def test_prepare_retry_resets_fields():
    task = Task(
        public_id="r2",
        user_id=0,
        type="pdf_compress",
        status=TaskStatus.FAILED.value,
        progress=40,
        retry_count=0,
        error_code=50001,
        error_class=ErrorClass.SYSTEM.value,
        output_meta={"userMsg": "boom", "cosKey": "x"},
        quota_settled=2,
    )
    timeout_at = datetime(2026, 9, 8, 12, 0, 0)
    prepare_retry(task, timeout_at=timeout_at)
    assert task.status == TaskStatus.QUEUED.value
    assert task.progress == 10
    assert task.retry_count == 1
    assert task.timeout_at == timeout_at
    assert task.error_code is None
    assert task.output_meta is None
    assert task.quota_settled == 0


def test_sweep_timed_out_tasks():
    now = datetime(2026, 9, 8, 12, 0, 0)
    overdue = Task(
        id=1,
        public_id="to1",
        user_id=0,
        type="pdf_compress",
        status=TaskStatus.RUNNING.value,
        progress=50,
        timeout_at=now - timedelta(seconds=1),
        quota_settled=0,
    )
    session = MagicMock()
    result = MagicMock()
    result.__iter__ = lambda self: iter([overdue])
    session.scalars.return_value = result

    import oc_core.tasks_repo as repo

    orig = repo._now
    repo._now = lambda: now
    try:
        n = sweep_timed_out_tasks(session)
    finally:
        repo._now = orig

    assert n == 1
    assert overdue.status == TaskStatus.FAILED.value
    assert overdue.error_code == ErrorCode.TASK_TIMEOUT.defn.code
    assert overdue.error_class == ErrorClass.TIMEOUT.value
