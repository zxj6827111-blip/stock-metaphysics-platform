"""W5 research API v2 的契约、范围与兼容测试。"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from src.core.config import settings
from src.core.schemas.common import Exchange, SourceRef
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservationResolution,
    FortuneBirthBasis,
    StockFortuneBirthProfile,
    StockFortuneIdentity,
)
from src.core.schemas.research_v2 import HistoricalDatasetVersions
from src.db.models import UniverseMembershipRow
from src.research.historical_dataset import HistoricalResearchDatasetStore

pytestmark = pytest.mark.integration

_FEATURE_VERSIONS = {
    "feature_version": "w4-v2-test-features",
    "pit_version": "pit-v2-test",
    "birth_profile_version": "birth-v2-test",
    "birth_profile_source_version": "source-birth-v2-test",
    "calendar_version": "calendar-v2-test",
    "engine_versions_json": json.dumps({"bazi": "bazi-v2-test"}, sort_keys=True),
    "rule_versions_json": json.dumps({"factor": "factor-v2-test"}, sort_keys=True),
    "config_version": "config-v2-test",
}
_LABEL_VERSIONS = {
    "label_version": "w3-v2-test",
    "bar_version": "raw-v2-test",
    "factor_version": "factor-data-v2-test",
    "price_basis": "raw_times_factor",
}
_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _identity(symbol: str) -> StockFortuneIdentity:
    return StockFortuneIdentity(
        symbol=symbol,
        exchange=Exchange.SSE,
        name=f"测试证券 {symbol}",
        source=SourceRef(source="integration-stock-master"),
        source_version="integration-stock-master-v1",
    )


def _profile(symbol: str) -> StockFortuneBirthProfile:
    birth_at = datetime.fromisoformat("2001-08-27T09:30:00+08:00")
    return StockFortuneBirthProfile(
        symbol=symbol,
        exchange=Exchange.SSE,
        listing_date=date(2001, 8, 27),
        first_trade_datetime=birth_at,
        first_trade_date=birth_at.date(),
        first_trade_resolution=FirstTradeObservationResolution.TRADE,
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        birth_datetime=birth_at,
        timezone="Asia/Shanghai",
        birth_time_precision=BirthTimePrecision.EXACT,
        source=SourceRef(source="integration-observed-trade"),
        source_version="integration-market-v1",
        birth_profile_version="stock-fortune-birth-v2",
        market_session_version="a-share-session-v1",
        config_version=settings.config_version,
    )


def _feature(security_id: str, stock_code: str, day: str, *, direction: int, value: float, score: float) -> dict:
    observation = {
        "factor_id": "B_NATAL_001",
        "availability": "ok",
        "direction": direction,
        "normalized_value": value,
        "rule_score": score,
        "engine": "bazi",
        "engine_version": "bazi-v2-test",
        "rule_version": "factor-v2-test",
    }
    return {
        "dataset_id": "w5-api-dataset",
        "security_id": security_id,
        "stock_code": stock_code,
        "research_date": day,
        "research_time": "15:00:00",
        "research_timezone": "Asia/Shanghai",
        **_FEATURE_VERSIONS,
        "pit_manifest_sha256": _HASH_A,
        "pit_calendar_digest": _HASH_B,
        "birth_profile_source": "integration-observed-profile",
        "birth_profile_recorded_at": "2026-09-20T10:00:00",
        "birth_evidence_asof_status": "NOT_PROVEN",
        "chart_artifact_ids_json": json.dumps([f"chart-{stock_code}-{day}"]),
        "chart_artifact_digests_json": json.dumps({f"chart-{stock_code}-{day}": _HASH_C}),
        "features_json": json.dumps({"factor_set": {"observations": [observation]}}),
        "research_use_status": "ENGINEERING_ONLY",
        "research_eligible": False,
    }


def _outcome(stock_code: str, day: str, value: float | None) -> dict:
    row = {
        "dataset_id": "w5-api-dataset",
        "security_id": "sec-w5",
        "stock_code": stock_code,
        "research_date": day,
        "research_time": "15:00:00",
        "research_timezone": "Asia/Shanghai",
        **_FEATURE_VERSIONS,
        **_LABEL_VERSIONS,
        "bar_manifest_sha256": _HASH_B,
        "factor_manifest_sha256": _HASH_C,
        "trade_date": day,
        "trade_index": 10,
        "benchmark_code": None,
        "is_degraded": False,
        "ret_1d": value,
        "bench_ret_1d": None,
        "excess_return_1d": None,
        "horizon_available_1d": value is not None,
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


def _dataset_store(tmp_path):
    store = HistoricalResearchDatasetStore(
        tmp_path / "research_datasets",
        dataset_id="w5-api-dataset",
        metadata={
            "research_eligible": False,
            "confirmatory_research_eligible": False,
            "known_limitations": ["W2 物理覆盖不完整", "仅工程样本"],
        },
    )
    store.write_shard(
        [
            _feature("sec-w5", "000001", "2020-01-02", direction=1, value=0.75, score=8.0),
            _feature("sec-w5", "000001", "2020-01-03", direction=-1, value=-0.25, score=4.0),
        ],
        [
            _outcome("000001", "2020-01-02", 0.05),
            _outcome("000001", "2020-01-03", -0.02),
        ],
        source_digest="d" * 64,
    )
    store.finalize(expected_shards=["sec-w5/2020"])
    return store


def _versions() -> HistoricalDatasetVersions:
    return HistoricalDatasetVersions(
        feature_version=_FEATURE_VERSIONS["feature_version"],
        pit_version=_FEATURE_VERSIONS["pit_version"],
        birth_profile_version=_FEATURE_VERSIONS["birth_profile_version"],
        birth_profile_source_version=_FEATURE_VERSIONS["birth_profile_source_version"],
        calendar_version=_FEATURE_VERSIONS["calendar_version"],
        engine_versions={"bazi": "bazi-v2-test"},
        rule_versions={"factor": "factor-v2-test"},
        config_version=_FEATURE_VERSIONS["config_version"],
        label_version=_LABEL_VERSIONS["label_version"],
        bar_version=_LABEL_VERSIONS["bar_version"],
        factor_version=_LABEL_VERSIONS["factor_version"],
        price_basis="raw_times_factor",
    )


def _monkeypatch_profile_resolver(monkeypatch):
    from apps.api.routers import research_v2

    calls: list[str] = []

    def resolve(stock_code, _market, **_kwargs):
        calls.append(stock_code)
        return _identity(stock_code), _profile(stock_code), "integration-market-v1"

    monkeypatch.setattr(research_v2, "_resolve_identity_and_birth_profile", resolve)
    return calls


def test_v2_timeline_resolves_stock_profile_on_server(client, monkeypatch) -> None:
    calls = _monkeypatch_profile_resolver(monkeypatch)
    response = client.post(
        "/api/v2/research/fortune/timeline",
        json={
            "stock_code": "600519",
            "start_date": "2025-01-10",
            "end_date": "2025-01-11",
            "config_version": settings.config_version,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert calls == ["600519"]
    assert body["contract_version"] == "research-api-v2"
    assert body["timeline"]["birth_context"]["symbol"] == "600519"
    assert [point["date"] for point in body["timeline"]["points"]] == [
        "2025-01-10", "2025-01-11",
    ]
    assert body["resolved_versions"]["market_data_version"] == "integration-market-v1"


def test_v2_scan_resolves_versioned_pit_and_excludes_delist_date(client, db_session, monkeypatch) -> None:
    calls = _monkeypatch_profile_resolver(monkeypatch)
    universe_version = "w5-api-pit-v2"
    evaluation_date = date(2026, 9, 24)
    db_session.add_all([
        UniverseMembershipRow(
            universe_version=universe_version,
            stock_code="000001",
            exchange="SSE",
            board="主板",
            list_date=date(2000, 1, 1),
            delist_date=None,
            status="active",
            source="test-source",
            source_snapshot=evaluation_date.isoformat(),
            delist_source="NOT_AVAILABLE_FROM_PROVIDER",
        ),
        UniverseMembershipRow(
            universe_version=universe_version,
            stock_code="000002",
            exchange="SSE",
            board="主板",
            list_date=date(2000, 1, 1),
            delist_date=evaluation_date,
            status="delisted",
            source="test-source",
            source_snapshot=evaluation_date.isoformat(),
            delist_source="verified-test-delist",
        ),
    ])
    db_session.commit()

    response = client.post(
        "/api/v2/research/fortune/scan",
        json={
            "universe_version": universe_version,
            "evaluation_date": evaluation_date.isoformat(),
            "config_version": settings.config_version,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert calls == ["000001"]
    assert body["contract_version"] == "research-api-v2"
    assert body["research_eligible"] is False
    assert body["pit_evidence"]["member_count"] == 1
    assert body["pit_evidence"]["snapshot_digest"]
    assert body["scan"]["items"][0]["symbol"] == "000001"


def test_v2_scan_rejects_oversized_pit_universe_before_profile_resolution(
    client, db_session, monkeypatch,
) -> None:
    from types import SimpleNamespace

    from apps.api.routers import research_v2

    evaluation_date = date(2026, 9, 24)
    snapshot = SimpleNamespace(
        member_codes=tuple(f"{index:06d}" for index in range(5001)),
        digest="d" * 64,
    )
    universe = SimpleNamespace(at_exclusive_delist=lambda _day: snapshot)
    monkeypatch.setattr(
        research_v2,
        "resolve_universe_evidence_as_of",
        lambda *_args, **_kwargs: SimpleNamespace(
            available=True,
            as_of=evaluation_date,
            source="integration-test",
            detail="verified",
        ),
    )
    monkeypatch.setattr(
        research_v2.PointInTimeUniverse,
        "load",
        lambda *_args, **_kwargs: universe,
    )
    calls = _monkeypatch_profile_resolver(monkeypatch)

    response = client.post(
        "/api/v2/research/fortune/scan",
        json={
            "universe_version": "w5-oversized-pit-v2",
            "evaluation_date": evaluation_date.isoformat(),
            "config_version": settings.config_version,
        },
    )

    assert response.status_code == 422
    assert calls == []
    assert "5000" in response.text


def test_v2_event_study_uses_explicit_versions_and_marks_engineering_data(client, tmp_path, monkeypatch) -> None:
    _dataset_store(tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    request = {
        "dataset_id": "w5-api-dataset",
        "scope_mode": "stock",
        "stock_code": "000001",
        "date_from": "2020-01-01",
        "date_to": "2020-12-31",
        "factor_ids": ["B_NATAL_001"],
        "activation": "positive",
        "horizon": 1,
        "versions": _versions().model_dump(mode="json"),
        "limit": 10,
        "offset": 0,
    }
    response = client.post("/api/v2/research/event-study", json=request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_observation_count"] == 2, body
    assert body["matched_observation_count"] == 1
    assert body["matched_date_count"] == 1
    assert body["matched"]["mean_return"] == pytest.approx(0.05)
    assert body["complement"]["mean_return"] == pytest.approx(-0.02)
    assert body["matched_date_equal_weighted"]["sample_count"] == 1
    assert body["research_status"] == "EXPLORATORY_NOT_GATED"
    assert "W2 物理覆盖不完整" in body["research_status_reasons"]
    assert body["events"][0]["factor_id"] == "B_NATAL_001"


def test_v2_event_study_rejects_version_mismatch(client, tmp_path, monkeypatch) -> None:
    _dataset_store(tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    versions = _versions().model_dump(mode="json")
    versions["feature_version"] = "unregistered-version"
    response = client.post(
        "/api/v2/research/event-study",
        json={
            "dataset_id": "w5-api-dataset",
            "scope_mode": "stock",
            "stock_code": "000001",
            "date_from": "2020-01-01",
            "date_to": "2020-12-31",
            "factor_ids": ["B_NATAL_001"],
            "activation": "any",
            "horizon": 1,
            "versions": versions,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_v2_event_study_rejects_oversized_candidate_set_before_materializing(
    client, tmp_path, monkeypatch,
) -> None:
    from src.research import historical_dataset_event_study

    _dataset_store(tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(historical_dataset_event_study, "MAX_EVENT_STUDY_CANDIDATES", 1)
    response = client.post(
        "/api/v2/research/event-study",
        json={
            "dataset_id": "w5-api-dataset",
            "scope_mode": "stock",
            "stock_code": "000001",
            "date_from": "2020-01-01",
            "date_to": "2020-12-31",
            "factor_ids": ["B_NATAL_001"],
            "activation": "any",
            "horizon": 1,
            "versions": _versions().model_dump(mode="json"),
        },
    )
    assert response.status_code == 422
    assert "候选观察超过单次查询上限" in response.text


def test_v2_dataset_and_experiment_endpoints_are_scoped_to_fixed_roots(client, tmp_path, monkeypatch) -> None:
    _dataset_store(tmp_path)
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    dataset = client.get("/api/v2/research/datasets/w5-api-dataset")
    assert dataset.status_code == 200, dataset.text
    body = dataset.json()
    assert body["dataset_digest"]
    assert body["research_eligible"] is False
    assert body["confirmatory_research_eligible"] is False
    assert len(body["available_versions"]) == 1
    assert body["available_versions"][0]["feature_version"] == "w4-v2-test-features"

    reports = tmp_path / "research_experiments"
    reports.mkdir()
    report = {
        "schema_version": "w6-research-experiment-v1",
        "experiment_id": "F5-EXP-001-test",
        "research_status": "EXPLORATORY_NOT_GATED",
    }
    (reports / "F5-EXP-001-test.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8",
    )
    experiment = client.get("/api/v2/research/experiments/F5-EXP-001-test")
    assert experiment.status_code == 200, experiment.text
    assert experiment.json()["report"]["research_status"] == "EXPLORATORY_NOT_GATED"
    assert len(experiment.json()["report_digest"]) == 64

    traversal = client.get("/api/v2/research/datasets/%2e%2e")
    assert traversal.status_code == 422


def test_v2_readiness_is_additive_and_v1_health_remains_available(client) -> None:
    v1 = client.get("/api/v1/system/health")
    v2 = client.get("/api/v2/system/readiness")
    assert v1.status_code == 200, v1.text
    assert "status" in v1.json()
    assert v2.status_code in {200, 503}
    assert "components" in v2.json()
    assert set(v2.json()["components"]) == {
        "database", "migrations", "ziwei_service", "research_data",
    }
