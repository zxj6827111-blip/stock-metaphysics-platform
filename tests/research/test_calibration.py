"""Phase 3C Research Calibration Layer 测试。

Calibration 是研究派生层：不得改写原始 score / direction，也不得让 OOS 参与 fit。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.research.calibration import (
    ResearchCalibrationLayer,
    cross_sectional_percentile,
    rank_score,
    research_percentile,
    z_score,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"engine": "bazi", "birth_model": "listing_open_v1", "as_of": date(2018, 1, 1),
         "partition": "TRAIN", "opinion_score": 10.0, "raw_direction": -1, "rule_score": 2.0},
        {"engine": "bazi", "birth_model": "listing_open_v1", "as_of": date(2018, 2, 1),
         "partition": "TRAIN", "opinion_score": 20.0, "raw_direction": -1, "rule_score": 3.0},
        {"engine": "bazi", "birth_model": "listing_open_v1", "as_of": date(2018, 3, 1),
         "partition": "TRAIN", "opinion_score": 30.0, "raw_direction": 0, "rule_score": 4.0},
        {"engine": "bazi", "birth_model": "listing_open_v1", "as_of": date(2018, 4, 1),
         "partition": "TRAIN", "opinion_score": 40.0, "raw_direction": 1, "rule_score": 5.0},
    ])


class TestPrimitiveCalibration:
    def test_percentile_uses_average_rank_for_ties(self):
        assert research_percentile(2.0, [1.0, 2.0, 2.0, 4.0]) == pytest.approx(0.5)
        assert research_percentile(None, [1.0]) is None
        assert research_percentile(1.0, []) is None

    def test_cross_sectional_keeps_order_and_missing(self):
        out = cross_sectional_percentile([1.0, 2.0, None, 2.0])
        assert out[0] == pytest.approx(1 / 6)
        assert out[1] == pytest.approx(2 / 3)
        assert out[2] is None
        assert out[3] == pytest.approx(2 / 3)

    def test_rank_score_and_constant_z_score_are_explicit(self):
        assert rank_score(0.25) == 25.0
        assert rank_score(None) is None
        assert z_score(2.0, [2.0, 2.0]) is None


class TestTrainOnlyLayer:
    def test_fit_and_transform_adds_derived_columns_without_mutating_raw(self):
        source = _frame()
        original = source.copy(deep=True)
        layer = ResearchCalibrationLayer(
            value_col="opinion_score", group_cols=("engine", "birth_model"),
            fit_max_as_of=date(2018, 12, 31),
        ).fit(source)
        transformed = layer.transform(source)

        assert source.equals(original)
        assert transformed["opinion_score"].tolist() == original["opinion_score"].tolist()
        assert transformed["raw_direction"].tolist() == original["raw_direction"].tolist()
        assert transformed["rule_score"].tolist() == original["rule_score"].tolist()
        assert {"research_percentile", "cross_sectional_percentile", "historical_percentile",
                "z_score", "rank_score", "calibrated_direction", "calibration_status"} <= set(transformed)
        assert set(transformed["calibration_status"]) == {"ok"}

    def test_fit_rejects_validation_or_oos_rows(self):
        frame = _frame()
        frame.loc[0, "partition"] = "OOS"
        with pytest.raises(ValueError, match="只能使用 TRAIN"):
            ResearchCalibrationLayer("opinion_score", ("engine", "birth_model")).fit(frame)

    def test_fit_rejects_future_cutoff_and_future_label_columns(self):
        frame = _frame()
        frame.loc[0, "as_of"] = date(2019, 1, 1)
        with pytest.raises(ValueError, match="fit_max_as_of"):
            ResearchCalibrationLayer(
                "opinion_score", ("engine", "birth_model"), fit_max_as_of=date(2018, 12, 31)
            ).fit(frame)

        frame = _frame().assign(ret_20d=0.1)
        with pytest.raises(ValueError, match="未来标签"):
            ResearchCalibrationLayer("opinion_score", ("engine", "birth_model")).fit(frame)

    def test_oos_changes_cannot_change_frozen_train_thresholds(self):
        train = _frame()
        layer = ResearchCalibrationLayer(
            "opinion_score", ("engine", "birth_model"), fit_max_as_of=date(2018, 12, 31)
        ).fit(train)
        before = layer.metadata()
        oos = train.assign(partition="OOS", as_of=date(2023, 1, 1), opinion_score=1000.0)
        transformed = layer.transform(oos)
        assert layer.metadata() == before
        assert transformed["calibrated_direction"].iloc[0] == 1
        assert layer.groups[("bazi", "listing_open_v1")].upper_threshold == pytest.approx(32.5)

    def test_constant_train_is_unavailable_not_zero(self):
        frame = _frame()
        frame["opinion_score"] = 20.0
        layer = ResearchCalibrationLayer("opinion_score", ("engine", "birth_model")).fit(frame)
        out = layer.transform(frame)
        assert set(out["calibration_status"]) == {"unavailable_constant_train"}
        assert out["calibrated_direction"].isna().all()
        assert out["z_score"].isna().all()
