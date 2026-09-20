"""Phase 3D 诊断：年份稳定性 / 非重叠敏感性 / 单一股票依赖度 / 效应量。

这些诊断回答的是 "这个 OOS 结果能不能信"，而不是 "收益高不高"：

* **重叠窗口**：每期都产生一个 20D 事件，会产生大量互相重叠的未来窗口。
  重叠样本不是独立样本，会低估标准误。本模块给出 ``overlap_ratio``，
  并提供 ``non_overlapping_subset`` 做敏感性对照。
* **年份稳定性**：整体正收益如果只由某一年极端行情驱动，不能判"稳定"。
* **单一股票依赖**：如果删掉一只股票信号就消失，标记 ``SINGLE_NAME_DEPENDENT``。
* **效应量**：p 值之外必须给 Cohen's d；本项目不接受"显著但效应为零"。

统计实现不引入 scipy（避免新增依赖）：Welch t 用正态近似算双侧 p
（n 上百时足够精确），随机对照另给经验 p 值（置换法，不依赖分布假设）。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

#: 判定"单一股票驱动"的绝对贡献份额上限（top1 占绝对贡献质量的比例）
MAX_TOP1_ABS_MASS = 0.5
#: 判定 "top_k 过度集中" 的上限
MAX_TOP5_ABS_MASS = 0.8


def _clean(values: Sequence[object]) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    return arr[np.isfinite(arr)]


def normal_two_sided_p(z: float) -> float:
    """标准正态双侧 p 值（``erfc`` 精确到浮点精度）。"""
    return float(math.erfc(abs(float(z)) / math.sqrt(2.0)))


def welch_ttest(a: Sequence[object], b: Sequence[object]) -> tuple[float | None, float | None]:
    """Welch t 检验，返回 ``(t, p)``；样本不足或方差为 0 时返回 ``(None, None)``。"""
    x, y = _clean(a), _clean(b)
    if len(x) < 2 or len(y) < 2:
        return None, None
    vx, vy = x.var(ddof=1), y.var(ddof=1)
    se = math.sqrt(vx / len(x) + vy / len(y))
    if se == 0.0:
        return None, None
    t = float((x.mean() - y.mean()) / se)
    return t, normal_two_sided_p(t)


def cohens_d(a: Sequence[object], b: Sequence[object]) -> float | None:
    """Cohen's d（合并标准差口径）；标准差为 0 时返回 ``None``，不用 0 冒充。"""
    x, y = _clean(a), _clean(b)
    if len(x) < 2 or len(y) < 2:
        return None
    nx, ny = len(x), len(y)
    pooled = ((nx - 1) * x.var(ddof=1) + (ny - 1) * y.var(ddof=1)) / (nx + ny - 2)
    if pooled <= 0:
        return None
    return float((x.mean() - y.mean()) / math.sqrt(pooled))


def effect_size_summary(
    real: Sequence[object],
    control: Sequence[object],
    *,
    permutation_p: float | None = None,
    control_draws: int | None = None,
) -> dict:
    """真实组 vs 对照组的效应量摘要。"""
    x, y = _clean(real), _clean(control)
    if len(x) == 0 or len(y) == 0:
        return {
            "n_real": int(len(x)), "n_control": int(len(y)),
            "mean_real": None, "mean_control": None, "delta_mean": None,
            "cohen_d": None, "welch_t": None, "welch_p": None,
            "permutation_p": None, "control_draws": control_draws,
        }
    t, p = welch_ttest(x, y)
    d = cohens_d(x, y)
    return {
        "n_real": int(len(x)),
        "n_control": int(len(y)),
        "mean_real": round(float(x.mean()), 6),
        "mean_control": round(float(y.mean()), 6),
        "delta_mean": round(float(x.mean() - y.mean()), 6),
        "cohen_d": None if d is None else round(d, 6),
        "welch_t": None if t is None else round(t, 6),
        "welch_p": None if p is None else round(p, 8),
        "permutation_p": None if permutation_p is None else round(float(permutation_p), 8),
        "control_draws": control_draws,
    }


# ---------------------------------------------------------------------------
# 年份稳定性
# ---------------------------------------------------------------------------


def year_stability(
    frame: pd.DataFrame,
    horizon: int,
    *,
    return_col: str | None = None,
) -> dict:
    """按年统计平均收益 / 超额收益 / 上涨率，并给出方向一致性。

    ``sign_consistency`` = 与"整体符号"一致的年数 / 有有效样本的年数。
    """
    col = return_col or f"excess_return_{horizon}d"
    if frame.empty or col not in frame.columns:
        return {"years": [], "year_count": 0, "positive_year_ratio": None,
                "sign_consistency": None, "overall_mean": None, "overall_sign": 0}
    work = frame.copy()
    work[col] = pd.to_numeric(work[col], errors="coerce")
    work["year"] = pd.to_datetime(work["trade_date"]).dt.year
    work = work.dropna(subset=[col])
    if work.empty:
        return {"years": [], "year_count": 0, "positive_year_ratio": None,
                "sign_consistency": None, "overall_mean": None, "overall_sign": 0}

    overall = float(work[col].mean())
    overall_sign = int(np.sign(overall))
    rows: list[dict] = []
    for year, group in work.groupby("year", sort=True):
        values = group[col].to_numpy(dtype=float)
        mean = float(values.mean())
        rows.append({
            "year": int(year),
            "event_count": int(len(values)),
            "mean_excess_return": round(mean, 6),
            "up_rate": round(float((values > 0).mean()), 6),
            "direction": int(np.sign(mean)),
        })
    positives = sum(1 for r in rows if r["mean_excess_return"] > 0)
    agreeing = sum(1 for r in rows if r["direction"] == overall_sign)
    return {
        "years": rows,
        "year_count": len(rows),
        "positive_year_ratio": round(positives / len(rows), 6),
        "sign_consistency": round(agreeing / len(rows), 6),
        "overall_mean": round(overall, 6),
        "overall_sign": overall_sign,
        "return_col": col,
    }


