"""十神目录与股票十神时历 API 集成测试（TG-2）。

重点验证的是**跨层一致性**，而不只是"接口返回 200"：

* 原局十神必须与 TG-1 固化的用户 Golden Case 完全一致；
* 流年/流月段的边界必须与 :mod:`tests.core.test_ten_god_calendar_boundaries`
  同源（立春、十二节）；
* 交易日四层语义（observed / published / out_of_coverage / weekend fallback）
  必须原样透传，未知不得写成 false；
* 「仅交易日」只是显示过滤，自然日底表不得少一行。
"""

from __future__ import annotations

from datetime import date, datetime
from itertools import pairwise

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import TEN_GODS
from src.db.models import StockBirthProfileRow, StockMasterRow, UniverseMembershipRow

CANONICAL_PROFILE = "v2-phase4b-listing_open"
CALENDAR_PATH = "/api/v1/research/ten-gods/stocks/{code}/calendar"


@pytest.fixture(autouse=True)
def _clear_caches():
    """隔离进程内缓存，避免不同测试的库内容与缓存键误配对。"""
    from src.core.orchestration.date_relation_scan import DATE_SCAN_CACHE
    from src.core.orchestration.ten_god_date_scan import TEN_GOD_SCAN_CACHE

    DATE_SCAN_CACHE.clear()
    TEN_GOD_SCAN_CACHE.clear()
    yield
    DATE_SCAN_CACHE.clear()
    TEN_GOD_SCAN_CACHE.clear()


def seed_stock(db_session, code: str, name: str, exchange: str, listing: date) -> str:
    """写入最小 canonical 样本：主档 + canonical 出生档案 + v4-full 成员资格。"""
    suffix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange, "SH")
    if db_session.get(StockMasterRow, code) is None:
        db_session.add(StockMasterRow(
            stock_code=code,
            wind_code=f"{code}.{suffix}",
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
def golden_stock(db_session) -> str:
    """壬申 · 乙巳 · 癸未 —— 用户给定的原局（1992-05-07 上市开盘）。"""
    return seed_stock(db_session, "600000", "golden", "SSE", date(1992, 5, 7))


# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------
def test_catalog_returns_all_enums_the_frontend_needs(client) -> None:
    response = client.get("/api/v1/research/ten-gods/catalog")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["name"] for item in body["ten_gods"]] == list(TEN_GODS)
    assert [group["name"] for group in body["ten_god_groups"]] == ["比劫", "食伤", "财星", "官杀", "印星"]
    assert all(len(group["members"]) == 2 for group in body["ten_god_groups"])
    assert body["wuxing_roles"] == ["用神", "喜神", "忌神", "仇神", "闲神", "未知"]
    assert body["verdicts"] == ["匹配", "不匹配", "未知"]
    assert body["ten_god_rule_version"] == settings.ten_god_rule_version == "ten-god-v1"


def test_catalog_declares_algorithm_direction_and_matrix_boundary(client) -> None:
    """目录必须自证"谁向日主取十神"，并显式声明 3×3 矩阵不是十神来源。"""
    body = client.get("/api/v1/research/ten-gods/catalog").json()
    assert body["day_master_source"] == "stock_natal_day_stem"
    assert body["other_stem_source"] == "temporal_or_natal_stem"
    assert body["relation_matrix_is_not_ten_god"] is True
    assert "矩阵" in body["relation_matrix_note"]
    assert body["observation_time"] == "12:00:00"
    assert body["timezone"] == "Asia/Shanghai"
    assert "不代表预期收益率" in body["disclaimer"]
    # 五类十神来源必须齐备，前端据此区分原局/藏干/流年/流月/流日
    assert body["ten_god_scopes"] == [
        "natal_stem", "natal_hidden_stem", "year_stem", "month_stem", "day_stem",
    ]


# ---------------------------------------------------------------------------
# stock calendar: natal
# ---------------------------------------------------------------------------
def test_calendar_natal_matches_the_user_golden_case(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"years": 1, "months": 1, "days": 1}).json()
    assert (body["stock"]["stock_code"], body["stock"]["exchange"]) == ("600000", "SSE")
    assert body["stock"]["birth_basis"] == "listing_open"
    assert body["stock"]["birth_profile_version"] == CANONICAL_PROFILE

    natal = body["natal"]
    assert natal["day_master"] == "癸"
    assert natal["day_master_wuxing"] == "水"
    pillars = {pillar["position"]: pillar for pillar in natal["pillars"]}
    assert [pillars[pos]["ganzhi"]["text"] for pos in ("year", "month", "day")] == ["壬申", "乙巳", "癸未"]

    assert pillars["year"]["stem"]["ten_god"] == "劫财"
    assert pillars["year"]["stem"]["display_label"] == "劫财"
    assert pillars["year"]["stem"]["is_day_master"] is False
    assert pillars["month"]["stem"]["ten_god"] == "食神"
    # 日柱：显示「日主」，规范关系仍是比肩（合同 §4）
    assert pillars["day"]["stem"]["display_label"] == "日主"
    assert pillars["day"]["stem"]["ten_god"] == "比肩"
    assert pillars["day"]["stem"]["is_day_master"] is True


