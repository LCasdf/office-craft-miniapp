"""Fix quotas.user_id — must not be AUTO_INCREMENT (dev user_id=0)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_quota_pk"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MySQL: INTEGER PK via Alembic became AUTO_INCREMENT; user_id=0 would be rewritten.
    op.alter_column(
        "quotas",
        "user_id",
        existing_type=sa.BigInteger(),
        autoincrement=False,
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "quotas",
        "user_id",
        existing_type=sa.BigInteger(),
        autoincrement=True,
        nullable=False,
    )
