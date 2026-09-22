"""关系历史研究的确定性观测构造（bazi-relation-v3）。

关系本身只描述**流日**与股票年/月/日三柱的结构命中；本模块不赋予任何涨跌方向，
只把指定关系的命中次数作为 ``normalized_value``，交给既有 Event Study 验证。

与 Date Scan 的口径一致性（硬要求）：

* 同一个 ``build_relation_matrix``（3×3，relation-matrix-v2）；
* 同一个 ``events_for_source_pillar(matrix, "day")``（aggregate_scope=external_day_row）；
* 同一个 ``settings.relation_rule_version``。

因此「Date Scan 按流日筛出的股票」与「Relation Study 统计的命中次数」
在同一 (股票, 日期, 关系) 上必须相等（见 tests/integration/test_api_relation_study.py）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.core.config import settings
from src.core.relations.date_relation import (
    NATAL_POSITIONS,
    build_relation_matrix,
    events_for_source_pillar,
)
from src.core.schemas.calendar import CalendarSnapshot, GanZhi
from src.core.schemas.common import Direction, EngineId
from src.core.schemas.factor import FactorCategory, FactorObservation
from src.core.schemas.relation import EVALUATION_TIME, RELATION_TYPES
from src.core.schemas.stock import StockBirthProfile
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine

RELATION_FACTOR_IDS: dict[str, str] = {
    "天干五合": "REL_TIANGAN_WUHE",
    "天干相冲": "REL_TIANGAN_XIANGCHONG",
    "天干生": "REL_TIANGAN_SHENG",
    "天干受生": "REL_TIANGAN_SHOUSHENG",
    "天干克": "REL_TIANGAN_KE",
    "天干受克": "REL_TIANGAN_SHOUKE",
    "天干同五行": "REL_TIANGAN_TONGWUXING",
    "六合": "REL_LIUHE",
    "六冲": "REL_LIUCHONG",
    "三合": "REL_SANHE",
    "半合": "REL_BANHE",
    "三会": "REL_SANHUI",
    "相刑": "REL_XIANGXING",
    "三刑": "REL_SANXING",
    "自刑": "REL_ZIXING",
    "相害": "REL_XIANGHAI",
    "六破": "REL_LIUPO",
    "同支": "REL_TONGZHI",
    "伏吟": "REL_FUYIN",
    "反吟": "REL_FANYIN",
    "天合地合": "REL_TIANHEDIHE",
    "天克地冲": "REL_TIANKEDICHONG",
}

RELATION_NAMES: dict[str, str] = {name: f"关系事件：{name}" for name in RELATION_TYPES}

EVALUATION_HOUR = int(EVALUATION_TIME.split(":")[0])


def relation_factor_id(relation_type: str) -> str:
    try:
        return RELATION_FACTOR_IDS[relation_type]
    except KeyError as exc:
        raise ValueError(f"不支持的关系类型: {relation_type}") from exc


def relation_snapshot(calendar: CalendarEngine, as_of_date: date) -> CalendarSnapshot:
    """按 v3 标准采样时点（12:00 Asia/Shanghai）构造日期快照。

    研究运行器对同一 ``as_of_date`` 只调用一次并缓存，避免每只股票重复排历。
    """
    return calendar.snapshot(datetime.combine(as_of_date, datetime.min.time()).replace(hour=EVALUATION_HOUR))


def build_relation_observations(
    *,
    stock_code: str,
    profile: StockBirthProfile,
    as_of_date: date,
    relation_type: str,
    bazi: BaziEngine,
    calendar: CalendarEngine,
    use_static_natal: Any | None = None,
    snapshot: CalendarSnapshot | None = None,
) -> list[FactorObservation]:
    """为一个 ``(股票, as_of)`` 构造一条关系因子观测。

    ``use_static_natal`` 可传入版本化原局快照；负对照必须传 ``None``，以确保
    出生日期平移后重新排盘，而不是复用真实组的事件集合。
    ``snapshot`` 可由调用方按日期缓存后传入（同一天对所有股票是同一个快照）。
    """
    factor_id = relation_factor_id(relation_type)
    as_of = datetime.combine(as_of_date, datetime.min.time()).replace(hour=15)
    if snapshot is None:
        snapshot = relation_snapshot(calendar, as_of_date)

    if use_static_natal is not None:
        natal = {
            position: GanZhi.from_text(
                str(use_static_natal.stems[position]) + str(use_static_natal.branches[position])
            )
            for position in NATAL_POSITIONS
        }
        day_master = str(use_static_natal.day_master)
        engine_version = str(use_static_natal.engine_version)
    else:
        chart = bazi.build_chart(
            birth_datetime=profile.birth_datetime.replace(tzinfo=None),
            as_of=as_of,
            variant_mode=profile.variant_mode,
            stock_code=stock_code,
        )
        natal = {
            position: chart.pillar_by_position(position).ganzhi
            for position in NATAL_POSITIONS
        }
        day_master = chart.day_master
        engine_version = chart.engine_version

    external = {"year": snapshot.year_ganzhi, "month": snapshot.month_ganzhi, "day": snapshot.day_ganzhi}
    matrix = build_relation_matrix(external, natal, day_master=day_master)
    events = [
        event for event in events_for_source_pillar(matrix, "day")
        if event.relation_type == relation_type
    ]
    explanations = [
        f"{event.source_pillar}{event.source_stem}{event.source_branch} × "
        f"{event.target_pillar}{event.target_stem}{event.target_branch}：{event.notes}"
        for event in events
    ]
    count = len(events)
    return [FactorObservation(
        factor_id=factor_id,
        stock_code=stock_code,
        as_of=as_of,
        trade_date=as_of_date,
        engine=EngineId.BAZI,
        category=FactorCategory.CROSS,
        name=RELATION_NAMES[relation_type],
        raw_value={
            "relation_type": relation_type,
            "hit_count": count,
            "events": explanations,
            "aggregate_scope": "external_day_row",
            "matrix_target_scope": list(NATAL_POSITIONS),
            "evaluation_time": EVALUATION_TIME,
        },
        normalized_value=float(count),
        direction=Direction.NEUTRAL,
        rule_score=float(min(count, 10)),
        confidence=1.0,
        availability="ok",
        rule_version=settings.relation_rule_version,
        engine_version=engine_version,
        explanation=(
            f"指定 as_of 的流日柱与股票年/月/日三柱，在 3×3 矩阵流日行中命中「{relation_type}」"
            f"的事件次数为 {count}；关系因子不赋予涨跌方向，历史信息量需由 Event Study 与负对照检验。"
        ),
        evidence=explanations[:8],
    )]


__all__ = [
    "RELATION_FACTOR_IDS",
    "RELATION_NAMES",
    "build_relation_observations",
    "relation_factor_id",
    "relation_snapshot",
]
