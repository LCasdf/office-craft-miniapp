"""Office → PDF via LibreOffice (soffice)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf"}


class OfficeConvertError(Exception):
    def __init__(self, message: str, *, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


def find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    # macOS .app install (not always on PATH)
    mac = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if mac.is_file():
        return str(mac)
    return None


def office_to_pdf(src: Path, out_dir: Path, *, timeout_sec: int = 180) -> Path:
    """Convert Word/ODT to PDF. Returns path to produced PDF."""
    if src.suffix.lower() not in _OFFICE_EXTS:
        raise OfficeConvertError(f"unsupported office type: {src.name}")
    soffice = find_soffice()
    if not soffice:
        raise OfficeConvertError("LibreOffice (soffice) not installed")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        soffice,
        "--headless",
        "--nologo",
        "--nofirststartwizard",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(src),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise OfficeConvertError("office convert timeout", stderr=str(e)) from e

    pdf = out_dir / f"{src.stem}.pdf"
    if proc.returncode != 0 or not pdf.is_file():
        raise OfficeConvertError(
            "office convert failed",
            stderr=(proc.stderr or proc.stdout or "")[:2000],
        )
    return pdf
