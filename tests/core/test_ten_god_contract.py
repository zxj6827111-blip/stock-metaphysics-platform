"""十神核心合同测试（TG-1）。

覆盖 docs/TEN_GOD_SYSTEM_V1_IMPLEMENTATION_PLAN_20260924.md 的
§2（唯一语义）、§22.1（100 组映射 + 结构性不变量）、§23.2（同一日主同一天干
在任何来源都不得给出不同十神）。

刻意**不依赖** CalendarEngine 与行情/数据库：十神是纯函数层，
它的正确性不应该被历法实现拖动。
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.core.constants import (
    BRANCH_HIDDEN_STEMS,
    EARTHLY_BRANCHES,
    HEAVENLY_STEMS,
    TEN_GOD_GROUP,
    TEN_GODS,
    ten_god,
)
from src.core.relations.ten_god import (
    DAY_MASTER_LABEL,
    catalog_response,
    day_stem_ten_god,
    hidden_stems_with_gods,
    role_and_verdict,
    ten_god_ref,
)
from src.core.schemas.relation import VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN

#: 10 日主 × 10 天干的完整期望表（按 HEAVENLY_STEMS 顺序）。
#: 逐点冻结的理由：常量表一旦被改动（例如五行生克字典写反），
#: 结构性不变量仍然成立，只有逐点期望值能发现"整体错位"。
#: 本表由一份**独立重写**的生克推导实现交叉验证过（零不一致），不是从
#: 被测函数复制出来的期望值。
EXPECTED_MATRIX: dict[str, tuple[str, ...]] = {
    "甲": ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"),
    "乙": ("劫财", "比肩", "伤官", "食神", "正财", "偏财", "正官", "七杀", "正印", "偏印"),
    "丙": ("偏印", "正印", "比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官"),
    "丁": ("正印", "偏印", "劫财", "比肩", "伤官", "食神", "正财", "偏财", "正官", "七杀"),
    "戊": ("七杀", "正官", "偏印", "正印", "比肩", "劫财", "食神", "伤官", "偏财", "正财"),
    "己": ("正官", "七杀", "正印", "偏印", "劫财", "比肩", "伤官", "食神", "正财", "偏财"),
    "庚": ("偏财", "正财", "七杀", "正官", "偏印", "正印", "比肩", "劫财", "食神", "伤官"),
    "辛": ("正财", "偏财", "正官", "七杀", "正印", "偏印", "劫财", "比肩", "伤官", "食神"),
    "壬": ("食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印", "比肩", "劫财"),
    "癸": ("伤官", "食神", "正财", "偏财", "正官", "七杀", "正印", "偏印", "劫财", "比肩"),
}


def _expected(day_master: str, stem: str) -> str:
    return EXPECTED_MATRIX[day_master][HEAVENLY_STEMS.index(stem)]


def test_frozen_expectation_table_is_self_consistent() -> None:
    """先验证期望表本身：10 行 × 10 列，每行必须是十神的一个全排列。

    这条测试防的是"期望表被打字错误污染"——如果表本身错了，
    下面 100 条逐点测试就成了错误的锚。
    """
    assert set(EXPECTED_MATRIX) == set(HEAVENLY_STEMS)
    for row in EXPECTED_MATRIX.values():
        assert len(row) == 10
        assert sorted(row) == sorted(TEN_GODS)


@pytest.mark.parametrize("day_master", HEAVENLY_STEMS)
@pytest.mark.parametrize("stem", HEAVENLY_STEMS)
def test_ten_god_full_100_mapping(day_master: str, stem: str) -> None:
    """100 组逐点映射（合同 §22.1）。"""
    assert ten_god(day_master, stem) == _expected(day_master, stem)


@pytest.mark.parametrize("day_master", HEAVENLY_STEMS)
def test_each_day_master_yields_every_ten_god_exactly_once(day_master: str) -> None:
    """极强的结构性不变量：10 个天干必产生 10 种十神各一次。"""
    produced = [ten_god(day_master, other) for other in HEAVENLY_STEMS]
    assert sorted(produced) == sorted(TEN_GODS)


@pytest.mark.parametrize("day_master", HEAVENLY_STEMS)
def test_same_day_master_same_wuxing_pair_shares_group(day_master: str) -> None:
    """十神组不变量：每个日主下五组各命中两次，且组表覆盖全部十神。"""
    gods = [ten_god(day_master, other) for other in HEAVENLY_STEMS]
    groups = [TEN_GOD_GROUP[god] for god in gods]
    assert sorted(groups) == sorted(["比劫", "食伤", "财星", "官杀", "印星"] * 2)
    assert set(TEN_GOD_GROUP) == set(TEN_GODS)


def test_direction_is_day_master_first_not_stem_first() -> None:
    """方向性防护：十神是"对象相对于日主"，参数写反会得到不同结果。

    这是本项目最容易被写反的一处（合同 §2.1）。``十神(癸, 丙)=正财``，
    反过来 ``十神(丙, 癸)=正官``；若哪天有人按"日主相对对象"实现，
    本测试立刻失败。
    """
    assert ten_god("癸", "丙") == "正财"
    assert ten_god("丙", "癸") == "正官"
    asymmetric = sum(1 for a in HEAVENLY_STEMS for b in HEAVENLY_STEMS if ten_god(a, b) != ten_god(b, a))
    # 只有同五行的干支互换（10 组）对称，其余 80 组互换必错
    assert asymmetric == 80


@pytest.mark.parametrize("day_master", HEAVENLY_STEMS)
def test_same_stem_same_ten_god_across_all_five_sources(day_master: str) -> None:
    """合同 §23.2：同一日主 + 同一天干，不得因来源不同（原局/藏干/流年/流月/流日）
    而返回不同十神。五类十神是同一个 ten_god() 的五种输入，不是五套算法。
    """
    for stem in HEAVENLY_STEMS:
        authoritative = ten_god(day_master, stem)
        as_natal_stem = ten_god_ref(day_master, stem).ten_god
        # 藏干路径：挑一个以该干为藏干的分支来走 hidden_stems_with_gods
        branch = next(b for b, stems in BRANCH_HIDDEN_STEMS.items() if stem in stems)
        as_hidden = next(
            row.ten_god for row in hidden_stems_with_gods(day_master, branch) if row.stem == stem
        )
        as_day_stem = day_stem_ten_god(day_master, stem)
        assert authoritative == as_natal_stem == as_hidden == as_day_stem


def test_day_stem_ten_god_is_the_only_authoritative_entry_point() -> None:
    """统一入口：服务层拿到的十神必须与 constants.ten_god 完全一致。"""
    for day_master in HEAVENLY_STEMS:
        for stem in HEAVENLY_STEMS:
            assert day_stem_ten_god(day_master, stem) == ten_god(day_master, stem)


def test_day_stem_ten_god_returns_empty_for_missing_inputs() -> None:
    """算不出来就空，不用 0 / 猜值冒充。"""
    assert day_stem_ten_god("", "丙") == ""
    assert day_stem_ten_god("癸", "") == ""
    assert day_stem_ten_god("癸", "閃") == ""


def test_ten_god_ref_carries_group_and_wuxing() -> None:
    ref = ten_god_ref("癸", "丙")
    assert (ref.stem, ref.wuxing, ref.ten_god, ref.ten_god_group) == ("丙", "火", "正财", "财星")
    empty = ten_god_ref("", "丙")
    assert empty.ten_god == "" and empty.ten_god_group == ""


def test_day_master_display_label_is_not_a_ten_god_value() -> None:
    """「日主」是盘面标签，不是十神枚举；规范关系仍是比肩（合同 §4）。"""
    assert DAY_MASTER_LABEL == "日主"
    assert DAY_MASTER_LABEL not in TEN_GODS
    assert ten_god("癸", "癸") == "比肩"


@pytest.mark.parametrize("branch,expected", [
    ("申", (("庚", "正印"), ("壬", "劫财"), ("戊", "正官"))),
    ("巳", (("丙", "正财"), ("庚", "正印"), ("戊", "正官"))),
    ("未", (("己", "七杀"), ("丁", "偏财"), ("乙", "食神"))),
])
def test_hidden_stems_ten_gods_for_day_master_gui(branch: str, expected: tuple) -> None:
    rows = hidden_stems_with_gods("癸", branch)
    assert [(row.stem, row.ten_god) for row in rows] == list(expected)
    assert [row.rank for row in rows] == ["本气", "中气", "余气"][: len(rows)]


def test_hidden_stems_cover_every_branch_and_weights_sum_to_one() -> None:
    for branch in EARTHLY_BRANCHES:
        rows = hidden_stems_with_gods("甲", branch)
        assert tuple(row.stem for row in rows) == BRANCH_HIDDEN_STEMS[branch]
        assert rows[0].rank == "本气"
        assert round(sum(row.weight or 0 for row in rows), 6) == 1.0
        assert all(row.ten_god in TEN_GODS for row in rows)


def test_catalog_is_the_single_enum_source_and_matches_constants() -> None:
    catalog = catalog_response()
    assert [item.name for item in catalog.ten_gods] == list(TEN_GODS)
    assert {item.name: item.group for item in catalog.ten_gods} == TEN_GOD_GROUP
    assert [g.name for g in catalog.ten_god_groups] == ["比劫", "食伤", "财星", "官杀", "印星"]
    # 每个组必须恰好拆出两个十神，且五组合起来不重不漏地覆盖十神全集
    members = [m for group in catalog.ten_god_groups for m in group.members]
    assert sorted(members) == sorted(TEN_GODS)
    assert catalog.wuxing_roles == ["用神", "喜神", "忌神", "仇神", "闲神", "未知"]
    assert catalog.verdicts == [VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN]
    assert catalog.hidden_stems_by_branch["丑"] == ["己", "癸", "辛"]


def test_catalog_declares_its_own_version_and_direction() -> None:
    catalog = catalog_response()
    assert catalog.ten_god_rule_version == settings.ten_god_rule_version == "ten-god-v1"
    assert catalog.day_master_source == "stock_natal_day_stem"
    assert catalog.other_stem_source == "temporal_or_natal_stem"
    # 关系矩阵不得成为十神真值来源，必须由目录显式声明（合同 §5 / §17）
    assert catalog.relation_matrix_is_not_ten_god is True
    assert "3×3" in catalog.relation_matrix_note or "矩阵" in catalog.relation_matrix_note


def test_role_and_verdict_are_independent_of_ten_god() -> None:
    """同一个十神（丙→正财）可以匹配也可以不匹配，取决于喜用集合。"""
    assert role_and_verdict("火", yong_shen=["火"]) == ("用神", VERDICT_MATCH, True)
    assert role_and_verdict("火", xi_shen=["火"]) == ("喜神", VERDICT_MATCH, True)
    assert role_and_verdict("火", ji_shen=["火"]) == ("忌神", VERDICT_MISMATCH, False)
    assert role_and_verdict("火", chou_shen=["火"]) == ("仇神", VERDICT_MISMATCH, False)
    assert role_and_verdict("火", xian_shen=["火"]) == ("闲神", VERDICT_MISMATCH, False)


def test_role_and_verdict_unknown_is_not_mismatch() -> None:
    """未知必须保持未知（AGENTS.md §2.4 不可用语义）。"""
    assert role_and_verdict("火") == ("未知", VERDICT_UNKNOWN, None)
    assert role_and_verdict("火", yong_shen=["水"]) == ("未知", VERDICT_UNKNOWN, None)
    assert role_and_verdict("", yong_shen=["火"]) == ("未知", VERDICT_UNKNOWN, None)
