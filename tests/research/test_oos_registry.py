"""Phase 3D 假设预注册与实验登记测试。

要点：
    * 假设定义必须先于 OOS 读取（``oos_labels_seen_at_registration = False``）；
    * 预注册内容非法时（未知方向来源 / 探索性冲突组合缺定义）必须立刻失败；
    * 实验记录必须携带全部版本信息，并能写进 CSV 与既有 DB 表（不改 schema）。
"""

from __future__ import annotations

import json

import pytest

from src.research.oos.registry import (
    ExperimentRecord,
    HypothesisSpec,
    load_hypothesis_registry,
    new_experiment_id,
    persist_experiments,
    write_experiment_registry_csv,
)

REGISTRY_PATH = "config/phase3d_hypothesis_registry.yaml"


class TestHypothesisRegistry:
    def test_registry_loads_and_is_pre_registered(self):
        registry = load_hypothesis_registry(REGISTRY_PATH)
        assert registry.version == "phase3d-hypotheses-v1"
        assert registry.oos_labels_seen_at_registration is False
        assert len(registry.hypotheses) >= 10
        assert "HYP-BZ-RAW-001" in registry.ids()
        assert "HYP-BZ-CAL-001" in registry.ids()
        assert "HYP-CON-ALL3-CAL-001" in registry.ids()

    def test_required_hypotheses_from_goal_are_present(self):
        registry = load_hypothesis_registry(REGISTRY_PATH)
        for hypothesis_id in (
            "HYP-BZ-RAW-001", "HYP-BZ-CAL-001", "HYP-ZW-CAL-001", "HYP-HL-CAL-001",
            "HYP-CON-BZ-ZW-CAL-001", "HYP-CON-ALL3-CAL-001",
        ):
            spec = registry.by_id(hypothesis_id)
            assert spec.primary_horizon == 20
            assert spec.horizons == (5, 10, 20, 60)
            assert len(spec.birth_models) == 3
            assert "random_event_position" in spec.control_kinds

    def test_ipo_approx_is_covered_by_every_hypothesis(self):
        registry = load_hypothesis_registry(REGISTRY_PATH)
        for spec in registry.hypotheses:
            assert "ipo_approx_v1" in spec.birth_models

    def test_conflict_hypotheses_are_exploratory(self):
        registry = load_hypothesis_registry(REGISTRY_PATH)
        conflicts = [spec for spec in registry.hypotheses if spec.logic == "conflict"]
        assert len(conflicts) == 4
        for spec in conflicts:
            assert spec.expected_direction == "exploratory"
            assert spec.conflict and spec.conflict.get("positive")
            assert spec.conflict and spec.conflict.get("negative")

    def test_unknown_hypothesis_raises(self):
        registry = load_hypothesis_registry(REGISTRY_PATH)
        with pytest.raises(KeyError):
            registry.by_id("HYP-DOES-NOT-EXIST")

    def test_registry_round_trips_to_json(self):
        registry = load_hypothesis_registry(REGISTRY_PATH)
        payload = json.dumps(registry.to_dict(), ensure_ascii=False)
        restored = json.loads(payload)
        assert restored["hypothesis_count"] == len(registry.hypotheses)
        assert restored["oos_labels_seen_at_registration"] is False


class TestHypothesisSpecValidation:
    def _base(self, **overrides):  # type: ignore[no-untyped-def]
        payload = {
            "hypothesis_id": "HYP-X", "title": "t", "object_id": "x",
            "engines": ("bazi",), "direction_source": "raw", "logic": "single",
        }
        payload.update(overrides)
        return payload

    def test_rejects_unknown_direction_source(self):
        with pytest.raises(ValueError):
            HypothesisSpec(**self._base(direction_source="invented"))

    def test_rejects_unknown_logic(self):
        with pytest.raises(ValueError):
            HypothesisSpec(**self._base(logic="free_search"))

    def test_conflict_requires_definition(self):
        with pytest.raises(ValueError):
            HypothesisSpec(**self._base(logic="conflict"))

    def test_primary_horizon_must_be_in_horizons(self):
        with pytest.raises(ValueError):
            HypothesisSpec(**self._base(horizons=(5, 10), primary_horizon=20))

    def test_rejects_unknown_expected_direction(self):
        with pytest.raises(ValueError):
            HypothesisSpec(**self._base(expected_direction="whatever"))


