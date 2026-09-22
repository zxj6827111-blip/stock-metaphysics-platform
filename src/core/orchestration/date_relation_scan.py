"""日期关系扫描编排服务（bazi-relation-v3 / relation-matrix-v2）。

口径（Date Scan 与 Relation Study 必须一致）：

* 矩阵：流年/流月/流日 × 股票年/月/日（3×3）；股票时柱不参与；
* 聚合：所有列表统计只读 ``events_for_source_pillar(matrix, "day")``（流日行）；
* 喜用：来自完整四柱原局（BaziEngine），矩阵不用时柱 ≠ 喜忌与时辰无关；
* 采样：日级标准时点 12:00:00 Asia/Shanghai（节气交界日不同时刻会影响月柱，
  因此固定一个可复现的标准时刻，而不是"hour 没作用"）。
"""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.orchestration.result_cache import ResultCache, cache_descriptor
from src.core.relations.date_relation import (
    COMPOUND_RELATIONS,
    DISTURBING_RELATIONS,
    NATAL_POSITIONS,
    SUPPORTIVE_RELATIONS,
    build_date_relation_fingerprint,
    build_day_stem_verdict,
    build_relation_matrix,
    classify_relation_group,
    events_for_source_pillar,
)
from src.core.schemas.bazi import BaziChart
from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import Warning_
from src.core.schemas.relation import (
    AGGREGATE_SCOPE,
    EVALUATION_TIME,
    EVALUATION_TIMEZONE,
    MATRIX_SOURCE_SCOPE,
    MATRIX_TARGET_SCOPE,
    RELATION_TYPES,
    YONGSHEN_BASIS,
    DateScanQuery,
    DateScanRequest,
    DateScanResponse,
    DateScanVersions,
    RelationMetrics,
    RelationScopeDescriptor,
    RelationStockResult,
)
from src.core.stock import codes
from src.core.stock.birth_profile import from_row
from src.db.models import StockBirthProfileRow, StockMasterRow
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.research.universe.point_in_time import PointInTimeUniverse

DATE_SCAN_CACHE = ResultCache(max_entries=16)

#: 原局快照完整性要求的柱位（喜用神来自完整四柱，故缓存仍按四柱校验）。
SNAPSHOT_POSITIONS: tuple[str, ...] = ("year", "month", "day", "hour")

#: v3 标准采样时刻（小时）。产品定义的日级研究时点，不是"hour 参数被吞掉"。
EVALUATION_HOUR = int(EVALUATION_TIME.split(":")[0])


@dataclass(frozen=True)
class NatalSnapshot:
    """股票原局快照：四柱（喜用基础）+ 日主 + 喜用忌仇闲（五类）。"""

    stems: dict[str, str]
    branches: dict[str, str]
    day_master: str
    yong_shen: tuple[str, ...]
    xi_shen: tuple[str, ...]
    ji_shen: tuple[str, ...]
    chou_shen: tuple[str, ...] = ()
    xian_shen: tuple[str, ...] = ()
    engine_version: str = ""
    source: str = ""


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _tuple_field(value: Any, name: str) -> tuple[str, ...]:
    raw = _field(value, name, [])
    return tuple(str(item) for item in (raw or []))


