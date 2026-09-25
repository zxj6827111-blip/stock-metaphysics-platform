"""Stock Fortune Engine V1 的内部领域契约。

这些模型不由现有 /api/v1 路由直接暴露。它们与 legacy StockBirthProfile
并存，供 Fortune Engine 后续阶段逐步接入；本模块不包含排盘或评分算法。
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Literal

from pydantic import FiniteFloat, Field, model_validator

from src.core.schemas.calendar import CalendarSnapshot, GanZhi
from src.core.schemas.common import (
    Assumption,
    DataQuality,
    Exchange,
    SMBaseModel,
    SourceRef,
    Warning_,
)
from src.core.schemas.ten_god import TenGodHiddenStem, TenGodRef


FORTUNE_CONTRACT_VERSION = "stock-fortune-contract-v1"
FORTUNE_BIRTH_PROFILE_VERSION = "stock-fortune-birth-v1"


class FortuneBirthBasis(str, Enum):
    """Fortune V1 采用的股票出生基准。"""

    MARKET_FIRST_TRADE = "MARKET_FIRST_TRADE"
    COMPANY_FOUNDING = "COMPANY_FOUNDING"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


class BirthTimePrecision(str, Enum):
    EXACT = "EXACT"
    INFERRED = "INFERRED"
    DATE_ONLY = "DATE_ONLY"
    UNKNOWN = "UNKNOWN"


class FortunePolarity(str, Enum):
    """可追溯的阴阳标签；它本身不决定大运方向。"""

    YANG = "YANG"
    YIN = "YIN"


class LuckCycleDirection(str, Enum):
    """排运算法产出的实际方向，与兼容性别参数分开保存。"""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"


class CompatibilityGender(str, Enum):
    """仅供传统算法 Adapter 使用的兼容参数，不是股票属性。"""

    MALE = "male"
    FEMALE = "female"


class FortuneAvailability(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class NatalPillarAvailability(str, Enum):
    FOUR_PILLARS = "four_pillars"
    THREE_PILLARS = "three_pillars"
    UNAVAILABLE = "unavailable"


class FortuneTemporalLayer(str, Enum):
    DAYUN = "dayun"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"


class FortuneRuleValence(str, Enum):
    """规则层方向，不表达市场涨跌方向。"""

    SUPPORT = "support"
    PRESSURE = "pressure"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class FortuneScoreKind(str, Enum):
    RULE_SCORE = "rule_score"
    RESONANCE_SCORE = "resonance_score"


class MarketSessionStatus(str, Enum):
    CONTINUOUS_TRADING = "continuous_trading"
    BREAK = "break"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class FortuneRelationCategory(str, Enum):
    """关系结构类别；不预设吉凶、财富方向或权重。"""

    COMBINATION = "combination"
    CLASH = "clash"
    PUNISHMENT = "punishment"
    HARM = "harm"
    BREAK = "break"
    OTHER = "other"


class FortuneRelationScope(str, Enum):
    NATAL_NATAL = "natal_natal"
    TEMPORAL_TO_NATAL = "temporal_to_natal"
    TEMPORAL_TO_TEMPORAL = "temporal_to_temporal"


class StockFortuneBirthProfile(SMBaseModel):
    """Fortune V1 出生档案；保留上市日期与实际首次交易时间的区别。"""

    contract_version: Literal["stock-fortune-contract-v1"] = FORTUNE_CONTRACT_VERSION
    symbol: str = Field(min_length=1, description="标准证券代码")
    exchange: Exchange = Exchange.UNKNOWN
    listing_date: date | None = None
    first_trade_datetime: datetime | None = Field(
        default=None,
        description="有来源证明的实际首次交易时刻；不得从 listing_date 伪造",
    )
    birth_basis: FortuneBirthBasis = FortuneBirthBasis.MARKET_FIRST_TRADE
    birth_datetime: datetime | None = Field(
        default=None,
        description="按 birth_basis 选定的计算时刻；DATE_ONLY/UNKNOWN 时必须为空",
    )
    timezone: str = "Asia/Shanghai"
    birth_time_precision: BirthTimePrecision = BirthTimePrecision.UNKNOWN
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="unavailable"))
    source_version: str = "unknown"
    confidence: FiniteFloat | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="来源数据可信度；不表示市场预测概率",
    )
    birth_profile_version: str = FORTUNE_BIRTH_PROFILE_VERSION
    rule_version: str = "stock-fortune-birth-rule-v1"
    config_version: str = ""
    assumptions: list[Assumption] = Field(default_factory=list)
    data_quality: DataQuality | None = None

    @model_validator(mode="after")
    def validate_precision_and_source_time(self) -> StockFortuneBirthProfile:
        requires_time = self.birth_time_precision in {
            BirthTimePrecision.EXACT,
            BirthTimePrecision.INFERRED,
        }
        if requires_time and self.birth_datetime is None:
            raise ValueError("EXACT/INFERRED 必须带 birth_datetime")
        if requires_time and (
            self.birth_datetime.tzinfo is None
            or self.birth_datetime.utcoffset() is None
        ):
            raise ValueError("birth_datetime 必须包含时区")
        if self.birth_time_precision in {
            BirthTimePrecision.DATE_ONLY,
            BirthTimePrecision.UNKNOWN,
        } and self.birth_datetime is not None:
            raise ValueError("DATE_ONLY/UNKNOWN 不得伪造 birth_datetime")
        if self.birth_time_precision in {
            BirthTimePrecision.DATE_ONLY,
            BirthTimePrecision.UNKNOWN,
        } and self.first_trade_datetime is not None:
            raise ValueError("DATE_ONLY/UNKNOWN 不得携带精确 first_trade_datetime")
        if self.birth_time_precision == BirthTimePrecision.INFERRED and not self.assumptions:
            raise ValueError("INFERRED 必须公开记录 assumptions")
        if (
            self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE
            and self.birth_time_precision == BirthTimePrecision.EXACT
            and self.first_trade_datetime is None
        ):
            raise ValueError("EXACT 的 MARKET_FIRST_TRADE 必须保留 first_trade_datetime")
        if (
            self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE
            and self.birth_time_precision == BirthTimePrecision.INFERRED
            and self.first_trade_datetime is not None
        ):
            raise ValueError("INFERRED 不得把推定时刻伪装成 first_trade_datetime")
        if self.first_trade_datetime is not None:
            if self.first_trade_datetime.tzinfo is None or self.first_trade_datetime.utcoffset() is None:
                raise ValueError("first_trade_datetime 必须包含时区")
            if self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE:
                if self.birth_time_precision != BirthTimePrecision.EXACT:
                    raise ValueError("实际首次交易时间必须标记为 EXACT")
                if self.birth_datetime != self.first_trade_datetime:
                    raise ValueError("MARKET_FIRST_TRADE 的 birth_datetime 必须等于实际 first_trade_datetime")
        return self


class FortuneLuckCycleContext(SMBaseModel):
    """显式保留极性、方向结论与传统算法兼容参数三个不同概念。"""

    polarity: FortunePolarity | None = None
    direction: LuckCycleDirection | None = None
    compatibility_gender: CompatibilityGender | None = Field(
        default=None,
        description="只在调用传统排运算法时使用；不表示股票有真实性别",
    )
    availability: FortuneAvailability = FortuneAvailability.UNAVAILABLE
    direction_basis: str = ""
    rule_version: str = "fortune-dayun-direction-v1"

    @model_validator(mode="after")
    def validate_direction_state(self) -> FortuneLuckCycleContext:
        if self.availability == FortuneAvailability.AVAILABLE and self.direction is None:
            raise ValueError("AVAILABLE 的排运上下文必须有实际 direction")
        if self.availability == FortuneAvailability.UNAVAILABLE and self.direction is not None:
            raise ValueError("UNAVAILABLE 不得携带看似有效的 direction")
        return self


class NatalPillarSet(SMBaseModel):
    """原局柱位的可用性；日期资料不足时可明确返回三柱。"""

    availability: NatalPillarAvailability
    year: GanZhi | None = None
    month: GanZhi | None = None
    day: GanZhi | None = None
    hour: GanZhi | None = None
    warnings: list[Warning_] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_pillar_shape(self) -> NatalPillarSet:
        required = (self.year, self.month, self.day)
        if self.availability == NatalPillarAvailability.FOUR_PILLARS:
            if any(pillar is None for pillar in (*required, self.hour)):
                raise ValueError("FOUR_PILLARS 必须包含年、月、日、时四柱")
        elif self.availability == NatalPillarAvailability.THREE_PILLARS:
            if any(pillar is None for pillar in required) or self.hour is not None:
                raise ValueError("THREE_PILLARS 必须有年、月、日柱且时柱为空")
        elif any(pillar is not None for pillar in (*required, self.hour)):
            raise ValueError("UNAVAILABLE 不得包含伪造的原局柱位")
        return self


class TemporalFortuneContext(SMBaseModel):
    """同一时点只持有一个 CalendarSnapshot，所有流年/月/日/时复用它。"""

    target_at: datetime
    timezone: str = "Asia/Shanghai"
    calendar_snapshot: CalendarSnapshot
    contract_version: Literal["stock-fortune-contract-v1"] = FORTUNE_CONTRACT_VERSION

    @model_validator(mode="after")
    def require_offset_aware_target(self) -> TemporalFortuneContext:
        if self.target_at.tzinfo is None or self.target_at.utcoffset() is None:
            raise ValueError("target_at 必须是带时区的时间戳")
        return self

    @property
    def flow_year(self) -> GanZhi:
        return self.calendar_snapshot.year_ganzhi

    @property
    def flow_month(self) -> GanZhi:
        return self.calendar_snapshot.month_ganzhi

    @property
    def flow_day(self) -> GanZhi:
        return self.calendar_snapshot.day_ganzhi

    @property
    def flow_hour(self) -> GanZhi:
        return self.calendar_snapshot.hour_ganzhi


class DaYunPeriod(SMBaseModel):
    """单步大运结果，避免现有 BaziChart 中无类型的 dict 被复制为新契约。"""

    start_year: int
    end_year: int
    start_age: int | None = None
    end_age: int | None = None
    ganzhi: str | None = None
    direction: LuckCycleDirection | None = None
    compatibility_gender: CompatibilityGender | None = None
    is_current: bool | None = None
    rule_version: str = "fortune-dayun-v1"

    @model_validator(mode="after")
    def validate_period(self) -> DaYunPeriod:
        if self.end_year < self.start_year:
            raise ValueError("end_year 不得早于 start_year")
        if self.start_age is not None and self.end_age is not None and self.end_age < self.start_age:
            raise ValueError("end_age 不得早于 start_age")
        return self


class MarketSessionInterval(SMBaseModel):
    """一个左闭右开的可交易时段。"""

    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_interval(self) -> MarketSessionInterval:
        if self.end_time <= self.start_time:
            raise ValueError("交易时段必须在同一自然日内且 end_time > start_time")
        return self


class MarketSessionAssessment(SMBaseModel):
    """市场时段判断；不覆盖 TemporalFortuneContext 中的传统时辰。"""

    exchange: Exchange
    target_at: datetime
    status: MarketSessionStatus
    tradable: bool | None
    source: str
    source_version: str
    reason: str = ""

    @model_validator(mode="after")
    def validate_status_value(self) -> MarketSessionAssessment:
        if self.target_at.tzinfo is None or self.target_at.utcoffset() is None:
            raise ValueError("target_at 必须带时区")
        if self.status == MarketSessionStatus.UNKNOWN and self.tradable is True:
            raise ValueError("UNKNOWN 的市场状态不得声称 tradable=true")
        if self.status in {
            MarketSessionStatus.BREAK,
            MarketSessionStatus.CLOSED,
        } and self.tradable is not False:
            raise ValueError("休市或闭市必须标记 tradable=false")
        if self.status == MarketSessionStatus.CONTINUOUS_TRADING and self.tradable is not True:
            raise ValueError("连续交易必须标记 tradable=true")
        return self


class FortuneRelationEvent(SMBaseModel):
    """Fortune 对既有刑冲合害破事件的统一、可追溯外壳。"""

    category: FortuneRelationCategory
    relation_type: str = Field(min_length=1, description="保留底层关系引擎原始类型")
    participants: list[str] = Field(min_length=2)
    scope: FortuneRelationScope
    direction: FortuneRuleValence = FortuneRuleValence.UNKNOWN
    severity: FiniteFloat | None = Field(default=None, ge=0.0)
    weight: FiniteFloat | None = Field(default=None, ge=0.0)
    rule_version: str
    evidence: list[str] = Field(default_factory=list)
    explanation: str = ""


class FortuneTenGodObservation(SMBaseModel):
    """复用现有十神结果，不在 Fortune 层复制映射表。"""

    layer: Literal["natal", "dayun", "year", "month", "day", "hour"]
    pillar: GanZhi
    stem: TenGodRef | None = None
    hidden_stems: list[TenGodHiddenStem] = Field(default_factory=list)
    availability: FortuneAvailability
    rule_version: str


class FortuneConfidenceComponent(SMBaseModel):
    """数据/规则完整度分量；score=None 表示没有量化方法或证据。"""

    availability: FortuneAvailability
    score: FiniteFloat | None = Field(default=None, ge=0.0, le=1.0)
    grade: str | None = None
    evidence: list[str] = Field(default_factory=list)
    rule_version: str = "fortune-confidence-v1"


class FortuneDataConfidence(SMBaseModel):
    """置信度只描述数据与规则完整度，不是市场预测概率。"""

    birth_data_confidence: FortuneConfidenceComponent
    calendar_confidence: FortuneConfidenceComponent
    rule_confidence: FortuneConfidenceComponent
    calculation_confidence: FortuneConfidenceComponent | None = Field(
        default=None,
        description="F1 不定义聚合公式；未登记规则时保持 None",
    )
    semantics: Literal["data_and_rule_completeness"] = "data_and_rule_completeness"
    rule_version: str = "fortune-confidence-v1"


class FortuneRuleFactor(SMBaseModel):
    """可解释的术数规则事实；数值与方向不代表金融结果。"""

    factor_id: str
    value: str | int | float | bool | None = None
    direction: FortuneRuleValence = FortuneRuleValence.UNKNOWN
    availability: FortuneAvailability = FortuneAvailability.AVAILABLE
    rule_score: FiniteFloat | None = None
    rule_version: str
    evidence: list[str] = Field(default_factory=list)
    explanation: str = ""

    @model_validator(mode="after")
    def unavailable_has_no_value(self) -> FortuneRuleFactor:
        if self.availability == FortuneAvailability.UNAVAILABLE:
            if self.value is not None or self.rule_score is not None:
                raise ValueError("UNAVAILABLE 的规则因子不得伪造 value 或 rule_score")
        return self


class FortuneRuleFactorGroup(SMBaseModel):
    availability: FortuneAvailability
    items: list[FortuneRuleFactor] = Field(default_factory=list)

    @model_validator(mode="after")
    def unavailable_group_is_empty(self) -> FortuneRuleFactorGroup:
        if self.availability == FortuneAvailability.UNAVAILABLE and self.items:
            raise ValueError("UNAVAILABLE 的规则因子组必须为空")
        return self


class WealthFortuneFactors(SMBaseModel):
    """财富相关的规则事实分组；不规定权重，也不合成金融概率。"""

    wealth_star_presence: FortuneRuleFactorGroup
    wealth_star_strength: FortuneRuleFactorGroup
    favorable_support: FortuneRuleFactorGroup
    unfavorable_pressure: FortuneRuleFactorGroup
    relations_positive: FortuneRuleFactorGroup
    relations_negative: FortuneRuleFactorGroup
    day_master_capacity: FortuneRuleFactorGroup
    resonance_depth: FortuneRuleFactorGroup
    rule_version: str


class FortuneResonanceLayer(SMBaseModel):
    layer: FortuneTemporalLayer
    availability: FortuneAvailability
    signal: str | None = Field(default=None, description="规则层标签，不是市场方向")
    factor_ids: list[str] = Field(default_factory=list)
    rule_version: str


class FortuneResonance(SMBaseModel):
    """共振覆盖层数。4/5 表示规则层数量，不是 80% 上涨概率。"""

    layers: list[FortuneResonanceLayer] = Field(default_factory=list)
    matching_layer_count: int | None = Field(default=None, ge=0, le=5)
    assessed_layer_count: int | None = Field(default=None, ge=0, le=5)
    rule_version: str

    @model_validator(mode="after")
    def validate_counts(self) -> FortuneResonance:
        if (self.matching_layer_count is None) != (self.assessed_layer_count is None):
            raise ValueError("共振计数必须同时提供或同时为空")
        if (
            self.matching_layer_count is not None
            and self.assessed_layer_count is not None
            and self.matching_layer_count > self.assessed_layer_count
        ):
            raise ValueError("matching_layer_count 不得超过 assessed_layer_count")
        return self

    @property
    def resonance_depth(self) -> str | None:
        if self.matching_layer_count is None or self.assessed_layer_count is None:
            return None
        return f"{self.matching_layer_count}/{self.assessed_layer_count}"


class FortuneScore(SMBaseModel):
    """Fortune 内部规则分；不是收益率、上涨概率、买入信号或预测准确率。"""

    kind: FortuneScoreKind
    value: FiniteFloat | None = None
    availability: FortuneAvailability
    rule_version: str
    explanation: str = ""
    semantics: Literal["traditional_rule_strength_or_resonance"] = (
        "traditional_rule_strength_or_resonance"
    )

    @model_validator(mode="after")
    def validate_score_availability(self) -> FortuneScore:
        if self.availability == FortuneAvailability.UNAVAILABLE and self.value is not None:
            raise ValueError("UNAVAILABLE 的 FortuneScore 必须为 None，不能用 0 代替")
        if self.availability == FortuneAvailability.AVAILABLE and self.value is None:
            raise ValueError("AVAILABLE 的 FortuneScore 必须带 value")
        return self


class FortuneResultV1(SMBaseModel):
    """未来结果的解释性外壳；F1 只定义结构，不计算财富评分。"""

    contract_version: Literal["stock-fortune-contract-v1"] = FORTUNE_CONTRACT_VERSION
    symbol: str
    birth_profile: StockFortuneBirthProfile
    natal_pillars: NatalPillarSet
    luck_cycle: FortuneLuckCycleContext
    dayun_periods: list[DaYunPeriod] = Field(default_factory=list)
    temporal_context: TemporalFortuneContext
    raw_chart: dict[str, object] = Field(min_length=1)
    chart_artifact_ids: list[str] = Field(min_length=1)
    score: FortuneScore | None = None
    wealth_factors: WealthFortuneFactors
    resonance: FortuneResonance
    confidence: FortuneDataConfidence
    positive_factors: list[FortuneRuleFactor] = Field(default_factory=list)
    negative_factors: list[FortuneRuleFactor] = Field(default_factory=list)
    neutral_factors: list[FortuneRuleFactor] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    data_quality: list[DataQuality] = Field(default_factory=list)
    engine_version: str
    rule_version: str
    birth_profile_version: str
    config_version: str
