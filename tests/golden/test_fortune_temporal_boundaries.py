from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.fortune.market_sessions import AShareMarketSessionAdapter
from src.core.schemas.common import Exchange
from src.core.schemas.fortune import MarketSessionStatus
from src.engines.calendar.calendar_engine import CalendarEngine

pytestmark = pytest.mark.golden


def test_flow_year_changes_at_exact_lichun_minute() -> None:
    engine = CalendarEngine()
    probe = engine.snapshot(datetime(2024, 2, 4, 0, 0))
    assert probe.jieqi.next_name == "立春"
    boundary = probe.jieqi.next_at
    assert boundary is not None

    before = engine.snapshot(boundary - timedelta(minutes=1))
    exact = engine.snapshot(boundary)
    after = engine.snapshot(boundary + timedelta(minutes=1))
    assert before.year_ganzhi.text == "癸卯"
    assert exact.year_ganzhi.text == "甲辰"
    assert after.year_ganzhi.text == "甲辰"


def test_flow_month_changes_at_exact_jieqi_minute() -> None:
    engine = CalendarEngine()
    probe = engine.snapshot(datetime(2024, 3, 5, 0, 0))
    assert probe.jieqi.next_name == "惊蛰"
    boundary = probe.jieqi.next_at
    assert boundary is not None

    before = engine.snapshot(boundary - timedelta(minutes=1))
    exact = engine.snapshot(boundary)
    after = engine.snapshot(boundary + timedelta(minutes=1))
    assert before.month_ganzhi.text == "丙寅"
    assert exact.month_ganzhi.text == "丁卯"
    assert after.month_ganzhi.text == "丁卯"


@pytest.mark.parametrize(
    ("moment", "day_ganzhi", "hour_branch"),
    [
        (datetime(2024, 11, 15, 22, 59), "癸未", "亥"),
        (datetime(2024, 11, 15, 23, 0), "甲申", "子"),
        (datetime(2024, 11, 15, 23, 1), "甲申", "子"),
        (datetime(2024, 11, 16, 0, 0), "甲申", "子"),
    ],
)
def test_current_calendar_engine_late_zi_day_boundary(moment, day_ganzhi, hour_branch) -> None:
    snapshot = CalendarEngine().snapshot(moment)
    assert snapshot.day_ganzhi.text == day_ganzhi
    assert snapshot.hour_ganzhi.branch == hour_branch


FLOW_HOUR_AND_SESSION_GOLDEN = [
    # A 股日期、当地时间、十二时辰地支、market status、tradable
    (datetime(2024, 11, 15, 9, 30), "巳", MarketSessionStatus.CONTINUOUS_TRADING, True, True),
    (datetime(2024, 11, 15, 10, 59), "巳", MarketSessionStatus.CONTINUOUS_TRADING, True, True),
    (datetime(2024, 11, 15, 11, 0), "午", MarketSessionStatus.CONTINUOUS_TRADING, True, True),
    (datetime(2024, 11, 15, 11, 30), "午", MarketSessionStatus.BREAK, False, True),
    (datetime(2024, 11, 15, 12, 0), "午", MarketSessionStatus.BREAK, False, True),
    (datetime(2024, 11, 15, 13, 0), "未", MarketSessionStatus.CONTINUOUS_TRADING, True, True),
    (datetime(2024, 11, 15, 14, 59), "未", MarketSessionStatus.CONTINUOUS_TRADING, True, True),
    (datetime(2024, 11, 15, 15, 0), "申", MarketSessionStatus.CLOSED, False, True),
    (datetime(2024, 11, 16, 10, 0), "巳", MarketSessionStatus.CLOSED, False, None),
    (datetime(2024, 11, 18, 10, 0), "巳", MarketSessionStatus.CLOSED, False, False),
]


@pytest.mark.parametrize("moment,branch,status,tradable,day_state", FLOW_HOUR_AND_SESSION_GOLDEN)
def test_traditional_flow_hour_and_market_session_are_independent(
    moment, branch, status, tradable, day_state
) -> None:
    local = moment.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    calendar = CalendarEngine().snapshot(moment)
    market = AShareMarketSessionAdapter().classify(
        local, Exchange.SSE, is_trading_day=day_state
    )

    assert calendar.hour_ganzhi.branch == branch
    assert market.status == status
    assert market.tradable is tradable
