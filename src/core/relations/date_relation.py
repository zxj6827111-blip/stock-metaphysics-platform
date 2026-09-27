"""确定性日期关系内核（bazi-relation-v3 / relation-matrix-v2）。

本模块只消费项目自己的 Schema 与常量，不依赖 lunar-python 或行情对象。

v3 口径（与 docs/calculation-differences-relation.md 对应）：

* 矩阵 = 流年/流月/流日 × 股票年/月/日（3×3）；股票时柱不参与日期关系研究。
* 3×3 只是择日关系扫描的研究范围，**不是**把股票八字改成三柱；
  喜用神仍来自 BaziEngine 的完整四柱分析。
* 聚合统一走 ``events_for_source_pillar(matrix, "day")``（流日行），
  Date Scan 与 Relation Study 共用，不允许各自实现一套。
* 流日十神由「股票日主 × 流日干」直接计算，不从事件列表 flatten。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.core.config import settings
from src.core.constants import (
    BRANCH_BREAK_OF,
    BRANCH_CLASH_OF,
    BRANCH_HARM_OF,
    BRANCH_HARMONY_OF,
    BRANCH_TRIPLE_HARMONY,
    BRANCH_TRIPLE_MEETING,
    BRANCH_WUXING,
    STEM_FIVE_HARMONY,
    STEM_WUXING,
    TEN_GOD_GROUP,
    WUXING_GENERATES,
    WUXING_OVERCOMES,
    ten_god,
)
from src.core.schemas.calendar import CalendarSnapshot, GanZhi
from src.core.schemas.relation import (
    RELATION_TYPES,
    VERDICT_MATCH,
    VERDICT_MISMATCH,
    VERDICT_UNKNOWN,
    DateRelationFingerprint,
    RelationCell,
    RelationDayVerdict,
    RelationEvent,
    RelationMatrix,
    RelationMatrixRow,
)
from src.engines.bazi.rules import _pair_key, _punishment_hit

#: 外部柱（日期侧）：流年 / 流月 / 流日。
EXTERNAL_POSITIONS: tuple[str, ...] = ("year", "month", "day")
#: 原局柱（股票侧）：年 / 月 / 日。时柱不参与择日关系矩阵。
NATAL_POSITIONS: tuple[str, ...] = ("year", "month", "day")

STEM_HARMONY_KEYS = {
    _pair_key(a, b) for a, b in STEM_FIVE_HARMONY
}
STEM_CLASH_KEYS = {
    _pair_key(a, b) for a, b in (("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"))
}

#: 协同（structuring）：外部对原局的结构性"合/生/同"关系。
#: 「天干受生 / 天干受克」是"我去生/克外部"，不属协同也不属扰动，刻意不计入 S/V。
SUPPORTIVE_RELATIONS = frozenset({
    "天干五合", "六合", "三合", "半合", "三会", "天合地合", "天干生", "天干同五行",
})
DISTURBING_RELATIONS = frozenset({
    "六冲", "相刑", "三刑", "自刑", "相害", "六破", "天干克", "天克地冲", "反吟",
})
COMPOUND_RELATIONS = frozenset({"伏吟", "反吟", "天合地合", "天克地冲"})

#: 结构型分组（v3）：S/V 是描述指标，不引入任何凭观感标定的阈值。
GROUP_SYNERGY = "协同型"
GROUP_DISTURB = "扰动型"
GROUP_MIXED = "混合型"
GROUP_WEAK = "弱关系"
GROUP_UNAVAILABLE = "不可用"


def classify_relation_group(s: int, v: int, u: int) -> str:
    """结构型分组：只看协同/扰动是否存在，U 作为独立结构维度在 UI 展示。

    * S > 0 且 V == 0 → 协同型
    * V > 0 且 S == 0 → 扰动型
    * S > 0 且 V > 0 → 混合型
    * S == 0 且 V == 0 → 弱关系
    """
    if s > 0 and v == 0:
        return GROUP_SYNERGY
    if v > 0 and s == 0:
        return GROUP_DISTURB
    if s > 0 and v > 0:
        return GROUP_MIXED
    return GROUP_WEAK


@dataclass(frozen=True)
class ExternalPillar:
    position: str
    ganzhi: GanZhi


def _event(
    relation_type: str,
    *,
    source_pillar: str,
    target_pillar: str,
    source: GanZhi,
    target: GanZhi,
    element: str = "",
    ten_god: str = "",
    notes: str = "",
) -> RelationEvent:
    return RelationEvent(
        relation_type=relation_type,
        source_scope="date_external",
        source_pillar=source_pillar,
        target_pillar=target_pillar,
        source_stem=source.stem,
        source_branch=source.branch,
        target_stem=target.stem,
        target_branch=target.branch,
        element=element,
        ten_god=ten_god,
        notes=notes,
        rule_version=settings.relation_rule_version,
    )


def _stem_events(source: GanZhi, target: GanZhi, source_pillar: str, target_pillar: str, day_master: str) -> list[RelationEvent]:
    events: list[RelationEvent] = []
    key = _pair_key(source.stem, target.stem)
    if key in STEM_HARMONY_KEYS:
        element = STEM_FIVE_HARMONY.get((source.stem, target.stem)) or STEM_FIVE_HARMONY.get(
            (target.stem, source.stem), ""
        )
        events.append(_event("天干五合", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=element,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"{source.stem}{target.stem} 天干五合"))
    if key in STEM_CLASH_KEYS:
        events.append(_event("天干相冲", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"{source.stem}{target.stem} 天干相冲"))

    source_wx = STEM_WUXING.get(source.stem, "")
    target_wx = STEM_WUXING.get(target.stem, "")
    if source_wx and source_wx == target_wx:
        events.append(_event("天干同五行", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=source_wx,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"天干同属{source_wx}"))
    elif source_wx and target_wx and WUXING_GENERATES.get(source_wx) == target_wx:
        events.append(_event("天干生", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=target_wx,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"{source_wx}生{target_wx}"))
    elif source_wx and target_wx and WUXING_GENERATES.get(target_wx) == source_wx:
        events.append(_event("天干受生", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=source_wx,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"{target_wx}生{source_wx}"))
    if source_wx and target_wx and WUXING_OVERCOMES.get(source_wx) == target_wx:
        events.append(_event("天干克", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=target_wx,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"{source_wx}克{target_wx}"))
    elif source_wx and target_wx and WUXING_OVERCOMES.get(target_wx) == source_wx:
        events.append(_event("天干受克", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=source_wx,
                             ten_god=_safe_ten_god(day_master, source.stem),
                             notes=f"{target_wx}克{source_wx}"))
    return events


def _safe_ten_god(day_master: str, stem: str) -> str:
    try:
        return ten_god(day_master, stem)
    except (KeyError, ValueError):
        return ""


def _branch_events(source: GanZhi, target: GanZhi, source_pillar: str, target_pillar: str, day_master: str) -> list[RelationEvent]:
    events: list[RelationEvent] = []
    a, b = source.branch, target.branch
    if a == b:
        events.append(_event("同支", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=BRANCH_WUXING.get(a, ""),
                             notes=f"外部{a}与原局{b}同支"))
        if a in ("辰", "午", "酉", "亥"):
            events.append(_event("自刑", source_pillar=source_pillar, target_pillar=target_pillar,
                                 source=source, target=target, notes=f"{a}{a}自刑"))
    if BRANCH_HARMONY_OF.get(b) == a:
        events.append(_event("六合", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, element=BRANCH_WUXING.get(a, ""),
                             notes=f"{a}{b}六合"))
    if BRANCH_CLASH_OF.get(b) == a:
        events.append(_event("六冲", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes=f"{a}{b}六冲"))
    if BRANCH_HARM_OF.get(b) == a:
        events.append(_event("相害", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes=f"{a}{b}六害"))
    if BRANCH_BREAK_OF.get(b) == a:
        events.append(_event("六破", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes=f"{a}{b}六破"))
    punishment = _punishment_hit(a, b)
    if punishment and a != b:
        events.append(_event("相刑", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes=f"{a}{b}相刑（{punishment}）"))
    return events


def _compound_for_cell(
    source: GanZhi,
    target: GanZhi,
    source_pillar: str,
    target_pillar: str,
    events: list[RelationEvent],
    day_master: str,
) -> None:
    types = {item.relation_type for item in events}
    if source.stem == target.stem and source.branch == target.branch:
        events.append(_event("伏吟", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target,
                             ten_god=_safe_ten_god(day_master, source.stem), notes="外部柱与原局柱完全相同"))
    if "天干五合" in types and "六合" in types:
        events.append(_event("天合地合", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes="同一外部柱同时形成天干五合与地支六合"))
    if "天干克" in types and "六冲" in types:
        events.append(_event("天克地冲", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes="同一外部柱同时形成天干克与地支六冲"))
    if ({"天干克", "天干相冲"} & types) and "六冲" in types:
        events.append(_event("反吟", source_pillar=source_pillar, target_pillar=target_pillar,
                             source=source, target=target, notes="天干冲/克且地支六冲"))


def _triple_events(
    source: GanZhi,
    source_pillar: str,
    natal: Mapping[str, GanZhi],
    cell_events: dict[str, list[RelationEvent]],
) -> None:
    # 只允许矩阵范围内的柱位参与三合/三会/三刑；传入时柱时同样被排除。
    values = {
        position: pillar.branch
        for position, pillar in natal.items()
        if position in NATAL_POSITIONS
    }
    for combo, element in BRANCH_TRIPLE_HARMONY.items():
        if source.branch not in combo:
            continue
        others = [branch for branch in combo if branch != source.branch]
        matched = [position for position, branch in values.items() if branch in others]
        if len(matched) >= 2:
            matched = matched[:2]
            label = "三合"
            note = f"{''.join(combo)}三合{element}局"
        elif len(matched) == 1:
            label = "半合"
            note = f"{source.branch}{values[matched[0]]}半合{element}局（缺一）"
        else:
            continue
        for target_pillar in matched:
            cell_events[target_pillar].append(_event(
                label, source_pillar=source_pillar, target_pillar=target_pillar,
                source=source, target=natal[target_pillar], element=element, notes=note,
            ))

    for combo, element in BRANCH_TRIPLE_MEETING.items():
        if source.branch not in combo:
            continue
        others = [branch for branch in combo if branch != source.branch]
        matched = [position for position, branch in values.items() if branch in others]
        if len(matched) >= 2:
            note = f"{''.join(combo)}三会{element}方"
            for target_pillar in matched[:2]:
                cell_events[target_pillar].append(_event(
                    "三会", source_pillar=source_pillar, target_pillar=target_pillar,
                    source=source, target=natal[target_pillar], element=element, notes=note,
                ))

    for group in (("寅", "巳", "申"), ("丑", "戌", "未"), ("子", "卯")):
        if source.branch in group:
            matched = [position for position, branch in values.items() if branch in group and branch != source.branch]
            if len(matched) >= 2 and len(group) == 3:
                for target_pillar in matched[:2]:
                    cell_events[target_pillar].append(_event(
                        "三刑", source_pillar=source_pillar, target_pillar=target_pillar,
                        source=source, target=natal[target_pillar], notes=f"{''.join(group)}三刑",
                    ))


def relation_events_for_external_pillar(
    source: GanZhi,
    source_pillar: str,
    natal: Mapping[str, GanZhi],
    *,
    day_master: str,
) -> list[RelationEvent]:
    """计算一个有名字的外部柱与原局年/月/日柱的关系事件。

    该入口复用 Date Scan 的同一组 stem/branch/compound/triple helpers，
    供 Fortune 的大运等非日历外部柱使用；不改变既有 3×3 扫描范围。
    """

    missing = [position for position in NATAL_POSITIONS if position not in natal]
    if missing:
        raise ValueError(f"natal 缺少必要柱位: {missing}（关系目标范围为年/月/日三柱）")
    by_target: dict[str, list[RelationEvent]] = {}
    for target_pillar in NATAL_POSITIONS:
        target = natal[target_pillar]
        events = _stem_events(source, target, source_pillar, target_pillar, day_master)
        events.extend(_branch_events(source, target, source_pillar, target_pillar, day_master))
        _compound_for_cell(source, target, source_pillar, target_pillar, events, day_master)
        by_target[target_pillar] = events
    _triple_events(source, source_pillar, natal, by_target)
    return [event for target_pillar in NATAL_POSITIONS for event in by_target[target_pillar]]


def build_relation_matrix(
    external: Mapping[str, GanZhi],
    natal: Mapping[str, GanZhi],
    *,
    day_master: str,
) -> RelationMatrix:
    """构造严格 3×3 矩阵；同一单元格允许多个事件且全部保留。

    ``natal`` 必须恰好包含 year/month/day 三柱；时柱不属于日期关系矩阵。
    """
    missing = [position for position in NATAL_POSITIONS if position not in natal]
    if missing:
        raise ValueError(f"natal 缺少必要柱位: {missing}（矩阵目标范围为年/月/日三柱）")
    rows: list[RelationMatrixRow] = []
    for source_pillar in EXTERNAL_POSITIONS:
        source = external[source_pillar]
        by_target: dict[str, list[RelationEvent]] = {}
        for target_pillar in NATAL_POSITIONS:
            target = natal[target_pillar]
            events = _stem_events(source, target, source_pillar, target_pillar, day_master)
            events.extend(_branch_events(source, target, source_pillar, target_pillar, day_master))
            _compound_for_cell(source, target, source_pillar, target_pillar, events, day_master)
            by_target[target_pillar] = events
        _triple_events(source, source_pillar, natal, by_target)
        cells = [
            RelationCell(
                source_pillar=source_pillar,
                target_pillar=target_pillar,
                source_ganzhi=source.text,
                target_ganzhi=natal[target_pillar].text,
                events=events,
                relation_types=list(dict.fromkeys(event.relation_type for event in events)),
            )
            for target_pillar, events in by_target.items()
        ]
        rows.append(RelationMatrixRow(
            source_pillar=source_pillar,
            source_ganzhi=source.text,
            cells=cells,
            relation_types=list(dict.fromkeys(
                event.relation_type for cell in cells for event in cell.events
            )),
        ))
    return RelationMatrix(
        rows=rows,
        columns=list(NATAL_POSITIONS),
        schema_version=settings.relation_matrix_schema_version,
        relation_rule_version=settings.relation_rule_version,
    )


def _external_map(snapshot: CalendarSnapshot) -> dict[str, GanZhi]:
    return {"year": snapshot.year_ganzhi, "month": snapshot.month_ganzhi, "day": snapshot.day_ganzhi}


def events_for_source_pillar(matrix: RelationMatrix, source_pillar: str) -> list[RelationEvent]:
    """取出矩阵中某一外部柱行的全部事件。

    Date Scan 与 Relation Study 的所有统计只允许通过本函数读取
    ``source_pillar == "day"``（流日行，即 aggregate_scope=external_day_row）；
    这里的 ``day`` 指**日期侧流日柱**，与股票日柱列无关。
    """
    return [
        event
        for row in matrix.rows
        if row.source_pillar == source_pillar
        for cell in row.cells
        for event in cell.events
    ]


def day_relation_types(matrix: RelationMatrix) -> list[str]:
    """流日行命中的关系类型（去重稳定序）。"""
    return list(dict.fromkeys(event.relation_type for event in events_for_source_pillar(matrix, "day")))


def build_day_stem_verdict(
    *,
    day_master: str,
    day_stem: str,
    yong_shen: Sequence[str] = (),
    xi_shen: Sequence[str] = (),
    ji_shen: Sequence[str] = (),
    chou_shen: Sequence[str] = (),
    xian_shen: Sequence[str] = (),
) -> RelationDayVerdict:
    """流日判定：日主 × 流日干 → 十神；流日干五行 → 喜用忌仇闲角色。

    十神与五行喜忌是两套独立维度，``reason`` 分开陈述。
    原局喜忌资料不足时 ``verdict = 未知`` 且 ``is_yong_or_xi = None``，
    绝不把"未知"写成"不匹配"，也不把"不在喜用"推断为"忌神"。
    """
    verdict = RelationDayVerdict(day_master=day_master, day_stem=day_stem)
    if not day_master or day_stem not in STEM_WUXING:
        verdict.verdict = VERDICT_UNKNOWN
        verdict.reason = "原局日主或流日干支资料不足，无法计算流日十神与五行角色，判定为「未知」。"
        return verdict

    verdict.day_stem_wuxing = STEM_WUXING[day_stem]
    verdict.ten_god = ten_god(day_master, day_stem)
    verdict.ten_god_group = TEN_GOD_GROUP.get(verdict.ten_god, "")

    wx = verdict.day_stem_wuxing
    yong, xi = set(yong_shen), set(xi_shen)
    ji, chou, xian = set(ji_shen), set(chou_shen), set(xian_shen)
    sets_known = bool(yong or xi or ji or chou or xian)
    role_of = (
        ("用神", yong), ("喜神", xi), ("忌神", ji), ("仇神", chou), ("闲神", xian),
    )
    role = next((label for label, values in role_of if wx in values), "未知")
    verdict.wuxing_role = role

    ten_god_sentence = f"流日干{day_stem}属{wx}；相对{day_master}日主的十神为「{verdict.ten_god}」"
    wish = "/".join([*yong_shen, *xi_shen]) or "（空）"
    if not sets_known or role == "未知":
        verdict.verdict = VERDICT_UNKNOWN
        verdict.is_yong_or_xi = None
        verdict.reason = (
            f"{ten_god_sentence}；但原局喜用忌仇闲资料不足或该五行未被归入任何一类，"
            f"五行角色为「未知」，判定为「未知」（未知不等于不匹配）。"
        )
        return verdict
    if role in ("用神", "喜神"):
        verdict.verdict = VERDICT_MATCH
        verdict.is_yong_or_xi = True
        verdict.reason = (
            f"{ten_god_sentence}；该五行（{wx}）在当前原局喜忌判定中属于「{role}」，"
            f"在用神/喜神集合（{wish}）之内，判定为「匹配」。"
        )
        return verdict
    verdict.verdict = VERDICT_MISMATCH
    verdict.is_yong_or_xi = False
    verdict.reason = (
        f"{ten_god_sentence}；该五行（{wx}）在当前原局喜忌判定中属于「{role}」，"
        f"不属于用神/喜神集合（{wish}），判定为「不匹配」。"
    )
    return verdict


def build_date_relation_fingerprint(snapshot: CalendarSnapshot) -> DateRelationFingerprint:
    """从日期快照生成不依赖具体股票的关系模板。"""
    stems = [snapshot.year_ganzhi.stem, snapshot.month_ganzhi.stem, snapshot.day_ganzhi.stem]
    branches = [snapshot.year_ganzhi.branch, snapshot.month_ganzhi.branch, snapshot.day_ganzhi.branch]
    stem_targets: dict[str, list[str]] = {}
    branch_targets: dict[str, list[str]] = {}
    for stem in stems:
        targets: list[str] = []
        for (a, b), _element in STEM_FIVE_HARMONY.items():
            if stem == a:
                targets.append(f"天干五合:{b}")
            elif stem == b:
                targets.append(f"天干五合:{a}")
        for a, b in (("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸")):
            if stem == a:
                targets.append(f"天干相冲:{b}")
            elif stem == b:
                targets.append(f"天干相冲:{a}")
        stem_targets[stem] = list(dict.fromkeys(targets))
    for branch in branches:
        targets = []
        for label, index in (("六合", BRANCH_HARMONY_OF), ("六冲", BRANCH_CLASH_OF), ("相害", BRANCH_HARM_OF), ("六破", BRANCH_BREAK_OF)):
            if index.get(branch):
                targets.append(f"{label}:{index[branch]}")
        branch_targets[branch] = list(dict.fromkeys(targets))

    candidates: dict[str, list[str]] = {"三合": [], "半合": [], "三会": [], "刑": []}
    for branch in branches:
        for combo, element in BRANCH_TRIPLE_HARMONY.items():
            if branch in combo:
                candidates["三合"].append(f"{''.join(combo)}:{element}")
                for other in combo:
                    if other != branch:
                        candidates["半合"].append(f"{branch}{other}半合{element}")
        for combo, element in BRANCH_TRIPLE_MEETING.items():
            if branch in combo:
                candidates["三会"].append(f"{''.join(combo)}:{element}")
    supported = list(RELATION_TYPES)
    return DateRelationFingerprint(
        date=snapshot.solar.date,
        year=snapshot.year_ganzhi.text,
        month=snapshot.month_ganzhi.text,
        day=snapshot.day_ganzhi.text,
        hour=snapshot.hour_ganzhi.text,
        stem_targets=stem_targets,
        branch_targets=branch_targets,
        candidates={key: list(dict.fromkeys(value)) for key, value in candidates.items()},
        supported_relations=supported,
        unavailable_relations=[],
        calendar_engine_version=snapshot.engine_version,
        fingerprint_version=settings.relation_fingerprint_version,
        relation_rule_version=settings.relation_rule_version,
    )


def relation_types(matrix: RelationMatrix) -> list[str]:
    return list(dict.fromkeys(
        event.relation_type
        for row in matrix.rows
        for cell in row.cells
        for event in cell.events
    ))


def flatten_events(matrix: RelationMatrix) -> list[RelationEvent]:
    return [event for row in matrix.rows for cell in row.cells for event in cell.events]


__all__ = [
    "COMPOUND_RELATIONS",
    "DISTURBING_RELATIONS",
    "EXTERNAL_POSITIONS",
    "GROUP_UNAVAILABLE",
    "ExternalPillar",
    "NATAL_POSITIONS",
    "SUPPORTIVE_RELATIONS",
    "build_date_relation_fingerprint",
    "build_day_stem_verdict",
    "build_relation_matrix",
    "classify_relation_group",
    "day_relation_types",
    "events_for_source_pillar",
    "flatten_events",
    "relation_types",
]
