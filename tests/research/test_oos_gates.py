"""Phase 3D OOS 状态门测试（GOAL §15 十项条件 + 状态映射 + FDR 暂缓）。

状态门必须：
    1. 逐条给出可核对的检查记录（不是只给一个结论）；
    2. 任一项不通过时给出正确的状态（INVALID_CONTROL / NO_SIGNAL / …）；
    3. **永远不会**产出 SUPPORTED_OUT_OF_SAMPLE。
"""

from __future__ import annotations

from datetime import date

import pytest

from src.research.oos import gates as G
from src.research.oos.splits import ResearchSplit
from src.research.status import ResearchStatus


def _split() -> ResearchSplit:
    return ResearchSplit(
        train_start=date(2010, 1, 1), train_end=date(2018, 12, 31),
        validation_start=date(2019, 1, 1), validation_end=date(2022, 12, 31),
        oos_start=date(2023, 1, 1), oos_end=date(2026, 8, 14),
        calibration_version="cal-v1",
    )


def _control(**overrides) -> dict:
    base = {
        "control_kind": "random_event_position", "decisive": True,
        "jaccard_with_real": 0.2, "mean_excess_return": 0.0, "p_value": 0.001,
        "event_count": 900, "delta_mean_excess_vs_real": 0.03,
    }
    base.update(overrides)
    return base


def _happy_inputs(**overrides) -> dict:
    payload = {
        "split": _split(),
        "hypothesis_id": "HYP-TEST",
        "oos_stats": {
            "event_count": 900, "sample_count": 880, "mean_excess_return": 0.03,
            "mean_return": 0.04, "sign": 1, "cohen_d": 0.2,
        },
        "validation_stats": {
            "event_count": 700, "sample_count": 690, "mean_excess_return": 0.02, "sign": 1,
        },
        "controls": [_control()],
        "year_stability": {
            "year_count": 4, "positive_year_ratio": 0.75, "sign_consistency": 0.75,
        },
        "stock_dependency": {
            "top_1_contribution": 0.05, "top_5_contribution": 0.2,
            "loo_sign_flip_count": 0, "single_name_dependent": False,
        },
        "calibration_audit": {
            "fit_max_as_of": "2018-12-31", "fit_scope": "TRAIN_ONLY",
            "calibration_fit_hash": "deadbeef",
        },
        "data_is_real": True,
    }
    payload.update(overrides)
    return payload


class TestThresholdsAreFrozen:
    def test_gate_thresholds_are_declared_and_versioned(self):
        thresholds = G.gate_thresholds()
        assert thresholds["gate_version"] == "phase3d-oos-gate-v1"
        assert thresholds["alpha"] == pytest.approx(0.05)
        assert thresholds["max_control_jaccard"] == pytest.approx(0.9)
        assert thresholds["max_status_phase3d"] == ResearchStatus.OOS_CANDIDATE_SUPPORTED.value
        assert thresholds["fdr_deferred_to_phase"] == "3F"

    def test_max_status_is_not_out_of_sample(self):
        assert G.MAX_STATUS_PHASE3D is not ResearchStatus.SUPPORTED_OUT_OF_SAMPLE


