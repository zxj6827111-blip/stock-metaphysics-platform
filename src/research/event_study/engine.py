"""Event Study / 因子历史验证（architecture §16、two_session_plan §12）。

输入：一个 Factor 或 Factor 组合
输出：样本数 / 上涨率 / 平均收益 / 中位数收益 / 超额收益 / 最大回撤

实现基于 pandas + numpy（V1 不强依赖 vectorbt，见 architecture §14）。

**统计纪律**

* 样本不足时必须返回 ``note`` 说明，而不是给出看似精确的比例。
* 同时给出「绝对上涨率」与「超额上涨率」，避免牛市偏差。
* 必须能被负对照模块复用（``variant`` 参数）。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import numpy as np
import pandas as pd

from src.core.config import settings
from src.core.schemas.common import Warning_
from src.core.schemas.market import EventStudyRequest, EventStudyResult, HorizonStats


def _empty_stats(horizon: int, note: str) -> HorizonStats:
    return HorizonStats(horizon=horizon, sample_count=0, note=note)


def compute_horizon_stats(df: pd.DataFrame, horizon: int) -> HorizonStats:
    """对单个持有期计算统计量。

    期望 ``df`` 含列：``ret_{h}d``、``excess_return_20d``（可选）、
    ``max_drawdown_20d``（可选）、``max_return_20d``（可选）。
    """
    col = f"ret_{horizon}d"
    if col not in df.columns:
        return _empty_stats(horizon, f"缺少字段 {col}")

    s = pd.to_numeric(df[col], errors="coerce").dropna()
    n = int(len(s))
    if n == 0:
        return _empty_stats(horizon, "无有效样本")

    # 超额收益 / 最大回撤 / 最大上涨 只有 20D 口径与持有期一致。
    # 把它们套用到 5D/10D/60D 属于指标错配，会误导阅读者，因此只在 20D 输出。
    is_20d = horizon == 20

    def _series(col: str) -> pd.Series:
        if not is_20d or col not in df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(df[col], errors="coerce").dropna()

    excess = _series("excess_return_20d")
    dd = _series("max_drawdown_20d")
    mr = _series("max_return_20d")

    stats = HorizonStats(
        horizon=horizon,
        sample_count=n,
        up_rate=round(float((s > 0).mean()), 6),
        excess_up_rate=round(float((excess > 0).mean()), 6) if len(excess) else None,
        mean_return=round(float(s.mean()), 6),
        median_return=round(float(s.median()), 6),
        std_return=round(float(s.std(ddof=1)), 6) if n > 1 else None,
        mean_excess_return=round(float(excess.mean()), 6) if len(excess) else None,
        max_drawdown=round(float(dd.min()), 6) if len(dd) else None,
        mean_max_return=round(float(mr.mean()), 6) if len(mr) else None,
    )

    basis = f"样本数 {n}"
    if not is_20d:
        basis += "；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）"
    if n < settings.min_event_sample_size:
        stats.note = f"{basis}；低于阈值 {settings.min_event_sample_size}，统计结果不具参考性"
    elif n < 30:
        stats.note = f"{basis}；样本偏少，置信区间较宽"
    else:
        stats.note = basis
    return stats


def evaluate_event_study(
    observations: pd.DataFrame,
    labels: pd.DataFrame,
    request: EventStudyRequest,
    *,
    variant: str = "real",
) -> EventStudyResult:
    """执行一次事件研究。

    Args:
        observations: 因子观测，含 ``stock_code`` / ``trade_date`` / ``factor_id`` /
            ``direction`` / ``rule_score`` / ``as_of``。
        labels: 未来收益标签，含 ``stock_code`` / ``trade_date`` / ``ret_*`` 等。
        request: 研究参数。
        variant: 变体标签（real / random_birth_date / …），用于负对照输出。
    """
    warnings: list[Warning_] = []
    experiment_id = f"ES-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    if observations.empty:
        return EventStudyResult(
            experiment_id=experiment_id, factor_ids=request.factor_ids,
            logic=request.logic, horizons=[_empty_stats(h, "无因子观测") for h in request.horizons],
            warnings=[Warning_(code="ES_NO_OBSERVATION", message="因子观测为空", severity="warning")],
        )

    obs = observations.copy()
    if request.factor_ids:
        obs = obs[obs["factor_id"].isin(request.factor_ids)]
    if request.stock_codes:
        obs = obs[obs["stock_code"].isin(request.stock_codes)]
    if request.date_from is not None:
        obs = obs[pd.to_datetime(obs["trade_date"]).dt.date >= request.date_from]
    if request.date_to is not None:
        obs = obs[pd.to_datetime(obs["trade_date"]).dt.date <= request.date_to]
    if request.direction_filter is not None:
        obs = obs[obs["direction"] == request.direction_filter]
    if request.min_rule_score is not None:
        obs = obs[pd.to_numeric(obs["rule_score"], errors="coerce") >= request.min_rule_score]

    # --- 事件激活条件 ---
    # 关键：如果"命中"只表示"这个因子被计算过"，那么真实组与对照组的事件集合
    # 将完全相同，负对照就毫无意义。因此默认要求该结构实际成立
    # （normalized_value 非 0，即方向判定不为「闲神/中性」）。
    activation = (request.activation or "nonzero").lower()
    if activation != "any":
        if "normalized_value" in obs.columns and obs["normalized_value"].notna().any():
            nv = pd.to_numeric(obs["normalized_value"], errors="coerce").fillna(0.0)
            if activation == "nonzero":
                obs = obs[nv != 0.0]
            elif activation == "positive":
                obs = obs[nv > 0.0]
            elif activation == "negative":
                obs = obs[nv < 0.0]
        elif "direction" in obs.columns:
            if activation == "nonzero":
                obs = obs[obs["direction"] != 0]
            elif activation == "positive":
                obs = obs[obs["direction"] == 1]
            elif activation == "negative":
                obs = obs[obs["direction"] == -1]

    if obs.empty:
        return EventStudyResult(
            experiment_id=experiment_id, factor_ids=request.factor_ids, logic=request.logic,
            horizons=[_empty_stats(h, "过滤后无满足条件的观测") for h in request.horizons],
            warnings=[Warning_(
                code="ES_FILTERED_EMPTY",
                message=(
                    f"过滤条件过严（activation={activation}），事件样本为 0。"
                    "请放宽 direction_filter / min_rule_score / activation。"
                ),
                severity="warning",
            )],
        )

    # 事件聚合：同一 (股票, 交易日) 命中多少个目标因子
    if request.logic == "all" and len(request.factor_ids) > 1:
        grouped = obs.groupby(["stock_code", "trade_date"])["factor_id"].nunique()
        hit = grouped[grouped >= len(request.factor_ids)].reset_index()[["stock_code", "trade_date"]]
    else:
        hit = obs[["stock_code", "trade_date"]].drop_duplicates()

    merged = hit.merge(labels, on=["stock_code", "trade_date"], how="inner")
    if merged.empty:
        return EventStudyResult(
            experiment_id=experiment_id, factor_ids=request.factor_ids, logic=request.logic,
            event_count=int(len(hit)),
            horizons=[_empty_stats(h, "事件与标签无交集（可能因 as_of 之后数据不足）") for h in request.horizons],
            warnings=[Warning_(
                code="ES_NO_LABEL_MATCH",
                message="事件命中但无对应未来收益标签；通常是数据末端附近的事件",
                severity="warning",
            )],
        )

    horizons = request.horizons or list(settings.event_study_horizons)
    stats = [compute_horizon_stats(merged, h) for h in horizons]

    date_from = pd.to_datetime(merged["trade_date"]).dt.date.min() if len(merged) else None
    date_to = pd.to_datetime(merged["trade_date"]).dt.date.max() if len(merged) else None

    return EventStudyResult(
        experiment_id=experiment_id,
        factor_ids=list(request.factor_ids),
        logic=request.logic,
        universe_size=int(merged["stock_code"].nunique()),
        event_count=int(len(merged)),
        date_from=date_from,
        date_to=date_to,
        horizons=stats,
        benchmark_code=request.benchmark_code,
        methodology=(
            f"variant={variant}；事件 = 因子命中（logic={request.logic}, activation={activation}）；"
            "持有期收益按事件日收盘至第 N 个交易日收盘计算；"
            "超额收益相对基准指数；样本要求事件日之后有完整的 N 个交易日数据，"
            "否则该样本被剔除（不用 0 填充）。"
        ),
        warnings=warnings,
    )


def build_observations_frame(rows: list[dict]) -> pd.DataFrame:
    """把 ``factor_observation`` 行集合转成研究用 DataFrame。"""
    if not rows:
        return pd.DataFrame(columns=[
            "stock_code", "trade_date", "as_of", "factor_id", "direction", "rule_score",
        ])
    df = pd.DataFrame(rows)
    for col in ("trade_date", "as_of"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col]).dt.date
    return df


def build_labels_frame(rows: list[dict]) -> pd.DataFrame:
    """把标签行集合转成研究用 DataFrame。"""
    if not rows:
        return pd.DataFrame(columns=[
            "stock_code", "trade_date", *[f"ret_{h}d" for h in settings.label_horizons],
            "excess_return_20d", "max_drawdown_20d", "max_return_20d",
        ])
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def mean_return_by_year(df: pd.DataFrame, horizon: int = 20) -> dict[int, float]:
    """年度稳定性：每年的平均收益。"""
    col = f"ret_{horizon}d"
    if df.empty or col not in df.columns:
        return {}
    tmp = df.copy()
    tmp[col] = pd.to_numeric(tmp[col], errors="coerce")
    tmp["year"] = pd.to_datetime(tmp["trade_date"]).dt.year
    out = tmp.dropna(subset=[col]).groupby("year")[col].mean()
    return {int(y): round(float(v), 6) for y, v in out.items()}


def distribution(df: pd.DataFrame, horizon: int = 20, bins: int = 21) -> dict:
    """收益分布（用于 UI 直方图）。"""
    col = f"ret_{horizon}d"
    if df.empty or col not in df.columns:
        return {"bin_edges": [], "counts": []}
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        return {"bin_edges": [], "counts": []}
    counts, edges = np.histogram(s.to_numpy(), bins=bins)
    return {
        "bin_edges": [round(float(e), 6) for e in edges],
        "counts": [int(c) for c in counts],
    }
