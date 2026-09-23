"""日期关系扫描 API 契约测试（bazi-relation-v3 / relation-matrix-v2 / 3×3）。"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select

from src.core.constants import ten_god
from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow

CANONICAL_PROFILE = "v2-phase4b-listing_open"


@pytest.fixture(autouse=True)
def _clear_date_scan_cache():
    """隔离进程内扫描缓存：避免不同测试的库内容与缓存键误配对。"""
    from src.core.orchestration.date_relation_scan import DATE_SCAN_CACHE

    DATE_SCAN_CACHE.clear()
    yield
    DATE_SCAN_CACHE.clear()


def _seed_stock(db_session, code: str, name: str, exchange: str, listing: date) -> str:
    if db_session.get(StockMasterRow, code) is None:
        db_session.add(StockMasterRow(
            stock_code=code,
            wind_code=f"{code}.{'SH' if exchange == 'SSE' else 'SZ'}",
            name=name,
            exchange=exchange,
            board="主板",
            listing_date=listing,
            source="test",
            data_quality_json={"grade": "A", "score": 1.0, "notes": []},
        ))
    if db_session.execute(
        select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code == code,
            StockBirthProfileRow.birth_profile_version == CANONICAL_PROFILE,
        )
    ).scalars().first() is None:
        db_session.add(StockBirthProfileRow(
            stock_code=code,
            exchange=exchange,
            birth_basis="listing_open",
            birth_datetime=datetime(listing.year, listing.month, listing.day, 9, 30),
            timezone="Asia/Shanghai",
            source="test",
            birth_profile_version=CANONICAL_PROFILE,
            evidence_json={"first_trading_day": listing.isoformat(), "lookup_key": "test"},
            assumptions_json=[],
            data_quality_json={"grade": "A", "score": 1.0, "notes": []},
            variant_mode="not_applicable",
            variant_note="",
        ))
    if db_session.execute(
        select(UniverseMembershipRow).where(
            UniverseMembershipRow.universe_version == "v4-full",
            UniverseMembershipRow.stock_code == code,
        )
    ).scalars().first() is None:
        db_session.add(UniverseMembershipRow(
            universe_version="v4-full",
            stock_code=code,
            exchange=exchange,
            board="主板",
            list_date=listing,
            status="active",
            source="test",
            source_snapshot="test",
            delist_source="test",
        ))
    db_session.flush()
    db_session.commit()
    return code


@pytest.fixture
def date_scan_seed(db_session):
    """在测试临时库里写入最小 canonical PIT 样本，不依赖开发库数据。"""
    return _seed_stock(db_session, "600519", "贵州茅台", "SSE", date(2001, 8, 27))


@pytest.fixture
def two_stock_seed(db_session):
    return (
        _seed_stock(db_session, "600519", "贵州茅台", "SSE", date(2001, 8, 27)),
        _seed_stock(db_session, "000001", "平安银行", "SZSE", date(1991, 4, 3)),
    )


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


def test_date_scan_returns_v3_contract(client, date_scan_seed):
    response = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "limit": 3, "offset": 0},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["target_date"] == "2026-09-22"
    assert body["versions"]["relation_rule_version"] == "bazi-relation-v3"
    assert body["versions"]["relation_matrix_schema_version"] == "relation-matrix-v2"
    assert body["versions"]["fingerprint_version"] == "date-relation-fingerprint-v1"
    assert body["versions"]["birth_profile_version"] == CANONICAL_PROFILE
    assert body["scope"]["aggregate_scope"] == "external_day_row"
    assert body["scope"]["matrix_source_scope"] == ["year", "month", "day"]
    assert body["scope"]["matrix_target_scope"] == ["year", "month", "day"]
    assert body["scope"]["yongshen_basis"] == "full_four_pillars"
    assert body["scope"]["evaluation_time"] == "12:00:00"
    assert body["scope"]["timezone"] == "Asia/Shanghai"
    assert body["stock_total"] >= body["returned_count"]
    assert body["rows"]
    row = body["rows"][0]
    assert set(row["natal"]) == {"year", "month", "day"}
    assert "hour" not in row["natal"]
    assert row["day_stem_verdict"] is not None
    assert row["day_stem_verdict"]["verdict"] in {"匹配", "不匹配", "未知"}
    assert row["metrics"]["group"] in {"协同型", "扰动型", "混合型", "弱关系", "不可用"}
    assert body["disclaimer"]
    # 关系目录（含 v3 新增受生/受克）必须能与扫描结果对齐。
    catalog = client.get("/api/v1/research/relation-catalog")
    assert catalog.status_code == 200
    catalog_body = catalog.json()
    assert catalog_body["relation_rule_version"] == "bazi-relation-v3"
    catalog_types = {item for group in catalog_body["groups"] for item in group["items"]}
    assert {"天干受生", "天干受克", "三刑"} <= catalog_types
    assert set(row["relation_types"]) <= catalog_types
    assert set(catalog_body["factors"]) >= {"REL_LIUHE", "REL_TIANGAN_SHOUSHENG", "REL_TIANGAN_SHOUKE"}


def test_date_scan_rejects_legacy_v2_rule_version(client, date_scan_seed):
    """旧 v2 口径请求必须在进入缓存/计算前被拒绝：不存在"用 v2 请求拿 v3 结构"。"""
    response = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "relation_rule_version": "bazi-relation-v2", "limit": 1},
    )
    assert response.status_code == 422
    assert "bazi-relation-v2" in response.json()["error"]["message"]


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


def test_date_scan_rejects_unknown_relation_type(client, date_scan_seed):
    response = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "relation_type": "不存在的关系统", "limit": 1},
    )
    assert response.status_code == 422
    assert "relation-catalog" in response.json()["error"]["message"]


def test_date_scan_detail_returns_3x3_matrix(client, date_scan_seed):
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
    payload = detail.json()
    matrix = payload["row"]["matrix"]
    assert matrix["schema_version"] == "relation-matrix-v2"
    assert matrix["relation_rule_version"] == "bazi-relation-v3"
    assert matrix["columns"] == ["year", "month", "day"]
    assert len(matrix["rows"]) == 3
    assert all(len(row["cells"]) == 3 for row in matrix["rows"])
    assert all(
        cell["target_pillar"] in {"year", "month", "day"}
        for row in matrix["rows"] for cell in row["cells"]
    )
    # 行级 relation_types：等于该行全部 cell 事件类型去重结果（前端不得重算）。
    for row in matrix["rows"]:
        expected = list(dict.fromkeys(
            event["relation_type"] for cell in row["cells"] for event in cell["events"]
        ))
        assert row["relation_types"] == expected
    assert payload["scope"]["aggregate_scope"] == "external_day_row"
    assert payload["versions"]["relation_matrix_schema_version"] == "relation-matrix-v2"
    assert payload["row"]["day_stem_verdict"]["day_master"]


def test_relation_type_counts_equal_filtered_count(client, date_scan_seed):
    """过滤一致性：relation_type_counts[T] == 按 T 过滤后的 filtered_count（按股票数）。"""
    body = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "limit": 1},
    ).json()
    catalog = client.get("/api/v1/research/relation-catalog").json()
    relation_types = [item for group in catalog["groups"] for item in group["items"]]

    checked = 0
    for relation in relation_types:
        expected = body["relation_type_counts"][relation]
        filtered = client.post(
            "/api/v1/research/date-scan",
            json={"date": "2026-09-22", "relation_type": relation, "limit": 500},
        ).json()
        assert filtered["filtered_count"] == expected, f"{relation} 计数与过滤结果不一致"
        assert filtered["returned_count"] == min(expected, 500)
        for row in filtered["rows"]:
            assert relation in row["relation_types"]
        if expected:
            checked += 1
        else:
            assert filtered["rows"] == []
    assert checked > 0, "样本日没有任何关系命中，无法验证过滤一致性"


def test_date_change_regression_same_stock(client, date_scan_seed):
    """固定股票、不同日干日期：原局字段不变，流日字段按规则变化。"""
    dates = ["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25"]
    details = {}
    for day in dates:
        scan = client.post(
            "/api/v1/research/date-scan",
            json={"date": day, "limit": 1},
        )
        assert scan.status_code == 200, scan.text
        body = scan.json()
        code = body["rows"][0]["stock_code"]
        detail = client.get(
            f"/api/v1/research/date-scan/{body['scan_id']}/stocks/{code}",
            params={"target_date": day},
        )
        assert detail.status_code == 200, detail.text
        details[day] = detail.json()["row"]

    base = details[dates[0]]
    day_stems = {payload["day_stem_verdict"]["day_stem"] for payload in details.values()}
    assert len(day_stems) == len(dates), "所选日期的日干必须两两不同（否则测试无意义）"

    for _day, payload in details.items():
        # 原局字段完全固定
        assert payload["natal"] == base["natal"]
        assert payload["day_master"] == base["day_master"]
        assert payload["yong_shen"] == base["yong_shen"]
        assert payload["xi_shen"] == base["xi_shen"]
        assert payload["ji_shen"] == base["ji_shen"]
        # 流日字段由流日规则驱动
        verdict = payload["day_stem_verdict"]
        assert verdict["ten_god"] == ten_god(base["day_master"], verdict["day_stem"])
        assert verdict["verdict"] in {"匹配", "不匹配", "未知"}
        # 流日十神只允许一个（来自 verdict），不是事件十神集合
        assert payload["ten_gods"] in ([verdict["ten_god"]], [])
    assert details[dates[1]]["day_stem_verdict"]["day_stem"] == "庚"


def test_yong_shen_relations_is_day_row_legacy(client, date_scan_seed):
    """legacy 字段只能来源于流日行；权威喜忌只读 day_stem_verdict。"""
    scan = client.post("/api/v1/research/date-scan", json={"date": "2026-09-22", "limit": 1}).json()
    code = scan["rows"][0]["stock_code"]
    detail = client.get(
        f"/api/v1/research/date-scan/{scan['scan_id']}/stocks/{code}",
        params={"target_date": "2026-09-22"},
    ).json()["row"]
    day_types = set(detail["relation_types"])
    assert set(detail["yong_shen_relations"]) <= day_types
    verdict = detail["day_stem_verdict"]
    assert verdict["verdict"] in {"匹配", "不匹配", "未知"}
    # 「天干五合」等关系类型不得出现在喜忌结论位置。
    assert "天干五合" not in (verdict["wuxing_role"], verdict["verdict"])