@lru_cache(maxsize=1)
def _load_static_natal_cache() -> dict[str, NatalSnapshot]:
    """读取已经按出生模型构建的原局快照。

    该文件是 Phase 4 的离线产物，不承担未来数据；只在元数据明确为
    ``v2-phase4b`` 且引擎版本一致时作为 canonical listing_open 快照使用。
    旧条目缺少仇神/闲神字段时按空元组兼容读取，不因此重算整份缓存。
    """
    path = settings.data_dir / "phase4_cache" / "astrology_natal_cache.pkl"
    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
    except (OSError, EOFError, pickle.PickleError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict) or not str(payload.get("birth_profile_prefix", "")).startswith("v2-phase4b"):
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {}

    result: dict[str, NatalSnapshot] = {}
    for key, raw in entries.items():
        if not isinstance(key, tuple) or len(key) < 2 or str(key[1]) != "listing_open_v1":
            continue
        if not isinstance(raw, dict):
            continue
        engine_version = str(raw.get("engine_version", ""))
        if engine_version and engine_version != settings.bazi_engine_version:
            continue
        stems = raw.get("stems")
        branches = raw.get("branches")
        if not isinstance(stems, dict) or not isinstance(branches, dict):
            continue
        code = str(key[0])
        if any(not stems.get(pos) or not branches.get(pos) for pos in SNAPSHOT_POSITIONS):
            continue
        yong = raw.get("yong_shen")
        result[code] = NatalSnapshot(
            stems={pos: str(stems[pos]) for pos in SNAPSHOT_POSITIONS},
            branches={pos: str(branches[pos]) for pos in SNAPSHOT_POSITIONS},
            day_master=str(raw.get("day_master", stems.get("day", ""))),
            yong_shen=_tuple_field(yong, "yong_shen"),
            xi_shen=_tuple_field(yong, "xi_shen"),
            ji_shen=_tuple_field(yong, "ji_shen"),
            chou_shen=_tuple_field(yong, "chou_shen"),
            xian_shen=_tuple_field(yong, "xian_shen"),
            engine_version=engine_version or settings.bazi_engine_version,
            source="phase4_natal_cache",
        )
    return result


def _snapshot_from_chart(chart: BaziChart) -> NatalSnapshot:
    return NatalSnapshot(
        stems={position: chart.pillar_by_position(position).ganzhi.stem for position in SNAPSHOT_POSITIONS},
        branches={position: chart.pillar_by_position(position).ganzhi.branch for position in SNAPSHOT_POSITIONS},
        day_master=chart.day_master,
        yong_shen=tuple(chart.yong_shen.yong_shen),
        xi_shen=tuple(chart.yong_shen.xi_shen),
        ji_shen=tuple(chart.yong_shen.ji_shen),
        chou_shen=tuple(chart.yong_shen.chou_shen),
        xian_shen=tuple(chart.yong_shen.xian_shen),
        engine_version=chart.engine_version,
        source="bazi_engine_fallback",
    )


def _natal_ganzhi(natal: NatalSnapshot) -> dict[str, GanZhi]:
    """矩阵目标柱位：只取年/月/日三柱（时柱退出择日关系研究范围）。"""
    return {
        position: GanZhi.from_text(natal.stems[position] + natal.branches[position])
        for position in NATAL_POSITIONS
    }


def _percentile(value: int, values: list[int]) -> float | None:
    if not values:
        return None
    less = sum(1 for item in values if item < value)
    equal = sum(1 for item in values if item == value)
    return round((less + 0.5 * equal) / len(values) * 100, 2)


def _fingerprint_cache_key(request: DateScanRequest, universe_digest: str) -> tuple[Any, ...]:
    """缓存键：任何会影响结果的版本与口径都可能使旧结构不可复用。"""
    return (
        request.date.isoformat(),
        request.universe,
        request.birth_basis,
        request.birth_profile_version,
        request.relation_rule_version,
        settings.relation_matrix_schema_version,
        AGGREGATE_SCOPE,
        tuple(MATRIX_TARGET_SCOPE),
        YONGSHEN_BASIS,
        EVALUATION_TIME,
        EVALUATION_TIMEZONE,
        settings.calendar_engine_version,
        settings.bazi_engine_version,
        settings.config_version,
        settings.relation_fingerprint_version,
        universe_digest,
    )


def _scan_id(key: tuple[Any, ...]) -> str:
    return "DRS-" + hashlib.sha256("|".join(str(item) for item in key).encode()).hexdigest()[:16]


def scope_descriptor() -> RelationScopeDescriptor:
    return RelationScopeDescriptor(
        aggregate_scope=AGGREGATE_SCOPE,
        matrix_source_scope=list(MATRIX_SOURCE_SCOPE),
        matrix_target_scope=list(MATRIX_TARGET_SCOPE),
        yongshen_basis=YONGSHEN_BASIS,
        evaluation_time=EVALUATION_TIME,
        timezone=EVALUATION_TIMEZONE,
    )


def _evaluation_datetime(day) -> datetime:  # type: ignore[no-untyped-def]
    return datetime.combine(day, datetime.min.time()).replace(hour=EVALUATION_HOUR)


