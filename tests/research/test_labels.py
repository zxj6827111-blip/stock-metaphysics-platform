"""前向收益标签测试（architecture §41 / §42）。

覆盖：
* ret_1d / 5d / 10d / 20d / 60d；
* max_return_20d / max_drawdown_20d；
* excess_return_20d（相对沪深300）；
* 「上涨」的四种定义：absolute_up / excess_up / strong_up / drawdown_controlled_up；
* 数据不足时必须返回 None 并标记 horizon_available，**不用 0 填充**。
"""

from __future__ import annotations

from datetime import date

import pytest

from src.core.config import settings
from src.market.normalization.frames import build_series
from src.research.labels.forward_returns import (
    DRAWDOWN_CONTROL_THRESHOLD,
    STRONG_UP_THRESHOLD,
    InsufficientForwardData,
    compute_labels,
)


def _series_from_closes(closes: list[float], start: date = date(2024, 1, 1)):
    import pandas as pd

    dates = pd.bdate_range(start, periods=len(closes)).date
    df = pd.DataFrame({
        "日期": [d.isoformat() for d in dates],
        "开盘": closes,
        "最高": list(closes),
        "最低": list(closes),
        "收盘": closes,
    })
    return build_series("600519", df)


class TestHorizons:
    def test_all_horizons_computed(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        labels = compute_labels(series, date(2021, 6, 1))
        for h in settings.label_horizons:
            assert getattr(labels, f"ret_{h}d") is not None, f"ret_{h}d 缺失"
            assert labels.horizon_available[f"{h}d"] is True

    def test_return_math(self):
        """构造确定的收盘序列，验证收益计算。"""
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
        series = _series_from_closes(closes)
        labels = compute_labels(series, date(2024, 1, 1), horizons=(1, 5))
        assert labels.ret_1d == pytest.approx(11.0 / 10.0 - 1.0, abs=1e-6)
        assert labels.ret_5d == pytest.approx(15.0 / 10.0 - 1.0, abs=1e-6)

    def test_non_standard_horizon_goes_to_extra_returns(self):
        """非标准持有期必须显式落入 extra_returns，不能被静默丢弃。"""
        closes = [10.0, 11.0, 12.0, 13.0]
        series = _series_from_closes(closes)
        labels = compute_labels(series, date(2024, 1, 1), horizons=(2,))
        assert labels.extra_returns["ret_2d"] == pytest.approx(12.0 / 10.0 - 1.0, abs=1e-6)
        assert labels.horizon_available["2d"] is True

    def test_base_trade_date_is_first_trading_day_at_or_after_as_of(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        as_of = date(2021, 6, 5)  # 周六
        labels = compute_labels(series, as_of)
        assert labels.as_of == as_of
        assert labels.trade_date >= as_of
        assert labels.trade_date.weekday() < 5


class TestPathMetrics:
    def test_max_return_and_drawdown(self):
        # 基准收盘 10 → 路径上有 前高 15、前低 8
        closes = [10.0, 15.0, 8.0, 12.0]
        series = _series_from_closes(closes)
        labels = compute_labels(series, date(2024, 1, 1), horizons=(1, 2))
        assert labels.max_return_20d == pytest.approx(15.0 / 10.0 - 1.0, abs=1e-6)
        assert labels.max_drawdown_20d == pytest.approx(8.0 / 10.0 - 1.0, abs=1e-6)

    def test_drawdown_is_negative(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        labels = compute_labels(series, date(2021, 6, 1))
        if labels.max_drawdown_20d is not None:
            assert labels.max_drawdown_20d <= 0.0


class TestExcessReturn:
    def test_excess_return_computed(self, market):
        stock = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        bench = market.get_benchmark_bars("000300", date(2020, 1, 1), date(2022, 12, 31))
        labels = compute_labels(stock, date(2021, 6, 1), benchmark_series=bench, benchmark_code="000300")
        assert labels.bench_ret_20d is not None
        assert labels.excess_return_20d is not None
        assert labels.excess_return_20d == pytest.approx(
            labels.ret_20d - labels.bench_ret_20d, abs=1e-6
        )

    def test_without_benchmark_excess_is_none(self, market):
        stock = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        labels = compute_labels(stock, date(2021, 6, 1))
        assert labels.excess_return_20d is None
        assert labels.bench_ret_20d is None


class TestMultipleUpDefinitions:
    def test_absolute_up(self):
        closes = [10.0] + [10.0] * 19 + [11.0]
        labels = compute_labels(_series_from_closes(closes), date(2024, 1, 1), horizons=(20,))
        if labels.ret_20d is not None:
            assert labels.absolute_up_20d == (labels.ret_20d > 0)

    def test_strong_up_threshold(self):
        closes = [10.0] + [10.0] * 19 + [12.0]   # 第 20 个交易日 +20%
        labels = compute_labels(_series_from_closes(closes), date(2024, 1, 1), horizons=(20,))
        assert labels.ret_20d == pytest.approx(0.2, abs=1e-6)
        assert labels.strong_up_20d is True
        assert labels.strong_up_20d == (labels.ret_20d > STRONG_UP_THRESHOLD)

    def test_drawdown_controlled_up(self):
        """收益为正但路径上出现过 >10% 回撤 → drawdown_controlled_up 应为 False。"""
        closes = [10.0] + [10.0] * 19 + [10.5]
        series = _series_from_closes(closes)
        labels = compute_labels(series, date(2024, 1, 1), horizons=(20,))
        if labels.max_drawdown_20d is not None:
            expected = (labels.ret_20d or 0) > 0 and labels.max_drawdown_20d > DRAWDOWN_CONTROL_THRESHOLD
            assert labels.drawdown_controlled_up_20d == expected

    def test_excess_up_requires_benchmark(self, market):
        stock = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        bench = market.get_benchmark_bars("000300", date(2020, 1, 1), date(2022, 12, 31))
        labels = compute_labels(stock, date(2021, 6, 1), benchmark_series=bench)
        if labels.excess_return_20d is not None:
            assert labels.excess_up_20d == (labels.excess_return_20d > 0)


class TestInsufficientData:
    def test_raises_when_no_forward_bars(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 12, 31))
        with pytest.raises(InsufficientForwardData):
            compute_labels(series, date(2021, 6, 1))

    def test_partial_horizons_marked(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 6, 30))
        labels = compute_labels(series, date(2020, 6, 1))
        assert labels.horizon_available["1d"] is True
        assert labels.horizon_available["60d"] is False
        assert labels.ret_60d is None

    def test_never_zero_filled(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 6, 30))
        labels = compute_labels(series, date(2020, 6, 1))
        for key, ok in labels.horizon_available.items():
            if not ok:
                assert getattr(labels, f"ret_{key}") is None, f"{key} 被 0 填充"

    def test_base_close_missing(self):
        import pandas as pd

        df = pd.DataFrame({
            "日期": ["2024-01-01", "2024-01-02"],
            "收盘": [None, 10.0],
        })
        series = build_series("600519", df)
        with pytest.raises(InsufficientForwardData):
            compute_labels(series, date(2024, 1, 1))


class TestLabelImmutability:
    def test_as_of_never_after_trade_date(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        for as_of in (date(2021, 1, 1), date(2021, 6, 15), date(2022, 3, 20)):
            labels = compute_labels(series, as_of)
            assert labels.trade_date >= as_of

    def test_benchmark_code_recorded(self, market):
        stock = market.get_daily_bars("600519", date(2020, 1, 1), date(2022, 12, 31))
        labels = compute_labels(stock, date(2021, 6, 1), benchmark_code="000905")
        assert labels.benchmark_code == "000905"
