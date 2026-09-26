from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.fortune.birth import (
    natal_pillar_availability,
    resolve_market_first_trade_profile,
)
from src.core.fortune.market_sessions import AShareMarketSessionAdapter
from src.core.fortune.temporal_context import build_temporal_context
from src.core.schemas.calendar import CalendarSnapshot, GanZhi, LunarDate, SolarDate
from src.core.schemas.common import Assumption, Exchange, SourceRef
from src.core.schemas.fortune import (
    BirthTimePrecision,
    CompatibilityGender,
    FortuneAvailability,
    FirstTradeObservation,
    FirstTradeObservationResolution,
    FirstTradeObservationStatus,
    FortunePolarity,
    FortuneRelationCategory,
    FortuneContextKind,
    FortuneRelationComponent,
    FortuneRelationEvent,
    FortuneRelationParticipant,
    FortuneRelationScope,
    FortuneResonance,
    FortuneConfidenceComponent,
    FortuneDataConfidence,
    FortuneResultV1,
    FortuneRuleFactorGroup,
    FortuneScore,
    FortuneScoreKind,
    FortuneTemporalLayer,
    FortuneRuleValence,
    LuckCycleDirection,
    MarketSessionStatus,
    NatalPillarAvailability,
    NatalPillarSet,
    FortuneLuckCycleContext,
    WealthFortuneFactors,
)


def _inferred_profile():
    observation = FirstTradeObservation(
        status=FirstTradeObservationStatus.OBSERVED_TRADING_DATE,
        first_trade_date=date(2001, 8, 27),
        resolution=FirstTradeObservationResolution.DAILY_BAR,
        source=SourceRef(source="historical_daily_bars"),
        source_version="daily-bars-v1",
        reason="最早可观测日线日期",
    )
    return resolve_market_first_trade_profile(
        symbol="600519",
        exchange=Exchange.SSE,
        listing_date=date(2001, 8, 27),
        observation=observation,
        config_version="v1",
        market_session_version="a-share-session-v1",
    )


def test_inferred_listing_open_is_explicit_and_not_actual_first_trade() -> None:
    profile = _inferred_profile()

    assert profile.birth_datetime == datetime.fromisoformat("2001-08-27T09:30:00+08:00")
    assert profile.birth_time_precision == BirthTimePrecision.INFERRED
    assert profile.first_trade_datetime is None
    assert profile.birth_datetime_status == BirthTimePrecision.INFERRED
    assert profile.birth_profile_version == "stock-fortune-birth-v2"
    assert profile.rule_version == "fortune-first-trade-resolution-v1"
    assert profile.source_version == "daily-bars-v1"
    assert profile.config_version == "v1"
    assert profile.source.source == "historical_daily_bars"
    assert profile.source.extra["birth_datetime_method"] == "market_session_open_inferred"
    assert profile.market_session_version == (
        "fortune-market-session-anchor-v1:a-share-session-v1:v1"
    )
    assert len(profile.assumptions) >= 2
    assert natal_pillar_availability(profile.birth_time_precision) == NatalPillarAvailability.FOUR_PILLARS


def test_precision_controls_pillar_availability_without_filling_time() -> None:
    assert natal_pillar_availability(BirthTimePrecision.DATE_ONLY) == NatalPillarAvailability.THREE_PILLARS
    assert natal_pillar_availability(BirthTimePrecision.UNKNOWN) == NatalPillarAvailability.UNAVAILABLE
    assert natal_pillar_availability(BirthTimePrecision.EXACT) == NatalPillarAvailability.FOUR_PILLARS


def test_exact_first_trade_and_custom_time_are_distinct_bases() -> None:
    from src.core.schemas.fortune import FortuneBirthBasis, StockFortuneBirthProfile

    actual = datetime.fromisoformat("2001-08-27T09:31:12+08:00")
    exact = StockFortuneBirthProfile(
        symbol="600519",
        exchange=Exchange.SSE,
        listing_date=date(2001, 8, 27),
        first_trade_datetime=actual,
        first_trade_date=actual.date(),
        first_trade_resolution=FirstTradeObservationResolution.TRADE,
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        birth_datetime=actual,
        birth_time_precision=BirthTimePrecision.EXACT,
        source=SourceRef(source="historical_tick"),
        source_version="ticks-v1",
    )
    custom = StockFortuneBirthProfile(
        symbol="600519",
        exchange=Exchange.SSE,
        birth_basis=FortuneBirthBasis.CUSTOM,
        birth_datetime=actual,
        birth_time_precision=BirthTimePrecision.EXACT,
        source=SourceRef(source="user:custom"),
        source_version="user-input-v1",
    )
    assert exact.first_trade_datetime == actual
    assert custom.birth_basis == FortuneBirthBasis.CUSTOM
    assert custom.first_trade_datetime is None


