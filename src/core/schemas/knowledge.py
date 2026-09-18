"""古籍知识中心 Schema。

设计纪律（architecture §30、§33）：

1. 古籍条目必须结构化，不能只保存 Markdown 大文本。
2. 每条必须带 ``provenance`` / ``edition`` / ``license_status``。
3. 检索必须同时返回 ``supporting_evidence`` 与 ``counter_evidence``，
   不允许只找支持当前结论的古籍。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from src.core.schemas.common import SMBaseModel


class KnowledgeDomain(str, Enum):
    """术数域。Phase 1 只启用 BAZI。"""

    BAZI = "bazi"
    ZIWEI = "ziwei"
    LIUYAO = "liuyao"
    QIMEN = "qimen"
    COMMON = "common"


class LicenseStatus(str, Enum):
    """版权状态。禁止因为某 GitHub 仓库使用了某文本就默认可商用。"""

    PUBLIC_DOMAIN = "public_domain"      # 公版（作者逝世逾版权期限的古代刊本原文）
    VERIFIED = "verified"                # 已核实授权
    UNKNOWN = "unknown"                  # 未核实 —— 不得商用
    RESTRICTED = "restricted"            # 明确受限


class EvidenceStance(str, Enum):
    """证据立场。"""

    SUPPORTING = "supporting"   # 支持当前规则/结论
    COUNTER = "counter"         # 与当前规则/结论相反
    NEUTRAL = "neutral"         # 中性背景


class ClassicalBook(SMBaseModel):
    """古籍书目。"""

    book_id: str
    title: str
    author: str = ""
    dynasty: str = ""
    domain: KnowledgeDomain = KnowledgeDomain.BAZI
    school: str = Field(default="", description="流派：子平 / 盲派 / 新派 / 三合 / 飞星 …")
    edition: str = Field(default="", description="版本，如 四库全书本 / 中华书局点校本")
    provenance: str = Field(default="", description="来源与流转")
    license_status: LicenseStatus = LicenseStatus.PUBLIC_DOMAIN
    authority_weight: float = Field(default=1.0, ge=0.0, le=2.0, description="权威权重")
    note: str = ""


class ClassicalEntry(SMBaseModel):
    """古籍条目（结构化最小单元）。"""

    entry_id: str
    book_id: str
    book: str = Field(default="", description="书名（冗余，便于检索展示）")
    domain: KnowledgeDomain = KnowledgeDomain.BAZI
    school: str = ""
    chapter: str = ""
    section: str = ""
    topic: list[str] = Field(default_factory=list, description="主题标签，如 ['财星','食神','格局']")
    original_text: str
    normalized_text: str = ""
    modern_note: str = Field(default="", description="现代说明（本项目自撰，避免使用未授权整理本）")
    commentary: str = Field(default="", description="历代注文（若为公版）")
    authority_weight: float = 1.0
    source: str = ""
    edition: str = ""
    provenance: str = ""
    license_status: LicenseStatus = LicenseStatus.PUBLIC_DOMAIN

    # 结构化匹配提示：用于"支持 / 反证"分类
    stance_hint: EvidenceStance = EvidenceStance.NEUTRAL
    applies_to: list[str] = Field(default_factory=list, description="适用的因子 ID 或结构名")


class EvidenceItem(SMBaseModel):
    """检索返回的一条证据。"""

    entry_id: str
    book: str
    chapter: str = ""
    school: str = ""
    topic: list[str] = Field(default_factory=list)
    original_text: str
    modern_note: str = ""
    score: float = 0.0
    authority_weight: float = 1.0
    stance: EvidenceStance = EvidenceStance.NEUTRAL
    source: str = ""
    edition: str = ""
    provenance: str = ""
    license_status: LicenseStatus = LicenseStatus.PUBLIC_DOMAIN
    matched_query_terms: list[str] = Field(default_factory=list)


class EvidenceQuery(SMBaseModel):
    """一次证据检索请求。"""

    query: str = ""
    factor_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    domain: KnowledgeDomain = KnowledgeDomain.BAZI
    school: str | None = None
    book_id: str | None = None
    top_k: int = 5
    include_counter: bool = True


class EvidenceBundle(SMBaseModel):
    """证据包：支持证据 + 反证 + 检索元信息。"""

    query: EvidenceQuery
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    counter_evidence: list[EvidenceItem] = Field(default_factory=list)
    neutral_evidence: list[EvidenceItem] = Field(default_factory=list)
    total_candidates: int = 0
    retrieval_method: str = Field(default="bm25+topic_match+authority_weight")
    knowledge_version: str = ""
    note: str = Field(
        default="",
        description="本系统同时检索支持与相反观点，以避免'先有结论后找古籍'",
    )
    computed_at: datetime = Field(default_factory=datetime.now)
