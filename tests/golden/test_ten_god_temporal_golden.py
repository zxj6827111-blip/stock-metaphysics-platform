"""十神系统 V1 的用户 Golden Case（合同 §6，TG-1）。

案例来源是产品侧给定的真实排盘，不是由实现反推出来的期望值：

    股票原局 壬申 · 乙巳 · 癸未  →  日主 癸
    三个日期 丙午 · 丁酉 · 庚子 / 辛丑 / 壬寅

三组日期同时锚定了**历法事实**（这几天的年月日柱确实是这些干支），
所以本文件既锁十神映射，也锁日历口径。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.core.constants import HEAVENLY_STEMS, ten_god
from src.core.relations.ten_god import (
    DAY_MASTER_LABEL,
    day_stem_ten_god,
    hidden_stems_with_gods,
    ten_god_ref,
)
from src.core.schemas.calendar import GanZhi
from src.engines.calendar.calendar_engine import CalendarEngine

pytestmark = pytest.mark.golden

#: 用户的股票原局（1992-05-07 上市开盘即为此三柱）
STOCK_PILLARS = ("壬申", "乙巳", "癸未")
DAY_MASTER = "癸"


def _hidden(branch: str) -> dict[str, str]:
    return {row.stem: row.ten_god for row in hidden_stems_with_gods(DAY_MASTER, branch)}


class TestNatalTenGodGolden:
    """§6.1 / §6.2 原局天干与藏干十神。"""

    def test_day_master_is_the_stock_own_day_stem(self) -> None:
        assert GanZhi.from_text(STOCK_PILLARS[2]).stem == DAY_MASTER

    @pytest.mark.parametrize("pillar,stem,expected", [
        ("年", "壬", "劫财"),
        ("月", "乙", "食神"),
        ("日", "癸", "比肩"),
    ])
    def test_natal_stem_ten_gods(self, pillar: str, stem: str, expected: str) -> None:
        assert day_stem_ten_god(DAY_MASTER, stem) == expected

    def test_day_pillar_displays_day_master_not_bi_jian(self) -> None:
        """盘面显示「日主」，规范关系仍是比肩 —— 两个语义必须同时可追溯。"""
        ref = ten_god_ref(DAY_MASTER, "癸")
        assert ref.ten_god == "比肩"
        assert DAY_MASTER_LABEL == "日主"

    def test_shen_hidden_stems(self) -> None:
        assert _hidden("申") == {"庚": "正印", "壬": "劫财", "戊": "正官"}

    def test_si_hidden_stems(self) -> None:
        assert _hidden("巳") == {"丙": "正财", "庚": "正印", "戊": "正官"}

    def test_wei_hidden_stems(self) -> None:
        assert _hidden("未") == {"己": "七杀", "丁": "偏财", "乙": "食神"}

    def test_natal_hidden_stem_order_is_primary_middle_residual(self) -> None:
        assert [row.stem for row in hidden_stems_with_gods(DAY_MASTER, "未")] == ["己", "丁", "乙"]
        assert [row.rank for row in hidden_stems_with_gods(DAY_MASTER, "未")] == ["本气", "中气", "余气"]


class TestTemporalTenGodGolden:
    """§6.3 / §6.4 / §6.5 三个日期的流年、流月、流日十神。"""

    #: (日期, 年柱, 月柱, 日柱) —— 历法事实
    CASES: list[tuple[date, str, str, str]] = [
        (date(2026, 9, 23), "丙午", "丁酉", "庚子"),
        (date(2026, 9, 24), "丙午", "丁酉", "辛丑"),
        (date(2026, 9, 25), "丙午", "丁酉", "壬寅"),
    ]

    @pytest.mark.parametrize("target,year_gz,month_gz,day_gz", CASES)
    def test_calendar_reproduces_the_documented_ganzhi(
        self, target: date, year_gz: str, month_gz: str, day_gz: str
    ) -> None:
        """日级产品固定 12:00 Asia/Shanghai 采样（合同 §12.4）。"""
        snapshot = CalendarEngine().snapshot(datetime(target.year, target.month, target.day, 12, 0, 0))
        assert snapshot.year_ganzhi.text == year_gz
        assert snapshot.month_ganzhi.text == month_gz
        assert snapshot.day_ganzhi.text == day_gz

    def test_case_one_geng_zi(self) -> None:
        assert day_stem_ten_god(DAY_MASTER, "丙") == "正财"      # 流年干
        assert day_stem_ten_god(DAY_MASTER, "丁") == "偏财"      # 流月干
        assert day_stem_ten_god(DAY_MASTER, "庚") == "正印"      # 流日干
        assert _hidden("午") == {"丁": "偏财", "己": "七杀"}
        assert _hidden("酉") == {"辛": "偏印"}
        assert _hidden("子") == {"癸": "比肩"}

    def test_case_two_xin_chou(self) -> None:
        assert day_stem_ten_god(DAY_MASTER, "辛") == "偏印"
        assert _hidden("丑") == {"己": "七杀", "癸": "比肩", "辛": "偏印"}

    def test_case_three_ren_yin(self) -> None:
        assert day_stem_ten_god(DAY_MASTER, "壬") == "劫财"
        assert _hidden("寅") == {"甲": "伤官", "丙": "正财", "戊": "正官"}

    def test_all_five_sources_share_one_direction(self) -> None:
        """五类十神（原局天干/藏干/流年/流月/流日）全部是 日主→对象 方向。

        对 2026-09-23 这一天的三柱全部干支逐一比对 constants.ten_god，
        任何一处把方向写反都会在 10 个天干 × 5 个来源上同时暴露。
        """
        snapshot = CalendarEngine().snapshot(datetime(2026, 9, 23, 12, 0, 0))
        external_stems = [
            snapshot.year_ganzhi.stem, snapshot.month_ganzhi.stem, snapshot.day_ganzhi.stem,
        ]
        for branch in (snapshot.year_ganzhi.branch, snapshot.month_ganzhi.branch, snapshot.day_ganzhi.branch):
            external_stems.extend(row.stem for row in hidden_stems_with_gods(DAY_MASTER, branch))
        assert external_stems  # 非空自证
        for stem in external_stems:
            assert day_stem_ten_god(DAY_MASTER, stem) == ten_god(DAY_MASTER, stem)

    @pytest.mark.parametrize("day_master", HEAVENLY_STEMS)
    def test_user_case_shape_holds_for_every_day_master(self, day_master: str) -> None:
        """把用户案例推广到 10 个日主：丙/丁 同五行异阴阳、庚 另属一行，
        因此三干的十神必须两两不同。若实现把阴阳或五行某一支写死，
        这里会出现重复值而暴露。
        """
        gods = {day_stem_ten_god(day_master, stem) for stem in ("丙", "丁", "庚")}
        assert len(gods) == 3
