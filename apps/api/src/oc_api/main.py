from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from oc_api.logging_setup import configure_logging
from oc_api.routers import auth, health, me, tasks
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import envelope_err

configure_logging()
logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Office Craft API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:24]}"
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "unknown")
        err = ErrorCode.PARAM_INVALID.defn
        return JSONResponse(
            status_code=err.http_status,
            content=envelope_err(err.code, err.message, err.user_msg, request_id),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("unhandled_error", error=str(exc))
        err = ErrorCode.INTERNAL_ERROR.defn
        return JSONResponse(
            status_code=err.http_status,
            content=envelope_err(err.code, err.message, err.user_msg, request_id),
        )

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/v1")
    app.include_router(me.router, prefix="/v1")
    app.include_router(tasks.router, prefix="/v1")
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("oc_api.main:app", host="0.0.0.0", port=8000, reload=True)
