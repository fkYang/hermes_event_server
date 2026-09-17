"""subscription match keys and scheduled delivery

Revision ID: b41f7c2e9a10
Revises: 93d1c445ab2e
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b41f7c2e9a10"
down_revision: str | None = "93d1c445ab2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_types", "match_key_field"),
    ("event_types", "match_key_options"),
    ("event_types", "match_keys_required"),
    ("subscriptions", "match_keys"),
)


def _empty_json_default() -> sa.TextClause:
    """MySQL rejects a plain literal default on JSON columns and needs an expression."""
    if op.get_bind().dialect.name == "mysql":
        return sa.text("(JSON_ARRAY())")
    return sa.text("'[]'")


def upgrade() -> None:
    empty_json = _empty_json_default()
    op.add_column("event_types", sa.Column("match_key_field", sa.String(length=64), nullable=True))
    op.add_column(
        "event_types",
        sa.Column("match_key_options", sa.JSON(), nullable=False, server_default=empty_json),
    )
    op.add_column(
        "event_types",
        sa.Column("match_keys_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "subscriptions",
        sa.Column("match_keys", sa.JSON(), nullable=False, server_default=empty_json),
    )


def downgrade() -> None:
    for table, column in reversed(ADDED_COLUMNS):
        op.drop_column(table, column)
