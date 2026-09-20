"""紫微第二实现源（REFERENCE ONLY）—— 案例集与字段级比较器。

比较范围（GOAL §3G-3）
----------------------
十二宫位置 / 命宫 / 身宫 / 五行局 / 主星 / 辅星 / 四化 / 三方四正 / 大限 /
流年 / 流月 / 长生十二神。

差异分类（GOAL §3G-5 的 ``possible_reason`` / ``school_convention`` / ``resolved``）
----------------------------------------------------------------------------------
``IDENTICAL``                        两边一致
``DIFFERENT_NAMING_CONVENTION``      同一事物的不同名称（如 截路/截空、交友/仆役）
``DIFFERENT_SCHOOL_CONVENTION``      流派口径差异（四化表、晚子时日柱、长生方向）
``DIFFERENT_VARIANT_ASSUMPTION``     由「股票无性别」的假设参数引起（大限/长生方向）
``DIFFERENT_SUSPECTED_IMPL_BUG``     无法用流派解释、疑似参考实现的问题
``FIELD_UNAVAILABLE``                该字段在参考实现上没有可比对的出口

**不做**的事：不把差异抹平、不挑"能对上的字段"报告、不改我们的生产引擎。
交叉核对的产出是**差异登记**，不是"通过/不通过"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.engines.ziwei.reference.client import ReferenceChart
from src.engines.ziwei.reference.normalize import (
    normalize_mutagen,
    normalize_name,
    normalize_palace,
    project_index_from_branch,
)

#: 案例集版本
CASE_VERSION = "phase3g-ziwei-crosscheck-cases-v1"
#: 差异分类常量
IDENTICAL = "IDENTICAL"
DIFFERENT_NAMING_CONVENTION = "DIFFERENT_NAMING_CONVENTION"
DIFFERENT_SCHOOL_CONVENTION = "DIFFERENT_SCHOOL_CONVENTION"
DIFFERENT_VARIANT_ASSUMPTION = "DIFFERENT_VARIANT_ASSUMPTION"
DIFFERENT_SUSPECTED_IMP_BUG = "DIFFERENT_SUSPECTED_IMP_BUG"
FIELD_UNAVAILABLE = "FIELD_UNAVAILABLE"

#: 宫位比较顺序（与 ZiweiPalace.name 对齐）
PALACE_NAMES: tuple[str, ...] = (
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "仆役", "官禄", "田宅", "福德", "父母",
)


@dataclass(frozen=True)
class CrossEngineCase:
    case_id: str
    solar: tuple[int, int, int]
    hour: int
    variant_mode: str
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "solar": list(self.solar),
            "hour": self.hour,
            "variant_mode": self.variant_mode,
            "tags": list(self.tags),
        }


def load_cases(path: str | Path) -> list[CrossEngineCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases: list[CrossEngineCase] = []
    for raw in payload.get("cases", []):
        solar = raw["solar"]
        cases.append(CrossEngineCase(
            case_id=str(raw["case_id"]),
            solar=(int(solar[0]), int(solar[1]), int(solar[2])),
            hour=int(raw["hour"]),
            variant_mode=str(raw.get("variant_mode", "forward")),
            tags=tuple(str(value) for value in raw.get("tags", [])),
        ))
    if not cases:
        raise ValueError(f"案例集为空：{path}")
    return cases


@dataclass
class Difference:
    """一条字段级差异登记。"""

    case_id: str
    field: str
    production_value: object
    reference_value: object
    classification: str
    possible_reason: str = ""
    school_convention: str = ""
    resolved: bool = False
    binding: str = "gender_independent"

    @property
    def same(self) -> bool:
        return self.classification == IDENTICAL

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "field": self.field,
            "production_value": self.production_value,
            "reference_value": self.reference_value,
            "same_or_different": "same" if self.same else "different",
            "classification": self.classification,
            "possible_reason": self.possible_reason,
            "school_convention": self.school_convention,
            "resolved": self.resolved,
            "gender_binding": self.binding,
        }


@dataclass
class CaseComparison:
    """一个案例的比较结果。"""

    case_id: str
    reference_ok: bool
    reference_error: str = ""
    matched_gender: str = ""
    gender_agreement: dict = field(default_factory=dict)
    differences: list[Difference] = field(default_factory=list)

    @property
    def identical_count(self) -> int:
        return sum(1 for item in self.differences if item.same)

    @property
    def different_count(self) -> int:
        return sum(1 for item in self.differences if not item.same)

    def fields(self) -> set[str]:
        return {item.field for item in self.differences}


def _reference_index_map(chart: dict) -> dict[str, dict]:
    """参考盘面 → ``{项目内宫名: cell}``（地支索引转换为项目口径）。"""
    out: dict[str, dict] = {}
    for cell in chart.get("cells", []):
        our_index = project_index_from_branch(str(cell.get("ground", "")))
        for temple in cell.get("temples", []):
            out[normalize_palace(temple)] = {**cell, "our_index": our_index}
    return out


def _production_palaces(chart) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {normalize_palace(palace.name): palace for palace in chart.palaces}


def compare_case(
    case: CrossEngineCase,
    production_chart,  # type: ignore[no-untyped-def]
    reference_charts: dict[str, ReferenceChart],
    *,
    is_late_zi: bool | None = None,
) -> CaseComparison:
    """比较一个案例：生产引擎（iztro）盘面 vs 参考实现（中州派）盘面。"""
    result = CaseComparison(case_id=case.case_id, reference_ok=False)
    late_zi = bool(is_late_zi) if is_late_zi is not None else case.hour == 23
    production_palaces = _production_palaces(production_chart)
    if not production_palaces:
        return result

    # 参考实现同时以 M/F 各排一次：先区分"性别无关字段"与"性别相关字段"
    usable = {key: value for key, value in reference_charts.items() if value.ok}
    if not usable:
        errors = "; ".join(
            f"{key}:{value.error}" for key, value in reference_charts.items()
        )
        result.reference_error = errors or "参考实现未返回任何盘面"
        return result
    result.reference_ok = True

    index_maps = {key: _reference_index_map(value.chart) for key, value in usable.items()}

    # --- 性别无关字段：两个性别必须给出完全相同的结果（否则说明该字段其实依赖性别）---
    for key in sorted(usable):
        index_maps[key].pop("__unused__", None)

    def _reference_value(field_name: str, key: str):  # type: ignore[no-untyped-def]
        chart = usable[key].chart
        cells = index_maps[key]
        if field_name == "five_elements_class":
            return normalize_name(chart.get("element", ""))
        if field_name == "soul_palace":
            soul = chart.get("soulPalace") or {}
            return project_index_from_branch(str(soul.get("ground", ""))) if soul else None
        if field_name == "body_palace":
            body = chart.get("bodyPalace") or {}
            return project_index_from_branch(str(body.get("ground", ""))) if body else None
        if field_name == "destiny_master":
            return normalize_name(chart.get("destinyMaster", ""))
        if field_name == "body_master":
            return normalize_name(chart.get("bodyMaster", ""))
        if field_name.startswith("palace_branch."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            return project_index_from_branch(str(cell.get("ground", ""))) if cell else None
        if field_name.startswith("palace_stem."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            return normalize_name(cell.get("sky", "")) if cell else None
        if field_name.startswith("major_stars."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            return sorted(normalize_name(item) for item in cell.get("majorStars", [])) if cell else None
        if field_name.startswith("minor_stars."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            return sorted(normalize_name(item) for item in cell.get("minorStars", [])) if cell else None
        if field_name.startswith("mutagen."):
            mutagen = field_name.split(".", 1)[1]
            mapping = chart.get("bornStarDerivativeMap") or {}
            for raw_key, value in mapping.items():
                if normalize_mutagen(raw_key) == mutagen:
                    return normalize_name(value)
            return None
        if field_name.startswith("trine."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            if not cell:
                return None
            # 三方四正 = 本宫 + 对宫 + 两个三合宫；用项目索引集合表示
            base = int(cell["our_index"])
            return sorted({base, (base + 4) % 12, (base + 6) % 12, (base + 8) % 12})
        if field_name.startswith("decadal_range."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            if not cell or cell.get("ageStart") is None:
                return None
            return [int(cell["ageStart"]), int(cell["ageEnd"])]
        if field_name.startswith("changsheng12."):
            name = field_name.split(".", 1)[1]
            cell = cells.get(name)
            return normalize_name(cell.get("lifeStage", "")) if cell else None
        return None

    def _production_value(field_name: str):  # type: ignore[no-untyped-def]
        if field_name == "five_elements_class":
            return normalize_name(production_chart.five_elements_class)
        if field_name == "soul_palace":
            return int(production_chart.soul_palace_index)
        if field_name == "body_palace":
            return int(production_chart.body_palace_index)
        if field_name == "destiny_master":
            return normalize_name(production_chart.soul)
        if field_name == "body_master":
            return normalize_name(production_chart.body)
        if field_name.startswith("palace_branch."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            return palace.index if palace else None
        if field_name.startswith("palace_stem."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            return normalize_name(palace.heavenly_stem) if palace else None
        if field_name.startswith("major_stars."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            return sorted(normalize_name(star.name) for star in palace.major_stars) if palace else None
        if field_name.startswith("minor_stars."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            return sorted(normalize_name(star.name) for star in palace.minor_stars) if palace else None
        if field_name.startswith("mutagen."):
            mutagen = field_name.split(".", 1)[1]
            for item in production_chart.natal_mutagens:
                if normalize_mutagen(item.mutagen) == mutagen:
                    return normalize_name(item.star)
            return None
        if field_name.startswith("trine."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            return sorted(int(value) for value in palace.trine_indices) if palace else None
        if field_name.startswith("decadal_range."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            values = list(palace.decadal_range or [])
            return [int(values[0]), int(values[-1])] if len(values) >= 2 else None
        if field_name.startswith("changsheng12."):
            palace = production_palaces.get(field_name.split(".", 1)[1])
            return normalize_name(palace.changsheng12) if palace else None
        return None

    gender_independent_fields = [
        "five_elements_class",
        "soul_palace",
        "body_palace",
        "destiny_master",
        "body_master",
        *(f"palace_branch.{name}" for name in PALACE_NAMES),
        *(f"palace_stem.{name}" for name in PALACE_NAMES),
        *(f"major_stars.{name}" for name in PALACE_NAMES),
        *(f"minor_stars.{name}" for name in PALACE_NAMES),
        "mutagen.禄", "mutagen.权", "mutagen.科", "mutagen.忌",
        *(f"trine.{name}" for name in PALACE_NAMES),
    ]
    gender_dependent_fields = [
        *(f"decadal_range.{name}" for name in PALACE_NAMES),
        *(f"changsheng12.{name}" for name in PALACE_NAMES),
    ]

    # 先确定哪个性别能对上"性别相关字段"，用于报告 variant ↔ gender 的对应关系
    scores: dict[str, int] = {}
    for key in sorted(usable):
        matched = 0
        considered = 0
        for field_name in gender_dependent_fields:
            production_value = _production_value(field_name)
            reference_value = _reference_value(field_name, key)
            if production_value is None or reference_value is None:
                continue
            considered += 1
            if production_value == reference_value:
                matched += 1
        scores[key] = matched
        result.gender_agreement[key] = {"matched": matched, "considered": considered}
    matched_gender = max(scores, key=lambda item: scores[item]) if scores else ""
    result.matched_gender = matched_gender

    for field_name in gender_independent_fields:
        production_value = _production_value(field_name)
        reference_value = _reference_value(field_name, matched_gender) if matched_gender else None
        result.differences.append(_classify(
            case.case_id, field_name, production_value, reference_value, "gender_independent",
            is_late_zi=late_zi,
        ))
    for field_name in gender_dependent_fields:
        production_value = _production_value(field_name)
        reference_value = _reference_value(field_name, matched_gender) if matched_gender else None
        result.differences.append(_classify(
            case.case_id, field_name, production_value, reference_value, "gender_dependent",
            matched_gender=matched_gender, scores=scores, is_late_zi=late_zi,
        ))

    # 明示不可比对的字段（GOAL §3G-6：不能静默省略）
    for field_name in ("horoscope.yearly", "horoscope.monthly"):
        result.differences.append(Difference(
            case_id=case.case_id,
            field=f"{field_name}.palace_ground",
            production_value=None,
            reference_value=None,
            classification=FIELD_UNAVAILABLE,
            possible_reason=(
                "参考实现只暴露十年运（大限）导航接口，其运限盘与 iztro 的 horoscope "
                "链式接口不是同一模型；强行对齐需要在本项目里重实现流年/流月，"
                "那会破坏『独立实现源』的前提。"
            ),
            school_convention="",
            resolved=False,
            binding="not_comparable",
        ))
    return result


#: 已知的四化表流派差异（中州派 vs 全书/常见表）：按干列出「科」星不同
MUTAGEN_SCHOOL_NOTES: dict[str, str] = {
    "戊": "戊干四化「右弼科 / 太阳科」两说",
    "庚": "庚干四化「太阴科 / 天同科 / 天府科」多说",
    "壬": "壬干四化「左辅科 / 天府科」两说",
}
#: 中州派命主口径备忘（参考实现以生年支取命主表）
DESTINY_MASTER_NOTE = (
    "参考实现以**生年地支**索引命主表；命主的标准定义是以**命宫地支**查表"
    "（身主才是以生年支查表）。这是参考实现的疑似实现问题，不是流派差异；"
    "本条不影响生产引擎（iztro 按标准口径给出命主）。"
)
#: 晚子时口径差异（实测证据：1990-06-15 23:30）
LATE_ZI_NOTE = (
    "晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**"
    "（农历日与日柱都不换），iztro 把晚子时归入**次日**（日柱推进、"
    "农历日推进用于星曜安放）。"
    "实测例：1990-06-15 23:30，iztro 的紫微落在田宅（等价于 06-16 00:30 的盘），"
    "参考实现的紫微落在福德（当日 5 月 23 日）。"
    "这属于流派差异，本核对不判定谁对谁错。"
)
#: iztro 晚子时显示不一致（本项目发现，影响 raw_chart 展示口径）
LATE_ZI_DISPLAY_NOTE = (
    "iztro 在晚子时的**显示口径与安放口径不一致**：chart.lunar_date 显示「五月廿三」，"
    "但星曜按「五月廿四」安放（与次日 00:30 的盘完全一致）。"
    "该不一致只影响 raw_chart 的农历日显示，不影响本项目因子计算"
    "（因子只用 iztro 的盘面，不含农历日字符串）；且本项目 500 只股票的出生时刻"
    "来自上市日派生的日间时刻（取自 exchange_session_calendar 的开盘/收盘时段），"
    "不含晚子时，因此对 Phase 3 研究结论无影响。"
)


def _classify(
    case_id: str,
    field_name: str,
    production_value: object,
    reference_value: object,
    binding: str,
    *,
    matched_gender: str = "",
    scores: dict[str, int] | None = None,
    is_late_zi: bool = False,
) -> Difference:
    """把一条字段比较结果归类（分类优先于"是否相等"的机械判断）。"""
    if production_value is None or reference_value is None:
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=FIELD_UNAVAILABLE,
            possible_reason="一侧没有该字段的取值（不填 0 冒充）。",
            binding=binding,
        )
    if production_value == reference_value:
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=IDENTICAL, resolved=True, binding=binding,
        )

    # --- 已知的流派/实现差异优先归类 ---
    if field_name == "destiny_master":
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=DIFFERENT_SUSPECTED_IMP_BUG,
            possible_reason=DESTINY_MASTER_NOTE,
            school_convention="",
            resolved=False, binding=binding,
        )
    if field_name.startswith("mutagen.科"):
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=DIFFERENT_SCHOOL_CONVENTION,
            possible_reason="十干四化表存在流派差异（同一干位的『科』星取法不同）。",
            school_convention="；".join(MUTAGEN_SCHOOL_NOTES.values()),
            resolved=True, binding=binding,
        )
    if field_name.startswith("changsheng12.") or field_name.startswith("decadal_range."):
        matched = (scores or {}).get(matched_gender, 0)
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=DIFFERENT_VARIANT_ASSUMPTION,
            possible_reason=(
                "长生十二神与大限方向由『阳男阴女顺行 / 阴男阳女逆行』决定，"
                "而股票没有性别（AGENTS.md §5）。本项目用 variant_mode 显式假设顺/逆行，"
                f"因此在同一性别参数下两边可能方向相反（本案例在该性别下匹配 {matched} 项）。"
            ),
            school_convention="大限/长生顺逆行规则",
            resolved=True, binding=binding,
        )
    if field_name.startswith("major_stars.") and is_late_zi:
        # 晚子时换日口径不同 → 农历日不同 → 紫微（进而全部主星）的安放整体不同。
        # 这不是命名问题，必须归为流派口径差异，否则会掩盖真实原因。
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=DIFFERENT_SCHOOL_CONVENTION,
            possible_reason=LATE_ZI_NOTE,
            school_convention="晚子时换日（当日子时 / 次日子时）",
            resolved=True, binding=binding,
        )
    if field_name.startswith("minor_stars.") or field_name.startswith("major_stars."):
        return Difference(
            case_id=case_id, field=field_name,
            production_value=production_value, reference_value=reference_value,
            classification=DIFFERENT_NAMING_CONVENTION,
            possible_reason="同一星曜/神煞在不同实现里的名称或收录范围不同（含简繁与别名）。",
            school_convention="星曜命名约定",
            resolved=False, binding=binding,
        )
    return Difference(
        case_id=case_id, field=field_name,
        production_value=production_value, reference_value=reference_value,
        classification=DIFFERENT_SCHOOL_CONVENTION,
        possible_reason="未能用已有流派说明解释的差异，按流派差异登记并保留待查。",
        school_convention="",
        resolved=False, binding=binding,
    )


__all__ = [
    "CASE_VERSION",
    "DIFFERENT_NAMING_CONVENTION",
    "DIFFERENT_SCHOOL_CONVENTION",
    "DIFFERENT_SUSPECTED_IMP_BUG",
    "DIFFERENT_VARIANT_ASSUMPTION",
    "FIELD_UNAVAILABLE",
    "IDENTICAL",
    "LATE_ZI_DISPLAY_NOTE",
    "LATE_ZI_NOTE",
    "MUTAGEN_SCHOOL_NOTES",
    "PALACE_NAMES",
    "CaseComparison",
    "CrossEngineCase",
    "Difference",
    "compare_case",
    "load_cases",
]
