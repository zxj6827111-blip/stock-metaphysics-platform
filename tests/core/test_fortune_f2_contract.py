from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.fortune.birth import resolve_market_first_trade_profile
from src.core.fortune.luck_cycle import (
    compatibility_variant_mode,
    resolve_first_day_yinyang_luck_cycle,
)
from src.core.fortune.temporal_context import resolve_temporal_input
from src.core.schemas.common import Exchange, MarketDataSource, SourceRef, VariantMode
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservation,
    FirstTradeObservationResolution,
    FirstTradeObservationStatus,
    FortuneAvailability,
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    FortuneTemporalResolutionMethod,
    FortuneTemporalResolutionStatus,
)
from src.core.schemas.market import Bar, BarSeries
from src.engines.calendar.calendar_engine import CalendarEngine
from src.market.normalization.errors import ProviderUnavailableError
from src.market.providers.fortune_first_trade import DailyBarFirstTradeProvider


class FakeDailyMarketProvider:
    provider_id = "test_daily"

    def __init__(self, result: BarSeries | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, date | None, date | None]] = []

    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "qfq",
    ) -> BarSeries:
        self.calls.append((code, start, end))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _daily_series(
    bars: list[Bar],
    *,
    source: str = "vendor_hfq",
    market_source: MarketDataSource = MarketDataSource.AKSHARE,
    is_degraded: bool = False,
) -> BarSeries:
    return BarSeries(
        stock_code="600519",
        bars=bars,
        source=market_source,
        source_ref=SourceRef(source=source, extra={"snapshot": "fixture-2026-09"}),
        is_degraded=is_degraded,
    )


def _observed_date(date_value: date = date(2010, 1, 4)) -> FirstTradeObservation:
    return FirstTradeObservation(
        status=FirstTradeObservationStatus.OBSERVED_TRADING_DATE,
        first_trade_date=date_value,
        resolution=FirstTradeObservationResolution.DAILY_BAR,
        source=SourceRef(source="vendor_hfq", extra={"snapshot": "daily-v7"}),
        source_version="daily-v7",
        reason="min(bar.trade_date) is the earliest observed trading date",
    )


def test_daily_provider_reports_earliest_observed_date_not_a_datetime() -> None:
    provider = FakeDailyMarketProvider(
        _daily_series(
            [
                Bar(trade_date=date(2010, 1, 5)),
                Bar(trade_date=date(2010, 1, 4)),
                Bar(trade_date=date(2010, 1, 6)),
            ]
        )
    )

    observation = DailyBarFirstTradeProvider(
        provider, source_version="daily-provider-v1"
    ).observe_first_trade("600519")

    assert observation.status == FirstTradeObservationStatus.OBSERVED_TRADING_DATE
    assert observation.first_trade_date == date(2010, 1, 4)
    assert observation.first_trade_datetime is None
    assert observation.resolution == FirstTradeObservationResolution.DAILY_BAR
    assert observation.source_version == "daily-provider-v1"
    assert observation.source.extra["date_semantics"] == "earliest_observed_trading_date"
    assert provider.calls == [("600519", None, None)]


@pytest.mark.parametrize(
    ("series", "error"),
    [
        (_daily_series([]), None),
        (_daily_series([Bar(trade_date=date(2010, 1, 4))], is_degraded=True), None),
        (None, ProviderUnavailableError("provider offline")),
    ],
)
def test_daily_provider_fails_closed_for_missing_or_degraded_history(series, error) -> None:
    provider = FakeDailyMarketProvider(error if error is not None else series)

    observation = DailyBarFirstTradeProvider(
        provider, source_version="daily-provider-v1"
    ).observe_first_trade("600519")

    assert observation.status == FirstTradeObservationStatus.UNAVAILABLE
    assert observation.first_trade_date is None
    assert observation.first_trade_datetime is None
    assert observation.reason


def test_daily_provider_requires_a_source_version_and_rejects_synthetic() -> None:
    with pytest.raises(ValueError, match="source_version"):
        DailyBarFirstTradeProvider(FakeDailyMarketProvider(_daily_series([])), source_version=" ")

    provider = FakeDailyMarketProvider(
        _daily_series(
            [Bar(trade_date=date(2010, 1, 4))],
            source="demo-bars",
            market_source=MarketDataSource.SYNTHETIC_DEMO,
        )
    )
    observation = DailyBarFirstTradeProvider(
        provider, source_version="daily-provider-v1"
    ).observe_first_trade("600519")
    assert observation.status == FirstTradeObservationStatus.UNAVAILABLE


