from fastapi import APIRouter, Request

from oc_shared.schemas import envelope_ok

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    return envelope_ok({"status": "ok", "service": "api"}, request_id)