# ---------------------------------------------------------------------------
# 重叠窗口
# ---------------------------------------------------------------------------


def overlap_ratio(
    frame: pd.DataFrame,
    horizon: int,
    *,
    index_col: str = "trade_index",
    stock_col: str = "stock_code",
) -> float | None:
    """事件窗口重叠比例：同股票在 ``horizon`` 个交易日内还有其它事件的比例。

    事件窗口定义为 ``[trade_index, trade_index + horizon]``（持有期），
    因此两只相距 ``< horizon`` 个交易日的事件会共享未来时段 —— 这是
    "伪样本"的来源，必须显式报告。
    """
    if frame.empty or index_col not in frame.columns:
        return None
    total = 0
    overlapping = 0
    for _stock, group in frame.groupby(stock_col, sort=False):
        idx = np.sort(group[index_col].to_numpy(dtype=int))
        total += len(idx)
        if len(idx) <= 1:
            continue
        # 相邻事件间隔（升序）；端点用哨兵值保证形状一致
        left_gap = np.diff(idx, prepend=idx[0] - 10**9)
        right_gap = np.diff(idx, append=idx[-1] + 10**9)
        overlapping += int(((left_gap < horizon) | (right_gap < horizon)).sum())
    if total == 0:
        return None
    return round(overlapping / total, 6)


def non_overlapping_subset(
    frame: pd.DataFrame,
    horizon: int,
    *,
    index_col: str = "trade_index",
    stock_col: str = "stock_code",
) -> pd.DataFrame:
    """贪心保留互不重叠的事件（按交易序号升序，间隔 >= horizon 才保留）。

    这是敏感性检查，不是主口径：主口径是否本来就非重叠由采样步长决定
    （Phase 3D 主面板为季度采样，20D/60D 天然非重叠）。
    """
    if frame.empty or index_col not in frame.columns:
        return frame.iloc[0:0].copy()
    kept_indices: list[int] = []
    for _stock, group in frame.groupby(stock_col, sort=False):
        ordered = group.sort_values(index_col)
        last: int | None = None
        for position, idx in zip(ordered.index, ordered[index_col].to_numpy(dtype=int), strict=True):
            if last is None or idx - last >= horizon:
                kept_indices.append(int(position))
                last = idx
    return frame.loc[sorted(kept_indices)].copy()


# ---------------------------------------------------------------------------
# 单一股票依赖度
# ---------------------------------------------------------------------------


def contribution_distribution(
    frame: pd.DataFrame, horizon: int, *, return_col: str | None = None
) -> list[dict]:
    """每只股票对总超额收益的绝对贡献质量与份额。

    ``abs_mass_share`` = ``|Σ_i r| / Σ_j |Σ_j r|``：始终有定义（总收益为负也成立），
    因此比"占总和的比例"更稳健。
    """
    col = return_col or f"excess_return_{horizon}d"
    if frame.empty or col not in frame.columns:
        return []
    work = frame.copy()
    work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=[col])
    if work.empty:
        return []
    grouped = work.groupby("stock_code")[col]
    sums = grouped.sum()
    counts = grouped.count()
    total_abs = float(sums.abs().sum())
    total = float(work[col].sum())
    rows: list[dict] = []
    for code, value in sums.items():
        rows.append({
            "stock_code": str(code),
            "event_count": int(counts[code]),
            "sum_excess_return": round(float(value), 6),
            "mean_excess_return": round(float(value / max(counts[code], 1)), 6),
            "abs_mass_share": None if total_abs == 0 else round(abs(float(value)) / total_abs, 6),
            "share_of_total": None if total == 0 else round(float(value) / total, 6),
        })
    rows.sort(key=lambda r: -(r["abs_mass_share"] or 0.0))
    return rows


