"""Phase 4A · 供应商数据落地：年包 ZIP → Parquet 仓库（一次性）。

为什么需要这一步
----------------
供应商数据是"按年打包、每年内每只股票一个 CSV"的结构，读**单只股票的完整历史**
必须扫全部 27 个年包（实测 60 秒/只）。研究侧与 UI 侧都不可能接受这个成本，
因此先做一次全量转换，产出**按 (stock_code, trade_date) 排序**的 Parquet：

    data/vendor/daily_bars.parquet       全市场日线（OHLCV）
    data/vendor/daily_valuation.parquet  逐日估值 / 股本 / 市值（Phase 3 缺的那部分）
    data/vendor/adj_factor.parquet       后复权因子
    data/vendor/_meta.json               来源、快照、行数、代码数与口径说明

**并集口径（重要）**
--------------------
供应商包**不含退市股**（实测 000003/000018/600001/600003 等均缺失）。
为避免把生存者偏差引进来，本脚本把 ``E:\\AStockData`` 的
``internal_delisted_complement``（333 只，仅 OHLCV）**补进同一个 Parquet**，
并给每一行打上来源标记：

    source = vendor_hfq             供应商日 K（有估值）
    source = astockdata_delisted    退市股补丁（无估值 → 估值列为 NaN）

覆盖规则：**同一代码优先用供应商**（它有估值）；供应商没有的代码才用补丁。
两个来源覆盖的代码集合除极少数重叠外互斥，因此不存在"同一只股票两套价格混用"。
退市股的估值列一律为 NaN —— 按项目纪律**不得用 0 冒充**。

用法::

    python scripts/phase4_import_vendor.py                 # 全量
    python scripts/phase4_import_vendor.py --years 2025 2026   # 只跑这两年（冒烟）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market.providers.vendor_zip_store import (  # noqa: E402
    BAR_COLUMNS,
    DEFAULT_VENDOR_ROOT,
    VALUATION_COLUMNS,
    VendorZipStore,
    to_numeric,
)

OUT_DIR = ROOT / "data" / "vendor"
SOURCE_VENDOR = "vendor_hfq"
SOURCE_DELISTED = "astockdata_delisted"
#: 退市股补丁 manifest（AStockData）
DELISTED_MANIFEST = (
    Path(r"E:\AStockData")
    / "datasets/market_data/manifests"
    / "internal_delisted_complement_1d_20260814_b3c980d40194.json"
)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def import_vendor_bars(
    store: VendorZipStore, years: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把年包转成 (行情, 估值) 两个长表。"""
    available = store.years()
    targets = [value for value in available if years is None or value in set(years)]
    if not targets:
        raise SystemExit(f"没有可转换的年包：请求 {years}，实际 {available}")
    bars_parts: list[pd.DataFrame] = []
    value_parts: list[pd.DataFrame] = []
    for year in targets:
        started = time.time()
        raw = store.read_year(year)
        if raw.empty:
            log(f"{year}: 空年包，跳过")
            continue
        frame = to_numeric(raw)
        bars_parts.append(frame[[
            "stock_code", "exchange", "trade_date", *BAR_COLUMNS,
        ]])
        value_parts.append(frame[[
            "stock_code", "trade_date",
            *[c for c in VALUATION_COLUMNS if c in frame.columns],
        ]])
        log(
            f"{year}: rows={len(frame):>7} codes={frame.stock_code.nunique():>5} "
            f"{time.time() - started:.1f}s"
        )
    bars = pd.concat(bars_parts, ignore_index=True)
    valuation = pd.concat(value_parts, ignore_index=True)
    bars["source"] = SOURCE_VENDOR
    # 同一年包内可能有重复（供应商偶发重复行）→ 去重保留最后一条
    bars = bars.drop_duplicates(subset=["stock_code", "trade_date"], keep="last")
    valuation = valuation.drop_duplicates(subset=["stock_code", "trade_date"], keep="last")
    return bars, valuation


def import_delisted_bars(vendor_codes: set[str]) -> pd.DataFrame:
    """把退市股补丁（仅 OHLCV）转成与供应商同构的长表，只保留供应商没有的代码。"""
    from src.market.providers.astockdata_store import AStockDataBlobStore

    if not DELISTED_MANIFEST.is_file():
        log(f"退市股补丁 manifest 不存在，跳过：{DELISTED_MANIFEST}")
        return pd.DataFrame()
    store = AStockDataBlobStore.from_manifest(DELISTED_MANIFEST)
    frames: list[pd.DataFrame] = []
    skipped = 0
    for symbol, entry in store.manifest.symbols.items():
        code = entry.stock_code
        if code in vendor_codes and code not in {"000003"}:
            # 供应商已有该代码 → 不引入第二套价格（除极少数需人工确认的代码外）
            skipped += 1
            continue
        try:
            raw = store.load_bars(symbol)
        except Exception as exc:  # noqa: BLE001 - 单只失败不阻塞全量
            log(f"  退市股 {symbol} 读取失败：{exc}")
            continue
        if raw.empty:
            continue
        frame = raw.rename(columns={"volume": "volume", "amount": "amount"})
        frame["stock_code"] = code
        frame["exchange"] = entry.exchange
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
        for column in ("pre_close", "change", "pct_chg"):
            frame[column] = float("nan")
        frames.append(frame[[
            "stock_code", "exchange", "trade_date", *BAR_COLUMNS,
        ]])
    log(f"退市股补丁：保留 {len(frames)} 只，因供应商已有而跳过 {skipped} 只")
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["source"] = SOURCE_DELISTED
    return out


