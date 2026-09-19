"""Phase 3A 落库：stocks.csv + bars/*.csv → stock_master / market_bar_daily / universe_memberships。

执行时机：**必须先**完成 ``scripts/phase3_expand_universe.py --yes`` 抓取。

三件事（按顺序）：
1) 重建 ``stock_master`` 中本快照的 100 只股票
   - 删除 ``source="synthetic_demo"`` 的残留（它是 Phase 1 演示遗留，不应留在研究库）
   - 为 Phase 3A 快照里每只股票写一行 ``StockMasterRow``，
     ``source="tencent_hfq_import"``
2) 调 ``offline_importer.import_market_to_db`` 把 ``data/import/bars/*.csv`` 落到
   ``market_bar_daily``（幂等：先 delete 同 code 后 insert）
3) 重建 ``universe_memberships``（``universe_version="v1-phase3a"``）：
   - ``list_date`` = 抓取到的首日
   - ``delist_date`` = NULL（腾讯对退市股返回 param error，结构性不可得）
   - ``delist_source`` = ``NOT_AVAILABLE_FROM_PROVIDER``
   - ``source_snapshot`` = ``_meta.json.fetched_at``

运行方法：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_import_to_db.py
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select  # noqa: E402

from src.db.base import init_db, session_scope  # noqa: E402
from src.db.models import (  # noqa: E402
    MarketBarDailyRow,
    StockMasterRow,
    UniverseMembershipRow,
)
from src.market.offline_importer import IMPORT_SOURCE_TAG, import_market_to_db  # noqa: E402

IMPORT_DIR = ROOT / "data" / "import"
UNIVERSE_VERSION = "v1-phase3a"


def _read_stocks_csv() -> list[dict]:
    path = IMPORT_DIR / "stocks.csv"
    if not path.exists():
        raise FileNotFoundError(f"缺少 {path}，先运行 scripts/phase3_expand_universe.py")
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _read_meta() -> dict:
    meta_path = IMPORT_DIR / "_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"缺少 {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. 重建 stock_master
# ---------------------------------------------------------------------------

def rebuild_stock_master(stocks: list[dict]) -> dict:
    init_db()
    stats = {"cleared_synthetic": 0, "upserted": 0, "rows_total_after": 0}
    valid_codes = {s["stock_code"] for s in stocks}
    with session_scope() as db:
        # 1) 清掉 Phase 1 残留的 synthetic_demo 行
        for row in db.execute(select(StockMasterRow)).scalars().all():
            if row.source == "synthetic_demo" and row.stock_code not in valid_codes:
                db.delete(row)
                stats["cleared_synthetic"] += 1
        db.flush()

        # 2) upsert 100 股真实档案
        from src.core.stock import codes

        for s in stocks:
            code = s["stock_code"]
            _c, exchange, board, wind = codes.parse(code)
            row = db.execute(
                select(StockMasterRow).where(StockMasterRow.stock_code == code)
            ).scalars().first()
            listing = date.fromisoformat(s["listing_date"]) if s.get("listing_date") else None
            if row is None:
                row = StockMasterRow(
                    stock_code=code,
                    wind_code=wind,
                    name=s.get("name", ""),
                    exchange=str(exchange) if exchange else s.get("exchange", ""),
                    board=board or s.get("board", ""),
                    industry=s.get("industry", ""),
                    listing_date=listing,
                    source=IMPORT_SOURCE_TAG,
                )
                db.add(row)
            else:
                row.wind_code = wind
                row.name = s.get("name", "")
                row.exchange = str(exchange) if exchange else s.get("exchange", "")
                row.board = board or s.get("board", "")
                row.industry = s.get("industry", "")
                row.listing_date = listing
                row.source = IMPORT_SOURCE_TAG
            stats["upserted"] += 1
        db.flush()

        stats["rows_total_after"] = db.execute(select(StockMasterRow)).scalars().all().__len__()
    return stats


# ---------------------------------------------------------------------------
# 2. 重建 universe_memberships
# ---------------------------------------------------------------------------

def rebuild_universe_memberships(stocks: list[dict], meta: dict) -> dict:
    stats = {"replaced_version": UNIVERSE_VERSION, "rows_written": 0, "cleared_prior": 0}
    snapshot_label = f"{meta.get('provider','tencent_ifzq_gtimg')}@{meta.get('fetched_at_phase3a') or meta.get('fetched_at','')}"
    with session_scope() as db:
        # 幂等：先删同 version
        res = db.execute(delete(UniverseMembershipRow).where(
            UniverseMembershipRow.universe_version == UNIVERSE_VERSION
        ))
        stats["cleared_prior"] = res.rowcount or 0

        for s in stocks:
            list_d = date.fromisoformat(s["listing_date"])
            db.add(UniverseMembershipRow(
                universe_version=UNIVERSE_VERSION,
                stock_code=s["stock_code"],
                exchange=s.get("exchange", ""),
                board=s.get("board", ""),
                list_date=list_d,
                delist_date=None,
                status="active",
                source=IMPORT_SOURCE_TAG,
                source_snapshot=snapshot_label,
                delist_source="NOT_AVAILABLE_FROM_PROVIDER",
                notes=(
                    "腾讯 K 线端点对退市股返回 param error；本 universe 未包含任何历史退市股票。"
                    "详见 docs/data-coverage-phase3.md §Survivorship Bias"
                ),
            ))
            stats["rows_written"] += 1
        db.flush()
    return stats


# ---------------------------------------------------------------------------
# 3. 验证：读写一致性 + 泄漏硬检查
# ---------------------------------------------------------------------------

def verify(stocks: list[dict]) -> dict:
    from src.research.universe import PointInTimeUniverse

    codes = {s["stock_code"] for s in stocks}
    problems: list[str] = []

    with session_scope() as db:
        # a) 每只股票在 market_bar_daily 中必须有行
        for code in codes:
            cnt = db.execute(
                select(MarketBarDailyRow).where(MarketBarDailyRow.stock_code == code)
            ).scalars().first()
            if cnt is None:
                problems.append(f"market_bar_daily 缺少 {code}")

        # b) universe_memberships 必须覆盖全部 stocks.csv
        um_codes = set()
        for row in db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION
            )
        ).scalars().all():
            um_codes.add(row.stock_code)
        missing = codes - um_codes
        extra = um_codes - codes
        if missing:
            problems.append(f"universe_memberships 缺: {sorted(missing)}")
        if extra:
            problems.append(f"universe_memberships 多: {sorted(extra)}")

        # c) PIT 语义硬断言：任何股票不得出现在 list_date 之前的 universe 里
        uni = PointInTimeUniverse.load(db, UNIVERSE_VERSION)
        # 抽 5 个时间点硬断言
        min_list = min(s.list_date for s in uni.list_all_members())
        test_days = [
            min_list,
            min_list.replace(year=min_list.year + 1) if min_list.year < 2024 else min_list,
            date(2010, 6, 30),
            date(2015, 6, 30),
            date(2020, 6, 30),
            date.today(),
        ]
        for d in test_days:
            snap = uni.at(d)
            # Survivorship bias warning 一定要出现（本 universe 就是不含退市股）
            kinds = {w.kind for w in snap.warnings}
            if "SURVIVORSHIP_BIAS_WARNING" not in kinds:
                problems.append(f"as_of={d} 缺少 SURVIVORSHIP_BIAS_WARNING")
            # 所有出现在 snap 中的股票必须满足 list_date <= as_of
            for m in snap.members:
                if m.list_date > d:
                    problems.append(f"泄漏: {m.stock_code} list={m.list_date} 出现在 as_of={d}")

    return {
        "stock_master": None,  # 由调用方填
        "universe_memberships": None,
        "problems": problems,
        "defensible": not problems,
    }


def main() -> int:
    stocks = _read_stocks_csv()
    meta = _read_meta()
    print(f"载入 {len(stocks)} 只股票", flush=True)
    print(f"_meta.fetched_at         = {meta.get('fetched_at')}", flush=True)
    print(f"_meta.fetched_at_phase3a = {meta.get('fetched_at_phase3a')}", flush=True)

    # 2: stock_master
    sm_stats = rebuild_stock_master(stocks)
    print(f"stock_master: 清除 synthetic={sm_stats['cleared_synthetic']}  "
          f"upsert={sm_stats['upserted']}  total={sm_stats['rows_total_after']}", flush=True)

    # 3: market_bar_daily（幂等导库）
    result = import_market_to_db()
    if result["errors"]:
        print("market_bar_daily 导入失败：", result["errors"], flush=True)
        return 2
    print(f"market_bar_daily: written_rows={result['rows_written']}  "
          f"series={result['series_written']}  snapshot={result['snapshot_fetched_at']}", flush=True)

    # 4: universe_memberships
    um_stats = rebuild_universe_memberships(stocks, meta)
    print(f"universe_memberships[{um_stats['replaced_version']}]: "
          f"cleared={um_stats['cleared_prior']}  written={um_stats['rows_written']}", flush=True)

    # 5: 验证
    report = verify(stocks)
    print("验证: defensible =", report["defensible"], flush=True)
    if report["problems"]:
        for p in report["problems"][:20]:
            print("  -", p, flush=True)
    return 0 if report["defensible"] else 3


if __name__ == "__main__":
    sys.exit(main())