def _load_profiles(db: Session, stock_codes: tuple[str, ...], request: DateScanRequest) -> dict[str, Any]:
    if not stock_codes:
        return {}
    rows = db.execute(
        select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code.in_(stock_codes),
            StockBirthProfileRow.birth_basis == request.birth_basis,
            StockBirthProfileRow.birth_profile_version == request.birth_profile_version,
        )
    ).scalars().all()
    return {row.stock_code: from_row(row) for row in rows}


def _load_names(db: Session, stock_codes: tuple[str, ...]) -> dict[str, tuple[str, str]]:
    if not stock_codes:
        return {}
    rows = db.execute(select(StockMasterRow).where(StockMasterRow.stock_code.in_(stock_codes))).scalars().all()
    return {row.stock_code: (row.name, row.exchange) for row in rows}


def _resolve_natal(
    code: str,
    profile: Any,
    request: DateScanRequest,
    bazi: BaziEngine,
) -> NatalSnapshot | None:
    static = _load_static_natal_cache().get(code)
    if static is not None:
        return static
    if profile is None:
        return None
    chart = bazi.build_chart(
        birth_datetime=profile.birth_datetime.replace(tzinfo=None),
        as_of=_evaluation_datetime(request.date),
        variant_mode=profile.variant_mode,
        stock_code=code,
    )
    return _snapshot_from_chart(chart)


def build_stock_relation_result(
    code: str,
    name: str,
    exchange: str,
    natal: NatalSnapshot | None,
    snapshot,
    *,
    include_matrix: bool,
) -> RelationStockResult:
    """构造单只股票的择日关系结果（Date Scan 与 Relation Study 共用的唯一口径）。"""
    if natal is None:
        return RelationStockResult(
            stock_code=code,
            name=name,
            exchange=exchange,
            metrics=RelationMetrics(),
            availability="unavailable",
            unavailable=["stock_birth_profile"],
            research_status="NOT_RUN",
        )

    external = {"year": snapshot.year_ganzhi, "month": snapshot.month_ganzhi, "day": snapshot.day_ganzhi}
    matrix = build_relation_matrix(external, _natal_ganzhi(natal), day_master=natal.day_master)
    day_events = events_for_source_pillar(matrix, "day")
    types = list(dict.fromkeys(event.relation_type for event in day_events))
    s = sum(1 for item in day_events if item.relation_type in SUPPORTIVE_RELATIONS)
    v = sum(1 for item in day_events if item.relation_type in DISTURBING_RELATIONS)
    u = sum(1 for item in day_events if item.relation_type in COMPOUND_RELATIONS)
    stem = list(dict.fromkeys(item.relation_type for item in day_events if item.relation_type.startswith("天干")))
    branch = list(dict.fromkeys(item.relation_type for item in day_events if item.relation_type in {
        "六合", "六冲", "三合", "半合", "三会", "相刑", "三刑", "自刑", "相害", "六破", "同支",
    }))
    compound_types = list(dict.fromkeys(
        item.relation_type for item in day_events if item.relation_type in COMPOUND_RELATIONS
    ))
    hit_explanations = list(dict.fromkeys(
        f"{event.relation_type}：{event.source_pillar}{event.source_stem}{event.source_branch} × {event.target_pillar}{event.target_stem}{event.target_branch}（{event.notes}）"
        for event in day_events
    ))
    yong = set(natal.yong_shen) | set(natal.xi_shen)
    yong_relations = [item.relation_type for item in day_events if item.element and item.element in yong]
    verdict = build_day_stem_verdict(
        day_master=natal.day_master,
        day_stem=snapshot.day_ganzhi.stem,
        yong_shen=natal.yong_shen,
        xi_shen=natal.xi_shen,
        ji_shen=natal.ji_shen,
        chou_shen=natal.chou_shen,
        xian_shen=natal.xian_shen,
    )
    ten_gods = [verdict.ten_god] if verdict.ten_god else []
    return RelationStockResult(
        stock_code=code,
        name=name,
        exchange=exchange,
        natal={position: natal.stems[position] + natal.branches[position] for position in NATAL_POSITIONS},
        day_master=natal.day_master,
        yong_shen=list(natal.yong_shen),
        xi_shen=list(natal.xi_shen),
        ji_shen=list(natal.ji_shen),
        chou_shen=list(natal.chou_shen),
        xian_shen=list(natal.xian_shen),
        relation_types=types,
        hit_explanations=hit_explanations,
        stem_relations=stem,
        branch_relations=branch,
        compound_relations=compound_types,
        ten_gods=ten_gods,
        yong_shen_relations=list(dict.fromkeys(yong_relations)),
        day_stem_verdict=verdict,
        metrics=RelationMetrics(s_raw=s, v_raw=v, u_raw=u, group=classify_relation_group(s, v, u)),
        research_status="NOT_RUN",
        matrix=matrix if include_matrix else None,
    )


