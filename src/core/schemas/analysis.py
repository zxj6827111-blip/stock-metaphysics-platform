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

    Phase 1 只由 BaziEngine / HuangliEngine 产出；**Phase 2 起紫微也产出**

    **观点是独立的**：每个引擎只消费自己的因子命名空间
    （bazi→``B_*``、huangli→``H_*``、ziwei→``Z_*``），
    不会互相"借"因子制造虚假一致。

    Phase 2 新增字段（均为可选，向后兼容）：
      * ``research_status`` —— 该引擎判断的历史验证状态（与分数**分开**）；
      * ``historical_validity`` —— 历史统计明细（未运行时为 ``{}``）；
      * ``data_quality`` —— 该观点所依赖数据的质量；
      * ``assumptions`` —— 该观点成立所依赖的假设（如运限方向）。
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

    # --- Phase 2 新增（可选） ---
    research_status: str = Field(
        default="NOT_RUN",
        description="该观点的历史验证状态（ResearchStatus 状态机）；与 score 完全分开",
    )
    historical_validity: dict = Field(default_factory=dict)
    data_quality: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)

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
    """共识快照。

    **Phase 1**：不实现正式 Consensus Engine，``display_only`` 恒为 ``True``。
    **Phase 2**：由 ``src/core/orchestration/consensus.py`` 的正式
    ``ConsensusEngine`` 产出，``display_only`` 改为 ``False``；
    字段本身保留（契约要求）。

    **共识 ≠ 历史有效**：
      * ``label`` / ``agreement_score`` —— 模型之间方向的一致程度；
      * ``research_status`` / ``historical_consensus_stats`` —— 这种一致
        在历史上是否有统计支持。

    两者必须分开呈现。系统完全可能给出"高共识 + NO_SIGNAL"。
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

    # --- Phase 2 正式 ConsensusEngine 输出（可选，向后兼容） ---
    consensus_class: str = Field(default="", description="与 label 同义的字符串形式，便于前端消费")
    agreement_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="方向一致度（与多数方向相同的引擎占比）。**不是分数平均**。",
    )
    available_engine_count: int = 0
    positive_engine_count: int = 0
    negative_engine_count: int = 0
    neutral_engine_count: int = 0
    engine_opinions: dict[str, dict] = Field(default_factory=dict)
    research_status: str = Field(default="NOT_RUN", description="ResearchStatus 状态机")
    historical_consensus_stats: dict = Field(default_factory=dict)
    interpretation: str = Field(
        default="", description="统一解读文案：共识与历史有效性同时呈现",
    )
    notes: list[str] = Field(default_factory=list)


class ConflictSnapshot(SMBaseModel):
    """分歧快照。

    **Phase 1**：展示层快照（``display_only=True``）。
    **Phase 2**：由正式 ``ConflictDetector`` 产出（``display_only=False``），字段保留。
    """

    display_only: bool = True
    has_conflict: bool = False
    severity: str = Field(default="none", description="none / minor / major")
    conflicting_engines: list[EngineId] = Field(default_factory=list)
    directions: dict[str, int] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    conflicting_factor_ids: list[str] = Field(default_factory=list)
    note: str = ""

    # --- Phase 2 正式 ConflictDetector 输出（可选，向后兼容） ---
    conflict_level: str = Field(default="none", description="none / minor / major / severe")
    major_conflicts: list[dict] = Field(default_factory=list)
    factor_conflicts: list[dict] = Field(default_factory=list)
    time_horizon_conflicts: list[dict] = Field(default_factory=list)
    assumption_conflicts: list[dict] = Field(default_factory=list)
    historical_conflict_stats: dict = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


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


class ZiweiAnalysisResponse(SMBaseModel):
    """``POST /api/v1/stocks/{code}/analysis/ziwei`` 的响应。

    紫微需要显式的方向 variant（见 ADR-0010）。``variant_mode=both`` 时
    ``charts`` 含两个 variant 的盘面，**分别保存、不得平均**。
    """

    analysis_id: str
    stock: StockMaster
    birth_profile: StockBirthProfile
    variant_mode: str = Field(description="forward / reverse / both")
    charts: dict[str, dict] = Field(
        default_factory=dict,
        description="variant → ZiweiChart 序列化结果（both 时有两个键）",
    )
    chart_artifact_ids: dict[str, str] = Field(default_factory=dict)
    factors: FactorSet | None = None
    opinions: dict[str, MetaphysicsOpinion] = Field(default_factory=dict)
    versions: VersionStamp = Field(default_factory=VersionStamp)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class MultiAnalysisResponse(SMBaseModel):
    """``POST /api/v1/stocks/{code}/analysis/multi`` 的响应（Phase 2 综合研判）。

    这是**唯一**允许被 UI 用作"综合研判"数据源的响应：
    它同时携带三个**独立**观点、共识、分歧与版本信息。

    纪律：
    * 三个 opinion 互相独立，各自只消费自己的因子命名空间；
    * 不可用引擎的 ``score`` 为 ``null``，且不计入共识分母；
    * ``consensus`` 只表达"模型之间方向一致程度"，不表达"历史有效"；
    * ``consensus.display_only`` 在 Phase 2 正式 Consensus 上线前保持 ``true``。
    """

    analysis_id: str
    stock: StockMaster
    birth_profile: StockBirthProfile
    as_of: datetime

    variant_mode: str = ""
    #: 研究窗口标签（如 ``20d``）。**只被记录，不参与因子计算**：
    #: 三个模型的分数不随它变化，事件研究使用自己的持有期集合。
    #: 回传它是为了让界面能显示"本次分析登记的窗口"，而不是让前端猜测。
    horizon: str = ""
    bazi_chart: dict | None = None
    ziwei_charts: dict[str, dict] = Field(default_factory=dict, description="variant → 盘面")
    huangli: HuangliSnapshot | None = None

    factors: FactorSet
    opinions: dict[str, MetaphysicsOpinion] = Field(default_factory=dict)
    consensus: ConsensusSnapshot | None = None
    conflict: ConflictSnapshot | None = None

    versions: VersionStamp = Field(default_factory=VersionStamp)
    warnings: list[Warning_] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
