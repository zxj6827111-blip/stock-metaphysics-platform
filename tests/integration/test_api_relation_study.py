"""关系历史研究 API 契约测试（bazi-relation-v3 口径 + 跨功能不变量）。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select

from src.core.config import settings
from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow


def _seed_stock(db_session, code: str = "600519") -> str:
    if db_session.get(StockMasterRow, code) is None:
        db_session.add(StockMasterRow(stock_code=code, wind_code=f"{code}.SH", name="贵州茅台", exchange="SSE", board="主板", listing_date=date(2001, 8, 27), source="test"))
    if db_session.execute(select(StockBirthProfileRow).where(StockBirthProfileRow.stock_code == code, StockBirthProfileRow.birth_basis == "listing_open", StockBirthProfileRow.birth_profile_version == "v2-phase4b-listing_open")).scalar_one_or_none() is None:
        db_session.add(StockBirthProfileRow(stock_code=code, exchange="SSE", birth_basis="listing_open", birth_datetime=datetime(2001, 8, 27, 9, 30), timezone="Asia/Shanghai", source="test", birth_profile_version="v2-phase4b-listing_open", evidence_json={}, assumptions_json=[], data_quality_json={"grade": "A"}, variant_mode="not_applicable", variant_note=""))
    if db_session.execute(select(UniverseMembershipRow).where(UniverseMembershipRow.universe_version == "v4-full", UniverseMembershipRow.stock_code == code)).scalar_one_or_none() is None:
        db_session.add(UniverseMembershipRow(universe_version="v4-full", stock_code=code, exchange="SSE", board="主板", list_date=date(2001, 8, 27), status="active", source="test", source_snapshot="test", delist_source="test"))
    db_session.commit()
    return code


def test_relation_study_returns_directionless_v3_factor(client, db_session):
    code = _seed_stock(db_session)
    response = client.post("/api/v1/research/relation-study", json={"relation_type": "六合", "universe": "v4-full", "stock_codes": [code], "date_from": "2024-01-01", "date_to": "2024-12-31", "horizons": [1, 5, 20], "sample_step_months": 3, "run_negative_controls": True, "persist": False})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["factor_id"] == "REL_LIUHE"
    assert body["direction"] == 0
    assert body["splits"]
    assert all(split["research_status"] for split in body["splits"])
    # v3 口径回显
    assert body["relation_rule_version"] == "bazi-relation-v3"
    assert body["relation_matrix_schema_version"] == "relation-matrix-v2"
    assert body["aggregate_scope"] == "external_day_row"
    assert body["matrix_target_scope"] == ["year", "month", "day"]
    assert body["yongshen_basis"] == "full_four_pillars"
    assert body["evaluation_time"] == "12:00:00"
    assert body["timezone"] == "Asia/Shanghai"
    # 多重比较范围与 p-value 对照类型必须如实回显
    assert body["multiplicity_scope"] == "within_relation_split_horizon"
    assert body["p_value_control_kind"] == "random_birth_date"
    assert "跨关系类型联合校正" in body["methodology"]
    assert body["factor_definition"]["factor_id"] == "REL_LIUHE"
    assert "3×3" in body["factor_definition"]["definition"]
    for split in body["splits"]:
        for horizon in split["horizons"]:
            assert horizon["p_value_control_kind"] == "random_birth_date"


def test_relation_study_requires_explicit_full_universe_confirmation(client, db_session):
    _seed_stock(db_session)
    response = client.post(
        "/api/v1/research/relation-study",
        json={"relation_type": "六合", "universe": "v4-full", "date_from": "2024-01-01", "date_to": "2024-12-31", "persist": False},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "allow_full_universe" in response.json()["error"]["message"]


def test_relation_study_full_universe_runs_only_when_confirmed(client, db_session):
    _seed_stock(db_session)
    response = client.post(
        "/api/v1/research/relation-study",
        json={
            "relation_type": "六合", "universe": "v4-full",
            "date_from": "2024-01-01", "date_to": "2024-12-31",
            "sample_step_months": 6, "horizons": [5],
            "run_negative_controls": False, "persist": False,
            "allow_full_universe": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data_source"]["stock_scope"] == "full_universe"
    assert body["data_source"]["stock_count"] >= 1
    assert any("全市场研究" in warning for warning in body["warnings"])


def test_relation_study_hit_count_matches_date_scan_day_row(client, db_session):
    """跨功能不变量：REL_ 命中次数 == Date Scan 流日行同关系事件数。"""
    code = _seed_stock(db_session)
    from src.core.orchestration.date_relation_scan import _load_static_natal_cache
    from src.core.schemas.stock import StockBirthProfile
    from src.core.stock.birth_profile import from_row
    from src.engines.bazi.bazi_engine import BaziEngine
    from src.engines.calendar.calendar_engine import CalendarEngine
    from src.research.relation_study import build_relation_observations

    scan = client.post("/api/v1/research/date-scan", json={"date": "2026-09-22", "limit": 1})
    assert scan.status_code == 200, scan.text
    scan_body = scan.json()
    detail = client.get(
        f"/api/v1/research/date-scan/{scan_body['scan_id']}/stocks/{code}",
        params={"target_date": "2026-09-22"},
    )
    assert detail.status_code == 200, detail.text
    row = detail.json()["row"]
    matrix = row["matrix"]
    day_events = [
        event
        for matrix_row in matrix["rows"] if matrix_row["source_pillar"] == "day"
        for cell in matrix_row["cells"] for event in cell["events"]
    ]
    assert day_events, "样本日流日行没有事件，无法验证跨功能一致性"
    relation = day_events[0]["relation_type"]
    expected_count = sum(1 for event in day_events if event["relation_type"] == relation)

    profile_row = db_session.execute(
        select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code == code,
            StockBirthProfileRow.birth_basis == "listing_open",
            StockBirthProfileRow.birth_profile_version == "v2-phase4b-listing_open",
        )
    ).scalars().one()
    profile = StockBirthProfile.model_validate(from_row(profile_row))
    observations = build_relation_observations(
        stock_code=code,
        profile=profile,
        as_of_date=date(2026, 9, 22),
        relation_type=relation,
        bazi=BaziEngine(),
        calendar=CalendarEngine(),
        use_static_natal=_load_static_natal_cache().get(code),
    )
    assert len(observations) == 1
    observation = observations[0]
    assert observation.raw_value["hit_count"] == expected_count, (
        f"REL_ 因子命中 {observation.raw_value['hit_count']} != 流日行事件数 {expected_count}"
    )
    assert observation.normalized_value == float(expected_count)
    assert observation.rule_version == settings.relation_rule_version
    assert observation.raw_value["aggregate_scope"] == "external_day_row"
    assert observation.raw_value["matrix_target_scope"] == ["year", "month", "day"]
    assert relation in row["relation_types"] or expected_count == 0


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


def test_relation_catalog_exposes_factor_definitions(client):
    """RELATION_DEFINITION_INDEX 必须真正被业务读取（目录/研究响应），而不是死代码。"""
    catalog = client.get("/api/v1/research/relation-catalog")
    assert catalog.status_code == 200
    body = catalog.json()
    assert body["factors"]["REL_LIUHE"]["rule_version"] == settings.relation_rule_version
    assert "流日" in body["factors"]["REL_LIUHE"]["definition"]
    assert set(body["factors"]) == {
        "REL_TIANGAN_WUHE", "REL_TIANGAN_XIANGCHONG", "REL_TIANGAN_SHENG",
        "REL_TIANGAN_SHOUSHENG", "REL_TIANGAN_KE", "REL_TIANGAN_SHOUKE",
        "REL_TIANGAN_TONGWUXING", "REL_LIUHE", "REL_LIUCHONG", "REL_SANHE",
        "REL_BANHE", "REL_SANHUI", "REL_XIANGXING", "REL_SANXING", "REL_ZIXING",
        "REL_XIANGHAI", "REL_LIUPO", "REL_TONGZHI", "REL_FUYIN", "REL_FANYIN",
        "REL_TIANHEDIHE", "REL_TIANKEDICHONG",
    }


def test_relation_factor_observation_uses_v3_rule_version(client, db_session):
    """REL_* 因子的 rule_version 必须一路都来自 settings.relation_rule_version。

    覆盖三个点：因子定义注册表、观测构造器、两者与 settings 的链式一致性；
    不允许任何一处退回成字符串字面量。
    """
    from src.core.orchestration.date_relation_scan import _load_static_natal_cache
    from src.core.schemas.relation import RELATION_TYPES
    from src.core.schemas.stock import StockBirthProfile
    from src.core.stock.birth_profile import from_row
    from src.engines.bazi.bazi_engine import BaziEngine
    from src.engines.calendar.calendar_engine import CalendarEngine
    from src.factors.registry.definitions import RELATION_DEFINITION_INDEX
    from src.research.relation_study import RELATION_FACTOR_IDS, build_relation_observations

    code = _seed_stock(db_session)
    profile_row = db_session.execute(
        select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code == code,
            StockBirthProfileRow.birth_basis == "listing_open",
            StockBirthProfileRow.birth_profile_version == "v2-phase4b-listing_open",
        )
    ).scalars().one()
    profile = StockBirthProfile.model_validate(from_row(profile_row))

    # 1) 注册表：22 个 REL_* 定义必须存在，且全部走 settings
    assert set(RELATION_FACTOR_IDS) == set(RELATION_TYPES), "因子注册表必须穷尽关系目录"
    assert set(RELATION_DEFINITION_INDEX) == set(RELATION_FACTOR_IDS.values())
    for definition in RELATION_DEFINITION_INDEX.values():
        assert definition.rule_version == settings.relation_rule_version == "bazi-relation-v3"
        assert "v2" not in definition.rule_version

    # 2) 观测构造器：rule_version 与引擎观测同源
    observations = build_relation_observations(
        stock_code=code,
        profile=profile,
        as_of_date=date(2026, 9, 22),
        relation_type="六合",
        bazi=BaziEngine(),
        calendar=CalendarEngine(),
        use_static_natal=_load_static_natal_cache().get(code),
    )
    assert len(observations) == 1
    observation = observations[0]
    assert observation.rule_version == "bazi-relation-v3"
    assert observation.rule_version == settings.relation_rule_version
    # 3) 声明的日级采样时点：12:00（与 Date Scan 同一标准时刻）
    assert observation.as_of.hour == 12
    assert observation.raw_value["evaluation_time"] == "12:00:00"


def test_relation_study_and_date_scan_agree_on_pinned_relation(client, db_session):
    """固定 600519 / 2026-09-22：两个模块对**全部**目录关系在流日行计数一致。

    这是 Date Scan（detail 矩阵）与 Relation Study（build_relation_observations）
    两条代码路径的收敛不变量：命中集合必须逐关系相等，不是某个抽样关系相等。
    """
    from src.core.orchestration.date_relation_scan import _load_static_natal_cache
    from src.core.schemas.relation import RELATION_TYPES
    from src.core.schemas.stock import StockBirthProfile
    from src.core.stock.birth_profile import from_row
    from src.engines.bazi.bazi_engine import BaziEngine
    from src.engines.calendar.calendar_engine import CalendarEngine
    from src.research.relation_study import build_relation_observations

    maotai = _seed_stock(db_session, "600519")
    pingan = _seed_stock(db_session, "000001")
    scan = client.post("/api/v1/research/date-scan", json={"date": "2026-09-22", "limit": 500})
    assert scan.status_code == 200, scan.text
    scan_id = scan.json()["scan_id"]

    static_cache = _load_static_natal_cache()
    # 两个引擎无肉眼可见状态，提到循环外共享，避免 22 关系 × 2 股票 × 重建。
    bazi = BaziEngine()
    calendar = CalendarEngine()
    for code in (maotai, pingan):
        detail = client.get(
            f"/api/v1/research/date-scan/{scan_id}/stocks/{code}",
            params={"target_date": "2026-09-22"},
        )
        assert detail.status_code == 200, detail.text
        matrix = detail.json()["row"]["matrix"]
        day_events = [
            event
            for matrix_row in matrix["rows"] if matrix_row["source_pillar"] == "day"
            for cell in matrix_row["cells"] for event in cell["events"]
        ]
        day_counts: dict[str, int] = {}
        for event in day_events:
            day_counts[event["relation_type"]] = day_counts.get(event["relation_type"], 0) + 1

        profile_row = db_session.execute(
            select(StockBirthProfileRow).where(
                StockBirthProfileRow.stock_code == code,
                StockBirthProfileRow.birth_basis == "listing_open",
                StockBirthProfileRow.birth_profile_version == "v2-phase4b-listing_open",
            )
        ).scalars().one()
        profile = StockBirthProfile.model_validate(from_row(profile_row))
        for relation in RELATION_TYPES:
            observations = build_relation_observations(
                stock_code=code,
                profile=profile,
                as_of_date=date(2026, 9, 22),
                relation_type=relation,
                bazi=bazi,
                calendar=calendar,
                use_static_natal=static_cache.get(code),
            )
            assert observations[0].raw_value["hit_count"] == day_counts.get(relation, 0), (
                f"{code} × {relation}: relation-study 命中 {observations[0].raw_value['hit_count']} "
                f"!= 流日行事件数 {day_counts.get(relation, 0)}"
            )
        # 非空兜底：两只股票都必须有任一关系的非零命中，保证比较不是空集对上空集。
        assert sum(day_counts.values()) > 0

    # 钉死两个必须存在非零命中的样本，确保"计数相等"不是侥幸的恒零等式。
    detail_pingan = client.get(
        f"/api/v1/research/date-scan/{scan_id}/stocks/{pingan}",
        params={"target_date": "2026-09-22"},
    ).json()["row"]["matrix"]
    pingan_day_events = [
        event["relation_type"]
        for matrix_row in detail_pingan["rows"] if matrix_row["source_pillar"] == "day"
        for cell in matrix_row["cells"] for event in cell["events"]
    ]
    assert pingan_day_events.count("三合") == 2, "000001 在 2026-09-22 的流日行必须命中两次三合"
