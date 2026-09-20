"""Phase 4C · 建设全量 universe（``v4-full``）与 stock_master。

与 Phase 3A 的关系（**只新增，不修改**）
----------------------------------------
``v2-phase3a``（500 只，含 333 退市股）是 Phase 3 全部结论的可复现基础，
**本脚本绝不触碰它**。Phase 4 另建一个版本：

    v4-full = 供应商全市场（5,796 只在市，含逐日估值）
            + AStockData 退市补丁（308 只供应商没有的退市股）

实测并集 **6,104 只 / 17,171,780 行**（``data/vendor/daily_bars.parquet``）。
其中 5,796 只有估值字段，308 只退市股只有 OHLCV。

字段来源
--------
* ``list_date``：供应商首个交易日；退市股用 AStockData manifest 的 ``first_date``
* ``delist_date``：退市股用 AStockData manifest 的 ``last_date``；在市股为 NULL
  （NULL 的含义是"截至本快照仍在市"，**不等于永不退市** —— 与 Phase 3A 同口径）
* ``board``：优先取 TuShare PIT 注册簿；注册簿没有的留空字符串（**不猜测**）
* ``industry``：**不可得**，一律留空（Phase 3 已确认无来源，不伪造）

与 Phase 3A 的 ``v2-phase3a`` 的差异必须写进报告：本 universe 的
**估值字段只覆盖在市部分**，退市股的 size/value 为 NaN。

用法::

    python scripts/phase4_build_universe.py --dry-run
    python scripts/phase4_build_universe.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.db.base import session_scope  # noqa: E402
from src.db.models import StockMasterRow, UniverseMembershipRow  # noqa: E402
from src.market.providers.vendor_parquet import (  # noqa: E402
    DELISTED_SOURCE_NAME,
    VENDOR_DATA_VERSION,
    VendorParquetProvider,
)

#: Phase 4 的全量 universe 版本号（与 v2-phase3a 并存）
UNIVERSE_VERSION_V4 = "v4-full"
#: 数据来源标识
SOURCE_FULL = "vendor_full_market_phase4"
#: PIT 注册簿（提供 board；只有 board/list_status，无行业）
PIT_UNIVERSE_PATH = Path(
    r"E:\AStockData\datasets\market_data\universes"
    r"\pit_universe_1d_20260717_bdd82bb209bd.json"
)
VENDOR_DIR = ROOT / "data" / "vendor"
OUT_REPORT = ROOT / "data" / "phase4_universe_report.json"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_pit_board() -> dict[str, str]:
    """``股票代码 -> board``（TuShare PIT 注册簿；没有则不在字典里）。"""
    if not PIT_UNIVERSE_PATH.is_file():
        log(f"PIT 注册簿不存在，board 一律留空：{PIT_UNIVERSE_PATH}")
        return {}
    payload = json.loads(PIT_UNIVERSE_PATH.read_text(encoding="utf-8"))
    board: dict[str, str] = {}
    for entry in payload.get("entries", []):
        code = str(entry.get("ts_code", "")).split(".")[0]
        if code:
            board[code] = str(entry.get("board", "") or "")
    return board


def build_rows(
    catalog,  # type: ignore[no-untyped-def]
    pit_board: dict[str, str],
) -> list[dict]:
    rows: list[dict] = []
    for _index, entry in catalog.iterrows():
        code = str(entry["stock_code"])
        source = str(entry.get("source", ""))
        first = entry.get("first_date")
        last = entry.get("last_date")
        is_delisted = source == DELISTED_SOURCE_NAME
        rows.append({
            "stock_code": code,
            "exchange": str(entry.get("exchange", "") or ""),
            "board": pit_board.get(code, ""),
            "list_date": first.date() if hasattr(first, "date") else first,
            "delist_date": (
                (last.date() if hasattr(last, "date") else last) if is_delisted else None
            ),
            "status": "delisted" if is_delisted else "active",
            "has_valuation": bool(entry.get("has_valuation", False)),
            "row_count": int(entry.get("rows", 0) or 0),
            "source": source,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4C 全量 universe 建设")
    parser.add_argument("--vendor-dir", default=str(VENDOR_DIR))
    parser.add_argument("--universe-version", default=UNIVERSE_VERSION_V4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    started = time.time()
    provider = VendorParquetProvider(Path(args.vendor_dir))
    catalog = provider.catalog()
    log(f"供应商目录：{len(catalog):,} 只（有估值 {int(catalog.has_valuation.sum()):,}）")
    pit_board = load_pit_board()
    log(f"PIT 注册簿 board 覆盖：{len(pit_board):,} 只")

    rows = build_rows(catalog, pit_board)
    missing_list = [r for r in rows if r["list_date"] is None]
    delisted = [r for r in rows if r["status"] == "delisted"]
    active = [r for r in rows if r["status"] == "active"]
    board_known = [r for r in rows if r["board"]]
    report = {
        "phase": "4C",
        "generated_at": datetime.now().isoformat(),
        "vendor_data_version": VENDOR_DATA_VERSION,
        "universe_version": args.universe_version,
        "counts": {
            "total": len(rows),
            "active": len(active),
            "delisted": len(delisted),
            "with_valuation": int(sum(1 for r in rows if r["has_valuation"])),
            "without_valuation": int(sum(1 for r in rows if not r["has_valuation"])),
            "board_known": len(board_known),
            "listing_date_missing": len(missing_list),
        },
        "sources": {"full_market": SOURCE_FULL, "delisted": DELISTED_SOURCE_NAME},
        "notes": [
            "v4-full 与 v2-phase3a 并存；Phase 3 结论仍锚定 v2-phase3a（500 只）。",
            "退市股只有 OHLCV → size/value 暴露为 NaN（不得用 0 冒充）。",
            "industry 不可得，一律留空；board 取 TuShare PIT 注册簿，缺失留空不猜测。",
            "delist_date 为 NULL 表示『截至快照仍在市』，不等于永不退市。",
        ],
        "listing_date_missing_sample": [r["stock_code"] for r in missing_list[:20]],
    }
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"统计：{report['counts']}")

    if args.dry_run:
        log("dry-run：未写库")
        return 0

    with session_scope() as db:
        existing_master = {
            row.stock_code: row for row in db.execute(select(StockMasterRow)).scalars().all()
        }
        master_added = master_updated = master_repaired = 0
        for row in rows:
            if row["list_date"] is None:
                continue
            current = existing_master.get(row["stock_code"])
            if current is None:
                master_added += 1
                db.add(StockMasterRow(
                    stock_code=row["stock_code"],
                    wind_code="",
                    name="",
                    exchange=row["exchange"],
                    board=row["board"],
                    industry="",
                    listing_date=row["list_date"],
                    is_active=row["status"] == "active",
                    source=SOURCE_FULL,
                ))
                continue
            # 已存在但**缺上市日期**的行必须补上：
            # 这类行来自运行时 provider 的兜底（source=code_prefix_only，无上市日），
            # 会让出生档案构造直接失败（002008 就是这种情况）。
            if current.listing_date is None:
                current.listing_date = row["list_date"]
                current.exchange = row["exchange"] or current.exchange
                current.board = row["board"] or current.board
                current.source = SOURCE_FULL
                master_repaired += 1
            else:
                master_updated += 1
        db.flush()
        log(
            f"stock_master：新增 {master_added}，补上市日期 {master_repaired}，"
            f"已存在且完整 {master_updated}"
        )

        prior = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == args.universe_version,
            )
        ).scalars().all()
        for row in prior:
            db.delete(row)
        db.flush()
        log(f"清理旧 {args.universe_version}：{len(prior)} 行")

        written = 0
        for row in rows:
            if row["list_date"] is None:
                continue
            db.add(UniverseMembershipRow(
                universe_version=args.universe_version,
                stock_code=row["stock_code"],
                exchange=row["exchange"],
                board=row["board"],
                list_date=row["list_date"],
                delist_date=row["delist_date"],
                status=row["status"],
                source=row["source"],
                source_snapshot=VENDOR_DATA_VERSION,
                delist_source=(
                    "astockdata_delisted_complement" if row["status"] == "delisted" else ""
                ),
                notes=(
                    f"has_valuation={row['has_valuation']};rows={row['row_count']};"
                    f"phase=4C"
                ),
            ))
            written += 1
        db.flush()
        log(f"universe_memberships[{args.universe_version}]：写入 {written} 行")

    _ = settings  # 保持导入以便未来写入 config_version
    log(f"完成，用时 {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
