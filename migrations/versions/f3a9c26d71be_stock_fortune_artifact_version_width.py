"""expand chart_artifact birth profile version storage for Fortune V2

Revision ID: f3a9c26d71be
Revises: e6b2c8f4a91d
Create Date: 2026-09-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f3a9c26d71be"
down_revision: str | None = "e6b2c8f4a91d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chart_artifact") as batch_op:
        batch_op.alter_column(
            "birth_profile_version",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    has_long_version = connection.execute(
        sa.text(
            "SELECT 1 FROM chart_artifact "
            "WHERE length(birth_profile_version) > 16 LIMIT 1"
        )
    ).first()
    if has_long_version:
        raise RuntimeError(
            "Cannot downgrade chart_artifact.birth_profile_version to 16 characters: "
            "longer version values exist. Preserve them or export the artifacts first."
        )

    with op.batch_alter_table("chart_artifact") as batch_op:
        batch_op.alter_column(
            "birth_profile_version",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
