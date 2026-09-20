"""术数日历工具的单元测试（铁律 17：所有计算必须有测试）。

这里只测**确定性、可离线验证**的部分：
* 六十甲子序号与顺逆判定辅助
* 时辰与盘中重叠分钟
* 大运覆盖年份
* 阴阳→性别假设映射（必须与引擎枚举一致）
* 契合度口径的自洽性（用独立重算校验，不硬编码具体分值）
"""

from __future__ import annotations

from datetime import datetime

import pytest

from scripts.astrology_calendar import (
    REL_LABEL,
    REL_WEIGHT,
    YINYANG_TO_GENDER,
    YONG_WEIGHT,
    VariantMode,
    covering_dayun,
    evaluate,
    ganzhi_index,
    natal_summary,
    session_overlap_minutes,
)

BIRTH = datetime(2001, 8, 27, 9, 30)


class TestGanzhiIndex:
    def test_boundaries(self) -> None:
        assert ganzhi_index("甲子") == 0
        assert ganzhi_index("乙丑") == 1
        assert ganzhi_index("癸亥") == 59

    def test_round_trip(self) -> None:
        """六十甲子每一个都应能定位，且序号唯一。"""
        stems = "甲乙丙丁戊己庚辛壬癸"
        branches = "子丑寅卯辰巳午未申酉戌亥"
        seen = set()
        for index in range(60):
            text = stems[index % 10] + branches[index % 12]
            got = ganzhi_index(text)
            assert got == index, f"{text} 应为 {index}，得到 {got}"
            seen.add(got)
        assert len(seen) == 60

    @pytest.mark.parametrize("bad", ["", "甲", "甲子丑", "子甲", "AB"])
    def test_invalid(self, bad: str) -> None:
        assert ganzhi_index(bad) is None


class TestSessionOverlap:
    def test_trading_hours(self) -> None:
        """A 股 09:30-11:30 / 13:00-15:00 与各时辰的重叠。"""
        assert session_overlap_minutes(9) == 90    # 巳时 09:00-11:00
        assert session_overlap_minutes(11) == 30   # 午时 11:00-13:00（11:30 就午休）
        assert session_overlap_minutes(13) == 120  # 未时 13:00-15:00

    def test_non_trading_hours(self) -> None:
        for hour in (0, 3, 7, 15, 21):
            assert session_overlap_minutes(hour) == 0


class TestDayunHelpers:
    ITEMS = [
        {"start_year": 2001, "end_year": 2007, "ganzhi": ""},
        {"start_year": 2008, "end_year": 2017, "ganzhi": "乙未"},
        {"start_year": 2018, "end_year": 2027, "ganzhi": "甲午"},
    ]

    def test_covering(self) -> None:
        assert covering_dayun(self.ITEMS, 2018) == "甲午"
        assert covering_dayun(self.ITEMS, 2027) == "甲午"
        assert covering_dayun(self.ITEMS, 2001) == ""

    def test_out_of_range(self) -> None:
        assert covering_dayun(self.ITEMS, 2100) == ""

    def test_empty(self) -> None:
        assert covering_dayun([], 2020) == ""


class TestYinyangMapping:
    def test_mapping_is_explicit_and_complete(self) -> None:
        """阳→男命（FORWARD）/ 阴→女命（REVERSE）；只允许这两个键。"""
        assert set(YINYANG_TO_GENDER) == {"阳", "阴"}
        assert YINYANG_TO_GENDER["阳"][0] is VariantMode.FORWARD
        assert YINYANG_TO_GENDER["阴"][0] is VariantMode.REVERSE

    def test_not_a_default_variant(self) -> None:
        """阴阳假设不得等于引擎默认（not_applicable）——否则等于偷偷起运。"""
        default = VariantMode.NOT_APPLICABLE
        assert all(variant is not default for variant, _gender in YINYANG_TO_GENDER.values())


class TestWeightTables:
    def test_yong_weights_match_engine_domain(self) -> None:
        """引擎 _annotate_temporal 只会输出这四种标注，权重表必须与之等域。"""
        assert set(YONG_WEIGHT) == {"用神", "喜神", "忌神", "闲神"}
        assert YONG_WEIGHT["用神"] > YONG_WEIGHT["喜神"] > YONG_WEIGHT["闲神"] > YONG_WEIGHT["忌神"]

    def test_relation_weights_present(self) -> None:
        """凡引擎会返回的关系类型，都要有非零权重（否则静默漏计）。"""
        for label in REL_LABEL.values():
            assert label in REL_WEIGHT, f"{label} 缺少权重"
        assert REL_WEIGHT["相冲"] < 0 < REL_WEIGHT["六合"]


class TestEvaluateConsistency:
    """契合度必须等于各成分权重的和——用独立重算校验口径自洽。"""

    def test_score_is_exact_sum_of_components(self) -> None:
        summary = natal_summary(BIRTH)
        for level, when in (
            ("day", datetime(2026, 9, 20, 12, 0)),
            ("hour", datetime(2026, 9, 20, 10, 0)),
            ("month", datetime(2026, 10, 5, 12, 0)),
        ):
            result = evaluate(summary, when, level)
            expected = YONG_WEIGHT[result["stem_is"]] + YONG_WEIGHT[result["branch_is"]]
            for relation in result["relations"]:
                label = relation.split("·")[0]
                expected += REL_WEIGHT.get(label, 0)
            assert result["score"] == expected, f"{level} 层契合度与成分之和不符"

    def test_annotation_domain(self) -> None:
        summary = natal_summary(BIRTH)
        result = evaluate(summary, datetime(2026, 9, 20, 12, 0), "day")
        assert result["stem_is"] in YONG_WEIGHT
        assert result["branch_is"] in YONG_WEIGHT

    def test_summary_fields(self) -> None:
        summary = natal_summary(BIRTH)
        assert summary["four_pillars"] == "辛巳 丙申 壬戌 乙巳"
        assert summary["day_master"] == "壬"
