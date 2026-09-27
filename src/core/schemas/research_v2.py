"""W5 新版研究 API 的请求与响应契约；v1 schema 保持原样。"""

from __future__ import annotations

from datetime import date, time
from typing import Any, Literal

from pydantic import Field, FiniteFloat, model_validator

from src.core.schemas.common import SMBaseModel
from src.core.schemas.fortune import (
    FortuneRelationFilter,
    FortuneScanAvailabilityPolicy,
    FortuneScanSort,
    FortuneTenGodFilter,
    FortuneTimelineAnchorMode,
    FortuneTimelineDateMode,
    StockFortuneScanResponse,
    StockFortuneTimeline,
)


class FortuneTimelineV2Request(SMBaseModel):
    stock_code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.]+$")
    start_date: date
    end_date: date
    date_mode: FortuneTimelineDateMode = FortuneTimelineDateMode.ALL_CALENDAR_DAYS
    anchor_mode: FortuneTimelineAnchorMode = FortuneTimelineAnchorMode.EXACT_LOCAL_TIME
    evaluation_time: time | None = None
    timezone: str = "Asia/Shanghai"
    market_session_version: str = "a-share-session-v1"
    config_version: str = Field(min_length=1)
    ten_god_filters: list[FortuneTenGodFilter] = Field(default_factory=list)
    relation_filters: list[FortuneRelationFilter] = Field(default_factory=list)
    include_relation_events: bool = True
    include_month_segments: bool = True
    include_ten_god_index: bool = True

    @model_validator(mode="after")
    def validate_range_and_versions(self) -> FortuneTimelineV2Request:
        if self.end_date < self.start_date:
            raise ValueError("end_date 不得早于 start_date")
        if (self.end_date - self.start_date).days + 1 > 3660:
            raise ValueError("单次 Fortune Timeline 最多支持 3660 个自然日")
        if self.relation_filters and not self.include_relation_events:
            raise ValueError("relation_filters 要求 include_relation_events=true")
        if not self.config_version.strip() or not self.market_session_version.strip():
            raise ValueError("config_version 与 market_session_version 必须显式提供")
        return self


class FortuneTimelineV2Response(SMBaseModel):
    contract_version: Literal["research-api-v2"] = "research-api-v2"
    resolved_versions: dict[str, str | None]
    timeline: StockFortuneTimeline


class FortuneScanV2Request(SMBaseModel):
    universe_version: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    evaluation_date: date
    ten_god_filters: list[FortuneTenGodFilter] = Field(default_factory=list)
    relation_filters: list[FortuneRelationFilter] = Field(default_factory=list)
    availability_policy: FortuneScanAvailabilityPolicy = FortuneScanAvailabilityPolicy.INCLUDE
    sort: FortuneScanSort = FortuneScanSort.SYMBOL
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=100_000)
    config_version: str = Field(min_length=1)
    market_session_version: str = "a-share-session-v1"


class PitUniverseEvidenceV2(SMBaseModel):
    universe_version: str
    evidence_available: bool
    evidence_as_of: date | None = None
    evidence_source: str
    evidence_detail: str
    snapshot_date: date
    snapshot_digest: str
    member_count: int = Field(ge=0)


class FortuneScanV2Response(SMBaseModel):
    contract_version: Literal["research-api-v2"] = "research-api-v2"
    research_eligible: bool = False
    research_eligibility_status: Literal["NOT_CERTIFIED"] = "NOT_CERTIFIED"
    pit_evidence: PitUniverseEvidenceV2
    scan: StockFortuneScanResponse


class HistoricalDatasetVersions(SMBaseModel):
    """Event query 的完整且显式的版本选择。"""

    feature_version: str = Field(min_length=1)
    pit_version: str = Field(min_length=1)
    birth_profile_version: str = Field(min_length=1)
    birth_profile_source_version: str = Field(min_length=1)
    calendar_version: str = Field(min_length=1)
    engine_versions: dict[str, Any]
    rule_versions: dict[str, Any]
    config_version: str = Field(min_length=1)
    label_version: str = Field(min_length=1)
    bar_version: str = Field(min_length=1)
    factor_version: str = Field(min_length=1)
    price_basis: Literal["raw_times_factor"]


