"""AI Narrator（Phase 2E）—— 只解释，不计算。

两种模式
--------
| 模式 | 触发 | 说明 |
|---|---|---|
| ``template`` | 未配置 LLM（**默认**） | 由 EvidenceBundle 确定性拼装，逐条遵守 ResearchStatus 约束 |
| ``llm`` | 配置了 API Key（``SMP_LLM_API_KEY``） | 把 bundle 交给 LLM 生成叙述，**必须**通过 NarratorValidator |

**默认走模板而不是 LLM**，这是刻意的：

* 模板是确定性的、可复现的、可离线运行的；
* 它已经能完整表达"三模型各自怎么看 + 共识 + 冲突 + 历史状态"；
* LLM 带来的增量价值是"读起来更顺"，而不是"更多的信息"；
* 因此没有 API Key 时系统**不应该降级成不可用**，而应该仍然给出完整、诚实的报告。

LLM 能做什么、不能做什么
-------------------------
允许：解释 / 整理 / 总结 / 比较。
禁止：重排八字、重排紫微、重算黄历、计算四化、修改 Factor、修改 Score、
修改 ResearchStatus、修改历史统计、编造古籍、删除负面证据、隐藏模型冲突。

这些不是"提示词建议"，而是**机器校验**：任何输出都要过 `NarratorValidator`，
不通过就拒绝返回 LLM 文本，退回模板。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from src.core.schemas.evidence import EvidenceBundle
from src.narrator.guard import GuardResult, NarratorValidator

#: Narrator 模式
MODE_TEMPLATE = "template"
MODE_LLM = "llm"

SYSTEM_PROMPT = """你是「股票玄学多模型研究平台」的报告解释器。

你的唯一职责是把给定的结构化证据包（EvidenceBundle）解释成人能读懂的中文报告。

**绝对禁止（违反即视为失败输出）**
1. 不得重新排八字、重新排紫微、重新算黄历、不得计算四化或任何术数结构。
2. 不得修改证据包里的任何分数、方向、置信度、研究状态、历史统计数字。
3. 不得编造古籍条文；引用的古籍必须来自证据包中的 classical_support /
   classical_counter_evidence。
4. 不得删除或弱化负面证据：反证、模型冲突、失败的历史检验必须原样呈现。
5. 不得使用"必涨/必跌/稳赚/高概率上涨/历史证明有效/准确率很高"这类表述。
6. 不得把 opinion.score 说成上涨概率或预期收益率 —— 它是传统规则强度。
7. ResearchStatus 为 NO_SIGNAL / NO_REAL_DATA / INVALID_CONTROL / INSUFFICIENT_SAMPLE
   时，必须明确写出"历史统计未支持该判断"，不得暗示有效性。
8. 不得给出买卖建议、目标价、仓位建议。

