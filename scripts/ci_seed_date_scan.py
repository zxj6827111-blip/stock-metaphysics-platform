"""CI/E2E 确定性种子：最小 canonical 股票集（StockMaster + BirthProfile + PIT 成员）。

用途：让择日关系扫描的端到端用例在**不访问真实行情网络**、不依赖开发库的前提下
跑真实代码路径（PIT 股票池 → 3×3 矩阵 → 流日判定 → API → 页面）。

用法::

    SMP_DATABASE_URL=sqlite:////tmp/smp-e2e.sqlite3 \\
        PYTHONUTF8=1 python scripts/ci_seed_date_scan.py

幂等：重复运行不会重复插入。仅写这 4 只固定标的，不触碰任何真实数据源。
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.db.base import get_engine, get_session_factory, init_db  # noqa: E402
from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow  # noqa: E402

#: 固定样本：跨交易所（SZSE / SSE）与不同上市年份。
FIXTURE_STOCKS = [
    ("000001", "平安银行", "SZSE", "000001.SZ", date(1991, 4, 3)),
    ("600519", "贵州茅台", "SSE", "600519.SH", date(2001, 8, 27)),
    ("600036", "招商银行", "SSE", "600036.SH", date(2002, 4, 9)),
    ("300750", "宁德时代", "SZSE", "300750.SZ", date(2018, 6, 11)),
]

UNIVERSE_VERSION = "v4-full"
BIRTH_PROFILE_VERSION = "v2-phase4b-listing_open"


def seed() -> int:
    init_db()
    session = get_session_factory()()
    inserted = 0
    try:
        for code, name, exchange, wind_code, listing in FIXTURE_STOCKS:
            if session.get(StockMasterRow, code) is None:
                session.add(StockMasterRow(
                    stock_code=code,
                    wind_code=wind_code,
                    name=name,
                    exchange=exchange,
                    board="主板" if not code.startswith("300") else "创业板",
                    listing_date=listing,
                    source="ci_seed",
                    data_quality_json={"grade": "A", "score": 1.0, "notes": ["ci fixture"]},
                ))
                inserted += 1
            profile_exists = session.execute(
                select(StockBirthProfileRow).where(
                    StockBirthProfileRow.stock_code == code,
                    StockBirthProfileRow.birth_basis == settings.canonical_birth_basis,
                    StockBirthProfileRow.birth_profile_version == BIRTH_PROFILE_VERSION,
                )
            ).scalars().first()
            if profile_exists is None:
                session.add(StockBirthProfileRow(
                    stock_code=code,
                    exchange=exchange,
                    birth_basis=settings.canonical_birth_basis,
                    birth_datetime=datetime(listing.year, listing.month, listing.day, 9, 30),
                    timezone="Asia/Shanghai",
                    source="ci_seed",
                    birth_profile_version=BIRTH_PROFILE_VERSION,
                    evidence_json={
                        "first_trading_day": listing.isoformat(),
                        "lookup_key": "ci_seed",
                    },
                    assumptions_json=[],
                    data_quality_json={"grade": "A", "score": 1.0, "notes": ["ci fixture"]},
                    variant_mode="not_applicable",
                    variant_note="",
                ))
            membership_exists = session.execute(
                select(UniverseMembershipRow).where(
                    UniverseMembershipRow.universe_version == UNIVERSE_VERSION,
                    UniverseMembershipRow.stock_code == code,
                )
            ).scalars().first()
            if membership_exists is None:
                session.add(UniverseMembershipRow(
                    universe_version=UNIVERSE_VERSION,
                    stock_code=code,
                    exchange=exchange,
                    board="主板" if not code.startswith("300") else "创业板",
                    list_date=listing,
                    status="active",
                    source="ci_seed",
                    source_snapshot="ci_seed",
                    delist_source="ci_seed",
                ))
        session.commit()
    finally:
        session.close()
    return inserted


if __name__ == "__main__":
    database = os.environ.get("SMP_DATABASE_URL", settings.resolved_database_url)
    count = seed()
    print(f"seeded stocks={len(FIXTURE_STOCKS)} new_master_rows={count} database={database}")
    # 触发一次 engine 解析，确保 URL 可连接（失败时以非 0 退出，CI 立刻可见）。
    get_engine()
