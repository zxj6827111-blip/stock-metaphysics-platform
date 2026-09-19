"""Golden Cases —— 固定案例回归测试（architecture §74）。

目的：**当第三方库（lunar-python）升级、或本项目规则内核调整时，
能立刻发现结果变化**。

这些期望值来自当前锁定版本：
    lunar-python 1.4.8
    smx-bazi-native 1.0.0

**如果某个 Golden Case 失败，不要直接改期望值。**
必须：
  1. 先确认是"升级导致的口径变化"还是"代码 bug"；
  2. 如果是口径变化，写入 `docs/calculation-differences.md`；
  3. 提升 engine_version 并重新跑全部案例。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.engines.calendar.calendar_engine import CalendarEngine

pytestmark = pytest.mark.golden


class TestGoldenGanzhi:
    """公历 → 干支（含立春换年、节气换月边界）。"""

    #: 期望值锁定自 lunar-python 1.4.8（2026-09 冻结）。
    #:
    #: 校验方式（不是"照着库抄一遍"）：
    #:   1. 主案例 2001-08-27 09:30（贵州茅台上市时刻）用 60 甲子手工推过：
    #:      以 2000-01-01 = 戊午日为锚点，闰年 366 + 238 = 604 天，604 mod 60 = 4，
    #:      戊+4 = 壬、午+4 = 戌 → 壬戌日，与期望一致；
    #:      时柱用五鼠遁（丁壬起庚子，壬日巳时 = 乙巳）独立验证一致。
    #:   2. 见 TestGoldenStructuralInvariants —— 连续 90 天日柱必须严格按 60 甲子推进，
    #:      这能捕获"整体错位一天"这类系统性错误。
    #:
    #: 若某条期望值失败：不要直接改期望值。先判断是"库升级导致的口径变化"
    #: 还是"代码 bug"，口径变化必须写入 docs/calculation-differences.md 并升版本。
    GOLDEN = [
        # (年, 月, 日, 时, 分, 年柱, 月柱, 日柱, 时柱, 备注)
        (2001, 8, 27, 9, 30, "辛巳", "丙申", "壬戌", "乙巳", "贵州茅台上市时刻（手工验证）"),
        (1991, 4, 3, 9, 30, "辛未", "辛卯", "癸卯", "丁巳", "平安银行上市时刻"),
        (2018, 6, 11, 9, 30, "戊戌", "戊午", "甲戌", "己巳", "宁德时代上市时刻"),
        (2000, 1, 1, 0, 0, "己卯", "丙子", "戊午", "壬子", "千禧年零点（锚点日）"),
        (1984, 2, 2, 12, 0, "癸亥", "乙丑", "丙寅", "甲午", "甲子年起点前（立春前）"),
        (2024, 2, 4, 20, 0, "甲辰", "丙寅", "戊戌", "壬戌", "2024 立春后"),
        (2024, 2, 4, 10, 0, "癸卯", "乙丑", "戊戌", "丁巳", "2024 立春前"),
        (1999, 12, 31, 23, 30, "己卯", "丙子", "戊午", "壬子", "跨年夜子时（晚子时归次日）"),
    ]

    @pytest.mark.parametrize("y,m,d,h,mi,yg,mg,dg,hg,note", GOLDEN)
    def test_ganzhi(self, y, m, d, h, mi, yg, mg, dg, hg, note):
        engine = CalendarEngine()
        snap = engine.snapshot(datetime(y, m, d, h, mi))
        assert snap.year_ganzhi.text == yg, f"{note}: 年柱 {snap.year_ganzhi.text} != {yg}"
        assert snap.month_ganzhi.text == mg, f"{note}: 月柱 {snap.month_ganzhi.text} != {mg}"
        assert snap.day_ganzhi.text == dg, f"{note}: 日柱 {snap.day_ganzhi.text} != {dg}"
        assert snap.hour_ganzhi.text == hg, f"{note}: 时柱 {snap.hour_ganzhi.text} != {hg}"


class TestGoldenJieqi:
    """节气边界（月柱换柱的唯一依据）。"""

    #: 月柱换柱点（十二「节」）。注意：立春换的是**年柱**，不是月柱，
    #: 因此立春单独由 test_lichun_changes_year_pillar 覆盖。
    JIEQI_GOLDEN = [
        (2024, 3, 5, "惊蛰", "丙寅", "丁卯"),
        (2024, 4, 4, "清明", "丁卯", "戊辰"),
        (2024, 8, 7, "立秋", "辛未", "壬申"),
        (2024, 11, 7, "立冬", "甲戌", "乙亥"),
        (2024, 12, 6, "大雪", "乙亥", "丙子"),
    ]

    @pytest.mark.parametrize("y,m,d,name,before_monthzhi,after_monthzhi", JIEQI_GOLDEN)
    def test_month_changes_at_jieqi(self, y, m, d, name, before_monthzhi, after_monthzhi):
        engine = CalendarEngine()
        prev = engine.snapshot(datetime(y, m, d, 0, 1))
        nxt = engine.snapshot(datetime(y, m, d, 23, 59))
        # 交节当日：0 点与 23 点之间必有一次换月
        assert {prev.month_ganzhi.text, nxt.month_ganzhi.text} == {before_monthzhi, after_monthzhi}, (
            f"{name} 当日月柱应跨越 {before_monthzhi} → {after_monthzhi}，"
            f"实际 {prev.month_ganzhi.text} → {nxt.month_ganzhi.text}"
        )

    def test_lichun_changes_year_pillar(self):
        """立春当日：年柱由癸卯变为甲辰（月柱同时由乙丑变丙寅）。"""
        engine = CalendarEngine()
        prev = engine.snapshot(datetime(2024, 2, 4, 0, 1))
        nxt = engine.snapshot(datetime(2024, 2, 4, 23, 59))
        assert {prev.year_ganzhi.text, nxt.year_ganzhi.text} == {"癸卯", "甲辰"}
        assert {prev.month_ganzhi.text, nxt.month_ganzhi.text} == {"乙丑", "丙寅"}

    def test_prev_next_jieqi_named(self):
        engine = CalendarEngine()
        snap = engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert snap.jieqi.prev_name == "处暑"
        assert snap.jieqi.next_name == "白露"


class TestGoldenFourPillars:
    """完整四柱装配（含藏干 / 十神 / 纳音）。"""

    def test_maotai_full_chart(self, bazi_engine):
        chart = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2024, 11, 15, 14, 32),
            stock_code="600519",
        )
        assert chart.year_pillar.ganzhi.text == "辛巳"
        assert chart.month_pillar.ganzhi.text == "丙申"
        assert chart.day_pillar.ganzhi.text == "壬戌"
        assert chart.hour_pillar.ganzhi.text == "乙巳"
        assert chart.day_master == "壬"
        assert chart.day_master_wuxing == "水"
        assert chart.year_pillar.nayin == "白蜡金"
        assert chart.month_pillar.nayin == "山下火"
        assert chart.day_pillar.nayin == "大海水"
        assert chart.hour_pillar.nayin == "覆灯火"
        assert chart.ming_gong == "壬辰"
        assert chart.tai_yuan == "丁亥"


class TestGoldenTenGods:
    """十神（相对日主）。"""

    def test_maotai_ten_gods(self, bazi_engine):
        chart = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2024, 11, 15, 14, 32),
        )
        assert chart.year_pillar.stem_ten_god == "正印"     # 壬 ← 辛
        assert chart.month_pillar.stem_ten_god == "偏财"    # 壬 → 丙
        assert chart.hour_pillar.stem_ten_god == "伤官"     # 壬 ← 乙
        assert chart.year_pillar.hidden_ten_gods == ["偏财", "偏印", "七杀"]

    def test_two_charts_differ(self, bazi_engine):
        a = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30), as_of=datetime(2024, 11, 15, 14, 32)
        )
        b = bazi_engine.build_chart(
            birth_datetime=datetime(2018, 6, 11, 9, 30), as_of=datetime(2024, 11, 15, 14, 32)
        )
        assert a.day_master != b.day_master
        assert a.year_pillar.ganzhi.text != b.year_pillar.ganzhi.text


class TestGoldenHuangli:
    """黄历字段（建除 / 十二神 / 黄黑道 / 冲煞 / 神煞）。"""

    GOLDEN = [
        (2001, 8, 27, "满", "司命", "黄道", "(丙辰)龙", "北"),
        (2024, 11, 15, "成", "明堂", "黄道", None, None),
        (2024, 1, 1, None, None, None, None, None),
    ]

    @pytest.mark.parametrize("y,m,d,duty,tianshen,type_,chong,sha", GOLDEN)
    def test_huangli(self, huangli_engine, y, m, d, duty, tianshen, type_, chong, sha):
        snap = huangli_engine.snapshot(datetime(y, m, d, 12, 0))
        p = snap.primary
        if duty is not None:
            assert p.duty_officer == duty
        if tianshen is not None:
            assert p.day_tian_shen == tianshen
        if type_ is not None:
            assert p.day_tian_shen_type == type_
        if chong is not None:
            assert p.chong_desc == chong
        if sha is not None:
            assert p.sha_direction == sha

    def test_all_fields_are_non_empty_for_known_day(self, huangli_engine):
        p = huangli_engine.snapshot(datetime(2001, 8, 27, 9, 30)).primary
        for field in (
            "solar_text", "lunar_text", "year_ganzhi", "month_ganzhi", "day_ganzhi",
            "zodiac", "day_nayin", "duty_officer", "day_tian_shen", "day_tian_shen_type",
            "chong_desc", "sha_direction", "pengzu_gan", "pengzu_zhi",
            "cai_shen_direction", "xi_shen_direction",
        ):
            assert getattr(p, field), f"黄历字段 {field} 为空"


class TestGoldenTemporal:
    """流年 / 流月 / 流日。"""

    CASES = [
        # (as_of, 流年干支, 流月干支, 流日干支)
        (datetime(2024, 11, 15, 14, 32), "甲辰", "乙亥", "癸未"),
        (datetime(2020, 3, 20, 10, 0), "庚子", "己卯", None),
        (datetime(2015, 6, 15, 9, 30), "乙未", "壬午", None),
    ]

    @pytest.mark.parametrize("as_of,year_gz,month_gz,day_gz", CASES)
    def test_temporal_pillars(self, bazi_engine, as_of, year_gz, month_gz, day_gz):
        chart = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30), as_of=as_of
        )
        assert chart.current_year_pillar.ganzhi.text == year_gz
        assert chart.current_month_pillar.ganzhi.text == month_gz
        if day_gz is not None:
            assert chart.current_day_pillar.ganzhi.text == day_gz


class TestGoldenStructuralInvariants:
    """结构性不变量 —— 比逐点期望值更强的回归保护。

    逐点期望值只能发现"这一个日期算错了"，
    而结构性不变量能发现"整套算法整体错位"。
    """

    def test_day_pillar_advances_through_60_jiazi(self):
        """连续自然日的日柱必须严格按 60 甲子逐位推进（+1 天干、+1 地支）。"""
        from datetime import timedelta

        from src.core.constants import BRANCH_INDEX, STEM_INDEX

        engine = CalendarEngine()
        cursor = datetime(2024, 1, 1, 12, 0)
        prev: tuple[int, int] | None = None
        for _ in range(120):
            snap = engine.snapshot(cursor)
            cur = (STEM_INDEX[snap.day_ganzhi.stem], BRANCH_INDEX[snap.day_ganzhi.branch])
            if prev is not None:
                assert (cur[0] - prev[0]) % 10 == 1, f"{cursor.date()} 天干推进异常"
                assert (cur[1] - prev[1]) % 12 == 1, f"{cursor.date()} 地支推进异常"
            prev = cur
            cursor += timedelta(days=1)

    def test_year_pillar_changes_exactly_once_per_year(self):
        """年柱在一年内只变化一次（立春），且必须按 60 甲子顺序推进。"""
        engine = CalendarEngine()
        changes = []
        cursor = datetime(2024, 1, 1, 12, 0)
        prev = engine.snapshot(cursor).year_ganzhi.text
        for _ in range(365):
            cursor += timedelta(days=1)
            cur = engine.snapshot(cursor).year_ganzhi.text
            if cur != prev:
                changes.append(cursor.date())
                prev = cur
        assert len(changes) == 1, f"2024 年年柱变化次数异常：{changes}"
        assert changes[0].month == 2, "年柱变化应发生在 2 月（立春）"

    def test_month_pillar_changes_exactly_12_times(self):
        """月柱一年内必须变化 12 次（十二节）。"""
        from datetime import timedelta

        engine = CalendarEngine()
        cursor = datetime(2024, 1, 1, 12, 0)
        prev = engine.snapshot(cursor).month_ganzhi.text
        changes = 0
        for _ in range(365):
            cursor += timedelta(days=1)
            cur = engine.snapshot(cursor).month_ganzhi.text
            if cur != prev:
                changes += 1
                prev = cur
        assert changes == 12, f"2024 年月柱变化 {changes} 次，应为 12 次"

    def test_hour_pillar_uses_five_rats_rule(self):
        """时柱必须符合五鼠遁：日干 → 子时天干映射固定。"""
        from src.core.constants import HEAVENLY_STEMS

        expected_zi_stem = {
            "甲": "甲", "己": "甲",
            "乙": "丙", "庚": "丙",
            "丙": "戊", "辛": "戊",
            "丁": "庚", "壬": "庚",
            "戊": "壬", "癸": "壬",
        }
        engine = CalendarEngine()
        checked = 0
        cursor = datetime(2024, 3, 1, 0, 30)   # 子时
        for _ in range(10):
            snap = engine.snapshot(cursor)
            day_stem = snap.day_ganzhi.stem
            assert snap.hour_ganzhi.stem == expected_zi_stem[day_stem], (
                f"{cursor.date()} 日干 {day_stem} 的子时时干应为 {expected_zi_stem[day_stem]}"
            )
            cursor = cursor.replace(day=cursor.day + 1)
            checked += 1
        assert checked == 10
        assert all(s in HEAVENLY_STEMS for s in expected_zi_stem.values())


class TestGoldenStability:
    """同一输入必须完全可复现 —— 这是"结果可追溯"的基础。"""

    def test_repeated_calls_identical(self, bazi_engine, huangli_engine):
        kwargs = dict(birth_datetime=datetime(2001, 8, 27, 9, 30),
                      as_of=datetime(2024, 11, 15, 14, 32), stock_code="600519")
        dumps = [
            bazi_engine.build_chart(**kwargs).model_dump_json(exclude={"calculated_at"})
            for _ in range(3)
        ]
        assert len(set(dumps)) == 1

        h = [
            huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=31).model_dump_json(
                # raw_huangli 内含 generated_at（每次调用必然不同），
                # 属于元信息而非计算结果，比较时排除
                exclude={"calculated_at", "raw_huangli"}
            )
            for _ in range(3)
        ]
        assert len(set(h)) == 1

    def test_engine_versions_pinned(self):
        from src.core.config import settings

        assert settings.calendar_engine_version == "lunar-python-1.4.8"
        assert settings.bazi_engine_version == "smx-bazi-native-1.0.0"
        assert settings.birth_profile_version == "v1"
        # v1.1 是有意提升：修复 B_YEAR_005/007/008 的流年关系接线错误
        # （005≡010 三合重复、刑冲错位、害未计算）。全过程见 docs/calculation-differences-phase1.md
        assert settings.factor_rule_version == "v1.1"


class TestGoldenStockBirthProfiles:
    """四类代表股票的出生档案（会话一验收标准要求抽样 4 只）。"""

    CASES = [
        # (代码, 板块, 交易所, 上市日, 期望出生日, 期望出生时刻)
        ("600519", "主板", "SSE", date(2001, 8, 27), date(2001, 8, 27), "09:30"),
        ("000001", "主板", "SZSE", date(1991, 4, 3), date(1991, 4, 3), "09:30"),
        ("300750", "创业板", "SZSE", date(2018, 6, 11), date(2018, 6, 11), "09:30"),
        ("688981", "科创板", "SSE", date(2020, 7, 16), date(2020, 7, 16), "09:30"),
        ("830799", "北交所", "BSE", date(2023, 9, 1), date(2023, 9, 1), "09:30"),
    ]

    @pytest.mark.parametrize("code,board,exchange,listing,exp_date,exp_time", CASES)
    def test_birth_profile(self, code, board, exchange, listing, exp_date, exp_time):
        from src.core.schemas.common import Exchange
        from src.core.schemas.stock import StockMaster
        from src.core.stock.birth_profile import build_birth_profile

        stock = StockMaster(
            stock_code=code, exchange=Exchange(exchange), board=board, listing_date=listing
        )
        profile = build_birth_profile(stock)
        assert profile.birth_datetime.date() == exp_date
        assert profile.birth_datetime.strftime("%H:%M") == exp_time
        assert profile.timezone == "Asia/Shanghai"
