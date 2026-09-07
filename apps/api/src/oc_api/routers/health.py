from fastapi import APIRouter, Request, Response
from oc_core.alerts import render_prometheus
from oc_shared.schemas import envelope_ok

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz(request: Request):
    request_id = getattr(request.state, "request_id", "unknown")
    return envelope_ok({"status": "ok", "service": "api"}, request_id)


@router.get("/metrics")
def metrics():
    """Prometheus text exposition for basic cleanup/alert gauges."""
    return Response(content=render_prometheus(), media_type="text/plain; version=0.0.4")
