"""时间窗口测试（Phase 2D）。

四条纪律（本文件的核心断言）
--------------------------
1. **禁止发明"流周"**：周必须由交易日的流日结果聚合，且带 ``aggregation_version``。
2. **一切基于实际交易日**：月/周窗口不得退回自然日；日历越界时如实降级。
3. **窗口不是一个综合数字**：每个月独立携带三模型观点 + 共识。
4. **聚合不给单一平均值**：mean / median / min / max / positive_day_ratio /
   weighted_mean 必须同时给出。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.core.orchestration.timeline import (
    TRADING_DAYS_PER_WEEK,
    TimelineBuilder,
    _weighted_mean,
    build_time_windows,
)
from src.core.schemas.common import Availability, EngineId, VariantMode
from src.core.schemas.timeline import AGGREGATION_VERSION, DayResult
from src.engines.base import EngineContext
from src.engines.ziwei.ziwei_engine import ZiweiEngine

AS_OF = datetime(2024, 11, 15, 14, 32)
BIRTH = datetime(2001, 8, 27, 9, 30)


def _ziwei_available() -> bool:
    return ZiweiEngine().availability == Availability.OK


requires_ziwei = pytest.mark.skipif(
    not _ziwei_available(), reason="本机缺少紫微服务（node + services/ziwei-service）",
)


# ---------------------------------------------------------------------------
# 1. 交易日基础
# ---------------------------------------------------------------------------


class TestTradingDayBasis:
    builder = TimelineBuilder()

    def test_weekends_are_not_trading_days(self):
        # 2024-11-16 是周六、11-17 是周日
        assert self.builder._is_trading_day(date(2024, 11, 16), "SSE") is False
        assert self.builder._is_trading_day(date(2024, 11, 17), "SSE") is False
        assert self.builder._is_trading_day(date(2024, 11, 15), "SSE") is True

    def test_holidays_are_excluded(self):
        """农历新年等节假日必须被剔除（实测日历，不是周末规则）。"""
        # 2024 春节假期
        for d in (date(2024, 2, 12), date(2024, 2, 13), date(2024, 2, 14),
                  date(2024, 2, 15), date(2024, 2, 16)):
            assert self.builder._is_trading_day(d, "SSE") is False, d
        assert self.builder._is_trading_day(date(2024, 2, 19), "SSE") is True

    def test_out_of_coverage_returns_unknown_not_guess(self):
        """日历覆盖之外的日期必须返回 None（不知道），**不能**用周末规则假装肯定。"""
        far = date(2099, 6, 15)  # 2099-06-15 是周一，但没有实测日历
        assert self.builder._is_trading_day(far, "SSE") is None

    def test_trading_days_in_range_are_all_real_trading_days(self):
        days, warnings = self.builder.trading_days_in(
            date(2024, 12, 1), date(2024, 12, 31), "SSE")
        assert all(d.weekday() < 5 for d in days)
        assert len(days) == 22, f"2024 年 12 月交易日应为 22 个，实际 {len(days)}"
        assert not warnings


# ---------------------------------------------------------------------------
# 2. 月度窗口
# ---------------------------------------------------------------------------


@requires_ziwei
class TestMonthWindows:
    def test_twelve_months_each_independent(self):
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=12, weeks=0, variant_mode=VariantMode.FORWARD,
        )
        assert len(r.months) == 12
        assert [m.month_index for m in r.months] == list(range(1, 13))
        # 逐月独立：不是一个综合数字
        for m in r.months:
            assert m.bazi is not None and m.ziwei is not None and m.huangli is not None
            assert m.consensus is not None
            assert m.conflict is not None
            assert m.research_status
            assert m.data_quality

    def test_months_are_sequential_and_start_next_month(self):
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=5, weeks=0, variant_mode=VariantMode.FORWARD,
        )
        assert r.months[0].month == "2024-12"
        assert [m.month for m in r.months] == [
            "2024-12", "2025-01", "2025-02", "2025-03", "2025-04",
        ]

    def test_calendar_partial_is_warned(self):
        """跨越日历覆盖边界时必须有 warning，而不是静默近似。"""
        r = build_time_windows(
            stock_code="600519", as_of=datetime(2026, 11, 15, 14, 32),
            birth_datetime=BIRTH, months=12, weeks=0, variant_mode=VariantMode.FORWARD,
        )
        codes = {w.code for w in r.warnings}
        assert "TIMELINE_CALENDAR_PARTIAL" in codes or "TIMELINE_NO_TRADING_DAY" in codes, (
            "2027 年超出实测日历覆盖，必须如实告警"
        )

    def test_month_without_trading_days_is_marked_not_scored(self):
        r = build_time_windows(
            stock_code="600519", as_of=datetime(2027, 11, 15, 14, 32),
            birth_datetime=BIRTH, months=3, weeks=0, variant_mode=VariantMode.FORWARD,
        )
        empty = [m for m in r.months if m.trading_days == 0]
        for m in empty:
            assert m.consensus is None
            assert m.research_status == "NOT_RUN"
            assert any(w.code == "TIMELINE_NO_TRADING_DAY" for w in m.warnings)


# ---------------------------------------------------------------------------
# 3. 周度窗口（交易日聚合）
# ---------------------------------------------------------------------------


@requires_ziwei
class TestWeekWindows:
    def test_weeks_are_built_from_trading_days(self):
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=0, weeks=12, variant_mode=VariantMode.FORWARD,
        )
        assert len(r.weeks) == 12
        for w in r.weeks:
            assert 1 <= w.trading_days <= TRADING_DAYS_PER_WEEK
            assert len(w.daily_results) == w.trading_days
            assert w.week_start <= w.week_end
            for d in w.daily_results:
                assert d.trade_date.weekday() < 5, "周内每一天都必须是交易日"

    def test_no_flow_week_concept_is_claimed(self):
        """必须显式否弃『流周』这一概念。"""
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=0, weeks=4, variant_mode=VariantMode.FORWARD,
        )
        for w in r.weeks:
            assert "流周" in w.aggregation_method
            assert "交易日" in w.aggregation_method

    def test_aggregation_method_is_versioned(self):
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=0, weeks=4, variant_mode=VariantMode.FORWARD,
        )
        assert r.aggregation_version == AGGREGATION_VERSION
        for w in r.weeks:
            assert w.aggregation_version == AGGREGATION_VERSION

    def test_all_required_aggregations_present(self):
        """不允许只给一个平均数。"""
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=0, weeks=4, variant_mode=VariantMode.FORWARD,
        )
        for w in r.weeks:
            for field in ("mean", "median", "min", "max",
                          "positive_day_ratio", "weighted_mean"):
                assert getattr(w, field) is not None, f"{w.week_index} 缺少 {field}"

    def test_week_windows_are_consecutive(self):
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=0, weeks=6, variant_mode=VariantMode.FORWARD,
        )
        for a, b in zip(r.weeks, r.weeks[1:], strict=False):
            assert a.week_end < b.week_start, "相邻周不能重叠"
        assert r.weeks[0].week_start > AS_OF.date()


# ---------------------------------------------------------------------------
# 4. 聚合口径
# ---------------------------------------------------------------------------


class TestAggregation:
    def test_weighted_mean_excludes_unavailable_days(self):
        """不可用引擎不参与，也不用 0 占位 —— 否则均值会被系统性地拉向中性。"""
        daily = [
            # 三引擎全可用，方向全为正
            DayResult(trade_date=date(2024, 1, 2), bazi_direction=1, ziwei_direction=1,
                      huangli_direction=1, combined_direction=1,
                      bazi_score=70, ziwei_score=70, huangli_score=70),
            # 只有黄历可用（其余为 None = 不可用），方向全为负
            DayResult(trade_date=date(2024, 1, 3), bazi_direction=0, ziwei_direction=0,
                      huangli_direction=-1, combined_direction=-1,
                      bazi_score=None, ziwei_score=None, huangli_score=30),
        ]
        # 权重 = 可用引擎数 → (1*3 + (-1)*1) / 4 = 0.5
        assert _weighted_mean(daily) == 0.5

    def test_weighted_mean_returns_none_when_nothing_available(self):
        daily = [DayResult(trade_date=date(2024, 1, 2), combined_direction=0)]
        assert _weighted_mean(daily) is None

    def test_aggregation_version_is_declared_constant(self):
        assert AGGREGATION_VERSION.startswith("agg-")


# ---------------------------------------------------------------------------
# 5. 与紫微 variant 的交互
# ---------------------------------------------------------------------------


@requires_ziwei
class TestVariantInteraction:
    def test_forward_and_reverse_can_differ(self):
        """顺行/逆行会改变大限/小限因子 → 紫微观点可能不同（也可能恰好相同）。"""
        fwd = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=3, weeks=0, variant_mode=VariantMode.FORWARD,
        )
        rev = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=3, weeks=0, variant_mode=VariantMode.REVERSE,
        )
        assert fwd.variant_mode == "forward"
        assert rev.variant_mode == "reverse"
        # 两者都必须如实产出，且都标注了 variant 假设
        for r in (fwd, rev):
            for m in r.months:
                if m.ziwei is not None and m.ziwei.availability == Availability.OK:
                    assert any("variant" in a or "性别" in a for a in m.ziwei.assumptions)

    def test_not_applicable_leaves_ziwei_unavailable_not_zero(self):
        """variant 不适用的场景仍要能构建窗口，但紫微必须是 unavailable。"""
        r = build_time_windows(
            stock_code="600519", as_of=AS_OF, birth_datetime=BIRTH,
            months=2, weeks=0, variant_mode=VariantMode.NOT_APPLICABLE,
        )
        for m in r.months:
            assert m.ziwei is not None
            assert m.ziwei.availability == Availability.UNAVAILABLE
            assert m.ziwei.score is None, "不可用必须是 null，不能用 0 冒充"
            assert m.consensus is not None
            assert "ziwei" in [str(e) for e in m.consensus.unavailable_engines]


class TestEngineContextContract:
    def test_ziwei_engine_requires_explicit_variant(self):
        """时间窗口不得偷偷替调用方选择方向。"""
        from src.engines.ziwei.ziwei_engine import ZiweiUnavailableError

        engine = ZiweiEngine()
        with pytest.raises(ZiweiUnavailableError):
            engine.calculate_chart(
                EngineContext(stock_code="600519"),
                birth_datetime=BIRTH, as_of=AS_OF,
                variant_mode=VariantMode.NOT_APPLICABLE,
            )

    def test_engine_id_constant(self):
        assert EngineId.ZIWEI.value == "ziwei"
