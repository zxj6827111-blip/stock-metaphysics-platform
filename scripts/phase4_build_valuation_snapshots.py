"""Phase 4A · 逐日估值 → as_of 快照（PIT 正确性的关键一步）。

为什么不能直接用原始逐日表
--------------------------
研究侧需要的是"**在 as_of 那一天，我们能看到的**每只股票的市值/估值/换手"。
直接用 ``trade_date == as_of`` 会漏掉两类股票：

* as_of 当天停牌的股票（它有更早的估值快照，理应可见）；
* as_of 恰逢非交易日的采样点（Phase 3 的 as_of 是每月 1 日，经常不是交易日）。

正确口径是"**截止 as_of 的最后一条**"（``trade_date <= as_of`` 取最大），
这正是 PIT 的定义。本脚本把 68 个采样点 × 全部股票的这条记录预计算成一张窄表，
研究者只需一次 join，不需要在 1,600 万行上反复做 as-of 连接。

产出
----
    data/vendor/valuation_snapshots.parquet
        as_of / stock_code / trade_date / 各估值与股本市值列 / staleness_days

``staleness_days`` 记录"快照距 as_of 有多少天" —— 停牌越久越大，
报告里可以据此披露数据新鲜度（而不是把停牌股票静默丢弃）。

用法::

    python scripts/phase4_build_valuation_snapshots.py
    python scripts/phase4_build_valuation_snapshots.py --as-of-file data/phase3_universe/phase3d_cache/dates.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market.providers.vendor_parquet import (  # noqa: E402
    VALUATION_FIELDS,
    VendorParquetProvider,
)

VENDOR_DIR = ROOT / "data" / "vendor"
#: 与 Phase 3D 一致的采样网格（季度，2010-01-01..2026-08-14）
DEFAULT_START = "2010-01-01"
DEFAULT_END = "2026-08-14"
DEFAULT_STEP_MONTHS = 3
#: 超过这个天数未更新的快照标记为陈旧（仅为披露，不丢弃）
STALE_DAYS_WARN = 30


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def sample_dates(start: str, end: str, step_months: int) -> list[date]:
    """生成 as_of 网格（每月 1 日 + 终点），与 Phase 3D 的口径一致。"""
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    out: list[date] = []
    current = date(first.year, first.month, 1)
    while current <= last:
        out.append(current)
        index = current.month - 1 + step_months
        current = date(current.year + index // 12, index % 12 + 1, 1)
    if last not in out:
        out.append(last)
    return sorted({value for value in out if first <= value <= last})


def build_snapshots(
    vendor_dir: Path, as_ofs: list[date],
) -> tuple[object, dict]:
    """对每个 as_of 取"截止当日的最后一条估值"，返回长表与诊断。"""
    import duckdb

    path = str(vendor_dir / "daily_valuation.parquet").replace("\\", "/")
    as_of_list = [value.isoformat() for value in as_ofs]
    connection = duckdb.connect()
    sql = f"""
        with grid as (
            select unnest(?::date[]) as as_of
        ),
        joined as (
            select g.as_of, v.stock_code, v.trade_date,
                   {', '.join('v.' + field for field in VALUATION_FIELDS)},
                   date_diff('day', v.trade_date, g.as_of) as staleness_days
            from grid g
            join read_parquet('{path}') v
              on v.trade_date <= g.as_of
        ),
        ranked as (
            select *, row_number() over (
                partition by as_of, stock_code order by trade_date desc
            ) as rn
            from joined
        )
        select * exclude (rn) from ranked where rn = 1 order by as_of, stock_code
    """
    started = time.time()
    frame = connection.execute(sql, [as_of_list]).df()
    log(f"snapshot 查询完成：{len(frame):,} 行，{time.time() - started:.1f}s")
    diagnostics = {
        "as_of_count": len(as_ofs),
        "row_count": int(len(frame)),
        "stock_count": int(frame["stock_code"].nunique()) if len(frame) else 0,
        "rows_with_market_cap": int(frame["total_mv"].notna().sum()) if len(frame) else 0,
        "rows_missing_pe_ttm": int(frame["pe_ttm"].isna().sum()) if len(frame) else 0,
        "stale_rows_over_30d": int((frame["staleness_days"] > STALE_DAYS_WARN).sum())
        if len(frame) else 0,
    }
    return frame, diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4A 估值 as_of 快照")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--step-months", type=int, default=DEFAULT_STEP_MONTHS)
    parser.add_argument("--vendor-dir", default=str(VENDOR_DIR))
    parser.add_argument("--out", default="valuation_snapshots.parquet")
    args = parser.parse_args()

    started = time.time()
    vendor_dir = Path(args.vendor_dir)
    provider = VendorParquetProvider(vendor_dir)  # 先校验仓库完整
    _ = provider
    as_ofs = sample_dates(args.start, args.end, args.step_months)
    log(f"as_of 网格：{len(as_ofs)} 个（{as_ofs[0]} .. {as_ofs[-1]}）")
    log(f"仓库目录：{vendor_dir}")

    frame, diagnostics = build_snapshots(vendor_dir, as_ofs)
    out_path = vendor_dir / args.out
    frame.to_parquet(out_path, index=False, compression="zstd")
    log(f"写入 {out_path}（{out_path.stat().st_size / 1e6:.1f} MB）")

    meta_path = vendor_dir / "valuation_snapshots_meta.json"
    meta_path.write_text(json.dumps({
        "phase": "4A",
        "generated_at": datetime.now().isoformat(),
        "as_of_rule": "截止 as_of 的最后一条估值（trade_date <= as_of 取最大）",
        "grid": {"start": args.start, "end": args.end, "step_months": args.step_months},
        "staleness_warn_days": STALE_DAYS_WARN,
        "diagnostics": diagnostics,
        "notes": [
            "staleness_days 越大表示该股越久没有新的估值行（停牌或退市前），不丢弃、只披露。",
            "退市股在供应商包中不存在 → 这些股票在快照里缺席，size/value 暴露为 NaN。",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"诊断：{diagnostics}")
    log(f"完成，用时 {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
