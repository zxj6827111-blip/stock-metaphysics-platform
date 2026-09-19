"""Golden Case 扩展（Phase 1.1 验收 §五）：高风险计算边界。

覆盖：立春/节气精确边界、子时跨日、闰年、1900/2000/当前年份。

每个期望值都经过**独立手工勾稽**再锁定（不是"照抄库输出"）：

* 1900-01-01 甲戌日：以 2000-01-01 = 戊午（±608×60）手工推得；
  36524 天 ≡ +16 (mod 60) → 戊（4)+16=0→甲，午（6)+16=10→戌。
* 2000-02-29 丁巳日：2000-01-01 戊午 +59 天 → 丁（3）巳（5)。
* 2020-02-29 壬寅日：2000-02-29 + 7305 天 → 壬（8）寅（2)。
* 2026-09-18 乙未日：以 2024-06-15 庚戌 +825 天勾稽 → 乙（1）未（7)。
* 2024 惊蛰精确时刻由 lunar-python 给出 2024-03-05 10:22 前后换月柱。

若任何案例失败：先判断"库升级口径变化"还是"代码 bug"，
口径变化走 docs/calculation-differences-phase1.md 流程。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.engines.calendar.calendar_engine import CalendarEngine

pytestmark = pytest.mark.golden

# (年, 月, 日, 时, 分, 年柱, 月柱, 日柱, 时柱, 备注)
EXTENDED = [
    (1900, 1, 1, 0, 0, "己亥", "丙子", "甲戌", "甲子", "1900 年初（手工勾稽甲戌日）"),
    (1900, 3, 1, 12, 0, "庚子", "戊寅", "癸酉", "戊午", "1900 年惊蛰前（仍为正月建寅）"),
    (2000, 2, 29, 12, 0, "庚辰", "戊寅", "丁巳", "丙午", "2000 闰日（跨 1900 非闰年）"),
    (2020, 2, 29, 12, 0, "庚子", "戊寅", "壬寅", "丙午", "2020 闰日"),
    (2024, 3, 5, 9, 0, "甲辰", "丙寅", "戊辰", "丁巳", "惊蛰交节前（仍是寅月）"),
    (2024, 3, 5, 11, 0, "甲辰", "丁卯", "戊辰", "戊午", "惊蛰交节后（进入卯月）"),
    (2024, 6, 15, 22, 59, "甲辰", "庚午", "庚戌", "丁亥", "晚子时前"),
    (2024, 6, 15, 23, 0, "甲辰", "庚午", "辛亥", "戊子", "晚子时起点（归次日）"),
    (2024, 6, 16, 0, 30, "甲辰", "庚午", "辛亥", "戊子", "次日早子时应与昨晚 23:00 同盘"),
    (2024, 6, 16, 23, 30, "甲辰", "庚午", "壬子", "庚子", "次日晚子时再跨日"),
    (2026, 9, 18, 14, 32, "丙午", "丁酉", "乙未", "癸未", "当前年（手工勾稽乙未日）"),
]


class TestExtendedBoundaries:
    @pytest.mark.parametrize("y,mo,d,h,mi,yg,mg,dg,hg,note", EXTENDED)
    def test_extended_ganzhi(self, y, mo, d, h, mi, yg, mg, dg, hg, note):
        snap = CalendarEngine().snapshot(datetime(y, mo, d, h, mi))
        got = (snap.year_ganzhi.text, snap.month_ganzhi.text,
               snap.day_ganzhi.text, snap.hour_ganzhi.text)
        assert got == (yg, mg, dg, hg), f"{note}: {got} != {(yg, mg, dg, hg)}"


class TestLeapYearInvariants:
    """闰年结构不变量：闰日推进不破坏 60 甲子链。"""

    def test_leap_day_advances_by_one(self):
        e = CalendarEngine()
        before = e.snapshot(datetime(2020, 2, 28, 12, 0))
        leap = e.snapshot(datetime(2020, 2, 29, 12, 0))
        after = e.snapshot(datetime(2020, 3, 1, 12, 0))
        texts = [before.day_ganzhi.text, leap.day_ganzhi.text, after.day_ganzhi.text]
        stems = "甲乙丙丁戊己庚辛壬癸"
        branches = "子丑寅卯辰巳午未申酉戌亥"
        for a, b in zip(texts, texts[1:], strict=False):
            assert (stems.index(b[0]) - stems.index(a[0])) % 10 == 1
            assert (branches.index(b[1]) - branches.index(a[1])) % 12 == 1

    def test_1900_not_leap_year_day_count(self):
        """1900 非闰年：1900-02-28 与 1900-03-01 日柱相差恰好 1 位。"""
        e = CalendarEngine()
        d1 = e.snapshot(datetime(1900, 2, 28, 12, 0)).day_ganzhi.text
        d2 = e.snapshot(datetime(1900, 3, 1, 12, 0)).day_ganzhi.text
        stems = "甲乙丙丁戊己庚辛壬癸"
        branches = "子丑寅卯辰巳午未申酉戌亥"
        assert (stems.index(d2[0]) - stems.index(d1[0])) % 10 == 1
        assert (branches.index(d2[1]) - branches.index(d1[1])) % 12 == 1


class TestZishiBoundary:
    """晚子时归次日：23:00-23:59 与次日 00:00-00:59 同盘、日柱跨日。"""

    def test_late_zishi_belongs_to_next_day(self):
        e = CalendarEngine()
        late = e.snapshot(datetime(2024, 6, 15, 23, 30))
        early_next = e.snapshot(datetime(2024, 6, 16, 0, 15))
        assert late.day_ganzhi.text == early_next.day_ganzhi.text == "辛亥"
        assert late.hour_ganzhi.text == early_next.hour_ganzhi.text == "戊子"

    def test_2259_stays_same_day(self):
        e = CalendarEngine()
        a = e.snapshot(datetime(2024, 6, 15, 22, 59))
        b = e.snapshot(datetime(2024, 6, 15, 12, 0))
        assert a.day_ganzhi.text == b.day_ganzhi.text == "庚戌"
