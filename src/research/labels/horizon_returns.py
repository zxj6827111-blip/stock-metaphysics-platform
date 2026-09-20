"""统一未来收益标签：多持有期 ret + 同口径 excess（Phase 3D）。

为什么需要它
------------
Phase 3C 之前，``excess_return`` 只有 20D 口径，5D/10D/60D 的超额收益无处可算。
Phase 3D 要求 ``ret_5d/10d/20d/60d`` 与 ``excess_return_5d/10d/20d/60d``
**同口径、同补丁、同纪律**地给出，因此这里实现唯一的计算入口。

三条纪律
--------
1. **不得用 0 冒充不可用**：数据不足（上市晚、已退市、接近快照末端）时字段为 ``None``，
   并通过 ``horizon_available`` 显式标记。
2. **基于真实交易日**：第 N 个持有期 = 该股票自己的第 N 根后续 bar，
   而不是自然日推算。停牌造成的"实际跨度更长"是真实风险，不做平滑。
3. **复权是收益的一部分**：AStockData canonical 是 ``composite_none``（不复权原始价），
   直接用它算收益会把除权除息当成下跌。因此收益一律用
   ``close × adj_factor`` 计算（除权因子与价格端点同时在分子分母，参考点自动抵消）。

``excess_return_Nd`` 与 ``ret_Nd`` 使用**完全相同的日历区间**（股票端点 trade_date
之间），基准按同一区间取价 —— 这是 Phase 1 审计修正过的口径，避免停牌股票
跨越远超 N 个自然日、而基准只走了 N 个交易日。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

#: 标签口径版本（HFQ 由 raw × adj_factor 推导）
LABEL_VERSION = "phase3d-hfq-adjfactor-v1"
#: Phase 3D 研究的所有持有期（GOAL §12）
HORIZONS: tuple[int, ...] = (5, 10, 20, 60)
#: 预注册的**主**持有期；其它持有期只作稳健性报告，不参与 gate
PRIMARY_HORIZON = 20

#: 基准代码（与 Phase 1/2 一致）
DEFAULT_BENCHMARK_CODE = "000300"


@dataclass(frozen=True)
class BenchmarkSeries:
    """基准指数序列（只做区间取价，不做复权 —— 指数本身是价格指数）。"""

    code: str
    dates: tuple[date, ...]
    closes: tuple[float, ...]

    @classmethod
    def from_frame(cls, frame: pd.DataFrame, *, code: str = DEFAULT_BENCHMARK_CODE) -> BenchmarkSeries:
        if frame.empty:
            return cls(code=code, dates=(), closes=())
        ordered = frame.sort_values("trade_date")
        return cls(
            code=code,
            dates=tuple(pd.to_datetime(ordered["trade_date"]).dt.date.tolist()),
            closes=tuple(float(v) for v in ordered["close"].tolist()),
        )

    def index_at_or_after(self, value: date) -> int | None:
        """返回第一个 ``trade_date >= value`` 的下标；不存在返回 None。"""
        lo, hi = 0, len(self.dates)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.dates[mid] < value:
                lo = mid + 1
            else:
                hi = mid
        return lo if lo < len(self.dates) else None

    def return_between(self, start: date, end: date) -> float | None:
        """基准在 ``[start, end]``（按各自 >= 的首个交易日）区间的收益率。"""
        i = self.index_at_or_after(start)
        j = self.index_at_or_after(end)
        if i is None or j is None:
            return None
        base = self.closes[i]
        if not base:
            return None
        return self.closes[j] / base - 1.0


def align_adj_factor(bars: pd.DataFrame, adj_factors: pd.DataFrame | None) -> tuple[np.ndarray, dict]:
    """把除权因子对齐到股票 bars 的交易日，并给出覆盖率诊断。

    ``adj_factor`` 是"除权日阶跃"型序列，同一因子在两次除权之间保持不变，
    因此**同日前向填充是等价的**；缺失日期若直接按 1.0 处理，会把除权当成下跌。
    这里先左连接、再前向填充、最后对上市首段用后向填充，
    并返回 ``{matched_rows, filled_rows, uncovered_rows}`` 供报告披露。
    """
    n = len(bars)
    stats = {"raw_rows": int(n), "matched_rows": 0, "filled_rows": 0, "uncovered_rows": 0}
    if adj_factors is None or adj_factors.empty:
        stats["uncovered_rows"] = int(n)
        return np.ones(n, dtype=float), stats
    # 类型归一：bars 的 trade_date 可能来自 DB 行（date 对象），
    # adj_factor 来自 CSV（datetime64）。字符串/日期混用会让 merge 直接报错。
    left = pd.DataFrame({
        "trade_date": pd.to_datetime(bars["trade_date"]).to_numpy(dtype="datetime64[ns]")
    })
    right = pd.DataFrame({
        "trade_date": pd.to_datetime(adj_factors["trade_date"]).to_numpy(dtype="datetime64[ns]"),
        "factor": pd.to_numeric(adj_factors["factor"], errors="coerce").to_numpy(dtype=float),
    }).drop_duplicates(subset="trade_date", keep="last")
    merged = left.merge(right, on="trade_date", how="left")
    raw = pd.to_numeric(merged["factor"], errors="coerce")
    stats["matched_rows"] = int(raw.notna().sum())
    filled = raw.ffill().bfill()
    stats["filled_rows"] = int((raw.isna() & filled.notna()).sum())
    stats["uncovered_rows"] = int(filled.isna().sum())
    factor = filled.to_numpy(dtype=float)
    factor = np.where(np.isfinite(factor), factor, 1.0)
    return factor, stats


def adjusted_closes(bars: pd.DataFrame, adj_factors: pd.DataFrame | None = None) -> np.ndarray:
    """``close × adj_factor``（对齐 + 前向填充；无因子历史时退化为原始价）。"""
    factor, _stats = align_adj_factor(bars, adj_factors)
    closes = pd.to_numeric(bars["close"], errors="coerce").to_numpy(dtype=float)
    return closes * factor


def _first_index_on_or_after(dates: np.ndarray, value: date) -> int | None:
    """股票 bars 中第一个 ``trade_date >= value`` 的下标。"""
    target = np.datetime64(value, "D")
    idx = int(np.searchsorted(dates, target, side="left"))
    return idx if idx < len(dates) else None


def compute_forward_returns(
    bars: pd.DataFrame,
    sample_dates: Sequence[date],
    *,
    stock_code: str = "",
    horizons: tuple[int, ...] = HORIZONS,
    adj_factors: pd.DataFrame | None = None,
    benchmark: BenchmarkSeries | None = None,
    is_degraded: bool = False,
    coverage_out: dict | None = None,
) -> list[dict]:
    """对一只股票、一组 ``as_of`` 计算未来收益标签。

    Args:
        bars: 该股票的日线（``trade_date`` / ``close``），必须是**完整历史**：
            标签本来就要读 as_of 之后的数据，这是标签模块的合法特权。
        sample_dates: 采样 as_of（可以是非交易日；基准日取 >= as_of 的首个交易日）。
        adj_factors: ``trade_date`` / ``factor`` 两列；None 表示无需复权。
        benchmark: 基准序列；None 表示不计算超额收益（字段留 None）。
        coverage_out: 可选；会把除权因子覆盖率诊断写进去（便于全库汇总披露）。

    Returns:
        每行一个 ``(stock_code, as_of)`` 的标签字典；``as_of`` 在数据末端之后
        时**不产出该行**（不产出 = 不可用，绝不填 0）。
    """
    if bars.empty:
        return []
    ordered = bars.sort_values("trade_date").reset_index(drop=True)
    trade_dates = pd.to_datetime(ordered["trade_date"]).dt.date.to_numpy()
    date_array = pd.to_datetime(ordered["trade_date"]).to_numpy(dtype="datetime64[D]")
    factor, coverage = align_adj_factor(ordered, adj_factors)
    if coverage_out is not None:
        coverage_out.update(coverage)
        coverage_out["stock_code"] = stock_code
    closes = pd.to_numeric(ordered["close"], errors="coerce").to_numpy(dtype=float) * factor
    raw_closes = pd.to_numeric(ordered["close"], errors="coerce").to_numpy(dtype=float)
    n = len(date_array)

    rows: list[dict] = []
    for as_of in sorted(set(sample_dates)):
        base_idx = _first_index_on_or_after(date_array, as_of)
        if base_idx is None:
            continue
        base_close = closes[base_idx]
        raw_base = raw_closes[base_idx]
        if not np.isfinite(base_close) or base_close == 0:
            continue
        row: dict = {
            "stock_code": stock_code,
            "as_of": as_of,
            "trade_date": trade_dates[base_idx],
            "trade_index": int(base_idx),
            "base_close_adjusted": float(base_close),
            "base_close_raw": float(raw_base) if np.isfinite(raw_base) else None,
            "label_version": LABEL_VERSION,
            "is_degraded": bool(is_degraded),
            "horizon_available": {},
        }
        for h in horizons:
            idx = base_idx + h
            key = f"{h}d"
            if idx >= n or not np.isfinite(closes[idx]):
                row["horizon_available"][key] = False
                row[f"ret_{h}d"] = None
                row[f"excess_return_{h}d"] = None
                row[f"bench_ret_{h}d"] = None
                continue
            ret = float(closes[idx] / base_close - 1.0)
            row["horizon_available"][key] = True
            row[f"ret_{h}d"] = round(ret, 6)
            bench_ret = None
            if benchmark is not None:
                bench_ret = benchmark.return_between(trade_dates[base_idx], trade_dates[idx])
            row[f"bench_ret_{h}d"] = None if bench_ret is None else round(bench_ret, 6)
            row[f"excess_return_{h}d"] = (
                None if bench_ret is None else round(ret - bench_ret, 6)
            )
        rows.append(row)
    return rows


def label_frame(rows: list[dict]) -> pd.DataFrame:
    """把标签行转成研究用 DataFrame（``horizon_available`` 展开为列）。"""
    columns = [
        "stock_code", "as_of", "trade_date", "trade_index",
        *[f"ret_{h}d" for h in HORIZONS],
        *[f"excess_return_{h}d" for h in HORIZONS],
        *[f"bench_ret_{h}d" for h in HORIZONS],
        "label_version", "is_degraded",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame([{k: v for k, v in row.items() if k != "horizon_available"} for row in rows])
    return frame


__all__ = [
    "DEFAULT_BENCHMARK_CODE",
    "HORIZONS",
    "LABEL_VERSION",
    "PRIMARY_HORIZON",
    "BenchmarkSeries",
    "adjusted_closes",
    "align_adj_factor",
    "compute_forward_returns",
    "label_frame",
]
