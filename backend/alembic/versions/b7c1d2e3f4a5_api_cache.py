"""api_cache table for restart-proof third-party response caching

Revision ID: b7c1d2e3f4a5
Revises: 7532ab95d30a
Create Date: 2026-09-20 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, None] = "7532ab95d30a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_cache",
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    with op.batch_alter_table("api_cache", schema=None) as batch_op:
        batch_op.create_index("ix_api_cache_expires_at", ["expires_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("api_cache", schema=None) as batch_op:
        batch_op.drop_index("ix_api_cache_expires_at")
    op.drop_table("api_cache")
