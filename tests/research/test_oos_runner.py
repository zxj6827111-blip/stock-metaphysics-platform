"""Phase 3D 执行器机制测试（合成面板，不依赖引擎与数据库）。

覆盖：
    * 命中掩码语义（缺失引擎不算命中；conflict 要求正为正、负为负）；
    * 事件表只保留有标签的命中；
    * 负对照的置换分布、Jaccard 诊断、退化检测；
    * 探索性对象不套用单向 gate；
    * ipo_approx 强制携带 IPO_APPROXIMATION_WARNING。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.oos import runner as R
from src.research.oos.registry import HypothesisSpec
from src.research.oos.splits import default_split


def _split():
    return default_split(calibration_version="cal-v1")


def _panel(birth_model: str = "listing_open_v1") -> pd.DataFrame:
    """40 只股票 × 4 个 OOS 季度点；bazi 全正、ziwei 半数正、huangli 反向。"""
    rows: list[dict] = []
    for stock_index in range(40):
        code = f"{stock_index:06d}"
        for _quarter, as_of in enumerate(
            (date(2023, 1, 1), date(2023, 7, 1), date(2024, 1, 1), date(2024, 7, 1))
        ):
            rows.append({
                "stock_code": code, "birth_model": birth_model, "as_of": as_of,
                "engine": "bazi", "opinion_score": 60.0, "raw_direction": 1,
                "partition": "OOS", "calibrated_direction": 1.0,
            })
            rows.append({
                "stock_code": code, "birth_model": birth_model, "as_of": as_of,
                "engine": "ziwei", "opinion_score": 60.0 if stock_index % 2 else 40.0,
                "raw_direction": 1 if stock_index % 2 else -1,
                "partition": "OOS",
                "calibrated_direction": 1.0 if stock_index % 2 else -1.0,
            })
            rows.append({
                "stock_code": code, "birth_model": birth_model, "as_of": as_of,
                "engine": "huangli", "opinion_score": 40.0, "raw_direction": -1,
                "partition": "OOS", "calibrated_direction": -1.0,
            })
    return pd.DataFrame(rows)


def _labels(panel: pd.DataFrame, *, effect: float = 0.0) -> pd.DataFrame:
    """构造标签：命中 bazi 的样本有 effect 的超额收益，其余为 0。

    ``trade_index`` 按"该 as_of 在采样网格中的序号 × 120 个交易日"给，
    与季度采样（约 63 个交易日）一致，因此 20D 窗口天然不重叠。
    """
    rng = np.random.default_rng(7)
    keys = panel[["stock_code", "as_of"]].drop_duplicates()
    grid = {value: position for position, value in enumerate(sorted(keys["as_of"].unique()))}
    rows: list[dict] = []
    for row in keys.itertuples():
        noise = float(rng.normal(0, 0.05))
        stock_bias = effect if int(row.stock_code) < 20 else effect / 2
        rows.append({
            "stock_code": row.stock_code, "as_of": row.as_of,
            "trade_date": row.as_of, "trade_index": grid[row.as_of] * 120,
            "ret_5d": noise, "ret_10d": noise, "ret_20d": noise, "ret_60d": noise,
            "excess_return_5d": noise, "excess_return_10d": noise,
            "excess_return_20d": noise + stock_bias, "excess_return_60d": noise,
            "bench_ret_5d": 0.0, "bench_ret_10d": 0.0, "bench_ret_20d": 0.0,
            "bench_ret_60d": 0.0,
            "label_version": "test", "is_degraded": False,
        })
    return pd.DataFrame(rows)


def _spec(**overrides) -> HypothesisSpec:
    payload = {
        "hypothesis_id": "HYP-TEST", "title": "t", "object_id": "bazi_calibrated",
        "engines": ("bazi",), "direction_source": "calibrated", "logic": "single",
        "birth_models": ("listing_open_v1",),
    }
    payload.update(overrides)
    return HypothesisSpec(**payload)


class TestEventConstruction:
    def test_direction_matrix_matches_calibrated_direction(self):
        mask = R.direction_matrix(
            _panel(), _spec(), birth_model="listing_open_v1", source="calibrated"
        )
        assert int(mask["hit"].sum()) == 160  # 40 股 × 4 期

    def test_missing_engine_is_not_a_hit(self):
        panel = _panel()
        panel = panel[~(panel["engine"] == "ziwei")]
        spec = _spec(
            engines=("bazi", "ziwei"), logic="all_positive",
            object_id="bazi_ziwei_calibrated",
        )
        mask = R.direction_matrix(
            panel, spec, birth_model="listing_open_v1", source="calibrated"
        )
        assert mask.empty or int(mask["hit"].sum()) == 0

    def test_conflict_logic_requires_positive_and_negative(self):
        spec = _spec(
            engines=("bazi", "ziwei"), logic="conflict",
            conflict={"positive": ["bazi"], "negative": ["ziwei"]},
            object_id="conflict_bazi_pos_ziwei_neg",
        )
        mask = R.direction_matrix(
            _panel(), spec, birth_model="listing_open_v1", source="calibrated"
        )
        assert int(mask["hit"].sum()) == 80  # 20 只 ziwei 为负的股票 × 4 期

    def test_events_require_labels(self):
        panel = _panel()
        labels = _labels(panel)
        mask = R.direction_matrix(
            panel, _spec(), birth_model="listing_open_v1", source="calibrated"
        )
        events = R.event_frame(mask, labels.iloc[:50])
        assert 0 < len(events) < int(mask["hit"].sum())


class TestControls:
    def test_permutation_control_reports_distribution_and_p(self):
        panel = _panel()
        labels = _labels(panel, effect=0.05)
        mask = R.direction_matrix(
            panel, _spec(), birth_model="listing_open_v1", source="calibrated"
        )
        events = R.event_frame(mask, labels)
        pool = mask[["stock_code", "as_of"]].merge(labels, on=["stock_code", "as_of"])
        outcome = R.random_event_position_control(
            events, pool, horizon=20, seed=1, draws=60,
        )
        assert outcome.decisive is True
        assert outcome.event_count == len(events)
        assert outcome.p_value is not None
        assert 0.0 <= outcome.p_value <= 1.0
        assert outcome.p_value_lower is not None and outcome.p_value_upper is not None
        assert outcome.jaccard_with_real is not None
        assert outcome.expected_overlap_fraction == pytest.approx(1.0)

    def test_random_birth_assignment_preserves_daily_count(self):
        panel = _panel()
        labels = _labels(panel)
        mask = R.direction_matrix(
            panel, _spec(), birth_model="listing_open_v1", source="calibrated"
        )
        events = R.event_frame(mask, labels)
        outcome = R.random_birth_assignment_control(
            panel, _spec(), birth_model="listing_open_v1", source="calibrated",
            labels=labels, partitions=("OOS",), horizon=20, seed=3,
            real_events=events, draws=40,
        )
        assert outcome.decisive is True
        assert outcome.event_count == len(events)  # 每日命中数守恒

    def test_shifted_birth_control_reports_jaccard_and_delta(self):
        panel = _panel()
        labels = _labels(panel)
        real = R.event_frame(
            R.direction_matrix(panel, _spec(), birth_model="listing_open_v1",
                               source="calibrated"),
            labels,
        )
        shifted = real.copy()
        shifted["excess_return_20d"] = shifted["excess_return_20d"] - 0.1
        outcome = R.shifted_birth_control(
            shifted, kind=R.CONTROL_SHIFT_MINUS_7, days=-7, real_events=real, horizon=20,
        )
        assert outcome.decisive is True
        assert outcome.jaccard_with_real == pytest.approx(1.0)  # 同集合、不同收益
        assert outcome.delta_mean_excess == pytest.approx(0.1, abs=1e-6)
        assert outcome.verdict == "outperform"

    def test_control_with_empty_pool_is_inconclusive(self):
        outcome = R.random_event_position_control(
            pd.DataFrame(), pd.DataFrame(), horizon=20, seed=1, draws=10,
        )
        assert outcome.decisive is False
        assert outcome.warnings


class TestRunHypothesis:
    def test_end_to_end_on_synthetic_panel(self):
        panel = _panel()
        labels = _labels(panel, effect=0.03)
        split = _split()
        outcome = R.run_hypothesis(
            calibrated_panel=panel, labels=labels, split=split, spec=_spec(),
            birth_model="listing_open_v1",
            calibration_audit={
                "calibration_version": "cal-v1", "fit_scope": "TRAIN_ONLY",
                "fit_max_as_of": "2018-12-31", "calibration_fit_hash": "abc",
            },
            permutation_draws=40,
        )
        assert outcome.partitioned["OOS"]["event_count"] == 160
        assert outcome.gate is not None
        assert outcome.gate.status.value in {
            "NO_SIGNAL", "INCONCLUSIVE", "WEAK_EVIDENCE", "OOS_CANDIDATE_SUPPORTED",
            "INVALID_CONTROL", "INSUFFICIENT_SAMPLE",
        }
        assert len(outcome.controls) == 3  # 位置 + 出生指派 + 随机方向
        assert outcome.overlap["overlap_ratio"] == 0.0  # 半年间隔 → 非重叠
        assert outcome.stock_dependency["top_1_contribution"] is not None

    def test_exploratory_spec_skips_the_one_sided_gate(self):
        panel = _panel()
        labels = _labels(panel)
        spec = _spec(
            logic="conflict", engines=("bazi", "huangli"),
            conflict={"positive": ["bazi"], "negative": ["huangli"]},
            object_id="conflict_bazi_pos_huangli_neg",
            expected_direction="exploratory",
        )
        outcome = R.run_hypothesis(
            calibrated_panel=panel, labels=labels, split=_split(), spec=spec,
            birth_model="listing_open_v1",
            calibration_audit={"calibration_version": "cal-v1", "fit_scope": "TRAIN_ONLY",
                               "fit_max_as_of": "2018-12-31", "calibration_fit_hash": "abc"},
            permutation_draws=20,
        )
        assert outcome.gate is None
        assert any("EXPLORATORY_NOT_GATED" in warning for warning in outcome.warnings)

    def test_ipo_approx_carries_approximation_warning(self):
        panel = _panel(birth_model="ipo_approx_v1")
        labels = _labels(panel)
        outcome = R.run_hypothesis(
            calibrated_panel=panel, labels=labels, split=_split(), spec=_spec(),
            birth_model="ipo_approx_v1",
            calibration_audit={"calibration_version": "cal-v1", "fit_scope": "TRAIN_ONLY",
                               "fit_max_as_of": "2018-12-31", "calibration_fit_hash": "abc"},
            permutation_draws=20,
        )
        assert any(
            "IPO_APPROXIMATION_WARNING" in warning for warning in outcome.warnings
        )

    def test_raw_source_uses_raw_direction(self):
        panel = _panel()
        labels = _labels(panel)
        spec = _spec(direction_source="raw", object_id="bazi_raw")
        outcome = R.run_hypothesis(
            calibrated_panel=panel, labels=labels, split=_split(), spec=spec,
            birth_model="listing_open_v1",
            calibration_audit={"calibration_version": "cal-v1", "fit_scope": "TRAIN_ONLY",
                               "fit_max_as_of": "2018-12-31", "calibration_fit_hash": "abc"},
            permutation_draws=20,
        )
        assert outcome.partitioned["OOS"]["event_count"] == 160

    def test_attach_calibration_never_mutates_raw_columns(self):
        panel = _panel()
        original = panel.copy(deep=True)

        class _StubLayer:
            calibration_version = "stub"

            def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
                out = frame.copy(deep=True)
                out["calibrated_direction"] = -1.0
                return out

        out = R.attach_calibration(panel, _StubLayer())
        assert panel.equals(original)
        assert out["calibrated_direction"].eq(-1.0).all()
