from pathlib import Path

import pytest
from oc_core.converters.pdf import PdfError, compress_pdf, find_gs, merge_pdfs, open_pdf
from pypdf import PdfReader, PdfWriter


def _blank(path: Path, pages: int = 1, encrypt: str | None = None) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if encrypt:
        writer.encrypt(encrypt)
    with path.open("wb") as f:
        writer.write(f)
    return path


def test_merge_two_pdfs(tmp_path: Path):
    a = _blank(tmp_path / "a.pdf", 1)
    b = _blank(tmp_path / "b.pdf", 2)
    dest = tmp_path / "out.pdf"
    merge_pdfs([a, b], dest)
    assert dest.is_file()
    assert len(PdfReader(dest).pages) == 3


def test_merge_timeout(tmp_path: Path, monkeypatch):
    import time

    import oc_core.converters.pdf as pdf_mod

    a = _blank(tmp_path / "a.pdf")
    b = _blank(tmp_path / "b.pdf")

    def slow_write(*_a, **_k):
        time.sleep(2)
        raise AssertionError("should have timed out")

    monkeypatch.setattr(pdf_mod.PdfWriter, "write", slow_write)
    with pytest.raises(PdfError) as ei:
        merge_pdfs([a, b], tmp_path / "out.pdf", timeout_sec=1)
    assert ei.value.kind == "timeout"


def test_merge_encrypted_raises(tmp_path: Path):
    a = _blank(tmp_path / "a.pdf")
    b = _blank(tmp_path / "b.pdf", encrypt="secret")
    with pytest.raises(PdfError) as ei:
        merge_pdfs([a, b], tmp_path / "out.pdf")
    assert ei.value.kind == "encrypted"


def test_merge_bad_magic(tmp_path: Path):
    a = _blank(tmp_path / "a.pdf")
    b = tmp_path / "b.pdf"
    b.write_bytes(b"not a pdf")
    with pytest.raises(PdfError) as ei:
        merge_pdfs([a, b], tmp_path / "out.pdf")
    assert ei.value.kind == "corrupted"


def test_merge_page_limit(tmp_path: Path):
    a = _blank(tmp_path / "a.pdf", 100)
    b = _blank(tmp_path / "b.pdf", 101)
    with pytest.raises(PdfError) as ei:
        merge_pdfs([a, b], tmp_path / "out.pdf", max_pages=200)
    assert ei.value.kind == "too_many_pages"


def test_open_pdf_ok(tmp_path: Path):
    p = _blank(tmp_path / "a.pdf")
    assert len(open_pdf(p).pages) == 1


def test_compress_unknown_quality(tmp_path: Path):
    src = _blank(tmp_path / "a.pdf")
    with pytest.raises(PdfError) as ei:
        compress_pdf(src, tmp_path / "out.pdf", quality="nope")
    assert ei.value.kind == "invalid"


def test_compress_encrypted_raises(tmp_path: Path):
    src = _blank(tmp_path / "enc.pdf", encrypt="secret")
    with pytest.raises(PdfError) as ei:
        compress_pdf(src, tmp_path / "out.pdf")
    assert ei.value.kind == "encrypted"


def test_compress_requires_gs_or_writes(tmp_path: Path):
    src = _blank(tmp_path / "in.pdf", 2)
    dest = tmp_path / "out.pdf"
    if find_gs():
        compress_pdf(src, dest, quality="extreme")
        assert dest.is_file()
        assert dest.stat().st_size > 0
        assert len(PdfReader(dest).pages) == 2
    else:
        with pytest.raises(PdfError) as ei:
            compress_pdf(src, dest)
        assert ei.value.kind == "gs_missing"
