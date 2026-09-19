"""``EvidenceBundle``（Phase 2E）—— AI Narrator **唯一**允许读取的数据。

设计原则
--------
1. **确定性结果与解释彻底分离。** Bundle 里的每一个数字都来自确定性代码；
   LLM 只能读取它，不能修改它。
2. **冲突与反证必须在内。** 只给"支持证据"的 bundle 会诱导 LLM 写出单向结论。
3. **ResearchStatus 必须在内。** 否则 LLM 无法知道"共识高但历史无信号"这一状态。
4. **版本与假设必须在内。** 让报告能够回答"为什么上个月是 83 分，今天是 76 分"。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from src.core.schemas.analysis import ConflictSnapshot, ConsensusSnapshot, MetaphysicsOpinion
from src.core.schemas.common import SMBaseModel, VersionStamp, Warning_
from src.core.schemas.factor import FactorSet


class EvidenceStock(SMBaseModel):
    stock_code: str
    name: str = ""
    exchange: str = ""
    board: str = ""
    industry: str = ""
    listing_date: str = ""


class EvidenceBirthProfile(SMBaseModel):
    birth_basis: str = ""
    birth_datetime: str = ""
    timezone: str = ""
    variant_mode: str = ""
    birth_profile_version: str = ""
    data_quality: dict = Field(default_factory=dict)
    assumptions: list[dict] = Field(default_factory=list)


class EvidenceMarketQuality(SMBaseModel):
    source: str = ""
    is_degraded: bool = False
    is_real: bool = True
    bar_rows: int = 0
    notes: list[str] = Field(default_factory=list)


class EvidenceClassical(SMBaseModel):
    """古籍证据（支持 / 反证 **必须同时存在**）。"""

    supporting: list[dict] = Field(default_factory=list)
    counter: list[dict] = Field(default_factory=list)
    neutral: list[dict] = Field(default_factory=list)
    retrieval_method: str = ""
    corpus_warnings: list[str] = Field(default_factory=list)


class EvidenceHistorical(SMBaseModel):
    research_status: str = "NOT_RUN"
    research_status_reasons: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    negative_control: dict = Field(default_factory=dict)
    note: str = ""


class EvidenceBundle(SMBaseModel):
    """给 AI Narrator 的结构化证据包。

    **这是 Narrator 唯一允许读取的数据源。** 任何不在 bundle 里的数字，
    LLM 都不许说；任何在 bundle 里的数字，LLM 都不许改。
    """

    bundle_version: str = "evidence-bundle-v1"
    analysis_id: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)

    # --- 基础事实 ---
    stock: EvidenceStock | None = None
    birth_profile: EvidenceBirthProfile | None = None
    market_data_quality: EvidenceMarketQuality = Field(default_factory=EvidenceMarketQuality)

    # --- 原始盘面（确定性结果；Narrator 不得重算） ---
    bazi_chart: dict | None = None
    ziwei_charts: dict[str, dict] = Field(default_factory=dict)
    huangli: dict | None = None

    # --- 因子与观点 ---
    factors: FactorSet | None = None
    engine_opinions: dict[str, MetaphysicsOpinion] = Field(default_factory=dict)
    consensus: ConsensusSnapshot | None = None
    conflicts: ConflictSnapshot | None = None

    # --- 历史验证 ---
    research_status: str = "NOT_RUN"
    historical: EvidenceHistorical = Field(default_factory=EvidenceHistorical)
    negative_control_stats: dict = Field(default_factory=dict)

    # --- 古籍 ---
    classical_support: list[dict] = Field(default_factory=list)
    classical_counter_evidence: list[dict] = Field(default_factory=list)
    classical: EvidenceClassical = Field(default_factory=EvidenceClassical)

    # --- 元信息 ---
    versions: VersionStamp = Field(default_factory=VersionStamp)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)

    #: 明确告诉 Narrator "你只能读这些"
    allowed_data_note: str = (
        "本 bundle 是 AI 解释层**唯一**允许读取的数据。"
        "禁止重新排盘、禁止修改任何分数/方向/状态、禁止编造古籍、"
        "禁止删除负面证据、禁止隐藏模型冲突。"
    )


__all__ = [
    "EvidenceBundle", "EvidenceStock", "EvidenceBirthProfile",
    "EvidenceMarketQuality", "EvidenceClassical", "EvidenceHistorical",
]
