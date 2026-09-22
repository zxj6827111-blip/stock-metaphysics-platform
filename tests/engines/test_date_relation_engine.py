"""日期关系内核契约测试（bazi-relation-v3 / relation-matrix-v2 / 3×3）。"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.constants import TEN_GOD_GROUP, ten_god
from src.core.relations.date_relation import (
    NATAL_POSITIONS,
    build_date_relation_fingerprint,
    build_day_stem_verdict,
    build_relation_matrix,
    classify_relation_group,
    day_relation_types,
    events_for_source_pillar,
    flatten_events,
)
from src.core.schemas.calendar import GanZhi
from src.core.schemas.relation import RELATION_TYPES, RelationMatrix
from src.engines.calendar.calendar_engine import CalendarEngine

EXTERNAL_2026_09_22 = {"year": "丙午", "month": "丁酉", "day": "己亥"}


def _matrix(external: dict[str, str], natal: dict[str, str]) -> RelationMatrix:
    return build_relation_matrix(
        {key: GanZhi.from_text(value) for key, value in external.items()},
        {key: GanZhi.from_text(value) for key, value in natal.items()},
        day_master="壬",
    )


def _types(matrix: RelationMatrix) -> set[str]:
    return {event.relation_type for event in flatten_events(matrix)}


def test_date_fingerprint_golden_2026_09_22():
    snapshot = CalendarEngine().snapshot(datetime(2026, 9, 22, 12))
    fingerprint = build_date_relation_fingerprint(snapshot)
    assert (fingerprint.year, fingerprint.month, fingerprint.day) == ("丙午", "丁酉", "己亥")
    assert "天干五合:辛" in fingerprint.stem_targets["丙"]
    assert "天干五合:壬" in fingerprint.stem_targets["丁"]
    assert "天干五合:甲" in fingerprint.stem_targets["己"]
    assert "六冲:子" in fingerprint.branch_targets["午"]
    assert "六冲:卯" in fingerprint.branch_targets["酉"]
    assert "六冲:巳" in fingerprint.branch_targets["亥"]
    assert "六破" in fingerprint.supported_relations
    assert fingerprint.unavailable_relations == []
    # 指纹版本按 v3 决策保持 v1（与股票矩阵口径解耦）。
    assert fingerprint.fingerprint_version == "date-relation-fingerprint-v1"


# ---------------------------------------------------------------------------
# 1–2：矩阵 3×3，且同 cell 多事件全部保留
# ---------------------------------------------------------------------------


def test_matrix_is_3_by_3_and_preserves_multiple_events_in_cell():
    matrix = _matrix(
        EXTERNAL_2026_09_22,
        {"year": "辛未", "month": "壬子", "day": "甲辰"},
    )
    assert [row.source_pillar for row in matrix.rows] == ["year", "month", "day"]
    assert all(len(row.cells) == 3 for row in matrix.rows)
    assert sum(len(row.cells) for row in matrix.rows) == 9
    assert [cell.target_pillar for cell in matrix.rows[0].cells] == ["year", "month", "day"]
    year_year = matrix.rows[0].cells[0]
    assert "天干五合" in year_year.relation_types
    assert "六合" in year_year.relation_types
    assert "天合地合" in year_year.relation_types
    assert len(year_year.events) >= 3
    # 新契约：行级 relation_types 是该行全部 cell 的类型去重稳定序。
    for row in matrix.rows:
        expected = list(dict.fromkeys(
            event.relation_type for cell in row.cells for event in cell.events
        ))
        assert row.relation_types == expected


def test_hour_is_not_a_matrix_position():
    """即使传入时柱，矩阵目标列也只取年/月/日（时柱退出择日关系范围）。"""
    natal_with_hour = {"year": "辛未", "month": "壬子", "day": "甲辰", "hour": "乙巳"}
    matrix = build_relation_matrix(
        {key: GanZhi.from_text(value) for key, value in EXTERNAL_2026_09_22.items()},
        {key: GanZhi.from_text(value) for key, value in natal_with_hour.items()},
        day_master="壬",
    )
    assert matrix.columns == ["year", "month", "day"]
    assert NATAL_POSITIONS == ("year", "month", "day")
    assert all(cell.target_pillar != "hour" for row in matrix.rows for cell in row.cells)


def test_matrix_requires_year_month_day():
    with pytest.raises(ValueError, match="natal 缺少必要柱位"):
        build_relation_matrix(
            {key: GanZhi.from_text(value) for key, value in EXTERNAL_2026_09_22.items()},
            {key: GanZhi.from_text(value) for key, value in {"year": "辛未", "day": "甲辰"}.items()},
            day_master="壬",
        )


def test_external_half_harmony_and_three_meeting_are_emitted():
    matrix = _matrix(
        EXTERNAL_2026_09_22,
        {"year": "甲申", "month": "乙戌", "day": "丙卯"},
    )
    types = _types(matrix)
    assert "半合" in types
    assert "三会" in types or "三合" in types


def test_compound_reverse_yin_and_tian_ke_di_chong_are_versioned():
    matrix = _matrix(
        {"year": "甲子", "month": "丁酉", "day": "己亥"},
        {"year": "戊午", "month": "壬辰", "day": "甲寅"},
    )
    types = _types(matrix)
    assert "天克地冲" in types
    assert "反吟" in types
    for row in matrix.rows:
        for cell in row.cells:
            for event in cell.events:
                assert event.rule_version == "bazi-relation-v3"


# ---------------------------------------------------------------------------
# 3–5：行级类型、catalog 不变量、版本号
# ---------------------------------------------------------------------------


def test_row_relation_types_match_cells_and_day_row_helpers():
    matrix = _matrix(EXTERNAL_2026_09_22, {"year": "辛未", "month": "壬子", "day": "甲辰"})
    day_row = next(row for row in matrix.rows if row.source_pillar == "day")
    day_events = events_for_source_pillar(matrix, "day")
    assert day_relation_types(matrix) == day_row.relation_types
    assert [event.relation_type for event in day_events] == [
        event.relation_type for cell in day_row.cells for event in cell.events
    ]
    # 其余两行的事件不得混入 day 聚合。
    other_types = {
        event.relation_type
        for row in matrix.rows if row.source_pillar != "day"
        for cell in row.cells for event in cell.events
    }
    assert set(day_row.relation_types) <= other_types | set(day_row.relation_types)


def test_all_emitted_relation_types_are_in_canonical_catalog():
    """不变量：引擎能 emit 的每一种关系类型都必须在 catalog 里（含天干受生/受克）。"""
    catalog = set(RELATION_TYPES)
    assert {"天干受生", "天干受克"} <= catalog
    matrices = [
        _matrix({"year": "丙午", "month": "丁酉", "day": "己亥"}, {"year": "辛未", "month": "壬子", "day": "甲辰"}),
        _matrix({"year": "甲子", "month": "丁酉", "day": "己亥"}, {"year": "戊午", "month": "壬辰", "day": "甲寅"}),
        _matrix({"year": "丙午", "month": "丁酉", "day": "己亥"}, {"year": "甲申", "month": "乙戌", "day": "丙卯"}),
        _matrix({"year": "癸卯", "month": "乙丑", "day": "戊戌"}, {"year": "癸卯", "month": "乙丑", "day": "戊戌"}),
    ]
    emitted = set().union(*(_types(matrix) for matrix in matrices))
    assert emitted <= catalog, f"引擎 emit 但 catalog 不存在: {sorted(emitted - catalog)}"


def test_relation_rule_and_matrix_schema_versions():
    matrix = _matrix(EXTERNAL_2026_09_22, {"year": "辛未", "month": "壬子", "day": "甲辰"})
    assert matrix.relation_rule_version == "bazi-relation-v3"
    assert matrix.schema_version == "relation-matrix-v2"
    assert matrix.columns == ["year", "month", "day"]


# ---------------------------------------------------------------------------
# 6：节气边界 —— 标准采样 12:00 是主动定义（hour 并非"死参数"）
# ---------------------------------------------------------------------------


def test_jieqi_boundary_hour_affects_month_and_year_pillar():
    """2024-02-04 立春（约 16:27）：12:00 仍在癸卯/乙丑，17:00 已换甲辰/丙寅。"""
    engine = CalendarEngine()
    noon = engine.snapshot(datetime(2024, 2, 4, 12))
    after_transit = engine.snapshot(datetime(2024, 2, 4, 17))
    assert (noon.year_ganzhi.text, noon.month_ganzhi.text) == ("癸卯", "乙丑")
    assert (after_transit.year_ganzhi.text, after_transit.month_ganzhi.text) == ("甲辰", "丙寅")
    assert noon.day_ganzhi.text == after_transit.day_ganzhi.text == "戊戌"


# ---------------------------------------------------------------------------
# 7：十神 golden —— 固定日主遍历十天干
# ---------------------------------------------------------------------------

#: 甲（阳木）日主对十天干的标准十神表（子平通行口径）。
TEN_GOD_OF_JIA = {
    "甲": "比肩", "乙": "劫财", "丙": "食神", "丁": "伤官", "戊": "偏财",
    "己": "正财", "庚": "七杀", "辛": "正官", "壬": "偏印", "癸": "正印",
}
#: 癸（阴水）日主抽查点（生我异性=正印；同我=比肩）。
TEN_GOD_OF_GUI_SPOT = {"甲": "伤官", "丙": "正财", "戊": "正官", "庚": "正印", "癸": "比肩"}


def test_ten_god_golden_full_mapping_for_jia_day_master():
    for stem, expected in TEN_GOD_OF_JIA.items():
        assert ten_god("甲", stem) == expected, f"甲日主见{stem}应为{expected}"


def test_ten_god_golden_spot_values_for_gui_day_master():
    for stem, expected in TEN_GOD_OF_GUI_SPOT.items():
        assert ten_god("癸", stem) == expected


def test_day_stem_verdict_ten_god_follows_day_stem_only():
    """固定日主与喜忌，流日干改变 → 十神按规则改变（不由事件列表决定）。"""
    base = dict(day_master="甲", yong_shen=["水"], xi_shen=["金"], ji_shen=["火"], chou_shen=["土"], xian_shen=["木"])
    seen: dict[str, str] = {}
    for stem, expected in TEN_GOD_OF_JIA.items():
        verdict = build_day_stem_verdict(day_stem=stem, **base)
        assert verdict.ten_god == expected
        assert verdict.ten_god_group == TEN_GOD_GROUP[expected]
        seen[stem] = verdict.ten_god
    assert len(set(seen.values())) == 10, "同一日主对十天干的十神必须两两不同"


# ---------------------------------------------------------------------------
# 8：喜忌 verdict —— 五类角色 + 未知
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stem", "wuxing", "role", "verdict", "is_yong_or_xi"),
    [
        ("壬", "水", "用神", "匹配", True),
        ("庚", "金", "喜神", "匹配", True),
        ("丙", "火", "忌神", "不匹配", False),
        ("戊", "土", "仇神", "不匹配", False),
        ("甲", "木", "闲神", "不匹配", False),
    ],
)
def test_day_stem_verdict_five_roles(stem, wuxing, role, verdict, is_yong_or_xi):
    result = build_day_stem_verdict(
        day_master="甲", day_stem=stem,
        yong_shen=["水"], xi_shen=["金"], ji_shen=["火"], chou_shen=["土"], xian_shen=["木"],
    )
    assert (result.day_stem_wuxing, result.wuxing_role) == (wuxing, role)
    assert (result.verdict, result.is_yong_or_xi) == (verdict, is_yong_or_xi)


def test_day_stem_verdict_unknown_is_not_mismatch():
    empty = build_day_stem_verdict(day_master="甲", day_stem="丙")
    assert empty.verdict == "未知"
    assert empty.is_yong_or_xi is None
    assert empty.wuxing_role == "未知"
    assert "未知不等于不匹配" in empty.reason

    unlisted = build_day_stem_verdict(
        day_master="甲", day_stem="丙", yong_shen=["水"], xi_shen=["金"], ji_shen=[], chou_shen=[], xian_shen=[],
    )
    assert unlisted.verdict == "未知"
    assert unlisted.is_yong_or_xi is None


def test_day_stem_verdict_reason_separates_ten_god_and_wuxing_role():
    result = build_day_stem_verdict(
        day_master="甲", day_stem="己",
        yong_shen=["水"], xi_shen=["金"], ji_shen=["火"], chou_shen=["土"], xian_shen=["木"],
    )
    assert result.ten_god == "正财" and result.wuxing_role == "仇神"
    assert "十神" in result.reason and "五行角色" not in result.reason
    assert "正财" in result.reason and "仇神" in result.reason
    # 禁止跨维度断言（十神 ∈ 忌神类写法）。
    assert "正财属于" not in result.reason and "正财是" not in result.reason
    assert "属于「仇神」" in result.reason and "不属于用神/喜神集合" in result.reason


def test_day_stem_verdict_invalid_input_is_unknown():
    result = build_day_stem_verdict(day_master="", day_stem="丙")
    assert result.verdict == "未知" and result.is_yong_or_xi is None
    result = build_day_stem_verdict(day_master="甲", day_stem="")
    assert result.verdict == "未知"


# ---------------------------------------------------------------------------
# 9：结构型分组（无阈值定标）
# ---------------------------------------------------------------------------


def test_classify_relation_group_is_structural():
    assert classify_relation_group(3, 0, 0) == "协同型"
    assert classify_relation_group(0, 2, 1) == "扰动型"
    assert classify_relation_group(2, 3, 4) == "混合型"
    assert classify_relation_group(0, 0, 2) == "弱关系"
    assert classify_relation_group(1, 0, 9) == "协同型"
