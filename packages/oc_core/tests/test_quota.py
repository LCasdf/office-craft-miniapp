from datetime import date

import pytest
from oc_core.models import Quota, Task
from oc_core.quota import (
    SETTLED_CHARGED,
    SETTLED_FROZEN,
    SETTLED_REFUNDED,
    apply_charge,
    apply_lazy_reset,
    apply_refund,
    apply_reserve,
    compute_available,
    settle_terminal_task,
)
from oc_shared.enums import ErrorClass, TaskStatus


def _quota(**kwargs) -> Quota:
    defaults = dict(
        user_id=0,
        daily_quota_limit=20,
        daily_used=0,
        daily_used_date=date(2026, 9, 7),
        total_used=0,
        frozen_quota=0,
        vip_balance=0,
    )
    defaults.update(kwargs)
    return Quota(**defaults)


def _task(**kwargs) -> Task:
    defaults = dict(
        public_id="t1",
        user_id=0,
        type="pdf_compress",
        status=TaskStatus.QUEUED.value,
        cost_quota=1,
        quota_settled=SETTLED_FROZEN,
    )
    defaults.update(kwargs)
    return Task(**defaults)


def test_lazy_reset_clears_daily_used():
    q = _quota(daily_used=5, daily_used_date=date(2026, 9, 1))
    apply_lazy_reset(q, today=date(2026, 9, 7))
    assert q.daily_used == 0
    assert q.daily_used_date == date(2026, 9, 7)


def test_reserve_and_available():
    q = _quota()
    apply_reserve(q, 3)
    assert q.frozen_quota == 3
    assert compute_available(q) == 17


def test_reserve_exhausted():
    q = _quota(daily_quota_limit=2, frozen_quota=0)
    with pytest.raises(Exception) as ei:
        apply_reserve(q, 3)
    assert ei.value.code == "exhausted"


def test_charge_after_success():
    q = _quota(frozen_quota=2)
    t = _task(cost_quota=2, status=TaskStatus.SUCCEEDED.value)
    assert settle_terminal_task(q, t) == "charged"
    assert t.quota_settled == SETTLED_CHARGED
    assert q.frozen_quota == 0
    assert q.daily_used == 2
    assert q.total_used == 2


def test_refund_on_user_fail():
    q = _quota(frozen_quota=1)
    t = _task(cost_quota=1, status=TaskStatus.FAILED.value, error_class=ErrorClass.USER.value)
    assert settle_terminal_task(q, t) == "refunded"
    assert t.quota_settled == SETTLED_REFUNDED
    assert q.frozen_quota == 0
    assert q.daily_used == 0


def test_safety_charges():
    q = _quota(frozen_quota=3)
    t = _task(
        cost_quota=3,
        status=TaskStatus.FAILED.value,
        error_class=ErrorClass.SAFETY.value,
    )
    assert settle_terminal_task(q, t) == "charged"
    assert t.quota_settled == SETTLED_CHARGED


def test_settle_idempotent():
    q = _quota(frozen_quota=1)
    t = _task(cost_quota=1, status=TaskStatus.SUCCEEDED.value)
    assert settle_terminal_task(q, t) == "charged"
    assert settle_terminal_task(q, t) is None
    assert apply_charge(q, t) is False
    assert apply_refund(q, t) is False
