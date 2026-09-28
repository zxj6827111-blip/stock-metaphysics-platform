from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.research.historical_dataset import (
    HistoricalResearchDatasetStore,
    query_historical_dataset,
    validate_feature_outcome_frames,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_FEATURE_VERSIONS = {
    "feature_version": "w4-features-v1",
    "pit_version": "pit-v2-sample",
    "birth_profile_version": "birth-v2",
    "birth_profile_source_version": "source-birth-v2",
    "calendar_version": "calendar-v1",
    "engine_versions_json": json.dumps({"bazi": "bazi-v1"}, sort_keys=True),
    "rule_versions_json": json.dumps({"factor": "factor-v1"}, sort_keys=True),
    "config_version": "config-v1",
}
_LABEL_VERSIONS = {
    "label_version": "w3-hfq-adjfactor-v2",
    "bar_version": "raw-overlay-v1",
    "factor_version": "adjfactor-overlay-v1",
    "price_basis": "raw_times_factor",
}


def _feature(security_id: str, stock_code: str, day: str, *, dataset_id: str = "w4-test") -> dict:
    return {
        "dataset_id": dataset_id,
        "security_id": security_id,
        "stock_code": stock_code,
        "research_date": day,
        "research_time": "15:00:00",
        "research_timezone": "Asia/Shanghai",
        **_FEATURE_VERSIONS,
        "pit_manifest_sha256": _HASH_A,
        "pit_calendar_digest": _HASH_B,
        "birth_profile_source": "research:listing_open",
        "birth_profile_recorded_at": "2026-09-20T10:00:00",
        "birth_evidence_asof_status": "NOT_PROVEN",
        "chart_artifact_ids_json": json.dumps([f"chart-{stock_code}-{day}"]),
        "chart_artifact_digests_json": json.dumps({f"chart-{stock_code}-{day}": _HASH_C}),
        "features_json": json.dumps({"factor_observations": [{"factor_id": "F"}]}),
        "research_use_status": "ENGINEERING_ONLY",
        "research_eligible": False,
    }


def _outcome(
    security_id: str,
    stock_code: str,
    day: str,
    *,
    ret_1d: float | None = 0.01,
    dataset_id: str = "w4-test",
) -> dict:
    row = {
        "dataset_id": dataset_id,
        "security_id": security_id,
        "stock_code": stock_code,
        "research_date": day,
        "research_time": "15:00:00",
        "research_timezone": "Asia/Shanghai",
        **_FEATURE_VERSIONS,
        **_LABEL_VERSIONS,
        "bar_manifest_sha256": _HASH_B,
        "factor_manifest_sha256": _HASH_C,
        "trade_date": day,
        "trade_index": 123,
        "benchmark_code": None,
        "is_degraded": False,
        "ret_1d": ret_1d,
        "bench_ret_1d": None,
        "excess_return_1d": None,
        "horizon_available_1d": ret_1d is not None,
        "horizon_requested_1d": True,
        "max_favorable_move_20d": None,
        "max_adverse_move_20d": None,
        "max_drawdown_20d": None,
    }
    for horizon in (5, 10, 20, 60):
        row[f"ret_{horizon}d"] = None
        row[f"bench_ret_{horizon}d"] = None
        row[f"excess_return_{horizon}d"] = None
        row[f"horizon_available_{horizon}d"] = False
        row[f"horizon_requested_{horizon}d"] = True
    return row


def _store(tmp_path, dataset_id: str = "w4-test", metadata: dict | None = None):
    return HistoricalResearchDatasetStore(
        tmp_path,
        dataset_id=dataset_id,
        metadata=metadata or {"scope": "engineering-only", "source": "unit-test"},
    )


def test_strict_join_supports_multi_security_dates_and_unavailable_outcomes():
    features = pd.DataFrame([
        _feature("sec-a", "000001", "2020-01-02"),
        _feature("sec-a", "000001", "2020-01-03"),
        _feature("sec-b", "000002", "2020-01-02"),
    ])
    outcomes = pd.DataFrame([
        _outcome("sec-b", "000002", "2020-01-02"),
        _outcome("sec-a", "000001", "2020-01-03", ret_1d=None),
        _outcome("sec-a", "000001", "2020-01-02"),
    ])

    joined = validate_feature_outcome_frames(features, outcomes)

    assert list(zip(joined.security_id, joined.research_date, strict=True)) == [
        ("sec-a", "2020-01-02"),
        ("sec-a", "2020-01-03"),
        ("sec-b", "2020-01-02"),
    ]
    unavailable = joined.loc[joined.research_date == "2020-01-03"].iloc[0]
    assert pd.isna(unavailable.ret_1d)
    assert not unavailable.horizon_available_1d
    assert not unavailable.research_eligible


def test_duplicate_identity_date_key_fails_closed():
    features = pd.DataFrame([_feature("sec-a", "000001", "2020-01-02")] * 2)
    outcomes = pd.DataFrame([_outcome("sec-a", "000001", "2020-01-02")] * 2)

    with pytest.raises(ValueError, match="重复.*键"):
        validate_feature_outcome_frames(features, outcomes)

    missing_id = _feature("sec-a", "000001", "2020-01-02")
    missing_id["security_id"] = None
    with pytest.raises(ValueError, match="security_id 不得为空"):
        validate_feature_outcome_frames(
            pd.DataFrame([missing_id]),
            pd.DataFrame([_outcome("sec-a", "000001", "2020-01-02")]),
        )


def test_missing_outcome_or_version_conflict_fails_closed():
    feature = _feature("sec-a", "000001", "2020-01-02")
    feature_next = _feature("sec-a", "000001", "2020-01-03")
    outcome = _outcome("sec-a", "000001", "2020-01-02")
    with pytest.raises(ValueError, match="范围不完全相同"):
        validate_feature_outcome_frames(
            pd.DataFrame([feature, feature_next]), pd.DataFrame([outcome]),
        )

    outcome["engine_versions_json"] = json.dumps({"bazi": "old-version"})
    with pytest.raises(ValueError, match="engine_versions_json"):
        validate_feature_outcome_frames(pd.DataFrame([feature]), pd.DataFrame([outcome]))


def test_dataset_shards_are_resumable_queryable_and_digest_stable(tmp_path):
    store = _store(tmp_path)
    a_features = [
        _feature("sec-a", "000001", "2020-01-02"),
        _feature("sec-a", "000001", "2020-01-03"),
    ]
    a_outcomes = [
        _outcome("sec-a", "000001", "2020-01-02"),
        _outcome("sec-a", "000001", "2020-01-03", ret_1d=None),
    ]
    source_a = hashlib.sha256(b"source-a").hexdigest()
    first = store.write_shard(a_features, a_outcomes, source_digest=source_a)
    resumed = store.write_shard(a_features, a_outcomes, source_digest=source_a)
    assert not first["resumed"]
    assert resumed["resumed"]
    assert first["input_digest"] == resumed["input_digest"]

    b_feature = _feature("sec-b", "000002", "2021-01-04")
    b_outcome = _outcome("sec-b", "000002", "2021-01-04")
    store.write_shard(
        [b_feature], [b_outcome], source_digest=hashlib.sha256(b"source-b").hexdigest(),
    )
    manifest = store.finalize(expected_shards=["sec-a/2020", "sec-b/2021"])
    assert manifest["status"] == "COMPLETE"
    assert manifest["row_count"] == 3

    reopened = _store(tmp_path)
    assert reopened.finalize(expected_shards=["sec-a/2020", "sec-b/2021"])[
        "dataset_digest"
    ] == manifest["dataset_digest"]
    result = query_historical_dataset(
        tmp_path,
        "w4-test",
        security_ids=["sec-a"],
        date_from=date(2020, 1, 3),
        date_to=date(2020, 1, 3),
    )
    assert len(result) == 1
    assert result.iloc[0].stock_code == "000001"
    assert pd.isna(result.iloc[0].ret_1d)
    assert result.iloc[0].research_eligible == False  # noqa: E712


def test_changed_completed_input_and_metadata_are_rejected(tmp_path):
    store = _store(tmp_path)
    feature = _feature("sec-a", "000001", "2020-01-02")
    outcome = _outcome("sec-a", "000001", "2020-01-02")
    source = hashlib.sha256(b"source").hexdigest()
    store.write_shard([feature], [outcome], source_digest=source)
    with pytest.raises(RuntimeError, match="输入发生变化"):
        store.write_shard(
            [{**feature, "features_json": json.dumps({"changed": True})}],
            [outcome],
            source_digest=source,
        )
    with pytest.raises(ValueError, match="metadata 已变化"):
        _store(tmp_path, metadata={"scope": "different"})


def test_partial_dataset_records_failures_and_query_uses_completed_shards(tmp_path):
    store = _store(tmp_path)
    feature = _feature("sec-a", "000001", "2020-01-02")
    outcome = _outcome("sec-a", "000001", "2020-01-02")
    store.write_shard(
        [feature], [outcome], source_digest=hashlib.sha256(b"source").hexdigest(),
    )
    store.record_failure(
        security_id="sec-b",
        year=2020,
        source_digest=hashlib.sha256(b"broken-source").hexdigest(),
        error_code="INPUT_UNAVAILABLE",
        error_type="FileNotFoundError",
    )
    manifest = store.finalize(expected_shards=["sec-a/2020", "sec-b/2020"])
    assert manifest["status"] == "PARTIAL"
    assert manifest["failed_shards"] == ["sec-b/2020"]
    assert len(query_historical_dataset(tmp_path, "w4-test")) == 1
    subset_manifest = store.finalize(expected_shards=["sec-a/2020"])
    assert subset_manifest["status"] == "PARTIAL"
    assert subset_manifest["failed_shards"] == ["sec-b/2020"]


def test_corrupted_parquet_is_detected_before_query(tmp_path):
    store = _store(tmp_path)
    feature = _feature("sec-a", "000001", "2020-01-02")
    outcome = _outcome("sec-a", "000001", "2020-01-02")
    entry = store.write_shard(
        [feature], [outcome], source_digest=hashlib.sha256(b"source").hexdigest(),
    )
    store.finalize(expected_shards=["sec-a/2020"])
    (store.root / entry["features_path"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest 不一致"):
        query_historical_dataset(tmp_path, "w4-test")


class _MemoryArtifactWriter:
    def persist_chart_artifact(self, **kwargs) -> str:
        payload = json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str)
        return f"test-{kwargs['engine_id']}-{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def _calculate_features_without_market_data():
    from scripts.build_w4_historical_dataset import (
        _build_feature_payload,
        _RecordingArtifactWriter,
    )

    return _build_feature_payload(
        writer=_RecordingArtifactWriter(_MemoryArtifactWriter()),
        stock_code="002561",
        stock_name="工程样本",
        exchange="SZSE",
        listing_date=date(2011, 3, 3),
        first_observed_bar_date=date(2011, 3, 3),
        source_birth_profile_version="v2-phase4b-listing_open",
        as_of=datetime(2012, 2, 23, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )


def test_future_market_changes_affect_labels_but_not_feature_replay():
    from src.research.labels.horizon_returns import compute_forward_returns

    feature_a = _calculate_features_without_market_data()
    feature_b = _calculate_features_without_market_data()
    assert feature_a["feature_payload"] == feature_b["feature_payload"]
    assert feature_a["artifact_ids"] == feature_b["artifact_ids"]

    dates = pd.date_range("2012-02-23", periods=22, freq="B")
    base_closes = [10.0 + index / 10 for index in range(len(dates))]
    changed_future_closes = [*base_closes[:1], 15.0, *base_closes[2:]]
    bars_a = pd.DataFrame({"trade_date": dates, "close": base_closes})
    bars_b = pd.DataFrame({"trade_date": dates, "close": changed_future_closes})
    factors = pd.DataFrame({"trade_date": dates, "factor": [1.0] * len(dates)})
    labels_a = compute_forward_returns(
        bars_a, [date(2012, 2, 23)], stock_code="002561", adj_factors=factors,
    )
    labels_b = compute_forward_returns(
        bars_b, [date(2012, 2, 23)], stock_code="002561", adj_factors=factors,
    )
    assert labels_a[0]["ret_1d"] != labels_b[0]["ret_1d"]


def test_w4_label_end_dates_match_the_exact_horizon_bar_and_preserve_unavailable():
    from scripts.build_w4_historical_dataset import _label_end_date

    bars = pd.DataFrame({
        "trade_date": pd.date_range("2020-01-02", periods=6, freq="B"),
    })
    label = {
        "trade_index": 0,
        "horizon_available": {"1d": True, "5d": True, "6d": False},
    }

    assert _label_end_date(bars, label, 1) == date(2020, 1, 3)
    assert _label_end_date(bars, label, 5) == date(2020, 1, 9)
    assert _label_end_date(bars, label, 6) is None
