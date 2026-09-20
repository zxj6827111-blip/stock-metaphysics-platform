"""Phase 3F · ``gate-v2``：允许解锁 ``SUPPORTED_OUT_OF_SAMPLE`` 的最终状态门。

为什么需要 v2，以及 v2 的合法性边界
-----------------------------------
Phase 3D 的 ``gate-v1`` 最高只能给 ``OOS_CANDIDATE_SUPPORTED``，并且**结构上禁止**
产出 ``SUPPORTED_OUT_OF_SAMPLE`` —— 因为当时没有做多重检验校正。3F 补齐校正、
bootstrap、日期分层置换与中性化之后，才有资格解锁最终状态。

v2 的合法性依赖三条自我约束（GOAL §4.7）：

1. 它只实现 **Phase 3D 已经预登记**的改进项（日期分层对照；
   3D 报告 §6.5 明确把它列为 3F 的协议改进项）；
2. 它**不修改** Phase 3D 的任何结果：v1 的判定仍然照常计算并如实输出；
3. 两版必须**同时报告**，禁止只保留更好看的那一版。

十二项条件（GOAL §4.8 的 A–L）
------------------------------
    A  足够 OOS 事件数                          ``G2``
    B  负对照有效（含日期分层对照）              ``G3``
    C  Validation 与 OOS 方向一致                ``G4``
    D  OOS 效应优于对照                          ``G5``
    E  效应量非零且有实际意义（阈值可判定）       ``G6``
    F  FDR q-value 通过预定义 alpha              ``G11``
    G  bootstrap CI 不跨关键零点                 ``G12``
    H  日期分层置换检验通过                      ``G7``
    I  跨年份稳定                                ``G8``
    J  leave-one-stock-out 稳定                  ``G9``
    K  非单一板块/风格驱动（中性化后仍存在）      ``G13``
    L  无严重 data-quality warning               ``G14``

只要任一**关键**条件失败，就**不得**输出 ``SUPPORTED_OUT_OF_SAMPLE``。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.research.status import ResearchStatus

#: 状态门版本号（改动任何阈值都必须提升）
GATE_V2_VERSION = "phase3f-oos-gate-v2"

#: A：OOS 事件数下限（与 v1 一致，保持可比）
MIN_OOS_EVENTS = 100
#: A：Validation 事件数下限
MIN_VALIDATION_EVENTS = 60
#: B：负对照独立性阈值（Jaccard）
MAX_CONTROL_JACCARD = 0.9
#: E：Cohen's d 的绝对值下限
MIN_ABS_COHEN_D = 0.02
#: E：效应量的**实际意义**下限（日期等权平均的市场超额，2%）
MIN_MEANINGFUL_EFFECT = 0.02
#: F：FDR 显著性水平
ALPHA = 0.05
#: G：bootstrap 置信水平
BOOTSTRAP_CONFIDENCE = 0.95
#: H：置换次数下限（GOAL §4.4）
MIN_PERMUTATION_COUNT = 1000
#: I：跨年份稳定
MIN_STABLE_YEARS = 3
MIN_POSITIVE_YEAR_RATIO = 0.6
MIN_SIGN_CONSISTENCY = 0.6
#: J：单一股票依赖
MAX_TOP1_CONTRIBUTION = 0.5
#: K：中性化后仍存在的下限（风格中性残差至少要有 50% 的原始效应）
MIN_NEUTRALIZED_RETENTION = 0.5
#: L：允许的严重告警（命中即失败）
SEVERE_WARNING_TOKENS: tuple[str, ...] = (
    "SYNTHETIC",
    "DEGRADED",
    "LEAKAGE",
    "SURVIVORSHIP_BIAS_CONFIRMED",
)


@dataclass(frozen=True)
class GateV2Check:
    name: str
    label: str
    passed: bool
    detail: str
    value: object = None
    blocking: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name, "label": self.label, "passed": self.passed,
            "detail": self.detail, "value": self.value, "blocking": self.blocking,
        }


@dataclass
class GateV2Result:
    """gate-v2 的判定结果。"""

    experiment_id: str
    status: ResearchStatus
    checks: list[GateV2Check] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    gate_version: str = GATE_V2_VERSION
    protocol_version: str = GATE_V2_VERSION
    gate_v1_status: str = ""
    fdr_applied: bool = True
    pending_fdr: bool = False

    @property
    def passed_all(self) -> bool:
        return self.status == ResearchStatus.SUPPORTED_OUT_OF_SAMPLE

    def check(self, name: str) -> GateV2Check | None:
        for item in self.checks:
            if item.name == name:
                return item
        return None

    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "gate_version": self.gate_version,
            "protocol_version": self.protocol_version,
            "gate_v1_status": self.gate_v1_status,
            "fdr_applied": self.fdr_applied,
            "pending_fdr": self.pending_fdr,
            "reasons": list(self.reasons),
            "checks": [item.to_dict() for item in self.checks],
        }


def gate_v2_thresholds() -> dict:
    """冻结阈值快照（写入报告，便于事后核对）。"""
    return {
        "gate_version": GATE_V2_VERSION,
        "min_oos_events": MIN_OOS_EVENTS,
        "min_validation_events": MIN_VALIDATION_EVENTS,
        "max_control_jaccard": MAX_CONTROL_JACCARD,
        "min_abs_cohen_d": MIN_ABS_COHEN_D,
        "min_mean_meaningful_effect": MIN_MEANINGFUL_EFFECT,
        "alpha": ALPHA,
        "bootstrap_confidence": BOOTSTRAP_CONFIDENCE,
        "min_permutation_count": MIN_PERMUTATION_COUNT,
        "min_stable_years": MIN_STABLE_YEARS,
        "min_positive_year_ratio": MIN_POSITIVE_YEAR_RATIO,
        "min_sign_consistency": MIN_SIGN_CONSISTENCY,
        "max_top1_contribution": MAX_TOP1_CONTRIBUTION,
        "min_neutralized_retention": MIN_NEUTRALIZED_RETENTION,
        "severe_warning_tokens": list(SEVERE_WARNING_TOKENS),
        "max_status_phase3f": ResearchStatus.SUPPORTED_OUT_OF_SAMPLE.value,
    }


def _fmt_pct(value: object) -> str:
    try:
        return f"{float(value):.4%}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "None"


def evaluate_gate_v2(
    *,
    experiment_id: str,
    oos_stats: dict,
    validation_stats: dict | None,
    controls: list[dict],
    year_stability: dict,
    stock_dependency: dict,
    calibration_audit: dict,
    multiple_testing: dict,
    bootstrap: dict,
    permutation: dict,
    neutralization: dict,
    horizon: int = 20,
    is_gated: bool = True,
    data_is_real: bool = True,
    data_problems: list[str] | None = None,
    warnings: list[str] | None = None,
    gate_v1_status: str = "",
) -> GateV2Result:
    """十二项条件（A–L）全过的唯一解锁路径。

    输入全部来自 3D/3E/3F 的已有产物（不重新计算统计量），
    因此本函数是**纯判定**：同样的输入必然给出同样的状态。
    """
    result = GateV2Result(
        experiment_id=experiment_id,
        status=ResearchStatus.NOT_RUN,
        gate_v1_status=gate_v1_status,
    )
    problems = list(data_problems or [])
    warning_list = list(warnings or [])
    severe = [
        warning for warning in warning_list
        if any(token in str(warning).upper() for token in SEVERE_WARNING_TOKENS)
    ]

    oos_events = int(oos_stats.get("event_count") or 0)
    oos_samples = int(oos_stats.get("sample_count") or 0)
    oos_mean = oos_stats.get("mean_market_excess_return")
    oos_sign = 0 if oos_mean is None else (1 if float(oos_mean) > 0 else (-1 if float(oos_mean) < 0 else 0))
    validation_mean = (validation_stats or {}).get("mean_market_excess_return")
    validation_events = int((validation_stats or {}).get("event_count") or 0)
    validation_sign = (
        0 if validation_mean is None
        else (1 if float(validation_mean) > 0 else (-1 if float(validation_mean) < 0 else 0))
    )
    decisive = [item for item in controls if item.get("decisive")]
    invalid_controls = [
        item for item in controls
        if item.get("jaccard_with_real") is not None
        and float(item["jaccard_with_real"]) > MAX_CONTROL_JACCARD
    ]

    # --- A 事件数 ---
    result.checks.append(GateV2Check(
        name="A_oos_event_count",
        label=f"OOS 事件数 >= {MIN_OOS_EVENTS}（主持有期 {horizon}D）",
        passed=oos_events >= MIN_OOS_EVENTS and oos_samples > 0,
        detail=f"OOS 事件 {oos_events}，有效样本 {oos_samples}",
        value=oos_events,
    ))
    result.checks.append(GateV2Check(
        name="A2_validation_event_count",
        label=f"Validation 事件数 >= {MIN_VALIDATION_EVENTS}",
        passed=validation_events >= MIN_VALIDATION_EVENTS,
        detail=f"Validation 事件 {validation_events}",
        value=validation_events,
        blocking=False,
    ))

    # --- B 负对照有效 ---
    result.checks.append(GateV2Check(
        name="B_control_valid",
        label=f"负对照独立（Jaccard <= {MAX_CONTROL_JACCARD}）且至少一类可判定",
        passed=(not invalid_controls) and bool(decisive),
        detail=(
            f"可判定对照 {len(decisive)}/{len(controls)} 类；"
            f"失效对照 {[item.get('kind') for item in invalid_controls] or '无'}"
        ),
        value=[item.get("kind") for item in invalid_controls],
    ))

    # --- C 方向一致 ---
    result.checks.append(GateV2Check(
        name="C_direction_consistent_with_validation",
        label="OOS 方向与 Validation 一致",
        passed=bool(
            validation_sign != 0 and oos_sign != 0 and validation_sign == oos_sign
            and validation_events >= MIN_VALIDATION_EVENTS
        ),
        detail=(
            f"Validation 超额均值 {_fmt_pct(validation_mean)}（符号 {validation_sign}），"
            f"OOS {_fmt_pct(oos_mean)}（符号 {oos_sign}）"
        ),
    ))

    # --- D 优于全部有效对照 ---
    beaten = [
        item for item in decisive
        if item.get("mean_excess_return") is not None and oos_mean is not None
        and float(oos_mean) > float(item["mean_excess_return"])
    ]
    result.checks.append(GateV2Check(
        name="D_oos_beats_all_controls",
        label="OOS 效应优于每一类有效对照",
        passed=bool(decisive) and len(beaten) == len(decisive),
        detail=f"击败 {len(beaten)}/{len(decisive)} 类可判定对照（OOS 超额 {_fmt_pct(oos_mean)}）",
    ))

    # --- E 效应量非零且有实际意义 ---
    cohen_d = oos_stats.get("cohen_d")
    effect_ok = cohen_d is not None and abs(float(cohen_d)) >= MIN_ABS_COHEN_D
    meaningful_ok = oos_mean is not None and abs(float(oos_mean)) >= MIN_MEANINGFUL_EFFECT
    result.checks.append(GateV2Check(
        name="E_effect_size_nonzero_and_meaningful",
        label=(
            f"|Cohen's d| >= {MIN_ABS_COHEN_D} 且 |OOS 市场超额| >= {MIN_MEANINGFUL_EFFECT}"
        ),
        passed=bool(effect_ok and meaningful_ok),
        detail=(
            f"Cohen's d = {cohen_d}；OOS 市场超额 {_fmt_pct(oos_mean)}"
            f"（下限 {MIN_MEANINGFUL_EFFECT:.2%}）"
        ),
    ))

    # --- F FDR ---
    q_value = multiple_testing.get("fdr_q_value")
    fdr_pass = bool(multiple_testing.get("fdr_pass")) and q_value is not None
    result.checks.append(GateV2Check(
        name="F_fdr_pass",
        label=f"FDR q-value <= {ALPHA}（族内 BH 校正）",
        passed=fdr_pass,
        detail=(
            f"family={multiple_testing.get('family_id')}，"
            f"族内检验数 m={multiple_testing.get('family_test_count')}，"
            f"raw p={multiple_testing.get('raw_p_value')}，q={q_value}"
        ),
        value=q_value,
    ))

    # --- G bootstrap CI ---
    ci_lower = bootstrap.get("ci_lower")
    ci_upper = bootstrap.get("ci_upper")
    crosses_zero = bootstrap.get("crosses_zero")
    bootstrap_ok = bool(
        ci_lower is not None and ci_upper is not None
        and crosses_zero is False
        and float(ci_lower) > 0.0
    )
    result.checks.append(GateV2Check(
        name="G_bootstrap_ci_excludes_zero",
        label=f"{BOOTSTRAP_CONFIDENCE:.0%} bootstrap CI 不跨 0 且下界为正",
        passed=bootstrap_ok,
        detail=(
            f"点估计 {bootstrap.get('point_estimate')}，"
            f"CI [{ci_lower}, {ci_upper}]，crosses_zero={crosses_zero}"
        ),
    ))

    # --- H 日期分层置换 ---
    permutation_p = permutation.get("p_value_upper")
    permutation_count = int(permutation.get("permutation_count") or 0)
    permutation_ok = bool(
        permutation_p is not None
        and permutation_count >= MIN_PERMUTATION_COUNT
        and float(permutation_p) <= ALPHA
    )
    result.checks.append(GateV2Check(
        name="H_date_stratified_permutation",
        label=(
            f"日期分层置换单侧 p <= {ALPHA} 且置换次数 >= {MIN_PERMUTATION_COUNT}"
        ),
        passed=permutation_ok,
        detail=(
            f"p={permutation_p}（{permutation_count} 次置换，"
            f"seed={permutation.get('permutation_seed')}）"
        ),
        value=permutation_p,
    ))

    # --- I 跨年份稳定 ---
    year_count = int(year_stability.get("year_count") or 0)
    positive_ratio = year_stability.get("positive_year_ratio")
    sign_consistency = year_stability.get("sign_consistency")
    stability_ok = bool(
        year_count >= MIN_STABLE_YEARS
        and positive_ratio is not None and float(positive_ratio) >= MIN_POSITIVE_YEAR_RATIO
        and sign_consistency is not None and float(sign_consistency) >= MIN_SIGN_CONSISTENCY
    )
    result.checks.append(GateV2Check(
        name="I_year_stability",
        label=f"跨年份稳定（>= {MIN_STABLE_YEARS} 年，正向比例/符号一致性 >= 0.6）",
        passed=stability_ok,
        detail=(
            f"有效年数 {year_count}，正向年份比例 {positive_ratio}，符号一致性 {sign_consistency}"
        ),
    ))

    # --- J LOO 稳定 ---
    top1 = stock_dependency.get("top_1_contribution")
    loo_flips = int(stock_dependency.get("loo_sign_flip_count") or 0)
    loo_ok = bool(
        top1 is not None and float(top1) <= MAX_TOP1_CONTRIBUTION and loo_flips == 0
    )
    result.checks.append(GateV2Check(
        name="J_not_single_name_driven",
        label=f"非单一股票驱动（top1 贡献 <= {MAX_TOP1_CONTRIBUTION}，LOO 无符号翻转）",
        passed=loo_ok,
        detail=f"top1 绝对贡献份额 {top1}，LOO 符号翻转 {loo_flips} 只股票",
        value=top1,
    ))

    # --- K 非单一板块/风格驱动 ---
    raw_effect = neutralization.get("hit_date_mean_market_excess")
    style_neutral = neutralization.get("style_neutral_hit_mean")
    segment_neutral = neutralization.get("segment_neutral_hit_mean")
    segment_available = bool(neutralization.get("segment_available"))
    retention: float | None = None
    if raw_effect is not None and style_neutral is not None and float(raw_effect) != 0:
        retention = float(style_neutral) / float(raw_effect)
    style_ok = bool(
        style_neutral is not None and float(style_neutral) > 0
        and retention is not None and retention >= MIN_NEUTRALIZED_RETENTION
    )
    segment_ok = True
    segment_detail = "板块维度不可用（未参与判定）"
    if segment_available and segment_neutral is not None:
        segment_ok = bool(float(segment_neutral) > 0)
        segment_detail = f"板块中性均值 {_fmt_pct(segment_neutral)}"
    result.checks.append(GateV2Check(
        name="K_not_style_or_segment_driven",
        label=(
            f"风格中性化后效应仍保留 >= {MIN_NEUTRALIZED_RETENTION:.0%}"
            "，且板块中性后仍为正"
        ),
        passed=bool(style_ok and segment_ok),
        detail=(
            f"原始命中均值 {_fmt_pct(raw_effect)}，风格中性均值 {_fmt_pct(style_neutral)}，"
            f"保留比例 {None if retention is None else round(retention, 4)}；{segment_detail}"
        ),
        value=retention,
    ))

    # --- L 数据质量 ---
    quality_ok = bool(data_is_real and not problems and not severe)
    result.checks.append(GateV2Check(
        name="L_data_quality_clean",
        label="无合成/降级/泄漏类严重告警",
        passed=quality_ok,
        detail=(
            "数据质量无严重告警"
            if quality_ok
            else f"数据问题：{problems or '无'}；严重告警：{severe or '无'}"
        ),
    ))

    # ------------------------------------------------------------------
    # 状态映射
    # ------------------------------------------------------------------
    if not is_gated:
        result.status = ResearchStatus.EXPLORATORY_NOT_GATED
        result.pending_fdr = False
        result.reasons = [
            "该假设预注册为探索性（无方向性），不套用单向 gate，"
            "因此**永不**解锁 SUPPORTED_OUT_OF_SAMPLE；仅给出双侧描述统计。"
        ]
        return result

    if not data_is_real:
        result.status = ResearchStatus.NO_REAL_DATA
        result.reasons = ["L 未通过：本次运行包含合成或降级数据，不构成任何证据。"]
        return result

    if oos_events == 0 or oos_samples == 0:
        result.status = ResearchStatus.NOT_RUN
        result.reasons = ["A 未通过：OOS 事件或有效样本为 0。"]
        return result
    if oos_samples < 8 or oos_events < MIN_OOS_EVENTS:
        result.status = ResearchStatus.INSUFFICIENT_SAMPLE
        result.reasons = [
            f"A 未通过：OOS 事件 {oos_events} / 有效样本 {oos_samples}，"
            f"低于预注册下限 {MIN_OOS_EVENTS}。"
        ]
        return result
    if invalid_controls:
        result.status = ResearchStatus.INVALID_CONTROL
        result.reasons = [
            "B 未通过：对照与真实事件集合 Jaccard > "
            f"{MAX_CONTROL_JACCARD}：{[item.get('kind') for item in invalid_controls]}"
        ]
        return result
    if not decisive:
        result.status = ResearchStatus.INCONCLUSIVE
        result.reasons = ["B 未通过：全部负对照均无法判定。"]
        return result
    if not result.check("D_oos_beats_all_controls").passed:  # type: ignore[union-attr]
        losers = len(decisive) - len(beaten)
        if not beaten:
            result.status = ResearchStatus.NO_SIGNAL
            result.reasons = [
                f"D 未通过：OOS 效应未超过任何一类有效对照（{losers} 类不弱于真实）。"
            ]
        else:
            result.status = ResearchStatus.INCONCLUSIVE
            result.reasons = [f"D 未通过：只击败 {len(beaten)}/{len(decisive)} 类对照。"]
        return result
    if not result.check("C_direction_consistent_with_validation").passed:  # type: ignore[union-attr]
        result.status = ResearchStatus.INCONCLUSIVE
        result.reasons = [
            "C 未通过："
            + str(result.check("C_direction_consistent_with_validation").detail)  # type: ignore[union-attr]
        ]
        return result

    failed = [item for item in result.checks if item.blocking and not item.passed]
    if failed:
        result.status = ResearchStatus.WEAK_EVIDENCE
        result.reasons = [
            f"{item.name[0]} 未通过：{item.detail}" for item in failed
        ] + ["存在未通过的关键条件，不得解锁 SUPPORTED_OUT_OF_SAMPLE。"]
        return result

    result.status = ResearchStatus.SUPPORTED_OUT_OF_SAMPLE
    result.pending_fdr = False
    result.reasons = [
        "A–L 十二项条件全部满足（gate-v2，含族内 BH-FDR、date-block bootstrap、"
        "日期分层置换、风格/板块中性化）。该实验解锁 SUPPORTED_OUT_OF_SAMPLE。"
        "注意：这只代表**研究管线**判定其为样本外支持的结果，"
        "不代表术数有效、也不构成任何交易建议。"
    ]
    return result


__all__ = [
    "ALPHA",
    "BOOTSTRAP_CONFIDENCE",
    "GATE_V2_VERSION",
    "MAX_CONTROL_JACCARD",
    "MAX_TOP1_CONTRIBUTION",
    "MIN_ABS_COHEN_D",
    "MIN_MEANINGFUL_EFFECT",
    "MIN_NEUTRALIZED_RETENTION",
    "MIN_OOS_EVENTS",
    "MIN_PERMUTATION_COUNT",
    "MIN_SIGN_CONSISTENCY",
    "MIN_STABLE_YEARS",
    "MIN_VALIDATION_EVENTS",
    "SEVERE_WARNING_TOKENS",
    "GateV2Check",
    "GateV2Result",
    "evaluate_gate_v2",
    "gate_v2_thresholds",
]
