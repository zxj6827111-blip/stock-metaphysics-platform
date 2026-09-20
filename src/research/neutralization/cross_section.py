"""Phase 3E · 横截面统计（RankIC / 分组收益 / long-short / 回归）。

为什么所有统计都"先按日、再跨日平均"
------------------------------------
面板是 ``(股票 × as_of)``：同一个 ``as_of`` 上的 300+ 只股票**不是独立样本**
（它们共享同一段市场行情）。直接把 5000 个事件当作 5000 个独立观测，
会把标准误压缩到虚假的显著 —— Phase 3D 已经用黄历证明这不是理论担忧：
同一天要么几乎全体命中、要么几乎全体不命中，行级 p 值与日级 p 值可以给出
完全相反的结论。

因此本模块的默认口径是 **date-clustered**：

1. 在每个 ``as_of`` 内部计算该日的统计量（IC、组均值、回归系数）；
2. 跨日对这些"每日统计量"求均值与 t 统计量，**自由度 = 有效日数 − 1**；
3. 同时保留 pooled（行级）口径用于对照，但报告里必须标明是哪一个。

long-short / 分组收益是**研究统计量**，不是交易策略建议：未计交易成本、
流动性、涨跌停与卖空约束，报告中不得表述为可交易收益。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: 单日横截面的最小股票数（低于此值该日不参与日级统计）
MIN_STOCKS_PER_DATE = 5


def _finite_pair(scores: pd.Series, values: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    s = pd.to_numeric(scores, errors="coerce").to_numpy(dtype=float)
    v = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(s) & np.isfinite(v)
    return s[mask], v[mask]


def spearman_rank_ic(scores: pd.Series, values: pd.Series) -> float | None:
    """Spearman 秩相关。任一变量为常量时返回 ``None``（不填 0）。"""
    s, v = _finite_pair(scores, values)
    if len(s) < 3:
        return None
    ranked_s = pd.Series(s).rank().to_numpy(dtype=float)
    ranked_v = pd.Series(v).rank().to_numpy(dtype=float)
    if ranked_s.std() == 0 or ranked_v.std() == 0:
        return None
    return round(float(np.corrcoef(ranked_s, ranked_v)[0, 1]), 8)


def _daily_t_stat(daily: list[float]) -> tuple[float | None, float | None, int]:
    """对每日统计量序列求均值与 t（自由度 = 日数 − 1）。"""
    arr = np.asarray([value for value in daily if value is not None and np.isfinite(value)], dtype=float)
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


def per_date_rank_ic(
    frame: pd.DataFrame,
    score_col: str,
    value_col: str,
    *,
    date_col: str = "as_of",
    min_stocks: int = MIN_STOCKS_PER_DATE,
) -> dict:
    """按日计算 RankIC，再跨日汇总（date-clustered）。"""
    if frame is None or len(frame) == 0:
        return {"rank_ic_mean": None, "rank_ic_t": None, "rank_ic_dates": 0,
                "rank_ic_std": None, "rank_ic_positive_ratio": None}
    daily: list[float] = []
    for _key, group in frame.groupby(date_col, sort=True):
        if len(group) < min_stocks:
            continue
        ic = spearman_rank_ic(group[score_col], group[value_col])
        daily.append(ic)  # type: ignore[arg-type]
    usable = [value for value in daily if value is not None]
    mean, t_stat, n = _daily_t_stat(usable)
    std = round(float(np.std(usable, ddof=1)), 8) if len(usable) > 1 else None
    positive_ratio = round(float(np.mean([value > 0 for value in usable])), 6) if usable else None
    return {
        "rank_ic_mean": mean,
        "rank_ic_std": std,
        "rank_ic_t": t_stat,
        "rank_ic_dates": n,
        "rank_ic_positive_ratio": positive_ratio,
    }


def date_equal_weighted_mean(
    frame: pd.DataFrame,
    value_col: str,
    *,
    date_col: str = "as_of",
    min_stocks: int = 1,
) -> dict:
    """按日求均值后再跨日平均（date-clustered）；同时给出 pooled 对照。"""
    if frame is None or len(frame) == 0 or value_col not in frame.columns:
        return {"pooled_mean": None, "date_mean": None, "date_t": None,
                "date_count": 0, "row_count": 0}
    numeric = pd.to_numeric(frame[value_col], errors="coerce")
    usable = frame.assign(__value=numeric).dropna(subset=["__value"])
    pooled = round(float(usable["__value"].mean()), 8) if len(usable) else None
    daily = [
        float(group["__value"].mean())
        for _key, group in usable.groupby(date_col, sort=True)
        if len(group) >= min_stocks
    ]
    mean, t_stat, n = _daily_t_stat(daily)
    return {
        "pooled_mean": pooled,
        "date_mean": mean,
        "date_t": t_stat,
        "date_count": n,
        "row_count": int(len(usable)),
    }


def group_returns(
    frame: pd.DataFrame,
    group_col: str,
    value_col: str,
    *,
    date_col: str = "as_of",
    min_stocks: int = MIN_STOCKS_PER_DATE,
) -> dict[str, dict]:
    """分组收益：每组 = 该组行值去重后的均值（date-clustered + pooled 双口径）。"""
    if frame is None or len(frame) == 0 or group_col not in frame.columns:
        return {}
    out: dict[str, dict] = {}
    for key, group in frame.groupby(group_col, dropna=False, sort=True):
        stats = date_equal_weighted_mean(group, value_col, date_col=date_col, min_stocks=min_stocks)
        stats["group"] = str(key)
        out[str(key)] = stats
    return out


def long_short_spread(
    frame: pd.DataFrame,
    hit_col: str,
    value_col: str,
    *,
    date_col: str = "as_of",
    min_stocks: int = MIN_STOCKS_PER_DATE,
) -> dict:
    """研究用 long-short spread = 命中组均值 − 未命中组均值（同日配对，再跨日平均）。

    这是**研究统计量**：它回答"命中与未命中的横截面收益差有多大"，
    不构成可交易策略（无交易成本 / 无卖空可行性 / 无涨跌停约束）。
    """
    if frame is None or len(frame) == 0 or hit_col not in frame.columns:
        return {"long_short_spread": None, "spread_t": None, "spread_dates": 0,
                "hit_mean": None, "non_hit_mean": None}
    daily_spreads: list[float] = []
    hit_means: list[float] = []
    non_hit_means: list[float] = []
    hit = frame[hit_col].astype(bool)
    for _key, group in frame.groupby(date_col, sort=True):
        if len(group) < min_stocks:
            continue
        group_hit = group[hit.loc[group.index]]
        group_rest = group[~hit.loc[group.index]]
        if group_hit.empty or group_rest.empty:
            continue
        a = pd.to_numeric(group_hit[value_col], errors="coerce").dropna()
        b = pd.to_numeric(group_rest[value_col], errors="coerce").dropna()
        if a.empty or b.empty:
            continue
        daily_spreads.append(float(a.mean() - b.mean()))
        hit_means.append(float(a.mean()))
        non_hit_means.append(float(b.mean()))
    mean, t_stat, n = _daily_t_stat(daily_spreads)
    hit_mean, _hit_t, _hit_n = _daily_t_stat(hit_means)
    rest_mean, _rest_t, _rest_n = _daily_t_stat(non_hit_means)
    return {
        "long_short_spread": mean,
        "spread_t": t_stat,
        "spread_dates": n,
        "hit_mean": hit_mean,
        "non_hit_mean": rest_mean,
    }


def _ols(y: np.ndarray, x: np.ndarray) -> np.ndarray | None:
    """最小二乘；秩不足或样本过少返回 ``None``（不静默给伪系数）。"""
    if len(y) <= x.shape[1]:
        return None
    beta, residuals, rank, _sv = np.linalg.lstsq(x, y, rcond=None)
    if rank < x.shape[1]:
        return None
    if not np.all(np.isfinite(beta)):
        return None
    _ = residuals
    return beta


def style_neutralize(
    frame: pd.DataFrame,
    value_col: str,
    exposure_cols: list[str],
    *,
    date_col: str = "as_of",
    min_stocks: int = 20,
    output_col: str = "style_residual",
) -> tuple[pd.DataFrame, dict]:
    """在每个横截面上对风格暴露回归并取残差（追加列，不覆盖原值）。

    Returns:
        ``(frame_with_residual, diagnostics)``；``diagnostics`` 含逐日 R² 均值与
        参与日数。风格列缺失的行同样保留（残差为 NaN），不做插补。
    """
    out = frame.copy()
    out[output_col] = np.nan
    out["style_residual_available"] = False
    r2_values: list[float] = []
    dates_used = 0
    if frame is None or len(frame) == 0 or not exposure_cols:
        return out, {"style_r2_mean": None, "style_dates_used": 0, "exposure_columns": []}

    usable_cols = [column for column in exposure_cols if column in out.columns]
    if not usable_cols:
        return out, {"style_r2_mean": None, "style_dates_used": 0, "exposure_columns": []}

    for _key, group in out.groupby(date_col, sort=True):
        sub = group[[value_col, *usable_cols]].apply(pd.to_numeric, errors="coerce")
        mask = sub.notna().all(axis=1).to_numpy()
        if int(mask.sum()) < max(min_stocks, len(usable_cols) + 2):
            continue
        y = sub.loc[mask, value_col].to_numpy(dtype=float)
        x = np.column_stack([
            np.ones(int(mask.sum())),
            *[sub.loc[mask, column].to_numpy(dtype=float) for column in usable_cols],
        ])
        beta = _ols(y, x)
        if beta is None:
            continue
        fitted = x @ beta
        residual = y - fitted
        ss_res = float(np.sum(residual ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        if ss_tot > 0:
            r2_values.append(1.0 - ss_res / ss_tot)
        idx = group.index[mask]
        out.loc[idx, output_col] = residual
        out.loc[idx, "style_residual_available"] = True
        dates_used += 1
    diagnostics = {
        "style_r2_mean": round(float(np.mean(r2_values)), 6) if r2_values else None,
        "style_dates_used": dates_used,
        "exposure_columns": list(usable_cols),
    }
    return out, diagnostics


def controlled_hit_coefficient(
    frame: pd.DataFrame,
    value_col: str,
    hit_col: str,
    control_cols: list[str],
    *,
    date_col: str = "as_of",
    min_stocks: int = 20,
) -> dict:
    """在控制风格暴露后，估计"命中"虚拟变量的横截面系数（逐日估计再平均）。

    逐日模型：``value ~ 1 + controls + hit``；报告 ``hit`` 的系数均值与 t。
    系数是"命中相对未命中、在风格暴露相同条件下的收益差"，
    与 long-short 的差在于它**控制了暴露**，因此可以直接回答 Q-E5。
    """
    if frame is None or len(frame) == 0 or hit_col not in frame.columns:
        return {"hit_coefficient": None, "hit_coefficient_t": None,
                "hit_coefficient_dates": 0, "control_columns": []}
    usable_cols = [column for column in control_cols if column in frame.columns]
    daily: list[float] = []
    for _key, group in frame.groupby(date_col, sort=True):
        columns = [value_col, hit_col, *usable_cols]
        sub = group[columns].copy()
        sub[value_col] = pd.to_numeric(sub[value_col], errors="coerce")
        for column in usable_cols:
            sub[column] = pd.to_numeric(sub[column], errors="coerce")
        sub[hit_col] = sub[hit_col].astype(bool).astype(float)
        mask = sub.notna().all(axis=1).to_numpy()
        n = int(mask.sum())
        if n < max(min_stocks, len(usable_cols) + 3):
            continue
        y = sub.loc[mask, value_col].to_numpy(dtype=float)
        x = np.column_stack([
            np.ones(n),
            *[sub.loc[mask, column].to_numpy(dtype=float) for column in usable_cols],
            sub.loc[mask, hit_col].to_numpy(dtype=float),
        ])
        beta = _ols(y, x)
        if beta is None:
            continue
        daily.append(float(beta[-1]))
    mean, t_stat, n_dates = _daily_t_stat(daily)
    return {
        "hit_coefficient": mean,
        "hit_coefficient_t": t_stat,
        "hit_coefficient_dates": n_dates,
        "control_columns": list(usable_cols),
    }


__all__ = [
    "MIN_STOCKS_PER_DATE",
    "controlled_hit_coefficient",
    "date_equal_weighted_mean",
    "group_returns",
    "long_short_spread",
    "per_date_rank_ic",
    "spearman_rank_ic",
    "style_neutralize",
]
