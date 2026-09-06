"""AI client abstraction — no FastAPI/Celery imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


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


class MockAIClient:
    """MVP placeholder — returns fixed JSON-ish text."""

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AIResult:
        last = messages[-1]["content"] if messages else ""
        return AIResult(
            content=f'{{"echo": {last[:200]!r}}}',
            prompt_tokens=10,
            completion_tokens=10,
            provider="mock",
            model=model or "mock",
        )


def build_ai_client(provider: str = "mock") -> AIClient:
    if provider == "mock":
        return MockAIClient()
    # Future: openai-compatible / vendor SDKs
    return MockAIClient()
