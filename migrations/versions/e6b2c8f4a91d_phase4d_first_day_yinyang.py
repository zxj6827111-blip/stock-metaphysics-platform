"""phase4d add first-day yinyang to stock_master

Revision ID: e6b2c8f4a91d
Revises: c3e8a91f0b22
Create Date: 2026-09-20 20:20:00.000000

为什么加这两列
--------------
用户提供的权威表里带有「首日涨跌标识」（阳=首日收涨 / 阴=首日收跌），并明确要求
把它体现到八字里：本项目按 **阳→男命 / 阴→女命** 的假设起运（大运顺逆由性别与
年干阴阳共同决定）。这两列只作为该**显式假设**的输入，用于：

* ``astrology_calendar.py`` 的运限展示（--dayun 开关）；
* 未来若要回测 forward/reverse 两种假设，可直接查这两列。

**不是** 股票的真实性别 —— ``variant_mode`` 默认仍是 ``not_applicable``，
不输出大运，也不进入任何正式因子（AGENTS.md §5 的硬性约束）。
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e6b2c8f4a91d"
down_revision: str | None = "c3e8a91f0b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("stock_master") as batch_op:
        batch_op.add_column(sa.Column("first_day_pct_chg", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("first_day_yinyang", sa.String(length=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stock_master") as batch_op:
        batch_op.drop_column("first_day_yinyang")
        batch_op.drop_column("first_day_pct_chg")
