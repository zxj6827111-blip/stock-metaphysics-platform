"""AI Narrator 与 NarratorValidator 测试（Phase 2E）。

本文件验证三件事：

1. **LLM 不得计算**：bundle 是 Narrator 唯一允许读取的数据。
2. **幻觉防护**：禁止词、状态一致性、数值一致性三道检查都要真的拦得住。
3. **降级不得不诚实**：没有 API Key 时必须仍能产出完整报告（模板模式），
   而不是"不可用"；LLM 输出不合格时必须退回模板并说明原因。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.schemas.analysis import (
    ConflictSnapshot,
    ConsensusSnapshot,
    MetaphysicsOpinion,
    ReasonItem,
)
from src.core.schemas.common import Availability, ConsensusLabel, EngineId, VersionStamp
from src.core.schemas.evidence import (
    EvidenceBirthProfile,
    EvidenceBundle,
    EvidenceClassical,
    EvidenceHistorical,
    EvidenceMarketQuality,
    EvidenceStock,
)
from src.core.schemas.factor import FactorObservation, FactorSet
from src.narrator.guard import (
    CONDITIONAL_PHRASES,
    FORBIDDEN_ALWAYS,
    GENERAL_DISCLAIMERS,
    NarratorValidator,
)
from src.narrator.narrator import MODE_LLM, MODE_TEMPLATE, SYSTEM_PROMPT, Narrator

AS_OF = datetime(2024, 11, 15, 14, 32)


# ---------------------------------------------------------------------------
# 构造 bundle
# ---------------------------------------------------------------------------


def _opinion(engine: str, direction: int, score: float | None, conf: float = 0.6,
             available: bool = True) -> MetaphysicsOpinion:
    if not available:
        return MetaphysicsOpinion(
            engine=EngineId(engine), availability=Availability.UNAVAILABLE,
            direction=0, score=None, confidence=0.0,
            note="测试：故意不可用，不以 0 分替代。",
        )
    return MetaphysicsOpinion(
        engine=EngineId(engine), engine_version="test-1.0",
        availability=Availability.OK, direction=direction, score=score, confidence=conf,
        top_positive_reasons=[ReasonItem(text="正向依据 A", factor_ids=["B_NATAL_001"])]
        if direction > 0 else [],
        top_negative_reasons=[ReasonItem(text="负向依据 B", factor_ids=["Z_LIFE_004"])]
        if direction < 0 else [],
        factor_ids=["B_NATAL_001"],
        assumptions=["测试假设：运限方向 variant 由调用方显式指定。"],
    )


def _factor_set() -> FactorSet:
    return FactorSet(
        stock_code="600519", as_of=AS_OF,
        observations=[
            FactorObservation(
                factor_id="B_NATAL_001", stock_code="600519", as_of=AS_OF,
                engine=EngineId.BAZI, category="natal", name="日主强弱",
                raw_value=0.5, normalized_value=0.5, direction=1,
                rule_score=5.0, confidence=0.7, availability="ok",
                rule_version="v1.1", engine_version="test",
            ),
            FactorObservation(
                factor_id="Z_LIFE_001", stock_code="600519", as_of=AS_OF,
                engine=EngineId.ZIWEI, category="natal", name="命宫主星庙旺和",
                raw_value=-0.4, normalized_value=-0.4, direction=-1,
                rule_score=4.0, confidence=0.6, availability="ok",
                rule_version="zv1.fwd", engine_version="test",
            ),
            FactorObservation(
                factor_id="H_DAY_003", stock_code="600519", as_of=AS_OF,
                engine=EngineId.HUANGLI, category="day", name="日支冲破",
                raw_value=0.0, normalized_value=None, direction=0,
                rule_score=0.0, confidence=0.0, availability="unavailable",
                rule_version="v1.1", engine_version="test",
            ),
        ],
    )


def make_bundle(
    *,
    research_status: str = "NOT_RUN",
    consensus_label: ConsensusLabel = ConsensusLabel.MIXED,
    with_conflict: bool = True,
    ziwei_available: bool = True,
) -> EvidenceBundle:
    opinions = {
        "bazi": _opinion("bazi", 1, 72.5, 0.65),
        "ziwei": _opinion("ziwei", -1 if ziwei_available else 0,
                          28.0 if ziwei_available else None, 0.6,
                          available=ziwei_available),
        "huangli": _opinion("huangli", 0, 51.0, 0.55),
    }
    consensus = ConsensusSnapshot(
        display_only=False,
        label=consensus_label,
        label_cn="模型分歧",
        participating_engines=[EngineId.BAZI, EngineId.ZIWEI, EngineId.HUANGLI],
        directions={"bazi": 1, "ziwei": -1, "huangli": 0},
        mean_score=50.5,
        agreement_score=0.6667,
        available_engine_count=3,
        positive_engine_count=1,
        negative_engine_count=1,
        neutral_engine_count=1,
        consensus_class=str(consensus_label),
        research_status=research_status,
        interpretation=(
            "术数模型之间的一致性：模型分歧。 "
            + ("**术数共识高，但历史统计未发现稳定信号**（ResearchStatus=NO_SIGNAL）。"
               if research_status == "NO_SIGNAL" else
               "**历史统计未运行**：上述一致性只是模型之间的方向比较。" )
        ),
    )
    conflict = ConflictSnapshot(
        display_only=False, has_conflict=with_conflict, severity="major",
        conflict_level="major",
        conflicting_engines=[EngineId.BAZI, EngineId.ZIWEI],
        directions={"bazi": 1, "ziwei": -1, "huangli": 0},
        reasons=["方向对立：bazi(偏强) vs ziwei(偏弱)。系统**不会**用平均值掩盖该分歧。"],
        major_conflicts=[
            {"engine": "bazi", "direction": 1, "direction_label": "偏强",
             "score": 72.5, "reasons": ["正向依据 A"]},
            {"engine": "ziwei", "direction": -1, "direction_label": "偏弱",
             "score": 28.0, "reasons": ["负向依据 B"]},
        ],
    )
    return EvidenceBundle(
        analysis_id="AN-TEST-0001",
        generated_at=AS_OF,
        stock=EvidenceStock(stock_code="600519", name="贵州茅台", exchange="SSE",
                            board="主板", industry="白酒", listing_date="2001-08-27"),
        birth_profile=EvidenceBirthProfile(
            birth_basis="listing_open", birth_datetime="2001-08-27T09:30:00",
            timezone="Asia/Shanghai", variant_mode="forward",
            birth_profile_version="v1", data_quality={"grade": "A"},
        ),
        market_data_quality=EvidenceMarketQuality(
            source="tencent_hfq_import", is_degraded=False, is_real=True, bar_rows=3800,
        ),
        factors=_factor_set(),
        engine_opinions=opinions,
        consensus=consensus,
        conflicts=conflict,
        research_status=research_status,
        historical=EvidenceHistorical(
            research_status=research_status,
            research_status_reasons=["测试用研究状态说明。"],
            stats={"sample_count": 448, "up_rate": 0.583, "mean_return": 0.0621,
                   "p_value": 0.12},
        ),
        classical_support=[
            {"entry_id": "ZWQS-0003", "book": "紫微斗数骨髓赋",
             "original_text": "紫微居午，无杀凑，位至公卿。", "score": 0.92},
        ],
        classical_counter_evidence=[
            {"entry_id": "ZWQS-0005", "book": "紫微斗数骨髓赋",
             "original_text": "七杀廉贞同位，反为积富之人。", "score": 0.81},
        ],
        classical=EvidenceClassical(corpus_warnings=["语料未逐字校勘"]),
        versions=VersionStamp(
            engine_version="smx-bazi-native-1.0.0", rule_version="v1.1",
            config_version="cfg-2026.09", birth_profile_version="v1",
            knowledge_version="kb-1.1.0", market_data_version="akshare-1.18.96",
        ),
        assumptions=["[bazi] 股票出生时柱口径：23:00 后归次日子时。"],
    )


# ---------------------------------------------------------------------------
# 1. NarratorValidator
# ---------------------------------------------------------------------------


class TestForbiddenWords:
    validator = NarratorValidator()

    @pytest.mark.parametrize("word", FORBIDDEN_ALWAYS)
    def test_every_forbidden_word_is_rejected(self, word):
        bundle = make_bundle()
        text = f"分析结论：该股{word}。不构成投资建议。"
        result = self.validator.validate(text, bundle)
        assert not result.passed, f"禁止词 {word} 未被拦截"
        assert any(v.kind == "forbidden_word" for v in result.violations)

    def test_clean_text_passes(self):
        bundle = make_bundle(research_status="NO_SIGNAL")
        text = (
            "该股八字偏强、紫微偏弱、黄历中性，模型之间存在分歧。"
            "术数共识高，但历史统计未发现稳定信号。"
            "分数是传统规则强度，不代表上涨概率，本报告不构成投资建议。"
        )
        result = self.validator.validate(text, bundle)
        assert result.passed, result.summary()


class TestConditionalClaims:
    validator = NarratorValidator()

    @pytest.mark.parametrize("phrase", list(CONDITIONAL_PHRASES))
    def test_conditional_phrase_requires_supporting_status(self, phrase):
        bundle = make_bundle(research_status="NO_SIGNAL")
        text = f"{phrase}。不构成投资建议。另：历史统计未发现稳定信号。"
        result = self.validator.validate(text, bundle)
        assert not result.passed, f"在 NO_SIGNAL 下仍放行了「{phrase}」"
        assert any(v.kind == "conditional_claim" for v in result.violations)

    def test_conditional_phrase_allowed_when_supported(self):
        bundle = make_bundle(research_status="SUPPORTED_IN_SAMPLE")
        text = (
            "历史验证有效（样本内）。不代表上涨概率，不构成投资建议。"
        )
        result = self.validator.validate(text, bundle)
        assert result.passed, result.summary()


class TestStatusDisclaimers:
    validator = NarratorValidator()

    @pytest.mark.parametrize("status", [
        "NO_SIGNAL", "NO_REAL_DATA", "INVALID_CONTROL",
        "INSUFFICIENT_SAMPLE", "INCONCLUSIVE", "NOT_RUN",
    ])
    def test_required_disclaimer_present_or_rejected(self, status):
        bundle = make_bundle(research_status=status)
        # 缺少对应状态说明 → 拒绝
        bad = self.validator.validate("该股结构偏强。不构成投资建议。", bundle)
        assert not bad.passed, f"{status} 时缺少状态说明却通过了校验"
        assert any(v.kind == "missing_disclaimer" for v in bad.violations)

    @pytest.mark.parametrize("phrase", GENERAL_DISCLAIMERS)
    def test_general_disclaimer_required(self, phrase):
        bundle = make_bundle(research_status="NOT_RUN")
        # 不包含任何通用免责时被拒
        no_disclaimer = self.validator.validate("该股结构偏强，未运行历史统计。", bundle)
        assert not no_disclaimer.passed
        ok = self.validator.validate(f"该股结构偏强。未运行历史统计。{phrase}。", bundle)
        assert ok.passed, ok.summary()


class TestNumberConsistency:
    validator = NarratorValidator()

    def test_fabricated_percentage_is_rejected(self):
        bundle = make_bundle()
        text = "历史上涨率 87.3%，不构成投资建议。历史统计未运行。"
        result = self.validator.validate(text, bundle)
        assert not result.passed
        assert any(v.kind == "number_mismatch" for v in result.violations)

    def test_bundle_numbers_are_accepted(self):
        bundle = make_bundle()
        # bundle 里有 72.5 / 28.0 / 0.583 / 0.0621
        text = (
            "八字规则强度 72.5，紫微 28.0。历史统计上涨率 58.3%，"
            "平均收益 6.21%。历史统计未运行（本行为示例）。不构成投资建议。"
        )
        result = self.validator.validate(text, bundle)
        assert result.passed, result.summary()

    def test_rounding_tolerance_allows_small_drift(self):
        bundle = make_bundle()
        text = "上涨率 58%（bundle 为 58.3%）。历史统计未运行。不构成投资建议。"
        result = self.validator.validate(text, bundle)
        assert result.passed, result.summary()

    def test_zero_is_always_allowed(self):
        bundle = make_bundle()
        text = "样本数 0，历史统计未运行。不构成投资建议。"
        assert self.validator.validate(text, bundle).passed

    def test_empty_output_is_rejected(self):
        bundle = make_bundle()
        assert not self.validator.validate("", bundle).passed
        assert not self.validator.validate("   ", bundle).passed


# ---------------------------------------------------------------------------
# 2. Narrator 模板模式（默认）
# ---------------------------------------------------------------------------


class TestNarratorTemplateMode:
    def test_default_mode_is_template_without_api_key(self):
        n = Narrator(api_key="")
        r = n.narrate(make_bundle(research_status="NO_SIGNAL"))
        assert r.mode == MODE_TEMPLATE
        assert r.llm_requested is False
        assert r.text
        assert r.passed_guard, r.guard.summary() if r.guard else ""

    def test_template_covers_all_required_sections(self):
        n = Narrator(api_key="")
        r = n.narrate(make_bundle())
        for key in ("标题", "一、基础事实", "二、三个模型各自怎么看", "三、共识与分歧",
                    "四、历史验证状态", "五、古籍依据与反证", "六、版本与假设",
                    "七、限制与免责"):
            assert key in r.sections, f"缺少章节 {key}"

    def test_template_states_each_model_separately(self):
        """三个模型必须分别陈述，不得被平均成一个总分。"""
        r = Narrator(api_key="").narrate(make_bundle())
        text = r.sections["二、三个模型各自怎么看"]
        for label in ("**八字**", "**紫微斗数**", "**黄历**"):
            assert label in text
        assert "不做平均" in text

    def test_template_exposes_conflict(self):
        r = Narrator(api_key="").narrate(make_bundle(with_conflict=True))
        text = r.sections["三、共识与分歧"]
        assert "模型分歧" in text
        assert "不使用平均值掩盖" in text
        assert "紫微斗数" in text and "八字" in text, (
            "面向人的文本必须用中文引擎名，不能直接抛 bazi/ziwei 这样的内部 key"
        )

    def test_template_shows_counter_evidence(self):
        r = Narrator(api_key="").narrate(make_bundle())
        text = r.sections["五、古籍依据与反证"]
        assert "反证" in text
        assert "ZWQS-0005" in text

    def test_template_warns_when_no_counter_evidence(self):
        b = make_bundle()
        b.classical_counter_evidence = []
        b.classical.counter = []
        r = Narrator(api_key="").narrate(b)
        text = r.sections["五、古籍依据与反证"]
        assert "未检索到反证" in text
        assert "古籍一致支持" in text, "必须明确禁止把『无反证』解读为『古籍一致支持』"

    def test_template_lists_versions(self):
        r = Narrator(api_key="").narrate(make_bundle())
        text = r.sections["六、版本与假设"]
        for v in ("smx-bazi-native-1.0.0", "kb-1.1.0", "cfg-2026.09"):
            assert v in text

    @pytest.mark.parametrize("status", ["NO_SIGNAL", "NO_REAL_DATA", "INVALID_CONTROL"])
    def test_template_respects_research_status(self, status):
        r = Narrator(api_key="").narrate(make_bundle(research_status=status))
        assert status in r.sections["四、历史验证状态"]
        assert r.passed_guard, r.guard.summary() if r.guard else ""

    def test_unavailable_engine_not_reported_as_zero(self):
        r = Narrator(api_key="").narrate(make_bundle(ziwei_available=False))
        text = r.sections["二、三个模型各自怎么看"]
        ziwei_line = next(ln for ln in text.splitlines() if ln.startswith("**紫微斗数**"))
        assert "不可用" in ziwei_line
        assert "/100" not in ziwei_line, "不可用引擎绝不能显示分数（更不能用 0 分）"

    def test_template_is_deterministic(self):
        b = make_bundle()
        a = Narrator(api_key="").narrate(b)
        c = Narrator(api_key="").narrate(b)
        assert a.text == c.text


# ---------------------------------------------------------------------------
# 3. Narrator LLM 路径与降级
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class TestNarratorLLMPath:
    def test_good_llm_output_is_used(self, monkeypatch):
        good = (
            "该股八字偏强、紫微偏弱，模型存在分歧。"
            "未运行历史统计。分数不代表上涨概率，不构成投资建议。"
        )
        monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse(good))
        n = Narrator(api_key="test-key")
        r = n.narrate(make_bundle(research_status="NOT_RUN"))
        assert r.llm_requested is True
        assert r.mode == MODE_LLM
        assert r.text == good
        assert r.passed_guard

    def test_hallucinating_llm_falls_back_to_template(self, monkeypatch):
        """LLM 输出含禁止词时必须退回模板，**不静默采用**。"""
        bad = "该股必涨，历史证明有效，准确率很高。"
        monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse(bad))
        n = Narrator(api_key="test-key")
        r = n.narrate(make_bundle(research_status="NO_SIGNAL"))
        assert r.mode == MODE_TEMPLATE
        assert r.fallback_reason, "必须说明为什么退回模板"
        assert "守卫" in r.fallback_reason
        assert "必涨" not in r.text
        assert r.passed_guard

    def test_llm_with_fabricated_numbers_falls_back(self, monkeypatch):
        bad = (
            "历史上涨率 94.7%，胜率极高。历史统计未发现稳定信号。不构成投资建议。"
        )
        monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse(bad))
        r = Narrator(api_key="test-key").narrate(make_bundle(research_status="NO_SIGNAL"))
        assert r.mode == MODE_TEMPLATE
        assert "number_mismatch" in r.fallback_reason or "守卫" in r.fallback_reason

    def test_llm_exception_falls_back_to_template(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("网络不可达")

        monkeypatch.setattr("httpx.post", boom)
        r = Narrator(api_key="test-key").narrate(make_bundle())
        assert r.mode == MODE_TEMPLATE
        assert "网络不可达" in r.fallback_reason
        assert r.passed_guard

    def test_prefer_llm_false_skips_llm(self):
        r = Narrator(api_key="test-key").narrate(make_bundle(), prefer_llm=False)
        assert r.mode == MODE_TEMPLATE
        assert r.llm_requested is False

    def test_system_prompt_contains_the_ten_prohibitions(self):
        """禁令必须是**机器可读的提示词**，而不是口头约定。"""
        for phrase in (
            "不得重新排八字", "不得修改", "不得编造古籍", "不得删除或弱化负面证据",
            "不得使用", "不得把 opinion.score", "不得给出买卖建议",
        ):
            assert phrase in SYSTEM_PROMPT, phrase
        assert "ResearchStatus" in SYSTEM_PROMPT

    def test_bundle_is_the_only_input(self, monkeypatch):
        """发给 LLM 的 payload 只应包含 EvidenceBundle。"""
        captured: dict = {}

        class _Cap(_FakeResponse):
            def __init__(self, *a, **k) -> None:
                super().__init__("未运行历史统计。不构成投资建议。")

        def fake_post(url, **kwargs):
            captured.update(kwargs.get("json", {}))
            return _Cap()

        monkeypatch.setattr("httpx.post", fake_post)
        Narrator(api_key="k").narrate(make_bundle(research_status="NOT_RUN"))
        content = captured["messages"][1]["content"]
        assert "AN-TEST-0001" in content, "bundle 内容必须原样传入"
        # 系统提示是固定常量（含禁令），用户消息只放 bundle —— 二者不得混用
        assert captured["messages"][0]["content"] == SYSTEM_PROMPT
        assert SYSTEM_PROMPT not in content, "系统提示不得重复塞进用户消息"


# ---------------------------------------------------------------------------
# 4. 多域语料
# ---------------------------------------------------------------------------


class TestMultiDomainCorpus:
    def test_ziwei_domain_is_loaded(self):
        from src.knowledge.ingest.loader import corpus_meta, get_books, get_entries

        entries = get_entries()
        domains = {str(e.domain) for e in entries}
        assert {"bazi", "ziwei"} <= domains
        assert any(str(b.domain) == "ziwei" for b in get_books())
        meta = corpus_meta()
        assert "ziwei" in meta.get("domains", {})
        assert not meta.get("missing_domains")

    def test_ziwei_entries_carry_required_provenance(self):
        from src.knowledge.ingest.loader import get_entries

        for e in get_entries():
            if str(e.domain) != "ziwei":
                continue
            assert e.source and e.edition and e.provenance
            assert str(e.license_status) == "public_domain"
            assert e.original_text
            assert e.modern_note, f"{e.entry_id} 缺少自撰说明"

    def test_ziwei_entries_declare_mapping_is_research_assumption(self):
        """紫微条目的现代说明必须声明宫位映射是研究假设，不是传统定论。"""
        from src.knowledge.ingest.loader import get_entries

        ziwei = [e for e in get_entries() if str(e.domain) == "ziwei"]
        assert len(ziwei) >= 10
        assert any("研究假设" in e.modern_note or "非传统定论" in e.modern_note
                   for e in ziwei)

    def test_ziwei_domain_is_retrievable_and_returns_counter_evidence(self):
        """紫微域必须能被检索到，且**必须同时返回反证**。"""
        from src.core.schemas.knowledge import EvidenceQuery, KnowledgeDomain
        from src.knowledge.retrieval.provider import get_knowledge_provider

        provider = get_knowledge_provider(force_rebuild=True)
        query = EvidenceQuery(query="命宫 紫微 庙旺 四化", domain=KnowledgeDomain.ZIWEI,
                              top_k=8, include_counter=True)
        bundle = provider.search(query)
        assert bundle.supporting_evidence, "紫微域应能检索到支持证据"
        assert bundle.counter_evidence, (
            "紫微域必须同时返回反证 —— 反证为空会让 LLM 写出单向结论"
        )
        for item in bundle.supporting_evidence + bundle.counter_evidence:
            assert str(item.license_status) == "public_domain"
            assert item.provenance

    def test_corpus_meta_warns_about_textual_criticism(self):
        from src.knowledge.ingest.loader import corpus_meta

        meta = corpus_meta()
        warnings = str(meta.get("textual_criticism_warning", "")) + str(
            meta.get("domains", {}).get("ziwei", {}).get("textual_criticism_warning", "")
        )
        assert "校勘" in warnings
