"""Phase 3D Walk-forward 的 P0 规则测试：**每个 fold 只能用 fold 训练前缀拟合**。

GOAL §6 的核心违规形态是：

    global_calibrator.transform(all_test_years)      ← 用全体 TRAIN(2010–2018) 的阈值评估 2015
    fold_calibrator.fit(fold_train).transform(fold_test)   ← 唯一合法形态

本文件用"间谍校准层"直接观测每次 fit 的**真实日期集合**，因此如果实现里
偷偷用了全 TRAIN（或任何越界数据），测试会失败，而不是仅仅"看起来没问题"。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.research.calibration import ResearchCalibrationLayer
from src.research.oos import walk_forward as wf
from src.research.oos.splits import ResearchSplit, SplitContractError


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start=date(2010, 1, 1), train_end=date(2018, 12, 31),
        validation_start=date(2019, 1, 1), validation_end=date(2022, 12, 31),
        oos_start=date(2023, 1, 1), oos_end=date(2026, 8, 14),
        calibration_version="cal-v1",
    )


def _panel() -> pd.DataFrame:
    """构造"分布随时间漂移"的面板：后段得分远高于前段。

    这样"用了哪一段拟合"会直接改变阈值，测试才有分辨力。
    """
    rows: list[dict] = []
    for year in range(2010, 2027):
        offset = 0.0 if year <= 2014 else 100.0
        for month in (1, 4, 7, 10):
            for index in range(40):
                rows.append({
                    "engine": "bazi",
                    "birth_model": "listing_open_v1",
                    "as_of": date(year, month, 1),
                    "partition": "TRAIN" if year <= 2018 else (
                        "VALIDATION" if year <= 2022 else "OOS"
                    ),
                    "opinion_score": float(index) + offset,
                    "raw_direction": 1,
                })
    return pd.DataFrame(rows)


class _SpyLayer(ResearchCalibrationLayer):
    """记录 fit / transform 帧的真实日期范围（用于证明无泄漏）。"""

    observations: dict[str, dict] = {}

    def fit(self, frame: pd.DataFrame) -> _SpyLayer:  # type: ignore[override]
        dates = pd.to_datetime(frame["as_of"]).dt.date
        _SpyLayer.observations[self.calibration_version] = {
            "fit_min": min(dates), "fit_max": max(dates), "fit_rows": int(len(frame)),
        }
        return super().fit(frame)

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:  # type: ignore[override]
        dates = pd.to_datetime(frame["as_of"]).dt.date
        record = _SpyLayer.observations.setdefault(self.calibration_version, {})
        record["transform_min"] = min(dates) if len(dates) else None
        record["transform_max"] = max(dates) if len(dates) else None
        record["transform_rows"] = int(len(frame))
        return super().transform(frame)


class TestFoldGeneration:
    def test_expanding_window_is_strictly_ordered(self):
        folds = wf.expanding_folds(_split(), min_train_years=5)
        assert [fold.fold_id for fold in folds][0] == "WF-2015"
        assert [fold.fold_id for fold in folds][-1] == "WF-2026"
        assert len(folds) == 12
        previous_end = None
        for fold in folds:
            assert fold.train_end < fold.test_start
            assert fold.train_start == date(2010, 1, 1)
            if previous_end is not None:
                assert fold.train_end > previous_end  # 扩窗单调
            previous_end = fold.train_end
        assert folds[-1].test_end == date(2026, 8, 14)  # 最后一年是部分区间

    def test_first_fold_can_be_deferred_and_is_recorded(self):
        late = wf.expanding_folds(_split(), min_train_years=7)
        assert late[0].fold_id == "WF-2017"

    def test_fold_rejects_reversed_time(self):
        with pytest.raises(SplitContractError):
            wf.WalkForwardFold(
                fold_id="BAD", train_start=date(2015, 1, 1), train_end=date(2015, 12, 31),
                test_start=date(2015, 1, 1), test_end=date(2015, 12, 31),
                calibration_version="x",
            )


class TestFoldTrainOnlyCalibration:
    def test_walkforward_calibration_uses_fold_train_only(self, monkeypatch):
        """P0：每个 fold 的 fit 帧必须止于该 fold 的 train_end，transform 帧必须在其后。"""
        monkeypatch.setattr(wf, "ResearchCalibrationLayer", _SpyLayer)
        _SpyLayer.observations = {}
        panel = _panel()
        folds = wf.expanding_folds(
            _split(), min_train_years=5, first_test_year=2015, last_test_year=2017
        )
        result = wf.run_walk_forward(
            panel, folds,
            evaluator=lambda fold, frame: {"test_rows": int(len(frame))},
            value_col="opinion_score", group_cols=("engine", "birth_model"),
        )
        assert len(result.folds) == len(folds)
        for fold in folds:
            observation = _SpyLayer.observations[fold.calibration_version]
            assert observation["fit_max"] <= fold.train_end, (
                f"{fold.fold_id} 的 fit 用到了 {observation['fit_max']}（越界）"
            )
            assert observation["transform_min"] > fold.train_end, (
                f"{fold.fold_id} 的 transform 含训练期样本"
            )
            assert observation["transform_min"] >= fold.test_start
            assert observation["transform_max"] <= fold.test_end

    def test_fold_thresholds_come_from_prefix_not_global_train(self, monkeypatch):
        """fold 2015 的阈值必须等于 2010–2014 前缀的 P75，而不是全 TRAIN 的 P75。"""
        monkeypatch.setattr(wf, "ResearchCalibrationLayer", _SpyLayer)
        _SpyLayer.observations = {}
        panel = _panel()
        folds = wf.expanding_folds(
            _split(), min_train_years=5, first_test_year=2015, last_test_year=2015
        )
        fold = folds[0]
        layer, audit = wf.fit_fold_calibration(
            panel, fold,
            value_col="opinion_score", group_cols=("engine", "birth_model"),
        )
        key = ("bazi", "listing_open_v1")
        prefix_p75 = 39.0 * 0.75  # 前段得分 0..39
        global_p75 = 139.0 * 0.75  # 全 TRAIN 得分 0..139
        assert layer.groups[key].upper_threshold == pytest.approx(prefix_p75, rel=1e-6)
        assert layer.groups[key].upper_threshold != pytest.approx(global_p75, rel=1e-3)
        assert audit["fit_actual_max_as_of"] <= "2014-12-31"
        assert audit["fit_partitions"] == ["TRAIN"]

    def test_fit_hash_differs_across_folds(self, monkeypatch):
        monkeypatch.setattr(wf, "ResearchCalibrationLayer", _SpyLayer)
        _SpyLayer.observations = {}
        panel = _panel()
        folds = wf.expanding_folds(_split(), min_train_years=5)
        result = wf.run_walk_forward(
            panel, folds, evaluator=lambda fold, frame: {},
            value_col="opinion_score", group_cols=("engine", "birth_model"),
        )
        hashes = [record["calibration_fit_hash"] for record in result.folds]
        assert len(set(hashes)) == len(hashes)
        assert result.summary["fold_calibration_refit"] is True

    def test_layer_rejects_fit_beyond_bound(self):
        """底层第二道闸门：显式 bound 之外的样本必须 raise，而不是被静默使用。"""
        frame = _panel()
        layer = ResearchCalibrationLayer(
            value_col="opinion_score", group_cols=("engine", "birth_model"),
            calibration_version="cal-wf-test", fit_max_as_of=date(2014, 12, 31),
        )
        with pytest.raises(ValueError):
            layer.fit(frame)

    def test_transform_guard_rejects_training_rows(self):
        """防御性闸门：即使 fold 被伪造（绕过构造校验），transform 也必须拒绝训练期样本。"""
        panel = _panel()
        folds = wf.expanding_folds(
            _split(), min_train_years=5, first_test_year=2015, last_test_year=2015
        )
        fold = folds[0]
        layer, _audit = wf.fit_fold_calibration(
            panel, fold, value_col="opinion_score", group_cols=("engine", "birth_model"),
        )

        class _UncheckedFold(wf.WalkForwardFold):
            def __post_init__(self) -> None:
                pass  # 故意跳过时间顺序校验，模拟"被伪造的 fold"

        forged = _UncheckedFold(
            fold_id="FORGED", train_start=fold.train_start, train_end=fold.train_end,
            test_start=date(2014, 1, 1), test_end=date(2015, 12, 31),
            calibration_version=fold.calibration_version,
        )
        with pytest.raises(wf.WalkForwardLeakError):
            wf.transform_fold(panel, forged, layer)

    def test_fit_partitions_recorded_for_expanding_window(self):
        """跨过 holdout Validation 分区的扩窗必须如实记录使用了哪些分区。"""
        panel = _panel()
        folds = wf.expanding_folds(
            _split(), min_train_years=5, first_test_year=2020, last_test_year=2020
        )
        _layer, audit = wf.fit_fold_calibration(
            panel, folds[0], value_col="opinion_score",
            group_cols=("engine", "birth_model"),
        )
        assert audit["fit_partitions"] == ["TRAIN", "VALIDATION"]
        assert audit["fit_actual_max_as_of"] <= "2019-12-31"
        assert audit["freeze_bound_exceeded"] is True  # 已越过 cal-v1 上界，必须留痕

    def test_fold_cannot_reuse_frozen_holdout_calibration_version(self):
        """P0：fold 不得复用 cal-v1（全 TRAIN 拟合）作为自己的校准版本。"""
        panel = _panel()
        fold = wf.WalkForwardFold(
            fold_id="BAD-CAL", train_start=date(2010, 1, 1), train_end=date(2014, 12, 31),
            test_start=date(2015, 1, 1), test_end=date(2015, 12, 31),
            calibration_version="cal-v1",
        )
        with pytest.raises(wf.WalkForwardLeakError):
            wf.fit_fold_calibration(
                panel, fold, value_col="opinion_score",
                group_cols=("engine", "birth_model"),
            )
