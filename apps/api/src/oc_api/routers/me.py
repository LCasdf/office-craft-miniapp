from fastapi import APIRouter, Request

from oc_shared.schemas import envelope_ok

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
    return envelope_ok(
        {
            "dailyQuotaLimit": 20,
            "dailyUsed": 0,
            "dailyUsedDate": None,
            "dailyRemaining": 20,
            "frozenQuota": 0,
            "vipBalance": 0,
            "vipExpireAt": None,
            "totalUsed": 0,
            "available": 20,
        },
        request_id,
    )
