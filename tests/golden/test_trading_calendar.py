"""交易日历 Golden Cases（P0-4）—— 用真实导入数据断言历法正确性。

断言的事实全部来自已公开的历史交易日记录：

* 春节 2024：02-09（除夕周五）~ 02-17 休市，02-19（周一）开市；
* 疫情延期：2020-01-23 ~ 2020-02-02 休市，2020-02-03 开市；
* 国庆 2024：10-01 ~ 10-07 休市，10-08 开市；
* 2023 国庆：09-29 ~ 10-06 休市，10-09 开市；
* 普通周末：非交易日；
* 25 年前的老股票（如 000001）在 1990 年代也有实测日历。

只要能读到 data/import/calendar/*.csv，这些断言就锁定真实交易所的休市记录；
日历文件缺失时测试**明确失败**（不错误地静默降级为"周末规则通过"）。
"""

from __future__ import annotations

from datetime import date

import pytest

from src.core.stock.trading_calendar import TradingCalendarProvider

pytestmark = pytest.mark.golden


@pytest.fixture(scope="module")
def provider():
    return TradingCalendarProvider()


class TestKnownHolidays:
    @pytest.mark.parametrize("ex,d", [
        ("SSE", date(2024, 2, 9)),   # 除夕
        ("SSE", date(2024, 2, 12)),  # 初三
        ("SSE", date(2024, 2, 16)),  # 初七
        ("SSE", date(2024, 10, 1)),  # 国庆
        ("SSE", date(2024, 10, 7)),
        ("SSE", date(2020, 1, 31)),  # 疫情延长休市期间
        ("SZSE", date(2024, 2, 9)),
        ("SZSE", date(2024, 10, 1)),
        ("SSE", date(2020, 1, 31)),
        ("SSE", date(2023, 9, 29)),  # 2023 中秋国庆
        ("SSE", date(2023, 10, 6)),
    ])
    def test_market_closed(self, provider, ex, d):
        cal = provider.for_exchange(ex)
        assert cal.loaded, f"{ex} 日历文件未加载"
        q = cal.is_trading_day(d)
        assert q.value is False, f"{ex} {d} 应为非交易日，实际={q.value}"

    @pytest.mark.parametrize("ex,d", [
        ("SSE", date(2024, 2, 8)),   # 除夕前最后交易日
        ("SSE", date(2024, 2, 19)),  # 节后首日
        ("SSE", date(2024, 9, 30)),  # 国庆前最后交易日（当日大涨，必然开市）
        ("SSE", date(2020, 1, 23)),  # 春节前最后交易日（1-27 才宣布延长休市）
        ("SSE", date(2024, 10, 8)),  # 国庆后首日
        ("SSE", date(2020, 2, 3)),   # 疫情后首日（真实大跌日）
        ("SSE", date(2023, 10, 9)),  # 2023 国庆后首日
        ("SZSE", date(2024, 2, 19)),
        ("SZSE", date(2024, 10, 8)),
    ])
    def test_market_open(self, provider, ex, d):
        cal = provider.for_exchange(ex)
        assert cal.loaded
        q = cal.is_trading_day(d)
        assert q.value is True, f"{ex} {d} 应为交易日，实际={q.value}（{q.degraded_reason}）"

    @pytest.mark.parametrize("d", [
        date(2024, 9, 28),   # 周六
        date(2024, 9, 29),   # 周日
        date(2025, 1, 4),   # 周六
        date(2025, 1, 5),   # 周日
    ])
    def test_weekend_not_trading(self, provider, d):
        assert provider.for_exchange("SSE").is_trading_day(d).value is False


class TestNextTradingDay:
    """出生档案对齐依赖的关键行为：上市日落在节假日时顺延到首个交易日。"""

    @pytest.mark.parametrize("listing,expected", [
        (date(2024, 10, 1), date(2024, 10, 8)),   # 国庆 → 节后首日
        (date(2024, 2, 10), date(2024, 2, 19)),   # 春节假期中 → 节后首日
        (date(2020, 1, 24), date(2020, 2, 3)),    # 疫情休市起点 → 2 月 3 日开市
        (date(2024, 9, 28), date(2024, 9, 30)),   # 周六 → 周一
        (date(2024, 9, 30), date(2024, 9, 30)),   # 本身是交易日 → 不动
        (date(2023, 10, 1), date(2023, 10, 9)),   # 2023 国庆
    ])
    def test_next_trading_day(self, provider, listing, expected):
        cal = provider.for_exchange("SSE")
        q = cal.next_trading_day(listing)
        assert q.value == expected, (
            f"上市日 {listing} 顺延结果 {q.value} != {expected}（{q.degraded_reason}）"
        )
        assert q.source == "observed_index_days"


class TestAddTradingDays:
    def test_add_5_trading_days(self, provider):
        cal = provider.for_exchange("SSE")
        # 语义：先对齐 d 到当日/下个交易日，再推进 n 个完整交易日。
        # 2024-02-08（春节前末个交易日）+5: →19,20,21,22,23（2-18 周日不开市）
        q = cal.add_trading_days(date(2024, 2, 8), 5)
        assert q.value == date(2024, 2, 23), f"实际 {q.value}"

    def test_add_zero_days_is_identity(self, provider):
        cal = provider.for_exchange("SSE")
        assert cal.add_trading_days(date(2024, 9, 30), 0).value == date(2024, 9, 30)

    def test_add_trading_days_only_counts_sessions(self, provider):
        cal = provider.for_exchange("SSE")
        # 2024-10-01 对齐 → 10-08（国庆后首日）；再 +1 → 10-09
        q = cal.add_trading_days(date(2024, 10, 1), 1)
        assert q.value == date(2024, 10, 9)


class TestCoverageAndHonesty:
    def test_coverage_starts_1990(self, provider):
        cal = provider.for_exchange("SSE")
        assert cal.loaded
        first, last = cal.coverage or (None, None)
        assert first is not None and first <= date(1990, 12, 19)
        assert last is not None and last >= date(2026, 1, 1)

    def test_deep_history_known_days(self, provider):
        """深历史已知交易日：浦发银行上市日 1999-11-10（SSE 实测）。"""
        cal = provider.for_exchange("SSE")
        assert cal.is_trading_day(date(1999, 11, 10)).value is True
        # SZSE 深证成指实测数据自 1993-01-03 起（以行情端实际覆盖为准）；
        # 起点之前的日期必须回答"未知"，禁止瞎猜。
        szse = provider.for_exchange("SZSE")
        assert szse.is_trading_day(date(1993, 1, 4)).value is True
        assert szse.is_trading_day(date(1991, 4, 3)).value is None

    def test_out_of_coverage_returns_unknown_not_weekend_lie(self, provider):
        """超出覆盖范围必须返回"未知"，禁止用周末规则伪装确定结论。"""
        cal = provider.for_exchange("SSE")
        _first, last = cal.coverage or (date(1990, 1, 1), date(1990, 1, 1))
        beyond = date(last.year + 2, 1, 6)  # 覆盖末端两年后的工作日
        if beyond.weekday() < 5:
            q = cal.is_trading_day(beyond)
            assert q.value is None and q.source == "out_of_coverage"

    def test_unknown_exchange_degrades_honestly(self, provider):
        cal = provider.for_exchange("BSE")
        # BSE 未接入实测日历 → 必须明确降级，不得假装已知
        q = cal.is_trading_day(date(2024, 10, 9))
        assert q.degraded_reason or q.source == "weekend_rule_fallback"
