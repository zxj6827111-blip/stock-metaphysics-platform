"""交易日历的"实测层 / 官方公布层 / 降级"三层语义。

这一批测试针对的是本轮修复的核心缺陷：**把"没有未来行情"误判成
"无法确定未来交易日"**，于是以当天为基准日的"未来 N 个交易日"直接返回空。

覆盖三件事：
1. 公布层确实能把实测层之后的日期答成"已知"（且长假缺席）；
2. 两层都没覆盖时仍然回答"未知"，绝不猜测、绝不照搬上一年；
3. 交叉校验不过时公布层**拒绝加载**（宁可用不了，也不给错答案）。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.core.stock.trading_calendar import (
    KNOWN_SOURCES,
    TradingCalendar,
    TradingCalendarProvider,
    get_trading_calendar_provider,
)

pytestmark = pytest.mark.golden


@pytest.fixture(scope="module")
def provider() -> TradingCalendarProvider:
    return get_trading_calendar_provider()


# ----------------------------------------------------------------------
# 1. 实测层：历史成交事实（本轮未改动，作为回归锚点）
# ----------------------------------------------------------------------
class TestObservedLayer:
    @pytest.mark.parametrize("d", [date(2024, 10, 1), date(2024, 10, 7),
                                   date(2024, 2, 12), date(2020, 1, 31)])
    def test_observed_holidays_still_closed(self, provider, d):
        cal = provider.for_exchange("SSE")
        q = cal.is_trading_day(d)
        assert q.value is False and q.source == "observed_index_days"

    def test_observed_source_is_the_only_fact_for_past_dates(self, provider):
        cal = provider.for_exchange("SSE")
        assert cal.loaded
        assert cal.is_trading_day(date(1999, 11, 10)).source == "observed_index_days"


# ----------------------------------------------------------------------
# 2. 公布层：交易所已公告的未来安排
# ----------------------------------------------------------------------
class TestPublishedLayer:
    def test_published_layer_loaded_and_verified(self, provider):
        cal = provider.for_exchange("SSE")
        assert cal.published_loaded, f"公布层未加载: {cal.published_error}"
        assert cal.published_coverage is not None
        verified = (cal.published_meta.get("cross_validation") or {}).get("verified")
        assert verified is True, "公布层必须通过与官方逐日口径的交叉校验"
        assert cal.published_meta.get("sources"), "公布层必须记录来源"

    def test_published_window_is_contiguous_with_observed(self, provider):
        """公布窗口必须紧接实测末日之后 —— 中间不能有'谁都没覆盖'的空洞。"""
        cal = provider.for_exchange("SSE")
        from datetime import timedelta
        assert cal.published_coverage[0] == cal.coverage[1] + timedelta(days=1)

    def test_future_day_after_observed_end_is_answered(self, provider):
        cal = provider.for_exchange("SSE")
        first_published = cal.published_coverage[0]
        q = cal.is_trading_day(first_published)
        assert q.value is not None, "公布层内的日期不能回答'未知'"
        assert q.source == "published_exchange_calendar"
        assert q.degraded_reason, "公布层结论必须带证据说明"

    def test_weekend_inside_published_window_is_closed(self, provider):
        """公布窗口覆盖了周末，因此周末是'确定休市'而不是'未知'。"""
        cal = provider.for_exchange("SSE")
        cur = cal.published_coverage[0]
        from datetime import timedelta
        weekend = next(
            cur + timedelta(days=i) for i in range(14)
            if (cur + timedelta(days=i)).weekday() >= 5
        )
        q = cal.is_trading_day(weekend)
        assert q.value is False and q.source == "published_exchange_calendar"

    def test_beyond_published_range_is_unknown_not_guessed(self, provider):
        """官方尚未公布下一年度安排 → 必须回答'未知'，不得照搬上一年。"""
        from datetime import timedelta
        cal = provider.for_exchange("SSE")
        beyond = cal.published_coverage[1] + timedelta(days=5)
        q = cal.is_trading_day(beyond)
        assert q.value is None
        assert q.source == "out_of_coverage"
        assert "update_trading_calendar" in q.degraded_reason

    def test_observed_takes_precedence_over_published(self):
        """重叠区间：已发生的成交事实优先于计划安排。"""
        from datetime import timedelta
        base = date(2026, 9, 1)
        next_day = base + timedelta(days=1)
        cal = TradingCalendar(
            exchange="SSE",
            _days=frozenset({base}),                     # 实测：9-1 成交
            _published={base: False, next_day: False},   # 公布：9-1 休市（人为冲突）
            _published_evidence={base: "test", next_day: "test"},
            published_loaded=True,
            loaded=True,
        )
        q = cal.is_trading_day(base)
        assert q.source == "observed_index_days" and q.value is True
        # 实测没覆盖的日子才走公布层
        q2 = cal.is_trading_day(next_day)
        assert q2.source == "published_exchange_calendar" and q2.value is False

    def test_cross_validation_failure_blocks_loading(self, tmp_path: Path):
        """交叉校验 verified=false → 拒绝加载公布层（不猜、不用可疑数据）。"""
        cal_dir = tmp_path / "calendar"
        pub_dir = cal_dir / "published"
        pub_dir.mkdir(parents=True)
        (cal_dir / "SSE.csv").write_text("trade_date\n2026-01-05\n2026-01-06\n",
                                         encoding="utf-8")
        (pub_dir / "SSE.csv").write_text(
            "trade_date,is_open,evidence\n2026-01-07,1,x\n", encoding="utf-8")
        (pub_dir / "_meta.json").write_text(
            json.dumps({"cross_validation": {"verified": False, "mismatches": [{"a": 1}]}}),
            encoding="utf-8",
        )
        cal = TradingCalendarProvider(calendar_dir=cal_dir).for_exchange("SSE")
        assert cal.loaded is True
        assert cal.published_loaded is False
        assert "交叉校验" in cal.published_error
        # 拒绝加载后，公布范围内的日期回到"未知"，不是"休市"
        assert cal.is_trading_day(date(2026, 1, 7)).value is None

    def test_missing_published_file_is_not_an_error_for_past_queries(self, tmp_path: Path):
        cal_dir = tmp_path / "calendar"
        cal_dir.mkdir()
        (cal_dir / "SSE.csv").write_text("trade_date\n2026-01-05\n", encoding="utf-8")
        cal = TradingCalendarProvider(calendar_dir=cal_dir).for_exchange("SSE")
        assert cal.published_loaded is False
        assert cal.is_trading_day(date(2026, 1, 5)).value is True


# ----------------------------------------------------------------------
# 3. 降级：绝不借用别的交易所、绝不用周末规则假装
# ----------------------------------------------------------------------
class TestDegradation:
    def test_bse_has_no_published_layer_and_never_borrows(self, provider):
        cal = provider.for_exchange("BSE")
        assert cal.published_loaded is False
        assert cal.published_error
        # 北交所没有可靠官方日历时，回答"周末规则近似"并明确标注，
        # 而不是拿沪深日历冒充
        q = cal.is_trading_day(date(2026, 10, 8))
        assert q.source == "weekend_rule_fallback"
        assert q.degraded_reason

    def test_weekend_fallback_is_not_a_known_source(self):
        assert "weekend_rule_fallback" not in KNOWN_SOURCES
        assert KNOWN_SOURCES == {"observed_index_days", "published_exchange_calendar"}

    def test_timeline_rejects_weekend_fallback(self, tmp_path: Path, monkeypatch):
        """时间窗口必须拒绝周末规则结果 —— 它会把长假当成交易日且毫无提示。"""
        from src.core.orchestration.timeline import TimelineBuilder

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        import src.core.stock.trading_calendar as tc

        monkeypatch.setattr(tc, "_default_provider", None)
        monkeypatch.setattr(
            tc, "get_trading_calendar_provider",
            lambda: TradingCalendarProvider(calendar_dir=empty_dir),
        )
        builder = TimelineBuilder()
        monkeypatch.setattr(
            TimelineBuilder, "_trading_calendar",
            staticmethod(lambda exchange="SSE": TradingCalendarProvider(
                calendar_dir=empty_dir).for_exchange(exchange)),
        )
        # 春节长假期间的工作日：周末规则会说"开市"，时间窗口必须说"不知道"
        assert builder._is_trading_day(date(2025, 1, 30), "SSE") is None


# ----------------------------------------------------------------------
# 4. 覆盖元数据必须把三层分开
# ----------------------------------------------------------------------
class TestCoverageDescriptor:
    def test_descriptor_separates_layers(self, provider):
        cal = provider.for_exchange("SSE")
        desc = cal.coverage_descriptor()
        assert desc["observed"]["end"]
        assert desc["published"]["end"]
        assert desc["published"]["verified"] is True
        assert desc["published"]["generated_at"]
        assert desc["published"]["boundary_cn"]
        assert desc["observed"]["source"] == "observed_index_days"
        assert desc["published"]["source"] == "published_exchange_calendar"
        # 公布的末日必须晚于实测的末日（否则这一层没有意义）
        assert desc["published"]["end"] > desc["observed"]["end"]

    def test_effective_coverage_spans_both_layers(self, provider):
        cal = provider.for_exchange("SSE")
        eff = cal.effective_coverage
        assert eff[0] == cal.coverage[0]
        assert eff[1] == cal.published_coverage[1]

    def test_trading_days_between_reports_unknown_span(self, provider):
        """区间跨出全部覆盖时，未知天数必须报出来，不能静默当休市。"""
        cal = provider.for_exchange("SSE")
        end = cal.published_coverage[1]
        from datetime import timedelta
        q = cal.trading_days_between(date(2026, 12, 28), end + timedelta(days=10))
        assert q.source and "published_exchange_calendar" in q.source
        assert q.degraded_reason and "未知" not in q.degraded_reason or q.degraded_reason
        assert "未计入交易日" in q.degraded_reason


# ----------------------------------------------------------------------
# 7. 缓存身份：内容变了（区间与行数不变）也必须换键、换数据
# ----------------------------------------------------------------------
class TestCalendarCacheIdentity:
    """反例驱动的回归：**覆盖区间和行数不变、但日历内容发生变化**。

    这是会给出错误答案的一类更新：
      * 公布层某天由休市改为开市（或反之）→ 行数不变、区间不变；
      * 实测层同一天数但日期不同（数据源修订/回填调整）；
      * 文件被 `update_trading_calendar.py` 重写后，已运行的进程必须重新加载。

    旧实现用「区间 + 行数 + 生成时间」做指纹，上述前两类都识别不出来，
    运行中的实例还会一直用内存里的旧日历（连"指纹变了"都无从得知）。
    """

    def _write(self, root: Path, days: list[str], published: dict[str, bool]) -> None:
        (root / "published").mkdir(parents=True, exist_ok=True)
        (root / "SSE.csv").write_text(
            "trade_date\n" + "".join(f"{d}\n" for d in days), encoding="utf-8"
        )
        rows = ["trade_date,is_open,evidence"]
        rows += [f"{d},{'1' if flag else '0'},test" for d, flag in published.items()]
        (root / "published" / "SSE.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        (root / "published" / "_meta.json").write_text(
            json.dumps({"generated_at": "2026-09-21T00:00:00", "verified": True}), encoding="utf-8"
        )

    def test_fingerprint_changes_when_flag_flips_with_same_shape(self, tmp_path: Path):
        """同区间同行数、只翻转一天的开市标志 → 指纹必须变。"""
        from src.core.stock.trading_calendar import published_flags_fingerprint

        a = {date(2026, 10, 1): True, date(2026, 10, 2): False}
        b = {date(2026, 10, 1): False, date(2026, 10, 2): True}  # 同行数、同区间
        assert len(a) == len(b)
        assert published_flags_fingerprint(a) != published_flags_fingerprint(b)

    def test_fingerprint_changes_when_observed_day_swapped(self):
        """实测层同一天数但换了一天 → 指纹必须变（区间端点也可能不变）。"""
        from src.core.stock.trading_calendar import observed_days_fingerprint

        a = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
        b = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 4)]
        assert len(a) == len(b)
        assert observed_days_fingerprint(a) != observed_days_fingerprint(b)

    def test_fingerprint_stable_regardless_of_input_order(self):
        """指纹必须只取决于内容：集合/字典的迭代顺序不能影响它。"""
        from src.core.stock.trading_calendar import (
            observed_days_fingerprint,
            published_flags_fingerprint,
        )

        days = {date(2026, 9, 3), date(2026, 9, 1), date(2026, 9, 2)}
        assert observed_days_fingerprint(days) == observed_days_fingerprint(
            frozenset(days)
        )
        flags = {date(2026, 10, 2): True, date(2026, 10, 1): False}
        assert published_flags_fingerprint(flags) == published_flags_fingerprint(
            {date(2026, 10, 1): False, date(2026, 10, 2): True}
        )

    def test_version_token_changes_on_content_only_update(self, tmp_path: Path):
        """端到端：文件重写（区间/行数不变、内容变）后 version_token 必须不同。"""
        root = tmp_path / "cal"
        days = ["2026-09-01", "2026-09-02"]
        self._write(root, days, {"2026-09-03": True})

        p = TradingCalendarProvider(calendar_dir=root)
        cal1 = p.for_exchange("SSE")
        token1 = cal1.version_token
        assert cal1.published_loaded
        assert cal1.is_trading_day(date(2026, 9, 3)).value is True

        # 同样两天、同一区间；只把公布层的 9-3 由开市改为休市
        self._write(root, days, {"2026-09-03": False})
        cal2 = p.for_exchange("SSE")
        assert cal2.version_token != token1, "内容变了但指纹没变 → 会把旧结果当新结果返回"
        assert cal2.is_trading_day(date(2026, 9, 3)).value is False

    def test_provider_reloads_after_source_file_rewrite(self, tmp_path: Path):
        """已运行实例必须加载到更新后的日历（不能永远用内存里的旧文件）。"""
        root = tmp_path / "cal"
        self._write(root, ["2026-09-01"], {"2026-09-02": False})
        p = TradingCalendarProvider(calendar_dir=root)
        assert p.for_exchange("SSE").is_trading_day(date(2026, 9, 2)).value is False

        self._write(root, ["2026-09-01", "2026-09-02"], {"2026-09-02": True})
        cal = p.for_exchange("SSE")
        assert cal.is_trading_day(date(2026, 9, 2)).source == "observed_index_days"
        assert cal.coverage[1] == date(2026, 9, 2)

    def test_provider_reload_is_idempotent_when_files_unchanged(self, tmp_path: Path):
        """文件没变时不应反复重建（保持缓存语义，避免每次请求都读盘解析）。"""
        root = tmp_path / "cal"
        self._write(root, ["2026-09-01"], {"2026-09-02": True})
        p = TradingCalendarProvider(calendar_dir=root)
        first = p.for_exchange("SSE")
        assert p.for_exchange("SSE") is first
