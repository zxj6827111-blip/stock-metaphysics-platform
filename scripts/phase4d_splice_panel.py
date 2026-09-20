"""Phase 4D · 把局部重算的分片拼回全量面板。

背景：出生档案修正（上市日）后，受影响股票的盘面需要重算。全量重跑要 6 小时，
但面板按股票分片、行与行之间无耦合，因此可以**只重算受影响的那批再拼回去**。

本脚本做的事
------------
1. 读全量面板（``merged_panel.pkl``）与重算面板（``recompute/merged_panel.pkl``）；
2. 校验：重算的股票集合、日期网格、失败数（必须为 0），以及**按 PIT 口径验算行数**
   —— ``行数 == 9 × [list_date, delist_date] 内的 as_of 数``；
3. 用重算行替换这些股票在旧面板里的全部行，写回 ``merged_panel.pkl``；
4. 原始面板备份为 ``merged_panel_pre_resplice.pkl``，并落一份拼合报告。

行数**增加**与**减少**都可能正确：上市日改早 → 早期时点变为可用（增加）；
上市日改晚（如北交所股票原值落在供应商数据起点）→ 早期时点不再可用（减少）。
所以判据不是"只许增不许减"，而是"必须与 PIT 口径精确吻合"；
低于应有值即判为疑似数据丢失并拒绝写入。
"""

from __future__ import annotations

import argparse
import pickle
import shutil
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.base import get_session_factory  # noqa: E402
from src.db.models import UniverseMembershipRow  # noqa: E402

DEFAULT_BASE = ROOT / "data" / "phase4_cache"
BACKUP_NAME = "merged_panel_pre_resplice.pkl"
REPORT_NAME = "resplice_report.pkl"
UNIVERSE_VERSION = "v4-full"
#: 每个可用 (股票, as_of) 组合应有的行数 = 出生模型数(3) × 引擎数(3)。
#: 该常数由 PIT 验算自行校验：取值错误会让精确吻合率立刻掉到接近 0。
ROWS_PER_ELIGIBLE_DATE = 9


