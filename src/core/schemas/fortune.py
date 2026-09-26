"""Stock Fortune Engine V1 的内部领域契约。

这些模型不由现有 /api/v1 路由直接暴露。它们与 legacy StockBirthProfile
并存，供 Fortune Engine 后续阶段逐步接入；本模块不包含排盘或评分算法。
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import FiniteFloat, Field, computed_field, model_validator

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
STOCK_FORTUNE_SNAPSHOT_VERSION = "stock-fortune-snapshot-v1"
STOCK_FORTUNE_ENGINE_VERSION = "stock-fortune-engine-v1"
FORTUNE_BIRTH_PROFILE_VERSION = "stock-fortune-birth-v2"
FORTUNE_BIRTH_RESOLUTION_RULE_VERSION = "fortune-first-trade-resolution-v1"
FORTUNE_LUCK_CYCLE_RULE_VERSION = "stock-luck-cycle-first-day-yinyang-v1"
FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION = "fortune-dayun-period-lunar-python-1.4.8-v1"
FORTUNE_TEMPORAL_RESOLUTION_RULE_VERSION = "fortune-temporal-resolution-v1"
FORTUNE_MARKET_SESSION_POLICY_VERSION = "fortune-market-session-anchor-v1"
FORTUNE_SNAPSHOT_RULE_VERSION = "stock-fortune-snapshot-v1"


class FortuneBirthBasis(str, Enum):
    """Fortune V1 采用的股票出生基准。"""

    MARKET_FIRST_TRADE = "MARKET_FIRST_TRADE"
    COMPANY_FOUNDING = "COMPANY_FOUNDING"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


class BirthTimePrecision(str, Enum):
    EXACT = "EXACT"
    MINUTE = "MINUTE"
    INFERRED = "INFERRED"
    DATE_ONLY = "DATE_ONLY"
    UNKNOWN = "UNKNOWN"


class FirstTradeObservationStatus(str, Enum):
    VERIFIED_DATETIME = "VERIFIED_DATETIME"
    OBSERVED_TRADING_DATE = "OBSERVED_TRADING_DATE"
    UNAVAILABLE = "UNAVAILABLE"


class FirstTradeObservationResolution(str, Enum):
    TICK = "TICK"
    TRADE = "TRADE"
    MINUTE_BAR = "MINUTE_BAR"
    DAILY_BAR = "DAILY_BAR"
    UNKNOWN = "UNKNOWN"


class FortuneTemporalInputKind(str, Enum):
    EXACT_DATETIME = "EXACT_DATETIME"
    MARKET_SESSION_DATE = "MARKET_SESSION_DATE"
    CIVIL_DATE_ONLY = "CIVIL_DATE_ONLY"


class FortuneTemporalResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    TIME_REQUIRED = "TIME_REQUIRED"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    UNAVAILABLE = "UNAVAILABLE"


class FortuneTemporalResolutionMethod(str, Enum):
    EXACT_DATETIME = "exact_datetime"
    MARKET_SESSION_INFERRED = "market_session_inferred"


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


class FortuneRelationComponent(str, Enum):
    STEM = "stem"
    BRANCH = "branch"
    PILLAR = "pillar"


class FortuneContextKind(str, Enum):
    NATAL = "natal"
    DAYUN = "dayun"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"


class FortuneTenGodLayer(str, Enum):
    NATAL = "natal"
    DAYUN = "dayun"
    ANNUAL = "year"
    MONTHLY = "month"
    DAILY = "day"
    HIDDEN_STEM = "hidden_stem"


class FortuneProvenanceComponent(str, Enum):
    STOCK_IDENTITY = "stock_identity"
    BIRTH_PROFILE = "birth_profile"
    EVALUATION_TIME = "evaluation_time"
    CALENDAR = "calendar"
    BAZI = "bazi"
    LUCK_CYCLE = "luck_cycle"
    TEN_GOD = "ten_god"
    RELATION = "relation"


class StockFortuneIdentity(SMBaseModel):
    """本次快照使用的证券身份，不承载行情或预测字段。"""

    symbol: str = Field(min_length=1, max_length=16)
    exchange: Exchange = Exchange.UNKNOWN
    name: str = ""
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="caller_input"))
    source_version: str = Field(default="caller-input-v1", min_length=1)


class FortuneLuckCycleEvidence(SMBaseModel):
    """ADR-0017 所需的首日阴阳证据；缺失时大运方向保持 unavailable。"""

    first_day_yinyang: Literal["阳", "阴"] | None = None
    observation_date: date | None = None
    is_trading_day: bool | None = None
    source: SourceRef | None = None
    source_version: str = Field(default="unknown", min_length=1)
    market_session_version: str = ""


class StockFortuneBirthProfile(SMBaseModel):
    """Fortune V1 出生档案；分离观察日期、推定时刻与实际成交观测。"""

    contract_version: Literal["stock-fortune-contract-v1"] = FORTUNE_CONTRACT_VERSION
    symbol: str = Field(min_length=1, max_length=16, description="标准证券代码")
    exchange: Exchange = Exchange.UNKNOWN
    listing_date: date | None = None
    first_trade_datetime: datetime | None = Field(
        default=None,
        description="来源观测到的首次成交时间；分钟 bar 必须同时标明 MINUTE 精度",
    )
    first_trade_date: date | None = Field(
        default=None,
        description="可靠行情源最早观测到的交易日期；日线日期不等于实际成交时刻",
    )
    first_trade_resolution: FirstTradeObservationResolution = (
        FirstTradeObservationResolution.UNKNOWN
    )
    birth_basis: FortuneBirthBasis = FortuneBirthBasis.MARKET_FIRST_TRADE
    birth_datetime: datetime | None = Field(
        default=None,
        description="按 birth_basis 选定的计算时刻；DATE_ONLY/UNKNOWN 时必须为空",
    )
    timezone: str = "Asia/Shanghai"
    birth_time_precision: BirthTimePrecision = BirthTimePrecision.UNKNOWN
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="unavailable"))
    source_version: str = Field(default="unknown", min_length=1)
    confidence: FiniteFloat | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="来源数据可信度；不表示市场预测概率",
    )
    birth_profile_version: str = Field(default=FORTUNE_BIRTH_PROFILE_VERSION, min_length=1)
    rule_version: str = Field(default="stock-fortune-birth-rule-v1", min_length=1)
    config_version: str = ""
    market_session_version: str = ""
    assumptions: list[Assumption] = Field(default_factory=list)
    data_quality: DataQuality | None = None

    @computed_field
    @property
    def birth_datetime_status(self) -> BirthTimePrecision:
        """明确输出 exact/inferred/date-only/unavailable 的时间状态。"""

        return self.birth_time_precision

    @model_validator(mode="after")
    def validate_precision_and_source_time(self) -> StockFortuneBirthProfile:
        if not self.timezone.strip():
            raise ValueError("birth profile 必须记录 timezone")
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("birth profile 必须使用有效 timezone") from exc
        requires_time = self.birth_time_precision in {
            BirthTimePrecision.EXACT,
            BirthTimePrecision.MINUTE,
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
        if self.birth_time_precision == BirthTimePrecision.DATE_ONLY:
            if self.first_trade_date is None:
                raise ValueError("DATE_ONLY 必须保留 first_trade_date")
            if self.first_trade_resolution != FirstTradeObservationResolution.DAILY_BAR:
                raise ValueError("DATE_ONLY 必须标记 DAILY_BAR 来源精度")
        if self.birth_time_precision == BirthTimePrecision.UNKNOWN:
            if self.first_trade_date is not None:
                raise ValueError("UNKNOWN 不得携带未确认的 first_trade_date")
            if self.first_trade_resolution != FirstTradeObservationResolution.UNKNOWN:
                raise ValueError("UNKNOWN 必须使用 UNKNOWN observation resolution")
        if self.birth_time_precision == BirthTimePrecision.INFERRED and not self.assumptions:
            raise ValueError("INFERRED 必须公开记录 assumptions")
        if self.birth_time_precision == BirthTimePrecision.INFERRED:
            if self.first_trade_date is None:
                raise ValueError("INFERRED 必须基于 first_trade_date")
            if not self.market_session_version.strip():
                raise ValueError("INFERRED 必须记录 market_session_version")
            if self.source_version.strip().lower() in {"", "unknown"}:
                raise ValueError("INFERRED 必须记录 source_version")
            if self.first_trade_resolution != FirstTradeObservationResolution.DAILY_BAR:
                raise ValueError("INFERRED 的首日证据必须是 DAILY_BAR")
            if not self.config_version.strip():
                raise ValueError("INFERRED 必须记录 config_version")
        if (
            self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE
            and self.birth_time_precision == BirthTimePrecision.EXACT
            and self.first_trade_datetime is None
        ):
            raise ValueError("EXACT 的 MARKET_FIRST_TRADE 必须保留 first_trade_datetime")
        if (
            self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE
            and self.birth_time_precision == BirthTimePrecision.MINUTE
            and self.first_trade_datetime is None
        ):
            raise ValueError("MINUTE 的 MARKET_FIRST_TRADE 必须保留分钟观测时刻")
        if (
            self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE
            and self.birth_time_precision == BirthTimePrecision.INFERRED
            and self.first_trade_datetime is not None
        ):
            raise ValueError("INFERRED 不得把推定时刻伪装成 first_trade_datetime")
        if self.first_trade_datetime is not None:
            if self.first_trade_datetime.tzinfo is None or self.first_trade_datetime.utcoffset() is None:
                raise ValueError("first_trade_datetime 必须包含时区")
            if self.birth_basis != FortuneBirthBasis.MARKET_FIRST_TRADE:
                raise ValueError("非 MARKET_FIRST_TRADE 档案不得携带 first_trade_datetime")
            if self.source_version.strip().lower() in {"", "unknown"}:
                raise ValueError("真实成交观测必须记录 source_version")
            source_name = self.source.source.strip().lower()
            if (
                not source_name
                or source_name == "unavailable"
                or source_name.startswith("synthetic")
            ):
                raise ValueError("真实成交观测必须记录真实来源")
            if self.first_trade_resolution == FirstTradeObservationResolution.MINUTE_BAR:
                expected_precision = BirthTimePrecision.MINUTE
            elif self.first_trade_resolution in {
                FirstTradeObservationResolution.TICK,
                FirstTradeObservationResolution.TRADE,
            }:
                expected_precision = BirthTimePrecision.EXACT
            else:
                raise ValueError("first_trade_datetime 必须来自 tick/trade/minute bar")
            if self.birth_basis == FortuneBirthBasis.MARKET_FIRST_TRADE:
                if self.birth_time_precision != expected_precision:
                    raise ValueError("first_trade_datetime 的 precision 必须与来源 resolution 一致")
                if self.birth_datetime != self.first_trade_datetime:
                    raise ValueError("MARKET_FIRST_TRADE 的 birth_datetime 必须等于实际 first_trade_datetime")
                if self.first_trade_date != self.first_trade_datetime.astimezone(ZoneInfo(self.timezone)).date():
                    raise ValueError("first_trade_date 必须与 first_trade_datetime 的本地日期一致")
        return self


class FirstTradeObservation(SMBaseModel):
    """行情观察结果；日线只证明日期，分钟 bar 不冒充 tick 精度。"""

    status: FirstTradeObservationStatus
    first_trade_datetime: datetime | None = None
    first_trade_date: date | None = None
    resolution: FirstTradeObservationResolution = FirstTradeObservationResolution.UNKNOWN
    source: SourceRef
    source_version: str
    timezone: str = "Asia/Shanghai"
    reason: str = ""

    @model_validator(mode="after")
    def validate_observation(self) -> FirstTradeObservation:
        if self.source_version.strip().lower() in {"", "unknown"}:
            raise ValueError("FirstTradeObservation 必须记录 source_version")
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("FirstTradeObservation 必须使用有效 timezone") from exc
        if not self.reason.strip():
            raise ValueError("FirstTradeObservation 必须说明 observation reason")
        if self.status == FirstTradeObservationStatus.VERIFIED_DATETIME:
            if self.resolution not in {
                FirstTradeObservationResolution.TICK,
                FirstTradeObservationResolution.TRADE,
                FirstTradeObservationResolution.MINUTE_BAR,
            }:
                raise ValueError("VERIFIED_DATETIME 必须来自 tick/trade/minute bar")
            if self.first_trade_datetime is None or self.first_trade_date is None:
                raise ValueError("VERIFIED_DATETIME 必须同时提供观测时刻和交易日期")
            if self.first_trade_datetime.tzinfo is None or self.first_trade_datetime.utcoffset() is None:
                raise ValueError("VERIFIED_DATETIME 必须带时区")
            source_name = self.source.source.strip().lower()
            if (
                not source_name
                or source_name == "unavailable"
                or source_name.startswith("synthetic")
            ):
                raise ValueError("VERIFIED_DATETIME 必须来自可追溯的真实来源")
            if self.first_trade_datetime.astimezone(ZoneInfo(self.timezone)).date() != self.first_trade_date:
                raise ValueError("first_trade_date 必须与观测时刻的本地日期一致")
        elif self.status == FirstTradeObservationStatus.OBSERVED_TRADING_DATE:
            if self.resolution != FirstTradeObservationResolution.DAILY_BAR:
                raise ValueError("OBSERVED_TRADING_DATE 必须来自 DAILY_BAR")
            if self.first_trade_date is None or self.first_trade_datetime is not None:
                raise ValueError("日线观察必须只有 first_trade_date，不得伪造时刻")
            source_name = self.source.source.strip().lower()
            if (
                not source_name
                or source_name == "unavailable"
                or source_name.startswith("synthetic")
            ):
                raise ValueError("OBSERVED_TRADING_DATE 必须来自可追溯的真实来源")
        else:
            if self.first_trade_datetime is not None or self.first_trade_date is not None:
                raise ValueError("UNAVAILABLE 不得携带交易日期或时间")
            if self.resolution != FirstTradeObservationResolution.UNKNOWN:
                raise ValueError("UNAVAILABLE 必须使用 UNKNOWN observation resolution")
        return self


class FortuneDayunPeriod(SMBaseModel):
    """由固定 lunar-python 版本产生的大运周期；区间使用左闭右开。"""

    cycle_index: int = Field(ge=1)
    start_at: datetime
    end_at: datetime
    start_year: int
    end_year: int
    start_age: int
    end_age: int
    ganzhi: GanZhi
    rule_version: str = FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION

    @model_validator(mode="after")
    def validate_cycle_period(self) -> FortuneDayunPeriod:
        if self.start_at.tzinfo is None or self.start_at.utcoffset() is None:
            raise ValueError("大运周期 start_at 必须带时区")
        if self.end_at.tzinfo is None or self.end_at.utcoffset() is None:
            raise ValueError("大运周期 end_at 必须带时区")
        if self.end_at <= self.start_at:
            raise ValueError("大运周期必须满足 start_at < end_at")
        if self.end_year < self.start_year or self.end_age < self.start_age:
            raise ValueError("大运周期结束年/年龄不得早于开始年/年龄")
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
    polarity_source: SourceRef = Field(default_factory=lambda: SourceRef(source="unavailable"))
    polarity_source_version: str = "unknown"
    market_session_version: str = ""
    polarity_observation_date: date | None = None
    polarity_observed_at: datetime | None = None
    assumptions: list[Assumption] = Field(default_factory=list)
    unavailability_reason: str = ""
    rule_version: str = FORTUNE_LUCK_CYCLE_RULE_VERSION
    period_rule_version: str = FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION
    start_basis: str = ""
    cycle_availability: FortuneAvailability = FortuneAvailability.UNAVAILABLE
    cycle_periods: list[FortuneDayunPeriod] = Field(default_factory=list)
    current_cycle: FortuneDayunPeriod | None = None
    cycle_index: int | None = Field(default=None, ge=1)
    cycle_start: datetime | None = None
    cycle_end: datetime | None = None
    stem: str | None = None
    branch: str | None = None

    @model_validator(mode="after")
    def validate_direction_state(self) -> FortuneLuckCycleContext:
        if self.availability == FortuneAvailability.AVAILABLE and self.direction is None:
            raise ValueError("AVAILABLE 的排运上下文必须有实际 direction")
        if self.availability == FortuneAvailability.UNAVAILABLE and self.direction is not None:
            raise ValueError("UNAVAILABLE 不得携带看似有效的 direction")
        if self.availability == FortuneAvailability.UNAVAILABLE and (
            self.polarity is not None or self.compatibility_gender is not None
        ):
            raise ValueError("UNAVAILABLE 不得携带 polarity 或 compatibility_gender")
        if self.availability == FortuneAvailability.AVAILABLE:
            if self.polarity is None or self.compatibility_gender is None or not self.direction_basis:
                raise ValueError("AVAILABLE 必须记录 polarity、compatibility_gender 与 direction_basis")
            if self.polarity_source_version.strip().lower() in {"", "unknown"}:
                raise ValueError("AVAILABLE 必须记录 polarity_source_version")
            if not self.market_session_version.strip():
                raise ValueError("AVAILABLE 必须记录 market_session_version")
            if (
                self.polarity_observation_date is None
                or self.polarity_observed_at is None
                or not self.assumptions
            ):
                raise ValueError("AVAILABLE 必须记录 polarity 观测日期、时间与 assumptions")
            if not self.rule_version:
                raise ValueError("AVAILABLE 必须记录 luck-cycle rule_version")
        if self.polarity_observed_at is not None and (
            self.polarity_observed_at.tzinfo is None
            or self.polarity_observed_at.utcoffset() is None
        ):
            raise ValueError("polarity_observed_at 必须带时区")
        if self.current_cycle is None:
            if any(value is not None for value in (
                self.cycle_index, self.cycle_start, self.cycle_end, self.stem, self.branch
            )):
                raise ValueError("没有 current_cycle 时不得填写其索引、边界、天干或地支")
        else:
            if self.cycle_availability != FortuneAvailability.AVAILABLE:
                raise ValueError("存在 current_cycle 时 cycle_availability 必须为 available")
            expected = {
                "cycle_index": self.current_cycle.cycle_index,
                "cycle_start": self.current_cycle.start_at,
                "cycle_end": self.current_cycle.end_at,
                "stem": self.current_cycle.ganzhi.stem,
                "branch": self.current_cycle.ganzhi.branch,
            }
            if any(getattr(self, key) != value for key, value in expected.items()):
                raise ValueError("current_cycle 的摘要字段必须与周期对象一致")
        if self.cycle_availability == FortuneAvailability.AVAILABLE and self.current_cycle is None:
            raise ValueError("cycle_availability=available 必须包含 current_cycle")
        if self.current_cycle is not None and self.current_cycle not in self.cycle_periods:
            raise ValueError("current_cycle 必须来自 cycle_periods")
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


class FortuneNatalHiddenStem(SMBaseModel):
    """原局某一柱地支藏干的完整既有结构化结果。"""

    position: Literal["year", "month", "day", "hour"]
    branch: str = Field(min_length=1)
    stem: TenGodHiddenStem


class FortuneNatalContext(SMBaseModel):
    """原局信息由 BaziEngine 产生；缺少安全时间时明确不可用。"""

    availability: FortuneAvailability
    pillars: NatalPillarSet
    day_master: str | None = None
    day_master_yang: bool | None = None
    day_master_wuxing: str | None = None
    hidden_stems: list[FortuneNatalHiddenStem] = Field(default_factory=list)
    bazi_engine: str = "bazi"
    bazi_engine_version: str = ""
    rule_version: str = ""

    @model_validator(mode="after")
    def validate_natal_availability(self) -> FortuneNatalContext:
        if self.availability == FortuneAvailability.AVAILABLE:
            if self.pillars.availability != NatalPillarAvailability.FOUR_PILLARS:
                raise ValueError("AVAILABLE 的原局必须有完整四柱")
            if not self.day_master or self.day_master_yang is None or not self.day_master_wuxing:
                raise ValueError("AVAILABLE 的原局必须说明日主、阴阳与五行")
            if not self.hidden_stems:
                raise ValueError("AVAILABLE 的原局必须保留藏干")
        elif self.availability == FortuneAvailability.UNAVAILABLE:
            if self.pillars.availability != NatalPillarAvailability.UNAVAILABLE:
                raise ValueError("UNAVAILABLE 的原局不能带有部分盘柱")
            if any(value is not None for value in (
                self.day_master, self.day_master_yang, self.day_master_wuxing
            )):
                raise ValueError("UNAVAILABLE 的原局不得伪造日主信息")
            if self.hidden_stems:
                raise ValueError("UNAVAILABLE 的原局不得包含藏干")
        return self


class TemporalFortuneContext(SMBaseModel):
    """同一时点只持有一个 CalendarSnapshot，所有流年/月/日/时复用它。"""

    target_at: datetime
    timezone: str = "Asia/Shanghai"
    calendar_snapshot: CalendarSnapshot
    temporal_resolution: FortuneTemporalResolutionMethod = (
        FortuneTemporalResolutionMethod.EXACT_DATETIME
    )
    market_session_version: str = ""
    assumptions: list[Assumption] = Field(default_factory=list)
    rule_version: str = FORTUNE_TEMPORAL_RESOLUTION_RULE_VERSION
    contract_version: Literal["stock-fortune-contract-v1"] = FORTUNE_CONTRACT_VERSION

    @model_validator(mode="after")
    def require_offset_aware_target(self) -> TemporalFortuneContext:
        if self.target_at.tzinfo is None or self.target_at.utcoffset() is None:
            raise ValueError("target_at 必须是带时区的时间戳")
        if self.temporal_resolution == FortuneTemporalResolutionMethod.MARKET_SESSION_INFERRED:
            if not self.market_session_version or not self.assumptions:
                raise ValueError("MARKET_SESSION_INFERRED 必须记录 session version 与 assumptions")
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


class FortuneTemporalInput(SMBaseModel):
    """强制调用方标明 exact、市场时段日期或纯自然日期语义。"""

    kind: FortuneTemporalInputKind
    target_datetime: datetime | None = None
    target_date: date | None = None
    exchange: Exchange | None = None
    is_trading_day: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_date_cast_to_datetime(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        raw_datetime = value.get("target_datetime")
        if isinstance(raw_datetime, date) and not isinstance(raw_datetime, datetime):
            raise ValueError("date-only 不得传入 target_datetime")
        if isinstance(raw_datetime, str) and len(raw_datetime.strip()) == 10:
            raise ValueError("date-only 不得传入 target_datetime")
        return value

    @model_validator(mode="after")
    def validate_temporal_input(self) -> FortuneTemporalInput:
        if self.kind == FortuneTemporalInputKind.EXACT_DATETIME:
            if self.target_datetime is None or self.target_date is not None:
                raise ValueError("EXACT_DATETIME 必须只提供 target_datetime")
            if self.target_datetime.tzinfo is None or self.target_datetime.utcoffset() is None:
                raise ValueError("EXACT_DATETIME 必须带时区")
        elif self.kind == FortuneTemporalInputKind.MARKET_SESSION_DATE:
            if self.target_date is None or self.target_datetime is not None:
                raise ValueError("MARKET_SESSION_DATE 必须只提供 target_date")
            if self.exchange in {None, Exchange.UNKNOWN}:
                raise ValueError("MARKET_SESSION_DATE 必须明确 exchange")
        else:
            if self.target_date is None or self.target_datetime is not None:
                raise ValueError("CIVIL_DATE_ONLY 必须只提供 target_date")
            if self.exchange is not None or self.is_trading_day is not None:
                raise ValueError("CIVIL_DATE_ONLY 不得隐含市场交易场景")
        return self


class FortuneTemporalResolution(SMBaseModel):
    """时间解析结果；未解析时不制造 CalendarSnapshot。"""

    input_kind: FortuneTemporalInputKind
    status: FortuneTemporalResolutionStatus
    context: TemporalFortuneContext | None = None
    requested_date: date | None = None
    reason: str = ""

    @model_validator(mode="after")
    def validate_resolution(self) -> FortuneTemporalResolution:
        if self.status == FortuneTemporalResolutionStatus.RESOLVED and self.context is None:
            raise ValueError("RESOLVED 必须包含 temporal context")
        if self.status != FortuneTemporalResolutionStatus.RESOLVED and self.context is not None:
            raise ValueError("未解析的时间输入不得包含 calendar snapshot")
        if (
            self.input_kind == FortuneTemporalInputKind.CIVIL_DATE_ONLY
            and self.status != FortuneTemporalResolutionStatus.TIME_REQUIRED
        ):
            raise ValueError("CIVIL_DATE_ONLY 必须返回 TIME_REQUIRED")
        if self.status == FortuneTemporalResolutionStatus.RESOLVED and self.context is not None:
            expected = (
                FortuneTemporalResolutionMethod.MARKET_SESSION_INFERRED
                if self.input_kind == FortuneTemporalInputKind.MARKET_SESSION_DATE
                else FortuneTemporalResolutionMethod.EXACT_DATETIME
            )
            if self.context.temporal_resolution != expected:
                raise ValueError("temporal context resolution 必须与 input_kind 一致")
        return self


class FortuneTemporalPillarContext(SMBaseModel):
    """流年/月/日字段只取自同一个 CalendarSnapshot。"""

    layer: Literal["annual", "monthly", "daily"]
    availability: FortuneAvailability
    pillar: GanZhi | None = None
    source_engine: str = "calendar"
    source_engine_version: str = ""
    rule_version: str = FORTUNE_TEMPORAL_RESOLUTION_RULE_VERSION

    @model_validator(mode="after")
    def validate_pillar_availability(self) -> FortuneTemporalPillarContext:
        if self.availability == FortuneAvailability.UNAVAILABLE and self.pillar is not None:
            raise ValueError("UNAVAILABLE 的时间柱不得携带干支值")
        if self.availability == FortuneAvailability.AVAILABLE and self.pillar is None:
            raise ValueError("AVAILABLE 的时间柱必须携带干支值")
        return self


class StockFortuneEvaluationRequest(SMBaseModel):
    """统一快照入口的 typed 输入。"""

    stock_identity: StockFortuneIdentity
    birth_profile: StockFortuneBirthProfile
    evaluation_context: FortuneTemporalInput
    evaluation_source: SourceRef = Field(
        default_factory=lambda: SourceRef(source="caller_input")
    )
    evaluation_source_version: str = "caller-input-v1"
    luck_cycle_evidence: FortuneLuckCycleEvidence | None = None
    market_session_version: str = ""
    config_version: str = ""

    @model_validator(mode="after")
    def validate_identity_matches_birth_profile(self) -> StockFortuneEvaluationRequest:
        if self.stock_identity.symbol != self.birth_profile.symbol:
            raise ValueError("stock_identity.symbol 必须与 birth_profile.symbol 一致")
        if (
            self.stock_identity.exchange != Exchange.UNKNOWN
            and self.birth_profile.exchange != Exchange.UNKNOWN
            and self.stock_identity.exchange != self.birth_profile.exchange
        ):
            raise ValueError("stock_identity.exchange 与 birth_profile.exchange 不得冲突")
        if self.evaluation_context.kind == FortuneTemporalInputKind.MARKET_SESSION_DATE:
            expected_exchange = (
                self.stock_identity.exchange
                if self.stock_identity.exchange != Exchange.UNKNOWN
                else self.birth_profile.exchange
            )
            if (
                expected_exchange != Exchange.UNKNOWN
                and self.evaluation_context.exchange != expected_exchange
            ):
                raise ValueError("MARKET_SESSION_DATE.exchange 必须与证券档案交易所一致")
        if not self.evaluation_source_version.strip():
            raise ValueError("evaluation_source_version 必须非空")
        return self

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


class FortuneRelationParticipant(SMBaseModel):
    """关系一端的精确归属；context 与 pillar 共同定位对象。"""

    context: FortuneContextKind
    pillar: str
    component: FortuneRelationComponent
    value: str = Field(min_length=1)


class FortuneRelationEvent(SMBaseModel):
    """Fortune 对既有关系命中的结构化包装，不赋予吉凶或金融方向。"""

    category: FortuneRelationCategory
    relation_type: str = Field(min_length=1, description="保留底层关系引擎原始类型")
    source: FortuneRelationParticipant
    target: FortuneRelationParticipant
    participants: list[str] = Field(min_length=2)
    scope: FortuneRelationScope
    direction: FortuneRuleValence = FortuneRuleValence.UNKNOWN
    severity: FiniteFloat | None = Field(default=None, ge=0.0)
    weight: FiniteFloat | None = Field(default=None, ge=0.0)
    rule_version: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    explanation: str = ""

    @model_validator(mode="after")
    def validate_participant_attribution(self) -> FortuneRelationEvent:
        source_id = (
            f"{getattr(self.source.context, 'value', self.source.context)}:{self.source.pillar}:"
            f"{getattr(self.source.component, 'value', self.source.component)}:{self.source.value}"
        )
        target_id = (
            f"{getattr(self.target.context, 'value', self.target.context)}:{self.target.pillar}:"
            f"{getattr(self.target.component, 'value', self.target.component)}:{self.target.value}"
        )
        if source_id not in self.participants or target_id not in self.participants:
            raise ValueError("participants 必须包含结构化 source 与 target")
        if self.scope == FortuneRelationScope.NATAL_NATAL and (
            self.source.context != FortuneContextKind.NATAL
            or self.target.context != FortuneContextKind.NATAL
        ):
            raise ValueError("NATAL_NATAL 关系两端必须都是原局对象")
        if self.scope == FortuneRelationScope.TEMPORAL_TO_NATAL and (
            self.source.context == FortuneContextKind.NATAL
            or self.target.context != FortuneContextKind.NATAL
        ):
            raise ValueError("TEMPORAL_TO_NATAL 必须由时间对象指向原局对象")
        if self.scope == FortuneRelationScope.TEMPORAL_TO_TEMPORAL and (
            self.source.context == FortuneContextKind.NATAL
            or self.target.context == FortuneContextKind.NATAL
        ):
            raise ValueError("TEMPORAL_TO_TEMPORAL 两端都必须是时间对象")
        return self


class FortuneRelationContext(SMBaseModel):
    availability: FortuneAvailability
    events: list[FortuneRelationEvent] = Field(default_factory=list)
    relation_count: int = Field(default=0, ge=0)
    relation_type_counts: dict[str, int] = Field(default_factory=dict)
    rule_version: str

    @model_validator(mode="after")
    def validate_relation_counts(self) -> FortuneRelationContext:
        if self.relation_count != len(self.events):
            raise ValueError("relation_count 必须与 events 数量一致")
        if any(count < 0 for count in self.relation_type_counts.values()):
            raise ValueError("relation_type_counts 不得包含负数")
        if sum(self.relation_type_counts.values()) != self.relation_count:
            raise ValueError("relation_type_counts 总数必须与 relation_count 一致")
        if self.availability == FortuneAvailability.UNAVAILABLE and self.events:
            raise ValueError("UNAVAILABLE 的 relation context 不得携带事件")
        return self


class FortuneTenGodObservation(SMBaseModel):
    """复用现有十神结果，不在 Fortune 层复制映射表。"""

    layer: FortuneTenGodLayer
    position: Literal["year", "month", "day", "hour"]
    pillar: GanZhi
    stem: TenGodRef | None = None
    display_label: str = Field(min_length=1)
    hidden_stems: list[TenGodHiddenStem] = Field(default_factory=list)
    availability: FortuneAvailability
    rule_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ten_god_observation(self) -> FortuneTenGodObservation:
        if self.availability == FortuneAvailability.AVAILABLE and self.stem is None:
            raise ValueError("AVAILABLE 的十神观察必须包含天干十神")
        if self.availability == FortuneAvailability.UNAVAILABLE and self.stem is not None:
            raise ValueError("UNAVAILABLE 的十神观察不得包含计算结果")
        return self


class FortuneHiddenStemTenGodObservation(SMBaseModel):
    """原局地支藏干十神；值直接来自 Bazi/Ten-God 现有输出。"""

    context: FortuneContextKind = FortuneContextKind.NATAL
    pillar: Literal["year", "month", "day", "hour"]
    branch: str = Field(min_length=1)
    stem: TenGodHiddenStem
    rule_version: str = Field(min_length=1)


class FortuneTenGodContext(SMBaseModel):
    """五类十神的统一容器：原局、流年、流月、流日、藏干。"""

    availability: FortuneAvailability
    day_master: str | None = None
    natal: list[FortuneTenGodObservation] = Field(default_factory=list)
    annual: FortuneTenGodObservation | None = None
    monthly: FortuneTenGodObservation | None = None
    daily: FortuneTenGodObservation | None = None
    hidden_stems: list[FortuneHiddenStemTenGodObservation] = Field(default_factory=list)
    rule_version: str

    @model_validator(mode="after")
    def validate_ten_god_context(self) -> FortuneTenGodContext:
        if self.availability == FortuneAvailability.UNAVAILABLE:
            if any((self.day_master, self.natal, self.annual, self.monthly, self.daily, self.hidden_stems)):
                raise ValueError("UNAVAILABLE 的十神上下文不得携带计算结果")
        if self.availability == FortuneAvailability.AVAILABLE:
            natal_positions = {item.position for item in self.natal}
            if not self.day_master or natal_positions != {"year", "month", "day", "hour"}:
                raise ValueError("AVAILABLE 的十神上下文必须有日主与原局四柱")
            if self.annual is None or self.monthly is None or self.daily is None:
                raise ValueError("AVAILABLE 的十神上下文必须有流年、流月、流日")
            if (
                self.annual.layer != "year"
                or self.monthly.layer != "month"
                or self.daily.layer != "day"
                or self.annual.position != "year"
                or self.monthly.position != "month"
                or self.daily.position != "day"
            ):
                raise ValueError("流年、流月、流日十神层标记不匹配")
            if not self.hidden_stems:
                raise ValueError("AVAILABLE 的十神上下文必须包含原局藏干十神")
        return self


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


class FortuneRuleVersions(SMBaseModel):
    """快照重放所需的算法、数据口径与配置版本。"""

    snapshot_rule_version: str = Field(min_length=1)
    birth_profile_version: str = Field(min_length=1)
    birth_rule_version: str = Field(min_length=1)
    market_session_version: str = Field(min_length=1)
    temporal_resolution_rule_version: str = Field(min_length=1)
    calendar_engine_version: str = Field(min_length=1)
    bazi_engine_version: str = Field(min_length=1)
    luck_cycle_direction_rule_version: str = Field(min_length=1)
    luck_cycle_period_rule_version: str = Field(min_length=1)
    ten_god_rule_version: str = Field(min_length=1)
    relation_rule_version: str = Field(min_length=1)
    relation_matrix_schema_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)


class FortuneProvenanceRecord(SMBaseModel):
    component: FortuneProvenanceComponent
    source: SourceRef
    source_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    assumptions: list[Assumption] = Field(default_factory=list)


class StockFortuneSnapshot(SMBaseModel):
    """可解释、可回放的股票术数时点快照；不包含金融预测或交易建议。"""

    contract_version: Literal["stock-fortune-snapshot-v1"] = STOCK_FORTUNE_SNAPSHOT_VERSION
    stock_identity: StockFortuneIdentity
    birth_profile: StockFortuneBirthProfile
    evaluation_time: datetime | None = None
    temporal_resolution: FortuneTemporalResolution
    temporal_context: TemporalFortuneContext | None = None
    natal_context: FortuneNatalContext
    luck_cycle_context: FortuneLuckCycleContext
    annual_context: FortuneTemporalPillarContext
    monthly_context: FortuneTemporalPillarContext
    daily_context: FortuneTemporalPillarContext
    ten_god_context: FortuneTenGodContext
    relation_context: FortuneRelationContext
    provenance: list[FortuneProvenanceRecord] = Field(min_length=1)
    rule_versions: FortuneRuleVersions
    availability: FortuneAvailability
    raw_chart: dict[str, object] = Field(default_factory=dict)
    chart_artifact_ids: list[str] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    engine_version: str = STOCK_FORTUNE_ENGINE_VERSION
    rule_version: str = FORTUNE_SNAPSHOT_RULE_VERSION

    @model_validator(mode="after")
    def validate_snapshot_consistency(self) -> StockFortuneSnapshot:
        if self.stock_identity.symbol != self.birth_profile.symbol:
            raise ValueError("snapshot 的证券身份必须与 birth_profile 一致")
        if (
            self.stock_identity.exchange != Exchange.UNKNOWN
            and self.birth_profile.exchange != Exchange.UNKNOWN
            and self.stock_identity.exchange != self.birth_profile.exchange
        ):
            raise ValueError("snapshot 的证券交易所必须与 birth_profile 一致")
        if self.temporal_resolution.status == FortuneTemporalResolutionStatus.RESOLVED:
            if self.temporal_context is None or self.evaluation_time is None:
                raise ValueError("resolved snapshot 必须包含 evaluation_time 与 temporal_context")
            if self.temporal_context.target_at != self.evaluation_time:
                raise ValueError("evaluation_time 必须与 temporal_context.target_at 一致")
        elif self.temporal_context is not None or self.evaluation_time is not None:
            raise ValueError("未解析的 evaluation time 不得伪造 temporal_context")
        if (
            self.temporal_resolution.status != FortuneTemporalResolutionStatus.RESOLVED
            and self.availability != FortuneAvailability.UNAVAILABLE
        ):
            raise ValueError("未解析的 evaluation time 必须将 Snapshot 标记为 unavailable")
        if self.birth_profile.birth_datetime is None and (
            self.natal_context.availability != FortuneAvailability.UNAVAILABLE
        ):
            raise ValueError("出生时刻不可用时不得输出部分或完整原局")
        if (
            self.rule_versions.snapshot_rule_version != self.rule_version
            or self.rule_versions.birth_profile_version
            != self.birth_profile.birth_profile_version
            or self.rule_versions.birth_rule_version != self.birth_profile.rule_version
            or self.rule_versions.luck_cycle_direction_rule_version
            != self.luck_cycle_context.rule_version
            or self.rule_versions.luck_cycle_period_rule_version
            != self.luck_cycle_context.period_rule_version
            or self.rule_versions.ten_god_rule_version != self.ten_god_context.rule_version
            or self.rule_versions.relation_rule_version != self.relation_context.rule_version
        ):
            raise ValueError("Snapshot rule_versions 必须与实际 profile/context 版本一致")
        if self.temporal_context and (
            self.rule_versions.calendar_engine_version
            != self.temporal_context.calendar_snapshot.engine_version
        ):
            raise ValueError("Snapshot calendar_engine_version 必须与 CalendarSnapshot 一致")
        if self.natal_context.availability == FortuneAvailability.AVAILABLE and (
            self.rule_versions.bazi_engine_version != self.natal_context.bazi_engine_version
        ):
            raise ValueError("Snapshot bazi_engine_version 必须与 BaziChart 一致")
        provenance_components = {record.component for record in self.provenance}
        required_provenance = {
            FortuneProvenanceComponent.STOCK_IDENTITY,
            FortuneProvenanceComponent.BIRTH_PROFILE,
            FortuneProvenanceComponent.EVALUATION_TIME,
            FortuneProvenanceComponent.LUCK_CYCLE,
            FortuneProvenanceComponent.TEN_GOD,
            FortuneProvenanceComponent.RELATION,
        }
        if not required_provenance <= provenance_components:
            raise ValueError("Snapshot provenance 缺少一个或多个核心组件")
        if self.temporal_context and FortuneProvenanceComponent.CALENDAR not in provenance_components:
            raise ValueError("存在 temporal context 时必须记录 Calendar provenance")
        if (
            self.natal_context.availability == FortuneAvailability.AVAILABLE
            and FortuneProvenanceComponent.BAZI not in provenance_components
        ):
            raise ValueError("存在 natal context 时必须记录 Bazi provenance")
        for expected_layer, context in (
            ("annual", self.annual_context),
            ("monthly", self.monthly_context),
            ("daily", self.daily_context),
        ):
            if context.layer != expected_layer:
                raise ValueError(f"{expected_layer} context 的 layer 不匹配")
        if self.availability == FortuneAvailability.AVAILABLE:
            required = (
                self.temporal_context is not None,
                self.natal_context.availability == FortuneAvailability.AVAILABLE,
                self.annual_context.availability == FortuneAvailability.AVAILABLE,
                self.monthly_context.availability == FortuneAvailability.AVAILABLE,
                self.daily_context.availability == FortuneAvailability.AVAILABLE,
                self.luck_cycle_context.availability == FortuneAvailability.AVAILABLE,
                self.luck_cycle_context.cycle_availability == FortuneAvailability.AVAILABLE,
                self.ten_god_context.availability == FortuneAvailability.AVAILABLE,
                self.relation_context.availability == FortuneAvailability.AVAILABLE,
            )
            if not all(required):
                raise ValueError("AVAILABLE snapshot 的核心上下文必须全部可用")
        if self.raw_chart and not self.chart_artifact_ids:
            raise ValueError("raw_chart 必须有对应 chart_artifact_ids")
        return self


# ---------------------------------------------------------------------------
# F4：历史/未来时间轴与日期横截面扫描契约
# ---------------------------------------------------------------------------

FORTUNE_TIMELINE_CONTRACT_VERSION = "stock-fortune-timeline-v1"
FORTUNE_TIMELINE_RULE_VERSION = "stock-fortune-timeline-rule-v1"
FORTUNE_CROSS_SECTION_CONTRACT_VERSION = "stock-fortune-cross-section-v1"
FORTUNE_CROSS_SECTION_RULE_VERSION = "stock-fortune-cross-section-rule-v1"


class FortuneTimelineDateMode(str, Enum):
    ALL_CALENDAR_DAYS = "ALL_CALENDAR_DAYS"
    TRADING_DAYS_ONLY = "TRADING_DAYS_ONLY"


class FortuneTimelineAnchorMode(str, Enum):
    EXACT_LOCAL_TIME = "EXACT_LOCAL_TIME"
    MARKET_SESSION_DATE = "MARKET_SESSION_DATE"


class FortuneScanTemporalMode(str, Enum):
    EXACT_DATETIME = "EXACT_DATETIME"
    DATE_SCAN_NOON = "DATE_SCAN_NOON"
    MARKET_SESSION_DATE = "MARKET_SESSION_DATE"


class FortuneScanAvailabilityPolicy(str, Enum):
    INCLUDE = "INCLUDE"
    AVAILABLE_ONLY = "AVAILABLE_ONLY"


class FortuneScanSort(str, Enum):
    SYMBOL = "symbol"
    MATCHED_CONDITION_COUNT = "matched_condition_count"
    RELATION_EVENT_COUNT = "relation_event_count"


class FortuneTenGodFilter(SMBaseModel):
    """十神筛选必须标明时间层；原局筛选必须再指定柱位。"""

    layer: FortuneTenGodLayer
    ten_god: str = Field(min_length=2)
    position: Literal["year", "month", "day", "hour"] | None = None
    hidden_stem: str | None = Field(default=None, min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_dimension(self) -> FortuneTenGodFilter:
        from src.core.constants import TEN_GODS

        if self.ten_god not in TEN_GODS:
            raise ValueError(f"未知十神 {self.ten_god!r}；合法值为 {list(TEN_GODS)}")
        layer = getattr(self.layer, "value", self.layer)
        if layer == FortuneTenGodLayer.DAYUN.value:
            raise ValueError("当前 Snapshot 未提供大运十神，不能将其作为筛选维度")
        if layer in {FortuneTenGodLayer.NATAL.value, FortuneTenGodLayer.HIDDEN_STEM.value}:
            if self.position is None:
                raise ValueError("原局/藏干十神筛选必须指定 position")
        elif self.position is not None or self.hidden_stem is not None:
            raise ValueError("流年/流月/流日筛选不得指定原局柱位或藏干")
        if layer != FortuneTenGodLayer.HIDDEN_STEM.value and self.hidden_stem is not None:
            raise ValueError("只有 HIDDEN_STEM 筛选可以指定 hidden_stem")
        return self


class FortuneRelationFilter(SMBaseModel):
    """一条关系条件明确限定关系类型、时空来源及原局目标。"""

    relation_type: str = Field(min_length=1)
    source_context: FortuneContextKind
    source_pillar: Literal["year", "month", "day", "dayun"]
    target_context: Literal[FortuneContextKind.NATAL] = FortuneContextKind.NATAL
    target_pillar: Literal["year", "month", "day"]
    source_component: FortuneRelationComponent | None = None
    target_component: FortuneRelationComponent | None = None

    @model_validator(mode="after")
    def validate_relation_scope(self) -> FortuneRelationFilter:
        from src.core.schemas.relation import RELATION_TYPES

        if self.relation_type not in RELATION_TYPES:
            raise ValueError(f"未知关系类型 {self.relation_type!r}")
        context = getattr(self.source_context, "value", self.source_context)
        expected_pillar = {
            FortuneContextKind.YEAR.value: "year",
            FortuneContextKind.MONTH.value: "month",
            FortuneContextKind.DAY.value: "day",
            FortuneContextKind.DAYUN.value: "dayun",
        }.get(context)
        if expected_pillar is None or expected_pillar != self.source_pillar:
            raise ValueError("source_context 与 source_pillar 必须指向同一时间上下文")
        if self.target_context != FortuneContextKind.NATAL:
            raise ValueError("当前关系过滤的 target_context 必须是 NATAL")
        return self


class StockFortuneTimelineRequest(SMBaseModel):
    """单证券时间轴请求；计算时点由明确的日期锚点策略生成。"""

    stock_identity: StockFortuneIdentity
    birth_profile: StockFortuneBirthProfile
    start_date: date
    end_date: date
    date_mode: FortuneTimelineDateMode = FortuneTimelineDateMode.ALL_CALENDAR_DAYS
    anchor_mode: FortuneTimelineAnchorMode = FortuneTimelineAnchorMode.EXACT_LOCAL_TIME
    evaluation_time: time | None = None
    timezone: str = "Asia/Shanghai"
    luck_cycle_evidence: FortuneLuckCycleEvidence | None = None
    evaluation_source: SourceRef = Field(
        default_factory=lambda: SourceRef(source="stock-fortune-timeline")
    )
    evaluation_source_version: str = "stock-fortune-timeline-v1"
    market_session_version: str = ""
    config_version: str = ""
    ten_god_filters: list[FortuneTenGodFilter] = Field(default_factory=list)
    relation_filters: list[FortuneRelationFilter] = Field(default_factory=list)
    include_relation_events: bool = True
    include_month_segments: bool = True
    include_ten_god_index: bool = True

    @model_validator(mode="after")
    def validate_timeline_request(self) -> StockFortuneTimelineRequest:
        if self.stock_identity.symbol != self.birth_profile.symbol:
            raise ValueError("stock_identity.symbol 必须与 birth_profile.symbol 一致")
        if self.relation_filters and not self.include_relation_events:
            raise ValueError("relation_filters 要求 include_relation_events=true")
        if self.end_date < self.start_date:
            raise ValueError("end_date 不得早于 start_date")
        if (self.end_date - self.start_date).days + 1 > 3660:
            raise ValueError("单次 Fortune Timeline 最多支持 3660 个自然日")
        try:
            ZoneInfo(self.timezone)
        except (KeyError, ValueError) as exc:
            raise ValueError("timezone 必须是有效 IANA 时区") from exc
        anchor = getattr(self.anchor_mode, "value", self.anchor_mode)
        date_mode = getattr(self.date_mode, "value", self.date_mode)
        if anchor == FortuneTimelineAnchorMode.MARKET_SESSION_DATE.value:
            if date_mode != FortuneTimelineDateMode.TRADING_DAYS_ONLY.value:
                raise ValueError("MARKET_SESSION_DATE 只适用于 TRADING_DAYS_ONLY")
            if self.evaluation_time is not None:
                raise ValueError("MARKET_SESSION_DATE 使用版本化开盘锚点，不接收 evaluation_time")
            exchange = (
                self.stock_identity.exchange
                if self.stock_identity.exchange != Exchange.UNKNOWN
                else self.birth_profile.exchange
            )
            if exchange == Exchange.UNKNOWN:
                raise ValueError("MARKET_SESSION_DATE 必须能够确定交易所")
            if not (
                self.market_session_version or self.birth_profile.market_session_version
            ).strip():
                raise ValueError("MARKET_SESSION_DATE 必须提供版本化交易时段")
            if not (self.config_version or self.birth_profile.config_version).strip():
                raise ValueError("MARKET_SESSION_DATE 必须提供 config_version")
        elif self.evaluation_time is None:
            self.evaluation_time = time(12, 0)
        if not self.evaluation_source_version.strip():
            raise ValueError("evaluation_source_version 必须非空")
        return self


class FortuneTradingCalendarCoverage(SMBaseModel):
    exchange: str
    version_token: str = ""
    observed_start: date | None = None
    observed_end: date | None = None
    published_start: date | None = None
    published_end: date | None = None
    confirmed_trading_days: int = Field(default=0, ge=0)
    confirmed_closed_days: int = Field(default=0, ge=0)
    unknown_days: int = Field(default=0, ge=0)
    sources: list[str] = Field(default_factory=list)


class StockFortuneStableContext(SMBaseModel):
    """一次计算后供整条时间轴共享的原局和规则上下文。"""

    source_snapshot_at: datetime
    natal_context: FortuneNatalContext
    natal_ten_gods: list[FortuneTenGodObservation] = Field(default_factory=list)
    hidden_stem_ten_gods: list[FortuneHiddenStemTenGodObservation] = Field(default_factory=list)
    luck_cycle_direction: LuckCycleDirection | None = None
    luck_cycle_availability: FortuneAvailability = FortuneAvailability.UNAVAILABLE
    polarity_observed_at: datetime | None = None
    luck_cycle_periods: list[FortuneDayunPeriod] = Field(default_factory=list)
    natal_relation_events: list[FortuneRelationEvent] = Field(default_factory=list)
    rule_versions: FortuneRuleVersions
    provenance: list[FortuneProvenanceRecord] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    chart_artifact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stable_context(self) -> StockFortuneStableContext:
        if self.source_snapshot_at.tzinfo is None or self.source_snapshot_at.utcoffset() is None:
            raise ValueError("source_snapshot_at 必须带时区")
        if self.luck_cycle_availability == FortuneAvailability.UNAVAILABLE:
            if self.luck_cycle_direction is not None or self.luck_cycle_periods:
                raise ValueError("UNAVAILABLE 的大运 stable context 不得携带方向或周期")
        if any(event.scope != FortuneRelationScope.NATAL_NATAL for event in self.natal_relation_events):
            raise ValueError("stable natal_relation_events 只能包含原局关系")
        return self


class StockFortuneTimelinePoint(SMBaseModel):
    date: date
    evaluation_datetime: datetime
    trading_day: bool | None = None
    trading_calendar_source: str = "unavailable"
    luck_cycle_ref: FortuneDayunPeriod | None = None
    annual_pillar: GanZhi | None = None
    monthly_pillar: GanZhi | None = None
    daily_pillar: GanZhi | None = None
    annual_ten_god: FortuneTenGodObservation | None = None
    monthly_ten_god: FortuneTenGodObservation | None = None
    daily_ten_god: FortuneTenGodObservation | None = None
    relation_events: list[FortuneRelationEvent] = Field(default_factory=list)
    availability: FortuneAvailability

    @model_validator(mode="after")
    def validate_point(self) -> StockFortuneTimelinePoint:
        if self.evaluation_datetime.tzinfo is None or self.evaluation_datetime.utcoffset() is None:
            raise ValueError("evaluation_datetime 必须带时区")
        if self.evaluation_datetime.date() != self.date:
            raise ValueError("evaluation_datetime 的本地日期必须与 point.date 一致")
        if self.trading_day is not None and self.trading_calendar_source not in {
            "observed_index_days",
            "published_exchange_calendar",
        }:
            raise ValueError("未验证的交易日历来源不得返回 trading_day=true/false")
        return self


class FortuneSolarMonthSegment(SMBaseModel):
    """流月按十二节精确切段；gregorian_months 仅用于公历分组展示。"""

    start_at: datetime
    end_at: datetime
    boundary_jieqi: str
    next_boundary_jieqi: str
    monthly_pillar: GanZhi
    monthly_ten_god: str | None = None
    gregorian_months: list[str] = Field(default_factory=list)
    effective_dates: list[date] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_segment(self) -> FortuneSolarMonthSegment:
        if self.start_at.tzinfo is None or self.start_at.utcoffset() is None:
            raise ValueError("solar month segment start_at 必须带时区")
        if self.end_at.tzinfo is None or self.end_at.utcoffset() is None:
            raise ValueError("solar month segment end_at 必须带时区")
        if self.start_at >= self.end_at:
            raise ValueError("solar month segment 必须是非空半开区间")
        if self.effective_dates != sorted(set(self.effective_dates)):
            raise ValueError("effective_dates 必须去重并按日期递增")
        return self


class FortuneTenGodDateIndex(SMBaseModel):
    layer: Literal["year", "month", "day"]
    ten_god: str
    dates: list[date] = Field(default_factory=list)


class FortuneTimelineTenGodIndex(SMBaseModel):
    entries: list[FortuneTenGodDateIndex] = Field(default_factory=list)
    stable_natal: list[FortuneTenGodObservation] = Field(default_factory=list)
    stable_hidden_stems: list[FortuneHiddenStemTenGodObservation] = Field(default_factory=list)


class StockFortuneTimeline(SMBaseModel):
    contract_version: Literal["stock-fortune-timeline-v1"] = FORTUNE_TIMELINE_CONTRACT_VERSION
    stock_identity: StockFortuneIdentity
    birth_context: StockFortuneBirthProfile
    stable_context: StockFortuneStableContext
    start_date: date
    end_date: date
    date_mode: FortuneTimelineDateMode
    anchor_mode: FortuneTimelineAnchorMode
    timezone: str
    ten_god_filters: list[FortuneTenGodFilter] = Field(default_factory=list)
    relation_filters: list[FortuneRelationFilter] = Field(default_factory=list)
    include_relation_events: bool = True
    include_month_segments: bool = True
    include_ten_god_index: bool = True
    points: list[StockFortuneTimelinePoint] = Field(default_factory=list)
    month_segments: list[FortuneSolarMonthSegment] = Field(default_factory=list)
    ten_god_index: FortuneTimelineTenGodIndex | None = None
    trading_calendar: FortuneTradingCalendarCoverage
    availability: FortuneAvailability
    rule_versions: FortuneRuleVersions
    provenance: list[FortuneProvenanceRecord] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    rule_version: str = FORTUNE_TIMELINE_RULE_VERSION

    @model_validator(mode="after")
    def validate_timeline(self) -> StockFortuneTimeline:
        if self.start_date > self.end_date:
            raise ValueError("timeline range 必须满足 start_date <= end_date")
        if self.stock_identity.symbol != self.birth_context.symbol:
            raise ValueError("timeline stock_identity 与 birth_context 不一致")
        if any(not (self.start_date <= point.date <= self.end_date) for point in self.points):
            raise ValueError("timeline point 超出请求日期范围")
        if any(left.date >= right.date for left, right in zip(self.points, self.points[1:])):
            raise ValueError("timeline points 必须按日期严格递增且不重复")
        return self


class StockFortuneScanTarget(SMBaseModel):
    stock_identity: StockFortuneIdentity
    birth_profile: StockFortuneBirthProfile
    luck_cycle_evidence: FortuneLuckCycleEvidence | None = None

    @model_validator(mode="after")
    def validate_target(self) -> StockFortuneScanTarget:
        if self.stock_identity.symbol != self.birth_profile.symbol:
            raise ValueError("scan target identity.symbol 必须与 birth_profile.symbol 一致")
        return self


class StockFortuneScanUniverse(SMBaseModel):
    """显式股票列表；更大的 PIT universe 可由上层 provider 映射到该契约。"""

    version: str = Field(min_length=1)
    source: SourceRef
    targets: list[StockFortuneScanTarget] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def validate_symbols(self) -> StockFortuneScanUniverse:
        symbols = [item.stock_identity.symbol for item in self.targets]
        if len(symbols) != len(set(symbols)):
            raise ValueError("scan universe 不得包含重复 symbol")
        return self


class StockFortuneScanRequest(SMBaseModel):
    contract_version: Literal["stock-fortune-cross-section-v1"] = FORTUNE_CROSS_SECTION_CONTRACT_VERSION
    temporal_mode: FortuneScanTemporalMode
    evaluation_date: date | None = None
    evaluation_datetime: datetime | None = None
    exchange: Exchange | None = None
    is_trading_day: bool | None = None
    universe: StockFortuneScanUniverse
    ten_god_filters: list[FortuneTenGodFilter] = Field(default_factory=list)
    relation_filters: list[FortuneRelationFilter] = Field(default_factory=list)
    availability_policy: FortuneScanAvailabilityPolicy = FortuneScanAvailabilityPolicy.INCLUDE
    sort: FortuneScanSort = FortuneScanSort.SYMBOL
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    market_session_version: str = ""
    config_version: str = ""

    @model_validator(mode="after")
    def validate_scan_time(self) -> StockFortuneScanRequest:
        mode = getattr(self.temporal_mode, "value", self.temporal_mode)
        if mode == FortuneScanTemporalMode.EXACT_DATETIME.value:
            if self.evaluation_datetime is None or self.evaluation_date is not None:
                raise ValueError("EXACT_DATETIME 必须只提供 evaluation_datetime")
            if self.evaluation_datetime.tzinfo is None or self.evaluation_datetime.utcoffset() is None:
                raise ValueError("EXACT_DATETIME 必须带时区")
            if self.exchange is not None or self.is_trading_day is not None:
                raise ValueError("EXACT_DATETIME 不接受 market-session 字段")
        else:
            if self.evaluation_date is None or self.evaluation_datetime is not None:
                raise ValueError("DATE_SCAN_NOON / MARKET_SESSION_DATE 必须只提供 evaluation_date")
        if mode == FortuneScanTemporalMode.DATE_SCAN_NOON.value:
            if self.exchange is not None or self.is_trading_day is not None:
                raise ValueError("DATE_SCAN_NOON 不接受 market-session 字段")
        elif mode == FortuneScanTemporalMode.MARKET_SESSION_DATE.value:
            if self.exchange in {None, Exchange.UNKNOWN} or self.is_trading_day is not True:
                raise ValueError("MARKET_SESSION_DATE 必须提供交易所及已确认交易日证据")
            if not self.market_session_version.strip() or not self.config_version.strip():
                raise ValueError("MARKET_SESSION_DATE 必须提供 market-session/config 版本")
            for target in self.universe.targets:
                target_exchange = (
                    target.stock_identity.exchange
                    if target.stock_identity.exchange != Exchange.UNKNOWN
                    else target.birth_profile.exchange
                )
                if target_exchange != self.exchange:
                    raise ValueError("MARKET_SESSION_DATE 的显式 universe 必须与指定交易所一致")
        return self


class StockFortuneMatchedCondition(SMBaseModel):
    kind: Literal["ten_god", "relation"]
    label: str = Field(min_length=1)
    ten_god_filter: FortuneTenGodFilter | None = None
    relation_filter: FortuneRelationFilter | None = None


class StockFortuneScanItem(SMBaseModel):
    symbol: str
    name: str = ""
    matched_conditions: list[StockFortuneMatchedCondition] = Field(default_factory=list)
    annual_ten_god: str | None = None
    monthly_ten_god: str | None = None
    daily_ten_god: str | None = None
    relevant_relation_events: list[FortuneRelationEvent] = Field(default_factory=list)
    availability: FortuneAvailability
    snapshot_ref: str | None = None
    rule_versions: FortuneRuleVersions


class StockFortuneScanRuleVersions(SMBaseModel):
    snapshot_rule_versions: list[str] = Field(default_factory=list)
    birth_profile_versions: list[str] = Field(default_factory=list)
    birth_rule_versions: list[str] = Field(default_factory=list)
    calendar_engine_versions: list[str] = Field(default_factory=list)
    bazi_engine_versions: list[str] = Field(default_factory=list)
    luck_cycle_rule_versions: list[str] = Field(default_factory=list)
    ten_god_rule_versions: list[str] = Field(default_factory=list)
    relation_rule_versions: list[str] = Field(default_factory=list)
    config_versions: list[str] = Field(default_factory=list)


class StockFortuneScanResponse(SMBaseModel):
    contract_version: Literal["stock-fortune-cross-section-v1"] = FORTUNE_CROSS_SECTION_CONTRACT_VERSION
    evaluation_context: FortuneTemporalResolution
    temporal_mode: FortuneScanTemporalMode
    exchange: Exchange | None = None
    is_trading_day: bool | None = None
    ten_god_filters: list[FortuneTenGodFilter] = Field(default_factory=list)
    relation_filters: list[FortuneRelationFilter] = Field(default_factory=list)
    availability_policy: FortuneScanAvailabilityPolicy = FortuneScanAvailabilityPolicy.INCLUDE
    sort: FortuneScanSort = FortuneScanSort.SYMBOL
    universe_version: str
    universe_source: SourceRef
    universe_digest: str
    request_digest: str = Field(min_length=64, max_length=64)
    trading_calendar_source: Literal[
        "observed_index_days", "published_exchange_calendar"
    ] | None = None
    trading_calendar_version: str | None = None
    total_examined: int = Field(ge=0)
    total_matched: int = Field(ge=0)
    total: int = Field(ge=0, description="等于 total_matched，供分页客户端使用")
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    items: list[StockFortuneScanItem] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    rule_versions: StockFortuneScanRuleVersions
    availability: FortuneAvailability
    rule_version: str = FORTUNE_CROSS_SECTION_RULE_VERSION

    @model_validator(mode="after")
    def validate_pagination(self) -> StockFortuneScanResponse:
        if self.total != self.total_matched:
            raise ValueError("total 必须与 total_matched 一致")
        if self.total_matched > self.total_examined:
            raise ValueError("total_matched 不得大于 total_examined")
        if len(self.items) > self.limit:
            raise ValueError("items 不得超过 limit")
        if self.temporal_mode == FortuneScanTemporalMode.MARKET_SESSION_DATE:
            if not self.trading_calendar_source or not self.trading_calendar_version:
                raise ValueError("MARKET_SESSION_DATE response 必须记录已验证交易日历来源与版本")
            if self.exchange in {None, Exchange.UNKNOWN} or self.is_trading_day is not True:
                raise ValueError("MARKET_SESSION_DATE response 必须回显交易所及已验证交易日")
        elif (
            self.trading_calendar_source is not None
            or self.trading_calendar_version is not None
            or self.exchange is not None
            or self.is_trading_day is not None
        ):
            raise ValueError("非 MARKET_SESSION_DATE response 不应携带交易日历证据")
        return self
