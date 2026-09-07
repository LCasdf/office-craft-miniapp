from __future__ import annotations

from pathlib import Path

from oc_core.converters.image_pdf import images_to_pdf
from oc_core.converters.office_pdf import OfficeConvertError, office_to_pdf
from oc_core.converters.pdf import PdfError, compress_pdf, merge_pdfs
from oc_shared.constants import (
    DEFAULT_TASK_TIMEOUT_SECONDS,
    IMAGE_TO_PDF_EXTS,
    IMAGE_TO_PDF_MAX_COUNT,
    OFFICE_TO_PDF_EXTS,
    PDF_COMPRESS_MAX_BYTES,
    PDF_COMPRESS_QUALITIES,
    PDF_EXTS,
    PDF_MERGE_MAX_COUNT,
    PDF_MERGE_MAX_FILE_BYTES,
    PDF_MERGE_MAX_PAGES,
    PDF_MERGE_MAX_TOTAL_BYTES,
    PDF_MERGE_MIN_COUNT,
    TASK_TIMEOUTS,
)
from oc_shared.error_codes import ErrorCode

from oc_worker.celery_app import celery_app
from oc_worker.tasks.tools.runner import UserFacingError, run_file_tool


def _convert_images(tmp: Path, ctx: dict) -> Path:
    files: list[Path] = ctx["files"]
    params = ctx.get("params") or {}
    if not (1 <= len(files) <= IMAGE_TO_PDF_MAX_COUNT):
        raise UserFacingError(ErrorCode.PARAM_INVALID, "image count out of range")
    for f in files:
        if f.suffix.lower() not in IMAGE_TO_PDF_EXTS:
            raise UserFacingError(ErrorCode.PARAM_INVALID, f"bad image: {f.name}")
    orientation = params.get("orientation") or "auto"
    if orientation not in ("auto", "portrait"):
        orientation = "auto"
    dest = tmp / "result.pdf"
    try:
        images_to_pdf(files, dest, orientation=orientation)
    except ValueError as e:
        raise UserFacingError(ErrorCode.PARAM_INVALID, str(e)) from e
    return dest


def _convert_office(tmp: Path, ctx: dict) -> Path:
    files: list[Path] = ctx["files"]
    if len(files) != 1:
        raise UserFacingError(ErrorCode.PARAM_INVALID, "office_to_pdf needs exactly 1 file")
    src = files[0]
    if src.suffix.lower() not in OFFICE_TO_PDF_EXTS:
        raise UserFacingError(ErrorCode.PARAM_INVALID, f"bad office file: {src.name}")
    timeout = TASK_TIMEOUTS.get("office_to_pdf", DEFAULT_TASK_TIMEOUT_SECONDS)
    try:
        return office_to_pdf(src, tmp / "out", timeout_sec=timeout)
    except OfficeConvertError as e:
        if "not installed" in str(e):
            raise UserFacingError(
                ErrorCode.INTERNAL_ERROR,
                str(e),
                user_msg="本机未安装 LibreOffice，无法转换 Word。"
                "请 brew install --cask libreoffice 后重启 Worker",
            ) from e
        raise UserFacingError(ErrorCode.PARAM_INVALID, str(e)) from e


def _raise_pdf(e: PdfError) -> None:
    if e.kind == "encrypted":
        raise UserFacingError(ErrorCode.PDF_ENCRYPTED, str(e)) from e
    if e.kind == "gs_missing":
        raise UserFacingError(
            ErrorCode.INTERNAL_ERROR,
            str(e),
            user_msg="本机未安装 Ghostscript，无法压缩 PDF。"
            "请 brew install ghostscript 后重启 Worker",
        ) from e
    if e.kind == "timeout":
        raise UserFacingError(ErrorCode.TASK_TIMEOUT, str(e)) from e
    if e.kind == "too_many_pages":
        raise UserFacingError(
            ErrorCode.PARAM_INVALID,
            str(e),
            user_msg="总页数超过 200 页，请拆分后再合并",
        ) from e
    raise UserFacingError(ErrorCode.PARAM_INVALID, str(e), user_msg=str(e)) from e


def _compress_pdf(tmp: Path, ctx: dict) -> Path:
    files: list[Path] = ctx["files"]
    params = ctx.get("params") or {}
    if len(files) != 1:
        raise UserFacingError(ErrorCode.PARAM_INVALID, "pdf_compress needs exactly 1 file")
    src = files[0]
    if src.suffix.lower() not in PDF_EXTS:
        raise UserFacingError(ErrorCode.PARAM_INVALID, f"bad pdf: {src.name}")
    if src.stat().st_size > PDF_COMPRESS_MAX_BYTES:
        raise UserFacingError(ErrorCode.FILE_TOO_LARGE, src.name)
    quality = params.get("quality") or "standard"
    if quality not in PDF_COMPRESS_QUALITIES:
        quality = "standard"
    timeout = TASK_TIMEOUTS.get("pdf_compress", DEFAULT_TASK_TIMEOUT_SECONDS)
    try:
        return compress_pdf(src, tmp / "result.pdf", quality=quality, timeout_sec=timeout)
    except PdfError as e:
        _raise_pdf(e)
        raise


def _merge_pdfs(tmp: Path, ctx: dict) -> Path:
    files: list[Path] = ctx["files"]
    if not (PDF_MERGE_MIN_COUNT <= len(files) <= PDF_MERGE_MAX_COUNT):
        raise UserFacingError(ErrorCode.PARAM_INVALID, "pdf_merge file count out of range")
    total = 0
    for f in files:
        if f.suffix.lower() not in PDF_EXTS:
            raise UserFacingError(ErrorCode.PARAM_INVALID, f"bad pdf: {f.name}")
        size = f.stat().st_size
        if size > PDF_MERGE_MAX_FILE_BYTES:
            raise UserFacingError(ErrorCode.FILE_TOO_LARGE, f.name)
        total += size
    if total > PDF_MERGE_MAX_TOTAL_BYTES:
        raise UserFacingError(ErrorCode.FILE_TOO_LARGE, "total too large")
    try:
        return merge_pdfs(files, tmp / "result.pdf", max_pages=PDF_MERGE_MAX_PAGES)
    except PdfError as e:
        _raise_pdf(e)
        raise


@celery_app.task(name="oc_worker.tasks.tools.image_to_pdf", bind=True, max_retries=1)
def image_to_pdf_task(self, *, task_id: str, request_id: str = "") -> dict:
    return run_file_tool(task_id=task_id, request_id=request_id, convert=_convert_images)


@celery_app.task(name="oc_worker.tasks.tools.office_to_pdf", bind=True, max_retries=1)
def office_to_pdf_task(self, *, task_id: str, request_id: str = "") -> dict:
    return run_file_tool(task_id=task_id, request_id=request_id, convert=_convert_office)


@celery_app.task(name="oc_worker.tasks.tools.pdf_compress", bind=True, max_retries=1)
def pdf_compress_task(self, *, task_id: str, request_id: str = "") -> dict:
    return run_file_tool(task_id=task_id, request_id=request_id, convert=_compress_pdf)


@celery_app.task(name="oc_worker.tasks.tools.pdf_merge", bind=True, max_retries=1)
def pdf_merge_task(self, *, task_id: str, request_id: str = "") -> dict:
    return run_file_tool(task_id=task_id, request_id=request_id, convert=_merge_pdfs)
