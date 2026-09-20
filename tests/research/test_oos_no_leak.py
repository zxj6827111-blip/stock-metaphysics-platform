"""Phase 3D 防未来数据泄漏测试（GOAL §23 全清单）。

清单与本文件对应关系：

    test_train_cannot_read_validation       ← TestPartitionIsolation
    test_train_cannot_read_oos
    test_validation_cannot_fit_oos
    test_walkforward_calibration_uses_fold_train_only  ← 也在 test_walk_forward.py 中单列
    test_oos_labels_not_used_during_selection
    test_oos_gate_is_frozen
    test_birth_profile_asof_safe
    test_market_label_asof_safe

这里的"能不能读"不是靠调用方自觉，而是靠**模块结构**：标签只能由
``src/research/labels/`` 生成；校准只能 fit TRAIN（layer 内置断言）；
fold 只能 fit 训练前缀（walk_forward 内置断言）；状态门阈值写死在 gates.py。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.research.calibration import ResearchCalibrationLayer
from src.research.labels.horizon_returns import (
    BenchmarkSeries,
    compute_forward_returns,
)
from src.research.oos import gates as G
from src.research.oos import runner as R
from src.research.oos import walk_forward as wf
from src.research.oos.calibration_freeze import (
    FREEZE_V1,
    CalibrationFreezeError,
)
from src.research.oos.registry import load_hypothesis_registry
from src.research.oos.splits import ResearchSplit, SplitContractError, default_split
from src.research.status import ResearchStatus


def _split() -> ResearchSplit:
    return default_split(calibration_version="cal-v1")


def _panel() -> pd.DataFrame:
    rows: list[dict] = []
    for year, partition in (
        (2013, "TRAIN"), (2014, "TRAIN"), (2015, "TRAIN"), (2016, "TRAIN"),
        (2020, "VALIDATION"), (2024, "OOS"),
    ):
        for index in range(20):
            rows.append({
                "engine": "bazi", "birth_model": "listing_open_v1",
                "as_of": date(year, 6, 1), "partition": partition,
                "opinion_score": float(50 + index), "raw_direction": 1,
                "stock_code": f"{index:06d}",
            })
    return pd.DataFrame(rows)


class TestPartitionIsolation:
    def test_split_rejects_reversed_time(self):
        with pytest.raises(SplitContractError):
            ResearchSplit(
                train_start=date(2010, 1, 1), train_end=date(2019, 12, 31),
                validation_start=date(2019, 1, 1), validation_end=date(2022, 12, 31),
                oos_start=date(2023, 1, 1), oos_end=date(2026, 8, 14),
            )
        with pytest.raises(SplitContractError):
            ResearchSplit(
                train_start=date(2010, 1, 1), train_end=date(2018, 12, 31),
                validation_start=date(2019, 1, 1), validation_end=date(2023, 6, 30),
                oos_start=date(2023, 1, 1), oos_end=date(2026, 8, 14),
            )

    def test_train_cannot_read_validation(self):
        """TRAIN 区间断言必须拒绝任何 Validation 日期。"""
        split = _split()
        split.assert_partition("TRAIN", [date(2018, 12, 31)])
        with pytest.raises(SplitContractError):
            split.assert_partition("TRAIN", [date(2018, 12, 31), date(2019, 1, 1)])

    def test_train_cannot_read_oos(self):
        split = _split()
        with pytest.raises(SplitContractError):
            split.assert_partition("TRAIN", [date(2024, 6, 1)])
        with pytest.raises(SplitContractError):
            split.assert_partition("VALIDATION", [date(2023, 1, 1)])

    def test_validation_cannot_fit_oos(self):
        """Validation 行不得进入 cal-v1 的 fit（layer 只接受 TRAIN 分区）。"""
        frame = _panel()
        layer = ResearchCalibrationLayer(
            "opinion_score", ("engine", "birth_model"), fit_max_as_of=date(2018, 12, 31)
        )
        with pytest.raises(ValueError):
            layer.fit(frame)  # 含 VALIDATION / OOS 行
        train_only = frame[frame["partition"] == "TRAIN"]
        layer.fit(train_only)  # 只喂 TRAIN 时才允许
        assert layer.fitted

    def test_freeze_rejects_fit_beyond_train(self):
        with pytest.raises(CalibrationFreezeError):
            FREEZE_V1.assert_fit_within_train(fit_max_as_of=date(2019, 1, 1))
        with pytest.raises(CalibrationFreezeError):
            FREEZE_V1.assert_partition("VALIDATION")
        FREEZE_V1.assert_fit_within_train(fit_max_as_of=date(2018, 12, 31))

    def test_out_of_scope_samples_are_rejected(self):
        rows = _panel().to_dict("records")
        rows.append({
            "engine": "bazi", "birth_model": "listing_open_v1",
            "as_of": date(2005, 6, 1), "partition": "OUT_OF_SCOPE",
            "opinion_score": 50.0, "raw_direction": 1, "stock_code": "000001",
        })
        panel = R.build_observation_panel(rows, _split())
        with pytest.raises(R.PanelError):
            R.assert_no_out_of_scope(panel, _split())


class TestSelectionAndGateDiscipline:
    def test_oos_labels_not_used_during_selection(self):
        """假设注册表必须在"未读取 OOS 标签"状态下冻结。"""
        registry = load_hypothesis_registry(
            "config/phase3d_hypothesis_registry.yaml"
        )
        assert registry.oos_labels_seen_at_registration is False
        assert registry.frozen_at, "预注册必须带冻结时间戳"
        for spec in registry.hypotheses:
            assert spec.primary_horizon == 20
            assert 20 in spec.horizons
            assert spec.birth_models, f"{spec.hypothesis_id} 未声明出生模型"
        assert _split().oos_labels_seen is False

    def test_oos_gate_is_frozen(self):
        """状态门阈值必须冻结且不可能产出 SUPPORTED_OUT_OF_SAMPLE。"""
        thresholds = G.gate_thresholds()
        assert thresholds["gate_version"] == G.GATE_VERSION
        assert thresholds["max_status_phase3d"] == "OOS_CANDIDATE_SUPPORTED"
        assert thresholds["fdr_deferred_to_phase"] == "3F"
        assert G.MAX_STATUS_PHASE3D is not ResearchStatus.SUPPORTED_OUT_OF_SAMPLE

        # 构造"十项全过"的输入：结果仍只能是候选状态
        result = G.evaluate_oos_gate(
            split=_split().with_oos_used(notes="test"),
            hypothesis_id="HYP-TEST",
            oos_stats={
                "event_count": 500, "sample_count": 500, "mean_excess_return": 0.03,
                "mean_return": 0.04, "sign": 1, "cohen_d": 0.2,
            },
            validation_stats={
                "event_count": 400, "sample_count": 400, "mean_excess_return": 0.02, "sign": 1,
            },
            controls=[{
                "control_kind": "random_event_position", "decisive": True,
                "jaccard_with_real": 0.2, "mean_excess_return": 0.0,
                "p_value": 0.001, "event_count": 500,
            }],
            year_stability={
                "year_count": 4, "positive_year_ratio": 1.0, "sign_consistency": 1.0,
            },
            stock_dependency={
                "top_1_contribution": 0.05, "top_5_contribution": 0.2,
                "loo_sign_flip_count": 0, "single_name_dependent": False,
            },
            calibration_audit={
                "fit_max_as_of": "2018-12-31", "fit_scope": "TRAIN_ONLY",
                "calibration_fit_hash": "abc123",
            },
        )
        assert result.status is ResearchStatus.OOS_CANDIDATE_SUPPORTED
        assert result.pending_fdr is True
        assert result.fdr_applied is False
        assert result.status is not ResearchStatus.SUPPORTED_OUT_OF_SAMPLE
        assert all(check.passed for check in result.checks)

    def test_high_jaccard_control_is_invalid_not_silently_accepted(self):
        result = G.evaluate_oos_gate(
            split=_split(), hypothesis_id="HYP-TEST",
            oos_stats={"event_count": 500, "sample_count": 500,
                       "mean_excess_return": 0.03, "sign": 1, "cohen_d": 0.2},
            validation_stats={"event_count": 400, "mean_excess_return": 0.02, "sign": 1},
            controls=[{
                "control_kind": "random_event_position", "decisive": True,
                "jaccard_with_real": 0.96, "mean_excess_return": 0.0, "p_value": 0.4,
            }],
            year_stability={"year_count": 4, "positive_year_ratio": 1.0, "sign_consistency": 1.0},
            stock_dependency={"top_1_contribution": 0.05, "loo_sign_flip_count": 0},
            calibration_audit={"fit_max_as_of": "2018-12-31", "fit_scope": "TRAIN_ONLY",
                               "calibration_fit_hash": "abc"},
        )
        assert result.status is ResearchStatus.INVALID_CONTROL


class TestAsOfSafety:
    def test_market_label_asof_safe(self):
        """标签只能向后读；数据不足时必须为 None（不得填 0）。"""
        bars = pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=30, freq="B"),
            "close": [10.0 + index for index in range(30)],
        })
        rows = compute_forward_returns(
            bars, [date(2020, 1, 1)], stock_code="000001",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["ret_5d"] is not None and row["ret_60d"] is None  # 60D 未来数据不足
        assert row["horizon_available"]["60d"] is False
        # 数据末端之后的 as_of 不产出任何行（不产出 = 不可用）
        assert compute_forward_returns(bars, [date(2021, 1, 1)], stock_code="000001") == []

    def test_excess_return_uses_same_calendar_window(self):
        bars = pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=40, freq="B"),
            "close": [10.0 * (1.01 ** index) for index in range(40)],
        })
        bench = BenchmarkSeries.from_frame(pd.DataFrame({
            "trade_date": pd.date_range("2020-01-01", periods=40, freq="B"),
            "close": [100.0] * 40,
        }), code="000300")
        row = compute_forward_returns(
            bars, [date(2020, 1, 1)], stock_code="000001", benchmark=bench,
        )[0]
        assert row["bench_ret_20d"] == 0.0
        assert row["excess_return_20d"] == pytest.approx(row["ret_20d"])

    def test_birth_profile_asof_safe(self):
        """出生档案必须早于 as_of：出生晚于 as_of 的样本不得产出观测。"""
        from scripts.phase3d_collect_panel import PanelCollector

        collector = PanelCollector(
            ["000001"], {("000001", "listing_open_v1"): pd.Timestamp("2020-06-01").to_pydatetime()},
            eligibility={"000001": (date(2020, 6, 1), None)},
            skip_ziwei=True,
        )
        assert collector.pit_eligible("000001", date(2020, 5, 31)) is False
        assert collector.skipped_pit["before_list"] == 1
        assert collector.pit_eligible("000001", date(2020, 6, 1)) is True
        # 退市后不可再产生事件（PIT 资格窗口上界）
        collector_delisted = PanelCollector(
            ["000002"], {("000002", "listing_open_v1"): pd.Timestamp("2000-01-01").to_pydatetime()},
            eligibility={"000002": (date(2000, 1, 1), date(2015, 6, 30))},
            skip_ziwei=True,
        )
        assert collector_delisted.pit_eligible("000002", date(2015, 6, 30)) is True
        assert collector_delisted.pit_eligible("000002", date(2016, 1, 1)) is False
        assert collector_delisted.skipped_pit["after_delist"] == 1


class TestFoldIsolation:
    def test_walkforward_calibration_uses_fold_train_only(self):
        """与 test_walk_forward.py 同名的 P0 断言（在此保留一份最简版本）。"""
        panel = _panel()
        folds = wf.expanding_folds(
            _split(), min_train_years=3, first_test_year=2016, last_test_year=2016
        )
        fold = folds[0]
        layer, audit = wf.fit_fold_calibration(
            panel, fold, value_col="opinion_score", group_cols=("engine", "birth_model"),
        )
        assert audit["fit_actual_max_as_of"] <= fold.train_end.isoformat()
        assert audit["calibration_version"] == "cal-wf-2016"
        assert layer.calibration_version != FREEZE_V1.calibration_version
        transformed = wf.transform_fold(panel, fold, layer)
        assert len(transformed) > 0
        assert pd.to_datetime(transformed["as_of"]).dt.date.min() > fold.train_end
