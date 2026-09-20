"""Phase 3E · 中性化研究执行器。

回答的问题（GOAL §3E-5）
------------------------
    Q-E1  Bazi calibrated 的 OOS 结果做 market neutral 后是否改变？
    Q-E2  Ziwei 是否存在市场暴露解释？
    Q-E3  Huangli 的日期效应是否其实是市场-wide calendar effect？
    Q-E4  Consensus 在控制市场后是否仍然 NO_SIGNAL？
    Q-E5  任何看似较好的结果，是否被 size / momentum / volatility 解释？

输出结构
--------
每个 ``(对象, 出生模型, 分区, 持有期)`` 一行，字段分四组：

1. **市场中性**：``mean_raw_return`` / ``mean_benchmark_return`` /
   ``mean_market_excess_return``。市场中性化 = 减去同区间基准收益，
   因此第三列就是市场中性化后的效应量。
2. **横截面**：``rank_ic_*``（因子分数或事件命中 vs 未来超额）、
   ``hit_mean`` / ``non_hit_mean`` / ``long_short_spread``。
3. **风格中性**：``style_neutral_hit_mean``（风格正交化后的残差均值）与
   ``controlled_hit_coefficient``（控制风格后命中虚拟变量的系数），
   以及 ``style_r2_mean``（风格横截面能解释多少收益方差）。
4. **日期效应**：命中是否只是"选了某些日期"。

计算纪律
--------
* 风格残差与板块去均值**只依赖 (出生模型, 分区, 持有期)**，与对象无关，
  因此按这三个键缓存复用（避免 648 次重复回归）。
* 所有统计的显著性以**日期**为观测单位（date-clustered）；
  行级 pooled 数值同时保留用于对照。
* 本模块不产出任何"可交易"表述：long-short 只是研究统计量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.research.neutralization import cross_section as xs
from src.research.neutralization.benchmark import (
    attach_market_excess,
    benchmark_policy,
    market_neutral_summary,
)
from src.research.neutralization.date_effect import (
    date_effect_analysis,
    date_effect_rows,
)
from src.research.neutralization.exposures import (
    STYLE_EXPOSURE_COLUMNS,
    exposure_availability,
)
from src.research.neutralization.industry import (
    UnavailableIndustryProvider,
    segment_neutralize,
)
from src.research.oos.registry import HypothesisSpec

#: 中性化研究口径版本
NEUTRALIZATION_VERSION = "phase3e-neutralization-v1"
#: 单引擎对象 → 用于 RankIC 的分数列前缀（raw 用归一化前的原始分）
_SINGLE_ENGINE_OBJECTS: dict[str, tuple[str, str]] = {
    "bazi_raw": ("bazi", "score_"),
    "bazi_calibrated": ("bazi", "pct_"),
    "ziwei_raw": ("ziwei", "score_"),
    "ziwei_calibrated": ("ziwei", "pct_"),
    "huangli_raw": ("huangli", "score_"),
    "huangli_calibrated": ("huangli", "pct_"),
}
#: 多引擎对象：没有单一连续分数，RankIC 只能基于事件命中（不做自造合成分数）
MULTI_ENGINE_RANK_IC_NOTE = "NOT_APPLICABLE_MULTI_ENGINE"


@dataclass
class NeutralizationOutcome:
    """一次 3E 运行的完整结果。"""

    rows: list[dict] = field(default_factory=list)
    date_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


def _partition_of(object_frame: pd.DataFrame, partition: str) -> pd.DataFrame:
    return object_frame[object_frame["partition"] == partition]


def _base_key_rows(
    frame: pd.DataFrame,
    horizons: tuple[int, ...],
) -> dict[tuple[str, str, int], dict]:
    """按 (出生模型, 分区, 持有期) 预计算与对象无关的风格/板块中性列。

    Returns:
        ``{(birth_model, partition, horizon): {"frame": DataFrame, "style": {...},
        "segment_available": bool}}``；``frame`` 已含
        ``style_residual_<h>d`` 与 ``segment_neutral_<h>d`` 两列。
    """
    base: dict[tuple[str, str, int], dict] = {}
    for birth_model, by_model in frame.groupby("birth_model", sort=True):
        for partition, by_partition in by_model.groupby("partition", sort=True):
            for horizon in horizons:
                excess_col = f"market_excess_return_{horizon}d"
                work = by_partition.copy()
                work = work[pd.to_numeric(work[excess_col], errors="coerce").notna()]
                if work.empty:
                    base[(birth_model, partition, horizon)] = {
                        "frame": work, "style": {}, "segment_available": False,
                        "residual_col": f"style_residual_{horizon}d",
                        "segment_col": f"segment_neutral_{horizon}d",
                    }
                    continue
                residual_col = f"style_residual_{horizon}d"
                work, style_diag = xs.style_neutralize(
                    work, excess_col, list(STYLE_EXPOSURE_COLUMNS),
                    output_col=residual_col,
                )
                seg = segment_neutralize(work, excess_col)
                segment_col = f"segment_neutral_{horizon}d"
                work[segment_col] = seg["segment_neutral_value"].to_numpy()
                segment_available = bool(
                    work[segment_col].notna().any() and work["segment"].nunique() > 1
                )
                style_diag["segment_available"] = segment_available
                base[(birth_model, partition, horizon)] = {
                    "frame": work,
                    "style": style_diag,
                    "segment_available": segment_available,
                    "residual_col": residual_col,
                    "segment_col": segment_col,
                }
    return base


def _date_clustered_hit_stats(
    work: pd.DataFrame,
    hit_col: str,
    value_col: str,
    *,
    min_stocks: int = xs.MIN_STOCKS_PER_DATE,
) -> dict:
    """命中组的 date-clustered 均值（同时给出 pooled 均值与命中行数）。"""
    if value_col not in work.columns:
        return {"date_mean": None, "date_t": None, "date_count": 0,
                "pooled_mean": None, "row_count": 0}
    hits = work[work[hit_col]]
    return xs.date_equal_weighted_mean(hits, value_col, min_stocks=min_stocks)


def run_neutralization(
    *,
    dataset,  # type: ignore[no-untyped-def]
    horizons: tuple[int, ...] | None = None,
    primary_horizon: int = 20,
    include_date_effect: bool = True,
) -> NeutralizationOutcome:
    """对全部预注册对象 × 出生模型 × 分区 × 持有期执行中性化分析。"""
    frame = dataset.frame
    if frame.empty:
        raise ValueError("研究数据集为空，无法执行中性化分析")
    horizons = horizons or dataset.split.horizons
    registry = dataset.registry
    specs: dict[str, HypothesisSpec] = {spec.object_id: spec for spec in registry.hypotheses}

    base = _base_key_rows(frame, horizons)
    rows: list[dict] = []
    date_tables: dict[str, pd.DataFrame] = {}

    for spec in registry.hypotheses:
        hit_col = "hit"
        for birth_model in dataset.birth_models:
            for partition in ("TRAIN", "VALIDATION", "OOS"):
                if (birth_model, partition, horizons[0]) not in base:
                    continue
                for horizon in horizons:
                    entry = base[(birth_model, partition, horizon)]
                    work = entry["frame"]
                    if work.empty:
                        continue
                    work = work.assign(**{hit_col: work[f"hit__{spec.object_id}"]})
                    excess_col = f"market_excess_return_{horizon}d"
                    row: dict = {
                        "neutralization_version": NEUTRALIZATION_VERSION,
                        "object_id": spec.object_id,
                        "hypothesis_id": spec.hypothesis_id,
                        "engines": "+".join(spec.engines),
                        "direction_source": spec.direction_source,
                        "logic": spec.logic,
                        "expected_direction": spec.expected_direction,
                        "birth_model": birth_model,
                        "partition": partition,
                        "horizon": horizon,
                        "is_primary_horizon": horizon == primary_horizon,
                        "eligible_row_count": int(len(work)),
                        "hit_row_count": int(work[hit_col].sum()),
                        "hit_share": round(float(work[hit_col].mean()), 6),
                    }
                    # --- 1. 市场中性 ---
                    # panel_*：该分区全部合格 (股票, 日期) 对 —— 是"这段样本整体怎样"的基线
                    panel_stats = market_neutral_summary(work, horizon)
                    row.update({f"panel_{key}": value for key, value in panel_stats.items()})
                    # hit_*：本对象命中子集 —— 才是"这个对象本身"的效应
                    hits = work[work[hit_col]]
                    hit_stats_neutral = market_neutral_summary(hits, horizon)
                    row.update({f"hit_{key}": value for key, value in hit_stats_neutral.items()})
                    # --- 2. 横截面 ---
                    pooled_hit = (
                        round(float(pd.to_numeric(hits[excess_col], errors="coerce").mean()), 8)
                        if len(hits) else None
                    )
                    row["pooled_hit_mean_market_excess"] = pooled_hit
                    hit_stats = xs.date_equal_weighted_mean(hits, excess_col)
                    row["hit_date_mean_market_excess"] = hit_stats["date_mean"]
                    row["hit_date_t_market_excess"] = hit_stats["date_t"]
                    non_hits = work[~work[hit_col]]
                    row["non_hit_pooled_mean_market_excess"] = (
                        round(float(pd.to_numeric(non_hits[excess_col], errors="coerce").mean()), 8)
                        if len(non_hits) else None
                    )
                    spread = xs.long_short_spread(work, hit_col, excess_col)
                    row["long_short_spread"] = spread["long_short_spread"]
                    row["long_short_spread_t"] = spread["spread_t"]
                    row["long_short_spread_dates"] = spread["spread_dates"]

                    hit_ic = xs.per_date_rank_ic(
                        work.assign(__hit=work[hit_col].astype(float)),
                        "__hit", excess_col,
                    )
                    row["event_rank_ic_mean"] = hit_ic["rank_ic_mean"]
                    row["event_rank_ic_t"] = hit_ic["rank_ic_t"]
                    row["event_rank_ic_dates"] = hit_ic["rank_ic_dates"]

                    engine_info = _SINGLE_ENGINE_OBJECTS.get(spec.object_id)
                    if engine_info is not None:
                        engine, prefix = engine_info
                        score_col = f"{prefix}{engine}"
                        if score_col in work.columns:
                            score_ic = xs.per_date_rank_ic(work, score_col, excess_col)
                            row["factor_rank_ic_mean"] = score_ic["rank_ic_mean"]
                            row["factor_rank_ic_t"] = score_ic["rank_ic_t"]
                            row["factor_rank_ic_dates"] = score_ic["rank_ic_dates"]
                            row["factor_rank_ic_source"] = score_col
                        else:
                            row["factor_rank_ic_mean"] = None
                            row["factor_rank_ic_t"] = None
                            row["factor_rank_ic_dates"] = 0
                            row["factor_rank_ic_source"] = "MISSING_COLUMN"
                    else:
                        row["factor_rank_ic_mean"] = None
                        row["factor_rank_ic_t"] = None
                        row["factor_rank_ic_dates"] = 0
                        row["factor_rank_ic_source"] = MULTI_ENGINE_RANK_IC_NOTE

                    # --- 3. 风格 / 板块中性 ---
                    style_diag = entry["style"]
                    row["style_r2_mean"] = style_diag.get("style_r2_mean")
                    row["style_dates_used"] = style_diag.get("style_dates_used", 0)
                    row["style_exposure_columns"] = ",".join(
                        str(column) for column in style_diag.get("exposure_columns", [])
                    )
                    residual_col = entry["residual_col"]
                    resid_stats = _date_clustered_hit_stats(work, hit_col, residual_col)
                    row["style_neutral_hit_mean"] = resid_stats["date_mean"]
                    row["style_neutral_hit_t"] = resid_stats["date_t"]
                    row["style_neutral_hit_dates"] = resid_stats["date_count"]
                    row["style_neutral_hit_pooled_mean"] = resid_stats["pooled_mean"]
                    controlled = xs.controlled_hit_coefficient(
                        work, excess_col, hit_col, list(STYLE_EXPOSURE_COLUMNS),
                    )
                    row["controlled_hit_coefficient"] = controlled["hit_coefficient"]
                    row["controlled_hit_coefficient_t"] = controlled["hit_coefficient_t"]
                    row["controlled_hit_coefficient_dates"] = controlled["hit_coefficient_dates"]

                    segment_col = entry["segment_col"]
                    row["segment_available"] = bool(entry["segment_available"])
                    if entry["segment_available"]:
                        seg_stats = _date_clustered_hit_stats(work, hit_col, segment_col)
                        row["segment_neutral_hit_mean"] = seg_stats["date_mean"]
                        row["segment_neutral_hit_t"] = seg_stats["date_t"]
                    else:
                        row["segment_neutral_hit_mean"] = None
                        row["segment_neutral_hit_t"] = None

                    # 风格解释占比：命中均值被风格解释掉多少
                    if row.get("hit_date_mean_market_excess") not in (None, 0) and \
                            row.get("style_neutral_hit_mean") is not None:
                        raw_effect = float(row["hit_date_mean_market_excess"])
                        if raw_effect != 0:
                            row["style_explained_share"] = round(
                                1.0 - float(row["style_neutral_hit_mean"]) / raw_effect, 6,
                            )
                        else:
                            row["style_explained_share"] = None
                    else:
                        row["style_explained_share"] = None

                    # --- 4. 日期效应 ---
                    if include_date_effect:
                        effect = date_effect_analysis(work, hit_col, horizon)
                        row["date_count"] = effect["date_count"]
                        row["stock_count_per_date_mean"] = effect["stock_count_per_date"]["mean"]
                        row["stock_count_per_date_min"] = effect["stock_count_per_date"]["min"]
                        row["stock_count_per_date_max"] = effect["stock_count_per_date"]["max"]
                        row["cross_sectional_mean_return"] = effect["cross_sectional_mean_return"]
                        row["market_return"] = effect["market_return"]
                        row["market_excess_date_mean"] = effect["market_excess"]
                        row["market_excess_date_t"] = effect["date_clustered"]["t"]
                        row["hit_dates_count"] = (effect["hit_dates"] or {}).get("date_count")
                        row["hit_dates_market_excess"] = (effect["hit_dates"] or {}).get(
                            "market_excess_mean"
                        )
                        row["non_hit_dates_count"] = (effect["non_hit_dates"] or {}).get("date_count")
                        row["non_hit_dates_market_excess"] = (effect["non_hit_dates"] or {}).get(
                            "market_excess_mean"
                        )
                        row["hit_vs_non_hit_date_difference"] = effect[
                            "date_clustered_difference"
                        ]["difference"]
                        row["hit_vs_non_hit_date_welch_t"] = effect[
                            "date_clustered_difference"
                        ]["welch_t"]
                        row["hit_share_slope"] = effect["hit_share_slope"]["slope"]
                        row["hit_share_slope_t"] = effect["hit_share_slope"]["t"]
                        row["date_binary_split_usable"] = effect["binary_split_usable"]
                        median_split = effect.get("median_split") or {}
                        row["hit_share_median"] = median_split.get("median_hit_share")
                        row["above_median_hit_share_date_excess"] = (
                            median_split.get("above_median") or {}
                        ).get("market_excess_mean")
                        row["below_median_hit_share_date_excess"] = (
                            median_split.get("below_median") or {}
                        ).get("market_excess_mean")
                        row["median_split_date_difference"] = median_split.get("difference")
                        row["median_split_welch_t"] = median_split.get("welch_t")
                        row["event_rows_vs_dates"] = (
                            f"{effect['event_row_count_vs_date_count']['event_rows']}"
                            f"/{effect['event_row_count_vs_date_count']['dates']}"
                        )
                        if spec.object_id in {
                            "huangli_raw", "huangli_calibrated",
                        } and horizon == primary_horizon:
                            date_tables[
                                f"{spec.object_id}__{birth_model}__{partition}"
                            ] = date_effect_rows(work, hit_col, horizon)
                    rows.append(row)

    meta = {
        "neutralization_version": NEUTRALIZATION_VERSION,
        "benchmark": benchmark_policy().to_dict(),
        "exposures": exposure_availability().to_dict(),
        "industry": UnavailableIndustryProvider().status().to_dict(),
        "primary_horizon": primary_horizon,
        "horizons": list(horizons),
        "object_count": len(specs),
        "row_count": len(rows),
        "segments": sorted({
            str(value) for value in frame.get("segment", pd.Series(dtype=str)).unique()
        }) if "segment" in frame.columns else [],
    }
    return NeutralizationOutcome(rows=rows, date_tables=date_tables, meta=meta)


def _clean(value: Any) -> Any:
    """把 numpy/pandas 的 NaN、Inf 与 numpy 标量转成 JSON 友好的 Python 值。

    ``json.dumps`` 默认会写出裸 ``NaN``（非法 JSON），报告消费方会解析失败，
    因此所有对外产物在序列化前必须经过本函数。
    """
    if value is None:
        return None
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(float(value)) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def _row_dict(row: pd.Series, fields: list[str]) -> dict:
    return {field: _clean(row.get(field)) for field in fields}


def answer_questions(rows: list[dict], *, primary_horizon: int = 20) -> dict:
    """把结果表收敛成 GOAL §3E-5 的 Q-E1..Q-E5 逐条回答（OOS，主持有期）。"""
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}
    oos = frame[(frame["partition"] == "OOS") & (frame["horizon"] == primary_horizon)]

    def _pick(object_id: str, birth_model: str) -> dict | None:
        sub = oos[(oos["object_id"] == object_id) & (oos["birth_model"] == birth_model)]
        if sub.empty:
            return None
        return sub.iloc[0].to_dict()

    answers: dict[str, Any] = {}
    # Q-E1：Bazi calibrated 在 OOS 做 market neutral 后是否改变
    q1: list[dict] = []
    for model in sorted(oos["birth_model"].unique()):
        row = _pick("bazi_calibrated", str(model))
        if row is None:
            continue
        q1.append({
            "birth_model": model,
            **_row_dict(row, [
                "hit_sample_count", "hit_mean_raw_return", "hit_mean_benchmark_return",
                "hit_mean_market_excess_return", "hit_date_mean_market_excess",
                "style_neutral_hit_mean", "controlled_hit_coefficient",
                "controlled_hit_coefficient_t", "style_explained_share",
            ]),
        })
    answers["Q-E1_bazi_calibrated_market_neutral"] = q1

    # Q-E2：Ziwei 是否可由市场暴露解释
    q2: list[dict] = []
    for object_id in ("ziwei_raw", "ziwei_calibrated"):
        for model in sorted(oos["birth_model"].unique()):
            row = _pick(object_id, str(model))
            if row is None:
                continue
            q2.append({
                "object_id": object_id,
                "birth_model": model,
                **_row_dict(row, [
                    "hit_sample_count", "hit_mean_raw_return", "hit_mean_benchmark_return",
                    "hit_mean_market_excess_return", "hit_date_mean_market_excess",
                    "event_rank_ic_mean", "factor_rank_ic_mean",
                    "controlled_hit_coefficient", "controlled_hit_coefficient_t",
                ]),
            })
    answers["Q-E2_ziwei_market_exposure"] = q2

    # Q-E3：Huangli 日期效应是否等于市场-wide calendar effect
    q3: list[dict] = []
    for object_id in ("huangli_raw", "huangli_calibrated"):
        for model in sorted(oos["birth_model"].unique()):
            row = _pick(object_id, str(model))
            if row is None:
                continue
            q3.append({
                "object_id": object_id,
                "birth_model": model,
                **_row_dict(row, [
                    "hit_share", "date_count", "stock_count_per_date_mean",
                    "market_excess_date_mean", "market_excess_date_t",
                    "date_binary_split_usable",
                    "hit_dates_count", "hit_dates_market_excess",
                    "non_hit_dates_count", "non_hit_dates_market_excess",
                    "hit_vs_non_hit_date_difference", "hit_vs_non_hit_date_welch_t",
                    "hit_share_median",
                    "above_median_hit_share_date_excess",
                    "below_median_hit_share_date_excess",
                    "median_split_date_difference", "median_split_welch_t",
                    "hit_share_slope", "hit_share_slope_t",
                ]),
            })
    answers["Q-E3_huangli_calendar_effect"] = q3

    # Q-E4：Consensus 控制市场后是否仍 NO_SIGNAL
    q4: list[dict] = []
    for object_id in (
        "bazi_ziwei_calibrated", "all_three_calibrated",
    ):
        for model in sorted(oos["birth_model"].unique()):
            row = _pick(object_id, str(model))
            if row is None:
                continue
            q4.append({
                "object_id": object_id,
                "birth_model": model,
                **_row_dict(row, [
                    "hit_row_count", "hit_sample_count",
                    "hit_mean_market_excess_return", "hit_date_mean_market_excess",
                    "style_neutral_hit_mean", "controlled_hit_coefficient",
                    "controlled_hit_coefficient_t", "event_rank_ic_mean",
                ]),
            })
    answers["Q-E4_consensus_after_market_control"] = q4

    # Q-E5：看似较好的结果是否被 size/momentum/volatility 解释
    interesting = oos.copy()
    interesting["_effect"] = pd.to_numeric(
        interesting["hit_date_mean_market_excess"], errors="coerce",
    )
    interesting = interesting[interesting["hit_row_count"] >= 100]
    interesting = interesting.sort_values("_effect", ascending=False)
    q5: list[dict] = []
    for _idx, row in interesting.head(10).iterrows():
        q5.append({
            "object_id": row["object_id"],
            "birth_model": row["birth_model"],
            **_row_dict(row, [
                "hit_row_count", "hit_date_mean_market_excess", "style_neutral_hit_mean",
                "controlled_hit_coefficient", "controlled_hit_coefficient_t",
                "style_explained_share", "style_r2_mean", "segment_neutral_hit_mean",
            ]),
        })
    answers["Q-E5_top_results_style_explained"] = q5
    return answers


__all__ = [
    "MULTI_ENGINE_RANK_IC_NOTE",
    "NEUTRALIZATION_VERSION",
    "NeutralizationOutcome",
    "answer_questions",
    "attach_market_excess",
    "run_neutralization",
]
