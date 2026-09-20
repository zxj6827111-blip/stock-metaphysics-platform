"""Phase 3D 诊断模块测试：年份稳定性 / 重叠窗口 / 单一股票依赖 / 效应量。

这些诊断决定"结果能不能信"，因此每一条都要有反例测试：
一个由极端年份驱动、或由单只股票驱动、或有严重重叠窗口的结果，
必须被对应的诊断标记出来，而不是被当成"看起来很显著"。
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.research.oos import diagnostics as diag


def _events(
    *,
    stocks: list[str] | None = None,
    dates: list[date] | None = None,
    excess: float = 0.01,
    spread: float = 0.2,
    seed: int = 20260920,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    stocks = stocks or [f"{index:06d}" for index in range(40)]
    dates = dates or [date(year, 1, 1) for year in range(2020, 2024)]
    rows: list[dict] = []
    for code in stocks:
        for index, as_of in enumerate(dates):
            value = excess + rng.normal(0, spread)
            rows.append({
                "stock_code": code,
                "as_of": as_of,
                "trade_date": as_of,
                "trade_index": index * 60,
                "ret_20d": value,
                "excess_return_20d": value,
            })
    return pd.DataFrame(rows)


class TestYearStability:
    def test_stable_positive_series(self):
        frame = _events(excess=0.02, spread=0.1, seed=1)
        result = diag.year_stability(frame, 20)
        assert result["year_count"] == 4
        assert result["positive_year_ratio"] == pytest.approx(1.0)
        assert result["sign_consistency"] == pytest.approx(1.0)
        assert result["overall_sign"] == 1

    def test_single_extreme_year_is_not_stable(self):
        frame = _events(excess=-0.05, spread=0.05, seed=2)
        # 只在 2021 年插入极端正收益：整体均值被拉正，但年份一致性应崩掉
        mask = frame["as_of"] == date(2021, 1, 1)
        frame.loc[mask, "excess_return_20d"] = 0.5
        result = diag.year_stability(frame, 20)
        assert result["overall_sign"] == 1  # 整体看起来是正的
        assert result["positive_year_ratio"] < 0.6  # 但只有 1/4 年为正
        assert result["sign_consistency"] < 0.6

    def test_empty_frame_is_explicit_none(self):
        result = diag.year_stability(pd.DataFrame(), 20)
        assert result["year_count"] == 0
        assert result["positive_year_ratio"] is None

    def test_year_rows_include_counts_and_direction(self):
        result = diag.year_stability(_events(seed=3), 20)
        assert {row["year"] for row in result["years"]} == {2020, 2021, 2022, 2023}
        assert all(row["event_count"] == 40 for row in result["years"])
        assert all(row["direction"] in (-1, 0, 1) for row in result["years"])


class TestOverlap:
    def test_non_overlapping_panel_reports_zero(self):
        frame = _events(seed=4)  # 相邻事件相隔 60 个交易日
        assert diag.overlap_ratio(frame, 20) == 0.0
        subset = diag.non_overlapping_subset(frame, 20)
        assert len(subset) == len(frame)

    def test_dense_panel_reports_true_overlap(self):
        dates = [date(2020, 1, 1) + timedelta(days=index) for index in range(10)]
        rows: list[dict] = []
        for code in ("000001", "000002"):
            for index, as_of in enumerate(dates):
                rows.append({
                    "stock_code": code, "as_of": as_of, "trade_date": as_of,
                    "trade_index": index, "ret_20d": 0.01, "excess_return_20d": 0.01,
                })
        frame = pd.DataFrame(rows)
        ratio = diag.overlap_ratio(frame, 20)
        assert ratio == pytest.approx(1.0)  # 全部事件都落在彼此的持有窗口内
        subset = diag.non_overlapping_subset(frame, 20)
        assert len(subset) == 2  # 每只股票只保留 1 个事件

    def test_non_overlapping_subset_keeps_largest_gap_ordering(self):
        frame = pd.DataFrame({
            "stock_code": ["000001"] * 4,
            "as_of": [date(2020, 1, 1)] * 4,
            "trade_index": [0, 5, 30, 60],
            "excess_return_20d": [0.1, 0.2, 0.3, 0.4],
        })
        subset = diag.non_overlapping_subset(frame, 20)
        assert subset["trade_index"].tolist() == [0, 30, 60]

    def test_empty_frame_is_none(self):
        assert diag.overlap_ratio(pd.DataFrame(), 20) is None


class TestStockDependency:
    def test_uniform_contribution_is_not_dependent(self):
        frame = _events(excess=0.02, spread=0.05, seed=5)
        result = diag.stock_dependency(frame, 20)
        assert result["single_name_dependent"] is False
        assert result["loo_sign_flip_count"] == 0
        # 单只股票的绝对贡献份额不应接近"主导"水平（阈值 0.5）
        assert result["top_1_contribution"] < 0.15
        assert result["top_5_contribution"] < 0.5

    def test_single_name_dominance_is_flagged(self):
        frame = _events(excess=0.0, spread=0.01, seed=6)
        mask = frame["stock_code"] == "000000"
        frame.loc[mask, "excess_return_20d"] = 5.0  # 一只股票贡献绝大部分收益
        result = diag.stock_dependency(frame, 20)
        assert result["single_name_dependent"] is True
        assert result["loo_sign_flip_count"] > 0

    def test_contribution_distribution_is_sorted_and_normalized(self):
        frame = _events(seed=7)
        distribution = diag.contribution_distribution(frame, 20)
        shares = [row["abs_mass_share"] for row in distribution]
        assert shares == sorted(shares, reverse=True)
        assert sum(shares) == pytest.approx(1.0, abs=1e-4)  # 份额按 1e-6 舍入
        assert sum(row["event_count"] for row in distribution) == len(frame)

    def test_empty_frame_is_explicit(self):
        result = diag.stock_dependency(pd.DataFrame(), 20)
        assert result["single_name_dependent"] is None
        assert result["loo_sign_flip_count"] == 0


class TestEffectSize:
    def test_welch_and_cohens_d_on_shifted_series(self):
        rng = np.random.default_rng(11)
        real = rng.normal(0.05, 0.1, size=500)
        control = rng.normal(0.0, 0.1, size=500)
        summary = diag.effect_size_summary(real, control, permutation_p=0.001, control_draws=200)
        assert summary["mean_real"] > summary["mean_control"]
        assert summary["delta_mean"] == pytest.approx(0.05, abs=0.02)
        assert summary["cohen_d"] == pytest.approx(0.5, abs=0.15)
        assert summary["welch_p"] < 0.01
        assert summary["permutation_p"] == pytest.approx(0.001)

    def test_zero_variance_returns_none_not_zero(self):
        t, p = diag.welch_ttest([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
        assert t is None and p is None
        assert diag.cohens_d([1.0, 1.0], [1.0, 1.0]) is None
        assert diag.effect_size_summary([], [1.0])["cohen_d"] is None

    def test_cohens_d_sign_follows_direction(self):
        assert diag.cohens_d([2.0, 2.1, 2.2], [1.0, 1.1, 1.2]) > 0
        assert diag.cohens_d([1.0, 1.1, 1.2], [2.0, 2.1, 2.2]) < 0

    def test_normal_two_sided_p_matches_known_values(self):
        assert diag.normal_two_sided_p(0.0) == pytest.approx(1.0)
        assert diag.normal_two_sided_p(1.96) == pytest.approx(0.05, abs=0.001)
        assert diag.normal_two_sided_p(-1.96) == pytest.approx(0.05, abs=0.001)
        assert diag.normal_two_sided_p(10.0) < 1e-20


class TestHitConcentration:
    def _frames(self, rates: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
        """构造 hits/pool：每个 as_of 的命中率由 ``rates`` 指定（每期 10 只股票）。"""
        hits: list[dict] = []
        pool: list[dict] = []
        for index, rate in enumerate(rates):
            as_of = date(2024, 1, 1) + timedelta(days=30 * index)
            for stock in range(10):
                pool.append({"stock_code": f"{stock:06d}", "as_of": as_of})
                if stock < round(rate * 10):
                    hits.append({"stock_code": f"{stock:06d}", "as_of": as_of})
        return pd.DataFrame(hits), pd.DataFrame(pool)

    def test_uniform_cross_sectional_engine_has_low_dispersion(self):
        hits, pool = self._frames([0.3, 0.3, 0.3, 0.3])
        result = diag.hit_concentration(hits, pool)
        assert result["std_rate"] == 0.0
        assert result["dates_above_high"] == 0
        assert result["dates_below_low"] == 0

    def test_calendar_switch_engine_is_flagged(self):
        """黄历那种"要么几乎全中、要么几乎不中"的形态必须被识别出来。"""
        hits, pool = self._frames([0.0, 0.9, 0.1, 0.8, 0.0, 0.9])
        result = diag.hit_concentration(hits, pool)
        assert result["min_rate"] == 0.0
        assert result["max_rate"] == 0.9
        assert result["dates_above_high"] == 3
        assert result["dates_below_low"] == 2
        assert result["std_rate"] > 0.35

    def test_empty_inputs_are_explicit(self):
        result = diag.hit_concentration(pd.DataFrame(), pd.DataFrame())
        assert result["date_count"] == 0
        assert result["std_rate"] is None
