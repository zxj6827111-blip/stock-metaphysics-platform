"""关系历史研究的确定性观测构造。

关系本身只描述日期外部柱与股票原局的结构命中；本模块不赋予任何涨跌方向，
只把指定关系的命中次数作为 ``normalized_value``，交给既有 Event Study 验证。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from src.core.relations.date_relation import build_relation_matrix, flatten_events
from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import Direction, EngineId
from src.core.schemas.factor import FactorCategory, FactorObservation
from src.core.schemas.relation import RELATION_TYPES
from src.core.schemas.stock import StockBirthProfile
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine

RELATION_FACTOR_IDS: dict[str, str] = {
    "天干五合": "REL_TIANGAN_WUHE",
    "天干相冲": "REL_TIANGAN_XIANGCHONG",
    "天干生": "REL_TIANGAN_SHENG",
    "天干克": "REL_TIANGAN_KE",
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


def relation_factor_id(relation_type: str) -> str:
    try:
        return RELATION_FACTOR_IDS[relation_type]
    except KeyError as exc:
        raise ValueError(f"不支持的关系类型: {relation_type}") from exc


def build_relation_observations(
    *,
    stock_code: str,
    profile: StockBirthProfile,
    as_of_date: date,
    relation_type: str,
    bazi: BaziEngine,
    calendar: CalendarEngine,
    use_static_natal: Any | None = None,
) -> list[FactorObservation]:
    """为一个 ``(股票, as_of)`` 构造一条关系因子观测。

    ``use_static_natal`` 可传入版本化原局快照；负对照必须传 ``None``，以确保
    出生日期平移后重新排盘，而不是复用真实组的事件集合。
    """
    factor_id = relation_factor_id(relation_type)
    as_of = datetime.combine(as_of_date, datetime.min.time()).replace(hour=15)
    snapshot = calendar.snapshot(datetime.combine(as_of_date, datetime.min.time()).replace(hour=12))

    if use_static_natal is not None:
        natal = {
            position: GanZhi.from_text(
                str(use_static_natal.stems[position]) + str(use_static_natal.branches[position])
            )
            for position in ("year", "month", "day", "hour")
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
            for position in ("year", "month", "day", "hour")
        }
        day_master = chart.day_master
        engine_version = chart.engine_version

    external = {"year": snapshot.year_ganzhi, "month": snapshot.month_ganzhi, "day": snapshot.day_ganzhi}
    matrix = build_relation_matrix(external, natal, day_master=day_master)
    events = [event for event in flatten_events(matrix) if event.relation_type == relation_type]
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
        },
        normalized_value=float(count),
        direction=Direction.NEUTRAL,
        rule_score=float(min(count, 10)),
        confidence=1.0,
        availability="ok",
        rule_version="bazi-relation-v2",
        engine_version=engine_version,
        explanation=(
            f"{relation_type} 在该日期与股票原局的确定性命中次数为 {count}；"
            "关系因子不赋予涨跌方向，历史信息量需由 Event Study 与负对照检验。"
        ),
        evidence=explanations[:8],
    )]


__all__ = ["RELATION_FACTOR_IDS", "RELATION_NAMES", "build_relation_observations", "relation_factor_id"]
