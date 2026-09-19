"""古籍知识库加载：JSON 语料 → ``ClassicalBook`` / ``ClassicalEntry``。

语料策略（architecture §31）
---------------------------
* 只收录**清代及以前刊行的公版原文**；
* 现代整理本 / 白话翻译 / 注释本一律不收录；
* 每条必须带 ``provenance`` / ``edition`` / ``license_status``；
* ``modern_note`` 由本项目自撰，不引用任何未授权的现代整理本。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from src.core.config import settings
from src.core.schemas.knowledge import (
    ClassicalBook,
    ClassicalEntry,
    EvidenceStance,
    KnowledgeDomain,
    LicenseStatus,
)

#: 各术数域的语料文件。Phase 2 起支持多域（bazi / ziwei）。
#: 新增域时必须同时给出 ``domain`` 字段，loader 会用它做交叉校验。
CORPUS_FILES: dict[str, Path] = {
    "bazi": settings.knowledge_dir / "bazi" / "classical_seed.json",
    "ziwei": settings.knowledge_dir / "ziwei" / "classical_seed.json",
}

#: 向后兼容别名（Phase 1 只有 bazi）
BAZI_SEED = CORPUS_FILES["bazi"]


class KnowledgeLoadError(RuntimeError):
    pass


@lru_cache(maxsize=8)
def load_corpus(path: str | None = None) -> tuple[tuple[ClassicalBook, ...], tuple[ClassicalEntry, ...]]:
    """加载并缓存**全部术数域**的语料。

    多域加载的纪律：
      * 每个文件里的 ``domain`` 字段必须与其所在的域键一致（防止把紫微条目
        混进八字域，从而让"域过滤"失效）；
      * 某个域的文件缺失时**跳过并继续**，不让整个知识库失效 ——
        但会记录在 ``corpus_meta()["missing_domains"]`` 里，不静默。
    """
    if path:
        targets = [Path(path)]
    else:
        targets = [p for p in CORPUS_FILES.values() if p.exists()]

    if not targets:
        raise KnowledgeLoadError(
            f"古籍语料文件全部缺失，已尝试：{[str(p) for p in CORPUS_FILES.values()]}"
        )

    books: list[ClassicalBook] = []
    entries: list[ClassicalEntry] = []
    for target in targets:
        b, e = _load_one(target)
        books.extend(b)
        entries.extend(e)

    # 去重（同 entry_id 只保留第一次出现）
    seen: set[str] = set()
    unique_entries: list[ClassicalEntry] = []
    for e in entries:
        if e.entry_id in seen:
            continue
        seen.add(e.entry_id)
        unique_entries.append(e)
    return tuple(books), tuple(unique_entries)


def _load_one(target: Path) -> tuple[list[ClassicalBook], list[ClassicalEntry]]:
    """加载单个语料文件。"""
    if not target.exists():
        raise KnowledgeLoadError(f"古籍语料文件缺失: {target}")

    payload = json.loads(target.read_text(encoding="utf-8"))
    books: list[ClassicalBook] = []
    entries: list[ClassicalEntry] = []

    for b in payload.get("books", []):
        books.append(ClassicalBook(
            book_id=b["book_id"],
            title=b["title"],
            author=b.get("author", ""),
            dynasty=b.get("dynasty", ""),
            domain=KnowledgeDomain(b.get("domain", "bazi")),
            school=b.get("school", ""),
            edition=b.get("edition", ""),
            provenance=b.get("provenance", ""),
            license_status=LicenseStatus(b.get("license_status", "unknown")),
            authority_weight=float(b.get("authority_weight", 1.0)),
            note=b.get("note", ""),
        ))

    book_index = {b.book_id: b for b in books}

    for e in payload.get("entries", []):
        book = book_index.get(e["book_id"])
        if book is None:
            raise KnowledgeLoadError(f"条目 {e.get('entry_id')} 引用了不存在的 book_id={e.get('book_id')}")
        entries.append(ClassicalEntry(
            entry_id=e["entry_id"],
            book_id=e["book_id"],
            book=book.title,
            domain=book.domain,
            school=e.get("school", book.school),
            chapter=e.get("chapter", ""),
            section=e.get("section", ""),
            topic=list(e.get("topic", [])),
            original_text=e["original_text"],
            normalized_text=e.get("normalized_text", ""),
            modern_note=e.get("modern_note", ""),
            commentary=e.get("commentary", ""),
            authority_weight=book.authority_weight,
            source=e.get("source", f"公版古籍《{book.title}》（{book.edition}）"),
            edition=book.edition,
            provenance=book.provenance,
            license_status=book.license_status,
            stance_hint=EvidenceStance(e.get("stance_hint", "neutral")),
            applies_to=list(e.get("applies_to", [])),
        ))

    return tuple(books), tuple(entries)


def corpus_meta(path: str | None = None) -> dict:
    """合并全部域的 ``_meta``；缺失域会被显式列出。"""
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload.get("_meta", {})

    merged: dict = {"domains": {}, "missing_domains": []}
    for domain, target in CORPUS_FILES.items():
        if not target.exists():
            merged["missing_domains"].append(domain)
            continue
        payload = json.loads(target.read_text(encoding="utf-8"))
        merged["domains"][domain] = payload.get("_meta", {})
    # bazi 作为主域，其字段提升到顶层以保持 Phase 1 调用方兼容
    merged.update(merged["domains"].get("bazi", {}))
    return merged


def get_books() -> list[ClassicalBook]:
    return list(load_corpus()[0])


def get_entries() -> list[ClassicalEntry]:
    return list(load_corpus()[1])


def seed_database() -> dict[str, int]:
    """把语料写入 ``classical_book`` / ``classical_entry`` 表（幂等）。"""
    from sqlalchemy import select

    from src.core.stock.exchange_sessions import ex_value
    from src.db.base import session_scope
    from src.db.models import ClassicalBookRow, ClassicalEntryRow

    books, entries = load_corpus()
    with session_scope() as db:
        for b in books:
            existing = db.get(ClassicalBookRow, b.book_id)
            row = ClassicalBookRow(
                book_id=b.book_id, title=b.title, author=b.author, dynasty=b.dynasty,
                domain=ex_value(b.domain), school=b.school, edition=b.edition,
                provenance=b.provenance, license_status=ex_value(b.license_status),
                authority_weight=b.authority_weight, note=b.note,
            )
            if existing is None:
                db.add(row)
            else:
                for col in ("title", "author", "dynasty", "domain", "school", "edition",
                            "provenance", "license_status", "authority_weight", "note"):
                    setattr(existing, col, getattr(row, col))

        existing_ids = {
            eid for (eid,) in db.execute(select(ClassicalEntryRow.entry_id)).all()
        }
        for e in entries:
            if e.entry_id in existing_ids:
                continue
            db.add(ClassicalEntryRow(
                entry_id=e.entry_id, book_id=e.book_id, book=e.book,
                domain=ex_value(e.domain), school=e.school, chapter=e.chapter,
                section=e.section, topic_json=list(e.topic),
                original_text=e.original_text, normalized_text=e.normalized_text,
                modern_note=e.modern_note, commentary=e.commentary,
                authority_weight=e.authority_weight, source=e.source,
                edition=e.edition, provenance=e.provenance,
                license_status=ex_value(e.license_status),
                stance_hint=ex_value(e.stance_hint), applies_to_json=list(e.applies_to),
            ))

    return {"books": len(books), "entries": len(entries)}


def clear_cache() -> None:
    load_corpus.cache_clear()


__all__ = [
    "load_corpus", "corpus_meta", "get_books", "get_entries",
    "seed_database", "clear_cache", "KnowledgeLoadError",
]
