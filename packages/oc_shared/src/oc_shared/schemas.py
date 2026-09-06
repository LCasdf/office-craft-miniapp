"""Shared API envelope & common schemas (no FastAPI dependency)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ApiEnvelope(ApiModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    user_msg: str = Field(default="ok", alias="user_msg")
    data: T | None = None
    request_id: str = Field(alias="requestId")
    task_id: str | None = Field(default=None, alias="taskId")


class WxLoginRequest(ApiModel):
    code: str


class TokenPair(ApiModel):
    access_token: str = Field(alias="accessToken")
    expires_in: int = Field(alias="expiresIn")
    refresh_token: str = Field(alias="refreshToken")
    refresh_expires_in: int = Field(alias="refreshExpiresIn")


class RefreshRequest(ApiModel):
    refresh_token: str = Field(alias="refreshToken")


class HealthData(ApiModel):
    status: str = "ok"
    service: str


def envelope_ok(
    data: Any,
    request_id: str,
    *,
    user_msg: str = "ok",
    task_id: str | None = None,
) -> dict[str, Any]:
    return {
        "code": 0,
        "message": "ok",
        "user_msg": user_msg,
        "data": data,
        "requestId": request_id,
        "taskId": task_id,
    }


def envelope_err(
    code: int,
    message: str,
    user_msg: str,
    request_id: str,
    *,
    task_id: str | None = None,
    data: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "user_msg": user_msg,
        "data": data,
        "requestId": request_id,
        "taskId": task_id,
    }
