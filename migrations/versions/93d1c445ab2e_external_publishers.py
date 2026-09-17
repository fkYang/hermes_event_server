"""external publishers

Revision ID: 93d1c445ab2e
Revises: 54b99720166f
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "93d1c445ab2e"
down_revision: str | None = "54b99720166f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MYSQL_TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    op.create_table(
        "event_publishers",
        sa.Column("publisher_key", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("allowed_event_prefixes", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("publisher_key"),
        **MYSQL_TABLE_OPTIONS,
    )
    op.create_index("ix_event_publishers_enabled", "event_publishers", ["enabled"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_event_publishers_enabled", table_name="event_publishers")
    op.drop_table("event_publishers")
