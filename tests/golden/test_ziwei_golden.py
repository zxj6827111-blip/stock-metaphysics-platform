"""紫微 Golden Cases（Phase 2A）。

分两层
------
**A. 结构性不变量（永远运行）** —— 由 `tests/fixtures/ziwei/` 的真实 iztro 快照驱动。
   结构不变量比逐点期望值更强：它能捕获"整体错位一格""宫名循环错位"
   "四化少一个"这类系统性错误。

**B. 实时扫描（`@pytest.mark.ziwei_live`）** —— 对**不同年份 / 月份 / 日期 / 时辰 /
   两个 variant** 现场排盘，验证不变量在任意输入下都成立。
   iztro 升级后必须先跑这一层（`make test-ziwei-golden`）。

注意：本文件**不是**逐点期望值表。紫微的逐点结果由 `tests/fixtures/ziwei/*.json`
冻结（那是 Adapter 契约层）；这里验证的是"无论输入怎么变都成立"的规律。
"""

from __future__ import annotations

import json
from datetime import datetime
from itertools import combinations
from pathlib import Path

import pytest

from src.core.schemas.common import VariantMode
from src.core.schemas.ziwei import ZiweiChart
from src.engines.base import EngineContext
from src.engines.ziwei import constants as zc
from src.engines.ziwei.ziwei_engine import TIME_INDEX_RANGES, ZiweiEngine

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ziwei"
MANIFEST = json.loads((FIXTURE_DIR / "_manifest.json").read_text(encoding="utf-8"))
CASE_NAMES = [c["name"] for c in MANIFEST["cases"]]

pytestmark = pytest.mark.golden


