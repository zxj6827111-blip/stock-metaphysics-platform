"""Phase 4D · 导入上市首日涨跌幅与「阴阳」标识到 stock_master。

口径
----
* ``first_day_pct_chg``：上市首日涨跌幅（来自用户权威表）
* ``first_day_yinyang``：``阳`` = 首日收涨 / ``阴`` = 首日收跌

这两个字段只用于**运限顺逆的显式假设**（本项目按「阳→男命 / 阴→女命」起运）。
股票没有真实性别；``variant_mode`` 默认仍为 ``not_applicable``，不输出大运，
也不进入任何正式因子（AGENTS.md §5）。

同时做**内部一致性校验**：标识必须与涨跌幅符号一致（阳 ⟺ >0，阴 ⟺ <0），
不一致的逐条列出、不写库。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import openpyxl
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.base import session_scope  # noqa: E402
from src.db.models import StockMasterRow  # noqa: E402

DEFAULT_SOURCE = r"C:\Users\zxj68\Desktop\日柱.xlsx"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workbook = openpyxl.load_workbook(args.source, read_only=True, data_only=True)
    parsed: dict[str, tuple[float, str]] = {}
    inconsistent: list[tuple[str, object, str]] = []
    for row in workbook["总表"].iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue
        code = str(row[0]).split(".")[0].zfill(6)
        pct, flag = row[5], (row[6] or "").strip()
        if not isinstance(pct, (int, float)) or flag not in ("阴", "阳"):
            continue
        # 内部一致性：标识必须与涨跌幅符号一致
        expected = "阳" if pct > 0 else ("阴" if pct < 0 else "")
        if expected and flag != expected:
            inconsistent.append((code, pct, flag))
            continue
        parsed[code] = (float(pct), flag)

    print(f"来源：{args.source}")
    print(f"  可解析 {len(parsed)} 只；符号与标识不一致 {len(inconsistent)} 只")
    if inconsistent:
        print("  不一致样例:", inconsistent[:5])
    print("  阴阳分布:", Counter(flag for _p, flag in parsed.values()).most_common())

    updated = 0
    missing = 0
    with session_scope() as db:
        masters = {
            row.stock_code: row
            for row in db.execute(select(StockMasterRow)).scalars().all()
        }
        for code, (pct, flag) in parsed.items():
            master = masters.get(code)
            if master is None:
                missing += 1
                continue
            if args.dry_run:
                continue
            master.first_day_pct_chg = pct
            master.first_day_yinyang = flag
            updated += 1
        print(f"  库内匹配 {len(parsed) - missing} 只（不在 stock_master 的 {missing} 只）")
        if args.dry_run:
            print("\n[DRY-RUN] 未写入任何数据")
            raise SystemExit(0)
        print(f"  已写入 {updated} 只")

    # 写后复核：按阴阳统计，并给出对应的运限假设
    with session_scope() as db:
        rows = db.execute(
            select(StockMasterRow.first_day_yinyang).where(
                StockMasterRow.first_day_yinyang.is_not(None)
            )
        ).scalars().all()
        print("\n复核（库内实际值）:", Counter(rows).most_common())
    print("\n假设映射：阳 → 男命（variant_mode=FORWARD）；阴 → 女命（variant_mode=REVERSE）")
    print("顺逆由「性别 + 年干阴阳」共同决定（阳男阴女顺行、阴男阳女逆行），由引擎自动计算。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
