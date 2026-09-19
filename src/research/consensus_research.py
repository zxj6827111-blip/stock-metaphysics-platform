"""多模型共振 / 冲突的历史研究（Phase 2C）。

它回答什么问题
--------------
"三个术数模型都说好" 是否比 "只有一个说好" 更有信息量？
"八字偏强、紫微偏弱" 这种冲突组合的后续表现又如何？

**它不回答"术数是否有效"。** 那个问题由 `research_status` 状态机回答，
且在本项目的样本上极可能仍停留在 `NO_SIGNAL`。本模块只负责**如实统计**。

三条硬纪律
----------
1. **共振必须有自己的负对照。** "三个模型都说好" 不能成为更有效的理由 ——
   必须与随机时间、随机模型方向、随机因子组合对照。
2. **禁止自由搜索组合。** 只允许在 `ALL_COMBO_IDS` 里预定义的 11 个组合上研究。
   自由组合搜索会迅速退化成数据挖掘，得到的"显著"没有意义。
3. **多重比较必须留痕。** 记录 `experiment_count` / `parameter_count` /
   `selection_method`，并在组合数超过阈值时产出 warning 与 Bonferroni 参考阈值。

as_of 纪律
----------
每个 (股票, as_of) 的引擎方向都由**该时刻的盘面**重新计算（不读取行情），
未来收益只从 as_of 之后读取。构造面板时复用 `ResearchPipeline` 的对齐逻辑。
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from src.core.config import settings
from src.core.schemas.common import VariantMode, Warning_
from src.core.schemas.consensus import (
    ALL_COMBO_IDS,
    CONFLICT_COMBO_SPECS,
    CONSENSUS_COMBO_SPECS,
    ConsensusComboStats,
    ConsensusResearchRequest,
    ConsensusResearchResult,
    MultipleTestingWarning,
)
from src.research.pipeline import new_experiment_id

#: 超过该组合数开始提示多重比较风险
MULTIPLE_TESTING_CAUTION_AT = 5
MULTIPLE_TESTING_HIGH_AT = 20
#: Bonferroni 的名义显著性水平
NOMINAL_ALPHA = 0.05
#: 判定"对照失效"的 Jaccard 阈值（与负对照口径一致）
JACCARD_INVALID = 0.9
#: 判定组合是否有统计意义的最小事件数
MIN_EVENTS = 30


def combo_description(combo_id: str) -> tuple[list[str], str]:
    """返回 ``(参与引擎, 可读说明)``。"""
    if combo_id in CONSENSUS_COMBO_SPECS:
        engines = list(CONSENSUS_COMBO_SPECS[combo_id])
        return engines, f"同向共振：{' + '.join(engines)} 同时偏强"
    if combo_id in CONFLICT_COMBO_SPECS:
        pos, neg = CONFLICT_COMBO_SPECS[combo_id]
        return sorted({*pos, *neg}), (
            f"冲突组合：{'/'.join(pos)} 偏强 vs {'/'.join(neg)} 偏弱"
        )
    raise KeyError(f"未定义的组合：{combo_id}")


def combo_mask(directions: pd.DataFrame, combo_id: str) -> pd.Series:
    """在方向面板上计算组合的命中掩码（布尔 Series）。

    冲突组合要求**正引擎为正**且**负引擎为负**；两者都不允许中性。
    """
    if combo_id in CONSENSUS_COMBO_SPECS:
        engines = CONSENSUS_COMBO_SPECS[combo_id]
        mask = pd.Series(True, index=directions.index)
        for e in engines:
            if e not in directions.columns:
                return pd.Series(False, index=directions.index)
            mask &= directions[e] > 0
        return mask
    if combo_id in CONFLICT_COMBO_SPECS:
        pos, neg = CONFLICT_COMBO_SPECS[combo_id]
        mask = pd.Series(True, index=directions.index)
        for e in pos:
            if e not in directions.columns:
                return pd.Series(False, index=directions.index)
            mask &= directions[e] > 0
        for e in neg:
            if e not in directions.columns:
                return pd.Series(False, index=directions.index)
            mask &= directions[e] < 0
        return mask
    raise KeyError(f"未定义的组合：{combo_id}")


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "std": None, "up_rate": None}
    arr = np.asarray(values, dtype=float)
    return {
        "n": int(arr.size),
        "mean": round(float(arr.mean()), 6),
        "median": round(float(np.median(arr)), 6),
        "std": round(float(arr.std(ddof=1)) if arr.size > 1 else 0.0, 6),
        "up_rate": round(float((arr > 0).mean()), 6),
    }


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluate_combo(
    panel: pd.DataFrame,
    directions: pd.DataFrame,
    combo_id: str,
    *,
    horizon: int = 20,
    run_negative_controls: bool = True,
    seed: int | None = None,
) -> ConsensusComboStats:
    """评估一个组合的事件研究统计 + 负对照。

    Args:
        panel: 含 ``stock_code`` / ``as_of`` / ``ret_{h}d`` / ``excess_return_20d`` 的面板
        directions: 与 panel **同索引同行序** 的引擎方向面板（列 = 引擎名）
    """
    engines, description = combo_description(combo_id)
    ret_col = f"ret_{horizon}d"
    stats = ConsensusComboStats(
        combo_id=combo_id, description=description, engines=engines,
        logic="conflict" if combo_id in CONFLICT_COMBO_SPECS else "consensus",
        horizon=horizon,
    )

    if ret_col not in panel.columns:
        stats.research_status = "NOT_RUN"
        stats.research_status_reasons.append(f"面板缺少 {ret_col} 列")
        return stats

    valid = panel[ret_col].notna()
    stats.sample_count = int(valid.sum())
    mask = combo_mask(directions, combo_id) & valid
    real_idx = panel.index[mask]
    stats.event_count = int(len(real_idx))
    stats.event_rate = round(len(real_idx) / max(stats.sample_count, 1), 6)

    if stats.event_count == 0:
        stats.research_status = "NOT_RUN"
        stats.research_status_reasons.append("该组合在样本内没有命中任何事件。")
        return stats

    real_returns = panel.loc[real_idx, ret_col].astype(float).tolist()
    s = _stats(real_returns)
    stats.up_rate = s["up_rate"]
    stats.mean_return = s["mean"]
    stats.median_return = s["median"]
    stats.std_return = s["std"]
    if "excess_return_20d" in panel.columns and horizon == 20:
        ex = panel.loc[real_idx, "excess_return_20d"].dropna()
        stats.excess_return = round(float(ex.mean()), 6) if len(ex) else None

    # --- 负对照：随机模型方向（保持每个引擎的激活率，只打乱"在哪天激活"） ---
    if run_negative_controls:
        rng = np.random.default_rng(settings.negative_control_seed if seed is None else seed)
        shuffled = pd.DataFrame(index=directions.index, columns=directions.columns)
        for e in directions.columns:
            col = directions[e].to_numpy(copy=True)
            rng.shuffle(col)
            shuffled[e] = col
        ctrl_mask = combo_mask(shuffled, combo_id) & valid
        ctrl_idx = panel.index[ctrl_mask]
        stats.control_kind = "random_engine_direction"
        stats.control_event_count = int(len(ctrl_idx))
        real_keys = {(panel.at[i, "stock_code"], panel.at[i, "as_of"]) for i in real_idx}
        ctrl_keys = {(panel.at[i, "stock_code"], panel.at[i, "as_of"]) for i in ctrl_idx}
        stats.jaccard_with_real = round(_jaccard(real_keys, ctrl_keys), 6)
        if len(ctrl_idx):
            ctrl_returns = panel.loc[ctrl_idx, ret_col].astype(float).tolist()
            cs = _stats(ctrl_returns)
            stats.control_up_rate = cs["up_rate"]
            stats.control_mean_return = cs["mean"]
            stats.t_stat, stats.p_value = _welch_t(real_returns, ctrl_returns)

        stats.control_result, stats.research_status, reasons = _verdict(stats)
        stats.research_status_reasons.extend(reasons)
        return stats

    stats.research_status = "INCONCLUSIVE"
    stats.research_status_reasons.append("未运行负对照；按项目纪律，没有负对照的『有效』不被承认。")
    return stats


def _welch_t(real: list[float], control: list[float]) -> tuple[float | None, float | None]:
    """Welch 双样本 t 检验（不假设等方差）。

    为什么不用"差值大于半个标准误"这种经验带：
    在**纯随机**数据上，那种带子会产生大量假阳性（实测 11 个组合里能冒出 7 个
    "outperform"）。用 t 检验把判定门槛和样本量、方差绑在一起，
    随机数据下才不会再轻易"胜出"。
    """
    n1, n2 = len(real), len(control)
    if n1 < 2 or n2 < 2:
        return None, None
    a = np.asarray(real, dtype=float)
    b = np.asarray(control, dtype=float)
    v1 = float(a.var(ddof=1))
    v2 = float(b.var(ddof=1))
    se2 = v1 / n1 + v2 / n2
    if se2 <= 0:
        return None, None
    t = float((a.mean() - b.mean()) / math.sqrt(se2))
    # Welch–Satterthwaite 自由度
    df_num = se2 ** 2
    df_den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = df_num / df_den if df_den > 0 else 1.0
    p = _student_t_two_sided_p(abs(t), df)
    return round(t, 6), round(p, 8)


def _student_t_two_sided_p(t: float, df: float) -> float:
    """双尾 p 值。

    为避免引入 scipy 依赖，用数值积分计算 Student-t 尾概率；
    样本量在数百级别时足够精确（误差 < 1e-6）。
    """
    if df <= 0 or not math.isfinite(t):
        return 1.0
    # t 分布密度（归一化常数用 Gamma 函数）
    log_c = (
        math.lgamma((df + 1) / 2)
        - math.lgamma(df / 2)
        - 0.5 * math.log(df * math.pi)
    )
    c = math.exp(log_c)
    # 尾概率 = 2 * ∫_t^∞ f(x) dx；用换元 x = t + u/(1-u) 把无穷区间映到 [0,1]
    steps = 2000
    total = 0.0
    for i in range(steps):
        u = (i + 0.5) / steps
        if u <= 0 or u >= 1:
            continue
        x = t + u / (1 - u)
        jac = 1.0 / (1 - u) ** 2
        total += c * (1 + x * x / df) ** (-(df + 1) / 2) * jac
    p = 2.0 * total / steps
    return max(0.0, min(1.0, p))


def _verdict(stats: ConsensusComboStats) -> tuple[str, str, list[str]]:
    """对照判决 → ``(control_result, research_status, reasons)``。"""
    if stats.jaccard_with_real is not None and stats.jaccard_with_real > JACCARD_INVALID:
        return "invalid", "INVALID_CONTROL", [
            f"对照事件集合与真实集合 Jaccard={stats.jaccard_with_real} > {JACCARD_INVALID}，"
            "对照失效：随机化没有真正改变命中位置。"
        ]
    if stats.event_count < MIN_EVENTS:
        return "tie", "INSUFFICIENT_SAMPLE", [
            f"事件数 {stats.event_count} < {MIN_EVENTS}，任何比例都没有统计意义。"
        ]
    if stats.mean_return is None or stats.control_mean_return is None:
        return "tie", "INCONCLUSIVE", ["收益数据不足，无法判定。"]

    diff = stats.mean_return - stats.control_mean_return
    p = stats.p_value
    if p is None:
        return "tie", "INCONCLUSIVE", ["对照样本不足，无法做显著性检验。"]

    sig = p < NOMINAL_ALPHA
    if diff > 0 and sig:
        return "outperform", "WEAK_EVIDENCE", [
            f"真实组合平均收益 {stats.mean_return:.4%} 高于随机方向对照 "
            f"{stats.control_mean_return:.4%}（差 {diff:.4%}，Welch t={stats.t_stat:.3f}，p={p:.5f}）。"
            "这最多是**样本内弱证据**：未做多重检验校正、未做样本外验证。"
            f"多组合同时检验时请对照 multiple_testing.bonferroni_alpha="
            f"{NOMINAL_ALPHA} 的校正参考。"
        ]
    if diff < 0 and sig:
        return "underperform", "NO_SIGNAL", [
            f"真实组合平均收益 {stats.mean_return:.4%} **低于**随机方向对照 "
            f"{stats.control_mean_return:.4%}（差 {diff:.4%}，Welch t={stats.t_stat:.3f}，p={p:.5f}）。"
            "如实结论：该组合在本样本下未表现出超越随机的信息量。"
        ]
    return "tie", "NO_SIGNAL", [
        f"真实组合与随机方向对照的收益差异 {diff:.4%} 未达统计显著 "
        f"（Welch t={stats.t_stat if stats.t_stat is None else round(stats.t_stat, 3)}，"
        f"p={p:.5f} ≥ {NOMINAL_ALPHA}）。"
        "如实结论：共振没有带来可辨识的信息量。"
    ]


# ---------------------------------------------------------------------------
# 多重比较
# ---------------------------------------------------------------------------


def build_multiple_testing_warning(
    experiment_count: int, parameter_count: int,
) -> MultipleTestingWarning:
    warn = MultipleTestingWarning(
        experiment_count=experiment_count,
        parameter_count=parameter_count,
        selection_method="exhaustive_over_predefined_combos",
    )
    warn.bonferroni_alpha = round(NOMINAL_ALPHA / max(experiment_count, 1), 6)
    if experiment_count >= MULTIPLE_TESTING_HIGH_AT:
        warn.warning_level = "high"
    elif experiment_count >= MULTIPLE_TESTING_CAUTION_AT:
        warn.warning_level = "caution"
    else:
        warn.warning_level = "none"

    if warn.warning_level == "none":
        warn.message = (
            f"本次只检验了 {experiment_count} 个**预定义**组合，未做组合搜索，"
            "多重比较风险较低。组合定义见 src/core/schemas/consensus.py。"
        )
    else:
        warn.message = (
            f"本次检验了 {experiment_count} 个组合。组合数越多，"
            "『某一个看起来显著』的概率越高（多重比较 / data mining 风险）。"
            f"Bonferroni 参考阈值 α={warn.bonferroni_alpha}（名义 α={NOMINAL_ALPHA}）。"
            "本系统**不做**学术级校正，因此这些结果只能作为探索性观察，"
            "不能作为有效性宣称。"
        )
    return warn


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_consensus_research(
    *,
    panel: pd.DataFrame,
    directions: pd.DataFrame,
    request: ConsensusResearchRequest,
    data_source: dict | None = None,
    warnings: list[Warning_] | None = None,
) -> ConsensusResearchResult:
    """在已构建的 (收益面板, 方向面板) 上运行共振研究。"""
    combos = request.combos or list(ALL_COMBO_IDS)
    unknown = [c for c in combos if c not in ALL_COMBO_IDS]
    if unknown:
        raise ValueError(
            f"不允许自由定义组合：{unknown}。"
            f"可用的预定义组合为 {list(ALL_COMBO_IDS)}（数据挖掘防护）。"
        )

    # (stock_code, as_of) 必须是唯一键：负对照的 Jaccard 依赖它做事件身份。
    # 若存在重复键，Jaccard 会被虚高，对照可能被误判为"失效"（或相反）。
    warn_all = list(warnings or [])
    if {"stock_code", "as_of"}.issubset(panel.columns) and len(panel):
        dup = int(panel.duplicated(subset=["stock_code", "as_of"]).sum())
        if dup:
            warn_all.append(Warning_(
                code="CONSENSUS_DUPLICATE_PANEL_KEYS",
                message=(
                    f"面板中存在 {dup} 行重复的 (stock_code, as_of) 组合键。"
                    "负对照的 Jaccard 以该键作为事件身份，重复键会使其失真 —— "
                    "结论请谨慎使用。"
                ),
                severity="warning",
            ))

    results: list[ConsensusComboStats] = []
    for i, combo_id in enumerate(combos):
        results.append(evaluate_combo(
            panel, directions, combo_id,
            horizon=request.horizon,
            run_negative_controls=request.run_negative_controls,
            seed=settings.negative_control_seed + i,
        ))

    # 参数计数：组合 × 持有期 × 变体 × 股票池规模
    parameter_count = (
        len(combos) * len(settings.event_study_horizons)
        * 2  # variant
    )
    mt = build_multiple_testing_warning(len(combos), parameter_count)

    statuses = [c.research_status for c in results]
    overall, reasons = _overall_status(statuses, results)

    out = ConsensusResearchResult(
        experiment_id=new_experiment_id("CONS"),
        universe_size=int(panel["stock_code"].nunique()) if "stock_code" in panel else 0,
        sample_dates=int(panel["as_of"].nunique()) if "as_of" in panel else 0,
        horizon=request.horizon,
        benchmark_code=settings.benchmark_index_code,
        data_source=dict(data_source or {}),
        combos=results,
        multiple_testing=mt,
        overall_research_status=overall,
        overall_reasons=reasons,
        methodology=(
            "① 对每个 (股票, as_of) 用**该时刻的盘面**重新计算三模型方向（不读行情）；"
            "② 未来收益只从 as_of 之后读取；"
            "③ 组合命中 = 预定义引擎方向同时满足条件；"
            "④ 负对照 = 打乱每个引擎的激活位置（保持激活率），重新计算组合命中；"
            f"⑤ Jaccard > {JACCARD_INVALID} 判为对照失效；"
            f"⑥ 事件数 < {MIN_EVENTS} 判为样本不足。"
        ),
        warnings=warn_all,
    )
    out.conclusion = _conclusion(out)
    return out


def _overall_status(statuses: list[str], results: list[ConsensusComboStats]) -> tuple[str, list[str]]:
    """把各组合状态收敛成一个总状态（取**最保守**的那个）。"""
    if not statuses:
        return "NOT_RUN", ["没有任何组合同步产出结果。"]
    if all(s == "NOT_RUN" for s in statuses):
        return "NOT_RUN", ["全部组合都没有命中事件。"]

    if any(s == "INVALID_CONTROL" for s in statuses):
        invalid = [c.combo_id for c in results if c.research_status == "INVALID_CONTROL"]
        return "INVALID_CONTROL", [
            f"以下组合的负对照失效（Jaccard 过高）：{', '.join(invalid)}。"
            "对照失去了区分能力，结论不可用。"
        ]
    if all(s == "INSUFFICIENT_SAMPLE" for s in statuses if s != "NOT_RUN"):
        return "INSUFFICIENT_SAMPLE", ["全部可判定组合的事件样本都不足。"]
    if any(s == "WEAK_EVIDENCE" for s in statuses):
        weak = [c.combo_id for c in results if c.research_status == "WEAK_EVIDENCE"]
        return "WEAK_EVIDENCE", [
            f"以下组合在样本内胜过随机方向对照：{', '.join(weak)}。"
            "这是**样本内弱证据**，未做多重检验校正、未做样本外验证。"
        ]
    return "NO_SIGNAL", [
        "所有可判定的组合都未表现出超越随机方向对照的信息量。"
        "如实结论：在本样本上，术数共振与术数冲突都没有显示出稳定的预测能力。"
    ]


def _conclusion(result: ConsensusResearchResult) -> str:
    n = len(result.combos)
    decisive = [c for c in result.combos if c.research_status != "NOT_RUN"]
    beats = [c.combo_id for c in decisive if c.control_result == "outperform"]
    loses = [c.combo_id for c in decisive if c.control_result == "underperform"]
    ties = [c.combo_id for c in decisive if c.control_result == "tie"]
    parts = [
        f"共检验 {n} 个预定义组合，其中 {len(decisive)} 个有可判定结果。",
        f"胜过随机方向对照：{len(beats)} 个{('（' + '、'.join(beats) + '）') if beats else ''}；",
        f"弱于对照：{len(loses)} 个{('（' + '、'.join(loses) + '）') if loses else ''}；",
        f"与对照无差异：{len(ties)} 个。",
        f"整体状态：{result.overall_research_status}。",
        "本结论只描述**本样本**的统计表现，"
        "不构成任何有效性宣称，也不构成投资建议。",
    ]
    return "".join(parts)


def month_sample_dates(date_from: str, date_to: str, step_months: int) -> list[date]:
    from src.research.pipeline import month_starts

    return month_starts(
        date.fromisoformat(date_from), date.fromisoformat(date_to), step_months=step_months,
    )


# ---------------------------------------------------------------------------
# 面板构建
# ---------------------------------------------------------------------------


def build_consensus_panel(
    *,
    stocks: list[str],
    sample_dates: list[date],
    opinion_builder,  # type: ignore[no-untyped-def]
    label_builder,  # type: ignore[no-untyped-def]
    warnings: list[Warning_] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """构建 (收益面板, 方向面板)。

    Args:
        opinion_builder: ``(code, as_of_date) -> dict[engine, direction] | None``
            必须返回**该时刻**各引擎的方向（只读 as_of 及之前的盘面）。
        label_builder: ``(code, as_of_date) -> LabelSet | None``
            只读 as_of **之后**的行情。

    两个面板**行序严格一致**（同一个 (code, as_of) 对应同一行），
    这是后续 ``combo_mask`` 能按位置对齐的前提。

    没有未来标签的样本直接剔除，而不是填 0 —— 填 0 会伪造"持平"样本。
    """
    warn = warnings if warnings is not None else []
    panel_rows: list[dict] = []
    dir_rows: list[dict] = []

    for code in stocks:
        for as_of_date in sample_dates:
            try:
                dirs = opinion_builder(code, as_of_date)
            except Exception as exc:  # noqa: BLE001
                warn.append(Warning_(
                    code="CONSENSUS_OPINION_FAILED",
                    message=f"{code}@{as_of_date} 引擎方向计算失败：{type(exc).__name__}: {exc}",
                    severity="warning",
                ))
                continue
            if not dirs:
                continue
            try:
                labels = label_builder(code, as_of_date)
            except Exception as exc:  # noqa: BLE001 - 数据不足属预期
                warn.append(Warning_(
                    code="CONSENSUS_LABEL_UNAVAILABLE",
                    message=f"{code}@{as_of_date} 标签不可用：{type(exc).__name__}: {exc}",
                    severity="info",
                ))
                continue
            if labels is None:
                continue

            panel_rows.append({
                "stock_code": code,
                "as_of": as_of_date,
                "ret_1d": labels.ret_1d, "ret_5d": labels.ret_5d,
                "ret_10d": labels.ret_10d, "ret_20d": labels.ret_20d,
                "ret_60d": labels.ret_60d,
                "excess_return_20d": labels.excess_return_20d,
            })
            dir_rows.append({"stock_code": code, "as_of": as_of_date, **dirs})

    panel = pd.DataFrame(panel_rows)
    directions = pd.DataFrame(dir_rows)
    if panel.empty:
        panel = pd.DataFrame(columns=[
            "stock_code", "as_of", "ret_1d", "ret_5d", "ret_10d", "ret_20d",
            "ret_60d", "excess_return_20d",
        ])
    if directions.empty:
        directions = pd.DataFrame(columns=["stock_code", "as_of", "bazi", "ziwei", "huangli"])
    return panel, directions


def engine_columns(directions: pd.DataFrame) -> list[str]:
    return [c for c in directions.columns if c not in ("stock_code", "as_of")]


_ = VariantMode  # 供类型与文档引用；实际 variant 由调用方在 opinion_builder 中决定


__all__ = [
    "run_consensus_research", "evaluate_combo", "combo_mask", "combo_description",
    "build_multiple_testing_warning", "month_sample_dates",
    "MIN_EVENTS", "JACCARD_INVALID", "NOMINAL_ALPHA",
]
