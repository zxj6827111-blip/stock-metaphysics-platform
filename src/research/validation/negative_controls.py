"""负对照（architecture §44）—— 本项目可信度的核心模块。

必须实现四类对照：

    1. 随机出生日期        打乱股票的出生时间，重新排盘、重新算因子
    2. 出生日期 +7 天      平移一周（保留星期结构，破坏具体日期）
    3. 出生日期 −7 天      同上，反向
    4. 随机因子            用同分布随机分数替换真实因子分数

**输出纪律**

如果真实术数因子并不优于随机结果，必须**如实输出**，不得隐藏、不得美化。
``NegativeControlResult.verdict`` 会取 ``outperform`` / ``tie`` / ``underperform`` /
``inconclusive``，并提供人类可读的 ``verdict_note``。
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.core.config import settings
from src.core.schemas.common import Warning_
from src.core.schemas.market import (
    EventStudyRequest,
    HorizonStats,
    NegativeControlKind,
    NegativeControlReport,
    NegativeControlResult,
)
from src.research.event_study.engine import evaluate_event_study, extract_event_keys

#: 判定为「更优」所需的最小差异（20 日平均收益）
OUTPERFORM_EPSILON = 0.002
#: 判定所需的最小样本数
MIN_VERDICT_SAMPLE = 20
#: 事件集合独立性阈值：Jaccard 超过该值说明对照与真实组几乎相同，对照失效
JACCARD_NOT_INDEPENDENT = 0.9


def _excess(hs: HorizonStats | None) -> float | None:
    return hs.mean_excess_return if hs else None


def _independence(
    real_keys: set | None,
    control_keys: set | None,
    warnings: list[Warning_],
) -> dict:
    """计算事件集合独立性诊断并追加告警。"""
    out: dict = {}
    if real_keys is None or control_keys is None:
        return out
    inter = len(real_keys & control_keys)
    union = len(real_keys | control_keys)
    jaccard = (inter / union) if union else 0.0
    out["real_event_count"] = len(real_keys)
    out["event_count"] = len(control_keys)
    out["overlap_with_real"] = inter
    out["jaccard_with_real"] = round(jaccard, 6)
    if union and jaccard > JACCARD_NOT_INDEPENDENT:
        warnings.append(Warning_(
            code="NEGATIVE_CONTROL_NOT_INDEPENDENT",
            message=(
                f"对照事件集合与真实集合 Jaccard={jaccard:.3f} > {JACCARD_NOT_INDEPENDENT}"
                f"（交集 {inter}/{union}）。负对照无法区分真实因子与对照，"
                "任何 tie 都不能解读为「没有信息量」的证据 —— 这是方法失效。"
            ),
            severity="error",
            context={"jaccard": round(jaccard, 6), "overlap": inter, "union": union},
        ))
    return out


def _verdict(
    real: HorizonStats | None, control: HorizonStats | None
) -> tuple[str, str, dict]:
    """比较真实与对照，返回 (verdict, note, deltas)。"""
    if real is None or control is None or real.sample_count == 0 or control.sample_count == 0:
        return "inconclusive", "真实组或对照组样本为空，无法比较。", {}

    delta_ret = (real.mean_return or 0.0) - (control.mean_return or 0.0)
    delta_up = (real.up_rate or 0.0) - (control.up_rate or 0.0)
    deltas = {
        "delta_mean_return_20d": round(delta_ret, 6),
        "delta_up_rate_20d": round(delta_up, 6),
    }

    if min(real.sample_count, control.sample_count) < MIN_VERDICT_SAMPLE:
        return (
            "inconclusive",
            f"样本数不足（真实 {real.sample_count} / 对照 {control.sample_count}，"
            f"阈值 {MIN_VERDICT_SAMPLE}），无法判定真实因子是否优于随机。",
            deltas,
        )

    if delta_ret > OUTPERFORM_EPSILON and delta_up > 0:
        return (
            "outperform",
            f"真实因子 20 日平均收益高于对照 {delta_ret:.4%}，上涨率高出 {delta_up:.2%}。"
            "注意：这仍可能来自市场环境差异与多重检验，需样本外验证。",
            deltas,
        )
    if delta_ret < -OUTPERFORM_EPSILON and delta_up < 0:
        return (
            "underperform",
            f"真实因子表现**弱于**对照（平均收益低 {abs(delta_ret):.4%}，上涨率低 {abs(delta_up):.2%}）。"
            "本系统如实输出该结果：在当前样本上，术数因子未显示正向信息量。",
            deltas,
        )
    return (
        "tie",
        f"真实因子与对照无显著差异（平均收益差 {delta_ret:.4%}，上涨率差 {delta_up:.2%}）。"
        "说明在当前样本上，术数因子相较随机未体现增量信息。",
        deltas,
    )


def _stats_by_horizon(result, horizon: int = 20) -> HorizonStats | None:  # type: ignore[no-untyped-def]
    for h in result.horizons:
        if h.horizon == horizon:
            return h
    return None


# ---------------------------------------------------------------------------
# 单类对照
# ---------------------------------------------------------------------------


def random_birth_date_control(
    control_observations: pd.DataFrame,
    labels_by_variant: pd.DataFrame,
    request: EventStudyRequest,
    *,
    real_stats: HorizonStats | None,
    real_keys: set | None = None,
    seed: int | None = None,
) -> NegativeControlResult:
    """随机出生日期对照。

    两个输入都必须是**用随机出生日期重新排盘、重新计算因子**后得到的结果。
    如果拿真实因子去比随机标签，检验的就不是"命盘是否有信息量"了。
    """
    seed = settings.negative_control_seed if seed is None else seed

    result = evaluate_event_study(
        control_observations, labels_by_variant, request, variant="random_birth_date"
    )
    hs = _stats_by_horizon(result, 20)
    verdict, note, deltas = _verdict(real_stats, hs)

    warnings = list(result.warnings)
    independence = _independence(
        real_keys, extract_event_keys(control_observations, request), warnings
    )

    return NegativeControlResult(
        kind=NegativeControlKind.RANDOM_BIRTH_DATE,
        description="把股票出生时间随机打乱后重新排盘、重新计算因子，检验真实命盘是否优于随机命盘。",
        seed=seed,
        horizon_stats=result.horizons,
        real_mean_return_20d=real_stats.mean_return if real_stats else None,
        control_mean_return_20d=hs.mean_return if hs else None,
        real_up_rate_20d=real_stats.up_rate if real_stats else None,
        control_up_rate_20d=hs.up_rate if hs else None,
        real_mean_excess_return_20d=_excess(real_stats),
        control_mean_excess_return_20d=_excess(hs),
        verdict=verdict,
        verdict_note=note,
        warnings=warnings,
        **independence,
        **deltas,
    )


def shift_birth_date_control(
    kind: NegativeControlKind,
    control_observations: pd.DataFrame,
    control_labels: pd.DataFrame,
    request: EventStudyRequest,
    *,
    real_stats: HorizonStats | None,
    days: int,
    real_keys: set | None = None,
) -> NegativeControlResult:
    """出生日期 ±N 天对照。必须使用平移后重算的因子观测。"""
    result = evaluate_event_study(
        control_observations, control_labels, request, variant=str(kind)
    )
    hs = _stats_by_horizon(result, 20)
    verdict, note, deltas = _verdict(real_stats, hs)

    warnings = list(result.warnings)
    independence = _independence(
        real_keys, extract_event_keys(control_observations, request), warnings
    )

    return NegativeControlResult(
        kind=kind,
        description=(
            f"把股票出生时间平移 {days:+d} 天后重新排盘、重新计算因子。"
            "平移保留了星期结构但破坏了具体日期，用于检验真实出生日是否有信息量。"
        ),
        horizon_stats=result.horizons,
        real_mean_return_20d=real_stats.mean_return if real_stats else None,
        control_mean_return_20d=hs.mean_return if hs else None,
        real_up_rate_20d=real_stats.up_rate if real_stats else None,
        control_up_rate_20d=hs.up_rate if hs else None,
        real_mean_excess_return_20d=_excess(real_stats),
        control_mean_excess_return_20d=_excess(hs),
        verdict=verdict,
        verdict_note=note,
        warnings=warnings,
        **independence,
        **deltas,
    )


def random_factor_control(
    observations: pd.DataFrame,
    labels: pd.DataFrame,
    request: EventStudyRequest,
    *,
    real_stats: HorizonStats | None,
    real_keys: set | None = None,
    seed: int | None = None,
) -> NegativeControlResult:
    """随机因子对照。

    保留真实因子的**命中频率与分布**，但把"哪些样本命中"随机打乱，
    从而检验真实因子的**选择性**是否具有信息量。
    """
    seed = settings.negative_control_seed if seed is None else seed
    rng = np.random.default_rng(seed)
    warnings: list[Warning_] = []

    if observations.empty or labels.empty:
        return NegativeControlResult(
            kind=NegativeControlKind.RANDOM_FACTOR,
            description="随机因子对照：无可用观测/标签。",
            seed=seed, verdict="inconclusive", verdict_note="数据为空，无法执行对照。",
            warnings=[Warning_(code="NC_EMPTY", message="观测或标签数据为空", severity="warning")],
        )

    # 真实命中率
    obs = observations.copy()
    if request.factor_ids:
        obs = obs[obs["factor_id"].isin(request.factor_ids)]
    obs = obs[obs["trade_date"].notna()]
    merged = obs[["stock_code", "trade_date"]].drop_duplicates().merge(
        labels, on=["stock_code", "trade_date"], how="inner"
    )
    if merged.empty:
        return NegativeControlResult(
            kind=NegativeControlKind.RANDOM_FACTOR, description="随机因子对照",
            seed=seed, verdict="inconclusive", verdict_note="事件与标签无交集。",
        )
    hit_rate = min(max(len(merged) / max(len(labels), 1), 0.0), 1.0)

    # 随机抽取同比例样本
    n_draw = max(1, int(round(hit_rate * len(labels))))
    idx = rng.choice(len(labels), size=min(n_draw, len(labels)), replace=False)
    random_hits = labels.iloc[np.sort(idx)].copy()

    # 随机因子对照：观测替换为"随机选中的 (股票, 交易日)"，标签保持不变
    synthetic_obs = random_hits.assign(factor_id="RANDOM_FACTOR")[
        ["stock_code", "trade_date", "factor_id"]
    ]
    # 随机因子对照本身已经决定了"哪些样本命中"，不需要再做 activation 过滤
    random_request = request.model_copy(update={
        "activation": "any",
        "factor_ids": [],       # 合成观测的 factor_id 是 RANDOM_FACTOR，不能按目标因子过滤
        "direction_filter": None,
        "min_rule_score": None,
    })
    result = evaluate_event_study(
        synthetic_obs, random_hits, random_request, variant="random_factor"
    )
    hs = _stats_by_horizon(result, 20)
    verdict, note, deltas = _verdict(real_stats, hs)

    # 随机因子的事件集合 = 随机抽中的 (股票, 交易日)；衡量它与真实集合的重合
    control_keys = {
        (str(r.stock_code), r.trade_date) for r in random_hits.itertuples()
    }
    independence = _independence(real_keys, control_keys, warnings)

    warnings.append(Warning_(
        code="NC_RANDOM_FACTOR_METHOD",
        message=(
            f"随机因子保留了真实命中率 {hit_rate:.4f}（随机抽取 {len(random_hits)} 个样本），"
            "只随机化『哪些样本命中』，因此检验的是因子的选择性而非覆盖度。"
        ),
        severity="info",
    ))

    return NegativeControlResult(
        kind=NegativeControlKind.RANDOM_FACTOR,
        description="保持命中比例不变，随机选择命中的（股票, 交易日），检验真实因子的选择性。",
        seed=seed,
        horizon_stats=result.horizons,
        real_mean_return_20d=real_stats.mean_return if real_stats else None,
        control_mean_return_20d=hs.mean_return if hs else None,
        real_up_rate_20d=real_stats.up_rate if real_stats else None,
        control_up_rate_20d=hs.up_rate if hs else None,
        real_mean_excess_return_20d=_excess(real_stats),
        control_mean_excess_return_20d=_excess(hs),
        verdict=verdict,
        verdict_note=note,
        warnings=warnings,
        **independence,
        **deltas,
    )


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def summarize_controls(
    experiment_id: str,
    factor_ids: list[str],
    results: list[NegativeControlResult],
) -> NegativeControlReport:
    """把四类对照汇总成结论。"""
    valid = [r for r in results if r.verdict not in ("inconclusive",)]
    outperform = [r for r in valid if r.verdict == "outperform"]
    underperform = [r for r in valid if r.verdict == "underperform"]
    tie = [r for r in valid if r.verdict == "tie"]

    if not valid:
        conclusion = (
            "本次未能得到有效对照结论（样本不足或数据缺失）。"
            "按项目纪律，系统不给出『术数因子有效』的任何暗示。"
        )
    elif len(underperform) == 0 and len(outperform) > len(tie):
        conclusion = (
            f"在 {len(valid)} 类对照中，有 {len(outperform)} 类显示真实因子优于随机，"
            f"{len(tie)} 类无差异，0 类弱于随机。"
            "即便如此，仍需样本外验证并考虑多重检验与市场环境差异，不能据此宣称预测能力。"
        )
    elif len(outperform) == 0:
        conclusion = (
            f"在 {len(valid)} 类对照中，没有任何一类显示真实术数因子显著优于随机"
            f"（无差异 {len(tie)} 类，弱于随机 {len(underperform)} 类）。"
            "本系统如实输出该结果：当前样本下，术数因子未表现出超越随机的信息量。"
        )
    else:
        conclusion = (
            f"对照结果不一致：优于随机 {len(outperform)} 类、无差异 {len(tie)} 类、"
            f"弱于随机 {len(underperform)} 类。结论为**不确定**，不能宣称有效性。"
        )

    return NegativeControlReport(
        experiment_id=experiment_id,
        factor_ids=factor_ids,
        results=results,
        conclusion=conclusion,
    )


def shifted_dates(d: date, days: int) -> date:
    return d + timedelta(days=days)