def import_adj_factors(store: VendorZipStore) -> pd.DataFrame:
    raw = store.read_adj_factors(which="hfq")
    frame = raw.copy()
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"].astype(str), format="%Y%m%d", errors="coerce",
    ).dt.date
    frame["factor"] = pd.to_numeric(frame["factor"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "factor"])
    frame["source"] = SOURCE_VENDOR
    return frame.drop_duplicates(subset=["stock_code", "trade_date"], keep="last")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4A 供应商数据落地")
    parser.add_argument("--vendor-root", default=str(DEFAULT_VENDOR_ROOT))
    parser.add_argument("--years", nargs="*", default=None,
                        help="只转换指定年份（冒烟用）；缺省=全部")
    parser.add_argument("--skip-delisted", action="store_true",
                        help="不并入退市股补丁（只做冒烟）")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()

    started = time.time()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = VendorZipStore(Path(args.vendor_root))
    log(f"供应商根目录：{store.root}")
    log(f"年包：{len(store.years())} 个（{store.years()[0]}..{store.years()[-1]}）")

    bars, valuation = import_vendor_bars(store, args.years)
    log(f"供应商行情：{len(bars):,} 行 / {bars.stock_code.nunique():,} 只")
    log(f"供应商估值：{len(valuation):,} 行")

    delisted = pd.DataFrame()
    if not args.skip_delisted:
        delisted = import_delisted_bars(set(bars.stock_code.unique()))
        if not delisted.empty:
            bars = pd.concat([bars, delisted], ignore_index=True)
            log(f"并集后行情：{len(bars):,} 行 / {bars.stock_code.nunique():,} 只")

    factors = import_adj_factors(store)
    log(f"后复权因子：{len(factors):,} 行 / {factors.stock_code.nunique():,} 只")

    log("写出 Parquet（按 stock_code, trade_date 排序以便行组裁剪）…")
    bars = bars.sort_values(["stock_code", "trade_date"], kind="mergesort")
    bars.to_parquet(out_dir / "daily_bars.parquet", index=False, compression="zstd")
    valuation = valuation.sort_values(["stock_code", "trade_date"], kind="mergesort")
    valuation.to_parquet(out_dir / "daily_valuation.parquet", index=False, compression="zstd")
    factors = factors.sort_values(["stock_code", "trade_date"], kind="mergesort")
    factors.to_parquet(out_dir / "adj_factor.parquet", index=False, compression="zstd")

    meta = {
        "phase": "4A",
        "generated_at": datetime.now().isoformat(),
        "vendor_root": str(store.root),
        "years": store.years() if args.years is None else args.years,
        "source_rules": {
            SOURCE_VENDOR: "供应商全A日K（含逐日估值/股本/市值）",
            SOURCE_DELISTED: "AStockData internal_delisted_complement（仅 OHLCV，估值列为 NaN）",
        },
        "coverage_rule": (
            "同一代码优先用供应商（有估值）；供应商缺失的代码才用退市股补丁。"
            "两来源覆盖集合基本互斥，不存在同一股票两套价格混用。"
        ),
        "rows": {
            "daily_bars": int(len(bars)),
            "daily_valuation": int(len(valuation)),
            "adj_factor": int(len(factors)),
        },
        "codes": {
            "daily_bars": int(bars.stock_code.nunique()),
            "vendor_only": int(bars.loc[bars.source == SOURCE_VENDOR, "stock_code"].nunique()),
            "delisted_only": int(
                bars.loc[bars.source == SOURCE_DELISTED, "stock_code"].nunique()
            ) if not delisted.empty else 0,
        },
        "valuation_coverage": {
            "rows_with_total_mv": int(valuation["total_mv"].notna().sum())
            if "total_mv" in valuation.columns else 0,
            "rows_missing_pe_ttm": int(valuation["pe_ttm"].isna().sum())
            if "pe_ttm" in valuation.columns else 0,
        },
        "date_range": {
            "min": str(bars.trade_date.min()),
            "max": str(bars.trade_date.max()),
        },
        "known_limitations": [
            "供应商包不含退市股；退市股由 AStockData 补丁补齐且**无估值字段**。",
            "退市股的 size/value 暴露一律 NaN（不得用 0 冒充）。",
            "供应商年包快照日期见文件 mtime；本地快照 2026 年包截至 2026-07-17。",
        ],
    }
    (out_dir / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    for name in ("daily_bars", "daily_valuation", "adj_factor"):
        path = out_dir / f"{name}.parquet"
        log(f"  {path.name}: {path.stat().st_size / 1e6:.1f} MB")
    log(f"写入 {out_dir / '_meta.json'}")
    log(f"完成，用时 {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
