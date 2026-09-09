"""Character card persistence — draft / optimistic lock / cover."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from oc_core.models import CharacterCard

SCHEMA_VERSION = "1"
PROMPT_VERSION = "character_card.v1"


class VersionConflict(Exception):
    """Optimistic lock failed."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_by_public_id(
    session: Session, public_id: str, *, user_id: int | None = None
) -> CharacterCard | None:
    stmt = select(CharacterCard).where(CharacterCard.public_id == public_id)
    if user_id is not None:
        stmt = stmt.where(CharacterCard.user_id == user_id)
    return session.scalar(stmt)


def get_by_idempotency(
    session: Session, *, user_id: int, key: str
) -> CharacterCard | None:
    return session.scalar(
        select(CharacterCard).where(
            CharacterCard.user_id == user_id,
            CharacterCard.idempotency_key == key,
        )
    )


def create_card(
    session: Session,
    *,
    public_id: str,
    user_id: int,
    title: str,
    payload: dict,
    idempotency_key: str | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> CharacterCard:
    card = CharacterCard(
        public_id=public_id,
        user_id=user_id,
        title=(title or "未命名角色")[:128],
        schema_version=SCHEMA_VERSION,
        version=1,
        payload_json=payload,
        status="draft",
        idempotency_key=idempotency_key,
        prompt_version=prompt_version,
    )
    session.add(card)
    session.flush()
    return card


def update_payload(
    session: Session,
    card: CharacterCard,
    *,
    payload: dict,
    expected_version: int,
    title: str | None = None,
) -> CharacterCard:
    if int(card.version) != int(expected_version):
        raise VersionConflict(f"expected {expected_version}, got {card.version}")
    card.payload_json = payload
    if title is not None:
        card.title = title[:128]
    elif payload.get("name"):
        card.title = str(payload["name"])[:128]
    card.version = int(card.version) + 1
    card.updated_at = _now()
    session.flush()
    return card


def set_cover_key(session: Session, card: CharacterCard, cos_key: str) -> None:
    card.cover_cos_key = cos_key
    card.status = "published"
    card.updated_at = _now()


def list_for_user(
    session: Session, user_id: int, *, limit: int = 50
) -> list[CharacterCard]:
    stmt = (
        select(CharacterCard)
        .where(CharacterCard.user_id == user_id)
        .order_by(CharacterCard.updated_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def delete_card_for_user(session: Session, public_id: str, *, user_id: int) -> bool:
    card = get_by_public_id(session, public_id, user_id=user_id)
    if card is None:
        return False
    session.delete(card)
    return True


def card_to_dict(card: CharacterCard, *, cover_url: str | None = None) -> dict:
    payload = dict(card.payload_json or {})
    payload.pop("_meta", None)
    data = {
        "cardId": card.public_id,
        "version": card.version,
        "schemaVersion": card.schema_version,
        "promptVersion": card.prompt_version,
        "title": card.title,
        "status": card.status,
        "payload": payload,
        "coverCosKey": card.cover_cos_key,
        "createdAt": card.created_at.isoformat() if card.created_at else None,
        "updatedAt": card.updated_at.isoformat() if card.updated_at else None,
    }
    if cover_url is not None:
        data["coverUrl"] = cover_url
    return data
