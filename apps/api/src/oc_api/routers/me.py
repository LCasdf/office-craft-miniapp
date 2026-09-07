from fastapi import APIRouter, Request
from oc_core.db import session_scope
from oc_core.quota import get_or_create_quota, quota_to_dict, settle_unsettled_for_user
from oc_core.tasks_repo import DEV_USER_ID
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import envelope_err, envelope_ok

router = APIRouter(tags=["me"])


@router.get("/me")
def get_me(request: Request):
    """M0 stub — no real auth yet."""
    request_id = getattr(request.state, "request_id", "unknown")
    return envelope_ok(
        {
            "id": "0",
            "nickname": None,
            "avatarUrl": None,
            "status": 1,
            "createdAt": None,
        },
        request_id,
    )


@router.get("/me/quota")
def get_quota(request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        with session_scope() as session:
            settle_unsettled_for_user(session, DEV_USER_ID)
            q = get_or_create_quota(session, DEV_USER_ID)
            data = quota_to_dict(q)
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(data, request_id)