class HistoricalEventStudyV2Request(SMBaseModel):
    dataset_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    scope_mode: Literal["stock", "dates"]
    stock_code: str | None = Field(default=None, min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.]+$")
    date_from: date
    date_to: date
    factor_ids: list[str] = Field(min_length=1, max_length=64)
    activation: Literal["any", "nonzero", "positive", "negative"]
    direction_filter: Literal[-1, 0, 1] | None = None
    min_rule_score: FiniteFloat | None = Field(default=None, ge=0)
    horizon: Literal[1, 5, 20]
    versions: HistoricalDatasetVersions
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_scope(self) -> HistoricalEventStudyV2Request:
        if self.date_from > self.date_to:
            raise ValueError("date_from 不能晚于 date_to")
        if (self.date_to - self.date_from).days > 3660:
            raise ValueError("单次历史事件查询最多支持 3661 个自然日")
        if self.scope_mode == "stock" and not self.stock_code:
            raise ValueError("stock 模式必须指定 stock_code")
        if self.scope_mode == "dates" and self.stock_code is not None:
            raise ValueError("dates 模式不能指定 stock_code")
        if len(set(self.factor_ids)) != len(self.factor_ids):
            raise ValueError("factor_ids 不得重复")
        if any(not value.strip() for value in self.factor_ids):
            raise ValueError("factor_ids 不得为空")
        return self


class DescriptiveStatistics(SMBaseModel):
    sample_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    mean_return: FiniteFloat | None = None
    median_return: FiniteFloat | None = None
    win_rate: FiniteFloat | None = Field(default=None, ge=0, le=1)


class HistoricalEventV2(SMBaseModel):
    security_id: str
    stock_code: str
    research_date: date
    factor_id: str
    direction: int | None = None
    rule_score: FiniteFloat | None = None
    normalized_value: FiniteFloat | None = None
    horizon: int
    return_value: FiniteFloat | None = None
    benchmark_return: FiniteFloat | None = None
    excess_return: FiniteFloat | None = None
    label_available: bool
    missing_reason: str | None = None


class HistoricalEventStudyV2Response(SMBaseModel):
    contract_version: Literal["research-api-v2"] = "research-api-v2"
    dataset_id: str
    dataset_digest: str
    scope_mode: Literal["stock", "dates"]
    date_from: date
    date_to: date
    factor_ids: list[str]
    activation: str
    horizon: int
    versions: HistoricalDatasetVersions
    research_status: Literal["NO_REAL_DATA", "EXPLORATORY_NOT_GATED", "INSUFFICIENT_SAMPLE"]
    research_status_reasons: list[str] = Field(default_factory=list)
    candidate_observation_count: int = Field(ge=0)
    matched_observation_count: int = Field(ge=0)
    matched_date_count: int = Field(ge=0)
    missing_observation_count: int = Field(ge=0)
    missing_by_reason: dict[str, int] = Field(default_factory=dict)
    matched: DescriptiveStatistics
    complement: DescriptiveStatistics
    overall: DescriptiveStatistics
    matched_date_equal_weighted: DescriptiveStatistics
    returned_count: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    events: list[HistoricalEventV2] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HistoricalDatasetV2Response(SMBaseModel):
    contract_version: Literal["research-api-v2"] = "research-api-v2"
    dataset_id: str
    dataset_digest: str
    schema_version: str
    status: Literal["COMPLETE", "PARTIAL"]
    row_count: int = Field(ge=0)
    expected_shard_count: int = Field(ge=0)
    complete_shard_count: int = Field(ge=0)
    failed_shards: list[str] = Field(default_factory=list)
    missing_shards: list[str] = Field(default_factory=list)
    metadata: dict[str, Any]
    available_versions: list[HistoricalDatasetVersions] = Field(default_factory=list)
    research_eligible: bool = False
    confirmatory_research_eligible: bool = False


class ExperimentReportV2Response(SMBaseModel):
    contract_version: Literal["research-api-v2"] = "research-api-v2"
    experiment_id: str
    report_digest: str
    report: dict[str, Any]


__all__ = [
    "DescriptiveStatistics",
    "ExperimentReportV2Response",
    "FortuneScanV2Request",
    "FortuneScanV2Response",
    "FortuneTimelineV2Request",
    "FortuneTimelineV2Response",
    "HistoricalDatasetVersions",
    "HistoricalDatasetV2Response",
    "HistoricalEventStudyV2Request",
    "HistoricalEventStudyV2Response",
]