def test_observed_daily_date_resolves_to_versioned_inferred_birth_open() -> None:
    observation = _observed_date()
    kwargs = dict(
        symbol="600519",
        exchange=Exchange.SSE,
        observation=observation,
        listing_date=None,
        config_version="v1",
        market_session_version="a-share-session-v1",
    )
    profile = resolve_market_first_trade_profile(**kwargs)
    replay = resolve_market_first_trade_profile(**kwargs)

    assert profile.birth_datetime == datetime(2010, 1, 4, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert profile.birth_datetime_status == BirthTimePrecision.INFERRED
    assert profile.birth_time_precision == BirthTimePrecision.INFERRED
    assert profile.first_trade_datetime is None
    assert profile.first_trade_date == date(2010, 1, 4)
    assert profile.source.source == "vendor_hfq"
    assert profile.source_version == "daily-v7"
    assert profile.timezone == "Asia/Shanghai"
    assert profile.market_session_version == (
        "fortune-market-session-anchor-v1:a-share-session-v1:v1"
    )
    assert profile.assumptions
    assert profile.model_dump(mode="json")["birth_datetime_status"] == "INFERRED"
    assert profile.model_dump(mode="json") == replay.model_dump(mode="json")


def test_unavailable_observation_never_falls_back_to_listing_date() -> None:
    observation = FirstTradeObservation(
        status=FirstTradeObservationStatus.UNAVAILABLE,
        source=SourceRef(source="market-provider:test_daily"),
        source_version="provider-v1",
        reason="没有可用的历史日线",
    )
    profile = resolve_market_first_trade_profile(
        symbol="600519",
        exchange=Exchange.SSE,
        observation=observation,
        listing_date=date(2010, 1, 4),
        config_version="v1",
        market_session_version="a-share-session-v1",
    )
    assert profile.birth_time_precision == BirthTimePrecision.UNKNOWN
    assert profile.first_trade_date is None
    assert profile.birth_datetime is None
    assert profile.assumptions


def test_observed_date_without_versioned_session_stays_date_only() -> None:
    profile = resolve_market_first_trade_profile(
        symbol="600519",
        exchange=Exchange.SSE,
        observation=_observed_date(),
        listing_date=date(2010, 1, 4),
        config_version="",
        market_session_version="",
    )
    assert profile.birth_time_precision == BirthTimePrecision.DATE_ONLY
    assert profile.birth_datetime is None
    assert profile.first_trade_datetime is None
    assert profile.first_trade_date == date(2010, 1, 4)
    assert profile.assumptions


def test_verified_minute_bar_retains_observed_minute_resolution() -> None:
    observed_at = datetime(2010, 1, 4, 9, 31, tzinfo=ZoneInfo("Asia/Shanghai"))
    observation = FirstTradeObservation(
        status=FirstTradeObservationStatus.VERIFIED_DATETIME,
        first_trade_datetime=observed_at,
        first_trade_date=date(2010, 1, 4),
        resolution=FirstTradeObservationResolution.MINUTE_BAR,
        source=SourceRef(source="minute-bars"),
        source_version="minute-v1",
        reason="first non-empty minute bar timestamp",
    )
    profile = resolve_market_first_trade_profile(
        symbol="600519",
        exchange=Exchange.SSE,
        observation=observation,
        listing_date=None,
        config_version="v1",
        market_session_version="a-share-session-v1",
    )
    assert profile.birth_time_precision == BirthTimePrecision.MINUTE
    assert profile.first_trade_datetime == observed_at
    assert profile.birth_datetime == observed_at


def test_first_day_polarity_is_unavailable_until_first_session_close() -> None:
    source = SourceRef(source="stock_master.first_day_yinyang")
    early = resolve_first_day_yinyang_luck_cycle(
        first_day_yinyang="阳",
        polarity_observation_date=date(2024, 11, 15),
        polarity_is_trading_day=True,
        source=source,
        source_version="stock-master-v1",
        market_session_version="a-share-session-v1:v1",
        exchange=Exchange.SSE,
        birth_year_stem="甲",
        as_of=datetime(2024, 11, 15, 14, 59, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    assert early.availability == FortuneAvailability.UNAVAILABLE
    assert early.direction is None
    assert "收盘后" in early.unavailability_reason


def test_missing_polarity_evidence_fails_closed_without_compatibility_default() -> None:
    unavailable = resolve_first_day_yinyang_luck_cycle(
        first_day_yinyang=None,
        polarity_observation_date=None,
        polarity_is_trading_day=None,
        source=None,
        source_version="",
        market_session_version="",
        exchange=Exchange.UNKNOWN,
        birth_year_stem=None,
        as_of=datetime(2024, 11, 15, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    assert unavailable.availability == FortuneAvailability.UNAVAILABLE
    assert unavailable.polarity is None
    assert unavailable.direction is None
    assert unavailable.compatibility_gender is None
    assert unavailable.unavailability_reason
    assert compatibility_variant_mode(unavailable) == VariantMode.NOT_APPLICABLE


class CalendarEngineProvider:
    def __init__(self) -> None:
        self.calls: list[datetime] = []
        self.engine = CalendarEngine()

    def snapshot(self, when: datetime):
        self.calls.append(when)
        return self.engine.snapshot(when)


@pytest.mark.parametrize(
    ("moment", "expected_day", "expected_hour"),
    [
        (datetime(2024, 11, 15, 9, 30), "癸未", "巳"),
        (datetime(2024, 11, 15, 15, 0), "癸未", "申"),
        (datetime(2024, 11, 15, 22, 59), "癸未", "亥"),
        (datetime(2024, 11, 15, 23, 0), "甲申", "子"),
        (datetime(2024, 11, 15, 23, 1), "甲申", "子"),
    ],
)
def test_exact_datetime_is_preserved_through_calendar_boundaries(
    moment, expected_day, expected_hour
) -> None:
    provider = CalendarEngineProvider()
    aware = moment.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    result = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.EXACT_DATETIME,
            target_datetime=aware,
        ),
        provider,
    )
    assert result.status == FortuneTemporalResolutionStatus.RESOLVED
    assert result.context is not None
    assert result.context.temporal_resolution == FortuneTemporalResolutionMethod.EXACT_DATETIME
    assert result.context.target_at == aware
    assert result.context.calendar_snapshot.day_ganzhi.text == expected_day
    assert result.context.calendar_snapshot.hour_ganzhi.branch == expected_hour


def test_market_session_date_uses_versioned_open_and_is_not_exact() -> None:
    provider = CalendarEngineProvider()
    result = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
            target_date=date(2024, 11, 15),
            exchange=Exchange.SSE,
            is_trading_day=True,
        ),
        provider,
        market_session_version="a-share-session-v1",
        config_version="v1",
    )
    assert result.status == FortuneTemporalResolutionStatus.RESOLVED
    assert result.context is not None
    assert result.context.target_at == datetime(
        2024, 11, 15, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert result.context.temporal_resolution == FortuneTemporalResolutionMethod.MARKET_SESSION_INFERRED
    assert result.context.market_session_version == (
        "fortune-market-session-anchor-v1:a-share-session-v1:v1"
    )
    assert len(result.context.assumptions) == 2


def test_civil_date_only_requires_time_without_calling_calendar() -> None:
    provider = CalendarEngineProvider()
    result = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.CIVIL_DATE_ONLY,
            target_date=date(2026, 9, 25),
        ),
        provider,
    )
    assert result.status == FortuneTemporalResolutionStatus.TIME_REQUIRED
    assert result.context is None
    assert provider.calls == []


