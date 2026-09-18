"""Event Study 测试（architecture §16）。

覆盖：
* 单因子 / 多因子组合（any / all）；
* 输出 sample_count / up_rate / mean_return / median_return / excess_return / max_drawdown；
* 5D / 10D / 20D / 60D 多持有期；
* 过滤条件（direction / min_rule_score / 日期区间 / 股票池）；
* activation 语义（事件必须"结构成立"才算命中，否则负对照无意义）；
* 样本不足必须如实说明。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.core.schemas.market import EventStudyRequest
from src.research.event_study.engine import (
    build_labels_frame,
    build_observations_frame,
    compute_horizon_stats,
    distribution,
    evaluate_event_study,
    mean_return_by_year,
)


def _obs(rows: list[tuple[str, date, str, int, float, float]]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "stock_code": code, "trade_date": d, "as_of": datetime(d.year, d.month, d.day),
            "factor_id": fid, "direction": direction, "rule_score": score,
            "normalized_value": norm, "availability": "ok",
        }
        for code, d, fid, direction, score, norm in rows
    ])


def _labels(rows: list[tuple[str, date, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "stock_code": code, "trade_date": d, "as_of": datetime(d.year, d.month, d.day),
            "ret_5d": r / 4, "ret_10d": r / 2, "ret_20d": r, "ret_60d": r * 2,
            "max_return_20d": r + 0.05, "max_drawdown_20d": -0.08,
            "excess_return_20d": r - 0.01, "bench_ret_20d": 0.01,
        }
        for code, d, r, _mr, _dd in rows
    ])


class TestHorizonStats:
    def test_basic_stats(self):
        df = pd.DataFrame({"ret_20d": [0.1, -0.05, 0.2, 0.0, -0.1]})
        stats = compute_horizon_stats(df, 20)
        assert stats.sample_count == 5
        assert stats.up_rate == pytest.approx(2 / 5)
        assert stats.mean_return == pytest.approx(0.03)
        assert stats.median_return == pytest.approx(0.0)

    def test_empty_returns_zero_sample(self):
        stats = compute_horizon_stats(pd.DataFrame({"ret_20d": []}), 20)
        assert stats.sample_count == 0
        assert stats.up_rate is None
        assert "无有效样本" in stats.note

    def test_missing_column(self):
        stats = compute_horizon_stats(pd.DataFrame({"ret_5d": [0.1]}), 20)
        assert stats.sample_count == 0
        assert "缺少字段" in stats.note

    def test_small_sample_note(self):
        df = pd.DataFrame({"ret_20d": [0.01] * 5})
        stats = compute_horizon_stats(df, 20)
        assert "低于阈值" in stats.note

    def test_nan_dropped(self):
        df = pd.DataFrame({"ret_20d": [0.1, np.nan, 0.2]})
        stats = compute_horizon_stats(df, 20)
        assert stats.sample_count == 2

    def test_excess_and_drawdown_only_on_20d(self):
        """超额收益/回撤只在 20D 输出，避免指标口径错配。"""
        df = pd.DataFrame({
            "ret_5d": [0.01, 0.02], "ret_20d": [0.05, 0.06],
            "excess_return_20d": [0.02, 0.03], "max_drawdown_20d": [-0.1, -0.2],
            "max_return_20d": [0.1, 0.12],
        })
        s5 = compute_horizon_stats(df, 5)
        s20 = compute_horizon_stats(df, 20)
        assert s5.mean_excess_return is None
        assert s5.max_drawdown is None
        assert s20.mean_excess_return is not None
        assert s20.max_drawdown is not None


class TestEventStudy:
    def test_single_factor(self):
        obs = _obs([("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8)] * 3)
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.15, -0.05),
        ])
        result = evaluate_event_study(obs, labels, EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[5, 10, 20, 60]))
        assert result.event_count == 1
        assert len(result.horizons) == 4
        h20 = next(h for h in result.horizons if h.horizon == 20)
        assert h20.sample_count == 1
        assert h20.mean_return == pytest.approx(0.10)

    def test_direction_filter(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8),
            ("600519", date(2020, 1, 3), "B_NATAL_001", -1, -8.0, -0.8),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 1, 3), -0.10, 0.1, -0.05),
        ])
        pos = evaluate_event_study(
            obs, labels, EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[20], direction_filter=1)
        )
        assert pos.event_count == 1

    def test_activation_nonzero_excludes_neutral(self):
        """normalized_value 为 0 的观测（闲神/中性）不应计入事件。"""
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_MONTH_001", 1, 8.0, 1.0),
            ("600519", date(2020, 1, 3), "B_MONTH_001", 0, 0.0, 0.0),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 1, 3), 0.20, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels, EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20])
        )
        assert result.event_count == 1

    def test_activation_any_counts_everything(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_MONTH_001", 1, 8.0, 1.0),
            ("600519", date(2020, 1, 3), "B_MONTH_001", 0, 0.0, 0.0),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 1, 3), 0.20, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels,
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20], activation="any"),
        )
        assert result.event_count == 2

    def test_multi_factor_any(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8),
            ("600519", date(2020, 1, 3), "B_MONTH_001", 1, 7.0, 0.7),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 1, 3), 0.20, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels,
            EventStudyRequest(factor_ids=["B_NATAL_001", "B_MONTH_001"], horizons=[20], logic="any"),
        )
        assert result.event_count == 2

    def test_multi_factor_all(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8),
            ("600519", date(2020, 1, 2), "B_MONTH_001", 1, 7.0, 0.7),
            ("600519", date(2020, 1, 3), "B_NATAL_001", 1, 8.0, 0.8),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 1, 3), 0.20, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels,
            EventStudyRequest(factor_ids=["B_NATAL_001", "B_MONTH_001"], horizons=[20], logic="all"),
        )
        assert result.event_count == 1

    def test_date_range_filter(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8),
            ("600519", date(2020, 6, 3), "B_NATAL_001", 1, 8.0, 0.8),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 6, 3), 0.20, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels,
            EventStudyRequest(
                factor_ids=["B_NATAL_001"], horizons=[20],
                date_from=date(2020, 5, 1), date_to=date(2020, 12, 31),
            ),
        )
        assert result.event_count == 1
        assert result.date_from >= date(2020, 5, 1)

    def test_stock_universe_filter(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8),
            ("000001", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("000001", date(2020, 1, 2), -0.10, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels,
            EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[20], stock_codes=["000001"]),
        )
        assert result.event_count == 1

    def test_min_rule_score_filter(self):
        obs = _obs([
            ("600519", date(2020, 1, 2), "B_NATAL_001", 1, 9.0, 0.9),
            ("600519", date(2020, 1, 3), "B_NATAL_001", 1, 2.0, 0.2),
        ])
        labels = _labels([
            ("600519", date(2020, 1, 2), 0.10, 0.1, -0.05),
            ("600519", date(2020, 1, 3), 0.20, 0.1, -0.05),
        ])
        result = evaluate_event_study(
            obs, labels,
            EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[20], min_rule_score=5.0),
        )
        assert result.event_count == 1

    def test_empty_observations(self):
        result = evaluate_event_study(
            pd.DataFrame(), pd.DataFrame(), EventStudyRequest(horizons=[20])
        )
        assert result.event_count == 0
        assert any(w.code == "ES_NO_OBSERVATION" for w in result.warnings)

    def test_methodology_documents_activation(self):
        obs = _obs([("600519", date(2020, 1, 2), "B_NATAL_001", 1, 8.0, 0.8)])
        labels = _labels([("600519", date(2020, 1, 2), 0.10, 0.1, -0.05)])
        result = evaluate_event_study(obs, labels, EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[20]))
        assert "activation=nonzero" in result.methodology
        assert "不含未来" in result.methodology or "持有期" in result.methodology


class TestAuxiliaryAnalytics:
    def test_mean_return_by_year(self):
        df = pd.DataFrame({
            "trade_date": [date(2020, 1, 2), date(2020, 6, 2), date(2021, 1, 4)],
            "ret_20d": [0.1, 0.2, -0.1],
        })
        out = mean_return_by_year(df, 20)
        assert out[2020] == pytest.approx(0.15)
        assert out[2021] == pytest.approx(-0.1)

    def test_distribution(self):
        df = pd.DataFrame({"ret_20d": np.random.default_rng(0).normal(0, 0.1, 500)})
        out = distribution(df, 20, bins=11)
        assert len(out["counts"]) == 11
        assert sum(out["counts"]) == 500

    def test_distribution_empty(self):
        out = distribution(pd.DataFrame({"ret_20d": []}), 20)
        assert out == {"bin_edges": [], "counts": []}

    def test_frame_builders(self):
        obs = build_observations_frame([{
            "stock_code": "600519", "trade_date": date(2020, 1, 2),
            "as_of": datetime(2020, 1, 2), "factor_id": "B_NATAL_001",
            "direction": 1, "rule_score": 8.0,
        }])
        assert obs["trade_date"].iloc[0] == date(2020, 1, 2)
        labels = build_labels_frame([{
            "stock_code": "600519", "trade_date": date(2020, 1, 2), "ret_20d": 0.1,
        }])
        assert labels["trade_date"].iloc[0] == date(2020, 1, 2)
