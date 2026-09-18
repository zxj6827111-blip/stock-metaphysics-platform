"""KnowledgeProvider —— 古籍知识检索接口（architecture §32、two_session_plan §14）。

检索管线（沿用 bazi-pro 的思路，但完全解耦）：

    BM25 相关性
      × Authority Weight（古籍权威权重）
      × Topic Match（主题匹配度）
      × Domain Filter（域过滤：紫微请求绝不能混入八字典籍）

**必须同时返回支持证据与反证**（architecture §33）：

    supporting_evidence  支持当前规则/结论的古籍
    counter_evidence     与当前规则/结论相反的古籍
    neutral_evidence     中性背景

这是为了避免"先有结论、后找古籍"。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from src.core.config import settings
from src.core.schemas.knowledge import (
    ClassicalEntry,
    EvidenceBundle,
    EvidenceItem,
    EvidenceQuery,
    EvidenceStance,
    KnowledgeDomain,
)

# 中文停用词（极简）
STOPWORDS = {
    "的", "了", "是", "在", "与", "和", "而", "之", "也", "矣", "者", "其",
    "以", "为", "不", "有", "无", "乃", "则", "於", "于", "所", "故", "皆",
}


class KnowledgeProvider(ABC):
    """古籍知识检索契约。"""

    provider_id: str = "base"

    @abstractmethod
    def search(self, query: EvidenceQuery) -> EvidenceBundle:
        """检索证据包（必须包含 counter_evidence）。"""

    @abstractmethod
    def entry_count(self) -> int:
        """语料规模。"""


def tokenize(text: str) -> list[str]:
    """中文分词：优先 jieba，失败时退化为字符 n-gram。

    jieba 首次加载较慢，但结果稳定；这里做懒加载。
    """
    if not text:
        return []
    try:
        import jieba

        tokens = [t.strip() for t in jieba.lcut(text) if t.strip()]
    except Exception:  # noqa: BLE001 - jieba 不可用时降级
        tokens = list(text)

    out: list[str] = []
    for t in tokens:
        if t in STOPWORDS:
            continue
        if len(t) == 1 and not _is_cjk(t):
            continue
        out.append(t)
    return out


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


class Bm25KnowledgeProvider(KnowledgeProvider):
    """BM25 + 主题匹配 + 权威权重 的本地检索实现。"""

    provider_id = "bm25"

    def __init__(self, entries: list[ClassicalEntry] | None = None) -> None:
        if entries is None:
            from src.knowledge.ingest.loader import get_entries

            entries = get_entries()
        self._entries = entries
        self._corpus_tokens = [tokenize(self._doc_text(e)) for e in entries]
        self._bm25 = None
        self._build_index()

    # ------------------------------------------------------------------
    def _doc_text(self, entry: ClassicalEntry) -> str:
        return " ".join([
            entry.original_text,
            entry.modern_note,
            " ".join(entry.topic),
            entry.book,
            entry.chapter,
        ])

    def _build_index(self) -> None:
        try:
            from rank_bm25 import BM25Okapi

            if self._corpus_tokens:
                self._bm25 = BM25Okapi(self._corpus_tokens)
        except Exception:  # noqa: BLE001 - 无 rank_bm25 时退化为关键词计数
            self._bm25 = None

    # ------------------------------------------------------------------
    def entry_count(self) -> int:
        return len(self._entries)

    def search(self, query: EvidenceQuery) -> EvidenceBundle:
        terms = self._query_terms(query)
        scored: list[tuple[float, ClassicalEntry]] = []

        for idx, entry in enumerate(self._entries):
            if not self._passes_filter(entry, query):
                continue
            score = self._score(entry, idx, terms, query)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        candidates = scored[: max(query.top_k * 3, query.top_k)]

        supporting, counter, neutral = [], [], []
        for score, entry in candidates:
            item = self._to_item(entry, score, terms)
            stance = self._classify(entry, query)
            item.stance = stance
            if stance == EvidenceStance.COUNTER:
                counter.append(item)
            elif stance == EvidenceStance.SUPPORTING:
                supporting.append(item)
            else:
                neutral.append(item)

        top_k = query.top_k
        return EvidenceBundle(
            query=query,
            supporting_evidence=supporting[:top_k],
            counter_evidence=counter[:top_k] if query.include_counter else [],
            neutral_evidence=neutral[:top_k],
            total_candidates=len(scored),
            retrieval_method="bm25 + topic_match + authority_weight + domain_filter",
            knowledge_version=settings.knowledge_version,
            note=(
                "本系统同时检索支持与相反观点，以避免『先有结论后找古籍』。"
                "古籍条文只说明传统术数的说法，不构成对股票收益的任何判断。"
            ),
        )

    # ------------------------------------------------------------------
    def _query_terms(self, query: EvidenceQuery) -> list[str]:
        parts = [query.query, *query.topics]
        tokens: list[str] = []
        for p in parts:
            tokens.extend(tokenize(p))
        # 去重并保序
        seen: set[str] = set()
        out: list[str] = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def _passes_filter(self, entry: ClassicalEntry, query: EvidenceQuery) -> bool:
        if query.domain and entry.domain != query.domain:
            return False
        if query.school and entry.school != query.school:
            return False
        return not (query.book_id and entry.book_id != query.book_id)

    def _score(
        self,
        entry: ClassicalEntry,
        idx: int,
        terms: list[str],
        query: EvidenceQuery,
    ) -> float:
        bm25 = 0.0
        if self._bm25 is not None and terms:
            try:
                scores = self._bm25.get_scores(terms)
                bm25 = float(scores[idx])
            except Exception:  # noqa: BLE001
                bm25 = 0.0

        if bm25 <= 0 and terms:
            # 退化路径：字符命中计数
            text = self._doc_text(entry)
            bm25 = float(sum(text.count(t) for t in terms)) * 0.5

        # 主题匹配：命中 topic 的查询词数量
        topic_hits = sum(1 for t in terms if any(t in tp or tp in t for tp in entry.topic))
        topic_bonus = topic_hits * 1.5

        # 因子 ID 精确匹配（applies_to 是结构化提示）
        factor_bonus = 0.0
        for fid in query.factor_ids:
            if fid in entry.applies_to:
                factor_bonus += 3.0

        # 反证条目在"支持检索"中不应被压低 —— 它本来就要被展示
        raw = (bm25 * 0.4) + topic_bonus + factor_bonus
        return raw * max(entry.authority_weight, 0.1)

    def _classify(self, entry: ClassicalEntry, query: EvidenceQuery) -> EvidenceStance:
        """判定条目相对本次查询的立场。

        规则：
          1. 条目自带 ``stance_hint`` 且与查询因子相关 → 采用之；
          2. 否则视为中性背景。
        """
        if entry.stance_hint in (EvidenceStance.COUNTER, EvidenceStance.SUPPORTING):
            if not query.factor_ids:
                return entry.stance_hint
            if any(f in entry.applies_to for f in query.factor_ids) or not entry.applies_to:
                return entry.stance_hint
        return EvidenceStance.NEUTRAL

    @staticmethod
    def _to_item(entry: ClassicalEntry, score: float, terms: list[str]) -> EvidenceItem:
        matched = [t for t in terms if t and (t in entry.original_text or t in entry.modern_note)]
        return EvidenceItem(
            entry_id=entry.entry_id,
            book=entry.book,
            chapter=entry.chapter,
            school=entry.school,
            topic=list(entry.topic),
            original_text=entry.original_text,
            modern_note=entry.modern_note,
            score=round(score, 4),
            authority_weight=entry.authority_weight,
            stance=entry.stance_hint,
            source=entry.source,
            edition=entry.edition,
            provenance=entry.provenance,
            license_status=entry.license_status,
            matched_query_terms=matched[:6],
        )


def build_query_from_factors(factor_ids: list[str], extra_query: str = "") -> EvidenceQuery:
    """根据因子 ID 自动构造检索请求（用因子名称 + 标签做检索词）。"""
    from src.factors.registry.definitions import DEFINITION_INDEX

    topics: list[str] = []
    names: list[str] = []
    for fid in factor_ids:
        d = DEFINITION_INDEX.get(fid)
        if d is None:
            continue
        topics.extend(d.tags)
        names.append(d.name)

    query_text = " ".join([extra_query, *names]).strip()
    seen: set[str] = set()
    uniq_topics = [t for t in topics if not (t in seen or seen.add(t))]

    return EvidenceQuery(
        query=query_text,
        factor_ids=list(factor_ids),
        topics=uniq_topics,
        domain=KnowledgeDomain.BAZI,
        top_k=6,
        include_counter=True,
    )


_PROVIDER: KnowledgeProvider | None = None


def get_knowledge_provider(force_rebuild: bool = False) -> KnowledgeProvider:
    global _PROVIDER
    if _PROVIDER is None or force_rebuild:
        _PROVIDER = Bm25KnowledgeProvider()
    return _PROVIDER


def reset_knowledge_provider() -> None:
    global _PROVIDER
    _PROVIDER = None


__all__ = [
    "KnowledgeProvider", "Bm25KnowledgeProvider", "get_knowledge_provider",
    "reset_knowledge_provider", "build_query_from_factors", "tokenize",
]


# 让正则导入不报未使用（保留供未来查询语法扩展使用）
_ = re
