"""store first-day polarity provenance and visibility evidence

Revision ID: b9c7d81a6e34
Revises: f3a9c26d71be
Create Date: 2026-09-28 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b9c7d81a6e34"
down_revision: str | None = "f3a9c26d71be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stock_master") as batch_op:
        batch_op.add_column(sa.Column("first_day_evidence_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stock_master") as batch_op:
        batch_op.drop_column("first_day_evidence_json")
