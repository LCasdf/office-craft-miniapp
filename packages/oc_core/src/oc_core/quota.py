"""Quota reserve / charge / refund — API-only (Worker must not call)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from oc_shared.constants import MAX_INFLIGHT_TASKS_PER_USER
from oc_shared.enums import ErrorClass, TaskStatus
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from oc_core.models import Quota, Task

# tasks.quota_settled tinyint
SETTLED_FROZEN = 0
SETTLED_CHARGED = 1
SETTLED_REFUNDED = 2

INFLIGHT_STATUSES = (
    TaskStatus.PENDING.value,
    TaskStatus.QUEUED.value,
    TaskStatus.RUNNING.value,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class QuotaError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code  # exhausted | inflight


def business_today() -> date:
    return datetime.now(_SHANGHAI).date()


def apply_lazy_reset(quota: Quota, *, today: date | None = None) -> None:
    today = today or business_today()
    if quota.daily_used_date < today:
        quota.daily_used = 0
        quota.daily_used_date = today


def compute_available(quota: Quota) -> int:
    daily_left = max(0, quota.daily_quota_limit - quota.daily_used)
    return daily_left + quota.vip_balance - quota.frozen_quota


def apply_reserve(quota: Quota, cost: int) -> None:
    """Freeze cost points. Caller must hold row lock."""
    if cost <= 0:
        return
    apply_lazy_reset(quota)
    if compute_available(quota) < cost:
        raise QuotaError("exhausted")
    quota.frozen_quota += cost


def apply_charge(quota: Quota, task: Task) -> bool:
    """Turn freeze into real spend. Idempotent if already settled."""
    if task.quota_settled != SETTLED_FROZEN:
        return False
    cost = int(task.cost_quota or 0)
    apply_lazy_reset(quota)
    if cost > 0:
        # ponytail: legacy tasks may lack matching freeze — settle flag only
        if quota.frozen_quota >= cost:
            quota.frozen_quota -= cost
            daily_left = max(0, quota.daily_quota_limit - quota.daily_used)
            from_daily = min(cost, daily_left)
            quota.daily_used += from_daily
            rest = cost - from_daily
            if rest:
                take_vip = min(rest, quota.vip_balance)
                quota.vip_balance -= take_vip
            quota.total_used += cost
    task.quota_settled = SETTLED_CHARGED
    return True


def apply_refund(quota: Quota, task: Task) -> bool:
    """Release freeze without spending. Idempotent if already settled."""
    if task.quota_settled != SETTLED_FROZEN:
        return False
    cost = int(task.cost_quota or 0)
    if cost > 0 and quota.frozen_quota > 0:
        quota.frozen_quota -= min(quota.frozen_quota, cost)
    task.quota_settled = SETTLED_REFUNDED
    return True


def settle_terminal_task(quota: Quota, task: Task) -> str | None:
    """
    Settle quota for a terminal task.
    Returns 'charged' | 'refunded' | None (skipped).
    """
    if task.quota_settled != SETTLED_FROZEN:
        return None
    status = task.status
    if status == TaskStatus.SUCCEEDED.value:
        apply_charge(quota, task)
        return "charged"
    if status == TaskStatus.FAILED.value and task.error_class == ErrorClass.SAFETY.value:
        apply_charge(quota, task)
        return "charged"
    if status in (
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    ):
        apply_refund(quota, task)
        return "refunded"
    return None


def get_or_create_quota(session: Session, user_id: int) -> Quota:
    q = session.scalar(
        select(Quota).where(Quota.user_id == user_id).with_for_update()
    )
    if q is not None:
        apply_lazy_reset(q)
        return q
    q = Quota(
        user_id=user_id,
        daily_quota_limit=20,
        daily_used=0,
        daily_used_date=business_today(),
        total_used=0,
        frozen_quota=0,
        vip_balance=0,
    )
    session.add(q)
    session.flush()
    apply_lazy_reset(q)
    return q


def count_inflight(session: Session, user_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.user_id == user_id, Task.status.in_(INFLIGHT_STATUSES))
        )
        or 0
    )


def assert_inflight_ok(session: Session, user_id: int, *, limit: int | None = None) -> None:
    lim = limit if limit is not None else MAX_INFLIGHT_TASKS_PER_USER
    if count_inflight(session, user_id) >= lim:
        raise QuotaError("inflight")


def reserve_for_user(session: Session, user_id: int, cost: int) -> Quota:
    q = get_or_create_quota(session, user_id)
    apply_reserve(q, cost)
    return q


def settle_task_for_user(session: Session, task: Task) -> str | None:
    if task.quota_settled != SETTLED_FROZEN:
        return None
    if task.status in INFLIGHT_STATUSES:
        return None
    q = get_or_create_quota(session, task.user_id)
    return settle_terminal_task(q, task)


def settle_unsettled_for_user(session: Session, user_id: int, *, limit: int = 50) -> int:
    """
    Lazy settle terminal tasks still frozen.
    ponytail: replaces outbox consumer until API event pipeline exists.
    """
    tasks = list(
        session.scalars(
            select(Task)
            .where(
                Task.user_id == user_id,
                Task.quota_settled == SETTLED_FROZEN,
                Task.status.in_(
                    (
                        TaskStatus.SUCCEEDED.value,
                        TaskStatus.FAILED.value,
                        TaskStatus.CANCELLED.value,
                    )
                ),
            )
            .order_by(Task.id.asc())
            .limit(limit)
        )
    )
    if not tasks:
        return 0
    q = get_or_create_quota(session, user_id)
    n = 0
    for t in tasks:
        if settle_terminal_task(q, t):
            n += 1
    return n


def quota_to_dict(quota: Quota) -> dict:
    apply_lazy_reset(quota)
    available = compute_available(quota)
    daily_remaining = max(0, quota.daily_quota_limit - quota.daily_used)
    return {
        "dailyQuotaLimit": quota.daily_quota_limit,
        "dailyUsed": quota.daily_used,
        "dailyUsedDate": quota.daily_used_date.isoformat() if quota.daily_used_date else None,
        "dailyRemaining": daily_remaining,
        "frozenQuota": quota.frozen_quota,
        "vipBalance": quota.vip_balance,
        "vipExpireAt": quota.vip_expire_at.isoformat() if quota.vip_expire_at else None,
        "totalUsed": quota.total_used,
        "available": available,
    }


def cancel_task(session: Session, task: Task) -> bool:
    """Mark cancelled if non-terminal; refund quota. Returns False if not cancellable."""
    if task.status not in INFLIGHT_STATUSES:
        return False
    now = datetime.now(_SHANGHAI).replace(tzinfo=None)
    task.status = TaskStatus.CANCELLED.value
    task.finished_at = now
    task.started_at = task.started_at or now
    q = get_or_create_quota(session, task.user_id)
    apply_refund(q, task)
    return True
