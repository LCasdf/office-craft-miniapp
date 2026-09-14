"""PPT outline persistence — optimistic lock."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from oc_core.models import PptOutline

SCHEMA_VERSION = "1"
PROMPT_VERSION = "ppt_outline.v1"


class VersionConflict(Exception):
    """Optimistic lock failed."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_by_public_id(
    session: Session, public_id: str, *, user_id: int | None = None
) -> PptOutline | None:
    stmt = select(PptOutline).where(PptOutline.public_id == public_id)
    if user_id is not None:
        stmt = stmt.where(PptOutline.user_id == user_id)
    return session.scalar(stmt)


def get_by_idempotency(
    session: Session, *, user_id: int, key: str
) -> PptOutline | None:
    return session.scalar(
        select(PptOutline).where(
            PptOutline.user_id == user_id,
            PptOutline.idempotency_key == key,
        )
    )


def create_outline(
    session: Session,
    *,
    public_id: str,
    user_id: int,
    topic: str,
    template_id: str,
    pages: list[dict],
    idempotency_key: str | None = None,
    prompt_version: str = PROMPT_VERSION,
) -> PptOutline:
    row = PptOutline(
        public_id=public_id,
        user_id=user_id,
        topic=(topic or "未命名")[:200],
        template_id=template_id[:64],
        schema_version=SCHEMA_VERSION,
        version=1,
        pages_json=pages,
        status="draft",
        idempotency_key=idempotency_key,
        prompt_version=prompt_version,
    )
    session.add(row)
    session.flush()
    return row


def update_pages(
    session: Session,
    row: PptOutline,
    *,
    pages: list[dict],
    expected_version: int,
    template_id: str | None = None,
) -> PptOutline:
    if int(row.version) != int(expected_version):
        raise VersionConflict(f"expected {expected_version}, got {row.version}")
    row.pages_json = pages
    if template_id:
        row.template_id = template_id[:64]
    row.version = int(row.version) + 1
    row.updated_at = _now()
    session.flush()
    return row


def outline_to_dict(row: PptOutline) -> dict:
    return {
        "outlineId": row.public_id,
        "outlineVersion": row.version,
        "topic": row.topic,
        "templateId": row.template_id,
        "schemaVersion": row.schema_version,
        "promptVersion": row.prompt_version,
        "pages": list(row.pages_json or []),
        "status": row.status,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }
