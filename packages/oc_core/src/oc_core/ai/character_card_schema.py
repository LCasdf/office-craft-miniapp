"""Character card payload schema (schemaVersion=2 — editor form fields)."""

from __future__ import annotations

from typing import Any


class SchemaError(ValueError):
    pass


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s[:n] if len(s) > n else s


def validate_and_normalize(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SchemaError("payload must be object")
    name = _clip(str(raw.get("name") or ""), 32) or "未命名角色"
    title = _clip(str(raw.get("title") or ""), 32)
    avatar_desc = _clip(str(raw.get("avatarDesc") or raw.get("appearance") or ""), 500)
    personality = _clip(str(raw.get("personality") or ""), 500)
    story = _clip(str(raw.get("story") or raw.get("summary") or ""), 1200)
    ability = _clip(str(raw.get("ability") or ""), 400)
    weakness = _clip(str(raw.get("weakness") or ""), 400)
    remark = _clip(str(raw.get("remark") or ""), 400)
    return {
        "schemaVersion": "2",
        "name": name,
        "title": title or "无名之辈",
        "avatarDesc": avatar_desc or "待补充外貌描写",
        "personality": personality or "沉稳、好奇",
        "story": story or "故事尚待书写",
        "ability": ability or "尚在觉醒",
        "weakness": weakness or "未知",
        "remark": remark,
    }
