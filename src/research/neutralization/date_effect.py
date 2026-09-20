"""Phase 3E · 日期效应分析（``HuangliDateEffectAnalysis``，P0 统计修正）。

要修正的统计错误
----------------
Phase 3D 发现黄历（``H_*``）方向是「日历开关」：同一个 ``as_of`` 上它要么几乎
全体命中、要么几乎全体不命中（命中率 0.00–0.78，std 0.27）。这带来的后果是：

* 把这些 ``(股票, 日期)`` 对当作独立事件，等于把**一个日期结论**重复计数 300 次；
* 于是"黄历事件集合的未来超额收益"实际上在问"这几个日期的市场表现如何"——
  这是一个**日期层面的**问题，不是股票横截面的问题。

正确做法（本模块）
------------------
1. 先把数据折叠到**日期**：每个 ``as_of`` 计算当日全体可用股票的等权平均收益与超额；
2. 日期级统计量的样本量 = **有效日期数**，不是事件行数；
3. 日期层面的对照是"全部交易日"，而不是"随机抽同样数量的股票"；
4. 同时给出 ``hit_share``（当日命中比例）作为"日期开关强度"的连续度量，
   并估计 ``cs_mean_excess ~ hit_share`` 的日期级斜率。

纪律
----
* 本模块**只做描述性统计**：它回答"黄历命中的日子，市场整体是否不同"，
  不回答"能不能靠它择时"（未计交易成本、未做交易可行性检验）。
* 分区（TRAIN / VALIDATION / OOS）必须分开报告：样本内发现的日期效应
  必须先在样本外复现，才谈得上"结构"。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: 日期效应口径版本
DATE_EFFECT_VERSION = "phase3e-huangli-date-effect-v1"
#: 该日至少要有这么多只股票才参与日期级统计
MIN_STOCKS_PER_DATE = 20


def _daily_t_stat(values: list[float]) -> tuple[float | None, float | None, int]:
    arr = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    n = int(len(arr))
    if n == 0:
        return None, None, 0
    mean = float(arr.mean())
    if n < 2:
        return round(mean, 8), None, n
    std = float(arr.std(ddof=1))
    if std == 0:
        return round(mean, 8), None, n
    return round(mean, 8), round(mean / (std / np.sqrt(n)), 6), n


def build_date_table(
    cross_section: pd.DataFrame,
    hit_col: str,
    horizon: int,
    *,
    date_col: str = "as_of",
    min_stocks: int = MIN_STOCKS_PER_DATE,
) -> pd.DataFrame:
    """把 ``(股票, as_of)`` 面板折叠成日期表。

    每个日期一行：股票数、命中数、命中比例、当日等权原始收益、当日基准收益、
    当日等权市场超额，以及横截面离散度（std）。
    """
    raw_col = f"raw_return_{horizon}d"
    bench_col = f"benchmark_return_{horizon}d"
    excess_col = f"market_excess_return_{horizon}d"
    for column in (raw_col, bench_col, excess_col, hit_col, date_col):
        if column not in cross_section.columns:
            raise ValueError(f"日期效应分析缺少字段：{column}")

    rows: list[dict] = []
    for key, group in cross_section.groupby(date_col, sort=True):
        raw = pd.to_numeric(group[raw_col], errors="coerce")
        excess = pd.to_numeric(group[excess_col], errors="coerce")
        bench = pd.to_numeric(group[bench_col], errors="coerce")
        usable = raw.notna() & excess.notna()
        stock_count = int(usable.sum())
        if stock_count < min_stocks:
            continue
        hit = group[hit_col].astype(bool)
        hit_count = int((hit & usable).sum())
        rows.append({
            "as_of": key,
            "horizon": horizon,
            "stock_count": stock_count,
            "hit_count": hit_count,
            "hit_share": round(hit_count / stock_count, 6),
            "cross_sectional_mean_return": round(float(raw[usable].mean()), 8),
            "cross_sectional_median_return": round(float(raw[usable].median()), 8),
            "cross_sectional_return_std": round(float(raw[usable].std(ddof=1)), 8)
            if stock_count > 1 else None,
            "market_return": round(float(bench[usable].mean()), 8),
            "market_excess": round(float(excess[usable].mean()), 8),
            "up_share": round(float((raw[usable] > 0).mean()), 6),
        })
    return pd.DataFrame(rows)


def _subset_stats(table: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    sub = table[mask]
    mean, t_stat, n = _daily_t_stat(sub["market_excess"].tolist())
    raw_mean, raw_t, _n = _daily_t_stat(sub["cross_sectional_mean_return"].tolist())
    return {
        "group": label,
        "date_count": int(n),
        "market_excess_mean": mean,
        "market_excess_t": t_stat,
        "cross_sectional_mean_return": raw_mean,
        "cross_sectional_t": raw_t,
    }


def _welch(a: list[float], b: list[float]) -> tuple[float | None, float | None]:
    """Welch t 检验（日期级；不做行级聚合）。"""
    x = np.asarray([v for v in a if np.isfinite(v)], dtype=float)
    y = np.asarray([v for v in b if np.isfinite(v)], dtype=float)
    if len(x) < 2 or len(y) < 2:
        return None, None
    diff = float(x.mean() - y.mean())
    vx = float(x.var(ddof=1)) / len(x)
    vy = float(y.var(ddof=1)) / len(y)
    denom = vx + vy
    if denom <= 0:
        return round(diff, 8), None
    return round(diff, 8), round(diff / np.sqrt(denom), 6)


def date_effect_analysis(
    cross_section: pd.DataFrame,
    hit_col: str,
    horizon: int,
    *,
    date_col: str = "as_of",
    min_stocks: int = MIN_STOCKS_PER_DATE,
) -> dict:
    """单个事件集合（例如 ``huangli_calibrated``）的日期效应分析。

    Returns:
        含 ``date_count`` / ``stock_count_per_date`` / ``cross_sectional_mean_return`` /
        ``market_return`` / ``market_excess`` / ``date_clustered`` / ``hit_dates`` /
        ``non_hit_dates`` / ``date_clustered_difference`` / ``hit_share_slope`` 的字典。
    """
    table = build_date_table(
        cross_section, hit_col, horizon, date_col=date_col, min_stocks=min_stocks,
    )
    if table.empty:
        return {
            "date_effect_version": DATE_EFFECT_VERSION,
            "horizon": horizon,
            "date_count": 0,
            "stock_count_per_date": {"mean": None, "min": None, "max": None},
            "cross_sectional_mean_return": None,
            "market_return": None,
            "market_excess": None,
            "date_clustered": {"mean": None, "t": None, "date_count": 0},
            "binary_split_usable": False,
            "binary_split_note": "无有效日期",
            "hit_dates": None,
            "non_hit_dates": None,
            "date_clustered_difference": {"difference": None, "welch_t": None},
            "median_split": None,
            "hit_share_slope": {"slope": None, "t": None},
            "event_row_count_vs_date_count": {"event_rows": 0, "dates": 0},
        }

    # 二值切分（hit_dates vs non_hit_dates）：只有存在**零命中日期**时才可解释。
    # 实测中黄历在 OOS 的每个日期都至少有 1 个命中（15/15），此时二值切分退化，
    # 必须如实标记，而不是把"全部日期"当成"命中日期组"给出一个空对照。
    hit_mask = table["hit_share"] > 0
    binary_usable = bool((~hit_mask).any() and hit_mask.any())
    hit_stats = _subset_stats(table, hit_mask, "hit_dates")
    non_hit_stats = _subset_stats(table, ~hit_mask, "non_hit_dates")
    diff, welch_t = _welch(
        table.loc[hit_mask, "market_excess"].tolist(),
        table.loc[~hit_mask, "market_excess"].tolist(),
    )
    if not binary_usable:
        hit_stats, non_hit_stats, diff, welch_t = None, None, None, None

    # 中位数切分：即使每个日期都有命中，也能比较"高命中日"与"低命中日"。
    # 这是「日期选择器」结构的稳健替代口径（不依赖任何日期恰好零命中）。
    median = float(table["hit_share"].median())
    above = table["hit_share"] > median
    below = table["hit_share"] <= median
    if above.any() and below.any():
        above_stats = _subset_stats(table, above, "above_median_hit_share")
        below_stats = _subset_stats(table, below, "below_median_hit_share")
        median_diff, median_welch = _welch(
            table.loc[above, "market_excess"].tolist(),
            table.loc[below, "market_excess"].tolist(),
        )
        median_split = {
            "median_hit_share": round(median, 6),
            "above_median": above_stats,
            "below_median": below_stats,
            "difference": median_diff,
            "welch_t": median_welch,
        }
    else:
        median_split = None

    all_mean, all_t, all_n = _daily_t_stat(table["market_excess"].tolist())
    raw_mean, raw_t, _raw_n = _daily_t_stat(table["cross_sectional_mean_return"].tolist())
    bench_mean = round(float(table["market_return"].mean()), 8)

    # 日期级斜率：cs_mean_excess = a + b * hit_share
    slope: float | None = None
    slope_t: float | None = None
    shares = table["hit_share"].to_numpy(dtype=float)
    excess = table["market_excess"].to_numpy(dtype=float)
    if len(shares) > 2 and shares.std() > 0:
        design = np.column_stack([np.ones(len(shares)), shares])
        beta, _res, rank, _sv = np.linalg.lstsq(design, excess, rcond=None)
        if rank == 2 and np.all(np.isfinite(beta)):
            fitted = design @ beta
            resid = excess - fitted
            dof = len(shares) - 2
            sigma2 = float(resid @ resid) / dof if dof > 0 else float("nan")
            try:
                cov = sigma2 * np.linalg.inv(design.T @ design)
                se = float(np.sqrt(cov[1, 1]))
                slope = round(float(beta[1]), 8)
                slope_t = round(float(beta[1]) / se, 6) if se > 0 else None
            except np.linalg.LinAlgError:  # pragma: no cover - 已在 rank 检查中排除
                pass

    return {
        "date_effect_version": DATE_EFFECT_VERSION,
        "horizon": horizon,
        "date_count": int(len(table)),
        "stock_count_per_date": {
            "mean": round(float(table["stock_count"].mean()), 2),
            "min": int(table["stock_count"].min()),
            "max": int(table["stock_count"].max()),
        },
        "cross_sectional_mean_return": raw_mean,
        "cross_sectional_t": raw_t,
        "market_return": bench_mean,
        "market_excess": all_mean,
        "date_clustered": {"mean": all_mean, "t": all_t, "date_count": all_n},
        "binary_split_usable": binary_usable,
        "binary_split_note": (
            "至少存在一个零命中日期，二值切分可用"
            if binary_usable
            else "每个日期都至少有 1 个命中 → 二值切分退化，请改看 median_split / hit_share_slope"
        ),
        "hit_dates": hit_stats,
        "non_hit_dates": non_hit_stats,
        "date_clustered_difference": {"difference": diff, "welch_t": welch_t},
        "median_split": median_split,
        "hit_share_slope": {"slope": slope, "t": slope_t},
        "event_row_count_vs_date_count": {
            "event_rows": int(table["hit_count"].sum()),
            "dates": int(len(table)),
            "raw_row_count": int(table["stock_count"].sum()),
        },
        "date_table_path_hint": "data/phase3_universe/phase3e_huangli_date_effect_dates.csv",
    }


def date_effect_rows(
    cross_section: pd.DataFrame,
    hit_col: str,
    horizon: int,
    **kwargs,  # type: ignore[no-untyped-def]
) -> pd.DataFrame:
    """返回逐日明细表（供 CSV 落盘，便于人工核对折叠是否正确）。"""
    return build_date_table(cross_section, hit_col, horizon, **kwargs)


__all__ = [
    "DATE_EFFECT_VERSION",
    "MIN_STOCKS_PER_DATE",
    "build_date_table",
    "date_effect_analysis",
    "date_effect_rows",
]