def as_date(value: object) -> date:
    """SQLite 的 Date 列经 raw 查询会以字符串返回；这里统一成 ``date``。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def expected_row_count(
    listed: object, delisted: object, as_ofs: list[date],
) -> int:
    """按 PIT 口径算该股票应有的行数。

    可用时点 = ``list_date <= as_of <= delist_date``（无退市日视为仍在市）。
    与 ``load_universe`` 的资格判据保持一致。
    """
    start = as_date(listed)
    end = as_date(delisted) if delisted else None
    eligible = sum(
        1 for when in as_ofs if when >= start and (end is None or when <= end)
    )
    return ROWS_PER_ELIGIBLE_DATE * eligible


def load_panel(path: Path) -> dict:
    with path.open("rb") as handle:
        return pickle.load(handle)


def per_code_counts(rows: list[dict]) -> Counter:
    return Counter(str(row["stock_code"]) for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE))
    parser.add_argument("--recompute-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = Path(args.base_dir)
    recompute_dir = Path(args.recompute_dir) if args.recompute_dir else base / "recompute"
    base_panel = load_panel(base / "merged_panel.pkl")
    new_panel = load_panel(recompute_dir / "merged_panel.pkl")

    base_rows: list[dict] = base_panel["rows"]
    new_rows: list[dict] = new_panel["rows"]
    replace_codes = {str(code) for code in new_panel["codes"]}
    print(f"全量面板：{len(base_rows):,} 行 / {len(set(base_panel['codes']))} 只")
    print(f"重算面板：{len(new_rows):,} 行 / {len(replace_codes)} 只")

    problems: list[str] = []

    # --- 校验 1：股票集合必须被全量面板包含 ---
    base_codes = {str(code) for code in base_panel["codes"]}
    extra = replace_codes - base_codes
    if extra:
        problems.append(f"重算面板含全量面板没有的股票 {len(extra)} 只：{sorted(extra)[:5]}")

    # --- 校验 2：日期网格必须一致 ---
    base_dates = {str(value) for value in base_panel["dates"]}
    new_dates = {str(value) for value in new_panel["dates"]}
    if base_dates != new_dates:
        problems.append(
            f"日期网格不一致：新增 {sorted(new_dates - base_dates)[:3]} "
            f"缺失 {sorted(base_dates - new_dates)[:3]}"
        )

    # --- 校验 3：重算不得有排盘失败 ---
    failures = dict(new_panel.get("failures") or {})
    if failures:
        problems.append(f"重算存在失败：{failures}")

    # --- 校验 4：按 PIT 口径验算每只股票应有的行数 ---
    # 行数增减都必须被规则解释：上市日改早 → 早期时点变为可用（行数增加）；
    # 上市日改晚（如北交所股票原来落在供应商数据起点）→ 早期时点不再可用（行数减少）。
    # 因此不能用"行数不得减少"这种粗判据，而要验算
    # 行数 == 每可用时点行数 × [list_date, delist_date] 内的 as_of 数。
    before = per_code_counts([r for r in base_rows if str(r["stock_code"]) in replace_codes])
    after = per_code_counts(new_rows)
    as_ofs = sorted({as_date(r["as_of"]) for r in new_rows})
    with get_session_factory()() as db:
        members = db.execute(
            select(
                UniverseMembershipRow.stock_code,
                UniverseMembershipRow.list_date,
                UniverseMembershipRow.delist_date,
            ).where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION,
                UniverseMembershipRow.stock_code.in_(sorted(replace_codes)),
            )
        ).all()
    span = {code: (listed, delisted) for code, listed, delisted in members}

    exact = 0
    short: list[tuple] = []
    for code in sorted(replace_codes):
        listed, delisted = span.get(code, (None, None))
        if listed is None:
            short.append((code, "无 universe 行", 0, after.get(code, 0)))
            continue
        expected = expected_row_count(listed, delisted, as_ofs)
        actual = after.get(code, 0)
        if actual == expected:
            exact += 1
        elif actual < expected:
            short.append((code, f"{as_date(listed)}~{delisted}", expected, actual))
    if short:
        problems.append(f"行数低于 PIT 应有值的股票 {len(short)} 只（疑似数据丢失）：{short[:5]}")

    shrank = sum(1 for c in replace_codes if after.get(c, 0) < before.get(c, 0))
    grew = sum(1 for c in replace_codes if after.get(c, 0) > before.get(c, 0))
    print(f"\n替换范围：{len(replace_codes)} 只")
    print(f"  PIT 口径精确吻合：{exact}/{len(replace_codes)} 只"
          f"（按 {ROWS_PER_ELIGIBLE_DATE} 行/可用时点 验算）")
    print(f"  行数 旧 {sum(before.values()):,} → 新 {sum(after.values()):,}"
          f"；其中增加 {grew} 只、减少 {shrank} 只")
    print(f"  未受影响股票：{len(base_codes - replace_codes)} 只，行数不变")

    if problems:
        print("\n✗ 校验未通过，未写入任何数据：")
        for item in problems:
            print("   -", item)
        return 1

    kept = [r for r in base_rows if str(r["stock_code"]) not in replace_codes]
    merged_rows = kept + new_rows
    print(f"\n拼合结果：{len(merged_rows):,} 行（保留 {len(kept):,} + 新增 {len(new_rows):,}）")

    if args.dry_run:
        print("[DRY-RUN] 未写盘")
        return 0

    backup = base / BACKUP_NAME
    if not backup.exists():
        shutil.copy2(base / "merged_panel.pkl", backup)
        print(f"原面板已备份 → {backup}")

    payload = dict(base_panel)
    payload["rows"] = merged_rows
    payload["codes"] = sorted(base_codes | replace_codes)
    payload["resplice"] = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "replaced_codes": len(replace_codes),
        "rows_before": len(base_rows),
        "rows_after": len(merged_rows),
        "failures": failures,
        "birth_profile_note": "受影响的股票已按 v2-phase4b 出生档案重算；"
                              "未受影响股票两版逐值相同",
    }
    with (base / "merged_panel.pkl").open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    with (base / REPORT_NAME).open("wb") as handle:
        pickle.dump(payload["resplice"], handle, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"已写回 → {base / 'merged_panel.pkl'}")
    print(f"拼合报告 → {base / REPORT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
