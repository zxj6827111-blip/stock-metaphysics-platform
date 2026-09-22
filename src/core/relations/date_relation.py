"""确定性日期关系内核。

本模块只消费项目自己的 Schema 与常量，不依赖 lunar-python 或行情对象。
旧版 ``relations_with_external`` 保持兼容；这里提供可序列化的 3×4 关系矩阵。
"""

from __future__ import annotations

from collections.abc import Mapping
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
    WUXING_GENERATES,
    WUXING_OVERCOMES,
)
from src.core.schemas.calendar import CalendarSnapshot, GanZhi
from src.core.schemas.relation import (
    RELATION_TYPES,
    DateRelationFingerprint,
    RelationCell,
    RelationEvent,
    RelationMatrix,
    RelationMatrixRow,
)
from src.engines.bazi.rules import _pair_key, _punishment_hit

POSITIONS: tuple[str, ...] = ("year", "month", "day", "hour")
EXTERNAL_POSITIONS: tuple[str, ...] = ("year", "month", "day")

STEM_HARMONY_KEYS = {
    _pair_key(a, b) for a, b in STEM_FIVE_HARMONY
}
STEM_CLASH_KEYS = {
    _pair_key(a, b) for a, b in (("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"))
}

SUPPORTIVE_RELATIONS = {
    "天干五合", "六合", "三合", "半合", "三会", "天合地合", "天干生", "天干同五行",
}
DISTURBING_RELATIONS = {
    "六冲", "相刑", "三刑", "自刑", "相害", "六破", "天干克", "天克地冲", "反吟",
}


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
        from src.core.constants import ten_god

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
                             source=source, target=target, notes="按 relation-v2：天干冲/克且地支六冲"))


def _triple_events(
    source: GanZhi,
    source_pillar: str,
    natal: Mapping[str, GanZhi],
    cell_events: dict[str, list[RelationEvent]],
) -> None:
    values = {position: pillar.branch for position, pillar in natal.items()}
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


def build_relation_matrix(
    external: Mapping[str, GanZhi],
    natal: Mapping[str, GanZhi],
    *,
    day_master: str,
) -> RelationMatrix:
    """构造严格 3×4 矩阵；单元格允许同时出现多个事件。"""
    rows: list[RelationMatrixRow] = []
    for source_pillar in EXTERNAL_POSITIONS:
        source = external[source_pillar]
        by_target: dict[str, list[RelationEvent]] = {}
        for target_pillar in POSITIONS:
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
        rows.append(RelationMatrixRow(source_pillar=source_pillar, source_ganzhi=source.text, cells=cells))
    return RelationMatrix(rows=rows, relation_rule_version=settings.relation_rule_version)


def _external_map(snapshot: CalendarSnapshot) -> dict[str, GanZhi]:
    return {"year": snapshot.year_ganzhi, "month": snapshot.month_ganzhi, "day": snapshot.day_ganzhi}


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
        targets: list[str] = []
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
    "EXTERNAL_POSITIONS", "POSITIONS", "ExternalPillar", "build_date_relation_fingerprint",
    "build_relation_matrix", "flatten_events", "relation_types",
]