#: 兼容旧引用名（内部/脚本使用）。
_build_one = build_stock_relation_result


def _sort_rows(rows: list[RelationStockResult], sort: str) -> list[RelationStockResult]:
    if sort == "s":
        return sorted(rows, key=lambda row: (-(row.metrics.S_raw or -1), row.stock_code))
    if sort == "v":
        return sorted(rows, key=lambda row: (-(row.metrics.V_raw or -1), row.stock_code))
    if sort == "u":
        return sorted(rows, key=lambda row: (-(row.metrics.U_raw or -1), row.stock_code))
    return sorted(rows, key=lambda row: row.stock_code)


def _validate_request(request: DateScanRequest) -> None:
    if request.universe != settings.canonical_universe_version:
        raise ValueError(f"当前扫描只允许 canonical universe={settings.canonical_universe_version}")
    if request.birth_profile_version != settings.canonical_birth_profile_version:
        raise ValueError(
            f"当前扫描只允许 canonical birth_profile_version={settings.canonical_birth_profile_version}"
        )
    if request.birth_basis != settings.canonical_birth_basis:
        raise ValueError(f"当前扫描只允许 canonical birth_basis={settings.canonical_birth_basis}")
    if request.relation_rule_version != settings.relation_rule_version:
        raise ValueError(f"不支持的 relation_rule_version={request.relation_rule_version}")
    if request.relation_type and request.relation_type not in RELATION_TYPES:
        raise ValueError(
            f"未知 relation_type={request.relation_type}；合法值见 /api/v1/research/relation-catalog"
        )


