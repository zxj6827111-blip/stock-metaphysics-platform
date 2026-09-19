"""Phase 3B：为 ``v2-phase3a`` universe 生成 4 种 birth model 的 birth_profile。

输出
====

* ``stock_birth_profile`` 每只股 × 每个可得模型 共 ~1500 行
  （``listing_open`` / ``listing_close`` / ``ipo_date`` × 500）
  + 500 行 ``company_foundation`` 的占位（``status=UNAVAILABLE``）——
  实际不插入（保持 NULL 语义）。

设计要点
========

* **不调用 BaziEngine** —— 那是 Phase 3B 的第二阶段任务（因子计算）。
  本脚本仅负责"把出生时刻定下来"。
* ``birth_basis`` 与 ``stock_birth_profile`` schema 已 ``Enum(BirthBasis)`` 使用；
  ``FIRST_TRADE`` 实际等价于 ``listing_close``，但保留枚举名，以方便扩展。
* 幂等：``(stock_code, birth_basis, birth_profile_version)`` 冲突时 update。

运行：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_generate_birth_profiles.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from src.core.schemas.common import (  # noqa: E402
    Assumption, BirthBasis, DataQuality, DataQualityGrade, SourceRef, VariantMode,
)
from src.core.schemas.stock import BirthProfileEvidence  # noqa: E402
from src.db.base import session_scope  # noqa: E402
from src.db.models import StockBirthProfileRow  # noqa: E402
from src.research.birth_models import (  # noqa: E402
    BirthModelId, build_birth,
)

UNIVERSE_VERSION = "v2-phase3a"

# 把 4 个 BirthModelId 映射到 BirthBasis（落库字段）。first_trade 我们用 listing_close 实现
# （连续竞价首日收盘时刻），落库 birth_basis=FIRST_TRADE，version="v1-phase3b-listing_close"。
MODEL_TO_BASIS: dict[BirthModelId, BirthBasis] = {
    BirthModelId.LISTING_OPEN: BirthBasis.LISTING_OPEN,
    BirthModelId.LISTING_CLOSE: BirthBasis.FIRST_TRADE,      # 首日收盘"视作首日真实落锚时刻"
    BirthModelId.IPO_DATE_APPROX: BirthBasis.IPO_DATE,
    BirthModelId.COMPANY_FOUNDATION: BirthBasis.COMPANY_FOUNDATION,
}

VERSION_SUFFIX: dict[BirthModelId, str] = {
    BirthModelId.LISTING_OPEN: "v1-phase3b-listing_open",
    BirthModelId.LISTING_CLOSE: "v1-phase3b-listing_close",
    BirthModelId.IPO_DATE_APPROX: "v1-phase3b-ipo_approx",
    BirthModelId.COMPANY_FOUNDATION: "v1-phase3b-company_foundation",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe-version", default=UNIVERSE_VERSION)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with session_scope() as db:
        from src.db.models import StockMasterRow, UniverseMembershipRow
        members = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == args.universe_version,
            )
        ).scalars().all()
        print(f"universe[{args.universe_version}] members: {len(members)}")

        by_code: dict[str, StockMasterRow] = {
            s.stock_code: s
            for s in db.execute(select(StockMasterRow)).scalars().all()
        }

        stats = {"total_possible": 0, "inserted": 0, "updated": 0, "unavailable_skipped": 0}

        for m in members:
            stock = by_code.get(m.stock_code)
            if stock is None or stock.listing_date is None:
                print(f"  [skip] {m.stock_code}: 缺 stock_master 或 listing_date")
                continue

            for mid, basis in MODEL_TO_BASIS.items():
                stats["total_possible"] += 1
                build = build_birth(mid, list_date=stock.listing_date)
                if build.birth_datetime is None:
                    # company_foundation 会走这里 → 跳过落库（保留"不可得"语义）
                    stats["unavailable_skipped"] += 1
                    continue

                version = VERSION_SUFFIX[mid]
                existing = db.execute(
                    select(StockBirthProfileRow).where(
                        StockBirthProfileRow.stock_code == stock.stock_code,
                        StockBirthProfileRow.birth_basis == basis.value,
                        StockBirthProfileRow.birth_profile_version == version,
                    )
                ).scalars().first()

                evidence = BirthProfileEvidence(
                    listing_date=stock.listing_date,
                    first_trading_day=build.birth_datetime.date(),
                    session_name="continuous_trading",
                    session_open_time="09:30:00",
                    timezone="Asia/Shanghai",
                    derivation=f"[phase3b:{mid.value}] {build.reason}",
                    lookup_key=f"phase3b:{mid.value}",
                )
                assumptions = [
                    Assumption(
                        key=f"birth.{mid.value}",
                        value=build.birth_datetime.isoformat(),
                        reason=build.reason,
                        impact="birth model 是研究假设，不是事实",
                    ).model_dump(mode="json")
                ]
                dq = DataQuality(
                    grade=DataQualityGrade(build.data_quality_grade),
                    score=build.data_quality_score,
                    notes=[build.reason] if build.reason else [],
                ).model_dump(mode="json")

                if existing:
                    existing.birth_datetime = build.birth_datetime.replace(tzinfo=None)
                    existing.evidence_json = evidence.model_dump(mode="json")
                    existing.assumptions_json = assumptions
                    existing.data_quality_json = dq
                    stats["updated"] += 1
                else:
                    db.add(StockBirthProfileRow(
                        stock_code=stock.stock_code,
                        exchange=m.exchange,
                        birth_basis=basis.value,
                        birth_datetime=build.birth_datetime.replace(tzinfo=None),
                        timezone="Asia/Shanghai",
                        source=f"research:{mid.value}",
                        birth_profile_version=version,
                        evidence_json=evidence.model_dump(mode="json"),
                        assumptions_json=assumptions,
                        data_quality_json=dq,
                        variant_mode=VariantMode.NOT_APPLICABLE.value,
                        variant_note="股票无性别；Phase 3B 不启用大运顺逆",
                        ipo_date=stock.listing_date if mid == BirthModelId.IPO_DATE_APPROX else None,
                        company_foundation=None,
                        first_trade=build.birth_datetime.replace(tzinfo=None) if mid == BirthModelId.LISTING_CLOSE else None,
                        custom_datetime=None,
                    ))
                    stats["inserted"] += 1

        if not args.dry_run:
            db.flush()
        print(f"\n股票数: {len(members)}")
        print(f"birth_model × 股票组合: {stats['total_possible']}")
        print(f"  inserted: {stats['inserted']}")
        print(f"  updated:  {stats['updated']}")
        print(f"  unavailable_skipped（未落库，UNAVAILABLE）: {stats['unavailable_skipped']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
