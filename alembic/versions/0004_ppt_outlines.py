"""Add ppt_outlines table (M2b)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004_ppt_outlines"
down_revision: Union[str, None] = "0003_character_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ppt_outlines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(length=16),
            nullable=False,
            server_default="1",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pages_json", mysql.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text(
                "CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uk_ppt_outlines_public_id"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uk_ppt_outlines_user_idempotency"
        ),
    )
    op.create_index(
        "idx_ppt_outlines_user",
        "ppt_outlines",
        ["user_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ppt_outlines_user", table_name="ppt_outlines")
    op.drop_table("ppt_outlines")