def scan_market_by_date(db: Session, request: DateScanRequest) -> DateScanResponse:
    """执行日期→PIT 股票池→3×3 关系矩阵扫描（聚合只读流日行）。"""
    _validate_request(request)
    universe = PointInTimeUniverse.load(db, request.universe, snapshot_at=request.date)
    membership = universe.at(request.date)
    key = _fingerprint_cache_key(request, membership.digest)
    cache_key = key + ("all",)

    def compute() -> dict[str, Any]:
        snapshot = CalendarEngine().snapshot(_evaluation_datetime(request.date))
        fingerprint = build_date_relation_fingerprint(snapshot)
        profiles = _load_profiles(db, membership.member_codes, request)
        names = _load_names(db, membership.member_codes)
        bazi = BaziEngine()
        static = _load_static_natal_cache()
        rows = [
            build_stock_relation_result(
                code,
                names.get(code, ("", ""))[0],
                names.get(code, ("", ""))[1],
                _resolve_natal(code, profiles.get(code), request, bazi),
                snapshot,
                include_matrix=False,
            )
            for code in membership.member_codes
        ]
        valid = [row for row in rows if row.availability == "ok"]
        s_values = [row.metrics.S_raw for row in valid if row.metrics.S_raw is not None]
        v_values = [row.metrics.V_raw for row in valid if row.metrics.V_raw is not None]
        u_values = [row.metrics.U_raw for row in valid if row.metrics.U_raw is not None]
        for row in valid:
            row.metrics.S_percentile = _percentile(row.metrics.S_raw or 0, s_values)
            row.metrics.V_percentile = _percentile(row.metrics.V_raw or 0, v_values)
            row.metrics.U_percentile = _percentile(row.metrics.U_raw or 0, u_values)
        relation_type_counts = {
            relation: sum(1 for row in rows if relation in row.relation_types)
            for relation in RELATION_TYPES
        }
        all_group_counts: dict[str, int] = {}
        for row in rows:
            all_group_counts[row.metrics.group] = all_group_counts.get(row.metrics.group, 0) + 1
        return {
            "fingerprint": fingerprint,
            "rows": rows,
            "static_count": len(static),
            "relation_type_counts": relation_type_counts,
            "all_group_counts": all_group_counts,
            "valid_scan_count": len(valid),
        }

    cached, hit = DATE_SCAN_CACHE.get_or_compute(cache_key, compute)
    all_rows = list(cached["rows"])
    rows = all_rows
    if request.relation_type:
        rows = [row for row in rows if request.relation_type in row.relation_types]
    rows = _sort_rows(rows, request.sort)
    page = rows[request.offset: request.offset + request.limit]

    group_counts: dict[str, int] = {}
    for row in rows:
        group_counts[row.metrics.group] = group_counts.get(row.metrics.group, 0) + 1
    warnings = [Warning_(
        code="RELATION_SCAN_DESCRIPTIVE_ONLY",
        message=(
            "S/V/U 仅统计流日行（external_day_row）的关系事件计数与横截面百分位，"
            "不代表收益预测；关系目录与口径见 relation-catalog 与版本字段。"
        ),
        severity="info",
    )]
    warnings.extend(
        Warning_(code="PIT_UNIVERSE_WARNING", message=item.reason, severity="warning")
        for item in membership.warnings
    )
    unavailable = sum(1 for row in all_rows if row.availability != "ok")
    if unavailable:
        warnings.append(Warning_(
            code="RELATION_SCAN_PROFILE_UNAVAILABLE",
            message=f"{unavailable} 只股票缺少指定出生档案，未用 0 冒充结果。",
            severity="warning",
        ))
    if cached.get("static_count", 0) < len(membership.member_codes):
        warnings.append(Warning_(
            code="RELATION_SCAN_NATAL_FALLBACK",
            message="部分股票未命中版本化原局缓存，已回退到确定性 BaziEngine；首次扫描可能较慢。",
            severity="info",
        ))

    versions = DateScanVersions(
        calendar_engine_version=settings.calendar_engine_version,
        bazi_engine_version=settings.bazi_engine_version,
        relation_rule_version=settings.relation_rule_version,
        relation_matrix_schema_version=settings.relation_matrix_schema_version,
        fingerprint_version=settings.relation_fingerprint_version,
        birth_basis=request.birth_basis,
        birth_profile_version=request.birth_profile_version,
        universe_version=request.universe,
        universe_digest=membership.digest,
    )
    return DateScanResponse(
        scan_id=_scan_id(key),
        target_date=request.date,
        fingerprint=cached["fingerprint"],
        versions=versions,
        scope=scope_descriptor(),
        stock_total=len(membership.member_codes),
        valid_scan_count=int(cached.get("valid_scan_count", sum(1 for row in all_rows if row.availability == "ok"))),
        returned_count=len(page),
        filtered_count=len(rows),
        offset=request.offset,
        limit=request.limit,
        group_counts=group_counts,
        relation_type_counts=dict(cached.get("relation_type_counts", {})),
        query=DateScanQuery(
            date=request.date,
            universe=request.universe,
            birth_basis=request.birth_basis,
            birth_profile_version=request.birth_profile_version,
            relation_rule_version=request.relation_rule_version,
            relation_type=request.relation_type,
            sort=request.sort,
            offset=request.offset,
            limit=request.limit,
        ),
        rows=page,
        warnings=warnings,
        cache=cache_descriptor(cache_key, hit),
    )


def relation_detail(db: Session, request: DateScanRequest, code: str) -> RelationStockResult:
    """读取单只股票的完整 3×3 关系矩阵与流日判定。"""
    _validate_request(request)
    normalized = codes.normalize_code(code)
    membership = PointInTimeUniverse.load(db, request.universe, snapshot_at=request.date).at(request.date)
    if normalized not in membership.member_codes:
        raise ValueError(f"股票 {normalized} 不在 {request.date} 的 PIT 股票池中")
    profile = _load_profiles(db, (normalized,), request).get(normalized)
    name, exchange = _load_names(db, (normalized,)).get(normalized, ("", ""))
    snapshot = CalendarEngine().snapshot(_evaluation_datetime(request.date))
    natal = _resolve_natal(normalized, profile, request, BaziEngine())
    return build_stock_relation_result(normalized, name, exchange, natal, snapshot, include_matrix=True)


__all__ = [
    "DATE_SCAN_CACHE",
    "NatalSnapshot",
    "build_stock_relation_result",
    "relation_detail",
    "scan_market_by_date",
    "scope_descriptor",
]
