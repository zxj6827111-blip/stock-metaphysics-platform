"""正式 ConsensusEngine 与 ConflictDetector（Phase 2C）。

**这是本模块最重要的一段话：**

    Consensus 只表示"多个术数模型之间方向的一致程度"，
    **不表示"历史证明它有效"**。

两者必须分开呈现：

* ``consensus_class`` / ``agreement_score`` —— 模型之间是否同向；
* ``research_status`` / ``historical_consensus_stats`` —— 这种同向在历史上
  是否有统计支持。

系统可能在"高共识 + NO_SIGNAL"的状态下给出结论，这**不是 bug**，
而是必须如实呈现的研究结果。UI 文案由 ``interpretation`` 字段统一给出，
禁止各处自行发挥。

禁止简单平均
------------
八字 90 / 紫微 20 / 黄历 50 **不允许**被平均成"整体一般 53"。
必须保留 八字=正向、紫微=负向、黄历=中性 的完整信息，并判定为 `MIXED`，
同时列出冲突原因。这是 AGENTS.md §2.4「模型分歧不得被平均值隐藏」的落地。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.core.schemas.analysis import MetaphysicsOpinion
from src.core.schemas.common import (
    CONSENSUS_CN_LABEL,
    Availability,
    ConsensusLabel,
)
from src.core.schemas.factor import FactorSet

#: 方向 → 中文标签
DIRECTION_CN: dict[int, str] = {1: "偏强", 0: "中性", -1: "偏弱"}

#: 引擎 key → 中文名。**面向人的文本一律用中文名**，
#: 机器可读字段（directions / engine_opinions 的键）保持英文 key 不变。
ENGINE_CN: dict[str, str] = {
    "bazi": "八字",
    "ziwei": "紫微斗数",
    "huangli": "黄历",
    "calendar": "历法",
}


def engine_label(key: str) -> str:
    return ENGINE_CN.get(key, key)

#: 强共识阈值。**只在方向完全一致时才会被使用**，
#: 且它衡量的是"规则强度"，不是"上涨概率"。
STRONG_POSITIVE_MIN_SCORE = 68.0
STRONG_NEGATIVE_MAX_SCORE = 32.0
#: 强共识还要求引擎自身的平均置信度不低于该值
STRONG_MIN_CONFIDENCE = 0.55


@dataclass
class ConsensusReport:
    """正式共识报告（写入 ``ConsensusSnapshot`` 的扩展字段）。"""

    consensus_class: ConsensusLabel
    label_cn: str
    agreement_score: float = 0.0
    available_engine_count: int = 0
    positive_engine_count: int = 0
    negative_engine_count: int = 0
    neutral_engine_count: int = 0
    engine_opinions: dict[str, dict] = field(default_factory=dict)
    directions: dict[str, int] = field(default_factory=dict)
    unavailable_engines: list[str] = field(default_factory=list)
    research_status: str = "NOT_RUN"
    historical_consensus_stats: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)
    interpretation: str = ""
    notes: list[str] = field(default_factory=list)


class ConsensusEngine:
    """把多个引擎的**独立**观点汇总为共识分类。"""

    @staticmethod
    def _available(opinions: dict[str, MetaphysicsOpinion]) -> dict[str, MetaphysicsOpinion]:
        return {
            k: v for k, v in opinions.items()
            if v.availability == Availability.OK and v.score is not None
        }

    def compute(
        self,
        opinions: dict[str, MetaphysicsOpinion],
        *,
        data_quality: str = "B",
        research_status: str = "NOT_RUN",
        historical_stats: dict | None = None,
        data_quality_detail: dict | None = None,
    ) -> ConsensusReport:
        available = self._available(opinions)
        unavailable = sorted(set(opinions) - set(available))

        dirs = {k: int(v.direction) for k, v in available.items()}
        pos = sum(1 for d in dirs.values() if d > 0)
        neg = sum(1 for d in dirs.values() if d < 0)
        neu = sum(1 for d in dirs.values() if d == 0)
        total = len(dirs)

        engine_opinions = {
            k: {
                "engine": k,
                "availability": str(v.availability),
                "direction": int(v.direction),
                "direction_label": DIRECTION_CN.get(int(v.direction), "中性"),
                "score": v.score,
                "confidence": v.confidence,
                "engine_version": v.engine_version,
                "factor_ids": list(v.factor_ids),
                "positive_reasons": [r.text for r in v.top_positive_reasons[:3]],
                "negative_reasons": [r.text for r in v.top_negative_reasons[:3]],
                "research_status": v.research_status,
                "historical_validity": dict(v.historical_validity),
                "data_quality": dict(v.data_quality),
                "assumptions": list(v.assumptions),
                "note": v.note,
            }
            for k, v in opinions.items()
        }

        report = ConsensusReport(
            consensus_class=ConsensusLabel.NEUTRAL,
            label_cn="不可评估",
            available_engine_count=total,
            positive_engine_count=pos,
            negative_engine_count=neg,
            neutral_engine_count=neu,
            engine_opinions=engine_opinions,
            directions=dirs,
            unavailable_engines=unavailable,
            research_status=research_status,
            historical_consensus_stats=dict(historical_stats or {}),
            data_quality={"grade": data_quality, **(data_quality_detail or {})},
        )

        # --- 没有任何可用引擎 ---
        if total == 0:
            report.label_cn = "不可评估"
            report.notes.append(
                "没有任何引擎产出可用结果，共识不可评估。"
                "不可用引擎不会被按 0 分计入。"
            )
            report.interpretation = (
                "当前没有可用的术数引擎结果，因此既没有共识也没有分歧可供解读。"
                "系统不会用 0 分或平均值填补这个空缺。"
            )
            return report

        # --- 分类（顺序即优先级：先看是否存在反向引擎） ---
        if pos > 0 and neg > 0:
            label = ConsensusLabel.MIXED
        elif pos == total:
            label = self._strong_or_plain(available, positive=True)
        elif neg == total:
            label = self._strong_or_plain(available, positive=False)
        else:
            label = ConsensusLabel.NEUTRAL

        report.consensus_class = label
        report.label_cn = (
            CONSENSUS_CN_LABEL[label.value]
            if total > 1
            else f"{DIRECTION_CN.get(next(iter(dirs.values())), '中性')}（单引擎）"
        )
        # 一致度 = 与多数方向相同的引擎占比。**它不是分数的平均**。
        report.agreement_score = round(max(pos, neg, neu) / total, 4)

        report.notes.append(
            "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），"
            "不是各引擎分数的平均，也不表示上涨概率。"
        )
        if unavailable:
            report.notes.append(
                f"以下引擎本次不可用，未计入分母：{', '.join(unavailable)}。"
            )
        if total == 1:
            report.notes.append("仅单一引擎可用，无法评估一致性；共识分类仅供参考。")

        report.interpretation = self._interpret(report, available)
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _strong_or_plain(
        available: dict[str, MetaphysicsOpinion], *, positive: bool,
    ) -> ConsensusLabel:
        scores = [float(v.score or 0.0) for v in available.values()]
        confs = [float(v.confidence or 0.0) for v in available.values()]
        mean_score = sum(scores) / len(scores)
        mean_conf = sum(confs) / len(confs)
        if positive:
            if mean_score >= STRONG_POSITIVE_MIN_SCORE and mean_conf >= STRONG_MIN_CONFIDENCE:
                return ConsensusLabel.STRONG_POSITIVE_CONSENSUS
            return ConsensusLabel.POSITIVE_CONSENSUS
        if mean_score <= STRONG_NEGATIVE_MAX_SCORE and mean_conf >= STRONG_MIN_CONFIDENCE:
            return ConsensusLabel.STRONG_NEGATIVE_CONSENSUS
        return ConsensusLabel.NEGATIVE_CONSENSUS

    @staticmethod
    def _interpret(report: ConsensusReport, available: dict[str, MetaphysicsOpinion]) -> str:
        """统一生成解读文案 —— 共识与历史有效性必须**同时**出现。

        这是本项目的硬性要求：不允许只讲共识、不讲历史统计。
        """
        label = report.label_cn
        parts = [
            f"术数模型之间的一致性：{label}"
            f"（可用 {report.available_engine_count} 个引擎："
            + "、".join(
                f"{engine_label(k)} {DIRECTION_CN.get(int(v.direction), '中性')}"
                for k, v in sorted(available.items())
            )
            + "）。"
        ]
        if report.unavailable_engines:
            parts.append(f"未计入：{'、'.join(report.unavailable_engines)}。")

        status = report.research_status
        if status in ("NOT_RUN", ""):
            parts.append(
                "**历史统计未运行**：上述一致性只是模型之间的方向比较，"
                "没有经过任何历史数据检验。"
            )
        elif status == "NO_SIGNAL":
            parts.append(
                "**术数共识高，但历史统计未发现稳定信号**（ResearchStatus=NO_SIGNAL）。"
                "本文的一致性不代表上涨概率较高。"
            )
        elif status == "NO_REAL_DATA":
            parts.append(
                "**当前数据为合成或降级行情**（ResearchStatus=NO_REAL_DATA），"
                "本结果仅用于系统联调，不构成任何历史有效性证据。"
            )
        elif status == "INVALID_CONTROL":
            parts.append(
                "**负对照失效**（ResearchStatus=INVALID_CONTROL）："
                "对照事件集合与真实事件集合重合度过高，历史验证结论不可用。"
            )
        elif status == "INSUFFICIENT_SAMPLE":
            parts.append(
                "**样本不足**（ResearchStatus=INSUFFICIENT_SAMPLE）："
                "现有样本不足以判定该组合是否有统计意义。"
            )
        elif status in ("INCONCLUSIVE", "WEAK_EVIDENCE"):
            parts.append(
                f"**历史证据不足**（ResearchStatus={status}）："
                "不能据此外推任何有效性。"
            )
        elif status in ("SUPPORTED_IN_SAMPLE", "SUPPORTED_OUT_OF_SAMPLE"):
            parts.append(
                f"**历史统计状态 {status}**：这是样本内结果，"
                "未做多重检验校正、未做样本外验证，不等于任何未来有效性。"
            )
        else:
            parts.append(f"历史统计状态：{status}。")

        if report.consensus_class == ConsensusLabel.MIXED:
            parts.append(
                "**方向存在冲突，本系统不做平均**："
                "各模型方向已如实并列展示，冲突原因见 conflict 报告。"
            )
        return " ".join(parts)


# ---------------------------------------------------------------------------
# ConflictDetector
# ---------------------------------------------------------------------------


@dataclass
class ConflictReport:
    has_conflict: bool = False
    conflict_level: str = "none"  # none / minor / major / severe
    severity: str = "none"
    conflicting_engines: list[str] = field(default_factory=list)
    directions: dict[str, int] = field(default_factory=dict)
    major_conflicts: list[dict] = field(default_factory=list)
    factor_conflicts: list[dict] = field(default_factory=list)
    time_horizon_conflicts: list[dict] = field(default_factory=list)
    assumption_conflicts: list[dict] = field(default_factory=list)
    historical_conflict_stats: dict = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


#: 因子标签 → 时间尺度（用于识别"短周期 vs 长周期"冲突）
SHORT_HORIZON_CATEGORIES = {"day", "month"}
LONG_HORIZON_CATEGORIES = {"natal", "year"}


class ConflictDetector:
    """识别多模型之间的不一致来源，并给出可读原因。"""

    def detect(
        self,
        opinions: dict[str, MetaphysicsOpinion],
        *,
        factor_set: FactorSet | None = None,
        historical_stats: dict | None = None,
    ) -> ConflictReport:
        available = ConsensusEngine._available(opinions)
        dirs = {k: int(v.direction) for k, v in available.items()}
        report = ConflictReport(
            directions=dirs,
            historical_conflict_stats=dict(historical_stats or {}),
        )

        pos = [k for k, d in dirs.items() if d > 0]
        neg = [k for k, d in dirs.items() if d < 0]
        neu = [k for k, d in dirs.items() if d == 0]

        # --- 1. 方向级冲突 ---
        if pos and neg:
            report.has_conflict = True
            report.conflicting_engines = pos + neg
            report.severity = "major"
            report.conflict_level = "major" if (len(pos) + len(neg)) >= 2 else "minor"
            for k in pos:
                tops = available[k].top_positive_reasons[:2]
                report.major_conflicts.append({
                    "kind": "direction",
                    "engine": k,
                    "direction": 1,
                    "direction_label": DIRECTION_CN[1],
                    "score": available[k].score,
                    "confidence": available[k].confidence,
                    "reasons": [r.text for r in tops] or ["该引擎无明细理由"],
                    "factor_ids": [f for r in tops for f in r.factor_ids],
                })
            for k in neg:
                tops = available[k].top_negative_reasons[:2]
                report.major_conflicts.append({
                    "kind": "direction",
                    "engine": k,
                    "direction": -1,
                    "direction_label": DIRECTION_CN[-1],
                    "score": available[k].score,
                    "confidence": available[k].confidence,
                    "reasons": [r.text for r in tops] or ["该引擎无明细理由"],
                    "factor_ids": [f for r in tops for f in r.factor_ids],
                })
            report.reasons.append(
                f"方向对立：{'、'.join(f'{engine_label(k)}({DIRECTION_CN[dirs[k]]})' for k in pos)} "
                f"vs {'、'.join(f'{engine_label(k)}({DIRECTION_CN[dirs[k]]})' for k in neg)}。"
                "系统**不会**用平均值掩盖该分歧。"
            )
        elif len(neu) and (pos or neg):
            report.has_conflict = True
            report.severity = "minor"
            report.conflict_level = "minor"
            report.conflicting_engines = sorted(dirs)
            report.reasons.append(
                f"部分引擎中性：{'、'.join(engine_label(x) for x in neu)} —— 与"
                f"{'、'.join(engine_label(x) for x in pos + neg)}并存，"
                "属于强度分歧而非方向对立。"
            )

        # --- 2. 因子级冲突（跨引擎、同主题、方向相反） ---
        if factor_set is not None:
            report.factor_conflicts = self._factor_conflicts(factor_set)
            if report.factor_conflicts:
                if not report.has_conflict:
                    report.has_conflict = True
                    report.conflict_level = "minor"
                    report.severity = "minor"
                report.reasons.append(
                    f"存在 {len(report.factor_conflicts)} 组跨引擎同主题反向因子。"
                )

        # --- 3. 时间尺度冲突 ---
        if factor_set is not None:
            report.time_horizon_conflicts = self._time_horizon_conflicts(available, factor_set)
            if report.time_horizon_conflicts:
                report.reasons.extend(
                    f"{c['engine']}：{c['description']}" for c in report.time_horizon_conflicts
                )
                if report.conflict_level == "none":
                    report.conflict_level = "minor"

        # --- 4. 假设冲突 ---
        report.assumption_conflicts = self._assumption_conflicts(available)
        if report.assumption_conflicts:
            report.reasons.extend(c["description"] for c in report.assumption_conflicts)
            if report.conflict_level == "none":
                report.conflict_level = "minor"

        if not report.has_conflict:
            report.reasons.append("当前无显著冲突：各可用模型方向一致或均为中性。")
        report.notes.append(
            "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，"
            "禁止用平均分掩盖冲突（AGENTS.md §2.4）。"
        )
        report.notes.append(
            "historical_conflict_stats 未运行时视为 `NOT_RUN`，"
            "即『历史类似冲突的后续表现』尚未被统计过。"
        )
        if not report.historical_conflict_stats:
            report.historical_conflict_stats = {"status": "NOT_RUN"}
        return report

    # ------------------------------------------------------------------
    @staticmethod
    def _factor_conflicts(factor_set: FactorSet) -> list[dict]:
        """跨引擎、同 tag、方向相反的因子对。

        只在**不同引擎**之间比较 —— 同一引擎内部的因子设计上允许同向或反向，
        那不是"模型分歧"。
        """
        # tag → (engine → [(direction, factor_id, normalized)])
        by_tag: dict[str, dict[str, list[tuple[int, str, float]]]] = {}
        for o in factor_set.observations:
            if o.availability != "ok" or not o.normalized_value:
                continue
            definition = _definition_of(o.factor_id)
            if definition is None:
                continue
            engine = str(o.engine)
            for tag in definition.tags:
                by_tag.setdefault(tag, {}).setdefault(engine, []).append(
                    (int(o.direction), o.factor_id, float(o.normalized_value))
                )

        out: list[dict] = []
        for tag, per_engine in sorted(by_tag.items()):
            engines = sorted(per_engine)
            if len(engines) < 2:
                continue
            for i, ea in enumerate(engines):
                for eb in engines[i + 1:]:
                    for da, fa, na in per_engine[ea]:
                        for db, fb, nb in per_engine[eb]:
                            if da * db < 0:
                                out.append({
                                    "tag": tag,
                                    "engine_a": ea, "factor_a": fa,
                                    "direction_a": da, "value_a": na,
                                    "engine_b": eb, "factor_b": fb,
                                    "direction_b": db, "value_b": nb,
                                    "description": (
                                        f"主题「{tag}」上 {ea}.{fa}({DIRECTION_CN[da]}) "
                                        f"与 {eb}.{fb}({DIRECTION_CN[db]}) 方向相反"
                                    ),
                                })
        return out[:20]

    @staticmethod
    def _time_horizon_conflicts(
        available: dict[str, MetaphysicsOpinion], factor_set: FactorSet,
    ) -> list[dict]:
        """同一引擎内，短周期与长周期因子方向相反。"""
        out: list[dict] = []
        for engine in sorted(available):
            short = [
                float(o.normalized_value or 0.0) for o in factor_set.observations
                if str(o.engine) == engine and o.availability == "ok"
                and o.normalized_value and str(o.category) in SHORT_HORIZON_CATEGORIES
            ]
            long_ = [
                float(o.normalized_value or 0.0) for o in factor_set.observations
                if str(o.engine) == engine and o.availability == "ok"
                and o.normalized_value and str(o.category) in LONG_HORIZON_CATEGORIES
            ]
            if not short or not long_:
                continue
            s = sum(short) / len(short)
            lo = sum(long_) / len(long_)
            if s * lo < 0 and abs(s) > 0.05 and abs(lo) > 0.05:
                out.append({
                    "engine": engine,
                    "short_horizon_mean": round(s, 4),
                    "long_horizon_mean": round(lo, 4),
                    "short_sample": len(short),
                    "long_sample": len(long_),
                    "description": (
                        f"{engine_label(engine)} 内部时间尺度不一致："
                        f"长周期因子均值 {lo:.3f}、"
                        f"短周期因子均值 {s:.3f}，方向相反。"
                        "传统术数偏中长周期，短周期噪声更大，不代表两者可以互相抵消。"
                    ),
                })
        return out

    @staticmethod
    def _assumption_conflicts(available: dict[str, MetaphysicsOpinion]) -> list[dict]:
        """不同引擎的假设差异（解释分歧来源，不代表谁对）。"""
        out: list[dict] = []
        variants = {
            k: [a for a in v.assumptions if "variant" in a.lower()] for k, v in available.items()
        }
        keys_with_variant = {k for k, v in variants.items() if v}
        if len(keys_with_variant) >= 2:
            out.append({
                "kind": "variant_assumption",
                "engines": sorted(keys_with_variant),
                "description": (
                    "以下引擎的结论依赖**运限方向假设**（顺行/逆行）："
                    f"{'、'.join(engine_label(x) for x in sorted(keys_with_variant))}。"
                    "股票没有真实性别，该假设不是事实；两个方向不能互相验证。"
                ),
            })
        return out


def _definition_of(factor_id: str):  # type: ignore[no-untyped-def]
    from src.factors.registry.definitions import DEFINITION_INDEX

    return DEFINITION_INDEX.get(factor_id)


def build_consensus_and_conflict(
    opinions: dict[str, MetaphysicsOpinion],
    *,
    factor_set: FactorSet | None = None,
    data_quality: str = "B",
    research_status: str = "NOT_RUN",
    historical_stats: dict | None = None,
    historical_conflict_stats: dict | None = None,
    computed_at: datetime | None = None,
) -> tuple[ConsensusReport, ConflictReport]:
    """便捷入口：同时产出共识与分歧。"""
    consensus = ConsensusEngine().compute(
        opinions,
        data_quality=data_quality,
        research_status=research_status,
        historical_stats=historical_stats,
    )
    conflict = ConflictDetector().detect(
        opinions, factor_set=factor_set, historical_stats=historical_conflict_stats,
    )
    _ = computed_at
    return consensus, conflict


__all__ = [
    "ConsensusEngine", "ConflictDetector", "ConsensusReport", "ConflictReport",
    "build_consensus_and_conflict", "DIRECTION_CN", "ENGINE_CN", "engine_label",
    "STRONG_POSITIVE_MIN_SCORE", "STRONG_NEGATIVE_MAX_SCORE",
]
