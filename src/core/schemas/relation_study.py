"""关系历史研究 API 的结构化响应。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from src.core.schemas.common import SMBaseModel


class RelationStudyRequest(SMBaseModel):
    relation_type: str = "六合"
    universe: str = "v4-full"
    stock_codes: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    horizons: list[int] = Field(default_factory=lambda: [1, 5, 20])
    sample_step_months: int = 3
    run_negative_controls: bool = True
    persist: bool = True


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
