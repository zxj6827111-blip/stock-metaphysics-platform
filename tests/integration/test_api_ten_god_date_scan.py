"""日期 → 全市场十神扫描 API 测试（TG-3）。

本文件承担合同 §23 的多条硬不变量，其中最关键的是第 1 条：

    同一股票、同一日期，在「十神时历」与「日期扫描」两个入口得到的
    流日十神必须完全一致。

两个入口共用 ``build_day_stem_verdict``，因此这条一致性是结构性的，
本文件用真实请求把它钉住，防止将来任何一方被改成"从 3×3 矩阵聚合十神"。
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import TEN_GOD_GROUP, TEN_GODS
from src.core.relations.date_relation import build_day_stem_verdict
from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow
from tests.integration.test_api_ten_god_calendar import CALENDAR_PATH, seed_stock

CANONICAL_PROFILE = "v2-phase4b-listing_open"
SCAN_PATH = "/api/v1/research/ten-gods/date-scan"
LEGACY_SCAN_PATH = "/api/v1/research/date-scan"

#: 5 只股票的样本池。688981 的上市日（2026-09-01）刻意设在整个池的最后，
#: 用它作为"可证据化边界"：晚于它的查询日期必须走 latest-known 分支。
UNIVERSE_CUTOFF = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _clear_caches():
    from src.core.orchestration.date_relation_scan import DATE_SCAN_CACHE
    from src.core.orchestration.ten_god_date_scan import TEN_GOD_SCAN_CACHE

    DATE_SCAN_CACHE.clear()
    TEN_GOD_SCAN_CACHE.clear()
    yield
    DATE_SCAN_CACHE.clear()
    TEN_GOD_SCAN_CACHE.clear()


@pytest.fixture
def market_seed(db_session) -> list[str]:
    codes = [
        seed_stock(db_session, "600000", "癸未日主", "SSE", date(1992, 5, 7)),
        seed_stock(db_session, "600519", "贵州茅台", "SSE", date(2001, 8, 27)),
        seed_stock(db_session, "000001", "平安银行", "SZSE", date(1991, 4, 3)),
        seed_stock(db_session, "300750", "宁德时代", "SZSE", date(2018, 6, 11)),
        seed_stock(db_session, "688981", "边界新股", "SSE", UNIVERSE_CUTOFF),
    ]
    # 再放一只"只进池、无出生档案"的股票：验证不可用不被 0 冒充。
    # 临时库是 session 级的，多个测试共用，因此必须幂等插入。
    if db_session.get(StockMasterRow, "601999") is None:
        db_session.add(StockMasterRow(
            stock_code="601999", wind_code="601999.SH", name="无档案股", exchange="SSE",
            board="主板", listing_date=date(2007, 1, 1), source="test",
            data_quality_json={"grade": "C", "score": 0.2, "notes": []},
        ))
    if db_session.execute(
        select(UniverseMembershipRow).where(
            UniverseMembershipRow.universe_version == "v4-full",
            UniverseMembershipRow.stock_code == "601999",
        )
    ).scalars().first() is None:
        db_session.add(UniverseMembershipRow(
            universe_version="v4-full", stock_code="601999", exchange="SSE", board="主板",
            list_date=date(2007, 1, 1), status="active", source="test",
            source_snapshot="test", delist_source="test",
        ))
    db_session.flush()
    db_session.commit()
    assert db_session.execute(
        select(StockBirthProfileRow).where(StockBirthProfileRow.stock_code == "601999")
    ).scalars().first() is None
    return codes


def _expected_verdict(db_session, code: str, target: date, day_stem: str):
    """绕开十神服务，独立重算一次流日判定作为期望值。

    刻意不复用 ``ten_god_calendar`` / ``ten_god_date_scan`` 的任何 helper，
    否则"服务与自己对表"就测不出服务写错了。
    """
    from datetime import datetime

    from src.core.stock.birth_profile import from_row
    from src.engines.bazi.bazi_engine import BaziEngine

    row = db_session.execute(
        select(StockBirthProfileRow).where(StockBirthProfileRow.stock_code == code)
    ).scalars().first()
    profile = from_row(row)
    chart = BaziEngine().build_chart(
        birth_datetime=profile.birth_datetime.replace(tzinfo=None),
        as_of=datetime(target.year, target.month, target.day, 12),
        variant_mode=profile.variant_mode,
        stock_code=code,
    )
    return build_day_stem_verdict(
        day_master=chart.day_master,
        day_stem=day_stem,
        yong_shen=tuple(chart.yong_shen.yong_shen),
        xi_shen=tuple(chart.yong_shen.xi_shen),
        ji_shen=tuple(chart.yong_shen.ji_shen),
        chou_shen=tuple(chart.yong_shen.chou_shen),
        xian_shen=tuple(chart.yong_shen.xian_shen),
    )


def _scan(client, payload: dict) -> dict:
    response = client.post(SCAN_PATH, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# 与内核的一致性
# ---------------------------------------------------------------------------
def test_row_matches_build_day_stem_verdict_exactly(client, db_session, market_seed) -> None:
    """单只股票的结果必须能用 build_day_stem_verdict 逐字段重算出来。"""
    body = _scan(client, {"date": "2026-09-23", "limit": 50})
    row = next(item for item in body["rows"] if item["stock_code"] == "600000")
    expected = _expected_verdict(db_session, "600000", date(2026, 9, 23), "庚")
    assert (row["day_master"], row["day_stem"]) == ("癸", "庚")
    assert row["ten_god"] == expected.ten_god == "正印"
    assert row["ten_god_group"] == expected.ten_god_group == "印星"
    assert row["day_stem_wuxing"] == expected.day_stem_wuxing == "金"
    assert row["wuxing_role"] == expected.wuxing_role
    assert row["verdict"] == expected.verdict
    assert row["is_yong_or_xi"] == expected.is_yong_or_xi
    assert row["reason"] == expected.reason


def test_ten_god_is_never_aggregated_from_the_relation_matrix(client, market_seed) -> None:
    """每行只有一个十神，且等于 ten_god(日主, 流日干)。

    3×3 矩阵的流日行里带着三份十神标签（年干/月干/日干各对一次日主），
    谁要是把它们 flatten 成列表端上来，这里会立刻失败。
    """
    body = _scan(client, {"date": "2026-09-24", "limit": 50})
    for row in body["rows"]:
        if row["availability"] != "ok":
            continue
        assert row["ten_god"] in TEN_GODS
        assert row["ten_god_group"] == TEN_GOD_GROUP[row["ten_god"]]
        # 行结构里根本没有"多十神列表"字段：矩阵聚合无路可走
        assert "ten_gods" not in row


# ---------------------------------------------------------------------------
# 过滤语义
# ---------------------------------------------------------------------------
def test_single_ten_god_filter_returns_only_that_god(client, market_seed) -> None:
    body = _scan(client, {"date": "2026-09-23", "ten_god": "正财", "limit": 50})
    assert all(row["ten_god"] == "正财" for row in body["rows"])
    assert set(body["filtered_ten_god_counts"]) <= {"正财"}
    # 与"逐股重算后再筛"的全集一致
    unfiltered = _scan(client, {"date": "2026-09-23", "limit": 50})
    expected_codes = sorted(
        row["stock_code"] for row in unfiltered["rows"] if row["ten_god"] == "正财"
    )
    assert sorted(row["stock_code"] for row in body["rows"]) == expected_codes


@pytest.mark.parametrize("group", ["比劫", "食伤", "财星", "官杀", "印星"])
def test_group_filter_equals_union_of_its_two_member_gods(client, market_seed, group: str) -> None:
    members = [god for god, god_group in TEN_GOD_GROUP.items() if god_group == group]
    grouped = _scan(client, {"date": "2026-09-23", "ten_god_group": group, "limit": 50})
    unfiltered = _scan(client, {"date": "2026-09-23", "limit": 50})["rows"]
    expected = sorted(row["stock_code"] for row in unfiltered if row["ten_god"] in members)
    assert sorted(row["stock_code"] for row in grouped["rows"]) == expected
    assert all(row["ten_god_group"] == group for row in grouped["rows"])


def test_verdict_filter_does_not_change_ten_god_values(client, market_seed) -> None:
    """按喜用匹配过滤时，每只股票的十神必须保持原值 —— 两维度不得互染。"""
    unfiltered = {row["stock_code"]: row for row in _scan(client, {"date": "2026-09-23", "limit": 50})["rows"]}
    for verdict in ("匹配", "不匹配", "未知"):
        filtered = _scan(client, {"date": "2026-09-23", "verdict": verdict, "limit": 50})["rows"]
        assert all(row["verdict"] == verdict for row in filtered)
        for row in filtered:
            assert row["ten_god"] == unfiltered[row["stock_code"]]["ten_god"]
            assert row["ten_god_group"] == unfiltered[row["stock_code"]]["ten_god_group"]


def test_relation_type_and_ten_god_are_anded(client, market_seed) -> None:
    """relation_type + ten_god 必须是 AND，而不是"先按关系筛、十神随便给"。

    期望值全部由未过滤结果在测试里自己求交集得出；同时要求两个单条件
    各自非空 —— 否则"交集为空"可能只是因为样本池本来就空。
    """
    unfiltered = _scan(client, {"date": "2026-09-23", "limit": 50})["rows"]
    ok_rows = [row for row in unfiltered if row["availability"] == "ok"]
    relation = next(
        (
            item for item in sorted({t for row in ok_rows for t in row["relation_types"]})
            if any(item in row["relation_types"] for row in ok_rows)
        ),
        None,
    )
    assert relation, "样本池未命中任何关系类型，无法验证复合过滤"
    god = sorted({row["ten_god"] for row in ok_rows})[0]

    only_relation = [row for row in ok_rows if relation in row["relation_types"]]
    only_god = [row for row in ok_rows if row["ten_god"] == god]
    assert only_relation and only_god
    expected = sorted(
        row["stock_code"] for row in only_relation if row["ten_god"] == god
    )

    body = _scan(client, {"date": "2026-09-23", "relation_type": relation, "ten_god": god, "limit": 50})
    assert sorted(row["stock_code"] for row in body["rows"]) == expected
    assert body["filtered_count"] == len(expected)
    for row in body["rows"]:
        assert relation in row["relation_types"] and row["ten_god"] == god
    # 单条件的 filtered_count 必须大于等于交集，证明 AND 真的在收窄集合
    single = _scan(client, {"date": "2026-09-23", "relation_type": relation, "limit": 50})
    assert single["filtered_count"] == len(only_relation) >= len(expected)


def test_filtering_happens_before_pagination(client, market_seed) -> None:
    """filtered_count 必须是"过滤后、分页前"的集合大小，与 limit/offset 无关。"""
    _scan(client, {"date": "2026-09-23", "limit": 50})  # 预热缓存
    unfiltered = _scan(client, {"date": "2026-09-23", "limit": 50})["rows"]
    # 动态选一个在样本池里出现 ≥2 次的十神组，避免依赖特定行情日
    counts: dict[str, int] = {}
    for row in unfiltered:
        counts[row["ten_god_group"]] = counts.get(row["ten_god_group"], 0) + 1
    group = max(counts, key=lambda key: counts[key])
    expected = [row for row in unfiltered if row["ten_god_group"] == group]
    total = len(expected)
    assert total >= 2, f"样本池里 {group} 行太少，无法验证分页"

    first = _scan(client, {"date": "2026-09-23", "ten_god_group": group, "limit": 1, "offset": 0})
    second = _scan(client, {"date": "2026-09-23", "ten_god_group": group, "limit": 1, "offset": 1})
    assert first["filtered_count"] == second["filtered_count"] == total
    assert first["returned_count"] == 1
    assert [row["stock_code"] for row in first["rows"]] == [expected[0]["stock_code"]]
    assert [row["stock_code"] for row in second["rows"]] == [expected[1]["stock_code"]]

    whole = _scan(client, {"date": "2026-09-23", "ten_god_group": group, "limit": 50, "offset": 0})
    assert [row["stock_code"] for row in whole["rows"]] == [row["stock_code"] for row in expected]
    # offset 越界必须返回空页，而不是悄悄回退到全集
    overflow = _scan(client, {"date": "2026-09-23", "ten_god_group": group, "limit": 10, "offset": total + 5})
    assert overflow["rows"] == []
    assert overflow["filtered_count"] == total


def _members_listed_by(db_session, as_of: date) -> set[str]:
    """直接从库里算出 as_of 当日应在池内的股票，不写死数字。

    临时库是 session 级的，其他集成测试也会往 v4-full 里塞股票；
    任何"样本池正好 N 只"的硬编码都会随测试执行顺序而变化。
    """
    rows = db_session.execute(
        select(UniverseMembershipRow).where(UniverseMembershipRow.universe_version == "v4-full")
    ).scalars().all()
    return {row.stock_code for row in rows if row.list_date <= as_of}


def test_counts_are_defined_and_internally_consistent(client, db_session, market_seed) -> None:
    body = _scan(client, {"date": "2026-09-23", "limit": 500})
    assert body["stock_total"] == len(_members_listed_by(db_session, UNIVERSE_CUTOFF))
    assert body["stock_total"] >= 6
    # 601999 没有出生档案 → 不可用，不计入 valid
    assert body["valid_scan_count"] == sum(
        1 for row in body["rows"] if row["availability"] == "ok"
    )
    assert body["valid_scan_count"] == body["stock_total"] - sum(
        1 for row in body["rows"] if row["availability"] != "ok"
    )
    assert sum(body["ten_god_counts"].values()) == body["valid_scan_count"]
    assert sum(body["ten_god_group_counts"].values()) == body["valid_scan_count"]
    assert sum(body["verdict_counts"].values()) == body["valid_scan_count"]
    assert set(body["ten_god_counts"]) <= set(TEN_GODS)
    assert body["universe_mode"] == "latest_known_for_future"


def test_unavailable_stock_is_not_faked_with_zero(client, market_seed) -> None:
    body = _scan(client, {"date": "2026-09-23", "limit": 50})
    row = next(item for item in body["rows"] if item["stock_code"] == "601999")
    assert row["availability"] == "unavailable"
    assert row["ten_god"] == ""
    assert row["s_raw"] is None and row["v_raw"] is None and row["u_raw"] is None
    assert row["unavailable"] == ["stock_birth_profile"]
    codes = {item["code"] for item in body["warnings"]}
    assert "TEN_GOD_SCAN_PROFILE_UNAVAILABLE" in codes


# ---------------------------------------------------------------------------
# 两个入口的一致性（合同 §23.1）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("target", ["2026-09-23", "2026-09-24", "2026-09-25", "2024-02-19"])
def test_calendar_and_date_scan_agree_for_the_same_stock_and_date(client, market_seed, target: str) -> None:
    scan_row = next(
        row for row in _scan(client, {"date": target, "limit": 50})["rows"] if row["stock_code"] == "600000"
    )
    calendar = client.get(CALENDAR_PATH.format(code="600000"), params={
        "start_date": target, "days": 1, "years": 0, "months": 0,
    }).json()
    day_row = calendar["days"][0]
    assert day_row["stem_ten_god"] == scan_row["ten_god"]
    assert day_row["ten_god_group"] == scan_row["ten_god_group"]
    assert day_row["wuxing_role"] == scan_row["wuxing_role"]
    assert day_row["verdict"] == scan_row["verdict"]
    assert day_row["is_yong_or_xi"] == scan_row["is_yong_or_xi"]
    assert day_row["reason"] == scan_row["reason"]
    assert day_row["ganzhi"]["text"] == (scan_row["day_stem"] + day_row["branch"])


# ---------------------------------------------------------------------------
# 股票池语义
# ---------------------------------------------------------------------------
def test_historical_date_uses_strict_point_in_time_universe(client, db_session, market_seed) -> None:
    """2024-02-19 早于可证据化边界 → 必须是严格 PIT，只含当日已上市的股票。"""
    body = _scan(client, {"date": "2024-02-19", "limit": 500})
    assert body["universe_mode"] == "point_in_time"
    assert body["universe_as_of"] == "2024-02-19"
    assert body["future_universe_assumption"] == ""
    assert {row["stock_code"] for row in body["rows"]} == _members_listed_by(db_session, date(2024, 2, 19))
    assert "688981" not in {row["stock_code"] for row in body["rows"]}, (
        "2026-09-01 才上市的股票不得出现在 2024 日的 PIT 池里"
    )
    assert {"600000", "600519", "000001", "601999"} <= {row["stock_code"] for row in body["rows"]}
    # 同一 universe 在边界日之后立刻变成"最新已知"模式，成员数只能变多不能变少
    future = _scan(client, {"date": "2026-09-23", "limit": 500})
    assert future["universe_mode"] == "latest_known_for_future"
    assert future["stock_total"] >= body["stock_total"]


def test_future_date_freezes_latest_known_universe_and_says_so(client, market_seed) -> None:
    body = _scan(client, {"date": "2027-03-01", "limit": 50})
    assert body["universe_mode"] == "latest_known_for_future"
    assert body["universe_as_of"] == UNIVERSE_CUTOFF.isoformat()
    assert "冻结" in body["future_universe_assumption"]
    assert "不包含未知的未来上市与未来退市事件" in body["future_universe_assumption"]
    codes = {row["stock_code"] for row in body["rows"]}
    assert "688981" in codes
    warning = next(item for item in body["warnings"] if item["code"] == "TEN_GOD_FUTURE_UNIVERSE_FROZEN")
    assert "冻结" in warning["message"]
    assert warning["severity"] == "warning"


# ---------------------------------------------------------------------------
# 契约与错误处理
# ---------------------------------------------------------------------------
def test_legacy_date_scan_contract_is_untouched(client, market_seed) -> None:
    """旧端点的请求体与响应结构必须逐字段保持原样（AGENTS.md §2.3）。"""
    response = client.post(LEGACY_SCAN_PATH, json={"date": "2026-09-23", "limit": 50, "offset": 0})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "scan_id", "target_date", "fingerprint", "versions", "scope", "stock_total",
        "valid_scan_count", "returned_count", "filtered_count", "offset", "limit",
        "group_counts", "relation_type_counts", "query", "rows", "warnings", "cache",
        "disclaimer",
    }
    assert set(body["query"]) == {
        "date", "universe", "birth_basis", "birth_profile_version",
        "relation_rule_version", "relation_type", "sort", "offset", "limit",
    }
    row_keys = set(body["rows"][0])
    assert "day_stem_verdict" in row_keys
    assert "ten_gods" in row_keys  # 旧字段仍在，未被删除或改名
    # 旧请求体不接受十神字段：多传必须被拒，而不是被静默吸收
    rejected = client.post(LEGACY_SCAN_PATH, json={"date": "2026-09-23", "ten_god": "正财"})
    assert rejected.status_code in (422, 400), rejected.text
    # 两个端点对同一股票同一天给出同一个十神
    legacy_row = next(row for row in body["rows"] if row["stock_code"] == "600000")
    ten_god_scan = _scan(client, {"date": "2026-09-23", "limit": 50})
    new_row = next(row for row in ten_god_scan["rows"] if row["stock_code"] == "600000")
    assert legacy_row["day_stem_verdict"]["ten_god"] == new_row["ten_god"]
    assert legacy_row["day_stem_verdict"]["verdict"] == new_row["verdict"]
    assert legacy_row["relation_types"] == new_row["relation_types"]


def test_old_scan_relation_type_filter_still_works(client, market_seed) -> None:
    legacy = client.post(LEGACY_SCAN_PATH, json={"date": "2026-09-23", "relation_type": "六合", "limit": 50})
    assert legacy.status_code == 200
    assert all("六合" in row["relation_types"] for row in legacy.json()["rows"])


@pytest.mark.parametrize("payload,expected_status", [
    ({"date": "2026-09-23", "ten_god_rule_version": "ten-god-v0"}, 422),
    ({"date": "2026-09-23", "relation_rule_version": "bazi-relation-v2"}, 422),
    ({"date": "2026-09-23", "universe": "v3-old"}, 422),
    ({"date": "2026-09-23", "birth_profile_version": "v1"}, 422),
    ({"date": "2026-09-23", "birth_basis": "ipo_date"}, 422),
    ({"date": "2026-09-23", "ten_god": "必涨"}, 422),
    ({"date": "2026-09-23", "relation_type": "不存在的合"}, 422),
    ({"date": "2026-09-23", "sort": "ten_god"}, 200),
    ({"date": "2026-09-23", "sort": "bogus"}, 422),
])
def test_bad_versions_and_enums_are_rejected(client, market_seed, payload, expected_status) -> None:
    response = client.post(SCAN_PATH, json=payload)
    assert response.status_code == expected_status, response.text


def test_sort_by_ten_god_groups_rows_in_canonical_order(client, market_seed) -> None:
    rows = _scan(client, {"date": "2026-09-23", "limit": 50, "sort": "ten_god"})["rows"]
    order = {god: idx for idx, god in enumerate(TEN_GODS)}
    keys = [order.get(row["ten_god"], len(order)) for row in rows]
    assert keys == sorted(keys)


def test_repeat_request_hits_cache_and_scan_id_is_stable(client, market_seed) -> None:
    first = _scan(client, {"date": "2026-09-23", "limit": 5})
    second = _scan(client, {"date": "2026-09-23", "limit": 5})
    assert first["scan_id"] == second["scan_id"]
    assert first["cache"]["hit"] is False
    assert second["cache"]["hit"] is True
    # 过滤条件不进底表缓存键：换筛选不应触发全量重算
    filtered = _scan(client, {"date": "2026-09-23", "limit": 5, "ten_god": "正财"})
    assert filtered["cache"]["hit"] is True


def test_response_declares_its_ten_god_provenance(client, market_seed) -> None:
    body = _scan(client, {"date": "2026-09-23", "limit": 5})
    assert body["day_master_source"] == "stock_natal_day_stem"
    assert body["ten_god_source"] == "ten_god(stock_day_master, target_day_stem)"
    assert body["observation_time"] == "12:00:00"
    assert body["timezone"] == "Asia/Shanghai"
    assert body["versions"]["ten_god_rule_version"] == settings.ten_god_rule_version
    assert "不等于「适合」" in body["disclaimer"]