class TestTenConditions:
    def test_all_conditions_pass_yields_candidate_with_pending_fdr(self):
        result = G.evaluate_oos_gate(**_happy_inputs())
        assert result.status is ResearchStatus.OOS_CANDIDATE_SUPPORTED
        assert result.pending_fdr is True
        assert result.fdr_applied is False
        assert len(result.checks) == 11  # 10 项 + Validation 样本量附加项
        assert all(check.passed for check in result.checks if check.blocking)

    def test_g1_synthetic_data_blocks_everything(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            data_is_real=False, data_problems=["synthetic_demo"],
        ))
        assert result.status is ResearchStatus.NO_REAL_DATA

    def test_g2_not_run_and_insufficient_sample(self):
        empty = _happy_inputs()
        empty["oos_stats"] = {"event_count": 0, "sample_count": 0, "sign": 0}
        assert G.evaluate_oos_gate(**empty).status is ResearchStatus.NOT_RUN

        tiny = _happy_inputs()
        tiny["oos_stats"] = {
            "event_count": 5, "sample_count": 5, "mean_excess_return": 0.1, "sign": 1,
        }
        assert G.evaluate_oos_gate(**tiny).status is ResearchStatus.INSUFFICIENT_SAMPLE

        small = _happy_inputs()
        small["oos_stats"] = {
            "event_count": G.MIN_OOS_EVENTS - 1, "sample_count": G.MIN_OOS_EVENTS - 1,
            "mean_excess_return": 0.03, "sign": 1, "cohen_d": 0.2,
        }
        assert G.evaluate_oos_gate(**small).status is ResearchStatus.INSUFFICIENT_SAMPLE

    def test_g3_invalid_control_when_jaccard_too_high(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            controls=[_control(jaccard_with_real=0.95)],
        ))
        assert result.status is ResearchStatus.INVALID_CONTROL

    def test_g3_inconclusive_when_no_decisive_control(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            controls=[_control(decisive=False, jaccard_with_real=None, p_value=None)],
        ))
        assert result.status is ResearchStatus.INCONCLUSIVE

    def test_g4_direction_mismatch_is_inconclusive(self):
        inputs = _happy_inputs()
        inputs["validation_stats"] = {
            "event_count": 700, "sample_count": 690, "mean_excess_return": -0.02, "sign": -1,
        }
        result = G.evaluate_oos_gate(**inputs)
        assert result.status is ResearchStatus.INCONCLUSIVE
        assert result.check("G4_direction_consistent_with_validation").passed is False

    def test_g5_no_signal_when_real_loses_to_control(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            controls=[_control(mean_excess_return=0.05)],
        ))
        assert result.status is ResearchStatus.NO_SIGNAL
        assert "样本外信息量" in " ".join(result.reasons)

    def test_g5_inconclusive_when_controls_disagree(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            controls=[
                _control(mean_excess_return=0.0),
                _control(control_kind="random_birth_assignment", mean_excess_return=0.09),
            ],
        ))
        assert result.status is ResearchStatus.INCONCLUSIVE

    def test_g6_zero_effect_size_downgrades_to_weak(self):
        inputs = _happy_inputs()
        inputs["oos_stats"] = {
            "event_count": 900, "sample_count": 880, "mean_excess_return": 0.03,
            "mean_return": 0.04, "sign": 1, "cohen_d": 0.0,
        }
        result = G.evaluate_oos_gate(**inputs)
        assert result.status is ResearchStatus.WEAK_EVIDENCE
        assert result.check("G6_effect_size_nonzero").passed is False

    def test_g7_insignificant_downgrades_to_weak(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            controls=[_control(p_value=0.4)],
        ))
        assert result.status is ResearchStatus.WEAK_EVIDENCE
        assert result.check("G7_significance").passed is False

    def test_g8_year_instability_downgrades_to_weak(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            year_stability={"year_count": 4, "positive_year_ratio": 0.25, "sign_consistency": 0.25},
        ))
        assert result.status is ResearchStatus.WEAK_EVIDENCE
        assert result.check("G8_year_stability").passed is False

    def test_g9_single_name_dependency_downgrades_to_weak(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            stock_dependency={
                "top_1_contribution": 0.8, "top_5_contribution": 0.99,
                "loo_sign_flip_count": 3, "single_name_dependent": True,
            },
        ))
        assert result.status is ResearchStatus.WEAK_EVIDENCE
        assert "SINGLE_NAME_DEPENDENT" in " ".join(result.reasons)

    def test_g10_calibration_leak_blocks_candidate(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            calibration_audit={
                "fit_max_as_of": "2020-01-01", "fit_scope": "TRAIN_ONLY",
                "calibration_fit_hash": "deadbeef",
            },
        ))
        assert result.status is ResearchStatus.INCONCLUSIVE
        assert result.check("G10_calibration_from_train").passed is False

    def test_g10_wrong_scope_blocks_candidate(self):
        result = G.evaluate_oos_gate(**_happy_inputs(
            calibration_audit={
                "fit_max_as_of": "2018-12-31", "fit_scope": "ALL",
                "calibration_fit_hash": "deadbeef",
            },
        ))
        assert result.check("G10_calibration_from_train").passed is False


class TestResultSerialization:
    def test_result_serializes_checks_and_flags(self):
        result = G.evaluate_oos_gate(**_happy_inputs())
        payload = result.to_dict()
        assert payload["status"] == "OOS_CANDIDATE_SUPPORTED"
        assert payload["pending_fdr"] is True
        assert payload["oos_used"] is True
        assert payload["gate_version"] == G.GATE_VERSION
        assert len(payload["checks"]) == len(result.checks)
        assert all({"name", "label", "passed", "detail"} <= set(c) for c in payload["checks"])

    def test_passed_property_only_for_supported_states(self):
        candidate = G.evaluate_oos_gate(**_happy_inputs())
        weak = G.evaluate_oos_gate(**_happy_inputs(controls=[_control(p_value=0.5)]))
        assert candidate.passed is True
        assert weak.passed is False
