"""Keyword moderation stub — bidirectional (premise / payload fields)."""

from __future__ import annotations

from typing import Any

# ponytail: keyword blacklist ceiling — upgrade to vendor moderation API
_BLOCKLIST = frozenset(
    {
        "违禁词",
        "色情暴力",
        "赌博诈骗",
        "恐怖袭击",
        "毒品交易",
    }
)


class ContentBlocked(Exception):
    def __init__(self, matched: str = ""):
        super().__init__(matched or "blocked")
        self.matched = matched


def _scan_text(text: str) -> str | None:
    if not text:
        return None
    lower = text.lower()
    for word in _BLOCKLIST:
        if word.lower() in lower:
            return word
    return None


def moderate_text(text: str) -> None:
    hit = _scan_text(text or "")
    if hit:
        raise ContentBlocked(hit)


def moderate_payload(payload: dict[str, Any]) -> None:
    """Scan common character-card string fields (+ nested lists)."""
    chunks: list[str] = []
    for key in (
        "name",
        "title",
        "summary",
        "personality",
        "background",
        "premise",
        "avatarDesc",
        "story",
        "ability",
        "weakness",
        "remark",
        "appearance",
    ):
        val = payload.get(key)
        if isinstance(val, str):
            chunks.append(val)
    for key in ("traits", "tags", "quirks"):
        val = payload.get(key)
        if isinstance(val, list):
            chunks.extend(str(x) for x in val)
        elif isinstance(val, str):
            chunks.append(val)
    moderate_text("\n".join(chunks))
