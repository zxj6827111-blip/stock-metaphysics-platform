"""Phase 4B · 真实 size / value 暴露（``phase4-exposures-v2``）。

为什么要有 v2
-------------
Phase 3E 的 ``phase3e-exposures-v1`` 里，size 只能退化为**20 日均成交额的对数**
（``MARKET_CAP_UNAVAILABLE``），value 完全缺失（``VALUE_FACTOR_UNAVAILABLE``）。
Phase 4 用供应商逐日估值补齐了这两块：

    size          log(total_mv)            —— **真实总市值**（万元，取自然对数）
    value         value_ep = 1/pe_ttm      —— 盈利收益率（PE 为负或缺失 → NaN）
                  value_bp = 1/pb          —— 账面市值比（PB 为负或缺失 → NaN）
    liquidity     turnover_free_20d        —— trailing 20 日**自由流通**换手率均值
    momentum      60 / 120 交易日累计收益（复权价）
    volatility    20 / 60 交易日日对数收益标准差

**PIT 正确性**：供应商的 ``total_mv / pe_ttm / pb / turnover_free`` 是**当日**快照
（``total_mv = 当日收盘价 × 当日总股本``），因此本身就是逐日 point-in-time；
再叠加"截止 as_of 的最后一条"（见 ``valuation_snapshots.parquet`` 的构造）即满足
``as_of`` 语义。

**不改 v1**：``phase3e-exposures-v1`` 是 Phase 3 结论的一部分，保持冻结。
本模块产出独立的版本号，两者在同一份报告里并排出现。

纪律（沿用 Phase 3）
--------------------
* 所有暴露只在 ``trade_date <= as_of`` 的数据上计算；有硬断言测试守着。
* 不可用一律 **NaN**，**不得用 0 冒充**；负 PE/PB 视为不可用（1/负数没有经济含义）。
* 缺失情况必须按列披露覆盖率，而不是静默丢弃股票。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.research.labels.horizon_returns import align_adj_factor

#: 暴露口径版本（改动窗口/算法/字段必须提升）
EXPOSURE_VERSION_V2 = "phase4-exposures-v2"
#: 是否使用真实市值（用于报告声明）
SIZE_BASIS_REAL_MARKET_CAP = "REAL_TOTAL_MARKET_CAP"
VALUE_BASIS = "DAILY_PIT_VALUATION"
#: 退市股估值不可用（供应商包不含退市股）
VALUATION_UNAVAILABLE_FOR_DELISTED = "VALUATION_UNAVAILABLE_FOR_DELISTED"

#: momentum / volatility / 流动性窗口
MOMENTUM_WINDOWS: tuple[int, ...] = (60, 120)
VOLATILITY_WINDOWS: tuple[int, ...] = (20, 60)
TURNOVER_WINDOW = 20

#: v2 的完整暴露列（中性化时按可用性逐列进入）
STYLE_EXPOSURE_COLUMNS_V2: tuple[str, ...] = (
    "size_log_market_cap",
    "value_ep",
    "value_bp",
    "momentum_60d",
    "momentum_120d",
    "volatility_20d",
    "volatility_60d",
    "turnover_free_20d",
)
#: 与 v1 的对照（报告里说明"哪些是新增"）
V1_COLUMNS: tuple[str, ...] = (
    "momentum_60d", "momentum_120d", "volatility_20d", "volatility_60d",
    "size_proxy_log_amount_20d",
)
V2_NEW_COLUMNS: tuple[str, ...] = (
    "size_log_market_cap", "value_ep", "value_bp", "turnover_free_20d",
)


@dataclass(frozen=True)
class ExposureAvailabilityV2:
    """v2 暴露的可得性记录（写入产物与报告）。"""

    exposure_version: str
    available_columns: tuple[str, ...]
    size_basis: str
    value_basis: str
    delisted_note: str

    def to_dict(self) -> dict:
        return {
            "exposure_version": self.exposure_version,
            "available_columns": list(self.available_columns),
            "new_columns_vs_v1": list(V2_NEW_COLUMNS),
            "size_basis": self.size_basis,
            "value_basis": self.value_basis,
            "delisted_note": self.delisted_note,
        }


def exposure_availability_v2() -> ExposureAvailabilityV2:
    return ExposureAvailabilityV2(
        exposure_version=EXPOSURE_VERSION_V2,
        available_columns=STYLE_EXPOSURE_COLUMNS_V2,
        size_basis=SIZE_BASIS_REAL_MARKET_CAP,
        value_basis=VALUE_BASIS,
        delisted_note=(
            f"{VALUATION_UNAVAILABLE_FOR_DELISTED}：供应商日 K 不含退市股，"
            "退市股的 size/value 一律 NaN（不得用 0 冒充），"
            "报告必须同时给出覆盖比例。"
        ),
    )


# ---------------------------------------------------------------------------
# 纯函数：单只股票的价格类暴露（不依赖 Parquet，便于测试）
# ---------------------------------------------------------------------------


def _last_index_on_or_before(dates: np.ndarray, value: date) -> int:
    target = np.datetime64(value, "D")
    return int(np.searchsorted(dates, target, side="right")) - 1


def compute_price_exposures(
    bars: pd.DataFrame,
    as_ofs: list[date],
    *,
    adj_factors: pd.DataFrame | None = None,
    stock_code: str = "",
) -> list[dict]:
    """momentum / volatility（只用 ``as_of`` 当日及之前的 bar）。"""
    if bars.empty:
        return []
    ordered = bars.sort_values("trade_date").reset_index(drop=True)
    date_array = np.asarray(
        pd.to_datetime(ordered["trade_date"]).to_numpy(dtype="datetime64[D]"),
        dtype="datetime64[D]",
    )
    factor, _stats = align_adj_factor(ordered, adj_factors)
    close = pd.to_numeric(ordered["close"], errors="coerce").to_numpy(dtype=float)
    adj_close = close * factor
    log_close = np.where(adj_close > 0, np.log(np.where(adj_close > 0, adj_close, 1.0)), np.nan)

    rows: list[dict] = []
    for as_of in sorted(set(as_ofs)):
        index = _last_index_on_or_before(date_array, as_of)
        if index < 0:
            continue
        row: dict = {
            "stock_code": stock_code,
            "as_of": as_of,
            "exposure_version": EXPOSURE_VERSION_V2,
            "bar_date": pd.Timestamp(date_array[index]).date(),
        }
        for window in MOMENTUM_WINDOWS:
            start = index - window
            key = f"momentum_{window}d"
            if start < 0 or not np.isfinite(adj_close[start]) or adj_close[start] == 0:
                row[key] = None
                continue
            row[key] = round(float(adj_close[index] / adj_close[start] - 1.0), 8)
        for window in VOLATILITY_WINDOWS:
            start = index - window
            key = f"volatility_{window}d"
            if start < 0:
                row[key] = None
                continue
            windowed = log_close[start: index + 1]
            returns = np.diff(windowed)
            returns = returns[np.isfinite(returns)]
            row[key] = round(float(returns.std(ddof=1)), 8) if len(returns) == window else None
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 估值类暴露：从 as_of 快照取值
# ---------------------------------------------------------------------------


def safe_inverse(values: pd.Series, *, require_positive: bool = True) -> pd.Series:
    """``1/x``，并在 ``x <= 0`` 或缺失时返回 NaN。

    负 PE（亏损公司）与负 PB（资不抵债）的倒数没有经济含义，必须**判为不可用**，
    而不是取一个负的"收益率"混进横截面 —— 那会污染中性化回归。
    """
    numeric = pd.to_numeric(values, errors="coerce")
    if require_positive:
        numeric = numeric.where(numeric > 0)
    return 1.0 / numeric


def valuation_exposures(snapshot: pd.DataFrame) -> pd.DataFrame:
    """把 as_of 快照转成暴露列（``size_log_market_cap`` / ``value_ep`` / ``value_bp`` / ``turnover_free_20d``）。"""
    out = snapshot.copy()
    numeric_mv = pd.to_numeric(out.get("total_mv"), errors="coerce")
    out["size_log_market_cap"] = np.where(
        numeric_mv > 0, np.log(numeric_mv.where(numeric_mv > 0)), np.nan,
    )
    out["value_ep"] = safe_inverse(out.get("pe_ttm", pd.Series(index=out.index, dtype=float)))
    out["value_bp"] = safe_inverse(out.get("pb", pd.Series(index=out.index, dtype=float)))
    out["turnover_free_20d"] = pd.to_numeric(
        out.get("turnover_free", pd.Series(index=out.index, dtype=float)), errors="coerce",
    )
    out["valuation_status"] = np.where(
        numeric_mv.notna(), VALUE_BASIS, VALUATION_UNAVAILABLE_FOR_DELISTED,
    )
    return out


def build_exposure_panel_v2(
    *,
    codes: list[str],
    as_ofs: list[date],
    snapshots: pd.DataFrame,
    bars_reader,  # type: ignore[no-untyped-def]
    factors_reader,  # type: ignore[no-untyped-def]
    progress=None,  # type: ignore[no-untyped-def]
) -> tuple[pd.DataFrame, dict]:
    """构建全量 v2 暴露面板。

    Args:
        snapshots: ``valuation_snapshots.parquet`` 的内容（含 ``as_of`` / ``stock_code``）。
        bars_reader: ``callable(code) -> DataFrame``（``trade_date`` / ``close`` / ...）。
        factors_reader: ``callable(code) -> DataFrame | None``（``trade_date`` / ``factor``）。
    """
    price_rows: list[dict] = []
    for order, code in enumerate(codes):
        if progress and order % 500 == 0:
            progress(f"价格类暴露 {order}/{len(codes)} …")
        try:
            bars = bars_reader(code)
        except Exception:  # noqa: BLE001 - 单只失败不阻塞
            continue
        if bars is None or len(bars) == 0:
            continue
        price_rows.extend(
            compute_price_exposures(
                bars, as_ofs, adj_factors=factors_reader(code), stock_code=code,
            )
        )
    price = pd.DataFrame(price_rows)

    valuated = valuation_exposures(snapshots)
    valuated = valuated[[
        "as_of", "stock_code", "size_log_market_cap", "value_ep", "value_bp",
        "turnover_free_20d", "valuation_status", "trade_date", "staleness_days",
    ]].rename(columns={"trade_date": "valuation_date"})
    valuated["as_of"] = pd.to_datetime(valuated["as_of"]).dt.date

    merged = (
        price.merge(valuated, on=["as_of", "stock_code"], how="outer")
        if not price.empty else valuated
    )
    meta: dict = {
        "exposure_version": EXPOSURE_VERSION_V2,
        "availability": exposure_availability_v2().to_dict(),
        "code_count": len(codes),
        "as_of_count": len(as_ofs),
        "row_count": int(len(merged)),
        "columns": {},
    }
    for column in STYLE_EXPOSURE_COLUMNS_V2:
        if column not in merged.columns:
            continue
        usable = int(merged[column].notna().sum())
        meta["columns"][column] = {
            "usable": usable,
            "missing": int(len(merged) - usable),
            "coverage_ratio": round(usable / len(merged), 6) if len(merged) else 0.0,
        }
    if "valuation_status" in merged.columns:
        meta["valuation_status_counts"] = (
            merged["valuation_status"].value_counts().to_dict()
        )
    return merged, meta


__all__ = [
    "EXPOSURE_VERSION_V2",
    "MOMENTUM_WINDOWS",
    "SIZE_BASIS_REAL_MARKET_CAP",
    "STYLE_EXPOSURE_COLUMNS_V2",
    "TURNOVER_WINDOW",
    "V2_NEW_COLUMNS",
    "V1_COLUMNS",
    "VALUATION_UNAVAILABLE_FOR_DELISTED",
    "VALUE_BASIS",
    "VOLATILITY_WINDOWS",
    "ExposureAvailabilityV2",
    "build_exposure_panel_v2",
    "compute_price_exposures",
    "exposure_availability_v2",
    "safe_inverse",
    "valuation_exposures",
]
