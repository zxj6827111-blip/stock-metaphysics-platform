"""日期关系扫描 API 契约测试（bazi-relation-v3 / relation-matrix-v2 / 3×3）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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


@pytest.fixture
def four_stock_seed(db_session):
    """四只真实上市日期的股票，覆盖 2026-09-22 流日行的重复命中样本。"""
    return (
        _seed_stock(db_session, "600519", "贵州茅台", "SSE", date(2001, 8, 27)),
        _seed_stock(db_session, "000001", "平安银行", "SZSE", date(1991, 4, 3)),
        _seed_stock(db_session, "600036", "招商银行", "SSE", date(2002, 4, 9)),
        _seed_stock(db_session, "300750", "宁德时代", "SZSE", date(2018, 6, 11)),
    )


def _detail_rows(client, codes, day: str = "2026-09-22"):
    rows = {}
    scan = client.post("/api/v1/research/date-scan", json={"date": day, "limit": 500})
    assert scan.status_code == 200, scan.text
    body = scan.json()
    for code in codes:
        detail = client.get(
            f"/api/v1/research/date-scan/{body['scan_id']}/stocks/{code}",
            params={"target_date": day},
        )
        assert detail.status_code == 200, detail.text
        rows[code] = detail.json()["row"]
    return rows


def test_relation_type_counts_are_stock_level_not_event_level(client, four_stock_seed):
    """relation_type_counts[T] = 命中该关系的**股票数**（不是事件条数）。

    2026-09-22 的确定性事实（两种原解析路径已在引擎测试中对拍一致）：
    000001 的流日行在年/月两个 cell 各命中一次「三合」与「天干生」；
    300750 的流日行在年/月两柱各命中一次「天干同五行」。
    这些重复命中在 counts 里必须折成 1 股 / 1 股。
    """
    codes = list(four_stock_seed)
    body = client.post(
        "/api/v1/research/date-scan",
        json={"date": "2026-09-22", "limit": 500},
    ).json()
    counts = body["relation_type_counts"]
    assert body["stock_total"] == len(codes)

    # 聚合不变量：counts[T] == relation_types 含 T 的股票数（逐关系）。
    for relation, expected in counts.items():
        by_stock = sum(1 for row in body["rows"] if relation in row["relation_types"])
        assert expected == by_stock, f"{relation}: counts={expected} 但按股票数为 {by_stock}"

    details = _detail_rows(client, codes)
    pingan = details["000001"]
    day_events = [
        event
        for matrix_row in pingan["matrix"]["rows"] if matrix_row["source_pillar"] == "day"
        for cell in matrix_row["cells"] for event in cell["events"]
    ]
    sanhe_events = [event for event in day_events if event["relation_type"] == "三合"]
    assert len(sanhe_events) == 2, "000001 流日行应有两个三合事件（年/月两柱）"
    assert pingan["relation_types"].count("三合") == 1
    assert counts["三合"] == 1, "三合 只命中 1 只股票，不得按 2 个事件计入"

    # 事件总数大于股票数的样本必须存在，否则「股票级 ≠ 事件级」无从区分。
    event_totals: dict[str, int] = {}
    for code in codes:
        for matrix_row in details[code]["matrix"]["rows"]:
            if matrix_row["source_pillar"] != "day":
                continue
            for cell in matrix_row["cells"]:
                for event in cell["events"]:
                    event_totals[event["relation_type"]] = event_totals.get(event["relation_type"], 0) + 1
    spread = [
        relation for relation, total in event_totals.items()
        if total > counts[relation]
    ]
    assert "三合" in spread and "天干生" in spread and "天干同五行" in spread
    for relation, expected in counts.items():
        assert expected <= event_totals.get(relation, 0)


def test_date_scan_sort_s_is_none_safe():
    """sort=s/v/u：不可用（None）排在真实 0 之后，绝不与「命中 0 次」混淆。"""
    from src.core.orchestration.date_relation_scan import _sort_rows
    from src.core.schemas.relation import RelationMetrics, RelationStockResult

    rows = [
        RelationStockResult(stock_code="000002", metrics=RelationMetrics(s_raw=None)),
        RelationStockResult(stock_code="000003", metrics=RelationMetrics(s_raw=0)),
        RelationStockResult(stock_code="000001", metrics=RelationMetrics(s_raw=2)),
    ]
    ordered = _sort_rows(rows, "s")
    assert [row.stock_code for row in ordered] == ["000001", "000003", "000002"], (
        "S=2 → S=0 → None；None 不得借 `or -1` 混进真实 0 的分组"
    )


def test_pingan_000001_multi_date_natal_invariance(client, db_session):
    """平安银行（000001）多日期回归：原局字段跨日全固定，流日字段随日干变化。

    这是 Phase 1.1 验收路径在择日关系上的同构复现：
    同一批样本日期里 natal/day_master/喜用忌必须为同一串字节，不许闪。
    """
    from src.engines.calendar.calendar_engine import CalendarEngine

    code = _seed_stock(db_session, "000001", "平安银行", "SZSE", date(1991, 4, 3))
    calendar = CalendarEngine()

    # 在扫描窗口里确定性挑 5 个流日干两两不同的日期（来自生产历法而非硬编码）。
    picked: list[str] = []
    seen_stems: set[str] = set()
    for i in range(40):
        day = date(2026, 1, 5) + timedelta(days=i)
        stem = calendar.snapshot(datetime(day.year, day.month, day.day, 12)).day_ganzhi.stem
        if stem not in seen_stems:
            seen_stems.add(stem)
            picked.append(day.isoformat())
        if len(picked) == 5:
            break
    assert len(picked) == 5, "2026-01-05 起 40 天内必须凑出 5 个不同干日"

    snapshots = {}
    for day in picked:
        scan = client.post("/api/v1/research/date-scan", json={"date": day, "limit": 500})
        assert scan.status_code == 200, scan.text
        body = scan.json()
        assert code in {row["stock_code"] for row in body["rows"]}
        detail = client.get(
            f"/api/v1/research/date-scan/{body['scan_id']}/stocks/{code}",
            params={"target_date": day},
        )
        assert detail.status_code == 200, detail.text
        snapshots[day] = detail.json()["row"]

    base = snapshots[picked[0]]
    # 000001 喜忌覆盖全部五行（用金 / 喜水 / 忌土火 / 仇木 / 闲-）：
    # 这是 v3 证据 CSV pingan-000001-2026-v3.csv 的真实分布（匹配 144 / 不匹配 221 / 无 未知）。
    assert set(base["yong_shen"]) | set(base["xi_shen"]) | set(base["ji_shen"]) \
        | set(base["chou_shen"]) | set(base["xian_shen"]) == {"木", "火", "土", "金", "水"}

    day_stems = {snapshots[day]["day_stem_verdict"]["day_stem"] for day in picked}
    assert len(day_stems) == 5, "所选 5 个日期的日干必须两两不同"
    ten_gods = {snapshots[day]["day_stem_verdict"]["ten_god"] for day in picked}
    assert len(ten_gods) == 5, "十神必须完全跟随流日干而非出生档案"

    verdicts: set[str] = set()
    for day in picked:
        payload = snapshots[day]
        # —— 原局字段：固定串 ——
        assert payload["natal"] == base["natal"]
        assert payload["day_master"] == base["day_master"]
        assert payload["yong_shen"] == base["yong_shen"]
        assert payload["xi_shen"] == base["xi_shen"]
        assert payload["ji_shen"] == base["ji_shen"]
        assert payload["chou_shen"] == base["chou_shen"]
        assert payload["xian_shen"] == base["xian_shen"]
        # —— 流日字段：只随规则变 ——
        verdict = payload["day_stem_verdict"]
        assert verdict["day_master"] == payload["day_master"]
        assert verdict["day_stem"] == calendar.snapshot(
            datetime(int(day[:4]), int(day[5:7]), int(day[8:10]), 12)
        ).day_ganzhi.stem
        assert verdict["ten_god"] == ten_god(base["day_master"], verdict["day_stem"])
        assert verdict["verdict"] in {"匹配", "不匹配"}, "喜忌全五行覆盖时不允许出现未知"
        assert verdict["wuxing_role"] in {"用神", "喜神", "忌神", "仇神"}
        assert verdict["reason"] and "十神" in verdict["reason"]
        assert payload["ten_gods"] == [verdict["ten_god"]]
        verdicts.add(verdict["verdict"])
    assert verdicts == {"匹配", "不匹配"}, "5 个不同干日必须同时产生匹配与不匹配（复现证据 CSV 的分布结论）"