@pytest.mark.parametrize("branch,expected", [
    ("申", {"庚": "正印", "壬": "劫财", "戊": "正官"}),
    ("巳", {"丙": "正财", "庚": "正印", "戊": "正官"}),
    ("未", {"己": "七杀", "丁": "偏财", "乙": "食神"}),
])
def test_calendar_natal_hidden_stems(client, golden_stock, branch: str, expected: dict) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"years": 0, "months": 0, "days": 0}).json()
    pillars = {pillar["position"]: pillar for pillar in body["natal"]["pillars"]}
    found = next(pillar for pillar in pillars.values() if pillar["branch"] == branch)
    assert {row["stem"]: row["ten_god"] for row in found["hidden_stems"]} == expected
    assert [row["rank"] for row in found["hidden_stems"]][0] == "本气"
    assert all(row["weight_is_engineering_approximation"] for row in found["hidden_stems"])


def test_natal_visible_gods_exclude_the_day_master(client, golden_stock) -> None:
    """可见天干统计不含日主（与 BaziEngine 同口径），藏干仍计入。

    本例四柱 壬申 · 乙巳 · 癸未 · 丁巳 里没有任何一个干是「癸」，
    所以比肩根本不该出现 —— 日主被计入统计会立刻把它凭空造出来。
    """
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"years": 0, "months": 0, "days": 0}).json()
    natal = body["natal"]
    assert {pillar["position"]: pillar["ganzhi"]["text"] for pillar in natal["pillars"]} == {
        "year": "壬申", "month": "乙巳", "day": "癸未", "hour": "丁巳",
    }
    assert [pillar["stem"]["display_label"] for pillar in natal["pillars"]] == ["劫财", "食神", "日主", "偏财"]
    assert natal["visible_stem_ten_gods"] == ["劫财", "食神", "偏财"]
    assert "比肩" not in natal["ten_god_counts"]
    # 藏干计入统计：申出一个庚（正印），巳出现两次（月支与时支）各出一个庚 → 共 3
    assert natal["ten_god_counts"]["正印"] == 3
    assert sum(natal["ten_god_group_counts"].values()) == sum(natal["ten_god_counts"].values())


# ---------------------------------------------------------------------------
# stock calendar: years / months / days
# ---------------------------------------------------------------------------
def test_calendar_default_ranges_are_10_years_24_months_365_days(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock)).json()
    assert len(body["years"]) == 10
    assert len(body["months"]) == 24
    assert body["natural_day_count"] == 365
    assert len(body["days"]) == 365


def test_year_segments_start_at_lichun_with_exact_offsets(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2024-02-04", "years": 3, "months": 0, "days": 0,
    }).json()
    segments = body["years"]
    assert [seg["ganzhi"]["text"] for seg in segments] == ["癸卯", "甲辰", "乙巳"]
    assert [seg["boundary_jieqi"] for seg in segments[1:]] == ["立春", "立春"]
    # 2024 立春 = 02-04 16:27:07；12:00 采样仍在立春前，所以首段是癸卯
    first_end = datetime.fromisoformat(segments[0]["end_at"])
    assert first_end.year == 2024 and first_end.month == 2 and first_end.day == 4
    assert segments[1]["stem_ten_god"] == "伤官"  # 甲木相对于癸水日主：我生、异阴阳
    assert segments[1]["stem_ten_god_group"] == "食伤"


