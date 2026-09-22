"""日期关系指纹与 3×4 矩阵契约测试。"""

from __future__ import annotations

from datetime import datetime

from src.core.relations.date_relation import build_date_relation_fingerprint, build_relation_matrix
from src.core.schemas.calendar import GanZhi
from src.engines.calendar.calendar_engine import CalendarEngine


def _matrix(external: dict[str, str], natal: dict[str, str]):
    return build_relation_matrix(
        {key: GanZhi.from_text(value) for key, value in external.items()},
        {key: GanZhi.from_text(value) for key, value in natal.items()},
        day_master="壬",
    )


def _types(matrix) -> set[str]:
    return {
        event.relation_type
        for row in matrix.rows
        for cell in row.cells
        for event in cell.events
    }


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


def test_matrix_is_3_by_4_and_preserves_multiple_events_in_cell():
    matrix = _matrix(
        {"year": "丙午", "month": "丁酉", "day": "己亥"},
        {"year": "辛未", "month": "壬子", "day": "甲巳", "hour": "乙辰"},
    )
    assert [row.source_pillar for row in matrix.rows] == ["year", "month", "day"]
    assert all(len(row.cells) == 4 for row in matrix.rows)
    year_year = matrix.rows[0].cells[0]
    assert "天干五合" in year_year.relation_types
    assert "六合" in year_year.relation_types
    assert "天合地合" in year_year.relation_types
    assert len(year_year.events) >= 3


def test_external_half_harmony_and_three_meeting_are_emitted():
    matrix = _matrix(
        {"year": "丙午", "month": "丁酉", "day": "己亥"},
        {"year": "甲申", "month": "乙戌", "day": "丙卯", "hour": "丁巳"},
    )
    types = _types(matrix)
    assert "半合" in types
    assert "三会" in types or "三合" in types


def test_compound_reverse_yin_and_tian_ke_di_chong_are_versioned():
    matrix = _matrix(
        {"year": "甲子", "month": "丁酉", "day": "己亥"},
        {"year": "戊午", "month": "壬辰", "day": "甲寅", "hour": "乙巳"},
    )
    types = _types(matrix)
    assert "天克地冲" in types
    assert "反吟" in types
    for row in matrix.rows:
        for cell in row.cells:
            for event in cell.events:
                assert event.rule_version == "bazi-relation-v2"