**必须做到**
* 三个模型（八字 / 紫微 / 黄历）的观点**分别**陈述，不得平均成一个分数；
* 存在模型冲突时，明确列出冲突双方与各自理由；
* 报告结尾必须包含免责声明（不构成投资建议、分数不代表上涨概率）；
* 只使用证据包里出现过的数字。
"""


@dataclass
class NarrativeResult:
    """Narrator 输出。"""

    mode: str = MODE_TEMPLATE
    text: str = ""
    sections: dict[str, str] = field(default_factory=dict)
    guard: GuardResult | None = None
    llm_requested: bool = False
    fallback_reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def passed_guard(self) -> bool:
        return bool(self.guard and self.guard.passed)


class Narrator:
    """把 EvidenceBundle 转成可读报告。"""

    def __init__(self, *, api_key: str = "", model: str = "", base_url: str = "") -> None:
        self.api_key = api_key or os.environ.get("SMP_LLM_API_KEY", "")
        self.model = model or os.environ.get("SMP_LLM_MODEL", "gpt-4o-mini")
        self.base_url = base_url or os.environ.get("SMP_LLM_BASE_URL", "")
        self.validator = NarratorValidator()

    # ------------------------------------------------------------------
    @property
    def llm_configured(self) -> bool:
        return bool(self.api_key)

    def narrate(self, bundle: EvidenceBundle, *, prefer_llm: bool = True) -> NarrativeResult:
        """生成叙述。

        LLM 可用且被要求时优先用 LLM；**无论哪条路径，最终文本都必须过守卫**。
        LLM 输出未通过守卫时**不会**被静默采用，而是退回模板并在
        ``fallback_reason`` 中说明原因。
        """
        result = NarrativeResult(llm_requested=bool(prefer_llm and self.llm_configured))

        if result.llm_requested:
            try:
                text = self._call_llm(bundle)
                guard = self.validator.validate(text, bundle)
                if guard.passed:
                    result.mode = MODE_LLM
                    result.text = text
                    result.guard = guard
                    result.sections = self._template_sections(bundle)
                    return result
                result.fallback_reason = f"LLM 输出未通过 Narrator 守卫：{guard.summary()}"
                result.guard = guard
            except Exception as exc:  # noqa: BLE001 - LLM 不可用必须退回模板
                result.fallback_reason = f"LLM 调用失败：{type(exc).__name__}: {exc}"

        result.mode = MODE_TEMPLATE
        result.sections = self._template_sections(bundle)
        result.text = _join_sections(result.sections)
        result.guard = self.validator.validate(result.text, bundle)
        if not result.guard.passed:  # pragma: no cover - 模板自身不合规属实现缺陷
            result.warnings.append(
                "模板输出未通过守卫（这是实现缺陷，请检查 narrator.py）："
                + result.guard.summary()
            )
        return result

    # ------------------------------------------------------------------
    # LLM 路径
    # ------------------------------------------------------------------
    def _call_llm(self, bundle: EvidenceBundle) -> str:
        """调用 LLM。**只传 bundle，不传其他任何上下文。**"""
        import httpx

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "以下是唯一可用的证据包（JSON）。请据此写一份中文研究报告，"
                        "严格遵守系统提示中的禁令与要求。\n\n"
                        + bundle.model_dump_json(indent=1)
                    ),
                },
            ],
            "temperature": 0.2,
        }
        url = (self.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])

    # ------------------------------------------------------------------
    # 模板路径（默认）
    # ------------------------------------------------------------------
    def _template_sections(self, bundle: EvidenceBundle) -> dict[str, str]:
        s: dict[str, str] = {}
        s["标题"] = self._title(bundle)
        s["一、基础事实"] = self._facts(bundle)
        s["二、三个模型各自怎么看"] = self._opinions(bundle)
        s["三、共识与分歧"] = self._consensus(bundle)
        s["四、历史验证状态"] = self._historical(bundle)
        s["五、古籍依据与反证"] = self._classical(bundle)
        s["六、版本与假设"] = self._versions(bundle)
        s["七、限制与免责"] = self._disclaimer(bundle)
        return s

    def _title(self, b: EvidenceBundle) -> str:
        name = b.stock.name if b.stock else ""
        code = b.stock.stock_code if b.stock else b.analysis_id
        return f"{name} {code} · 多模型研究解读（分析 {b.analysis_id}）"

    def _facts(self, b: EvidenceBundle) -> str:
        lines: list[str] = []
        if b.stock:
            lines.append(
                f"股票：{b.stock.name}（{b.stock.stock_code}，{b.stock.exchange}"
                f"{'/' + b.stock.board if b.stock.board else ''}），"
                f"上市日期 {b.stock.listing_date or '未知'}。"
            )
        if b.birth_profile:
            bp = b.birth_profile
            lines.append(
                f"出生模型：{bp.birth_basis} → {bp.birth_datetime}（{bp.timezone}），"
                f"版本 {bp.birth_profile_version}，variant_mode={bp.variant_mode}。"
            )
        mq = b.market_data_quality
        lines.append(
            f"行情数据：来源 {mq.source or '未标注'}，"
            f"{'**已降级/合成**' if mq.is_degraded else '真实数据'}，"
            f"{mq.bar_rows} 行。"
        )
        if b.assumptions:
            lines.append("关键假设：")
            lines.extend(f"  - {a}" for a in b.assumptions[:8])
        return "\n".join(lines)

    def _opinions(self, b: EvidenceBundle) -> str:
        if not b.engine_opinions:
            return "本次分析没有任何引擎产出观点。"
        cn = {"bazi": "八字", "ziwei": "紫微斗数", "huangli": "黄历"}
        lines: list[str] = [
            "三个模型**各自独立**给出观点，本系统不做平均、不做加权成一个总分。",
            "",
        ]
        for key in ("bazi", "ziwei", "huangli"):
            op = b.engine_opinions.get(key)
            if op is None:
                continue
            label = cn.get(key, key)
            if str(op.availability) != "ok" or op.score is None:
                lines.append(f"**{label}**：不可用。{op.note}")
                continue
            direction_cn = {1: "偏强", 0: "中性", -1: "偏弱"}.get(int(op.direction), "中性")
            lines.append(
                f"**{label}**：{direction_cn}，规则强度 {op.score}/100，"
                f"置信度 {op.confidence:.2f}（引擎版本 {op.engine_version or '未记录'}）。"
            )
            for r in op.top_positive_reasons[:3]:
                lines.append(f"  - 正向依据：{r.text}")
            for r in op.top_negative_reasons[:3]:
                lines.append(f"  - 负向依据：{r.text}")
            if op.assumptions:
                lines.append("  - 该观点依赖的假设：" + "；".join(op.assumptions[:3]))
            lines.append(f"  - 说明：{op.note}")
            lines.append("")
        return "\n".join(lines)

    def _consensus(self, b: EvidenceBundle) -> str:
        c = b.consensus
        if c is None:
            return "共识不可评估（未产出共识快照）。"
        lines = [
            f"共识分类：**{c.label_cn or c.consensus_class}**"
            f"（方向一致度 {c.agreement_score:.2f}，可用引擎 {c.available_engine_count} 个）。",
        ]
        if c.engine_opinions:
            lines.append("各引擎方向：" + "；".join(
                f"{_engine_label(k)} {v.get('direction_label', '')}"
                for k, v in c.engine_opinions.items()
                if str(v.get("availability")) == "ok"
            ) + "。")
        if c.unavailable_engines:
            lines.append(
                "本次不可用的引擎：" + "、".join(str(e) for e in c.unavailable_engines)
                + "（**不计入分母，也不以 0 分代替**）。"
            )
        if c.interpretation:
            lines.append("")
            lines.append(c.interpretation)
        conf = b.conflicts
        if conf is not None and conf.has_conflict:
            lines.append("")
            lines.append(f"**模型分歧**（级别：{conf.conflict_level}）：")
            lines.extend(f"  - {r}" for r in conf.reasons[:6])
            for item in conf.major_conflicts[:4]:
                lines.append(
                    f"  - {_engine_label(str(item.get('engine')))} "
                    f"判为 {item.get('direction_label')}："
                    + "；".join(item.get("reasons", [])[:2])
                )
            lines.append(
                "  本系统如实并列展示分歧，**不使用平均值掩盖它**。"
            )
        else:
            lines.append("")
            lines.append("本次未检出显著模型分歧。")
        return "\n".join(lines)

    #: research_status → 模板中必须出现的状态解读（与 NarratorValidator 的要求对齐）
    _STATUS_NOTE: dict[str, str] = {
        "NO_SIGNAL": "本样本下**未发现稳定信号**：真实组合不优于随机对照，系统如实输出。",
        "NO_REAL_DATA": (
            "本次数据为**合成或降级行情**，不构成历史有效性证据（非真实数据）。"
        ),
        "INVALID_CONTROL": (
            "**负对照失效**：对照事件集合与真实集合重合度过高，对照不独立，结论不可用。"
        ),
        "INSUFFICIENT_SAMPLE": "**样本不足**，任何比例都没有统计意义。",
        "INCONCLUSIVE": "**证据不足**，对照结果不一致，无法判定。",
        "WEAK_EVIDENCE": "仅**样本内弱证据**，未做多重检验校正与样本外验证。",
        "SUPPORTED_IN_SAMPLE": "**样本内支持**，不等于样本外有效，也不等于未来有效。",
        "NOT_RUN": "**尚未运行历史统计**：分数与共识都没有经过历史检验。",
    }

    def _historical(self, b: EvidenceBundle) -> str:
        st = b.research_status or "NOT_RUN"
        lines = [f"研究状态（ResearchStatus）：**{st}**。"]
        note = self._STATUS_NOTE.get(st)
        if note:
            lines.append(f"  - {note}")
        if b.historical.research_status_reasons:
            lines.extend(f"  - {r}" for r in b.historical.research_status_reasons[:6])
        if b.historical.stats:
            h = b.historical.stats
            lines.append(
                "历史统计："
                + "，".join(
                    f"{k}={v}" for k, v in h.items()
                    if v is not None and k in (
                        "sample_count", "event_count", "up_rate", "mean_return",
                        "excess_return", "p_value",
                    )
                ) + "。"
            )
        if b.negative_control_stats:
            lines.append("负对照组摘要：" + str(b.negative_control_stats)[:400])
        lines.append("")
        lines.append(
            "**规则强度与统计有效性是两件事**：上面的分数只表达传统规则认为的方向与强弱，"
            "它是否在历史上有信息量，由上方的 ResearchStatus 回答。"
        )
        return "\n".join(lines)

    def _classical(self, b: EvidenceBundle) -> str:
        sup = b.classical_support or b.classical.supporting
        ctr = b.classical_counter_evidence or b.classical.counter
        lines: list[str] = []
        lines.append(f"支持性古籍证据：{len(sup)} 条。")
        for e in sup[:4]:
            lines.append(
                f"  - 《{e.get('book', '')}》：「{_clip(e.get('original_text', ''))}」"
                f"（{e.get('entry_id', '')}）"
            )
        lines.append("")
        lines.append(f"反证 / 不同流派解释：{len(ctr)} 条。")
        for e in ctr[:4]:
            lines.append(
                f"  - 《{e.get('book', '')}》：「{_clip(e.get('original_text', ''))}」"
                f"（{e.get('entry_id', '')}）"
            )
        lines.append("")
        if not ctr:
            lines.append(
                "**本次未检索到反证** —— 这本身是一个需要警惕的信号："
                "古籍检索同时返回支持与反证是本项目的强制要求，"
                "反证为空可能意味着检索词覆盖不足，请勿据此认为『古籍一致支持』。"
            )
        if b.classical.corpus_warnings:
            lines.extend(f"  - 语料提示：{w}" for w in b.classical.corpus_warnings[:3])
        lines.append("")
        lines.append(
            "古籍条文只说明传统术数的说法，**不构成对股票收益的任何判断**；"
            "本系统同时检索支持与相反观点，以避免『先有结论后找古籍』。"
        )
        return "\n".join(lines)

    def _versions(self, b: EvidenceBundle) -> str:
        v = b.versions
        rows = [
            ("engine_version", v.engine_version),
            ("rule_version", v.rule_version),
            ("config_version", v.config_version),
            ("birth_profile_version", v.birth_profile_version),
            ("knowledge_version", v.knowledge_version),
            ("market_data_version", v.market_data_version),
        ]
        lines = ["本报告所有结论可追溯到以下版本："]
        lines.extend(f"  - {k} = {val or '未记录'}" for k, val in rows)
        if b.warnings:
            lines.append("")
            lines.append("警告：")
            lines.extend(f"  - [{w.severity}] {w.code}: {w.message}" for w in b.warnings[:8])
        return "\n".join(lines)

    def _disclaimer(self, b: EvidenceBundle) -> str:
        return (
            "本报告是研究性解读，**不构成任何投资建议**，也不是荐股系统。\n"
            "\n"
            "* 观点分数是**传统规则强度**，不代表预期收益率，也不代表上涨概率；\n"
            "* 传统术数与股票未来收益之间不存在经现代金融科学确认的稳定因果关系；\n"
            "* 历史统计结果不代表未来表现；\n"
            "* 模型之间的「共识」只表示方向一致程度，不表示预测能力；\n"
            "* 使用者需自行承担全部决策风险。\n"
            "\n"
            f"（研究状态：{b.research_status or 'NOT_RUN'}；"
            f"解释模式：本段由确定性模板生成，未经 LLM 改写。）"
        )


def _engine_label(key: str) -> str:
    """引擎 key → 中文名（面向人的文本一律用中文名）。"""
    from src.core.orchestration.consensus import engine_label

    return engine_label(key)


def _clip(text: str, n: int = 60) -> str:
    text = re.sub(r"\s+", "", text or "")
    return text if len(text) <= n else text[:n] + "…"


def _join_sections(sections: dict[str, str]) -> str:
    return "\n\n".join(f"## {k}\n\n{v}" for k, v in sections.items() if v)


__all__ = ["Narrator", "NarrativeResult", "SYSTEM_PROMPT", "MODE_TEMPLATE", "MODE_LLM"]