def test_month_segments_switch_on_the_twelve_jie_not_calendar_months(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2024-05-06", "years": 0, "months": 6, "days": 0,
    }).json()
    segments = body["months"]
    # 立夏 2024-05-05 08:10 → 5/6 起段属巳月
    assert segments[0]["boundary_jieqi"] == "立夏"
    assert segments[0]["ganzhi"]["text"] == "己巳"
    assert [seg["boundary_jieqi"] for seg in segments] == [
        "立夏", "芒种", "小暑", "立秋", "白露", "寒露",
    ]
    # 段起点不得落在"每月 1 号"这种公历口径上
    assert all(seg["start_at"].split("T")[1] != "00:00:00" for seg in segments)


def test_segment_timezone_is_shanghai_and_intervals_half_open(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"years": 2, "months": 3, "days": 0}).json()
    for seg in body["years"] + body["months"]:
        assert seg["timezone"] == "Asia/Shanghai"
        assert seg["start_at"].endswith("+08:00"), seg["start_at"]
        assert seg["end_at"].endswith("+08:00")
    for current, following in pairwise(body["months"]):
        assert current["end_at"] == following["start_at"]


def test_day_rows_include_branch_hidden_stem_ten_gods(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2026-09-23", "years": 0, "months": 0, "days": 3,
    }).json()
    rows = body["days"]
    assert [(row["date"], row["ganzhi"]["text"]) for row in rows] == [
        ("2026-09-23", "庚子"), ("2026-09-24", "辛丑"), ("2026-09-25", "壬寅"),
    ]
    assert [row["stem_ten_god"] for row in rows] == ["正印", "偏印", "劫财"]
    assert [row["ten_god_group"] for row in rows] == ["印星", "印星", "比劫"]
    assert {row["stem"]: row["ten_god"] for row in rows[0]["branch_hidden_stems"]} == {"癸": "比肩"}
    assert {row["stem"]: row["ten_god"] for row in rows[1]["branch_hidden_stems"]} == {
        "己": "七杀", "癸": "比肩", "辛": "偏印",
    }
    assert {row["stem"]: row["ten_god"] for row in rows[2]["branch_hidden_stems"]} == {
        "甲": "伤官", "丙": "正财", "戊": "正官",
    }
    assert [row["year_ganzhi"] for row in rows] == ["丙午"] * 3
    assert [row["month_ganzhi"] for row in rows] == ["丁酉"] * 3


def test_every_natural_day_is_generated_including_leap_day(client, golden_stock) -> None:
    """闰年 2/29 必须出行，不得被交易日过滤吃掉。"""
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2024-02-27", "years": 0, "months": 0, "days": 4,
    }).json()
    assert [row["date"] for row in body["days"]] == [
        "2024-02-27", "2024-02-28", "2024-02-29", "2024-03-01",
    ]
    assert body["natural_day_count"] == 4


def test_day_ganzhi_follows_the_sixty_jiazi_without_gaps(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"days": 61, "years": 0, "months": 0}).json()
    stems = "甲乙丙丁戊己庚辛壬癸"
    branches = "子丑寅卯辰巳午未申酉戌亥"
    jiazi = [stems[idx % 10] + branches[idx % 12] for idx in range(60)]
    texts = [row["ganzhi"]["text"] for row in body["days"]]
    start = jiazi.index(texts[0])
    assert texts == [jiazi[(start + step) % 60] for step in range(61)]


# ---------------------------------------------------------------------------
# 交易日语义
# ---------------------------------------------------------------------------
def test_observed_trading_day_is_authoritative(client, golden_stock) -> None:
    """2024-02-19 是实测成交日 → true 且 authoritative。"""
    row = _single_day(client, golden_stock, date(2024, 2, 19))
    assert row["is_trading_day"] is True
    assert row["trading_calendar_source"] == "observed_index_days"
    assert row["trading_calendar_authoritative"] is True


def test_non_trading_day_still_has_a_ten_god_row(client, golden_stock) -> None:
    """周六必须出行：is_trading_day=false，但十神结果不得丢失。"""
    row = _single_day(client, golden_stock, date(2024, 2, 24))  # 周六
    assert row["is_trading_day"] is False
    assert row["trading_calendar_authoritative"] is True
    assert row["stem_ten_god"] in TEN_GODS
    assert row["ten_god_group"]


