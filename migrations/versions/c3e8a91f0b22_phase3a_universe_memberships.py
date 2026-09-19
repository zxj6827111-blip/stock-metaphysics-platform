"""phase3a add universe_memberships (Point-in-Time Universe)

Revision ID: c3e8a91f0b22
Revises: dadb21454a4b
Create Date: 2026-09-19 14:35:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3e8a91f0b22"
down_revision: str | None = "dadb21454a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "universe_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("universe_version", sa.String(length=32), nullable=False),
        sa.Column("stock_code", sa.String(length=16), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("board", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("list_date", sa.Date(), nullable=False),
        sa.Column("delist_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="tencent_hfq_import"),
        sa.Column("source_snapshot", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "delist_source",
            sa.String(length=64),
            nullable=False,
            server_default="NOT_AVAILABLE_FROM_PROVIDER",
        ),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "universe_version", "stock_code",
            name="uq_universe_memberships_version_stock",
        ),
    )
    with op.batch_alter_table("universe_memberships", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_universe_memberships_universe_version"),
            ["universe_version"], unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_universe_memberships_stock_code"),
            ["stock_code"], unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_universe_memberships_list_date"),
            ["list_date"], unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_universe_memberships_delist_date"),
            ["delist_date"], unique=False,
        )
        batch_op.create_index(
            "ix_universe_memberships_asof",
            ["universe_version", "list_date", "delist_date"], unique=False,
        )
        batch_op.create_index(
            "ix_universe_memberships_stock",
            ["stock_code", "universe_version"], unique=False,
        )


def downgrade() -> None:
    op.drop_table("universe_memberships")
