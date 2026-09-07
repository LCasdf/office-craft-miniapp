"""Upload credential + server-side put to MinIO (miniapp-friendly)."""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from oc_core.config import get_settings
from oc_core.storage import put_bytes, upload_path_prefix
from oc_shared.constants import (
    IMAGE_TO_PDF_EXTS,
    IMAGE_TO_PDF_MAX_BYTES,
    IMAGE_TO_PDF_MAX_COUNT,
    OFFICE_TO_PDF_EXTS,
    PDF_COMPRESS_MAX_BYTES,
    PDF_EXTS,
    PDF_MERGE_MAX_COUNT,
    PDF_MERGE_MAX_FILE_BYTES,
    PDF_MERGE_MIN_COUNT,
    TASK_COST_QUOTA,
    UPLOAD_CREDENTIAL_TTL_SECONDS,
)
from oc_shared.enums import TaskType
from oc_shared.error_codes import ErrorCode
from oc_shared.schemas import envelope_err, envelope_ok
from pydantic import BaseModel, Field

router = APIRouter(prefix="/uploads", tags=["uploads"])

_DEV_USER_ID = "0"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class CredentialBody(BaseModel):
    task_type: TaskType = Field(alias="taskType")
    file_count: int = Field(alias="fileCount", ge=1)
    total_size_bytes: int | None = Field(default=None, alias="totalSizeBytes")
    filename_hints: list[str] | None = Field(default=None, alias="filenameHints")

    model_config = {"populate_by_name": True}


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "file"
    return cleaned[:180]


@router.post("/credential")
def create_credential(body: CredentialBody, request: Request):
    """Issue uploadId + pathPrefix. Local: use POST .../objects to put files."""
    request_id = getattr(request.state, "request_id", "unknown")
    settings = get_settings()

    if body.task_type == TaskType.IMAGE_TO_PDF and body.file_count > IMAGE_TO_PDF_MAX_COUNT:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "图片最多 20 张", request_id)
    if body.task_type == TaskType.OFFICE_TO_PDF and body.file_count != 1:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "Word 转 PDF 每次仅支持 1 个文件", request_id)
    if body.task_type == TaskType.PDF_COMPRESS and body.file_count != 1:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "PDF 压缩每次仅支持 1 个文件", request_id)
    if body.task_type == TaskType.PDF_MERGE and not (
        PDF_MERGE_MIN_COUNT <= body.file_count <= PDF_MERGE_MAX_COUNT
    ):
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(
            err.code,
            err.message,
            f"合并须选择 {PDF_MERGE_MIN_COUNT}–{PDF_MERGE_MAX_COUNT} 个 PDF",
            request_id,
        )

    ttl = settings.upload_credential_ttl_seconds or UPLOAD_CREDENTIAL_TTL_SECONDS
    now = datetime.now(UTC)
    expire_at = now + timedelta(seconds=ttl)
    upload_id = f"upl_{uuid.uuid4().hex[:16]}"
    env = settings.cos_env_prefix or settings.app_env
    path_prefix = upload_path_prefix(env=env, user_id=_DEV_USER_ID, upload_id=upload_id)
    start = int(time.time())
    expired = start + ttl

    data = {
        "uploadId": upload_id,
        "expireAt": expire_at.isoformat(),
        "cos": {
            "bucket": settings.cos_bucket or "office-craft",
            "region": settings.s3_region or settings.cos_region,
            "endpoint": settings.s3_endpoint_url or None,
            "pathPrefix": path_prefix,
            "credentials": {
                "tmpSecretId": settings.s3_access_key or "minioadmin",
                "tmpSecretKey": settings.s3_secret_key or "minioadmin",
                "sessionToken": "",
                "startTime": start,
                "expiredTime": expired,
            },
        },
        "uploadApiPath": f"/v1/uploads/{upload_id}/objects",
        "estimatedCostQuota": TASK_COST_QUOTA.get(body.task_type.value, 1),
    }
    return envelope_ok(data, request_id)


@router.post("/{upload_id}/objects")
async def put_upload_object(
    upload_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    index: Annotated[int, Form()] = 0,
    task_type: Annotated[str | None, Form()] = None,
    taskType: Annotated[str | None, Form()] = None,
):
    """Server-side put into MinIO under the upload prefix (M1 local path)."""
    request_id = getattr(request.state, "request_id", "unknown")
    if not upload_id.startswith("upl_") or len(upload_id) > 40:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    raw_name = file.filename or "file"
    safe = _safe_filename(raw_name)
    ext = Path(safe).suffix.lower()
    tt = taskType or task_type or ""
    if tt == TaskType.IMAGE_TO_PDF.value and ext not in IMAGE_TO_PDF_EXTS:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "仅支持 jpg/png/webp", request_id)
    if tt == TaskType.OFFICE_TO_PDF.value and ext not in OFFICE_TO_PDF_EXTS:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "仅支持 doc/docx", request_id)
    if tt in (TaskType.PDF_COMPRESS.value, TaskType.PDF_MERGE.value) and ext not in PDF_EXTS:
        err = ErrorCode.PARAM_INVALID.defn
        return envelope_err(err.code, err.message, "仅支持 PDF", request_id)

    data = await file.read()
    if tt == TaskType.IMAGE_TO_PDF.value and len(data) > IMAGE_TO_PDF_MAX_BYTES:
        err = ErrorCode.FILE_TOO_LARGE.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)
    if tt == TaskType.PDF_COMPRESS.value and len(data) > PDF_COMPRESS_MAX_BYTES:
        err = ErrorCode.FILE_TOO_LARGE.defn
        return envelope_err(err.code, err.message, "单个 PDF 不能超过 50MB", request_id)
    if tt == TaskType.PDF_MERGE.value and len(data) > PDF_MERGE_MAX_FILE_BYTES:
        err = ErrorCode.FILE_TOO_LARGE.defn
        return envelope_err(err.code, err.message, "单个 PDF 不能超过 30MB", request_id)
    if len(data) > 50 * 1024 * 1024:
        err = ErrorCode.FILE_TOO_LARGE.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    settings = get_settings()
    env = settings.cos_env_prefix or settings.app_env
    prefix = upload_path_prefix(env=env, user_id=_DEV_USER_ID, upload_id=upload_id)
    cos_key = f"{prefix}{index}_{safe}"
    try:
        put_bytes(cos_key, data, content_type=file.content_type or "application/octet-stream")
    except Exception:
        err = ErrorCode.INTERNAL_ERROR.defn
        return envelope_err(err.code, err.message, err.user_msg, request_id)

    return envelope_ok(
        {
            "uploadId": upload_id,
            "cosKey": cos_key,
            "filename": safe,
            "sizeBytes": len(data),
            "index": index,
        },
        request_id,
    )
