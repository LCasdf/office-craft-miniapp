"""AI client abstraction — no FastAPI/Celery imports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from oc_core.ai.character_card_schema import validate_and_normalize
from oc_core.ai.prompts import CHARACTER_CARD_PROMPT_VERSION


@dataclass(slots=True)
class AIResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    provider: str = "mock"
    model: str = "mock"


class AIClient(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AIResult: ...


def _extract_premise(messages: list[dict[str, str]]) -> str:
    last = messages[-1]["content"] if messages else ""
    m = re.search(r"Premise[^\n]*:\n(.*)", last, re.S)
    text = (m.group(1) if m else last).strip()
    return text[:2000]


def _mock_character_card(premise: str) -> dict[str, Any]:
    token = (re.split(r"[\s，,、]", premise) or ["旅人"])[0][:8] or "旅人"
    return validate_and_normalize(
        {
            "name": f"{token}",
            "title": "旅途中人",
            "avatarDesc": f"与「{premise[:36]}」气质相符的外貌：清瘦身形，眼神沉静。",
            "personality": "外冷内热，善于观察；面对抉择时会犹豫，但一旦决定就贯彻到底。",
            "story": f"因「{premise[:80]}」而踏上旅途。沿途结识盟友，也学会独自承担。",
            "ability": "洞察人心、草药辨识、短兵相接",
            "weakness": "不擅拒绝他人请托，易被旧忆牵绊",
            "remark": "Mock 草稿，可继续编辑。",
        }
    )


class MockAIClient:
    """MVP — returns schema-valid character-card JSON when asked."""

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AIResult:
        purpose = (extra or {}).get("purpose") or ""
        sys = " ".join(
            (m.get("content") or "") for m in messages if m.get("role") == "system"
        )
        if purpose == "character_card" or "avatarDesc" in sys or "character-card" in sys.lower():
            premise = _extract_premise(messages)
            payload = _mock_character_card(premise)
            return AIResult(
                content=json.dumps(payload, ensure_ascii=False),
                prompt_tokens=len(premise) // 2 + 20,
                completion_tokens=80,
                provider="mock",
                model=model or "mock",
            )
        last = messages[-1]["content"] if messages else ""
        return AIResult(
            content=f'{{"echo": {last[:200]!r}}}',
            prompt_tokens=10,
            completion_tokens=10,
            provider="mock",
            model=model or "mock",
        )


def parse_character_card_content(content: str) -> dict[str, Any]:
    data = json.loads(content)
    return validate_and_normalize(data)


def build_ai_client(provider: str = "mock") -> AIClient:
    if provider == "mock":
        return MockAIClient()
    return MockAIClient()


__all__ = [
    "AIClient",
    "AIResult",
    "MockAIClient",
    "build_ai_client",
    "parse_character_card_content",
    "CHARACTER_CARD_PROMPT_VERSION",
]
