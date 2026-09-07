"""Auth stubs — full WeChat login in later milestone."""

from fastapi import APIRouter, Request
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import RefreshRequest, WxLoginRequest, envelope_err, envelope_ok

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/wx-login")
def wx_login(body: WxLoginRequest, request: Request):
    """M0 stub: accepts any non-empty code, returns mock tokens."""
    request_id = getattr(request.state, "request_id", "unknown")
    if not body.code.strip():
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    return envelope_ok(
        {
            "accessToken": "dev_access_token",
            "expiresIn": 7200,
            "refreshToken": "dev_refresh_token",
            "refreshExpiresIn": 2592000,
            "user": {"id": "0", "nickname": None, "avatarUrl": None},
        },
        request_id,
        user_msg="ok",
    )


@router.post("/refresh")
def refresh(body: RefreshRequest, request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    if not body.refresh_token.strip():
        err = ErrorCode.UNAUTHORIZED.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    return envelope_ok(
        {
            "accessToken": "dev_access_token_refreshed",
            "expiresIn": 7200,
            "refreshToken": body.refresh_token,
            "refreshExpiresIn": 2592000,
        },
        request_id,
    )