def test_published_calendar_days_are_marked_with_their_source(client, golden_stock) -> None:
    """2026-10-08（国庆后首个工作日）只有公布日历覆盖，必须标 published 且带证据。"""
    row = _single_day(client, golden_stock, date(2026, 10, 8))
    assert row["is_trading_day"] is True
    assert row["trading_calendar_source"] == "published_exchange_calendar"
    assert row["trading_calendar_authoritative"] is True
    assert "公布" in row["trading_calendar_degraded_reason"] or "官方" in row["trading_calendar_degraded_reason"]


def test_out_of_coverage_future_day_is_null_not_false(client, golden_stock) -> None:
    """超出实测 + 已公布范围的未来日：未知必须是 null，绝不能伪装成休市。"""
    row = _single_day(client, golden_stock, date(2027, 6, 15))
    assert row["is_trading_day"] is None
    assert row["trading_calendar_source"] == "out_of_coverage"
    assert row["trading_calendar_authoritative"] is False
    assert "超出" in row["trading_calendar_degraded_reason"]
    # 十神结果照常给出
    assert row["stem_ten_god"] in TEN_GODS


def test_weekend_rule_fallback_is_flagged_as_degraded(db_session, client) -> None:
    """BSE 未接入实测/公布日历 → 只能走周末规则，必须显式降级。"""
    seed_stock(db_session, "830799", "bse", "BSE", date(2024, 1, 2))
    body = client.get(CALENDAR_PATH.format(code="830799"), params={
        "start_date": "2024-02-19", "days": 3, "years": 0, "months": 0,
    }).json()
    sources = {row["trading_calendar_source"] for row in body["days"]}
    assert sources == {"weekend_rule_fallback"}
    assert all(row["trading_calendar_authoritative"] is False for row in body["days"])
    assert all("降级" in row["trading_calendar_degraded_reason"] or "近似" in row["trading_calendar_degraded_reason"]
               for row in body["days"])
    codes = {item["code"] for item in body["warnings"]}
    assert "TRADING_CALENDAR_WEEKEND_FALLBACK" in codes


def test_trading_view_is_display_only_and_keeps_natural_day_count(client, golden_stock) -> None:
    all_days = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2024-02-19", "days": 10, "years": 0, "months": 0, "view": "all",
    }).json()
    trading = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2024-02-19", "days": 10, "years": 0, "months": 0, "view": "trading",
    }).json()
    assert all_days["natural_day_count"] == trading["natural_day_count"] == 10
    assert trading["displayed_day_count"] < all_days["displayed_day_count"]
    assert all(row["is_trading_day"] is not False for row in trading["days"])
    codes = {item["code"] for item in trading["warnings"]}
    assert "TEN_GOD_TRADING_VIEW_IS_DISPLAY_ONLY" in codes


def test_unknown_trading_days_survive_the_trading_view(client, golden_stock) -> None:
    """view=trading 不得把 null 当成休市悄悄删掉。"""
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "start_date": "2027-06-14", "days": 4, "years": 0, "months": 0, "view": "trading",
    }).json()
    assert body["unknown_trading_day_count"] >= 1
    assert any(row["is_trading_day"] is None for row in body["days"])
    codes = {item["code"] for item in body["warnings"]}
    assert "TRADING_CALENDAR_OUT_OF_COVERAGE" in codes


def test_trading_calendar_coverage_descriptor_is_reported(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"days": 5, "years": 0, "months": 0}).json()
    status = body["trading_calendar"]
    assert status["exchange"] == "SSE"
    assert status["loaded"] is True
    assert status["observed_start"] and status["observed_end"]
    assert status["published_start"] == "2026-09-22"
    assert status["version_token"]
    assert "不等于休市" in status["note"]


# ---------------------------------------------------------------------------
# 版本、筛选、错误
# ---------------------------------------------------------------------------
def test_versions_are_all_present_and_match_settings(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"days": 1, "years": 0, "months": 0}).json()
    versions = body["versions"]
    assert versions["ten_god_rule_version"] == settings.ten_god_rule_version
    assert versions["calendar_engine_version"] == settings.calendar_engine_version
    assert versions["bazi_engine_version"] == settings.bazi_engine_version
    assert versions["birth_profile_version"] == CANONICAL_PROFILE
    assert versions["trading_calendar_version_token"]
    assert "不构成收益预测或交易建议" in body["disclaimer"]
    assert "独立维度" in body["disclaimer"]