def test_market_date_rejects_missing_or_conflicting_trading_day_evidence() -> None:
    provider = CalendarEngineProvider()
    missing = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
            target_date=date(2024, 11, 15),
            exchange=Exchange.SSE,
        ),
        provider,
    )
    weekend = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
            target_date=date(2024, 11, 16),
            exchange=Exchange.SSE,
            is_trading_day=True,
        ),
        provider,
    )
    closed = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
            target_date=date(2024, 11, 15),
            exchange=Exchange.SSE,
            is_trading_day=False,
        ),
        provider,
    )
    no_version = resolve_temporal_input(
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
            target_date=date(2024, 11, 15),
            exchange=Exchange.SSE,
            is_trading_day=True,
        ),
        provider,
        market_session_version="a-share-session-v1",
    )
    assert missing.status == FortuneTemporalResolutionStatus.TIME_REQUIRED
    assert weekend.status == FortuneTemporalResolutionStatus.UNAVAILABLE
    assert closed.status == FortuneTemporalResolutionStatus.NON_TRADING_DAY
    assert no_version.status == FortuneTemporalResolutionStatus.UNAVAILABLE
    assert provider.calls == []


def test_temporal_inputs_reject_naive_and_date_cast_to_datetime() -> None:
    with pytest.raises(ValidationError, match="必须带时区"):
        FortuneTemporalInput(
            kind=FortuneTemporalInputKind.EXACT_DATETIME,
            target_datetime=datetime(2024, 11, 15, 9, 30),
        )
    with pytest.raises(ValidationError, match="date-only 不得传入 target_datetime"):
        FortuneTemporalInput.model_validate(
            {
                "kind": "EXACT_DATETIME",
                "target_datetime": "2024-11-15",
            }
        )


def test_existing_date_scan_anchor_remains_noon() -> None:
    from src.core.schemas.relation import EVALUATION_TIME

    assert EVALUATION_TIME == "12:00:00"
