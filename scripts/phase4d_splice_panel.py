"""Phase 4D · 把局部重算的分片拼回全量面板。

背景：出生档案修正（上市日）后，受影响股票的盘面需要重算。全量重跑要 6 小时，
但面板按股票分片、行与行之间无耦合，因此可以**只重算受影响的那批再拼回去**。

本脚本做的事
------------
1. 读全量面板（``merged_panel.pkl``）与重算面板（``recompute/merged_panel.pkl``）；
2. 校验：重算的股票集合、日期网格、失败数（必须为 0）、每只股票行数不得减少；
3. 用重算行替换这些股票在旧面板里的全部行，写回 ``merged_panel.pkl``；
4. 原始面板备份为 ``merged_panel_pre_resplice.pkl``，并落一份拼合报告。

**预期行数会增加**：上市日修正后，老股在更早的 as_of 上才变得 PIT 可见，
可用行数应当增加。行数**减少**才可疑，会被列为异常。
"""

from __future__ import annotations

import argparse
import pickle
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_BASE = ROOT / "data" / "phase4_cache"
BACKUP_NAME = "merged_panel_pre_resplice.pkl"
REPORT_NAME = "resplice_report.pkl"


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

    # --- 校验 4：每只股票行数不得减少 ---
    before = per_code_counts([r for r in base_rows if str(r["stock_code"]) in replace_codes])
    after = per_code_counts(new_rows)
    decreased = [
        (code, before.get(code, 0), after.get(code, 0))
        for code in sorted(replace_codes)
        if after.get(code, 0) < before.get(code, 0)
    ]
    if decreased:
        problems.append(f"行数减少的股票 {len(decreased)} 只（可疑）：{decreased[:5]}")

    grew = sum(max(0, after.get(c, 0) - before.get(c, 0)) for c in replace_codes)
    print(f"\n替换范围：{len(replace_codes)} 只")
    print(f"  替换前这些股票共 {sum(before.values()):,} 行 → 重算后 {sum(after.values()):,} 行"
          f"（+{grew:,}，来自上市日提前导致的 PIT 可见时点增加）")
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