def test_day_filters_are_and_semantics_and_do_not_change_ten_god(client, golden_stock) -> None:
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "days": 40, "years": 0, "months": 0, "ten_god": "正财",
    }).json()
    assert body["days"]
    assert {row["stem_ten_god"] for row in body["days"]} == {"正财"}
    assert body["filters_applied"] == {"ten_god": "正财"}
    # 复合：再加十神组必须是空集（正财的组是财星，不可能是印星）
    conflict = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "days": 40, "years": 0, "months": 0, "ten_god": "正财", "ten_god_group": "印星",
    }).json()
    assert conflict["days"] == []
    assert conflict["natural_day_count"] == 40  # 底表不受过滤影响


@pytest.mark.parametrize("field", ["verdict", "wuxing_role", "ten_god", "ten_god_group"])
def test_each_filter_dimension_selects_exactly_its_own_rows(client, golden_stock, field: str) -> None:
    """对每个维度逐一验证：过滤结果 = 未过滤结果里该字段等于该值的行集合。

    这条测试同时锁住两件事：筛选是精确的（不多不少），
    以及筛选**不改变**任何一行的十神/喜忌值（合同 §23.4 / §23.5）。
    """
    attribute = {"ten_god": "stem_ten_god"}.get(field, field)
    baseline = client.get(CALENDAR_PATH.format(code=golden_stock), params={
        "days": 60, "years": 0, "months": 0,
    }).json()["days"]
    values = sorted({row[attribute] for row in baseline if row[attribute]})
    assert values, f"{field} 在 60 天窗口内不应全为空"
    for value in values:
        filtered = client.get(CALENDAR_PATH.format(code=golden_stock), params={
            "days": 60, "years": 0, "months": 0, field: value,
        }).json()
        expected = [row for row in baseline if row[attribute] == value]
        assert filtered["filters_applied"] == {field: value}
        assert filtered["natural_day_count"] == 60, "底表行数不得被筛选改变"
        assert [row["date"] for row in filtered["days"]] == [row["date"] for row in expected]
        # 被选中的行，其全部维度值必须与未过滤时逐字相同
        for got, want in zip(filtered["days"], expected, strict=True):
            assert got == want


def test_verdict_unknown_is_not_the_same_as_mismatch(client, golden_stock) -> None:
    """未知与不匹配必须是两个可区分的取值（AGENTS.md §2.4 不可用语义）。"""
    body = client.get(CALENDAR_PATH.format(code=golden_stock), params={"days": 60, "years": 0, "months": 0}).json()
    by_verdict = {}
    for row in body["days"]:
        by_verdict.setdefault(row["verdict"], []).append(row)
    for verdict_value, rows in by_verdict.items():
        flag = {row["is_yong_or_xi"] for row in rows}
        if verdict_value == "未知":
            assert flag == {None}
        elif verdict_value == "匹配":
            assert flag == {True}
        else:
            assert flag == {False}
    assert "未知" != "不匹配"  # 明确：两者不是同一个桶


def test_unknown_filter_enums_are_rejected(client, golden_stock) -> None:
    """未知枚举必须被拒，且报错文案指向 catalog（前端据此重建下拉项）。"""
    for params in (
        {"ten_god": "必涨"},
        {"ten_god_group": "财"},
        {"wuxing_role": "吉神"},
        {"verdict": "大概匹配"},
    ):
        response = client.get(CALENDAR_PATH.format(code=golden_stock), params={"days": 1, **params})
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "INVALID_REQUEST"
        assert "catalog" in error["message"]


def test_missing_birth_profile_is_404_not_empty_calendar(client, db_session) -> None:
    response = client.get(CALENDAR_PATH.format(code="900001"))
    assert response.status_code == 404
    assert "出生档案" in response.json()["error"]["message"]


def test_view_and_range_parameters_are_validated(client, golden_stock) -> None:
    assert client.get(CALENDAR_PATH.format(code=golden_stock), params={"view": "trading_day"}).status_code == 422
    assert client.get(CALENDAR_PATH.format(code=golden_stock), params={"days": 5000}).status_code == 422


def _single_day(client, code: str, day: date) -> dict:
    body = client.get(CALENDAR_PATH.format(code=code), params={
        "start_date": day.isoformat(), "days": 1, "years": 0, "months": 0,
    }).json()
    assert len(body["days"]) == 1
    return body["days"][0]
