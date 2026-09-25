"""十神系统 V1 的纯计算层：把「固定日主 × 外部天干」映射成可展示的十神结构。

这里**没有第二套十神算法**：所有十神都取自
``src.core.constants.ten_god(day_master, other_stem)``（合同 §2.2）。
本模块只负责把它包装成 Schema、补上十神组/五行/藏干，并输出目录常量。

与关系矩阵的分工（合同 §5 / §17）：
``src/core/relations/date_relation.py`` 的 3×3 矩阵负责冲合刑害破生克伏吟反吟；
矩阵单元格里出现的 ``ten_god`` 只是"该天干对日主的关系标签"，
**不得**被聚合成"流日十神"。权威流日十神只有 :func:`day_stem_ten_god`。
"""

from __future__ import annotations

from collections.abc import Sequence

from src.core.config import settings
from src.core.constants import (
    BRANCH_HIDDEN_STEMS,
    BRANCH_WUXING,
    EARTHLY_BRANCHES,
    STEM_WUXING,
    TEN_GOD_GROUP,
    TEN_GODS,
    hidden_stem_weight,
    ten_god,
)
from src.core.schemas.relation import (
    VERDICT_MATCH,
    VERDICT_MISMATCH,
    VERDICT_UNKNOWN,
    WUXING_ROLES,
)
from src.core.schemas.ten_god import (
    DAY_MASTER_SOURCE,
    OTHER_STEM_SOURCE,
    TEN_GOD_GROUPS,
    TenGodCatalogItem,
    TenGodCatalogResponse,
    TenGodGroupItem,
    TenGodHiddenStem,
    TenGodRef,
)

#: 日柱天干的盘面显示值。规范关系是「比肩」，显示是「日主」，两者不合并。
DAY_MASTER_LABEL = "日主"


def ten_god_ref(day_master: str, stem: str) -> TenGodRef:
    """一个天干相对固定日主的十神；日主为空或天干非法时返回不可用（不猜）。"""
    if not day_master or day_master not in STEM_WUXING or stem not in STEM_WUXING:
        return TenGodRef(stem=stem, wuxing=STEM_WUXING.get(stem, ""), ten_god="", ten_god_group="")
    god = ten_god(day_master, stem)
    return TenGodRef(
        stem=stem,
        wuxing=STEM_WUXING[stem],
        ten_god=god,
        ten_god_group=TEN_GOD_GROUP.get(god, ""),
    )


def day_stem_ten_god(day_master: str, day_stem: str) -> str:
    """权威流日十神：``ten_god(股票日主, 流日干)``。

    这是合同 §17 唯一允许的十神真值入口；关系矩阵的事件列表不是来源。
    """
    if not day_master or day_stem not in STEM_WUXING:
        return ""
    return ten_god(day_master, day_stem)


def hidden_stems_with_gods(day_master: str, branch: str) -> list[TenGodHiddenStem]:
    """地支藏干及其相对固定日主的十神（顺序 = 本气/中气/余气）。"""
    stems = BRANCH_HIDDEN_STEMS.get(branch, ())
    total = len(stems)
    ranks = ("本气", "中气", "余气")
    out: list[TenGodHiddenStem] = []
    for idx, stem in enumerate(stems):
        ref = ten_god_ref(day_master, stem)
        out.append(TenGodHiddenStem(
            stem=stem,
            wuxing=ref.wuxing or STEM_WUXING.get(stem, ""),
            ten_god=ref.ten_god,
            ten_god_group=ref.ten_god_group,
            rank=ranks[idx] if idx < len(ranks) else "余气",
            weight=round(hidden_stem_weight(idx, total), 3),
        ))
    return out


def branch_wuxing(branch: str) -> str:
    return BRANCH_WUXING.get(branch, "")


def count_ten_gods(refs: Sequence[TenGodRef]) -> tuple[dict[str, int], dict[str, int]]:
    """十神计数与十神组计数（调用方决定哪些干计入，日主由上层排除）。"""
    counts: dict[str, int] = {}
    groups: dict[str, int] = {}
    for ref in refs:
        if not ref.ten_god:
            continue
        counts[ref.ten_god] = counts.get(ref.ten_god, 0) + 1
        group = TEN_GOD_GROUP.get(ref.ten_god, "其他")
        groups[group] = groups.get(group, 0) + 1
    return counts, groups


def role_and_verdict(
    wuxing: str,
    yong_shen: Sequence[str] = (),
    xi_shen: Sequence[str] = (),
    ji_shen: Sequence[str] = (),
    chou_shen: Sequence[str] = (),
    xian_shen: Sequence[str] = (),
) -> tuple[str, str, bool | None]:
    """五行 → (角色, 匹配状态, 是否喜用)。

    与 ``build_day_stem_verdict`` 同一条判定顺序（用/喜/忌/仇/闲），
    但**只返回维度值、不返回十神**，供流年/流月段复用；
    流日行仍直接调用 ``build_day_stem_verdict``，不在此处重复实现十神。
    资料不足时角色「未知」、状态「未知」，不冒充「不匹配」。
    """
    sets_known = bool(yong_shen or xi_shen or ji_shen or chou_shen or xian_shen)
    if not wuxing or not sets_known:
        return "未知", VERDICT_UNKNOWN, None
    for label, values in (
        ("用神", yong_shen), ("喜神", xi_shen), ("忌神", ji_shen),
        ("仇神", chou_shen), ("闲神", xian_shen),
    ):
        if wuxing in values:
            if label in ("用神", "喜神"):
                return label, VERDICT_MATCH, True
            return label, VERDICT_MISMATCH, False
    return "未知", VERDICT_UNKNOWN, None


def catalog_response() -> TenGodCatalogResponse:
    """十神目录：前端所有十神相关下拉项的唯一来源（合同 §10.1）。"""
    return TenGodCatalogResponse(
        ten_god_rule_version=settings.ten_god_rule_version,
        ten_gods=[TenGodCatalogItem(name=god, group=TEN_GOD_GROUP.get(god, "")) for god in TEN_GODS],
        ten_god_groups=[
            TenGodGroupItem(
                name=group,
                members=[god for god in TEN_GODS if TEN_GOD_GROUP.get(god) == group],
            )
            for group in TEN_GOD_GROUPS
        ],
        wuxing_roles=list(WUXING_ROLES),
        verdicts=[VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN],
        day_master_source=DAY_MASTER_SOURCE,
        other_stem_source=OTHER_STEM_SOURCE,
        hidden_stems_by_branch={b: list(BRANCH_HIDDEN_STEMS[b]) for b in EARTHLY_BRANCHES},
        calendar_engine_version=settings.calendar_engine_version,
    )


__all__ = [
    "DAY_MASTER_LABEL",
    "branch_wuxing",
    "catalog_response",
    "count_ten_gods",
    "day_stem_ten_god",
    "hidden_stems_with_gods",
    "role_and_verdict",
    "ten_god_ref",
]
