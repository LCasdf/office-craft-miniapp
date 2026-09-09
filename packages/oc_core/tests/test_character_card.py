"""Character card schema + mock AI + moderation + Pillow."""

from __future__ import annotations

from pathlib import Path

import pytest
from oc_core.ai.character_card_schema import SchemaError, validate_and_normalize
from oc_core.ai.client import MockAIClient, parse_character_card_content
from oc_core.ai.prompts import CHARACTER_CARD_PROMPT_VERSION, character_card_messages
from oc_core.converters.character_card_image import render_character_card_png
from oc_core.moderation import ContentBlocked, moderate_payload, moderate_text


def test_schema_normalize_truncates():
    raw = {
        "name": "x" * 40,
        "title": "t" * 40,
        "avatarDesc": "a" * 600,
        "personality": "p" * 600,
        "story": "s" * 2000,
        "ability": "ab" * 300,
        "weakness": "w" * 500,
        "remark": "r" * 500,
    }
    out = validate_and_normalize(raw)
    assert out["schemaVersion"] == "2"
    assert len(out["name"]) == 32
    assert len(out["title"]) == 32
    assert len(out["avatarDesc"]) == 500
    assert out["ability"]


def test_schema_defaults():
    out = validate_and_normalize({"name": ""})
    assert out["name"] == "未命名角色"
    assert out["title"]


def test_moderation_blocks_premise():
    with pytest.raises(ContentBlocked):
        moderate_text("这段含违禁词应被拦")


def test_moderation_blocks_payload():
    with pytest.raises(ContentBlocked):
        moderate_payload({"name": "ok", "story": "涉及色情暴力内容"})


def test_moderation_allows_clean():
    moderate_text("江南雨巷的少年")
    moderate_payload(
        {
            "name": "林秋",
            "title": "纸鸢客",
            "avatarDesc": "青衫",
            "personality": "沉默",
            "story": "卖纸鸢",
            "ability": "手巧",
            "weakness": "内向",
            "remark": "",
        }
    )


def test_mock_generate_schema():
    client = MockAIClient()
    result = client.complete(
        messages=character_card_messages("一位剑客"),
        extra={"purpose": "character_card"},
    )
    payload = parse_character_card_content(result.content)
    assert payload["schemaVersion"] == "2"
    assert payload["name"]
    assert payload["avatarDesc"]
    assert CHARACTER_CARD_PROMPT_VERSION.startswith("character_card")


def test_pillow_writes_png(tmp_path: Path):
    out = tmp_path / "card.png"
    render_character_card_png(
        {
            "name": "林秋",
            "title": "纸鸢客",
            "story": "雨巷少年",
            "personality": "沉默寡言",
            "ability": "手巧",
            "weakness": "内向",
        },
        out,
    )
    assert out.is_file()
    assert out.stat().st_size > 500
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_text_to_portrait_png():
    from oc_core.ai.image_gen import generate_character_portrait_png

    png = generate_character_portrait_png(
        "隐居山林的草药师，银发", name="阿蘅", title="药庐主人"
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 2000
