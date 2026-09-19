"""BaziEngine（smx-bazi-native）× lunar-python 对拍测试（验收 §五）。

原则：不容忍静默分歧。任何不一致都必须：

1. 在这里红掉；
2. 写入 ``docs/calculation-differences-phase1.md``；
3. 提升对应 ``engine_version``。

对拍范围（bazi-engine 为自研规则内核）：
* 四柱干支 —— 由 CalendarEngine 供给，必须等于 lunar-python EightChar；
* 藏干内容（不齐整比序，按集合比对 —— 权重排序属本项目规则细节）；
* 天干十神、藏干十神；
* 纳音。

另测：raw_chart 可复现（同输入两次计算完全一致，除审计时间戳外）。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from lunar_python import Solar  # noqa: 对拍测试是被允许的特例 —— 见下

# NOTE: tests/test_third_party_isolation.py 的白名单约束针对业务层 src/。
# 本测试文件属于"验证层"，直接引用 lunar-python 以对拍 adapter 输出，
# 这正是 adapter 隔离设计的验收测试。
from src.engines.bazi.bazi_engine import BaziEngine

pytestmark = pytest.mark.golden

CASES = [
    (2001, 8, 27, 9, 30),    # 贵州茅台上市时刻（手工锚定）
    (1991, 4, 3, 9, 30),     # 平安银行上市时刻
    (2018, 6, 11, 9, 30),    # 宁德时代上市时刻
    (2000, 2, 29, 12, 0),    # 闰日
    (1900, 1, 1, 0, 0),      # 1900 边界
    (2024, 2, 4, 20, 0),     # 立春后
    (2024, 2, 4, 10, 0),     # 立春前
    (2026, 9, 18, 14, 32),   # 当前
    (2020, 12, 21, 23, 30),  # 晚子时
    (1998, 4, 27, 15, 0),    # 五粮液上市
]


def _lunar_ref(y: int, mo: int, d: int, h: int, mi: int):
    """取 lunar-python 参考输出。

    口径对齐说明（勿删）：
    lunar-python 的 ``EightChar`` 默认 ``sect=2``（晚子时日柱不归次日），
    本项目日历引擎采用 ``sect=1``（晚子时归次日，子平通行口径）。
    两个流派**都合法**，但对拍必须显式同口径，否则 23:00-23:59 必有差 —
    该差异与处理决定已登记于 ``docs/calculation-differences-phase1.md``。
    """
    ec = Solar.fromYmdHms(y, mo, d, h, mi, 0).getLunar().getEightChar()
    ec.setSect(1)
    return {
        "year": ec.getYear(), "month": ec.getMonth(), "day": ec.getDay(), "time": ec.getTime(),
        "hide": {
            "year": list(ec.getYearHideGan()), "month": list(ec.getMonthHideGan()),
            "day": list(ec.getDayHideGan()), "time": list(ec.getTimeHideGan()),
        },
        "shishen_gan": {
            "year": ec.getYearShiShenGan(), "month": ec.getMonthShiShenGan(),
            "day": ec.getDayShiShenGan(), "time": ec.getTimeShiShenGan(),
        },
        "shishen_zhi": {
            "year": list(ec.getYearShiShenZhi()), "month": list(ec.getMonthShiShenZhi()),
            "day": list(ec.getDayShiShenZhi()), "time": list(ec.getTimeShiShenZhi()),
        },
        "nayin": {
            "year": ec.getYearNaYin(), "month": ec.getMonthNaYin(),
            "day": ec.getDayNaYin(), "time": ec.getTimeNaYin(),
        },
    }


class TestCrossValidation:
    @pytest.mark.parametrize("y,mo,d,h,mi", CASES)
    def test_pillars_match_lunar_python(self, y, mo, d, h, mi):
        chart = BaziEngine().build_chart(
            birth_datetime=datetime(y, mo, d, h, mi),
            as_of=datetime(2024, 11, 15, 14, 32),
        )
        ref = _lunar_ref(y, mo, d, h, mi)
        got = {p: getattr(chart, f"{p}_pillar").ganzhi.text for p in ("year", "month", "day", "hour")}
        exp = {"year": ref["year"], "month": ref["month"], "day": ref["day"], "hour": ref["time"]}
        assert got == exp, (
            f"{y}-{mo}-{d} 四柱不一致（不得静默取其一）: {got} vs {exp}。"
            "必须先写入 docs/calculation-differences-phase1.md 并提升 engine_version。"
        )

    @pytest.mark.parametrize("y,mo,d,h,mi", CASES)
    def test_hidden_stems_content_match(self, y, mo, d, h, mi):
        chart = BaziEngine().build_chart(
            birth_datetime=datetime(y, mo, d, h, mi),
            as_of=datetime(2024, 11, 15, 14, 32),
        )
        ref = _lunar_ref(y, mo, d, h, mi)
        for pos, ref_key in (("year", "year"), ("month", "month"),
                             ("day", "day"), ("hour", "time")):
            ours = {hs.stem for hs in getattr(chart, f"{pos}_pillar").hidden_stems}
            theirs = set(ref["hide"][ref_key])
            assert ours == theirs, f"{pos} 柱藏干内容不一致: {ours} vs {theirs}"

    @pytest.mark.parametrize("y,mo,d,h,mi", CASES)
    def test_ten_gods_match(self, y, mo, d, h, mi):
        chart = BaziEngine().build_chart(
            birth_datetime=datetime(y, mo, d, h, mi),
            as_of=datetime(2024, 11, 15, 14, 32),
        )
        ref = _lunar_ref(y, mo, d, h, mi)
        for pos, gkey, zkey in (("year", "year", "year"), ("month", "month", "month"),
                                ("day", "day", "day"), ("hour", "time", "time")):
            pillar = getattr(chart, f"{pos}_pillar")
            assert pillar.stem_ten_god == ref["shishen_gan"][gkey], (
                f"{pos} 干十神: {pillar.stem_ten_god} != {ref['shishen_gan'][gkey]}"
            )
            ours_zhi = [hs.ten_god for hs in pillar.hidden_stems]
            theirs_zhi = ref["shishen_zhi"][zkey]
            assert sorted(ours_zhi) == sorted(theirs_zhi), (
                f"{pos} 支十神(藏干): {ours_zhi} vs {theirs_zhi}"
            )

    @pytest.mark.parametrize("y,mo,d,h,mi", CASES)
    def test_nayin_match(self, y, mo, d, h, mi):
        chart = BaziEngine().build_chart(
            birth_datetime=datetime(y, mo, d, h, mi),
            as_of=datetime(2024, 11, 15, 14, 32),
        )
        ref = _lunar_ref(y, mo, d, h, mi)
        for pos, key in (("year", "year"), ("month", "month"), ("day", "day"), ("hour", "time")):
            ours = getattr(chart, f"{pos}_pillar").nayin
            assert ours == ref["nayin"][key], f"{pos} 纳音: {ours} != {ref['nayin'][key]}"


class TestChartReproducibility:
    def test_identical_input_identical_output(self):
        """raw_chart 必须可复现（审计字段 calculated_at 除外）。"""
        engine = BaziEngine()
        a = engine.build_chart(birth_datetime=datetime(2001, 8, 27, 9, 30),
                               as_of=datetime(2024, 11, 15, 14, 32))
        b = engine.build_chart(birth_datetime=datetime(2001, 8, 27, 9, 30),
                               as_of=datetime(2024, 11, 15, 14, 32))
        exclude = {"calculated_at", "computed_at"}
        assert a.model_dump(mode="json", exclude=exclude) == b.model_dump(mode="json", exclude=exclude)
