from __future__ import annotations

from datetime import date

from src.core.stock.trading_calendar import TradingCalendar
from src.research.labels.research_date import resolve_research_date


class _Provider:
    def __init__(self, calendars):
        self.calendars = calendars

    def for_exchange(self, exchange):
        return self.calendars[exchange]


def test_non_trading_anchor_returns_auditable_verified_shift():
    days = {date(2024, 1, 1), date(2024, 1, 3)}
    calendar = TradingCalendar(exchange="SSE", _days=frozenset(days), loaded=True)
    resolution = resolve_research_date(
        date(2024, 1, 2), "SSE", provider=_Provider({"SSE": calendar}),
    )
    assert resolution.available
    assert resolution.status == "SHIFTED"
    assert resolution.requested_date == date(2024, 1, 2)
    assert resolution.research_date == date(2024, 1, 3)
    assert resolution.source == "observed_index_days"
    assert resolution.calendar_version


def test_unknown_exchange_weekday_fallback_is_unavailable():
    calendar = TradingCalendar(exchange="BSE", loaded=False, load_error="no mapping")
    resolution = resolve_research_date(
        date(2024, 1, 2), "BSE", provider=_Provider({"BSE": calendar}),
    )
    assert not resolution.available
    assert resolution.status == "UNAVAILABLE"
    assert resolution.research_date is None
    assert resolution.source == "weekend_rule_fallback"
