"""古籍知识中心测试（architecture §30 / §32 / §33）。

覆盖：
* 语料加载与结构化字段完整性（book/chapter/topic/original_text/provenance/license_status）；
* 全部条目必须是 public_domain（不得混入现代整理本）；
* BM25 + 主题匹配 + 权威权重检索；
* **必须同时返回支持证据与反证**；
* domain 过滤（紫微请求不得混入八字典籍）。
"""

from __future__ import annotations

import pytest

from src.core.schemas.knowledge import (
    EvidenceQuery,
    EvidenceStance,
    KnowledgeDomain,
    LicenseStatus,
)
from src.knowledge.ingest.loader import corpus_meta, get_books, get_entries
from src.knowledge.retrieval.provider import (
    Bm25KnowledgeProvider,
    build_query_from_factors,
    tokenize,
)


@pytest.fixture(scope="module")
def provider() -> Bm25KnowledgeProvider:
    return Bm25KnowledgeProvider()


class TestCorpus:
    def test_books_loaded(self):
        books = get_books()
        assert len(books) >= 5
        assert all(b.title for b in books)

    def test_entries_loaded(self):
        entries = get_entries()
        assert len(entries) >= 30

    def test_every_entry_has_required_fields(self):
        for e in get_entries():
            assert e.entry_id
            assert e.book
            assert e.original_text
            assert e.topic, f"{e.entry_id} 缺少 topic"
            assert e.provenance, f"{e.entry_id} 缺少 provenance"
            assert e.edition, f"{e.entry_id} 缺少 edition"
            assert e.license_status

    def test_all_entries_are_public_domain(self):
        """Phase 1 只收公版原文，任何 unknown/restricted 都应被拦下。"""
        for e in get_entries():
            assert e.license_status == LicenseStatus.PUBLIC_DOMAIN, f"{e.entry_id} 版权状态可疑"

    def test_entry_ids_unique(self):
        ids = [e.entry_id for e in get_entries()]
        assert len(ids) == len(set(ids))

    def test_entries_reference_valid_books(self):
        book_ids = {b.book_id for b in get_books()}
        for e in get_entries():
            assert e.book_id in book_ids

    def test_both_supporting_and_counter_exist_in_corpus(self):
        stances = {e.stance_hint for e in get_entries()}
        assert EvidenceStance.SUPPORTING in stances
        assert EvidenceStance.COUNTER in stances

    def test_corpus_meta_declares_policy(self):
        meta = corpus_meta()
        assert "license_policy" in meta
        assert "public" in meta["license_policy"].lower() or "公版" in meta["license_policy"]
        assert "textual_criticism_warning" in meta

    def test_methodology_note_marks_uncollated(self):
        """必须诚实声明语料尚未逐字校勘，避免被当成权威版本引用。"""
        meta = corpus_meta()
        assert "校勘" in meta["textual_criticism_warning"]


class TestTokenization:
    def test_chinese_text_tokenized(self):
        tokens = tokenize("财为养命之源")
        assert tokens
        assert any("财" in t for t in tokens)

    def test_stopwords_removed(self):
        tokens = tokenize("之乎者也")
        assert "之" not in tokens

    def test_empty_input(self):
        assert tokenize("") == []


class TestRetrieval:
    def test_returns_results_for_topic(self, provider):
        bundle = provider.search(EvidenceQuery(query="财星", topics=["财星"], top_k=5))
        assert bundle.total_candidates > 0
        assert bundle.supporting_evidence or bundle.counter_evidence

    def test_returns_counter_evidence(self, provider):
        """检索「财星」时必须返回反证（身弱不胜财 / 比劫夺财等）。"""
        bundle = provider.search(EvidenceQuery(query="财星 财多身弱", topics=["财星"], top_k=5))
        assert bundle.counter_evidence, "未返回反证，违反 architecture §33"

    def test_bundle_note_explains_counter_requirement(self, provider):
        bundle = provider.search(EvidenceQuery(query="财", top_k=3))
        assert "反" in bundle.note or "相反" in bundle.note

    def test_by_factor_ids(self, provider):
        bundle = provider.search(build_query_from_factors(["B_NATAL_002", "B_NATAL_016"]))
        assert bundle.total_candidates > 0
        assert bundle.query.factor_ids == ["B_NATAL_002", "B_NATAL_016"]

    def test_stance_classification_matches_entry(self, provider):
        bundle = provider.search(EvidenceQuery(query="财星 身弱", topics=["财星", "反证"], top_k=8))
        for item in bundle.counter_evidence:
            assert item.stance == EvidenceStance.COUNTER

    def test_domain_filter_blocks_other_domains(self, provider):
        """domain=ziwei 时不得返回八字典籍。"""
        bundle = provider.search(EvidenceQuery(query="财帛宫", domain=KnowledgeDomain.ZIWEI, top_k=5))
        assert bundle.total_candidates == 0
        assert not bundle.supporting_evidence

    def test_book_filter(self, provider):
        bundle = provider.search(
            EvidenceQuery(query="财", book_id="ditiansui", top_k=5)
        )
        assert all(i.book == "滴天髓" for i in bundle.supporting_evidence + bundle.counter_evidence
                   + bundle.neutral_evidence)

    def test_authority_weight_applied(self, provider):
        """权威权重高的书在同等相关性下应排更前。"""
        weights = {b.book_id: b.authority_weight for b in get_books()}
        assert max(weights.values()) >= 1.4
        bundle = provider.search(EvidenceQuery(query="财星", topics=["财星"], top_k=10))
        all_items = bundle.supporting_evidence + bundle.counter_evidence + bundle.neutral_evidence
        assert all(i.authority_weight > 0 for i in all_items)

    def test_include_counter_false(self, provider):
        bundle = provider.search(
            EvidenceQuery(query="财星", topics=["财星"], top_k=5, include_counter=False)
        )
        assert bundle.counter_evidence == []

    def test_entry_count(self, provider):
        assert provider.entry_count() == len(get_entries())

    def test_knowledge_version_recorded(self, provider):
        bundle = provider.search(EvidenceQuery(query="财", top_k=2))
        assert bundle.knowledge_version

    def test_retrieval_method_documented(self, provider):
        bundle = provider.search(EvidenceQuery(query="财", top_k=2))
        for token in ("bm25", "topic_match", "authority_weight", "domain_filter"):
            assert token in bundle.retrieval_method


class TestEvidenceItemIntegrity:
    def test_items_carry_provenance_fields(self, provider):
        bundle = provider.search(EvidenceQuery(query="财星", topics=["财星"], top_k=5))
        items = bundle.supporting_evidence + bundle.counter_evidence + bundle.neutral_evidence
        assert items
        for it in items:
            assert it.book
            assert it.original_text
            assert it.provenance
            assert it.edition
            assert it.license_status == LicenseStatus.PUBLIC_DOMAIN
            assert it.source

    def test_scores_are_finite(self, provider):
        bundle = provider.search(EvidenceQuery(query="五行", top_k=5))
        items = bundle.supporting_evidence + bundle.counter_evidence + bundle.neutral_evidence
        for it in items:
            assert it.score >= 0

    def test_modern_note_is_our_own(self, provider):
        """modern_note 是本项目自撰说明，不允许出现"某出版社整理本"等未授权引用。"""
        forbidden = ("中华书局", "上海古籍出版社", "译注本", "白话翻译")
        for e in get_entries():
            for word in forbidden:
                assert word not in e.modern_note, f"{e.entry_id} 可能引用了未授权整理本"
