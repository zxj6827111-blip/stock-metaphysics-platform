"""十神时历的时间边界测试（TG-2 核心，不依赖数据库）。

锁死三件事（合同 §12 / §23.7 / §23.8）：

1. **流年不是公历年**：换柱点是立春交节时刻，精确到秒；
2. **流月不是公历月**：十二个「节」各自换一次月柱，中气不得换月；
3. **两条独立实现必须互证**：段边界、日级 12:00 采样、以及独立重写的
   五虎遁月干推导，三者对同一时刻的月柱判断必须一致。
   只跟 CalendarEngine 自己对表的话，测不出"整体错位"。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from itertools import pairwise

import pytest

from src.core.constants import EARTHLY_BRANCHES, HEAVENLY_STEMS
from src.core.orchestration.ten_god_calendar import (
    MONTH_BOUNDARY_JIEQI,
    TenGodCalendarError,
    _at_noon,
    _read,
    segment_boundaries,
)
from src.core.schemas.relation import EVALUATION_TIME

pytestmark = pytest.mark.golden

#: 2024 十二节的**交节所在自然日**与该段月柱。
#: 期望值来源：独立重写的五虎遁推导（见 :func:`_month_stem_from_year`）
#: 加传统月支序（立春起寅），不是从被测实现里抄出来的。
JIEQI_2024: list[tuple[str, date, str]] = [
    ("立春", date(2024, 2, 4), "丙寅"),
    ("惊蛰", date(2024, 3, 5), "丁卯"),
    ("清明", date(2024, 4, 4), "戊辰"),
    ("立夏", date(2024, 5, 5), "己巳"),
    ("芒种", date(2024, 6, 5), "庚午"),
    ("小暑", date(2024, 7, 6), "辛未"),
    ("立秋", date(2024, 8, 7), "壬申"),
    ("白露", date(2024, 9, 7), "癸酉"),
    ("寒露", date(2024, 10, 8), "甲戌"),
    ("立冬", date(2024, 11, 7), "乙亥"),
    ("大雪", date(2024, 12, 6), "丙子"),
    ("小寒", date(2025, 1, 5), "丁丑"),
]

#: 五虎遁（《五虎遁年起月诀》）：甲己之年丙作首，乙庚之岁戊为头，
#: 丙辛必定寻庚起，丁壬壬位顺行流，戊癸何方发，甲寅之上好追求。
_WUHU_HEAD_STEM: dict[str, str] = {
    "甲": "丙", "己": "丙",
    "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}


def _month_ganzhi_from_year(year_stem: str, branch: str) -> str:
    """独立推导：由年干 + 月支推出月柱（寅月起算）。"""
    offset = (EARTHLY_BRANCHES.index(branch) - EARTHLY_BRANCHES.index("寅")) % 12
    head = _WUHU_HEAD_STEM[year_stem]
    stem = HEAVENLY_STEMS[(HEAVENLY_STEMS.index(head) + offset) % 10]
    return stem + branch


def _segments_from(origin_day: date, kind: str, count: int) -> list:
    return segment_boundaries(_at_noon(origin_day), count, kind=kind)


def _segment_switching(segments: list, jieqi: str, switch_day: date):
    """取出「在 switch_day 因 jieqi 而换柱」的那一段。

    刻意同时用节气名**和**交节日期定位：十二节在跨年的窗口里会出现两次
    （例如 2023-12-07 与 2024-12-06 都是大雪），只按名字查会拿到错误的那一段。
    """
    matched = [
        seg for seg in segments
        if seg.boundary_jieqi == jieqi and seg.start_at.date() == switch_day
    ]
    assert len(matched) == 1, (
        jieqi, switch_day,
        [(seg.boundary_jieqi, seg.start_at.date()) for seg in segments],
    )
    return matched[0]


def test_month_boundary_jieqi_whitelist_is_exactly_the_twelve_jie() -> None:
    """十二节白名单必须正好 12 个且不含任何中气。

    「雨水 / 春分 / 谷雨…」绝不能出现在这里 —— 那是中气，不换月柱。
    """
    assert MONTH_BOUNDARY_JIEQI == frozenset(name for name, _, _ in JIEQI_2024)
    assert len(MONTH_BOUNDARY_JIEQI) == 12
    for zhong_qi in ("雨水", "春分", "谷雨", "小满", "夏至", "大暑",
                     "处暑", "霜降", "小雪", "冬至", "大寒"):
        assert zhong_qi not in MONTH_BOUNDARY_JIEQI


class TestLichunYearBoundary:
    """流年边界 = 立春，不是 1 月 1 日。"""

    def test_year_segments_all_start_at_lichun(self) -> None:
        segments = _segments_from(date(2024, 6, 1), "year", 5)
        assert [seg.boundary_jieqi for seg in segments] == ["立春"] * 5
        assert all(seg.start_at.month == 2 and seg.start_at.day in (3, 4, 5) for seg in segments)

    def test_2024_lichun_exact_second_boundary(self) -> None:
        """立春前 1 秒仍是癸卯，立春当刻起才是甲辰。"""
        segments = _segments_from(date(2024, 2, 4), "year", 2)
        assert segments[0].ganzhi_text == "癸卯"
        assert segments[1].ganzhi_text == "甲辰"
        boundary = segments[0].end_at
        assert boundary.date() == date(2024, 2, 4)
        assert _read(boundary - timedelta(seconds=1)).year == "癸卯"
        assert _read(boundary + timedelta(seconds=1)).year == "甲辰"

    def test_january_first_is_not_a_year_boundary(self) -> None:
        """公历 1/1 不得成为换年点（BaziEngine._year_range 的旧口径正是 1/1）。"""
        segments = _segments_from(date(2024, 1, 1), "year", 2)
        assert segments[0].end_at.date() == date(2024, 2, 4)
        assert segments[0].start_at.date() == date(2023, 2, 4)

    @pytest.mark.parametrize("probe", [date(2024, 2, 3), date(2024, 2, 4), date(2024, 2, 5), date(2024, 3, 1)])
    def test_every_probe_falls_in_exactly_one_year_segment(self, probe: date) -> None:
        """半开区间必须互斥且完备：任一时刻只属于一个流年段。"""
        segments = _segments_from(date(2023, 6, 1), "year", 3)
        instant = _at_noon(probe)
        hits = [seg for seg in segments if seg.start_at <= instant < seg.end_at]
        assert len(hits) == 1, (probe, [(s.ganzhi_text, s.start_at, s.end_at) for s in segments])


class TestTwelveJieMonthBoundary:
    """流月边界 = 十二节，不是公历每月 1 号。"""

    @pytest.mark.parametrize("jieqi,switch_day,expected_pillar", JIEQI_2024)
    def test_each_jie_switches_the_month_pillar_on_its_exact_day(
        self, jieqi: str, switch_day: date, expected_pillar: str
    ) -> None:
        segments = _segments_from(date(2024, 1, 1), "month", 14)
        segment = _segment_switching(segments, jieqi, switch_day)
        assert segment.ganzhi_text == expected_pillar

    @pytest.mark.parametrize("jieqi,switch_day,expected_pillar", JIEQI_2024)
    def test_pillar_matches_independent_wuhudun_derivation(
        self, jieqi: str, switch_day: date, expected_pillar: str
    ) -> None:
        """与五虎遁独立推导对表 —— 不是拿实现和实现对表。"""
        segments = _segments_from(date(2024, 1, 1), "month", 14)
        segment = _segment_switching(segments, jieqi, switch_day)
        year_stem = _read(segment.start_at + timedelta(seconds=1)).year[0]
        assert _month_ganzhi_from_year(year_stem, segment.ganzhi_text[1]) == segment.ganzhi_text
        assert segment.ganzhi_text == expected_pillar

    def test_sixty_month_sequence_is_unbroken(self) -> None:
        """连续 60 个月段的干支必须沿六十甲子顺行，一格不错位。

        甲子表在测试里独立重建（不用 src.core.constants 的私有表），
        否则"整体错位"这类错误会同时改掉实现和期望值。
        """
        jiazi = tuple(
            HEAVENLY_STEMS[idx % 10] + EARTHLY_BRANCHES[idx % 12] for idx in range(60)
        )
        segments = _segments_from(date(2024, 1, 1), "month", 61)
        order = [seg.ganzhi_text for seg in segments]
        start = jiazi.index(order[0])
        assert order == [jiazi[(start + step) % 60] for step in range(len(order))]

    def test_zhongqi_does_not_switch_the_month_pillar(self) -> None:
        """雨水 2024-02-19 12:13 是中气：其前后月柱必须同为丙寅。"""
        assert _read(datetime(2024, 2, 19, 12, 0, 0)).month == "丙寅"
        assert _read(datetime(2024, 2, 19, 13, 0, 0)).month == "丙寅"
        boundaries = [seg.start_at.date() for seg in _segments_from(date(2024, 2, 5), "month", 2)]
        assert date(2024, 2, 19) not in boundaries

    def test_month_segments_are_contiguous_and_half_open(self) -> None:
        segments = _segments_from(date(2026, 9, 24), "month", 24)
        assert len(segments) == 24
        for current, following in pairwise(segments):
            assert current.end_at == following.start_at, "段之间不得留空洞或重叠"
            assert current.ganzhi_text != following.ganzhi_text, "相邻段必须换柱"
            assert current.next_boundary_jieqi == following.boundary_jieqi

    def test_year_segments_are_contiguous(self) -> None:
        segments = _segments_from(date(2026, 9, 24), "year", 10)
        assert len(segments) == 10
        for current, following in pairwise(segments):
            assert current.end_at == following.start_at
            assert current.ganzhi_text != following.ganzhi_text


class TestSegmentAgreesWithDaySamples:
    """段边界与日级 12:00 采样必须互证（两条路径不得各说各话）。"""

    def test_noon_month_pillar_equals_containing_segment(self) -> None:
        origin = date(2026, 1, 1)
        # 段窗口必须严格覆盖被探测的全部日子，否则下面的断言会因"取不到所属段"
        # 而变成测试自身的假失败。
        segments = _segments_from(origin, "month", 16)
        assert segments[-1].end_at > _at_noon(origin + timedelta(days=400))
        for step in range(400):
            day = origin + timedelta(days=step)
            containing = next(seg for seg in segments if seg.start_at <= _at_noon(day) < seg.end_at)
            assert _read(_at_noon(day)).month == containing.ganzhi_text, day

    def test_noon_year_pillar_equals_containing_segment(self) -> None:
        origin = date(2023, 12, 1)
        segments = _segments_from(origin, "year", 4)
        for step in range(800):
            day = origin + timedelta(days=step)
            containing = next(seg for seg in segments if seg.start_at <= _at_noon(day) < seg.end_at)
            assert _read(_at_noon(day)).year == containing.ganzhi_text, day


class TestObservationTimeContract:
    """日级产品固定 12:00，晚子时不得混进整日口径（合同 §12.4）。"""

    def test_day_product_samples_at_noon(self) -> None:
        assert EVALUATION_TIME == "12:00:00"
        assert _at_noon(date(2026, 9, 24)) == datetime(2026, 9, 24, 12, 0, 0)

    def test_late_zi_hour_does_not_change_the_day_level_row(self) -> None:
        """23:30 的日柱（sect=1 口径归次日）不得进入日级结果：
        日级只读 12:00 采样，同一自然日全天只有一个日柱。"""
        assert _read(_at_noon(date(2026, 9, 24))).day == _read(datetime(2026, 9, 24, 0, 30)).day


def test_segment_boundaries_rejects_unknown_kind() -> None:
    with pytest.raises(TenGodCalendarError, match="未知段类型"):
        segment_boundaries(_at_noon(date(2026, 9, 24)), 3, kind="hour")


def test_count_zero_returns_empty_list() -> None:
    assert segment_boundaries(_at_noon(date(2026, 9, 24)), 0, kind="month") == []
