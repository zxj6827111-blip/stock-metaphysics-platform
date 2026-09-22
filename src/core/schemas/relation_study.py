"""关系历史研究 API 的结构化响应（bazi-relation-v3）。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from src.core.schemas.common import SMBaseModel
from src.core.schemas.relation import (
    AGGREGATE_SCOPE,
    EVALUATION_TIME,
    EVALUATION_TIMEZONE,
    MATRIX_TARGET_SCOPE,
    YONGSHEN_BASIS,
)


class RelationStudyRequest(SMBaseModel):
    relation_type: str = "六合"
    universe: str = "v4-full"
    #: 指定股票即可运行小样本研究；为空时必须显式 allow_full_universe=True。
    stock_codes: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    horizons: list[int] = Field(default_factory=lambda: [1, 5, 20])
    sample_step_months: int = 3
    run_negative_controls: bool = True
    persist: bool = True
    #: 全市场确认开关：stock_codes 为空且本字段为 False 时返回 422（防误触十年重算）。
    allow_full_universe: bool = False


class RelationStudyHorizon(SMBaseModel):
    horizon: int
    sample_count: int = 0
    activation_rate: float | None = None
    mean_return: float | None = None
    median_return: float | None = None
    mean_excess_return: float | None = None
    up_rate: float | None = None
    max_drawdown: float | None = None
    p_value: float | None = None
    q_value: float | None = None
    #: p-value 与下面两个对照统计来自同一个对照面板（回显对照类型）。
    p_value_control_kind: str | None = None
    control_mean_return: float | None = None
    control_up_rate: float | None = None


class RelationStudySplit(SMBaseModel):
    name: str
    date_from: date | None = None
    date_to: date | None = None
    event_count: int = 0
    observation_count: int = 0
    sample_count: int = 0
    activation_rate: float | None = None
    horizons: list[RelationStudyHorizon] = Field(default_factory=list)
    research_status: str = "NOT_RUN"
    research_status_reasons: list[str] = Field(default_factory=list)
    negative_controls: dict[str, dict] = Field(default_factory=dict)


class RelationStudyResponse(SMBaseModel):
    experiment_id: str
    relation_type: str
    factor_id: str
    direction: int = 0
    universe: str
    universe_size: int = 0
    date_from: date | None = None
    date_to: date | None = None
    horizons: list[int] = Field(default_factory=list)
    splits: list[RelationStudySplit] = Field(default_factory=list)
    data_source: dict = Field(default_factory=dict)
    methodology: str = ""
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    # --- v3 口径回显：与 Date Scan 共用同一矩阵/聚合语义 ---
    relation_rule_version: str = ""
    relation_matrix_schema_version: str = ""
    aggregate_scope: str = AGGREGATE_SCOPE
    matrix_target_scope: list[str] = Field(default_factory=lambda: list(MATRIX_TARGET_SCOPE))
    yongshen_basis: str = YONGSHEN_BASIS
    evaluation_time: str = EVALUATION_TIME
    timezone: str = EVALUATION_TIMEZONE
    #: BH 校正范围（当前 relation_type 本次运行内的 split × horizon）。
    multiplicity_scope: str = ""
    p_value_control_kind: str | None = None
    #: 关系因子定义摘要（来自 RELATION_DEFINITION_INDEX，由 API 层填充）。
    factor_definition: dict = Field(default_factory=dict)
