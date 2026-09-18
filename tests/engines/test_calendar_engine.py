"""CalendarEngine 测试（历法与黄历基础字段）。

覆盖：公历/农历、干支（立春换年 / 节气换月）、节气、生肖、纳音、
建除十二值、十二神、黄黑道、冲煞、彭祖百忌、吉神方位。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.constants import BRANCH_WUXING, EARTHLY_BRANCHES, HEAVENLY_STEMS, STEM_WUXING


class TestGanzhiBasics:
    def test_stems_and_branches_tables(self):
        assert len(HEAVENLY_STEMS) == 10
        assert len(EARTHLY_BRANCHES) == 12
        assert set(STEM_WUXING) == set(HEAVENLY_STEMS)
        assert set(BRANCH_WUXING) == set(EARTHLY_BRANCHES)

    def test_known_date_ganzhi(self, calendar_engine):
        """2001-08-27 09:30 → 辛巳年 丙申月 壬戌日 乙巳时。"""
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.year_ganzhi.text == "辛巳"
        assert snap.month_ganzhi.text == "丙申"
        assert snap.day_ganzhi.text == "壬戌"
        assert snap.hour_ganzhi.text == "乙巳"

    def test_year_boundary_uses_lichun_not_lunar_new_year(self, calendar_engine):
        """立春换年：2024-02-04 立春前后年柱应不同。

        2024 年春节为 2 月 10 日；若按农历正月初一换年，
        2 月 5 日的年柱仍会是癸卯，这是错误的。
        """
        before = calendar_engine.snapshot(datetime(2024, 2, 3, 12, 0))
        after = calendar_engine.snapshot(datetime(2024, 2, 5, 12, 0))
        assert before.year_ganzhi.text == "癸卯"
        assert after.year_ganzhi.text == "甲辰"

    def test_month_boundary_uses_jieqi(self, calendar_engine):
        """月柱以『节』换月：2024-03-05 惊蛰前后月柱应不同。"""
        before = calendar_engine.snapshot(datetime(2024, 3, 4, 12, 0))
        after = calendar_engine.snapshot(datetime(2024, 3, 6, 12, 0))
        assert before.month_ganzhi.text == "丙寅"
        assert after.month_ganzhi.text == "丁卯"

    def test_hour_pillar_follows_wushudun(self, calendar_engine):
        """五鼠遁：壬日巳时应为乙巳。"""
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.day_ganzhi.stem == "壬"
        assert snap.hour_ganzhi.text == "乙巳"

    def test_midnight_hour_belongs_to_zishi(self, calendar_engine):
        """23:00 之后属次日子时（晚子时口径）。"""
        snap = calendar_engine.snapshot(datetime(2024, 11, 15, 23, 30))
        assert snap.hour_ganzhi.branch == "子"


class TestJieqi:
    def test_prev_next_jieqi_present(self, calendar_engine):
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.jieqi.prev_name == "处暑"
        assert snap.jieqi.next_name == "白露"
        assert snap.jieqi.prev_at is not None
        assert snap.jieqi.next_at is not None
        assert snap.jieqi.next_at > snap.jieqi.prev_at

    def test_days_from_prev_jie(self, calendar_engine):
        """处暑 2001-08-23 09:27 → 距 08-27 09:30 约 4 天。"""
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.jieqi.days_from_prev_jie is not None
        assert 3.9 < snap.jieqi.days_from_prev_jie < 4.1

    def test_lichun_day_itself(self, calendar_engine):
        """2024 立春为 02-04 16:27，之前仍属癸卯年。"""
        before = calendar_engine.snapshot(datetime(2024, 2, 4, 10, 0))
        after = calendar_engine.snapshot(datetime(2024, 2, 4, 20, 0))
        assert before.year_ganzhi.text == "癸卯"
        assert after.year_ganzhi.text == "甲辰"


class TestLunarAndHuangliFields:
    def test_lunar_date_and_zodiac(self, calendar_engine):
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.lunar.year == 2001
        assert snap.lunar.month == 7
        assert snap.lunar.day == 9
        assert snap.lunar.zodiac == "蛇"

    def test_huangli_basic_fields(self, calendar_engine):
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.duty_officer == "满"          # 建除十二值
        assert snap.day_tian_shen == "司命"        # 十二神
        assert snap.day_tian_shen_type == "黄道"   # 黄黑道
        assert snap.day_tian_shen_luck == "吉"
        assert snap.chong_desc == "(丙辰)龙"
        assert snap.sha_direction == "北"
        assert "壬不泱水" in snap.pengzu_gan
        assert snap.cai_shen_direction
        assert snap.xi_shen_direction
        assert snap.xiu

    def test_nayin_present(self, calendar_engine):
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.year_ganzhi.nayin == "白蜡金"
        assert snap.month_ganzhi.nayin == "山下火"
        assert snap.day_ganzhi.nayin == "大海水"

    def test_raw_source_is_kept_for_audit(self, calendar_engine):
        """原始第三方输出必须保留（可审计），但业务层不读它。"""
        snap = calendar_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.raw_source["lunar_full"]
        assert snap.raw_source["eight_char"] == "辛巳 丙申 壬戌 乙巳"

    def test_engine_version_recorded(self, calendar_engine):
        snap = calendar_engine.snapshot(datetime(2024, 1, 1, 0, 0))
        assert snap.engine_version
        assert snap.engine_id == "calendar"


class TestRobustness:
    @pytest.mark.parametrize(
        "moment",
        [
            datetime(1990, 1, 1, 0, 0),
            datetime(2024, 2, 29, 12, 0),   # 闰日
            datetime(2030, 12, 31, 23, 59),
        ],
    )
    def test_various_moments_do_not_crash(self, calendar_engine, moment):
        snap = calendar_engine.snapshot(moment)
        assert snap.year_ganzhi.text
        assert snap.day_ganzhi.text

    def test_missing_when_raises(self, calendar_engine):
        from src.engines.base import EngineContext

        with pytest.raises(ValueError):
            calendar_engine.calculate_chart(EngineContext())
