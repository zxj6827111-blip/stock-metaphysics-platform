"""F4 Golden：精确节气流月、23:00 日界与正式交易日历边界。"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.core.orchestration.stock_fortune import StockFortuneEngine
from src.core.orchestration.stock_fortune_timeline import StockFortuneTimelineEngine
from src.core.schemas.common import Exchange, SourceRef
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservationResolution,
    FortuneBirthBasis,
    FortuneTimelineDateMode,
    StockFortuneBirthProfile,
    StockFortuneIdentity,
    StockFortuneTimelineRequest,
)
from src.core.stock.trading_calendar import KNOWN_SOURCES, get_trading_calendar_provider
from src.engines.calendar.calendar_engine import CalendarEngine

pytestmark = pytest.mark.golden

SHANGHAI = ZoneInfo("Asia/Shanghai")


class MemoryArtifactWriter:
    """Golden 使用确定性内存 ID；生产 API 使用数据库 artifact writer。"""

    def persist_chart_artifact(self, **kwargs) -> str:
        return f"{kwargs['engine_id']}:{kwargs['symbol']}:{kwargs['as_of'].isoformat()}"


def _request(
    start: date,
    end: date,
    *,
    evaluation_time: time = time(12, 0),
    date_mode: FortuneTimelineDateMode = FortuneTimelineDateMode.ALL_CALENDAR_DAYS,
) -> StockFortuneTimelineRequest:
    birth_at = datetime(2001, 8, 27, 9, 30, tzinfo=SHANGHAI)
    profile = StockFortuneBirthProfile(
        symbol="600519",
        exchange=Exchange.SSE,
        first_trade_date=birth_at.date(),
        first_trade_datetime=birth_at,
        first_trade_resolution=FirstTradeObservationResolution.TRADE,
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        birth_datetime=birth_at,
        timezone="Asia/Shanghai",
        birth_time_precision=BirthTimePrecision.EXACT,
        source=SourceRef(source="golden-realistic-profile"),
        source_version="golden-profile-v1",
        birth_profile_version="stock-fortune-birth-v2",
        market_session_version="a-share-session-v1",
        config_version="golden-config-v1",
    )
    return StockFortuneTimelineRequest(
        stock_identity=StockFortuneIdentity(
            symbol="600519",
            exchange=Exchange.SSE,
            name="贵州茅台",
            source=SourceRef(source="golden-stock-master"),
        ),
        birth_profile=profile,
        start_date=start,
        end_date=end,
        date_mode=date_mode,
        evaluation_time=evaluation_time,
        include_ten_god_index=False,
    )


def _engine() -> tuple[StockFortuneTimelineEngine, CalendarEngine]:
    calendar = CalendarEngine()
    return StockFortuneTimelineEngine(StockFortuneEngine(MemoryArtifactWriter(), calendar=calendar)), calendar


def test_month_segment_uses_exact_jieqi_inside_one_gregorian_month() -> None:
    timeline_engine, calendar = _engine()
    anchor = date(2026, 1, 1)
    prior_day = anchor
    prior_month = calendar.snapshot(datetime.combine(prior_day, time(12))).month_ganzhi.text
    boundary_day: date | None = None
    for offset in range(1, 366):
        current_day = date.fromordinal(anchor.toordinal() + offset)
        current_month = calendar.snapshot(datetime.combine(current_day, time(12))).month_ganzhi.text
        if current_day.month == prior_day.month and current_month != prior_month:
            boundary_day = current_day
            break
        prior_day, prior_month = current_day, current_month

    assert boundary_day is not None, "CalendarEngine 未在搜索年内给出公历月中流月切换"
    timeline = timeline_engine.build(
        _request(boundary_day.fromordinal(boundary_day.toordinal() - 1), boundary_day)
    )

    expected = {
        current: calendar.snapshot(datetime.combine(current, time(12))).month_ganzhi.text
        for current in (date.fromordinal(boundary_day.toordinal() - 1), boundary_day)
    }
    actual = {point.date: point.monthly_pillar.text for point in timeline.points}
    assert actual == expected
    assert actual[date.fromordinal(boundary_day.toordinal() - 1)] != actual[boundary_day]
    segments = [
        item for item in timeline.month_segments
        if item.effective_dates and item.effective_dates[0].month == boundary_day.month
    ]
    assert len(segments) == 2
    assert {item.monthly_pillar.text for item in segments} == set(expected.values())
    assert all(item.start_at.tzinfo is not None and item.end_at.tzinfo is not None for item in segments)


def test_timeline_preserves_calendar_engine_2300_day_boundary() -> None:
    timeline_engine, calendar = _engine()
    target = date(2025, 1, 10)
    readings = {}
    for evaluation_time in (time(22, 59), time(23, 0), time(23, 1)):
        expected = calendar.snapshot(datetime.combine(target, evaluation_time)).day_ganzhi.text
        timeline = timeline_engine.build(
            _request(target, target, evaluation_time=evaluation_time)
        )
        assert len(timeline.points) == 1
        readings[evaluation_time] = timeline.points[0].daily_pillar.text
        assert readings[evaluation_time] == expected

    assert readings[time(22, 59)] != readings[time(23, 0)]
    assert readings[time(23, 0)] == readings[time(23, 1)]


def test_verified_exchange_calendar_marks_known_holiday_closed() -> None:
    calendar = get_trading_calendar_provider().for_exchange("SSE")
    holiday = date(2025, 10, 1)
    query = calendar.is_trading_day(holiday)

    assert query.source in KNOWN_SOURCES
    assert query.value is False
    timeline_engine, _ = _engine()
    timeline = timeline_engine.build(
        _request(
            holiday,
            holiday,
            date_mode=FortuneTimelineDateMode.TRADING_DAYS_ONLY,
        )
    )
    assert timeline.points == []
    assert timeline.trading_calendar.confirmed_closed_days == 1
    assert timeline.trading_calendar.unknown_days == 0
