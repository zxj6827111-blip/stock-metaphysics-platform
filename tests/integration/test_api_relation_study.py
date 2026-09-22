"""关系历史研究 API 契约测试。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow


def _seed_stock(db_session):
    code = "600519"
    if db_session.get(StockMasterRow, code) is None:
        db_session.add(StockMasterRow(stock_code=code, wind_code="600519.SH", name="贵州茅台", exchange="SSE", board="主板", listing_date=date(2001, 8, 27), source="test"))
    if db_session.execute(select(StockBirthProfileRow).where(StockBirthProfileRow.stock_code == code, StockBirthProfileRow.birth_basis == "listing_open", StockBirthProfileRow.birth_profile_version == "v2-phase4b-listing_open")).scalar_one_or_none() is None:
        db_session.add(StockBirthProfileRow(stock_code=code, exchange="SSE", birth_basis="listing_open", birth_datetime=datetime(2001, 8, 27, 9, 30), timezone="Asia/Shanghai", source="test", birth_profile_version="v2-phase4b-listing_open", evidence_json={}, assumptions_json=[], data_quality_json={"grade": "A"}, variant_mode="not_applicable", variant_note=""))
    if db_session.execute(select(UniverseMembershipRow).where(UniverseMembershipRow.universe_version == "v4-full", UniverseMembershipRow.stock_code == code)).scalar_one_or_none() is None:
        db_session.add(UniverseMembershipRow(universe_version="v4-full", stock_code=code, exchange="SSE", board="主板", list_date=date(2001, 8, 27), status="active", source="test", source_snapshot="test", delist_source="test"))
    db_session.commit()
    return code


def test_relation_study_returns_directionless_factor(client, db_session):
    code = _seed_stock(db_session)
    response = client.post("/api/v1/research/relation-study", json={"relation_type": "六合", "universe": "v4-full", "stock_codes": [code], "date_from": "2024-01-01", "date_to": "2024-12-31", "horizons": [1, 5, 20], "sample_step_months": 3, "run_negative_controls": True, "persist": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["factor_id"] == "REL_LIUHE"
    assert body["direction"] == 0
    assert body["splits"]
    assert all(split["research_status"] for split in body["splits"])


def test_experiment_detail_returns_audit_metadata(client):
    response = client.get("/api/v1/research/experiments")
    assert response.status_code == 200
    items = response.json()["items"]
    if not items:
        return
    detail = client.get(f"/api/v1/research/experiments/{items[0]['experiment_id']}")
    assert detail.status_code == 200
    experiment = detail.json()["experiment"]
    for field in ("status", "date_from", "date_to", "benchmark_code", "params"):
        assert field in experiment
