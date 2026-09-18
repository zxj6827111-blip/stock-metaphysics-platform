"""分析编排与 API 输出 Schema。

包含：
  - ``MetaphysicsOpinion``：引擎观点契约（Phase 2 的 Consensus 基础）
  - ``AnalysisRun``：一次分析的完整上下文
  - ``ConsensusSnapshot`` / ``ConflictSnapshot``：**展示层**聚合（Phase 1 不做正式
    Consensus Engine，仅用于 UI 呈现，且必须显式标注 ``display_only=True``）
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from src.core.schemas.calendar import HuangliSnapshot
from src.core.schemas.common import (
    Availability,
    ConsensusLabel,
    EngineId,
    SMBaseModel,
    VersionStamp,
    Warning_,
)
from src.core.schemas.factor import FactorSet
from src.core.schemas.stock import StockBirthProfile, StockMaster


class ReasonItem(SMBaseModel):
    """一条正向/负向理由。"""

    text: str
    factor_ids: list[str] = Field(default_factory=list)
    rule_score: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class MetaphysicsOpinion(SMBaseModel):
    """引擎观点契约（对应 two_session_plan §26）。

    Phase 1 只由 BaziEngine / HuangliEngine 产出，**不**做最终融合。
    """

    engine: EngineId
    engine_version: str = ""
    availability: Availability = Availability.OK
    direction: int = Field(default=0, description="-1 / 0 / 1")
    score: float | None = Field(default=None, description="0-100 规则分；不可用时为 None，禁止用 0 冒充")
    confidence: float = 0.0
    top_positive_reasons: list[ReasonItem] = Field(default_factory=list)
    top_negative_reasons: list[ReasonItem] = Field(default_factory=list)
    factor_ids: list[str] = Field(default_factory=list)
    historical_validity: dict = Field(default_factory=dict)
    note: str = Field(
        default="该分数由传统规则强度聚合得到，属于研究性指标，不代表收益率预测。",
    )
    warnings: list[Warning_] = Field(default_factory=list)


class EngineDisplayCard(SMBaseModel):
    """UI 模型评分卡数据。"""

    engine: EngineId
    display_name: str
    availability: Availability = Availability.OK
    score: float | None = None
    direction: int = 0
    direction_label: str = ""
    confidence: float | None = None
    positive_count: int = 0
    negative_count: int = 0
    summary: str = ""
    unavailable_reason: str = ""
    detail_route: str = ""


class ConsensusSnapshot(SMBaseModel):
    """展示层共识快照。

    **重要**：Phase 1 不实现正式 Consensus Engine。
    本结构仅用于 UI 呈现，``display_only`` 必须为 True，
    且参与引擎为空/不可用时必须如实显示 unavailable，绝不用 0 分替代。
    """

    display_only: bool = True
    label: ConsensusLabel = ConsensusLabel.NEUTRAL
    label_cn: str = ""
    participating_engines: list[EngineId] = Field(default_factory=list)
    unavailable_engines: list[EngineId] = Field(default_factory=list)
    directions: dict[str, int] = Field(default_factory=dict)
    mean_score: float | None = None
    agreement: str = Field(default="", description="一致性：高 / 中 / 低 / 不可评估")
    historical_validity: str = Field(default="", description="历史验证强度——与共识分开")
    data_quality: str = ""
    note: str = ""


class ConflictSnapshot(SMBaseModel):
    """展示层分歧快照（正式 ConflictDetector 属 Phase 2）。"""

    display_only: bool = True
    has_conflict: bool = False
    severity: str = Field(default="none", description="none / minor / major")
    conflicting_engines: list[EngineId] = Field(default_factory=list)
    directions: dict[str, int] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    conflicting_factor_ids: list[str] = Field(default_factory=list)
    note: str = ""


class AnalysisRun(SMBaseModel):
    """一次分析运行的完整上下文（API ``GET /analysis/{id}`` 的基础）。"""

    analysis_id: str
    stock_code: str
    as_of: datetime
    horizon: str = "20d"

    stock: StockMaster | None = None
    birth_profile: StockBirthProfile | None = None

    engines_requested: list[EngineId] = Field(default_factory=list)
    engines_completed: list[EngineId] = Field(default_factory=list)
    engines_failed: list[dict] = Field(default_factory=list)

    chart_artifact_ids: dict[str, str] = Field(default_factory=dict, description="engine → chart_artifact_id")
    factor_set: FactorSet | None = None
    opinions: dict[str, MetaphysicsOpinion] = Field(default_factory=dict)
    consensus: ConsensusSnapshot | None = None
    conflict: ConflictSnapshot | None = None

    versions: VersionStamp = Field(default_factory=VersionStamp)
    warnings: list[Warning_] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    duration_ms: int = 0


class StockSearchItem(SMBaseModel):
    """股票搜索结果项。"""

    stock_code: str
    wind_code: str = ""
    name: str = ""
    exchange: str = ""
    board: str = ""
    listing_date: str = ""


class StockSearchResponse(SMBaseModel):
    items: list[StockSearchItem] = Field(default_factory=list)
    total: int = 0
    query: str = ""
    source: str = ""
    is_degraded: bool = False
    warnings: list[Warning_] = Field(default_factory=list)


class DataQualityReport(SMBaseModel):
    """数据质量报告（UI DataQualityBadge 数据源）。"""

    overall_grade: str = "B"
    overall_score: float = 0.8
    items: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BaziAnalysisResponse(SMBaseModel):
    """``POST /api/v1/stocks/{code}/analysis/bazi`` 的响应。"""

    analysis_id: str
    stock: StockMaster
    birth_profile: StockBirthProfile
    chart: dict = Field(description="BaziChart 序列化结果（原始盘面）")
    huangli: HuangliSnapshot | None = None
    factors: FactorSet
    opinion: MetaphysicsOpinion
    versions: VersionStamp = Field(default_factory=VersionStamp)
    warnings: list[Warning_] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
