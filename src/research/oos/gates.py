"""Phase 3D 的 OOS 状态门（GOAL §15）—— 本阶段最重要的一道闸门。

为什么单独一个模块
------------------
"OOS 平均收益 > 0" 不是证据。样本外结论必须同时满足一组**预先声明**的条件，
并且这些条件在任何结果产生之前就写死在代码里（本模块常量），
不能在看到结果之后再调整。因此：

* 阈值全部是模块级常量，附带版本号 ``GATE_VERSION``；
* 判定函数是**纯函数**：给定同样的输入必然给出同样的状态；
* ``SUPPORTED_OUT_OF_SAMPLE`` 在本阶段**永远不会**被产出 ——
  正式解锁留给 Phase 3F（BH-FDR 多重检验校正）。3D 的上限是
  ``OOS_CANDIDATE_SUPPORTED``，且必须携带 ``pending_fdr=True``。

十项条件（GOAL §15 的 1–10）
----------------------------
    G1  数据真实性              非合成 / 非降级行情
    G2  OOS 事件数               >= ``MIN_OOS_EVENTS``
    G3  负对照有效              所有对照 Jaccard <= 0.9，且至少一类可判定
    G4  方向与 Validation 一致  sign(OOS) == sign(VALIDATION) 且非零
    G5  优于全部有效对照        OOS 效应 > 每一类可判定对照
    G6  效应量非零              |Cohen's d| >= ``MIN_ABS_COHEN_D``
    G7  显著性达到预注册标准    permutation p < ``ALPHA``
    G8  跨年份稳定              有效年数 >= 3，正向年份比例与符号一致性 >= 0.6
    G9  非单一股票驱动          top1 绝对贡献份额 <= 0.5 且 LOO 无符号翻转
    G10 校准完全来自训练数据    fit_max_as_of <= split.train_end 且 fit_scope=TRAIN_ONLY
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.research.oos.splits import ResearchSplit
from src.research.status import ResearchStatus

#: 状态门版本号（改动任何阈值都必须提升它，并在报告中说明）
GATE_VERSION = "phase3d-oos-gate-v1"

#: G2：OOS 事件数下限
MIN_OOS_EVENTS = 100
#: G2 附加：Validation 事件数下限（用于方向一致性判定）
MIN_VALIDATION_EVENTS = 60
#: G3：负对照独立性阈值（与 Phase 1 口径一致）
MAX_CONTROL_JACCARD = 0.9
#: G6：Cohen's d 的绝对值下限（"effect_size != 0" 的可操作化）
MIN_ABS_COHEN_D = 0.02
#: G7：显著性水平（预注册：置换法单侧 p）
ALPHA = 0.05
#: G8：跨年稳定性
MIN_STABLE_YEARS = 3
MIN_POSITIVE_YEAR_RATIO = 0.6
MIN_SIGN_CONSISTENCY = 0.6
#: G9：单一股票依赖
MAX_TOP1_CONTRIBUTION = 0.5

#: Phase 3D 允许产出的最高状态（正式 SUPPORTED_OUT_OF_SAMPLE 留给 Phase 3F）
MAX_STATUS_PHASE3D = ResearchStatus.OOS_CANDIDATE_SUPPORTED


@dataclass(frozen=True)
class GateCheck:
    """单项 gate 的判定记录。"""

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
class OOSGateResult:
    """一次 OOS 假设的状态门结论。"""

    hypothesis_id: str
    status: ResearchStatus
    checks: list[GateCheck] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    pending_fdr: bool = False
    fdr_applied: bool = False
    oos_used: bool = False
    gate_version: str = GATE_VERSION
    split_fingerprint: str = ""

    @property
    def passed(self) -> bool:
        return self.status in (
            ResearchStatus.OOS_CANDIDATE_SUPPORTED,
            ResearchStatus.SUPPORTED_OUT_OF_SAMPLE,
        )

    def check(self, name: str) -> GateCheck | None:
        for item in self.checks:
            if item.name == name:
                return item
        return None

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "status": self.status.value,
            "pending_fdr": self.pending_fdr,
            "fdr_applied": self.fdr_applied,
            "oos_used": self.oos_used,
            "gate_version": self.gate_version,
            "split_fingerprint": self.split_fingerprint,
            "reasons": list(self.reasons),
            "checks": [c.to_dict() for c in self.checks],
        }


def gate_thresholds() -> dict:
    """冻结阈值快照（写入报告，便于事后核对）。"""
    return {
        "gate_version": GATE_VERSION,
        "min_oos_events": MIN_OOS_EVENTS,
        "min_validation_events": MIN_VALIDATION_EVENTS,
        "max_control_jaccard": MAX_CONTROL_JACCARD,
        "min_abs_cohen_d": MIN_ABS_COHEN_D,
        "alpha": ALPHA,
        "min_stable_years": MIN_STABLE_YEARS,
        "min_positive_year_ratio": MIN_POSITIVE_YEAR_RATIO,
        "min_sign_consistency": MIN_SIGN_CONSISTENCY,
        "max_top1_contribution": MAX_TOP1_CONTRIBUTION,
        "p_value_metric": "permutation_p_one_sided_random_event_position",
        "max_status_phase3d": MAX_STATUS_PHASE3D.value,
        "fdr_deferred_to_phase": "3F",
    }


def _fmt_pct(value: float | None) -> str:
    return "None" if value is None else f"{value:.4%}"


def evaluate_oos_gate(
    *,
    split: ResearchSplit,
    hypothesis_id: str,
    oos_stats: dict,
    validation_stats: dict | None,
    controls: list[dict],
    year_stability: dict,
    stock_dependency: dict,
    calibration_audit: dict,
    data_is_real: bool = True,
    data_problems: list[str] | None = None,
    primary_horizon: int | None = None,
    oos_used: bool = True,
) -> OOSGateResult:
    """对单个假设的 OOS 结果做状态判定。

    ``oos_stats`` / ``validation_stats`` 需要含：``event_count`` / ``sample_count`` /
    ``mean_excess_return`` / ``mean_return`` / ``sign``（主持有期）以及 ``by_horizon``。
    ``controls`` 是 ``ControlSummary.to_dict()`` 的列表。
    """
    horizon = primary_horizon or split.primary_horizon
    result = OOSGateResult(
        hypothesis_id=hypothesis_id,
        status=ResearchStatus.NOT_RUN,
        gate_version=GATE_VERSION,
        split_fingerprint=split.fingerprint(),
        oos_used=oos_used,
    )

    oos_events = int(oos_stats.get("event_count") or 0)
    oos_samples = int(oos_stats.get("sample_count") or 0)
    oos_mean = oos_stats.get("mean_excess_return")
    oos_sign = int(oos_stats.get("sign") or 0)

    decisive = [c for c in controls if c.get("decisive")]
    invalid = [
        c for c in controls
        if c.get("jaccard_with_real") is not None
        and float(c["jaccard_with_real"]) > MAX_CONTROL_JACCARD
    ]

    validation_events = int((validation_stats or {}).get("event_count") or 0)
    validation_mean = (validation_stats or {}).get("mean_excess_return")
    validation_sign = int((validation_stats or {}).get("sign") or 0)

    # --- G1 数据真实性 -------------------------------------------------
    result.checks.append(GateCheck(
        name="G1_data_is_real",
        label="数据真实性（非合成/降级）",
        passed=bool(data_is_real),
        detail=("标签与行情全部来自真实快照" if data_is_real
                else f"存在合成/降级数据：{'；'.join(data_problems or [])}"),
    ))

    # --- G2 样本量 -----------------------------------------------------
    result.checks.append(GateCheck(
        name="G2_oos_event_count",
        label=f"OOS 事件数 >= {MIN_OOS_EVENTS}（主持有期 {horizon}D 有效样本）",
        passed=oos_events >= MIN_OOS_EVENTS and oos_samples > 0,
        detail=f"OOS 事件 {oos_events}，主持有期有效样本 {oos_samples}",
        value=oos_events,
    ))
    result.checks.append(GateCheck(
        name="G2b_validation_event_count",
        label=f"Validation 事件数 >= {MIN_VALIDATION_EVENTS}",
        passed=validation_events >= MIN_VALIDATION_EVENTS,
        detail=f"Validation 事件 {validation_events}",
        value=validation_events,
        blocking=False,
    ))

    # --- G3 负对照有效性 -----------------------------------------------
    result.checks.append(GateCheck(
        name="G3_control_valid",
        label=f"负对照独立（Jaccard <= {MAX_CONTROL_JACCARD}）且至少一类可判定",
        passed=(not invalid) and bool(decisive),
        detail=(
            f"可判定对照 {len(decisive)}/{len(controls)} 类；"
            f"失效对照 {[c.get('kind') for c in invalid] or '无'}"
        ),
        value=[c.get("kind") for c in invalid],
    ))

    # --- G4 与 Validation 方向一致 -------------------------------------
    direction_ok = (
        validation_sign != 0
        and oos_sign != 0
        and validation_sign == oos_sign
        and validation_events >= MIN_VALIDATION_EVENTS
    )
    result.checks.append(GateCheck(
        name="G4_direction_consistent_with_validation",
        label="OOS 方向与 Validation 一致",
        passed=direction_ok,
        detail=(
            f"Validation 超额均值为 {_fmt_pct(validation_mean)}（符号 {validation_sign}），"
            f"OOS 为 {_fmt_pct(oos_mean)}（符号 {oos_sign}）"
        ),
    ))

    # --- G5 优于全部有效对照 -------------------------------------------
    beaten = [c for c in decisive if (
        c.get("mean_excess_return") is not None and oos_mean is not None
         and float(oos_mean) > float(c["mean_excess_return"])
    )]
    effect_gt_control = bool(decisive) and len(beaten) == len(decisive)
    result.checks.append(GateCheck(
        name="G5_oos_beats_all_controls",
        label="OOS 效应优于每一类有效对照",
        passed=effect_gt_control,
        detail=(
            f"击败 {len(beaten)}/{len(decisive)} 类可判定对照"
            f"（OOS 超额 {_fmt_pct(oos_mean)}）"
        ),
    ))

    # --- G6 效应量非零 -------------------------------------------------
    cohen_d = oos_stats.get("cohen_d")
    effect_size_ok = cohen_d is not None and abs(float(cohen_d)) >= MIN_ABS_COHEN_D
    result.checks.append(GateCheck(
        name="G6_effect_size_nonzero",
        label=f"|Cohen's d| >= {MIN_ABS_COHEN_D}",
        passed=effect_size_ok,
        detail=f"Cohen's d = {cohen_d}",
        value=cohen_d,
    ))

    # --- G7 显著性（预注册：置换法单侧 p） ------------------------------
    best_p = min(
        [float(c["p_value"]) for c in decisive if c.get("p_value") is not None],
        default=None,
    )
    significance_ok = best_p is not None and best_p < ALPHA
    result.checks.append(GateCheck(
        name="G7_significance",
        label=f"置换法单侧 p < {ALPHA}（随机事件位置零假设）",
        passed=significance_ok,
        detail=f"最小可判定对照 p = {best_p}",
        value=best_p,
    ))

    # --- G8 跨年份稳定 -------------------------------------------------
    year_count = int(year_stability.get("year_count") or 0)
    positive_ratio = year_stability.get("positive_year_ratio")
    sign_consistency = year_stability.get("sign_consistency")
    stability_ok = (
        year_count >= MIN_STABLE_YEARS
        and positive_ratio is not None and float(positive_ratio) >= MIN_POSITIVE_YEAR_RATIO
        and sign_consistency is not None and float(sign_consistency) >= MIN_SIGN_CONSISTENCY
    )
    result.checks.append(GateCheck(
        name="G8_year_stability",
        label=f"跨年份稳定（>= {MIN_STABLE_YEARS} 年，正向比例/符号一致性 >= 0.6）",
        passed=stability_ok,
        detail=(
            f"有效年数 {year_count}，正向年份比例 {positive_ratio}，"
            f"符号一致性 {sign_consistency}"
        ),
    ))

    # --- G9 非单一股票驱动 --------------------------------------------
    top1 = stock_dependency.get("top_1_contribution")
    loo_flips = int(stock_dependency.get("loo_sign_flip_count") or 0)
    single_name_ok = (
        top1 is not None and float(top1) <= MAX_TOP1_CONTRIBUTION and loo_flips == 0
    )
    result.checks.append(GateCheck(
        name="G9_not_single_name_driven",
        label=f"非单一股票驱动（top1 贡献 <= {MAX_TOP1_CONTRIBUTION}，LOO 无符号翻转）",
        passed=single_name_ok,
        detail=f"top1 绝对贡献份额 {top1}，LOO 符号翻转 {loo_flips} 只股票",
        value=top1,
    ))

    # --- G10 校准来自训练数据 ------------------------------------------
    fit_max = calibration_audit.get("fit_max_as_of")
    fit_scope = str(calibration_audit.get("fit_scope", ""))
    fit_hash = calibration_audit.get("calibration_fit_hash")
    calibration_ok = bool(
        fit_max is not None
        and fit_scope == "TRAIN_ONLY"
        and fit_hash
        and _as_date(fit_max) <= split.train_end
    )
    result.checks.append(GateCheck(
        name="G10_calibration_from_train",
        label="校准完全由训练数据拟合（fit_max_as_of <= train_end）",
        passed=calibration_ok,
        detail=(
            f"fit_scope={fit_scope or 'None'}，fit_max_as_of={fit_max}，"
            f"train_end={split.train_end}，fit_hash={fit_hash or 'None'}"
        ),
    ))

    # ------------------------------------------------------------------
    # 状态映射：先判"不可用"，再判"信号方向"，最后才是强度
    # ------------------------------------------------------------------
    lookup = {c.name: c for c in result.checks}

    if not data_is_real:
        result.status = ResearchStatus.NO_REAL_DATA
        result.reasons = [
            "G1 未通过：本次 OOS 运行包含合成或降级数据，不构成任何证据。"
        ]
        return result

    if oos_events == 0 or oos_samples == 0:
        result.status = ResearchStatus.NOT_RUN
        result.reasons = ["G2 未通过：OOS 事件或主持有期有效样本为 0，没有可判定结果。"]
        return result

    if oos_samples < 8:
        result.status = ResearchStatus.INSUFFICIENT_SAMPLE
        result.reasons = [f"G2 未通过：OOS 主持有期有效样本 {oos_samples} < 8，比例无统计意义。"]
        return result

    if not lookup["G2_oos_event_count"].passed:
        result.status = ResearchStatus.INSUFFICIENT_SAMPLE
        result.reasons = [
            f"G2 未通过：{lookup['G2_oos_event_count'].detail}，"
            f"低于预注册下限 {MIN_OOS_EVENTS}。"
        ]
        return result

    if invalid:
        result.status = ResearchStatus.INVALID_CONTROL
        result.reasons = [
            "G3 未通过：以下负对照与真实事件集合 Jaccard > "
            f"{MAX_CONTROL_JACCARD}，对照失效："
            f"{', '.join(str(c.get('kind')) for c in invalid)}。"
            "事件集合几乎等同于「整个面板」时，任何对照都无法区分真实与随机。"
        ]
        return result

    if not decisive:
        result.status = ResearchStatus.INCONCLUSIVE
        result.reasons = ["G3 未通过：全部负对照均因样本不足无法判定（inconclusive）。"]
        return result

    if not effect_gt_control:
        losers = [c for c in decisive if c not in beaten]
        if len(beaten) == 0:
            result.status = ResearchStatus.NO_SIGNAL
            result.reasons = [
                f"G5 未通过：OOS 效应未超过任何一类有效对照（对照中 {len(losers)} 类不弱于真实）。"
                "如实结论：在本样本与协议下，该对象没有显示样本外信息量。"
            ]
        else:
            result.status = ResearchStatus.INCONCLUSIVE
            result.reasons = [
                f"G5 未通过：OOS 效应只击败 {len(beaten)}/{len(decisive)} 类对照，结果不一致。"
            ]
        return result

    # 到这里：真实组已击败全部可判定对照 —— 剩下的是"强度/稳健性"问题
    weak_reasons: list[str] = []
    if not lookup["G8_year_stability"].passed:
        weak_reasons.append(f"G8 未通过：{lookup['G8_year_stability'].detail}")
    if not lookup["G9_not_single_name_driven"].passed:
        weak_reasons.append(
            f"G9 未通过：{lookup['G9_not_single_name_driven'].detail} → SINGLE_NAME_DEPENDENT"
        )
    if not lookup["G6_effect_size_nonzero"].passed:
        weak_reasons.append(f"G6 未通过：{lookup['G6_effect_size_nonzero'].detail}")
    if not lookup["G7_significance"].passed:
        weak_reasons.append(f"G7 未通过：{lookup['G7_significance'].detail}")
    if not lookup["G4_direction_consistent_with_validation"].passed:
        weak_reasons.append(f"G4 未通过：{lookup['G4_direction_consistent_with_validation'].detail}")
    if not lookup["G10_calibration_from_train"].passed:
        weak_reasons.append(f"G10 未通过：{lookup['G10_calibration_from_train'].detail}")

    if not direction_ok:
        result.status = ResearchStatus.INCONCLUSIVE
        result.reasons = weak_reasons or ["方向与 Validation 不一致，无法判定。"]
        return result

    # 校准纪律失败属于流程性错误，必须显式暴露而不是降级成"弱证据"
    if not lookup["G10_calibration_from_train"].passed:
        result.status = ResearchStatus.INCONCLUSIVE
        result.reasons = weak_reasons
        return result

    if weak_reasons:
        result.status = ResearchStatus.WEAK_EVIDENCE
        result.reasons = weak_reasons + [
            "全部有效对照均被击败，但强度/稳健性条件未全部满足，只能记为弱证据。"
        ]
        return result

    # 十项全过 —— 但 Phase 3D 最多给候选状态，正式解锁留给 Phase 3F 的 FDR
    if MAX_STATUS_PHASE3D == ResearchStatus.SUPPORTED_OUT_OF_SAMPLE:  # pragma: no cover
        raise AssertionError(
            "Phase 3D 不得直接把状态门上限提到 SUPPORTED_OUT_OF_SAMPLE；"
            "正式解锁必须在 Phase 3F 完成 BH-FDR 之后另行改版。"
        )
    result.status = MAX_STATUS_PHASE3D
    result.pending_fdr = True
    result.reasons = [
        f"十项 OOS 条件全部满足（gate {GATE_VERSION}），但**尚未做多重检验校正**（FDR 属于 Phase 3F），"
        "因此只能是候选状态 OOS_CANDIDATE_SUPPORTED，不得表述为'样本外验证通过'。"
    ]
    return result


def _as_date(value: object):
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:  # pragma: no cover - 非法值直接判失败
        return date.max


__all__ = [
    "ALPHA",
    "GATE_VERSION",
    "MAX_CONTROL_JACCARD",
    "MAX_STATUS_PHASE3D",
    "MAX_TOP1_CONTRIBUTION",
    "MIN_ABS_COHEN_D",
    "MIN_OOS_EVENTS",
    "MIN_POSITIVE_YEAR_RATIO",
    "MIN_SIGN_CONSISTENCY",
    "MIN_STABLE_YEARS",
    "MIN_VALIDATION_EVENTS",
    "GateCheck",
    "OOSGateResult",
    "evaluate_oos_gate",
    "gate_thresholds",
]
