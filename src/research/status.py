"""研究结论状态机（Phase 1.1 验收要求）。

为什么需要它
------------
"Event Study 输出了一堆数字" 不等于 "存在研究结论"。
本模块把研究输出收敛到一个**显式状态**，防止把以下情况误读为"术数有效"：

* 数据是合成的 / 降级的（synthetic_demo / degraded cache）
* 样本不足却被当成精确统计
* 负对照与真实事件集合高度重叠（对照失效）
* 真实因子 **弱于** 随机（必须如实输出 NO_SIGNAL）

状态定义（顺序即优先级）
-----------------------
    NOT_RUN                  根本没有有效运行（无事件/无标签/无观测）
    NO_REAL_DATA             只有合成或降级行情 —— 禁止产出任何"有效性"含义
    INSUFFICIENT_SAMPLE      有真实数据但事件样本低于统计阈值
    INVALID_CONTROL          负对照与真实事件集合重合度过高（Jaccard > 0.9），对照失效
    NO_SIGNAL                真实因子不优于随机（含 underperform 与全部 tie）
    INCONCLUSIVE             对照结果不一致或样本达不到判定级
    WEAK_EVIDENCE            部分负对照被击败，但未达到"全部对照显著弱于真实"的强度
    SUPPORTED_IN_SAMPLE      四类对照全部被真实因子击败且样本充足（仍只是样本内）
    OOS_CANDIDATE_SUPPORTED  Phase 3D 引入：OOS 十项条件全过，但**尚未做多重检验校正**
                             （FDR 属 Phase 3F），因此只能记为候选，不得解锁
    EXPLORATORY_NOT_GATED    预注册为探索性（无方向性预测）：不套用单向门，
                             永远不解锁任何候选/支持状态
    SUPPORTED_OUT_OF_SAMPLE  Phase 3F 起可用：必须通过 gate-v2 的 A–L 十二项条件
                             （含族内 BH-FDR、date-block bootstrap、日期分层置换、
                             风格/板块中性化）

硬性规则
--------
* 任何数据为 synthetic / degraded 时，唯一允许的状态是 ``NO_REAL_DATA``。
* Phase 3D 的 OOS 状态门（``src/research/oos/gates.py``）最高只产出
  ``OOS_CANDIDATE_SUPPORTED`` 且必须携带 ``pending_fdr=True``。
* 只有 ``src/research/multipletesting/gate_v2.py`` 的 A–L 十二项条件全部通过，
  才会返回 ``SUPPORTED_OUT_OF_SAMPLE``；``assess_research_status``（Phase 1.1 的
  样本内判定）仍然永不返回它。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResearchStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    NO_REAL_DATA = "NO_REAL_DATA"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    INVALID_CONTROL = "INVALID_CONTROL"
    NO_SIGNAL = "NO_SIGNAL"
    INCONCLUSIVE = "INCONCLUSIVE"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    SUPPORTED_IN_SAMPLE = "SUPPORTED_IN_SAMPLE"
    #: Phase 3D：OOS 条件全过但未做 FDR 校正 —— 候选状态，不等于"样本外验证通过"
    OOS_CANDIDATE_SUPPORTED = "OOS_CANDIDATE_SUPPORTED"
    #: 预注册为探索性（无方向性预测）的对象：照常做描述统计与多重检验校正，
    #: 但**不套用单向状态门**，永远不解锁候选/支持状态。
    #: Phase 3D 起以字符串形式出现在结果 CSV 中；Phase 3F 提升为正式枚举成员。
    EXPLORATORY_NOT_GATED = "EXPLORATORY_NOT_GATED"
    #: Phase 3F 起可用（必须通过 gate-v2 的 A–L 十二项条件，含族内 BH-FDR）
    SUPPORTED_OUT_OF_SAMPLE = "SUPPORTED_OUT_OF_SAMPLE"


#: 判定"全对照均被击败"所需的最小事件样本（与负对照判定阈值一致）
MIN_SUPPORTED_SAMPLE = 30
#: 负对照独立性阈值：Jaccard 超过该值视为对照失效
JACCARD_INVALID_THRESHOLD = 0.9

#: 合成/降级来源标识
DEGRADED_SOURCES = {"synthetic_demo", "synthetic"}


@dataclass
class ResearchStatusAssessment:
    status: ResearchStatus
    reasons: list[str] = field(default_factory=list)
    #: 数据真实性结论，供 UI / 审计直接消费
    data_is_real: bool = True
    council: dict = field(default_factory=dict)  # 诊断明细（样本数、对照判决等）


def _horizon20(event_result) -> object | None:  # type: ignore[no-untyped-def]
    for h in getattr(event_result, "horizons", []) or []:
        if getattr(h, "horizon", None) == 20:
            return h
    return None


def assess_research_status(
    event_result,  # type: ignore[no-untyped-def]
    control_report=None,  # type: ignore[no-untyped-def]
    *,
    data_is_real: bool = True,
    data_problems: list[str] | None = None,
) -> ResearchStatusAssessment:
    """对一次研究运行做状态判定。

    Args:
        event_result: ``EventStudyResult``
        control_report: ``NegativeControlReport`` 或 None
        data_is_real: 标签/观测使用的行情是否全部为真实数据
            （synthetic / degraded → False）
        data_problems: 数据层面的问题描述（写入 reasons）
    """
    council: dict = {}

    # --- 1. 数据真实性是最高优先级 ---
    if not data_is_real:
        return ResearchStatusAssessment(
            status=ResearchStatus.NO_REAL_DATA,
            reasons=[
                "当前运行使用了合成或降级行情数据。该输出仅用于系统联调与 UI 演示，"
                "不构成任何历史有效性证据。"
                + (f"（{'；'.join(data_problems or [])}）" if data_problems else "")
            ],
            data_is_real=False,
            council=council,
        )

    h20 = _horizon20(event_result)
    sample_20d = int(getattr(h20, "sample_count", 0) or 0) if h20 else 0
    event_count = int(getattr(event_result, "event_count", 0) or 0)
    council["event_count"] = event_count
    council["sample_20d"] = sample_20d

    # --- 2. 无事件 / 无样本 ---
    if event_count == 0 or h20 is None or sample_20d == 0:
        return ResearchStatusAssessment(
            status=ResearchStatus.NOT_RUN,
            reasons=["没有可用的事件样本（观测为空、激活条件过严或 as_of 之后无标签数据）。"],
            data_is_real=True,
            council=council,
        )

    if sample_20d < 8:
        return ResearchStatusAssessment(
            status=ResearchStatus.INSUFFICIENT_SAMPLE,
            reasons=[f"20 日持有期样本 {sample_20d} < 8，任何比例都没有统计意义。"],
            data_is_real=True,
            council=council,
        )

    # --- 3. 负对照是否运行且有效 ---
    if control_report is None or not getattr(control_report, "results", None):
        return ResearchStatusAssessment(
            status=ResearchStatus.INCONCLUSIVE,
            reasons=["未运行负对照。按项目纪律，没有负对照的『有效性』不被承认。"],
            data_is_real=True,
            council=council,
        )

    results = control_report.results
    verdicts = [r.verdict for r in results]
    council["verdicts"] = {str(getattr(r, "kind", "?")): v for r, v in zip(results, verdicts, strict=True)}

    invalid_controls = [
        str(getattr(r, "kind", "?"))
        for r in results
        if getattr(r, "jaccard_with_real", None) is not None
        and float(r.jaccard_with_real) > JACCARD_INVALID_THRESHOLD
    ]
    if invalid_controls:
        return ResearchStatusAssessment(
            status=ResearchStatus.INVALID_CONTROL,
            reasons=[
                f"以下负对照与真实事件集合 Jaccard 相似度 > {JACCARD_INVALID_THRESHOLD}，"
                f"对照失效：{', '.join(invalid_controls)}。"
                "请检查因子区分度（activation）或样本设计。"
            ],
            data_is_real=True,
            council=council,
        )

    decisive = [v for v in verdicts if v != "inconclusive"]
    if not decisive:
        return ResearchStatusAssessment(
            status=ResearchStatus.INCONCLUSIVE,
            reasons=["全部负对照均因样本不足而无法判定（inconclusive）。"],
            data_is_real=True,
            council=council,
        )

    n_out = sum(1 for v in decisive if v == "outperform")
    n_under = sum(1 for v in decisive if v == "underperform")
    council["decisive"] = {"outperform": n_out, "underperform": n_under,
                           "tie": len(decisive) - n_out - n_under}

    # --- 4. 信号判定 ---
    if n_out == 0:
        return ResearchStatusAssessment(
            status=ResearchStatus.NO_SIGNAL,
            reasons=[
                f"真实因子在 {len(decisive)} 类可判定负对照中无一胜出"
                f"（underperform {n_under} 类，其余为 tie）。"
                "如实结论：当前样本下术数因子未表现出超越随机的信息量。"
            ],
            data_is_real=True,
            council=council,
        )

    if n_under > 0:
        return ResearchStatusAssessment(
            status=ResearchStatus.INCONCLUSIVE,
            reasons=[
                f"对照结果方向不一致：outperform {n_out} 类、underperform {n_under} 类。"
                "不能宣称有效性。"
            ],
            data_is_real=True,
            council=council,
        )

    if n_out < len(results):
        return ResearchStatusAssessment(
            status=ResearchStatus.WEAK_EVIDENCE,
            reasons=[
                f"真实因子胜过 {n_out}/{len(results)} 类负对照，未达到全部对照均被击败的强度，"
                "且未做多重检验校正与样本外验证。"
            ],
            data_is_real=True,
            council=council,
        )

    if sample_20d < MIN_SUPPORTED_SAMPLE:
        return ResearchStatusAssessment(
            status=ResearchStatus.WEAK_EVIDENCE,
            reasons=[
                f"全部 {len(results)} 类负对照均被击败，但 20 日样本 {sample_20d} "
                f"< {MIN_SUPPORTED_SAMPLE}，只能记为弱证据。",
            ],
            data_is_real=True,
            council=council,
        )

    # 守卫：Phase 1 绝不产出 SUPPORTED_OUT_OF_SAMPLE
    _ = ResearchStatus.SUPPORTED_OUT_OF_SAMPLE  # 存在性引用，防止未来误删枚举
    return ResearchStatusAssessment(
        status=ResearchStatus.SUPPORTED_IN_SAMPLE,
        reasons=[
            f"全部 {len(results)} 类负对照均被真实因子击败，20 日样本 {sample_20d} ≥ "
            f"{MIN_SUPPORTED_SAMPLE}。注意：这仅是**样本内**结果，"
            "未做多重检验校正，未做样本外验证，不等于任何未来有效性。",
        ],
        data_is_real=True,
        council=council,
    )


__all__ = [
    "ResearchStatus", "ResearchStatusAssessment", "assess_research_status",
    "DEGRADED_SOURCES", "JACCARD_INVALID_THRESHOLD", "MIN_SUPPORTED_SAMPLE",
]
