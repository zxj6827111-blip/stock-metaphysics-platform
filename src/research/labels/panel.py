"""研究用标签面板构建（Phase 3D 起为唯一入口）。

为什么单独一个模块
------------------
Phase 3D 的标签构建最初写在 ``scripts/phase3d_oos_pipeline.py`` 里。Phase 3E/3F
必须读取**完全同一份**标签（同一行情来源、同一复权因子快照、同一标签口径），
否则中性化/多重检验的结果无法与 3D 对齐。把构建逻辑放在研究层而不是脚本里，
3D/3E/3F 共用一份实现，避免"两次构建、两个口径"。

纪律
----
* 行情只取 ``source = astockdata_composite_none``（ADR-0012 canonical，不复权原始价）。
* 复权因子来自 TuShare ``adj_factor`` 快照并集（主快照 + 退市补丁）；
  缺因子的股票**不静默按 1.0 处理**——``compute_forward_returns`` 会逐行统计
  ``uncovered_rows`` 并写入 meta，由调用方决定是否披露。
* 标签可以读 ``as_of`` 之后的数据（这是标签模块的合法特权）；
  **特征侧不得**使用本模块的输出。
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from src.db.base import get_session_factory
from src.db.models import MarketBarDailyRow
from src.research.labels.horizon_returns import (
    DEFAULT_BENCHMARK_CODE,
    HORIZONS,
    BenchmarkSeries,
    compute_forward_returns,
    label_frame,
)

#: canonical 行情来源（ADR-0012）
BAR_SOURCE = "astockdata_composite_none"
#: 基准代码（沪深 300；本项目唯一可得的宽基基准）
BENCHMARK_CODE = "IDX000300"
#: ADJ_FACTOR 快照（主 + 退市补丁；并集覆盖全部 500 只）
ADJ_SNAPSHOTS: tuple[str, ...] = (
    "tsfactor_20260731T221443_49624041",
    "tsfactor_20260806T110553_91dc1a9e",
)
#: TuShare adj_factor 快照根目录（可用环境变量覆盖）
ASTOCKDATA_FACTOR_ROOT = Path(
    os.environ.get("SMP_ASTOCKDATA_ROOT", r"E:\AStockData")
) / "factors" / "tushare" / "adj_factor"


def adj_factor_index(root: Path = ASTOCKDATA_FACTOR_ROOT) -> dict[str, Path]:
    """``stock_code -> adj_factor csv``（主快照优先，退市补丁兜底）。"""
    index: dict[str, Path] = {}
    for snapshot in reversed(ADJ_SNAPSHOTS):  # 先写补丁，再被主快照覆盖
        directory = root / snapshot
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            code = path.stem.split(".")[0]
            index[code] = path
    return index


def load_adj_factors(
    code: str, index: dict[str, Path], cache: dict[str, pd.DataFrame | None],
) -> pd.DataFrame | None:
    """读取一只股票的除权因子（``trade_date`` / ``factor``）；缺失返回 None。"""
    if code in cache:
        return cache[code]
    path = index.get(code)
    if path is None:
        cache[code] = None
        return None
    frame = pd.read_csv(path, dtype={"trade_date": str, "adj_factor": float})
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d")
    frame = frame.rename(columns={"adj_factor": "factor"})[["trade_date", "factor"]]
    cache[code] = frame
    return frame


def load_bars_by_code(codes: list[str]) -> dict[str, pd.DataFrame]:
    """批量读取 canonical 日线（``trade_date`` / ``close`` / ``is_degraded``）。"""
    factory = get_session_factory()
    out: dict[str, pd.DataFrame] = {}
    with factory() as db:
        for start in range(0, len(codes), 100):
            chunk = codes[start:start + 100]
            rows = db.execute(
                select(
                    MarketBarDailyRow.stock_code, MarketBarDailyRow.trade_date,
                    MarketBarDailyRow.close, MarketBarDailyRow.volume,
                    MarketBarDailyRow.amount,
                    MarketBarDailyRow.is_degraded,
                ).where(
                    MarketBarDailyRow.stock_code.in_(chunk),
                    MarketBarDailyRow.source == BAR_SOURCE,
                ).order_by(MarketBarDailyRow.stock_code, MarketBarDailyRow.trade_date)
            ).all()
            frame = pd.DataFrame(
                rows,
                columns=[
                    "stock_code", "trade_date", "close", "volume", "amount", "is_degraded",
                ],
            )
            for code, group in frame.groupby("stock_code", sort=False):
                out[str(code)] = group.reset_index(drop=True)
    return out


def load_benchmark(code: str = BENCHMARK_CODE) -> BenchmarkSeries:
    """读取基准指数序列（价格指数，不做复权）。"""
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(MarketBarDailyRow.trade_date, MarketBarDailyRow.close).where(
                MarketBarDailyRow.stock_code == code
            ).order_by(MarketBarDailyRow.trade_date)
        ).all()
    frame = pd.DataFrame(rows, columns=["trade_date", "close"])
    return BenchmarkSeries.from_frame(frame, code=DEFAULT_BENCHMARK_CODE)


def build_label_panel(
    bars: dict[str, pd.DataFrame],
    sample_dates: list[date],
    *,
    adj_root: Path = ASTOCKDATA_FACTOR_ROOT,
) -> tuple[pd.DataFrame, dict]:
    """对全部 (股票 × as_of) 计算未来收益标签。

    Returns:
        ``(labels, meta)``；``labels`` 每行一个 ``(stock_code, as_of)``，
        ``meta`` 含复权覆盖率、降级行情清单与逐股票诊断（用于报告披露）。
    """
    index = adj_factor_index(adj_root)
    factor_cache: dict[str, pd.DataFrame | None] = {}
    benchmark = load_benchmark()
    rows: list[dict] = []
    coverage_totals: Counter = Counter()
    per_code: list[dict] = []
    for code, frame in bars.items():
        coverage: dict = {}
        produced = compute_forward_returns(
            frame, sample_dates, stock_code=code, horizons=HORIZONS,
            adj_factors=load_adj_factors(code, index, factor_cache),
            benchmark=benchmark,
            is_degraded=bool(frame["is_degraded"].any()),
            coverage_out=coverage,
        )
        rows.extend(produced)
        for key in ("raw_rows", "matched_rows", "filled_rows", "uncovered_rows"):
            coverage_totals[key] += int(coverage.get(key, 0))
        per_code.append({
            "stock_code": code,
            "label_rows": len(produced),
            "adj_raw_rows": coverage.get("raw_rows", 0),
            "adj_matched_rows": coverage.get("matched_rows", 0),
            "adj_filled_rows": coverage.get("filled_rows", 0),
            "adj_uncovered_rows": coverage.get("uncovered_rows", 0),
            "adj_source": "missing" if code not in index else "provided",
            "has_degraded_bars": bool(frame["is_degraded"].any()),
        })
    labels = label_frame(rows)
    if not labels.empty:
        labels["as_of"] = pd.to_datetime(labels["as_of"]).dt.date
        labels["trade_date"] = pd.to_datetime(labels["trade_date"]).dt.date
    meta = {
        "label_version": str(labels["label_version"].iloc[0]) if not labels.empty else "",
        "benchmark_code": BENCHMARK_CODE,
        "bar_source": BAR_SOURCE,
        "adj_snapshots": list(ADJ_SNAPSHOTS),
        "adj_factor_files": len(index),
        "codes_with_adj": sum(1 for code in bars if code in index),
        "codes_without_adj": sum(1 for code in bars if code not in index),
        "coverage_totals": dict(coverage_totals),
        "per_code": per_code,
        "label_rows": int(len(labels)),
        "degraded_codes": sorted(
            code for code, frame in bars.items() if bool(frame["is_degraded"].any())
        ),
    }
    return labels, meta


__all__ = [
    "ADJ_SNAPSHOTS",
    "ASTOCKDATA_FACTOR_ROOT",
    "BAR_SOURCE",
    "BENCHMARK_CODE",
    "adj_factor_index",
    "build_label_panel",
    "load_adj_factors",
    "load_bars_by_code",
    "load_benchmark",
]
