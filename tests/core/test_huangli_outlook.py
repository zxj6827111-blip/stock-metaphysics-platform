"""未来交易日黄历（outlook）的边界测试。

这一批测试针对的是最容易"看起来对、其实在猜"的地方：

* 跨周末 / 长假 —— 日期卡里不能出现非交易日；
* 基准日不是交易日 —— 必须从其后首个交易日开始，且规则写清楚；
* 交易日历覆盖不足 —— **只返回覆盖到的天数**，明确说明原因，
  绝不补造日期、绝不填零、绝不假装休市。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.core.orchestration.huangli_outlook import (
    MAX_TRADING_DAYS,
    build_huangli_outlook,
)
from src.engines.huangli.huangli_engine import HuangliEngine


@pytest.fixture()
def engine() -> HuangliEngine:
    return HuangliEngine()


def _dates(out: dict) -> list[str]:
    return [d["date"] for d in out["days"]]


def test_twenty_trading_days_skip_weekends_and_holidays(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 15, 15), exchange="SSE",
        mode="trading_days", days=20, engine=engine,
    )
    assert out["returned_days"] == 20
    assert out["anchor_is_trading_day"] is True
    dates = [date.fromisoformat(d) for d in _dates(out)]
    # 首日就是基准日（基准日是交易日）
    assert dates[0] == date(2024, 11, 15)
    # 没有任何周末
    assert all(d.weekday() < 5 for d in dates)
    # 2024-11-16/17 是周末，必须缺席（而不是被当成交易日）
    assert date(2024, 11, 16) not in dates
    assert date(2024, 11, 17) not in dates
    # 严格递增且互不重复
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)


def test_long_holiday_is_excluded_not_invented(engine):
    """2025 春节长假（1/28–2/4 休市）不能出现在日期卡里。"""
    out = build_huangli_outlook(
        as_of=datetime(2025, 1, 20, 15), exchange="SSE",
        mode="months", months=1, engine=engine,
    )
    dates = [date.fromisoformat(d) for d in _dates(out)]
    assert dates, "应有交易日"
    spring_festival = [
        d for d in dates
        if date(2025, 1, 29) <= d <= date(2025, 2, 4)
    ]
    assert spring_festival == [], f"长假休市日被当成交易日：{spring_festival}"


def test_anchor_on_non_trading_day_starts_from_next_session(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 16, 15), exchange="SSE",  # 周六
        mode="trading_days", days=3, engine=engine,
    )
    assert out["anchor_is_trading_day"] is False
    assert _dates(out) == ["2024-11-18", "2024-11-19", "2024-11-20"]
    assert "基准日不是交易日" in out["rule_cn"]


def test_calendar_out_of_coverage_returns_nothing_and_explains(engine):
    """基准日越过实测日历末尾：返回 0 天 + 明确原因，不猜测。"""
    out = build_huangli_outlook(
        as_of=datetime(2099, 1, 5, 15), exchange="SSE",
        mode="trading_days", days=20, engine=engine,
    )
    assert out["returned_days"] == 0
    assert out["days"] == []
    assert out["coverage"]["status"] == "unavailable"
    assert out["coverage"]["calendar_loaded"] is True
    assert out["coverage"]["calendar_coverage"] is not None
    assert "覆盖" in out["coverage"]["explanation_cn"]
    assert any(w["code"] == "HUANGLI_OUTLOOK_CALENDAR_UNAVAILABLE" for w in out["warnings"])
    # 绝不能用"排除周末"兜底
    assert "周末规则" not in out["coverage"]["explanation_cn"]


def test_partial_coverage_stops_at_calendar_boundary(engine):
    """请求的天数越过日历边界时，只返回边界之前的交易日并标注 partial。"""
    coverage_end = date(2026, 9, 18)
    anchor = coverage_end - timedelta(days=3)
    out = build_huangli_outlook(
        as_of=datetime(anchor.year, anchor.month, anchor.day, 15), exchange="SSE",
        mode="trading_days", days=20, engine=engine,
    )
    assert out["coverage"]["status"] == "partial"
    assert 0 < out["returned_days"] < 20
    assert out["coverage"]["unknown_days"] >= 1
    assert out["coverage"]["first_unknown_date"] is not None
    assert all(date.fromisoformat(d) <= coverage_end for d in _dates(out))
    assert any(w["code"] == "HUANGLI_OUTLOOK_CALENDAR_PARTIAL" for w in out["warnings"])


def test_today_mode_keeps_non_trading_anchor_and_labels_it(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 16, 15), exchange="SSE",
        mode="today", engine=engine,
    )
    assert _dates(out) == ["2024-11-16"]
    assert out["anchor_is_trading_day"] is False
    assert out["days"][0]["is_trading_day"] is True  # 字段含义是"这张卡来自按日取黄历"


def test_months_mode_groups_by_calendar_month(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 15, 15), exchange="SSE",
        mode="months", months=3, engine=engine,
    )
    groups = out["month_groups"]
    assert [g["month"] for g in groups] == ["2024-11", "2024-12", "2025-01"]
    # 分组里的日期必须与 days 完全一致（没有孤儿日期）
    flattened = [d for g in groups for d in g["dates"]]
    assert flattened == _dates(out)
    assert out["returned_days"] == len(flattened)
    assert len(flattened) <= MAX_TRADING_DAYS


def test_days_limit_is_clamped(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 15, 15), exchange="SSE",
        mode="trading_days", days=10_000, engine=engine,
    )
    assert out["requested_days"] == MAX_TRADING_DAYS
    assert out["returned_days"] <= MAX_TRADING_DAYS


def test_unknown_exchange_degrades_explicitly(engine):
    """没有实测日历的交易所必须显式降级，不得静默用周末规则。"""
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 15, 15), exchange="BSE",
        mode="trading_days", days=5, engine=engine,
    )
    assert out["coverage"]["status"] == "unavailable"
    assert out["coverage"]["calendar_loaded"] is False
    assert out["returned_days"] == 0
    assert "BSE" in out["coverage"]["explanation_cn"]


def test_every_card_carries_class_and_traceable_basis(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 15, 15), exchange="SSE",
        mode="trading_days", days=20, engine=engine,
    )
    for card in out["days"]:
        assert card["class_code"] in (None, "auspicious", "inauspicious")
        assert card["class_label_cn"] in (None, "吉", "凶")
        assert card["class_basis_cn"]
        assert card["is_trading_day"] is True
        assert "is_trading_day" in card
    # 20 天里两种类别都出现（十二神黄黑道交替，不可能只有一种）
    labels = {c["class_label_cn"] for c in out["days"]}
    assert labels == {"吉", "凶"}


def test_class_rule_is_published_with_the_outlook(engine):
    out = build_huangli_outlook(
        as_of=datetime(2024, 11, 15, 15), exchange="SSE", engine=engine,
    )
    rule = out["class_rule"]
    assert rule["third_category_supported"] is False
    assert [c["label_cn"] for c in rule["categories"]] == ["吉", "凶"]
    assert out["engine_version"]
    assert out["methodology_cn"]


def test_unknown_mode_rejected(engine):
    with pytest.raises(ValueError):
        build_huangli_outlook(
            as_of=datetime(2024, 11, 15, 15), exchange="SSE",
            mode="weekly", engine=engine,
        )
