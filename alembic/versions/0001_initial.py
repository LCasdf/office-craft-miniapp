"""Initial schema — users / quotas / tasks (MVP subset)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("openid", sa.String(64), nullable=False),
        sa.Column("unionid", sa.String(64), nullable=True),
        sa.Column("nickname", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("status", mysql.TINYINT(), nullable=False, server_default="1"),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("openid", name="uk_users_openid"),
        sa.UniqueConstraint("unionid", name="uk_users_unionid"),
    )
    op.create_table(
        "quotas",
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("daily_quota_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("daily_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_used_date", sa.Date(), nullable=False),
        sa.Column("total_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("frozen_quota", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vip_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vip_expire_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(26), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("progress", mysql.TINYINT(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Integer(), nullable=True),
        sa.Column("error_class", sa.String(16), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("retry_count", mysql.TINYINT(), nullable=False, server_default="0"),
        sa.Column("cost_quota", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quota_settled", mysql.TINYINT(), nullable=False, server_default="0"),
        sa.Column("input_meta", mysql.JSON(), nullable=True),
        sa.Column("output_meta", mysql.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("timeout_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("result_expires_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("started_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=3), server_default=sa.text("CURRENT_TIMESTAMP(3)"), nullable=False),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=3),
            server_default=sa.text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uk_tasks_public_id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uk_tasks_user_idempotency"),
    )
    op.create_index("idx_tasks_user_created", "tasks", ["user_id", "created_at"])
    op.create_index("idx_tasks_user_status", "tasks", ["user_id", "status"])


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("quotas")
    op.drop_table("users")
