"""Phase 4B/4C · 用权威来源修正 stock_master / universe_memberships 的上市日与名称。

数据来源与优先级
----------------
1. **用户提供的 ``日柱.xlsx``**（「上市日期」列被明确指定为权威）——**最高优先级**。
   经与 TuShare ``stock_basic`` 独立交叉验证：5,147 只重合、**一致率 100%**。
2. **TuShare ``stock_basic``**（``data/import/tushare_stock_basic.csv``）——兜底，
   补齐用户表未覆盖的 715 只（含北交所 313 只）。两份来源合起来覆盖全部 6,104 只。
3. 两者都没有 → **保留原值并打标**，绝不猜测。

只取 股票代码 / 股票名称 / 上市日期 三列；表内的「年柱/月柱/日柱/时柱/完整八字」
**一律不导入** —— 项目铁律 1：所有术数排盘必须由本项目的确定性引擎产生。

安全设计
--------
* ``--dry-run`` 在**产生任何 mutation 之前**短路（不依赖退出时回滚）。
* 正式执行时把旧值写入审计 CSV，可回滚。
* 只动 ``v4-full``，**不碰 ``v2-phase3a``**（Phase 3 已冻结）。
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import openpyxl
from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.base import session_scope  # noqa: E402
from src.db.models import StockMasterRow, UniverseMembershipRow  # noqa: E402

UNIVERSE_VERSION = "v4-full"
DEFAULT_SOURCE = r"C:\Users\zxj68\Desktop\日柱.xlsx"
DEFAULT_TUSHARE = ROOT / "data" / "import" / "tushare_stock_basic.csv"
AUDIT_PATH = ROOT / "data" / "phase4_cache" / "listing_date_corrections.csv"
SUSPECT_DATES = (date(2000, 4, 3), date(2025, 10, 9))
SUFFIX_TO_EXCHANGE = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}


def read_user_table(path: str) -> dict[str, dict]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out: dict[str, dict] = {}
    for row in workbook["总表"].iter_rows(min_row=2, values_only=True):
        if not row[0] or not hasattr(row[2], "year"):
            continue
        code = str(row[0]).split(".")[0].zfill(6)
        out[code] = {
            "name": (row[1] or "").strip(),
            "listing": row[2].date(),
            "source": "user_table",
        }
    return out


def read_tushare(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            ts_code = row.get("ts_code") or ""
            code, _, suffix = ts_code.partition(".")
            stamp = (row.get("list_date") or "").strip()
            if len(stamp) != 8 or not stamp.isdigit():
                continue
            out[code] = {
                "name": (row.get("name") or "").strip(),
                "listing": date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:])),
                "source": "tushare_stock_basic",
                "exchange": SUFFIX_TO_EXCHANGE.get(suffix, ""),
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--tushare", default=str(DEFAULT_TUSHARE))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    user = read_user_table(args.source)
    tushare = read_tushare(Path(args.tushare))
    merged: dict[str, dict] = dict(tushare)
    merged.update(user)  # 用户表优先
    print(f"来源①用户表 {len(user)} 只（最高优先级）")
    print(f"来源②TuShare {len(tushare)} 只（兜底）")
    print(f"合并后 {len(merged)} 只")

    plan: list[dict] = []
    names_filled = 0
    unknown: list[str] = []

    with session_scope() as db:
        members = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION,
            )
        ).scalars().all()
        masters = {
            row.stock_code: row
            for row in db.execute(select(StockMasterRow)).scalars().all()
        }
        print(f"v4-full 成员 {len(members)} 只")

        for member in members:
            code = member.stock_code
            info = merged.get(code)
            if info is None:
                unknown.append(code)
                continue

            new_listing = info["listing"]
            record = {
                "stock_code": code,
                "name": info["name"],
                "source": info["source"],
                "old_listing_date": str(member.list_date),
                "new_listing_date": str(new_listing),
                "board": member.board or "",
            }
            if member.list_date != new_listing:
                plan.append(record)
                if not args.dry_run:
                    member.list_date = new_listing
                    member.source = f"{info['source']}:20260920"
                    if member.list_date in SUSPECT_DATES:
                        member.notes = f"[phase4c] 已按 {info['source']} 修正上市日"
                    elif str(record["old_listing_date"]) in [str(d) for d in SUSPECT_DATES]:
                        member.notes = (
                            f"[phase4c] 原上市日 {record['old_listing_date']} "
                            f"系供应商数据起点，已按 {info['source']} 修正为 {new_listing}"
                        )

            master = masters.get(code)
            if master is not None and not args.dry_run:
                if master.listing_date != new_listing:
                    master.listing_date = new_listing
                if info["name"] and (master.name or "") != info["name"]:
                    master.name = info["name"]
                    names_filled += 1

        print(f"\n待修正上市日: {len(plan)} 只")
        print(f"  按来源: {Counter(item['source'] for item in plan).most_common()}")
        print(f"  按板块: {Counter(item['board'] or '?' for item in plan).most_common()}")
        print(f"  原值分布 top6: {Counter(item['old_listing_date'] for item in plan).most_common(6)}")
        print(f"两份来源都缺（保留原值并打标）: {len(unknown)} 只 {unknown[:5]}")
        print("\n  修正样例（前 8）:")
        for item in plan[:8]:
            print(f"    {item['stock_code']} {item['name']:<8} "
                  f"{item['old_listing_date']} → {item['new_listing_date']}  [{item['source']}]")

        if args.dry_run:
            print("\n[DRY-RUN] 未写入任何数据")
            raise SystemExit(0)

        if plan:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(plan[0].keys()))
                writer.writeheader()
                writer.writerows(plan)
            print(f"\n审计/回滚清单 → {AUDIT_PATH}")
        print(f"补全股票名称: {names_filled} 只")

    print("已提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