def load_chart(name: str) -> ZiweiChart:
    return ZiweiChart.model_validate(
        json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def _live_available() -> bool:
    from src.engines.ziwei.transport import SubprocessZiweiTransport

    return SubprocessZiweiTransport().available()


LIVE = _live_available()
live_only = pytest.mark.skipif(
    not LIVE, reason="本机缺少 node 或 services/ziwei-service 未构建（make ziwei-build）"
)


# ---------------------------------------------------------------------------
# A. 结构性不变量（快照驱动）
# ---------------------------------------------------------------------------


class TestStructuralInvariants:
    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_palace_ring_is_fixed(self, name):
        """十二宫地支环固定：index 0..11 对应 寅..丑，且每宫恰好一次。"""
        chart = load_chart(name)
        branches = [p.earthly_branch for p in chart.palaces]
        assert branches == list(zc.ZIWEI_PALACE_BRANCHES)
        assert len(set(branches)) == 12

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_soul_palace_always_opposite_migration(self, name):
        """命宫与迁移宫恒相对（相差 6 宫）。"""
        chart = load_chart(name)
        soul = chart.soul_palace_index
        migration = next(p.index for p in chart.palaces if p.name == "迁移")
        assert abs(soul - migration) in (6, 6), "命宫与迁移宫必须相差 6 宫"
        assert (soul + 6) % 12 == migration

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_wealth_and_career_offsets(self, name):
        """财帛位 = 命宫 +8，官禄位 = 命宫 +4（三方四正结构）。"""
        chart = load_chart(name)
        soul = chart.soul_palace_index
        by_name = {p.name: p.index for p in chart.palaces}
        assert by_name["财帛"] == (soul + 8) % 12
        assert by_name["官禄"] == (soul + 4) % 12
        assert by_name["迁移"] == (soul + 6) % 12

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_palace_stems_follow_five_tiger_rule(self, name):
        """十二宫天干由五虎遁自寅宫起顺行。

        结构性质：``stems[i] == stems[0] + i (mod 10)``，对 **全部 12 宫**成立。
        （注意：宫位有 12 个而天干只有 10 个，所以绕回寅宫时**不是** +1 ——
        这正是"紫微 12 宫与 10 天干不同步"的固有性质，不能用简单的
        "相邻差恒为 1（含环回）"来断言。）
        """
        from src.core.constants import STEM_INDEX

        chart = load_chart(name)
        stems = [p.heavenly_stem for p in chart.palaces]
        assert all(s in STEM_INDEX for s in stems), f"宫干异常：{stems}"
        base = STEM_INDEX[stems[0]]
        for i, stem in enumerate(stems):
            assert STEM_INDEX[stem] == (base + i) % 10, (
                f"第 {i} 宫天干 {stem} 不等于 {stems[0]}+{i}（五虎遁顺行结构被破坏）"
            )

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_exactly_one_soul_and_body_palace(self, name):
        chart = load_chart(name)
        assert sum(1 for p in chart.palaces if p.name == "命宫") == 1
        assert sum(1 for p in chart.palaces if p.is_body_palace) == 1
        assert chart.soul_palace_index == next(p.index for p in chart.palaces if p.name == "命宫")

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_mutagen_stars_are_distinct(self, name):
        """生年四化必须落在**四个不同的星曜**上，且各占禄/权/科/忌。"""
        chart = load_chart(name)
        stars = [m.star for m in chart.natal_mutagens]
        assert len(stars) == 4
        assert len(set(stars)) == 4, f"四化星重复：{stars}"
        assert [m.mutagen for m in chart.natal_mutagens] == list(zc.MUTAGEN_ORDER)

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_mutagen_placement_matches_palace_stars(self, name):
        """四化记录必须与宫位里的星曜标记一致（防止两处数据不同步）。"""
        chart = load_chart(name)
        for m in chart.natal_mutagens:
            palace = chart.palaces[m.palace_index]
            hits = [s for s in palace.all_stars() if s.mutagen == m.mutagen]
            assert [h.name for h in hits] == [m.star], (
                f"{m.mutagen} 记录为 {m.star}@{m.palace_name}，"
                f"但该宫实际标记为 {[h.name for h in hits]}"
            )

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_decadal_ranges_are_contiguous_and_non_overlapping(self, name):
        """大限必须构成一段连续、不重叠的年龄覆盖（从起运岁到起运+119）。"""
        chart = load_chart(name)
        ranges = sorted((list(r.range) for r in chart.decadals if r.range), key=lambda x: x[0])
        assert len(ranges) == 12, f"大限数量应为 12，实际 {len(ranges)}"
        for (_s1, e1), (s2, _e2) in zip(ranges, ranges[1:], strict=False):
            assert e1 + 1 == s2, f"大限区间不连续：{_s1}-{e1} 与 {s2}"
        assert ranges[0][1] - ranges[0][0] == 9, "每段大限应为 10 年"

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_decadal_start_age_matches_five_elements_class(self, name):
        """首限起运岁数 = 五行局数（水二/木三/金四/土五/火六）。"""
        chart = load_chart(name)
        ju, _wx = zc.FIVE_ELEMENTS_CLASS[chart.five_elements_class]
        first = min((r.range[0] for r in chart.decadals if r.range), default=None)
        assert first == ju, f"{chart.five_elements_class} 应从 {ju} 岁起运，实际 {first}"

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_small_limit_ages_are_multiple_of_12_offset(self, name):
        """小限年龄在十二宫中相差 12（同一宫位每隔 12 年重复一次）。"""
        chart = load_chart(name)
        for p in chart.palaces:
            if len(p.ages) >= 2:
                assert p.ages[1] - p.ages[0] == 12

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_horoscope_palace_names_are_permutations(self, name):
        for scope in ("yearly", "monthly", "daily", "hourly"):
            sec = getattr(chart_h := load_chart(name).horoscope, scope)
            assert sorted(sec.palace_names) == sorted(zc.ZIWEI_PALACE_NAMES), (
                f"{scope} 的十二宫名不是全集的排列"
            )
            assert sec.palace_names.index("命宫") == sec.index
            _ = chart_h

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_stars_never_appear_in_two_palaces(self, name):
        """十四主星不得重复出现在两个宫位（安星必须互斥）。"""
        chart = load_chart(name)
        seen: dict[str, int] = {}
        for p in chart.palaces:
            for s in p.major_stars:
                assert s.name not in seen, (
                    f"主星 {s.name} 同时出现在第 {seen[s.name]} 宫与第 {p.index} 宫"
                )
                seen[s.name] = p.index

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_major_star_count_is_14_minus_empty_palaces(self, name):
        """14 主星分布：紫微系 6 + 天府系 8，空宫（无主星）也计入位置。"""
        chart = load_chart(name)
        total = sum(len(p.major_stars) for p in chart.palaces)
        assert total == 14, f"主星总数应为 14，实际 {total}"

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_palace_branches_map_to_expected_time_index_of_birth(self, name):
        """time_index 与时辰名必须自洽（防止小时映射错位）。"""
        case = next(c for c in MANIFEST["cases"] if c["name"] == name)
        chart = load_chart(name)
        start, _end = TIME_INDEX_RANGES[case["time_index"]]
        assert chart.time_index == case["time_index"]
        assert chart.time_name, "时辰名不能为空"
        assert chart.time_range, "时辰区间不能为空"
        assert str(start) in chart.time_range or chart.time_range.startswith(
            f"{start:02d}"
        ), f"time_index={case['time_index']} 与 {chart.time_range} 不一致"


# ---------------------------------------------------------------------------
# B. 实时扫描（多输入不变量）
# ---------------------------------------------------------------------------

#: 覆盖不同年 / 月 / 日 / 时辰 / variant 的组合
SCAN_INPUTS: list[tuple[str, int, str]] = [
    ("1990-01-27", 0, "variant_forward"),
    ("1995-06-15", 3, "variant_reverse"),
    ("2000-02-29", 6, "variant_forward"),   # 闰日
    ("2005-11-03", 9, "variant_reverse"),
    ("2010-08-08", 12, "variant_forward"),  # 晚子时
    ("2015-03-21", 1, "variant_reverse"),
    ("2019-12-31", 11, "variant_forward"),
    ("2023-05-05", 7, "variant_reverse"),
    ("2024-02-04", 2, "variant_forward"),   # 立春当日
    ("2026-09-18", 5, "variant_reverse"),
]


@live_only
class TestLiveStructuralScan:
    """对多组输入现场排盘，验证不变量在任意输入下成立。"""

    @staticmethod
    def _chart(solar: str, ti: int, variant: str) -> ZiweiChart:
        y, m, d = (int(x) for x in solar.split("-"))
        birth = datetime(y, m, d, TIME_INDEX_RANGES[ti][0], 30)
        engine = ZiweiEngine()
        return engine.calculate_chart(
            EngineContext(stock_code="SCAN", as_of=datetime(2024, 11, 15, 13, 30)),
            birth_datetime=birth,
            as_of=datetime(2024, 11, 15, 13, 30),
            variant_mode=VariantMode.FORWARD if variant == "variant_forward" else VariantMode.REVERSE,
        )

    @pytest.mark.ziwei_live
    @pytest.mark.parametrize("solar,ti,variant", SCAN_INPUTS)
    def test_all_invariants_hold(self, solar, ti, variant):
        chart = self._chart(solar, ti, variant)

        # 1. 宫环
        assert [p.earthly_branch for p in chart.palaces] == list(zc.ZIWEI_PALACE_BRANCHES)
        assert sorted(p.name for p in chart.palaces) == sorted(zc.ZIWEI_PALACE_NAMES)

        # 2. 主星互斥且共 14
        assert sum(len(p.major_stars) for p in chart.palaces) == 14

        # 3. 四化
        assert [m.mutagen for m in chart.natal_mutagens] == list(zc.MUTAGEN_ORDER)
        assert len({m.star for m in chart.natal_mutagens}) == 4

        # 4. 大限连续
        ranges = sorted((list(r.range) for r in chart.decadals if r.range), key=lambda x: x[0])
        assert len(ranges) == 12
        for (_s1, e1), (s2, _e2) in zip(ranges, ranges[1:], strict=False):
            assert e1 + 1 == s2
        assert ranges[0][0] == zc.FIVE_ELEMENTS_CLASS[chart.five_elements_class][0]

        # 5. 宫干：五虎遁自寅宫顺行（全部 12 宫，注意天干只有 10 个）
        from src.core.constants import STEM_INDEX

        stems = [p.heavenly_stem for p in chart.palaces]
        base = STEM_INDEX[stems[0]]
        assert all(STEM_INDEX[s] == (base + i) % 10 for i, s in enumerate(stems))

        # 6. 三方四正与本地规则一致
        for p in chart.palaces:
            assert p.trine_indices == zc.trine_indices(p.index)

        # 7. 运限层完整
        for scope in ("yearly", "monthly", "daily"):
            sec = getattr(chart.horoscope, scope)
            assert sorted(sec.palace_names) == sorted(zc.ZIWEI_PALACE_NAMES)

    @pytest.mark.ziwei_live
    def test_no_two_charts_are_identical_across_dates(self):
        """不同出生时刻必须产出不同盘面（防止参数被静默忽略）。"""
        charts = [
            self._chart(solar, ti, variant)
            for solar, ti, variant in SCAN_INPUTS[:6]
        ]
        fingerprints = {
            c.chinese_date + "|" + "".join(p.name + p.earthly_branch for p in c.palaces)
            + "|" + "".join(s.name for p in c.palaces for s in p.major_stars)
            for c in charts
        }
        assert len(fingerprints) == len(charts), "存在完全相同的紫微盘面（输入可能被忽略）"

    @pytest.mark.ziwei_live
    def test_forward_reverse_pairs_share_everything_except_direction(self):
        """对同一出生时刻，两个 variant 的差异必须**仅限于**方向相关字段。"""
        forward = self._chart("2001-08-27", 5, "variant_forward")
        reverse = self._chart("2001-08-27", 5, "variant_reverse")
        for a, b in zip(forward.palaces, reverse.palaces, strict=True):
            assert a.name == b.name
            assert a.earthly_branch == b.earthly_branch
            assert a.heavenly_stem == b.heavenly_stem
            assert a.major_stars == b.major_stars
            assert a.minor_stars == b.minor_stars
            assert a.trine_indices == b.trine_indices
        assert forward.natal_mutagens == reverse.natal_mutagens
        assert [p.decadal_range for p in forward.palaces] != \
               [p.decadal_range for p in reverse.palaces]

    @pytest.mark.ziwei_live
    def test_direction_of_decadals_is_consistent_with_variant(self):
        """顺行 variant 的大限年龄必须沿宫位索引递增；逆行必须递减。

        这条不变量直接锁定 ADR-0010 的实现语义：variant 表达的是**方向**，
        而不是"姓什么性别"。
        """
        fwd = self._chart("2001-08-27", 5, "variant_forward")
        rev = self._chart("2001-08-27", 5, "variant_reverse")

        def direction(chart: ZiweiChart) -> int:
            """命宫恒为第一个大限；看**第二个**大限落在 +1 还是 −1 邻居宫。

            返回 +1 表示顺行（沿宫位索引递增），−1 表示逆行。
            """
            soul = chart.soul_palace_index
            first_start = chart.palaces[soul].decadal_range[0]
            assert first_start == min(
                p.decadal_range[0] for p in chart.palaces
            ), "命宫必须持有第一个大限（起运）"
            for delta in (1, -1):
                nb = chart.palaces[(soul + delta) % 12]
                if nb.decadal_range[0] == first_start + 10:
                    return delta
            raise AssertionError("命宫的下一个大限既不在 +1 也不在 −1 邻居宫")

        assert direction(fwd) == 1, "forward 必须顺行（下一个大限在 命宫+1）"
        assert direction(rev) == -1, "reverse 必须逆行（下一个大限在 命宫−1）"

    @pytest.mark.ziwei_live
    def test_birth_year_stem_polarity_selects_variant_gender(self):
        """variant 借用的性别参数必须与年干阴阳一致（可审计、可复算）。"""
        from src.core.constants import STEM_YANG

        # 戊戌年（阳）与 辛巳年（阴）各取一例
        yang = self._chart("2018-06-11", 5, "variant_forward")
        yin = self._chart("2001-08-27", 5, "variant_forward")
        yang_stem = yang.chinese_date.split()[0][0]
        yin_stem = yin.chinese_date.split()[0][0]
        assert STEM_YANG[yang_stem] is True
        assert STEM_YANG[yin_stem] is False
        assert yang.gender_parameter == "男"   # 阳年顺行 → 男
        assert yin.gender_parameter == "女"    # 阴年顺行 → 女


class TestSnapshotCoverage:
    """快照集合本身必须覆盖任务要求（不同年/月/日/时辰/两个 variant）。"""

    def test_covers_multiple_years(self):
        years = {c["solar_date"][:4] for c in MANIFEST["cases"]}
        assert len(years) >= 5, f"快照年份覆盖不足：{years}"

    def test_covers_multiple_time_indices(self):
        tis = {c["time_index"] for c in MANIFEST["cases"]}
        assert len(tis) >= 4, f"时辰覆盖不足：{tis}"
        assert 12 in tis, "必须覆盖晚子时（timeIndex=12，已知流派差异点）"

    def test_covers_both_variants(self):
        variants = {c["variant_mode"] for c in MANIFEST["cases"]}
        assert variants == {"variant_forward", "variant_reverse"}

    def test_same_birth_two_variants_present(self):
        """同一出生时刻的 forward/reverse 必须成对存在，才能做 variant 对比。"""
        by_birth: dict[str, set[str]] = {}
        for c in MANIFEST["cases"]:
            by_birth.setdefault(c["solar_date"], set()).add(c["variant_mode"])
        pairs = [k for k, v in by_birth.items() if len(v) == 2]
        assert pairs, "缺少同一出生时刻的 forward/reverse 成对快照"

    def test_manifest_matches_files(self):
        for name in CASE_NAMES:
            assert (FIXTURE_DIR / f"{name}.json").is_file()

    def test_all_cases_have_distinct_soul_palace_or_five_elements(self):
        """快照不能全是同一种盘（否则覆盖是假的）。"""
        sigs = {(c["soul_palace_index"], c["five_elements_class"]) for c in MANIFEST["cases"]}
        assert len(sigs) >= 4, f"盘面特征重复度过高：{sigs}"

    def test_pairwise_differences_exist(self):
        charts = [load_chart(n) for n in CASE_NAMES]
        for a, b in combinations(charts, 2):
            assert a.chinese_date != b.chinese_date or a.variant_mode != b.variant_mode