def test_inferred_or_date_only_cannot_hide_missing_assumptions_or_time() -> None:
    from src.core.schemas.fortune import FortuneBirthBasis, StockFortuneBirthProfile

    with pytest.raises(ValidationError, match="INFERRED 必须公开记录 assumptions"):
        StockFortuneBirthProfile(
            symbol="600519",
            birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
            birth_datetime=datetime.fromisoformat("2001-08-27T09:30:00+08:00"),
            birth_time_precision=BirthTimePrecision.INFERRED,
        )
    with pytest.raises(ValidationError, match="DATE_ONLY/UNKNOWN 不得伪造 birth_datetime"):
        StockFortuneBirthProfile(
            symbol="600519",
            birth_datetime=datetime.fromisoformat("2001-08-27T09:30:00+08:00"),
            birth_time_precision=BirthTimePrecision.DATE_ONLY,
        )


def test_direction_polarity_and_compatibility_gender_are_separate() -> None:
    context = FortuneLuckCycleContext(
        polarity=FortunePolarity.YANG,
        direction=LuckCycleDirection.REVERSE,
        compatibility_gender=CompatibilityGender.MALE,
        availability=FortuneAvailability.AVAILABLE,
        direction_basis="explicit-research-variant-v1",
        polarity_source=SourceRef(source="explicit-research-input"),
        polarity_source_version="research-input-v1",
        market_session_version="explicit-session-v1",
        polarity_observation_date=date(2024, 11, 15),
        polarity_observed_at=datetime(2024, 11, 15, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        assumptions=[Assumption(
            key="test.variant", value="explicit", reason="显式测试输入", impact="测试",
        )],
    )
    assert context.polarity == FortunePolarity.YANG
    assert context.direction == LuckCycleDirection.REVERSE
    assert context.compatibility_gender == CompatibilityGender.MALE
    assert FortuneLuckCycleContext().direction is None


def test_unavailable_score_is_none_but_zero_can_be_a_real_rule_value() -> None:
    unavailable = FortuneScore(
        kind=FortuneScoreKind.RULE_SCORE,
        value=None,
        availability=FortuneAvailability.UNAVAILABLE,
        rule_version="rule-v1",
    )
    zero = FortuneScore(
        kind=FortuneScoreKind.RULE_SCORE,
        value=0,
        availability=FortuneAvailability.AVAILABLE,
        rule_version="rule-v1",
    )
    assert unavailable.value is None
    assert zero.value == 0
    with pytest.raises(ValidationError, match="不能用 0 代替"):
        FortuneScore(
            kind=FortuneScoreKind.RULE_SCORE,
            value=0,
            availability=FortuneAvailability.UNAVAILABLE,
            rule_version="rule-v1",
        )


def test_resonance_depth_is_rule_layer_count_not_probability() -> None:
    resonance = FortuneResonance(
        matching_layer_count=4,
        assessed_layer_count=5,
        rule_version="resonance-v1",
    )
    assert resonance.resonance_depth == "4/5"
    assert set(FortuneTemporalLayer) == {
        FortuneTemporalLayer.DAYUN,
        FortuneTemporalLayer.YEAR,
        FortuneTemporalLayer.MONTH,
        FortuneTemporalLayer.DAY,
        FortuneTemporalLayer.HOUR,
    }


def test_relation_contract_preserves_raw_type_without_inventing_direction_or_weight() -> None:
    source = FortuneRelationParticipant(
        context=FortuneContextKind.MONTH,
        pillar="month",
        component=FortuneRelationComponent.BRANCH,
        value="丑",
    )
    target = FortuneRelationParticipant(
        context=FortuneContextKind.NATAL,
        pillar="day",
        component=FortuneRelationComponent.BRANCH,
        value="子",
    )
    event = FortuneRelationEvent(
        category=FortuneRelationCategory.COMBINATION,
        relation_type="六合",
        source=source,
        target=target,
        participants=["month:month:branch:丑", "natal:day:branch:子"],
        scope=FortuneRelationScope.TEMPORAL_TO_NATAL,
        rule_version="bazi-relation-v3",
    )
    assert event.relation_type == "六合"
    assert event.direction == FortuneRuleValence.UNKNOWN
    assert event.severity is None
    assert event.weight is None


def test_three_pillar_shape_does_not_fabricate_hour_pillar() -> None:
    triple = NatalPillarSet(
        availability=NatalPillarAvailability.THREE_PILLARS,
        year=GanZhi.from_text("辛巳"),
        month=GanZhi.from_text("丙申"),
        day=GanZhi.from_text("壬戌"),
    )
    assert triple.hour is None
    with pytest.raises(ValidationError, match="THREE_PILLARS"):
        NatalPillarSet(
            availability=NatalPillarAvailability.THREE_PILLARS,
            year=GanZhi.from_text("辛巳"),
            month=GanZhi.from_text("丙申"),
            day=GanZhi.from_text("壬戌"),
            hour=GanZhi.from_text("乙巳"),
        )


def test_a_share_market_session_separates_lunch_from_traditional_hour() -> None:
    adapter = AShareMarketSessionAdapter()
    at_lunch = adapter.classify(
        datetime(2024, 11, 15, 3, 30, tzinfo=timezone.utc),
        Exchange.SSE,
        is_trading_day=True,
    )
    assert at_lunch.status == MarketSessionStatus.BREAK
    assert at_lunch.tradable is False


def test_a_share_weekend_conflicting_open_evidence_is_not_silently_overridden() -> None:
    with pytest.raises(ValueError, match="周末与交易日证据冲突"):
        AShareMarketSessionAdapter().classify(
            datetime(2024, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            Exchange.SSE,
            is_trading_day=True,
        )


@pytest.mark.parametrize(
    ("local_at", "is_trading_day", "status", "tradable"),
    [
        (datetime(2024, 11, 15, 9, 30), True, MarketSessionStatus.CONTINUOUS_TRADING, True),
        (datetime(2024, 11, 15, 12, 0), True, MarketSessionStatus.BREAK, False),
        (datetime(2024, 11, 15, 12, 0), None, MarketSessionStatus.UNKNOWN, False),
        (datetime(2024, 11, 15, 10, 0), None, MarketSessionStatus.UNKNOWN, None),
        (datetime(2024, 11, 18, 10, 0), False, MarketSessionStatus.CLOSED, False),
        (datetime(2024, 11, 16, 10, 0), None, MarketSessionStatus.CLOSED, False),
    ],
)
def test_a_share_session_status(local_at, is_trading_day, status, tradable) -> None:
    result = AShareMarketSessionAdapter().classify(
        local_at.replace(tzinfo=ZoneInfo("Asia/Shanghai")),
        Exchange.SSE,
        is_trading_day=is_trading_day,
    )
    assert result.status == status
    assert result.tradable is tradable


def _snapshot(when: datetime) -> CalendarSnapshot:
    return CalendarSnapshot(
        engine_version="test-calendar-v1",
        solar=SolarDate(
            date=when.date(), timestamp=when, year=when.year, month=when.month,
            day=when.day, hour=when.hour, minute=when.minute,
        ),
        lunar=LunarDate(year=2024, month=10, day=15, text="测试农历"),
        year_ganzhi=GanZhi.from_text("甲辰"),
        month_ganzhi=GanZhi.from_text("乙亥"),
        day_ganzhi=GanZhi.from_text("癸未"),
        hour_ganzhi=GanZhi.from_text("己未"),
    )


class _CountingCalendarProvider:
    def __init__(self) -> None:
        self.calls: list[datetime] = []

    def snapshot(self, when: datetime) -> CalendarSnapshot:
        self.calls.append(when)
        return _snapshot(when)


def test_temporal_context_requests_one_shared_local_calendar_snapshot() -> None:
    provider = _CountingCalendarProvider()
    context = build_temporal_context(
        datetime(2024, 11, 15, 6, 32, tzinfo=timezone.utc), provider
    )
    assert provider.calls == [datetime(2024, 11, 15, 14, 32)]
    assert context.flow_year.text == context.calendar_snapshot.year_ganzhi.text
    assert context.flow_month.text == context.calendar_snapshot.month_ganzhi.text
    assert context.flow_day.text == context.calendar_snapshot.day_ganzhi.text
    assert context.flow_hour.text == context.calendar_snapshot.hour_ganzhi.text


def test_fortune_result_retains_raw_chart_and_persisted_artifact_reference() -> None:
    profile = _inferred_profile()
    provider = _CountingCalendarProvider()
    temporal = build_temporal_context(
        datetime(2024, 11, 15, 6, 32, tzinfo=timezone.utc), provider
    )
    unavailable_group = FortuneRuleFactorGroup(availability=FortuneAvailability.UNAVAILABLE)
    unavailable_confidence = FortuneConfidenceComponent(
        availability=FortuneAvailability.UNAVAILABLE
    )
    result = FortuneResultV1(
        symbol="600519",
        birth_profile=profile,
        natal_pillars=NatalPillarSet(availability=NatalPillarAvailability.UNAVAILABLE),
        luck_cycle=FortuneLuckCycleContext(),
        temporal_context=temporal,
        raw_chart={"bazi": {"day_master": "壬"}},
        chart_artifact_ids=["artifact-600519-bazi-v1"],
        wealth_factors=WealthFortuneFactors(
            wealth_star_presence=unavailable_group,
            wealth_star_strength=unavailable_group,
            favorable_support=unavailable_group,
            unfavorable_pressure=unavailable_group,
            relations_positive=unavailable_group,
            relations_negative=unavailable_group,
            day_master_capacity=unavailable_group,
            resonance_depth=unavailable_group,
            rule_version="fortune-wealth-factors-v1",
        ),
        resonance=FortuneResonance(rule_version="fortune-resonance-v1"),
        confidence=FortuneDataConfidence(
            birth_data_confidence=unavailable_confidence,
            calendar_confidence=unavailable_confidence,
            rule_confidence=unavailable_confidence,
        ),
        engine_version="fortune-engine-v1",
        rule_version="fortune-rule-v1",
        birth_profile_version=profile.birth_profile_version,
        config_version="fortune-config-v1",
    )
    assert result.raw_chart["bazi"]["day_master"] == "壬"
    assert result.chart_artifact_ids == ["artifact-600519-bazi-v1"]
