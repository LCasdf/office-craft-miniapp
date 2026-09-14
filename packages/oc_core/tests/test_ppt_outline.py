"""PPT outline schema + mock + pptx render."""

from __future__ import annotations

from pathlib import Path

import pytest
from oc_core.ai.client import MockAIClient, parse_ppt_outline_content
from oc_core.ai.ppt_outline_schema import (
    OutlineSchemaError,
    mock_outline_pages,
    normalize_pages,
    validate_page_count,
)
from oc_core.ai.prompts import PPT_OUTLINE_PROMPT_VERSION, ppt_outline_messages
from oc_core.converters.pptx_fill import render_outline_pptx


def test_page_count_bounds():
    assert validate_page_count(5) == 5
    assert validate_page_count(15) == 15
    with pytest.raises(OutlineSchemaError):
        validate_page_count(4)
    with pytest.raises(OutlineSchemaError):
        validate_page_count(16)


def test_normalize_pages():
    pages = normalize_pages(
        [{"title": "A", "bullets": ["1", "2"]}, {"title": "B", "bullets": ["x"]}]
        + [{"title": f"P{i}", "bullets": ["y"]} for i in range(3)]
    )
    assert len(pages) == 5
    assert pages[0]["title"] == "A"


def test_mock_outline_exact_count():
    pages = mock_outline_pages("季度复盘", 8)
    assert len(pages) == 8
    assert pages[0]["title"]


def test_mock_ai_ppt_outline():
    client = MockAIClient()
    result = client.complete(
        messages=ppt_outline_messages("产品发布", page_count=6),
        extra={"purpose": "ppt_outline"},
    )
    pages = parse_ppt_outline_content(result.content)
    assert len(pages) == 6
    assert PPT_OUTLINE_PROMPT_VERSION.startswith("ppt_outline")


def test_render_pptx(tmp_path: Path):
    pages = mock_outline_pages("演示文稿", 5)
    out = tmp_path / "deck.pptx"
    render_outline_pptx(pages, out)
    assert out.is_file()
    assert out.stat().st_size > 2000
    # zip/pptx magic
    assert out.read_bytes()[:2] == b"PK"
