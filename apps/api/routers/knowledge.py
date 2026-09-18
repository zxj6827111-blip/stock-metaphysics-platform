"""``/api/v1/knowledge`` 路由：古籍书目、条目、证据检索。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from apps.api.deps import get_knowledge
from src.core.config import settings
from src.core.schemas.knowledge import (
    EvidenceBundle,
    EvidenceQuery,
    KnowledgeDomain,
)
from src.knowledge.ingest.loader import corpus_meta, get_books, get_entries
from src.knowledge.retrieval.provider import build_query_from_factors

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class EvidenceSearchRequest(BaseModel):
    """证据检索请求。"""

    query: str = ""
    factor_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    domain: KnowledgeDomain = KnowledgeDomain.BAZI
    school: str | None = None
    book_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_counter: bool = Field(default=True, description="是否同时返回反证（默认必须开启）")


@router.get("/books", summary="古籍书目列表")
def list_books(domain: str | None = None) -> dict:
    books = get_books()
    if domain:
        books = [b for b in books if str(b.domain) == domain]
    return {
        "total": len(books),
        "items": [b.model_dump(mode="json") for b in books],
        "meta": corpus_meta(),
    }


@router.get("/entries", summary="古籍条目列表")
def list_entries(
    domain: str | None = None,
    school: str | None = None,
    book_id: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    entries = get_entries()
    if domain:
        entries = [e for e in entries if str(e.domain) == domain]
    if school:
        entries = [e for e in entries if e.school == school]
    if book_id:
        entries = [e for e in entries if e.book_id == book_id]
    window = entries[offset: offset + limit]
    return {
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "items": [e.model_dump(mode="json") for e in window],
        "knowledge_version": settings.knowledge_version,
    }


@router.post("/search", response_model=EvidenceBundle, summary="古籍证据检索（含反证）")
def search_evidence(payload: EvidenceSearchRequest, knowledge=Depends(get_knowledge)) -> EvidenceBundle:
    """检索古籍证据。

    **必须同时返回支持证据与反证**，以避免"先有结论、后找古籍"。
    """
    query = EvidenceQuery(
        query=payload.query,
        factor_ids=payload.factor_ids,
        topics=payload.topics,
        domain=payload.domain,
        school=payload.school,
        book_id=payload.book_id,
        top_k=payload.top_k,
        include_counter=payload.include_counter,
    )
    return knowledge.search(query)


@router.get("/by-factors", response_model=EvidenceBundle, summary="按因子 ID 检索证据")
def search_by_factors(
    factor_ids: str = Query(..., description="逗号分隔的因子 ID"),
    top_k: int = Query(5, ge=1, le=20),
    knowledge=Depends(get_knowledge),
) -> EvidenceBundle:
    ids = [f.strip() for f in factor_ids.split(",") if f.strip()]
    query = build_query_from_factors(ids)
    query.top_k = top_k
    return knowledge.search(query)


@router.get("/stats", summary="知识库统计")
def knowledge_stats(knowledge=Depends(get_knowledge)) -> dict:
    books = get_books()
    entries = get_entries()
    by_stance: dict[str, int] = {}
    for e in entries:
        by_stance[str(e.stance_hint)] = by_stance.get(str(e.stance_hint), 0) + 1
    by_license: dict[str, int] = {}
    for e in entries:
        by_license[str(e.license_status)] = by_license.get(str(e.license_status), 0) + 1
    return {
        "knowledge_version": settings.knowledge_version,
        "provider": knowledge.provider_id,
        "indexed_entries": knowledge.entry_count(),
        "books": len(books),
        "entries": len(entries),
        "by_stance": by_stance,
        "by_license_status": by_license,
        "meta": corpus_meta(),
    }
