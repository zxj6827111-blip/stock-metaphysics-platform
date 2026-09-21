"""时间窗口批量求值 vs 逐日求值的等价性。

``TimelineBuilder.evaluate_days`` 是性能优化（批量黄历切片 + 批量紫微），
**不允许改变任何分数**。这个测试把两条路径对同一批交易日的结果逐字段比对：

* 三个引擎的 direction / score / availability；
* 因子集的 rule_score / normalized_value（共识与冲突都读它）。

如果哪天有人"顺手"在批量路径里调整了某个引擎的参与方式，这里会立刻红。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.core.orchestration.timeline import TimelineBuilder
from src.core.schemas.common import VariantMode

BIRTH = datetime(2001, 8, 27, 9, 30)
TARGETS = [date(2024, 11, 18), date(2024, 11, 21), date(2024, 12, 2), date(2024, 12, 13)]


@pytest.fixture(scope="module")
def builder() -> TimelineBuilder:
    return TimelineBuilder()


def _naive(builder: TimelineBuilder, day: date):
    return builder._score_at(
        stock_code="600519",
        as_of=datetime(day.year, day.month, day.day, 15, 0, 0),
        variant_mode=VariantMode.FORWARD,
        birth_datetime=BIRTH,
    )


def test_opinions_identical_between_batch_and_per_day(builder):
    batch, warnings = builder.evaluate_days(
        stock_code="600519", target_days=TARGETS,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    assert set(batch) == set(TARGETS)
    for day in TARGETS:
        naive_opinions, _fset, _w = _naive(builder, day)
        got = batch[day].opinions
        assert set(got) == set(naive_opinions), f"{day} 引擎集合不同"
        for engine in naive_opinions:
            a, b = got[engine], naive_opinions[engine]
            assert a.engine == b.engine, f"{day}/{engine} engine"
            assert a.availability == b.availability, f"{day}/{engine} availability"
            assert a.direction == b.direction, f"{day}/{engine} direction"
            assert a.score == b.score, f"{day}/{engine} score {a.score} != {b.score}"
            assert a.confidence == b.confidence, f"{day}/{engine} confidence"
    assert isinstance(warnings, list)


def test_factor_set_identical_between_batch_and_per_day(builder):
    batch, _w = builder.evaluate_days(
        stock_code="600519", target_days=TARGETS,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    for day in TARGETS:
        _opinions, naive_set, _w = _naive(builder, day)
        got_set = batch[day].factor_set
        got_map = {o.factor_id: o for o in got_set.observations}
        naive_map = {o.factor_id: o for o in naive_set.observations}
        assert set(got_map) == set(naive_map), f"{day} 因子集合不同"
        for fid, naive_obs in naive_map.items():
            got_obs = got_map[fid]
            assert got_obs.normalized_value == naive_obs.normalized_value, f"{day}/{fid} normalized"
            assert got_obs.rule_score == naive_obs.rule_score, f"{day}/{fid} rule_score"
            assert got_obs.direction == naive_obs.direction, f"{day}/{fid} direction"
            assert got_obs.availability == naive_obs.availability, f"{day}/{fid} availability"


def test_month_and_week_windows_use_the_same_numbers(builder):
    """月/周窗口改走批量路径后，逐日结果仍必须与批量路径一致。"""
    weeks, _w = builder.build_weeks(
        stock_code="600519", as_of=datetime(2024, 11, 15, 15), weeks=2,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    days = [d.trade_date for w in weeks for d in w.daily_results]
    assert days, "周度窗口应产出逐日结果"
    batch, _w2 = builder.evaluate_days(
        stock_code="600519", target_days=days,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    for week in weeks:
        for day_result in week.daily_results:
            opinions = batch[day_result.trade_date].opinions

            def score(name: str):
                o = opinions.get(name)
                # availability 在模型里序列化为字符串（"ok" / "unavailable"）
                if o is None or str(o.availability) != "ok":
                    return None
                return o.score

            assert day_result.bazi_score == score("bazi")
            assert day_result.ziwei_score == score("ziwei")
            assert day_result.huangli_score == score("huangli")


def test_build_days_respects_trading_calendar_and_limit(builder):
    day_results, warnings = builder.build_days(
        stock_code="600519", as_of=datetime(2024, 11, 15, 15), days=20,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    assert len(day_results) == 20
    assert all(d.is_trading_day for d in day_results)
    assert all(d.trade_date.weekday() < 5 for d in day_results)
    dates = [d.trade_date for d in day_results]
    assert dates == sorted(dates)
    # as_of 之后（不含 as_of 当日）
    assert dates[0] == date(2024, 11, 18)
    # 缺失的模型必须 score=None（不填 0）
    for d in day_results:
        assert d.bazi_score is None or d.bazi_score > 0
    assert isinstance(warnings, list)


def test_build_days_reports_calendar_shortfall(builder):
    """越过**全部可用**日历覆盖时返回实际天数并给出 warning，而不是补造日期。

    边界已随"官方已公布日历"轮次从实测末日（2026-09-21）推进到
    官方公布末日（2026-12-31）：实测层只能到过去，"没有未来行情"不等于
    "无法确定未来交易日"。因此这里从 2026-12-20 起请求 20 天 ——
    必须先跨过公布边界，短少才算真实短少。
    """
    day_results, warnings = builder.build_days(
        stock_code="600519", as_of=datetime(2026, 12, 20, 15), days=20,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    assert len(day_results) < 20
    codes = {w.code for w in warnings}
    assert "TIMELINE_DAILY_PARTIAL" in codes or "TIMELINE_NO_TRADING_DAY" in codes
    # 越过边界后一律不产出日期，也不补造
    assert all(d.trade_date <= date(2026, 12, 31) for d in day_results)


def test_build_days_uses_published_calendar_beyond_observed_end(builder):
    """实测成交日历之后、官方已公布范围内的交易日必须能查出来。

    这条断言锁的是本轮修复的核心：以前 as_of 落在实测末日附近，
    "未来 20 个交易日"只返回一两天就报 partial；现在应补足到官方公布范围内。
    """
    day_results, warnings = builder.build_days(
        stock_code="600519", as_of=datetime(2026, 9, 21, 15), days=20,
        variant_mode=VariantMode.FORWARD, birth_datetime=BIRTH,
    )
    assert len(day_results) == 20, "官方已公布范围内应能取满 20 个交易日"
    dates = [d.trade_date for d in day_results]
    # 中秋（09-25 起）与国庆长假（10-01~10-07）不能出现在交易日列表里
    assert not any(date(2026, 10, 1) <= d <= date(2026, 10, 7) for d in dates)
    assert date(2026, 9, 25) not in dates
    # 节后首个交易日必须在
    assert date(2026, 10, 8) in dates
    assert "TIMELINE_DAILY_PARTIAL" not in {w.code for w in warnings}
