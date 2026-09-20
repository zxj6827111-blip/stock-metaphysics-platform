"""Phase 3E · 风格暴露（size / momentum / volatility / value）。

为什么需要它
------------
"事件集合的未来超额收益为正"可能只是**风格暴露**的另一种说法：高动量、低波动、
大市值的股票本来就在某些样本里跑赢。要判断术数事件是否携带**独立于风格**的信息，
必须先把风格暴露量化出来，再在控制它之后重估效应。

可得性（2026-09-20 实测，不得伪造）
-----------------------------------
================  ==========================================================
维度               状态
================  ==========================================================
size（真实市值）    **不可得**：canonical 快照只有 OHLCV，没有总股本 / 流通股本，
                   也没有 ``daily_basic`` 一类的基本面表 → ``MARKET_CAP_UNAVAILABLE``。
                   本模块退化为**流动性规模代理**（trailing 20 日均成交额的对数），
                   显式标记 ``SIZE_PROXY_LIQUIDITY_AMOUNT`` —— 它是 proxy，不是市值。
momentum          **可得**：trailing 60 / 120 个交易日累计收益（复权价）。
volatility        **可得**：trailing 20 / 60 个交易日日对数收益标准差。
value（PE/PB 等）   **不可得**：没有 PIT 基本面 → ``VALUE_FACTOR_UNAVAILABLE``。
================  ==========================================================

防泄漏
------
所有暴露都在 ``trade_date <= as_of`` 的 bar 上计算（窗口末端 = as_of 当日或之前
的最后一个交易日）。``tests/research/test_style_exposures.py`` 用"改写 as_of 之后
的 bar 后暴露必须保持不变"的硬断言验证这一点 —— 不是靠人工检查。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.research.labels.horizon_returns import align_adj_factor

#: 暴露口径版本（改动窗口/算法必须提升）
EXPOSURE_VERSION = "phase3e-exposures-v1"
#: momentum 窗口（交易日）
MOMENTUM_WINDOWS: tuple[int, ...] = (60, 120)
#: volatility 窗口（交易日）
VOLATILITY_WINDOWS: tuple[int, ...] = (20, 60)
#: 流动性规模代理的窗口（交易日）
SIZE_PROXY_WINDOW = 20

#: 显式不可用状态（不是 0，不是 NaN 静默）
MARKET_CAP_UNAVAILABLE = "MARKET_CAP_UNAVAILABLE"
VALUE_FACTOR_UNAVAILABLE = "VALUE_FACTOR_UNAVAILABLE"
#: 已实现的代理口径标记
SIZE_PROXY_LIQUIDITY_AMOUNT = "SIZE_PROXY_LIQUIDITY_AMOUNT"

#: 全部风格暴露列（可用于中性化的列；value 因不可用而缺席）
STYLE_EXPOSURE_COLUMNS: tuple[str, ...] = (
    "momentum_60d",
    "momentum_120d",
    "volatility_20d",
    "volatility_60d",
    "size_proxy_log_amount_20d",
)
#: 不可用的暴露维度（必须在报告中同时列出，避免"只报告能算的"）
UNAVAILABLE_EXPOSURE_DIMENSIONS: dict[str, str] = {
    "size_market_cap": MARKET_CAP_UNAVAILABLE,
    "value": VALUE_FACTOR_UNAVAILABLE,
}


@dataclass(frozen=True)
class ExposureAvailability:
    """风格暴露可得性记录（写入产物与报告）。"""

    exposure_version: str
    available_columns: tuple[str, ...]
    size_proxy_note: str
    unavailable: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "exposure_version": self.exposure_version,
            "available_columns": list(self.available_columns),
            "size_proxy_note": self.size_proxy_note,
            "unavailable_dimensions": dict(self.unavailable),
            "size_status": SIZE_PROXY_LIQUIDITY_AMOUNT,
            "value_status": VALUE_FACTOR_UNAVAILABLE,
        }


def exposure_availability() -> ExposureAvailability:
    return ExposureAvailability(
        exposure_version=EXPOSURE_VERSION,
        available_columns=STYLE_EXPOSURE_COLUMNS,
        size_proxy_note=(
            "size 使用 trailing 20 日均成交额的对数作为**流动性代理**；"
            "这是 proxy 而不是市值。它衡量的是交易活跃度，"
            "与市值高度相关但不相等，报告与结论都必须按 proxy 解释。"
        ),
        unavailable=dict(UNAVAILABLE_EXPOSURE_DIMENSIONS),
    )


def _last_index_on_or_before(dates: np.ndarray, value: date) -> int:
    """返回最后一个 ``date <= value`` 的下标；全部晚于 value 时返回 -1。"""
    target = np.datetime64(value, "D")
    idx = int(np.searchsorted(dates, target, side="right")) - 1
    return idx


def compute_stock_exposures(
    bars: pd.DataFrame,
    as_ofs: Sequence[date],
    *,
    adj_factors: pd.DataFrame | None = None,
    stock_code: str = "",
) -> list[dict]:
    """对一只股票、一组 ``as_of`` 计算风格暴露（只用 ``as_of`` 当日及之前的 bar）。"""
    if bars.empty:
        return []
    ordered = bars.sort_values("trade_date").reset_index(drop=True)
    date_array = np.asarray(
        pd.to_datetime(ordered["trade_date"]).to_numpy(dtype="datetime64[D]"), dtype="datetime64[D]"
    )
    factor, _stats = align_adj_factor(ordered, adj_factors)
    close = pd.to_numeric(ordered["close"], errors="coerce").to_numpy(dtype=float)
    adj_close = close * factor
    amount = (
        pd.to_numeric(ordered["amount"], errors="coerce").to_numpy(dtype=float)
        if "amount" in ordered.columns
        else np.full(len(ordered), np.nan, dtype=float)
    )

    rows: list[dict] = []
    for as_of in sorted(set(as_ofs)):
        idx = _last_index_on_or_before(date_array, as_of)
        if idx < 0:
            continue
        row: dict = {
            "stock_code": stock_code,
            "as_of": as_of,
            "exposure_version": EXPOSURE_VERSION,
            "bar_index": int(idx),
            "bar_date": pd.Timestamp(date_array[idx]).date(),
        }
        for window in MOMENTUM_WINDOWS:
            key = f"momentum_{window}d"
            start = idx - window
            if start < 0:
                row[key] = None
                continue
            base = adj_close[start]
            value = adj_close[idx]
            if not np.isfinite(base) or not np.isfinite(value) or base == 0:
                row[key] = None
                continue
            row[key] = round(float(value / base - 1.0), 8)

        # 日对数收益：窗口内 window 个收益率需要 window+1 个价格点。
        log_close = np.where(adj_close > 0, np.log(np.where(adj_close > 0, adj_close, 1.0)), np.nan)
        for window in VOLATILITY_WINDOWS:
            key = f"volatility_{window}d"
            start = idx - window
            if start < 0:
                row[key] = None
                continue
            windowed = log_close[start: idx + 1]
            returns = np.diff(windowed)
            returns = returns[np.isfinite(returns)]
            if len(returns) < window:
                row[key] = None
                continue
            row[key] = round(float(returns.std(ddof=1)), 8)

        start = idx - SIZE_PROXY_WINDOW + 1
        key = "size_proxy_log_amount_20d"
        if start < 0:
            row[key] = None
        else:
            windowed_amount = amount[start: idx + 1]
            usable = windowed_amount[np.isfinite(windowed_amount) & (windowed_amount > 0)]
            if len(usable) < SIZE_PROXY_WINDOW:
                row[key] = None
            else:
                row[key] = round(float(np.log1p(usable.mean())), 8)
        row["size_proxy_status"] = SIZE_PROXY_LIQUIDITY_AMOUNT
        row["market_cap_status"] = MARKET_CAP_UNAVAILABLE
        row["value_status"] = VALUE_FACTOR_UNAVAILABLE
        rows.append(row)
    return rows


def build_exposure_panel(
    bars: dict[str, pd.DataFrame],
    as_ofs: Sequence[date],
    *,
    adj_root: Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    """对全部股票 × ``as_of`` 构建风格暴露面板。

    Returns:
        ``(frame, meta)``。``frame`` 里不可用的暴露是 **NaN**（经 DataFrame 化之后
        ``None`` 即 NaN）—— 任何调用方都必须按"缺失"处理，不得填 0；
        ``meta`` 给出逐列覆盖率 —— 低覆盖率必须被看到，而不是被静默忽略。
    """
    from src.research.labels.panel import adj_factor_index, load_adj_factors

    index = adj_factor_index(adj_root) if adj_root is not None else adj_factor_index()
    cache: dict[str, pd.DataFrame | None] = {}
    rows: list[dict] = []
    for code, frame in bars.items():
        rows.extend(
            compute_stock_exposures(
                frame, as_ofs, adj_factors=load_adj_factors(code, index, cache), stock_code=code,
            )
        )
    out = pd.DataFrame(rows)
    meta: dict = {
        "exposure_version": EXPOSURE_VERSION,
        "stock_count": len(bars),
        "row_count": int(len(out)),
        "columns": {},
    }
    if not out.empty:
        for column in STYLE_EXPOSURE_COLUMNS:
            usable = out[column].notna().sum() if column in out.columns else 0
            meta["columns"][column] = {
                "usable": int(usable),
                "missing": int(len(out) - usable),
                "coverage_ratio": round(float(usable) / len(out), 6),
            }
    meta["availability"] = exposure_availability().to_dict()
    return out, meta


def zscore_cross_section(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    date_col: str = "as_of",
) -> pd.DataFrame:
    """按横截面（同一 ``as_of``）做 z-score 标准化；常量截面返回 NaN。

    为什么按横截面标准化：风格暴露的绝对值在 A 股 30 年样本里跨度极大
    （成交额从万元到百亿元），只有**同日相对位置**才是可比的暴露。
    """
    out = frame.copy()
    for column in columns:
        values = pd.to_numeric(out[column], errors="coerce")
        grouped = values.groupby(out[date_col])
        mean = grouped.transform("mean")
        std = grouped.transform("std")
        z = (values - mean) / std.where(std > 0)
        out[f"z_{column}"] = z.where(std > 0)
    return out


__all__ = [
    "EXPOSURE_VERSION",
    "MARKET_CAP_UNAVAILABLE",
    "MOMENTUM_WINDOWS",
    "SIZE_PROXY_LIQUIDITY_AMOUNT",
    "SIZE_PROXY_WINDOW",
    "STYLE_EXPOSURE_COLUMNS",
    "UNAVAILABLE_EXPOSURE_DIMENSIONS",
    "VALUE_FACTOR_UNAVAILABLE",
    "VOLATILITY_WINDOWS",
    "ExposureAvailability",
    "build_exposure_panel",
    "compute_stock_exposures",
    "exposure_availability",
    "zscore_cross_section",
]
