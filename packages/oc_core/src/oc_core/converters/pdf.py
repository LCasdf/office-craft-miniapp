"""PDF compress (Ghostscript) and merge (pypdf)."""

from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

from pypdf import PdfReader, PdfWriter

GS_QUALITY = {
    "high": "/printer",
    "standard": "/ebook",
    "extreme": "/screen",
}


class PdfError(Exception):
    def __init__(self, message: str, *, kind: str = "invalid"):
        super().__init__(message)
        self.kind = kind  # encrypted|corrupted|too_many_pages|gs_missing|timeout|invalid


def find_gs() -> str | None:
    return shutil.which("gs") or shutil.which("gswin64c")


def open_pdf(path: Path) -> PdfReader:
    with path.open("rb") as f:
        head = f.read(5)
    if not head.startswith(b"%PDF"):
        raise PdfError(f"{path.name} 不是有效 PDF", kind="corrupted")
    try:
        reader = PdfReader(path, strict=False)
    except Exception as e:
        raise PdfError(f"{path.name} 已损坏，无法打开", kind="corrupted") from e
    if reader.is_encrypted:
        raise PdfError(f"{path.name} 已加密", kind="encrypted")
    return reader


def compress_pdf(
    src: Path,
    dest: Path,
    *,
    quality: str = "standard",
    timeout_sec: int = 60,
) -> Path:
    if quality not in GS_QUALITY:
        raise PdfError(f"unknown quality: {quality}", kind="invalid")
    open_pdf(src)
    gs = find_gs()
    if not gs:
        raise PdfError("Ghostscript (gs) not installed", kind="gs_missing")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        gs,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={GS_QUALITY[quality]}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        f"-sOutputFile={dest}",
        str(src),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired as e:
        raise PdfError("pdf compress timeout", kind="timeout") from e
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 5:
        raise PdfError("PDF 无法压缩，请检查文件是否损坏", kind="invalid")
    return dest


def merge_pdfs(
    paths: list[Path],
    dest: Path,
    *,
    max_pages: int = 200,
    timeout_sec: int = 120,
) -> Path:
    if len(paths) < 2:
        raise PdfError("merge needs at least 2 files", kind="invalid")

    def _do() -> Path:
        writer = PdfWriter()
        total = 0
        for p in paths:
            reader = open_pdf(p)
            n = len(reader.pages)
            total += n
            if total > max_pages:
                raise PdfError(f"total pages exceed {max_pages}", kind="too_many_pages")
            for page in reader.pages:
                writer.add_page(page)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            writer.write(f)
        return dest

    # ponytail: thread join can't kill native hangs; ceiling=timeout_sec → process isolate
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_do)
        try:
            return fut.result(timeout=timeout_sec)
        except FuturesTimeout as e:
            raise PdfError("pdf merge timeout", kind="timeout") from e
        except PdfError:
            raise
        except Exception as e:
            raise PdfError(str(e) or "merge failed", kind="invalid") from e
