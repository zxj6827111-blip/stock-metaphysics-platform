"""Narrator 输出守卫（Phase 2E）。

职责
----
对 LLM（或模板）产出的文本做**机器校验**：文本里是否出现了
EvidenceBundle 不支持的断言。

三类检查
--------
1. **禁止词**：`必涨` / `稳赚` / `高概率上涨` / `历史证明有效` / `准确率很高` …
   一律拒绝（或触发重写）。
2. **数字一致性**：文本里出现的百分数/分数如果与 bundle 中的数值对不上，
   视为幻觉。允许"1 个百分点"级别的舍入差异。
3. **状态一致性**：bundle 的 `research_status` 是 `NO_SIGNAL` / `NO_REAL_DATA` /
   `INVALID_CONTROL` 时，文本**必须**出现对应的免责表述；否则拒绝。

为什么用"拒绝 + 可读原因"而不是静默过滤
---------------------------------------
静默删词会让输出看起来"通过检查"，但读者看到的仍可能是一段被拼接得语无伦次的
文本。本项目选择**显式失败**：要么重写，要么把问题暴露给调用方。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.core.schemas.evidence import EvidenceBundle

#: 绝对禁止的表述（在任何 bundle 下都不允许出现）
FORBIDDEN_ALWAYS: tuple[str, ...] = (
    "必涨", "必跌", "稳赚", "稳赚不赔", "包赚", "保本",
    "保证上涨", "一定上涨", "必然上涨", "肯定上涨",
    "保证收益", "零风险", "无风险套利",
    "历史证明有效", "历史证明该术数有效", "准确率很高", "准确率极高",
    "高概率上涨", "大涨在即", "即将暴涨",
)

#: 只有 bundle 支持时才允许出现的表述 → 需要的 research_status 集合
CONDITIONAL_PHRASES: dict[str, frozenset[str]] = {
    "历史验证有效": frozenset({"SUPPORTED_IN_SAMPLE", "SUPPORTED_OUT_OF_SAMPLE"}),
    "统计上显著": frozenset({"SUPPORTED_IN_SAMPLE", "SUPPORTED_OUT_OF_SAMPLE"}),
    "胜率较高": frozenset({"SUPPORTED_IN_SAMPLE", "SUPPORTED_OUT_OF_SAMPLE"}),
    "样本外验证通过": frozenset({"SUPPORTED_OUT_OF_SAMPLE"}),
    "具有预测能力": frozenset({"SUPPORTED_OUT_OF_SAMPLE"}),
}

#: research_status → 文本中必须出现的表述之一
REQUIRED_DISCLAIMERS: dict[str, tuple[str, ...]] = {
    "NO_SIGNAL": ("未发现稳定信号", "未表现出超越随机", "没有统计支持", "不优于随机", "无稳定信号"),
    "NO_REAL_DATA": ("合成", "降级", "非真实数据", "不构成历史有效性证据"),
    "INVALID_CONTROL": ("负对照失效", "对照失效", "对照不独立"),
    "INSUFFICIENT_SAMPLE": ("样本不足", "样本量不足"),
    "INCONCLUSIVE": ("不确定", "证据不足", "无法判定", "结论不明确"),
    "NOT_RUN": ("未运行", "尚未检验", "没有历史统计", "未做历史检验"),
}

#: 通用强制免责（任何输出都必须包含至少一条）
GENERAL_DISCLAIMERS: tuple[str, ...] = (
    "不构成投资建议", "不构成任何投资建议", "非投资建议",
    "不代表预期收益率", "不代表上涨概率", "不代表收益预测",
    "研究用途", "研究性指标", "不是荐股",
)

_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|％)")


@dataclass
class GuardViolation:
    kind: str            # forbidden_word / conditional_claim / missing_disclaimer / number_mismatch
    detail: str
    severity: str = "error"   # error 表示必须拒绝输出


@dataclass
class GuardResult:
    passed: bool
    violations: list[GuardViolation] = field(default_factory=list)
    checked_chars: int = 0

    def summary(self) -> str:
        if self.passed:
            return "Narrator 输出通过校验。"
        return "Narrator 输出被拒绝：" + "；".join(v.detail for v in self.violations[:5])


class NarratorValidator:
    """对最终文本做机器校验。"""

    def __init__(self, *, tolerance: float = 1.0) -> None:
        #: 百分数容差（百分点）。文本说 "上涨率 58%" 而 bundle 是 58.4% 是允许的。
        self.tolerance = tolerance

    # ------------------------------------------------------------------
    def validate(self, text: str, bundle: EvidenceBundle) -> GuardResult:
        violations: list[GuardViolation] = []
        if not text or not text.strip():
            return GuardResult(
                passed=False,
                violations=[GuardViolation("empty", "输出为空")],
                checked_chars=0,
            )

        # 1) 绝对禁止词
        for phrase in FORBIDDEN_ALWAYS:
            if phrase in text:
                violations.append(GuardViolation(
                    "forbidden_word",
                    f"出现禁止表述「{phrase}」",
                ))

        # 2) 有条件表述
        status = bundle.research_status or "NOT_RUN"
        for phrase, allowed in CONDITIONAL_PHRASES.items():
            if phrase in text and status not in allowed:
                violations.append(GuardViolation(
                    "conditional_claim",
                    f"出现「{phrase}」，但 ResearchStatus={status} 不支持该表述",
                ))

        # 3) 状态对应免责
        required = REQUIRED_DISCLAIMERS.get(status, ())
        if required and not any(p in text for p in required):
            violations.append(GuardViolation(
                "missing_disclaimer",
                f"ResearchStatus={status} 时输出必须包含以下表述之一：{'/'.join(required)}",
            ))

        # 4) 通用免责
        if not any(p in text for p in GENERAL_DISCLAIMERS):
            violations.append(GuardViolation(
                "missing_disclaimer",
                "输出必须包含免责表述（如『不构成投资建议』或『不代表上涨概率』）",
            ))

        # 5) 数字一致性
        violations.extend(self._check_numbers(text, bundle))

        return GuardResult(
            passed=not violations, violations=violations, checked_chars=len(text),
        )

    # ------------------------------------------------------------------
    def _check_numbers(self, text: str, bundle: EvidenceBundle) -> list[GuardViolation]:
        """文本中的百分数必须能在 bundle 里找到对应数值（容许容差）。

        只校验**百分数**：绝对数字（如"样本 1248"）在中文叙述里形态太多，
        过度校验会大量误报。百分数是最容易被 LLM 编造、也最容易被读者当作事实的。
        """
        allowed = self._collect_numbers(bundle)
        out: list[GuardViolation] = []
        for m in _NUMBER_RE.finditer(text):
            value = float(m.group(1))
            if not self._matches(value, allowed):
                out.append(GuardViolation(
                    "number_mismatch",
                    f"文本中的 {m.group(0)} 在 EvidenceBundle 中找不到对应数值",
                ))
        return out[:10]

    def _collect_numbers(self, bundle: EvidenceBundle) -> list[float]:
        """收集 bundle 里所有百分数形态的数值（0-100 尺度）。"""
        vals: list[float] = []

        def add(x: object) -> None:
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                f = float(x)
                vals.append(f)
                if 0.0 <= f <= 1.0:      # 比例 → 也接受百分数形态
                    vals.append(f * 100.0)
                elif 0.0 <= f <= 100.0:  # 百分数 → 也接受比例形态
                    vals.append(f / 100.0)

        for op in bundle.engine_opinions.values():
            add(op.score)
            add(op.confidence)
        if bundle.consensus is not None:
            add(bundle.consensus.agreement_score)
            add(bundle.consensus.mean_score)
        h = bundle.historical.stats
        for key in ("up_rate", "mean_return", "excess_return", "positive_day_ratio",
                    "event_rate", "p_value"):
            add(h.get(key))
        for item in _iter_stat_dicts(bundle.negative_control_stats):
            add(item)
        for f in (bundle.factors.observations if bundle.factors else []):
            add(f.normalized_value)
            add(f.rule_score)
            add(f.confidence)
        return vals

    def _matches(self, value: float, allowed: list[float]) -> bool:
        if value == 0:
            return True
        for a in allowed:
            if abs(a - value) <= self.tolerance:
                return True
            # 相对容差：大数值（如收益 12.6%）允许 5% 相对误差
            if a != 0 and abs(a - value) / max(abs(a), 1e-9) <= 0.05:
                return True
        return False


def _iter_stat_dicts(payload: object):
    """递归遍历嵌套 dict/list，产出其中的数值。"""
    if isinstance(payload, dict):
        for v in payload.values():
            yield from _iter_stat_dicts(v)
    elif isinstance(payload, (list, tuple)):
        for v in payload:
            yield from _iter_stat_dicts(v)
    elif isinstance(payload, (int, float)) and not isinstance(payload, bool):
        yield float(payload)


__all__ = [
    "NarratorValidator", "GuardResult", "GuardViolation",
    "FORBIDDEN_ALWAYS", "CONDITIONAL_PHRASES", "REQUIRED_DISCLAIMERS",
    "GENERAL_DISCLAIMERS",
]
