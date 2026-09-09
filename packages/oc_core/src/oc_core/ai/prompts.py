"""Prompt versions for AI features (see docs/08-AI与Prompt规范.md)."""

from __future__ import annotations

CHARACTER_CARD_PROMPT_VERSION = "character_card.v2"

CHARACTER_CARD_SYSTEM = (
    "You are a character-card author for a WeChat miniapp. "
    "Given a short premise, output ONLY a JSON object with fields: "
    "name, title, avatarDesc, personality, story, ability, weakness, remark. "
    "All values are Chinese strings. name≤32, title≤32, others concise prose. "
    "No markdown, no code fences, no extra keys."
)


def character_card_messages(premise: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": CHARACTER_CARD_SYSTEM},
        {
            "role": "user",
            "content": f"Premise (≤2000 chars):\n{(premise or '').strip()}",
        },
    ]
