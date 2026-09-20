"""Phase 3D 统一未来收益标签测试（含复权口径与不可用语义）。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.labels.horizon_returns import (
    HORIZONS,
    LABEL_VERSION,
    BenchmarkSeries,
    align_adj_factor,
    compute_forward_returns,
    label_frame,
)


def _bars(closes: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": pd.date_range(start, periods=len(closes), freq="B"),
        "close": closes,
    })


class TestReturnComputation:
    def test_all_horizons_use_real_trading_days(self):
        bars = _bars([100.0 + index for index in range(80)])
        rows = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T")
        row = rows[0]
        assert row["trade_index"] == 0
        for horizon in HORIZONS:
            expected = (100.0 + horizon) / 100.0 - 1.0
            assert row[f"ret_{horizon}d"] == pytest.approx(expected, abs=1e-6)
            assert row["horizon_available"][f"{horizon}d"] is True

    def test_insufficient_forward_data_is_none_not_zero(self):
        bars = _bars([100.0 + index for index in range(30)])
        row = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T")[0]
        assert row["ret_5d"] is not None
        assert row["ret_60d"] is None
        assert row["excess_return_60d"] is None
        assert row["horizon_available"]["60d"] is False

    def test_as_of_after_data_end_produces_no_row(self):
        bars = _bars([100.0 + index for index in range(10)])
        assert compute_forward_returns(bars, [date(2021, 6, 1)], stock_code="T") == []

    def test_as_of_on_non_trading_day_uses_next_trading_day(self):
        bars = _bars([10.0, 11.0, 12.0, 13.0, 14.0, 15.0], start="2020-01-03")  # 周五起
        rows = compute_forward_returns(
            bars, [date(2020, 1, 4)], stock_code="T", horizons=(1,)
        )
        assert rows[0]["trade_date"] == date(2020, 1, 6)  # 周六 as_of → 下周一为基准日
        assert rows[0]["trade_index"] == 1
        assert rows[0]["ret_1d"] == pytest.approx(12.0 / 11.0 - 1.0, abs=1e-6)


class TestAdjustment:
    def test_dividend_drop_is_not_a_loss(self):
        """未复权价在除权日跳水；用 adj_factor 后收益必须反映真实回报。"""
        bars = pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=6, freq="B"),
            "close": [10.0, 10.0, 5.0, 5.0, 5.0, 5.0],  # 第 3 天 1 拆 2
        })
        factors = pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=6, freq="B"),
            "factor": [1.0, 1.0, 2.0, 2.0, 2.0, 2.0],
        })
        raw_row = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T",
                                          horizons=(2,))[0]
        assert raw_row["ret_2d"] == pytest.approx(-0.5, abs=1e-6)  # 未复权：-50%
        adj_row = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T",
                                          horizons=(2,), adj_factors=factors)[0]
        assert adj_row["ret_2d"] == pytest.approx(0.0, abs=1e-6)  # 复权后：0%

    def test_align_adj_factor_reports_coverage(self):
        bars = _bars([10.0] * 5)
        factors = pd.DataFrame({
            "trade_date": bars["trade_date"].tolist()[:2],
            "factor": [1.0, 2.0],
        })
        factor, stats = align_adj_factor(bars, factors)
        assert stats["raw_rows"] == 5
        assert stats["matched_rows"] == 2
        assert stats["filled_rows"] == 3  # 前向填充
        assert stats["uncovered_rows"] == 0
        assert factor.tolist() == [1.0, 2.0, 2.0, 2.0, 2.0]

    def test_missing_adj_factor_is_reported_not_silently_one(self):
        bars = _bars([10.0] * 3)
        _factor, stats = align_adj_factor(bars, None)
        assert stats["uncovered_rows"] == 3

    def test_adj_factor_accepts_date_objects_from_database(self):
        """DB 行给出的是 date 对象，CSV 给出 datetime64：合并必须类型归一。"""
        bars = pd.DataFrame({
            "trade_date": [date(2020, 1, 1), date(2020, 1, 2)],
            "close": [10.0, 11.0],
        })
        factors = pd.DataFrame({
            "trade_date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "factor": [1.0, 1.0],
        })
        factor, stats = align_adj_factor(bars, factors)
        assert stats["matched_rows"] == 2
        assert factor.tolist() == [1.0, 1.0]


class TestExcessReturns:
    def test_excess_uses_stock_calendar_window(self):
        bars = _bars([100.0 * (1.02 ** index) for index in range(80)])
        bench_frame = pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=80, freq="B"),
            "close": [100.0 * (1.01 ** index) for index in range(80)],
        })
        bench = BenchmarkSeries.from_frame(bench_frame)
        row = compute_forward_returns(
            bars, [date(2020, 1, 1)], stock_code="T", benchmark=bench,
        )[0]
        for horizon in HORIZONS:
            expected = (1.02 ** horizon) - (1.01 ** horizon)
            assert row[f"excess_return_{horizon}d"] == pytest.approx(expected, abs=1e-6)
            assert row[f"bench_ret_{horizon}d"] is not None

    def test_benchmark_missing_leaves_excess_none(self):
        bars = _bars([100.0 + index for index in range(30)])
        row = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T")[0]
        assert row["excess_return_20d"] is None
        assert row["bench_ret_20d"] is None
        assert row["ret_20d"] is not None

    def test_benchmark_index_at_or_after(self):
        bench = BenchmarkSeries.from_frame(pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=5, freq="B"),
            "close": [1.0, 2.0, 3.0, 4.0, 5.0],
        }))
        assert bench.index_at_or_after(date(2020, 1, 1)) == 0
        assert bench.index_at_or_after(date(2020, 1, 4)) == 3  # 周六 → 下周一（01-06）
        assert bench.index_at_or_after(date(2030, 1, 1)) is None
        assert bench.return_between(date(2020, 1, 1), date(2020, 1, 3)) == pytest.approx(2.0)


class TestLabelFrame:
    def test_label_frame_has_all_horizon_columns(self):
        bars = _bars([100.0 + index for index in range(80)])
        rows = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T")
        frame = label_frame(rows)
        assert len(frame) == 1
        for horizon in HORIZONS:
            assert f"ret_{horizon}d" in frame.columns
            assert f"excess_return_{horizon}d" in frame.columns
        assert frame["label_version"].iloc[0] == LABEL_VERSION
        assert frame["trade_index"].iloc[0] == 0

    def test_label_frame_accepts_empty_rows(self):
        frame = label_frame([])
        assert frame.empty
        assert "ret_20d" in frame.columns

    def test_degraded_flag_propagates(self):
        bars = _bars([100.0 + index for index in range(30)])
        row = compute_forward_returns(
            bars, [date(2020, 1, 1)], stock_code="T", is_degraded=True,
        )[0]
        assert row["is_degraded"] is True

    def test_no_nan_leaks_into_returns_as_zero(self):
        bars = _bars([100.0 + index for index in range(30)])
        rows = compute_forward_returns(bars, [date(2020, 1, 1)], stock_code="T")
        values = [rows[0].get(f"ret_{h}d") for h in HORIZONS]
        assert None in values
        assert all(value != 0.0 for value in values if value is not None)
        assert not np.any(np.isnan([value for value in values if value is not None]))
