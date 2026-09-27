"""W6 首批预注册实验：冻结协议、连续日期块与 fail-closed 结果。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

import pandas as pd
import pytest

from src.research import f5_preregistered_experiments
from src.research.f5_preregistered_experiments import (
    PROTOCOL_PATH,
    analyze_f5_panel,
    load_f5_protocol,
    write_f5_experiment_reports,
)
from src.research.multipletesting.resample import moving_date_block_bootstrap


def _synthetic_panel() -> list[dict]:
    protocol, _ = load_f5_protocol(PROTOCOL_PATH)
    categories = protocol["experiments"][0]["raw_value_categories"]
    start = date(2012, 3, 1)
    rows = []
    for day_index in range(30):
        research_date = start + timedelta(days=day_index)
        for security_index in range(30):
            category = categories[security_index % len(categories)]
            rows.append({
                "dataset_id": "w4-engineering-002561-20120223-asof-v2",
                "security_id": f"sec-{security_index:03d}",
                "stock_code": f"{security_index:06d}",
                "research_date": research_date,
                "trade_date": research_date,
                "is_degraded": False,
                "research_eligible": False,
                "research_use_status": "ENGINEERING_ONLY",
                "ret_5d": ((security_index % 7) - 3) / 100.0,
                "ret_20d": ((security_index % 9) - 4) / 100.0,
                "excess_return_5d": ((security_index % 11) - 5) / 1000.0,
                "excess_return_20d": ((security_index % 13) - 6) / 1000.0,
                "horizon_available_5d": True,
                "horizon_available_20d": True,
                "label_end_date_5d": research_date + timedelta(days=7),
                "label_end_date_20d": research_date + timedelta(days=28),
                "factors": {
                    "B_DAY_005": {
                        "factor_id": "B_DAY_005", "availability": "ok", "raw_value": category,
                        "direction": 0, "rule_score": 0.0, "normalized_value": 0.0,
                    },
                    "B_DAY_003": {
                        "factor_id": "B_DAY_003", "availability": "ok",
                        "raw_value": int(security_index % 5 == 0), "direction": 0,
                        "rule_score": 0.0, "normalized_value": float(security_index % 5 == 0),
                    },
                    "B_DAY_002": {
                        "factor_id": "B_DAY_002", "availability": "ok",
                        "raw_value": int(security_index % 7 == 0), "direction": 0,
                        "rule_score": 0.0, "normalized_value": float(security_index % 7 == 0),
                    },
                    "B_DAY_008": {
                        "factor_id": "B_DAY_008", "availability": "ok",
                        "raw_value": int(security_index % 9 == 0), "direction": 0,
                        "rule_score": 0.0, "normalized_value": float(security_index % 9 == 0),
                    },
                },
            })
    return rows


def test_protocol_freezes_scope_horizons_family_sizes_and_unconfigured_exp003() -> None:
    protocol, digest = load_f5_protocol()
    assert len(digest) == 64
    assert protocol["dataset"]["use"] == "engineering_replay_only"
    assert protocol["analysis"]["horizons"] == [5, 20]
    assert protocol["analysis"]["permutation"]["count"] == 2000
    assert protocol["analysis"]["bootstrap"]["count"] == 2000
    assert protocol["analysis"]["bootstrap"]["block_length_trading_dates"] == 20
    assert [item["registered_family_size"] for item in protocol["experiments"]] == [60, 18]
    assert protocol["not_configured"][0]["experiment_id"] == "F5-EXP-003"


def test_unregistered_factor_values_fail_closed() -> None:
    protocol, _ = load_f5_protocol()
    experiment = protocol["experiments"][0]
    condition = f5_preregistered_experiments._condition_specs(experiment)[0]
    row = {"factors": {"B_DAY_005": {"availability": "ok", "raw_value": "未注册类别"}}}
    with pytest.raises(ValueError, match="未预注册十神类别"):
        f5_preregistered_experiments._is_hit(row, "F5-EXP-001", condition)


def test_moving_block_bootstrap_is_seeded_and_keeps_consecutive_twenty_day_blocks() -> None:
    rows = []
    for day_index in range(45):
        day = date(2020, 1, 1) + timedelta(days=day_index)
        for stock_index in range(4):
            rows.append({
                "as_of": day,
                "hit": stock_index < 2,
                "excess": (day_index / 1000) + (0.02 if stock_index < 2 else 0.0),
            })
    frame = pd.DataFrame(rows)
    first = moving_date_block_bootstrap(
        frame, "excess", date_col="as_of", hit_col="hit",
        block_length=20, bootstrap_count=2000, seed=91,
    )
    second = moving_date_block_bootstrap(
        frame, "excess", date_col="as_of", hit_col="hit",
        block_length=20, bootstrap_count=2000, seed=91,
    )
    assert first == second
    assert first.bootstrap_count == 2000
    assert first.date_count == 45
    assert first.candidate_block_count == 26
    assert first.block_length == 20
    assert first.ci_lower is not None and first.ci_upper is not None


def test_single_twenty_day_block_does_not_claim_a_confidence_interval() -> None:
    rows = []
    for day_index in range(20):
        day = date(2020, 1, 1) + timedelta(days=day_index)
        rows.extend([
            {"as_of": day, "hit": True, "excess": 0.02},
            {"as_of": day, "hit": False, "excess": 0.0},
        ])
    result = moving_date_block_bootstrap(
        pd.DataFrame(rows), "excess", block_length=20, bootstrap_count=2000, seed=7,
    )
    assert result.bootstrap_count == 2000
    assert result.candidate_block_count == 1
    assert result.ci_lower is None and result.ci_upper is None
    assert result.crosses_zero is None


def test_experiment_analysis_preserves_registered_families_and_reports_controls() -> None:
    protocol, protocol_digest = load_f5_protocol()
    protocol = deepcopy(protocol)
    protocol["analysis"]["permutation"]["count"] = 40
    protocol["analysis"]["bootstrap"]["count"] = 40
    manifest = {
        "dataset_id": protocol["dataset"]["dataset_id"],
        "dataset_digest": protocol["dataset"]["dataset_digest"],
        "schema_version": "w4-historical-dataset-v1",
        "status": "COMPLETE",
        "metadata": {"research_eligible": False, "confirmatory_research_eligible": False},
    }
    columns = {"label_end_date_5d", "label_end_date_20d"}
    reports = analyze_f5_panel(
        _synthetic_panel(), manifest, columns, protocol,
        protocol_digest=protocol_digest,
        implementation_digest="a" * 64,
    )
    assert [item["experiment_id"] for item in reports] == [
        "F5-EXP-001", "F5-EXP-002", "F5-EXP-003",
    ]
    exp001, exp002, exp003 = reports
    assert len(exp001["registered_tests"]) == 60
    assert len(exp002["registered_tests"]) == 18
    first = next(item for item in exp001["registered_tests"] if item["partition"] == "TRAIN")
    assert first["partition_window_status"] == "VERIFIED"
    assert first["permutation"]["permutation_count"] == 40
    assert first["moving_block_bootstrap"]["bootstrap_count"] == 40
    assert first["moving_block_bootstrap"]["block_length"] == 20
    assert first["negative_control"]["kind"] == "random_factor"
    assert exp001["family_correction"]["registered_test_count"] == 60
    assert exp003["status"] == "NOT_CONFIGURED"
    assert exp003["search_performed"] is False


def test_missing_horizon_end_date_withholds_partition_inference() -> None:
    protocol, digest = load_f5_protocol()
    protocol = deepcopy(protocol)
    protocol["analysis"]["permutation"]["count"] = 5
    protocol["analysis"]["bootstrap"]["count"] = 5
    manifest = {
        "dataset_id": protocol["dataset"]["dataset_id"],
        "dataset_digest": protocol["dataset"]["dataset_digest"],
        "schema_version": "w4-historical-dataset-v1",
        "status": "COMPLETE",
        "metadata": {"research_eligible": False},
    }
    panel = _synthetic_panel()
    for row in panel:
        row["excess_return_5d"] = None
        row["excess_return_20d"] = None
        row["label_end_date_5d"] = None
        row["label_end_date_20d"] = None
    reports = analyze_f5_panel(
        panel, manifest, set(), protocol,
        protocol_digest=digest, implementation_digest="b" * 64,
    )
    first = next(item for item in reports[0]["registered_tests"] if item["partition"] == "TRAIN")
    assert first["partition_window_status"] == "UNVERIFIABLE_LABEL_END_DATE"
    assert first["permutation"]["permutation_count"] == 0
    assert first["permutation"]["p_value"] is None
    assert first["moving_block_bootstrap"]["bootstrap_count"] == 0
    assert first["research_status"] == "EXPLORATORY_NOT_GATED"
    assert reports[0]["family_correction"]["registered_test_count"] == 60
    assert reports[0]["family_correction"]["evaluable_p_value_count"] == 0
    assert reports[0]["family_correction"]["unavailable_p_value_count"] == 60


def test_report_writer_is_idempotent_and_refuses_different_overwrite(tmp_path) -> None:
    report = {"experiment_id": "F5-EXP-001", "research_status": "EXPLORATORY_NOT_GATED"}
    first = write_f5_experiment_reports(tmp_path, [report])
    second = write_f5_experiment_reports(tmp_path, [report])
    assert first == second
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_f5_experiment_reports(
            tmp_path,
            [{"experiment_id": "F5-EXP-001", "research_status": "INSUFFICIENT_SAMPLE"}],
        )


def test_manifest_loader_checks_versioned_feature_outcome_join(tmp_path, monkeypatch) -> None:
    import duckdb

    protocol, _ = load_f5_protocol()
    version_fields = {
        "feature_version": "feature-v1",
        "pit_version": "pit-v1",
        "birth_profile_version": "birth-v1",
        "birth_profile_source_version": "source-v1",
        "calendar_version": "calendar-v1",
        "engine_versions_json": '{"bazi":"bazi-v1"}',
        "rule_versions_json": '{"factor":"factor-v1"}',
        "config_version": "config-v1",
    }
    features_path = tmp_path / "features.parquet"
    outcomes_path = tmp_path / "outcomes.parquet"
    feature = {
        "dataset_id": protocol["dataset"]["dataset_id"],
        "security_id": "sec-1",
        "stock_code": "000001",
        "research_date": date(2012, 3, 1),
        "features_json": '{"factor_set":{"observations":[{"factor_id":"B_DAY_005","availability":"ok","raw_value":"比肩"}]}}',
        "research_eligible": False,
        "research_use_status": "ENGINEERING_ONLY",
        **version_fields,
    }
    outcome = {
        "dataset_id": protocol["dataset"]["dataset_id"],
        "security_id": "sec-1",
        "research_date": date(2012, 3, 1),
        "trade_date": date(2012, 3, 1),
        "trade_index": 10,
        "is_degraded": False,
        "ret_5d": 0.01,
        "ret_20d": 0.02,
        "excess_return_5d": None,
        "excess_return_20d": None,
        "horizon_available_5d": True,
        "horizon_available_20d": True,
        "label_end_date_5d": date(2012, 3, 8),
        "label_end_date_20d": date(2012, 3, 29),
        **version_fields,
    }
    con = duckdb.connect()
    try:
        con.register("features_frame", pd.DataFrame([feature]))
        con.register("outcomes_frame", pd.DataFrame([outcome]))
        safe_features_path = features_path.as_posix().replace("'", "''")
        safe_outcomes_path = outcomes_path.as_posix().replace("'", "''")
        con.execute(f"COPY features_frame TO '{safe_features_path}' (FORMAT PARQUET)")
        con.execute(f"COPY outcomes_frame TO '{safe_outcomes_path}' (FORMAT PARQUET)")
    finally:
        con.close()
    manifest = {
        "dataset_id": protocol["dataset"]["dataset_id"],
        "dataset_digest": protocol["dataset"]["dataset_digest"],
        "schema_version": "w4-historical-dataset-v1",
        "status": "COMPLETE",
        "metadata": {"research_eligible": False},
    }
    monkeypatch.setattr(
        f5_preregistered_experiments,
        "_read_manifest",
        lambda *_args, **_kwargs: (manifest, [features_path], [outcomes_path]),
    )

    rows, loaded_manifest, columns = f5_preregistered_experiments._load_w4_panel(
        tmp_path, protocol,
    )
    assert loaded_manifest["dataset_digest"] == protocol["dataset"]["dataset_digest"]
    assert rows[0]["factors"]["B_DAY_005"]["raw_value"] == "比肩"
    assert rows[0]["excess_return_20d"] is None
    assert rows[0]["label_end_date_20d"] == date(2012, 3, 29)
    assert "label_end_date_5d" in columns