def leave_one_stock_out(
    frame: pd.DataFrame, horizon: int, *, return_col: str | None = None
) -> dict:
    """逐股剔除后的均值范围与符号翻转计数。"""
    col = return_col or f"excess_return_{horizon}d"
    if frame.empty or col not in frame.columns:
        return {"loo_stock_count": 0, "loo_mean_min": None, "loo_mean_max": None,
                "loo_sign_flip_count": 0, "overall_mean": None}
    work = frame.copy()
    work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=[col])
    if work.empty:
        return {"loo_stock_count": 0, "loo_mean_min": None, "loo_mean_max": None,
                "loo_sign_flip_count": 0, "overall_mean": None}
    overall = float(work[col].mean())
    sign = int(np.sign(overall))
    total_sum = float(work[col].sum())
    count = len(work)
    means: list[float] = []
    flips = 0
    for _code, group in work.groupby("stock_code", sort=False):
        remaining_count = count - len(group)
        if remaining_count <= 0:
            continue
        mean = (total_sum - float(group[col].sum())) / remaining_count
        means.append(mean)
        if sign != 0 and int(np.sign(mean)) != sign:
            flips += 1
    if not means:
        return {"loo_stock_count": 0, "loo_mean_min": None, "loo_mean_max": None,
                "loo_sign_flip_count": 0, "overall_mean": round(overall, 6)}
    return {
        "loo_stock_count": len(means),
        "loo_mean_min": round(min(means), 6),
        "loo_mean_max": round(max(means), 6),
        "loo_sign_flip_count": int(flips),
        "overall_mean": round(overall, 6),
    }


def stock_dependency(
    frame: pd.DataFrame, horizon: int, *, return_col: str | None = None
) -> dict:
    """单一股票依赖度总览（top1/top5 贡献 + LOO）。"""
    distribution = contribution_distribution(frame, horizon, return_col=return_col)
    if not distribution:
        return {"top_1_contribution": None, "top_5_contribution": None,
                "stock_contribution_distribution": [], "single_name_dependent": None, **leave_one_stock_out(frame, horizon, return_col=return_col)}
    shares = [r["abs_mass_share"] or 0.0 for r in distribution]
    top1 = shares[0]
    top5 = float(sum(shares[:5]))
    loo = leave_one_stock_out(frame, horizon, return_col=return_col)
    dependent = bool(top1 > MAX_TOP1_ABS_MASS or loo["loo_sign_flip_count"] > 0)
    return {
        "stock_count": len(distribution),
        "top_1_contribution": round(top1, 6),
        "top_5_contribution": round(top5, 6),
        "max_top1_threshold": MAX_TOP1_ABS_MASS,
        "max_top5_threshold": MAX_TOP5_ABS_MASS,
        "single_name_dependent": dependent,
        "stock_contribution_distribution": distribution,
        **loo,
    }


def hit_concentration(
    hits: pd.DataFrame,
    pool: pd.DataFrame,
    *,
    date_col: str = "as_of",
    stock_col: str = "stock_code",
    threshold_high: float = 0.6,
    threshold_low: float = 0.05,
) -> dict:
    """命中在**日期上**的集中度（横截面区分度诊断）。

    每个 ``as_of`` 的命中率 = 当日命中股票数 / 当日可用股票数。
    如果某引擎常常"几乎全体命中或几乎全体不命中"，它的事件集合实际是
    **日期选择**而不是**股票选择** —— 这会让两类负对照测量不同的零假设：

    * 位置对照（从池中随机抽同数量）→ 混合了日期构成；
    * 逐日数量守恒对照（随机出生指派 / 随机方向）→ 保留日期构成。

    两者结论不一致时必须**同时报告**，不得只挑一个好看的口径。
    """
    empty = {
        "date_count": 0, "min_rate": None, "max_rate": None, "std_rate": None,
        "dates_above_high": None, "dates_below_low": None,
        "mean_hit_per_date": None, "threshold_high": threshold_high,
        "threshold_low": threshold_low,
    }
    if hits is None or hits.empty or pool is None or pool.empty:
        return empty
    hit_counts = hits.groupby(date_col)[stock_col].nunique()
    pool_counts = pool.groupby(date_col)[stock_col].nunique()
    # "当天零命中"的日期不会出现在 hit_counts 的索引里；必须按池的日期补齐为 0，
    # 否则"完全无命中的日期"会被丢掉，把日历开关形态误判成温和分布。
    hit_counts = hit_counts.reindex(pool_counts.index, fill_value=0)
    rates = (hit_counts / pool_counts).dropna()
    if rates.empty:
        return empty
    values = rates.to_numpy(dtype=float)
    return {
        "date_count": int(len(values)),
        "min_rate": round(float(values.min()), 6),
        "max_rate": round(float(values.max()), 6),
        "std_rate": round(float(values.std(ddof=1)), 6) if len(values) > 1 else None,
        "dates_above_high": int((values > threshold_high).sum()),
        "dates_below_low": int((values < threshold_low).sum()),
        "mean_hit_per_date": round(float(hit_counts.mean()), 6),
        "threshold_high": threshold_high,
        "threshold_low": threshold_low,
    }


__all__ = [
    "MAX_TOP1_ABS_MASS",
    "MAX_TOP5_ABS_MASS",
    "cohens_d",
    "contribution_distribution",
    "effect_size_summary",
    "hit_concentration",
    "leave_one_stock_out",
    "non_overlapping_subset",
    "normal_two_sided_p",
    "overlap_ratio",
    "stock_dependency",
    "welch_ttest",
    "year_stability",
]