class TestExperimentRecord:
    def _record(self) -> ExperimentRecord:
        return ExperimentRecord(
            experiment_id=new_experiment_id("HYP-BZ-CAL-001", "listing_open_v1"),
            hypothesis_id="HYP-BZ-CAL-001",
            git_sha="deadbeef",
            dataset_version="phase3a_astockdata_cutoff_20260814",
            universe_version="v2-phase3a",
            birth_model_version="listing_open_v1",
            factor_version="v1.1",
            calibration_version="cal-v1",
            split_version="phase3-oos-v1",
            train_period="2010-01-01..2018-12-31",
            validation_period="2019-01-01..2022-12-31",
            oos_period="2023-01-01..2026-08-14",
            horizon=20,
            parameters={"logic": "single"},
            random_seed=20260918,
            created_at="2026-09-20T00:00:00",
            result_status="NO_SIGNAL",
            result_reasons=("G5 未通过",),
            metrics={"event_count": 900, "mean_excess_return": 0.001},
            oos_used=True,
        )

    def test_experiment_row_carries_all_required_versions(self):
        row = self._record().to_row()
        for field in (
            "experiment_id", "hypothesis_id", "git_sha", "dataset_version",
            "universe_version", "birth_model_version", "factor_version",
            "calibration_version", "split_version", "train_period",
            "validation_period", "oos_period", "horizon", "random_seed",
            "created_at", "result_status",
        ):
            assert row[field] not in (None, ""), f"{field} 缺失"
        assert row["oos_used"] is True
        assert json.loads(row["parameters"])["logic"] == "single"

    def test_experiment_id_is_hypothesis_scoped(self):
        assert new_experiment_id("HYP-A", "listing_open_v1") == "OOS3D--HYP-A--listing_open_v1"

    def test_csv_written_with_header(self, tmp_path):
        path = write_experiment_registry_csv(
            [self._record()], tmp_path / "registry.csv"
        )
        text = path.read_text(encoding="utf-8")
        assert text.startswith("experiment_id,hypothesis_id,git_sha")
        assert "HYP-BZ-CAL-001" in text
        assert len(text.strip().splitlines()) == 2

    def test_csv_written_even_when_empty(self, tmp_path):
        path = write_experiment_registry_csv([], tmp_path / "empty.csv")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == ""

    def test_persist_into_existing_backtest_tables(self, db_session):
        """复用已有 backtest_experiment / backtest_result，不新增表、不改 schema。"""
        from sqlalchemy import select

        from src.db.models import BacktestExperimentRow, BacktestResultRow

        record = self._record()
        written = persist_experiments([record])
        assert written == 1
        db_session.commit()
        row = db_session.get(BacktestExperimentRow, record.experiment_id)
        assert row is not None
        assert row.kind == "oos"
        assert row.status == "NO_SIGNAL"
        assert row.params_json["calibration_version"] == "cal-v1"
        assert row.params_json["split_version"] == "phase3-oos-v1"
        assert row.params_json["oos_used"] is True
        results = db_session.execute(
            select(BacktestResultRow).where(
                BacktestResultRow.experiment_id == record.experiment_id
            )
        ).scalars().all()
        assert len(results) == 1
        assert results[0].variant == "oos_gate"
        assert results[0].horizon == 20

    def test_persist_is_idempotent(self, db_session):
        """重复落库不得产生重复结果行（先删后写，保持幂等）。"""
        from sqlalchemy import select

        from src.db.models import BacktestResultRow

        record = self._record()
        persist_experiments([record])
        persist_experiments([record])
        db_session.commit()
        results = db_session.execute(
            select(BacktestResultRow).where(
                BacktestResultRow.experiment_id == record.experiment_id
            )
        ).scalars().all()
        assert len(results) == 1
