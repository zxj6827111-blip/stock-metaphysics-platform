"""日期关系扫描 API 契约测试。"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow


@pytest.fixture
def date_scan_seed(db_session):
    """在测试临时库里写入最小 canonical PIT 样本，不依赖开发库数据。"""
    stock_code = "600519"
    if db_session.get(StockMasterRow, stock_code) is None:
        db_session.add(StockMasterRow(
            stock_code=stock_code,
            wind_code="600519.SH",
            name="贵州茅台",
            exchange="SSE",
            board="主板",
            listing_date=date(2001, 8, 27),
            source="test",
            data_quality_json={"grade": "A", "score": 1.0, "notes": []},
        ))
    if db_session.execute(
        select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code == stock_code,
            StockBirthProfileRow.birth_profile_version == "v2-phase4b-listing_open",
        )
    ).scalars().first() is None:
        db_session.add(StockBirthProfileRow(
            stock_code=stock_code,
            exchange="SSE",
            birth_basis="listing_open",
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            timezone="Asia/Shanghai",
            source="test",
            birth_profile_version="v2-phase4b-listing_open",
            evidence_json={"first_trading_day": "2001-08-27", "lookup_key": "test"},
            assumptions_json=[],
            data_quality_json={"grade": "A", "score": 1.0, "notes": []},
            variant_mode="not_applicable",
            variant_note="",
        ))
    if db_session.execute(
        select(UniverseMembershipRow).where(
            UniverseMembershipRow.universe_version == "v4-full",
            UniverseMembershipRow.stock_code == stock_code,
        )
    ).scalars().first() is None:
        db_session.add(UniverseMembershipRow(
            universe_version="v4-full",
            stock_code=stock_code,
            exchange="SSE",
            board="主板",
            list_date=date(2001, 8, 27),
            status="active",
            source="test",
            source_snapshot="test",
            delist_source="test",
        ))
    db_session.flush()
    db_session.commit()
    return stock_code


def test_date_relation_fingerprint_endpoint(client):
    response = client.get("/api/v1/research/date-relations/2026-09-22")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["year"], body["month"], body["day"]) == ("丙午", "丁酉", "己亥")
    assert body["fingerprint_version"] == "date-relation-fingerprint-v1"
    assert "六破" in body["supported_relations"]
    assert body["candidates"]["半合"]


def test_date_relation_fingerprint_hour_zero_is_not_default_noon(client):
    noon = client.get("/api/v1/research/date-relations/2026-09-22")
    midnight = client.get("/api/v1/research/date-relations/2026-09-22", params={"hour": 0})
    assert noon.status_code == 200
    assert midnight.status_code == 200
    assert noon.json()["hour"] != midnight.json()["hour"]


def test_date_scan_endpoint_returns_versions_and_pit_rows(client, date_scan_seed):
    response = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "limit": 3, "offset": 0},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_date"] == "2026-09-22"
    assert body["stock_total"] >= body["returned_count"]
    assert body["versions"]["birth_profile_version"] == "v2-phase4b-listing_open"
    assert body["versions"]["universe_version"] == "v4-full"
    assert body["rows"]
    assert set(body["rows"][0]["natal"]) == {"year", "month", "day", "hour"}
    assert body["disclaimer"]


def test_date_scan_rejects_noncanonical_profile(client):
    response = client.post(
        "/api/v1/research/date-scan",
        json={
            "date": "2026-09-22",
            "birth_profile_version": "v1-phase3b-listing_open",
            "limit": 1,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_date_scan_detail_returns_3x4_matrix(client, date_scan_seed):
    scan = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "limit": 1},
    )
    assert scan.status_code == 200, scan.text
    body = scan.json()
    code = body["rows"][0]["stock_code"]
    detail = client.get(
        f"/api/v1/research/date-scan/{body['scan_id']}/stocks/{code}",
        params={"target_date": "2026-09-22"},
    )
    assert detail.status_code == 200, detail.text
    matrix = detail.json()["row"]["matrix"]
    assert len(matrix["rows"]) == 3
    assert all(len(row["cells"]) == 4 for row in matrix["rows"])
