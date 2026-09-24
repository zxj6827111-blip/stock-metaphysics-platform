"""日期 → 全市场十神扫描（TG-3，``ten-god-v1``）。

与已有 ``POST /api/v1/research/date-scan`` 的关系
------------------------------------------------
关系矩阵（流年/流月/流日 × 股票年/月/日 的 3×3）继续负责冲合刑害破生克伏吟反吟，
本模块**不**从矩阵单元格里聚合"流日十神"。权威值只有一条路径：

    ten_god(股票日主, 目标日日干)

因此行构造直接复用 ``build_stock_relation_result``，其内部走
``relations/date_relation.build_day_stem_verdict`` —— 与旧端点、与
「股票 → 十神时历」端点是同一个函数，两个入口不可能给出不同十神。

为什么不直接给旧的 ``DateScanRequest`` 加字段
--------------------------------------------
AGENTS.md §2.3：``/api/v1/**`` 已公开的请求体字段名与响应结构不得无版本号修改。
新端点是加法，旧契约零改动（由 ``tests/integration/test_api_ten_god_date_scan.py``
反向锁定）。

未来日期的股票池
----------------
系统无法知道未来的上市/退市事件，因此目标日超出可证据化范围时使用
**最新已知 canonical universe**，并把 ``universe_mode`` /
``universe_as_of`` / ``future_universe_assumption`` 显式写进响应（合同 §14）。
可证据化范围用「该 universe_version 中已登记的最晚上市日」界定 ——
晚于它的日期我们可能漏掉尚未入库的新股，也完全不知道谁会退市。
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.constants import TEN_GOD_GROUP, TEN_GODS
from src.core.orchestration.date_relation_scan import (
    EVALUATION_HOUR,
    _load_names,
    _load_profiles,
    _resolve_natal,
    build_stock_relation_result,
)
from src.core.orchestration.result_cache import ResultCache, cache_descriptor
from src.core.schemas.common import Warning_
from src.core.schemas.relation import (
    RELATION_TYPES,
    VERDICT_MATCH,
    VERDICT_MISMATCH,
    VERDICT_UNKNOWN,
    WUXING_ROLES,
    RelationStockResult,
)
from src.core.schemas.ten_god import (
    TEN_GOD_GROUPS,
    UNIVERSE_MODE_LATEST_KNOWN,
    UNIVERSE_MODE_PIT,
    TenGodDateScanRequest,
    TenGodDateScanResponse,
    TenGodDateScanRow,
    TenGodDateScanVersions,
)
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.research.universe.point_in_time import PointInTimeUniverse, UniverseSnapshot

#: 全量底表缓存：键只含"影响每行结果"的口径，过滤条件不进键（否则翻页即重算）。
TEN_GOD_SCAN_CACHE = ResultCache(max_entries=16)

_FUTURE_UNIVERSE_ASSUMPTION = (
    "未来股票池按当前已知成分冻结：取该 universe_version 中已登记的最晚上市日 "
    "({universe_as_of}) 作为成员基准，不包含未知的未来上市与未来退市事件。"
    "该集合不是 Point-in-Time 股票池，不得用于历史收益结论。"
)

_VERDICT_ENUM = {VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN}


class TenGodScanError(ValueError):
    """扫描口径不支持或筛选枚举非法。"""


def _validate_request(request: TenGodDateScanRequest) -> None:
    if request.ten_god_rule_version != settings.ten_god_rule_version:
        raise TenGodScanError(
            f"不支持的 ten_god_rule_version={request.ten_god_rule_version}；"
            f"当前只接受 {settings.ten_god_rule_version}"
        )
    if request.relation_rule_version != settings.relation_rule_version:
        raise TenGodScanError(
            f"不支持的 relation_rule_version={request.relation_rule_version}；"
            f"当前只接受 {settings.relation_rule_version}"
        )
    if request.universe != settings.canonical_universe_version:
        raise TenGodScanError(f"当前扫描只允许 canonical universe={settings.canonical_universe_version}")
    if request.birth_profile_version != settings.canonical_birth_profile_version:
        raise TenGodScanError(
            f"当前扫描只允许 canonical birth_profile_version={settings.canonical_birth_profile_version}"
        )
    if request.birth_basis != settings.canonical_birth_basis:
        raise TenGodScanError(f"当前扫描只允许 canonical birth_basis={settings.canonical_birth_basis}")

    legal: dict[str, tuple[str, set[str]]] = {
        "ten_god": ("十神", set(TEN_GODS)),
        "ten_god_group": ("十神组", set(TEN_GOD_GROUPS)),
        "wuxing_role": ("五行角色", set(WUXING_ROLES)),
        "verdict": ("匹配状态", _VERDICT_ENUM),
        "relation_type": ("关系类型", set(RELATION_TYPES)),
    }
    for field, (label, allowed) in legal.items():
        value = getattr(request, field)
        if value and value not in allowed:
            raise TenGodScanError(
                f"未知{label} {field}={value!r}；合法值见 "
                "/api/v1/research/ten-gods/catalog 与 /api/v1/research/relation-catalog"
            )


def resolve_universe(db: Session, request: TenGodDateScanRequest) -> tuple[UniverseSnapshot, str, date]:
    """返回（成员快照, universe_mode, universe_as_of）。

    历史/当前日期走严格 PIT；超出可证据化范围（已登记的最晚上市日）时
    冻结为最新已知成分，绝不伪造"未来 PIT"。
    """
    universe = PointInTimeUniverse.load(db, request.universe, snapshot_at=request.date)
    cutoff = max((record.list_date for record in universe.list_all_members()), default=None)
    if cutoff is None:
        raise TenGodScanError(f"universe_version={request.universe} 下没有任何 membership 记录")
    if request.date > cutoff:
        return universe.at(cutoff), UNIVERSE_MODE_LATEST_KNOWN, cutoff
    return universe.at(request.date), UNIVERSE_MODE_PIT, request.date


def _cache_key(request: TenGodDateScanRequest, membership: UniverseSnapshot) -> tuple[Any, ...]:
    return (
        request.date.isoformat(),
        request.universe,
        request.birth_basis,
        request.birth_profile_version,
        settings.ten_god_rule_version,
        settings.relation_rule_version,
        settings.relation_matrix_schema_version,
        settings.calendar_engine_version,
        settings.bazi_engine_version,
        settings.config_version,
        membership.digest,
    )


def _scan_id(key: tuple[Any, ...]) -> str:
    return "TGS-" + hashlib.sha256("|".join(str(item) for item in key).encode()).hexdigest()[:16]


def _row_from_result(result: RelationStockResult) -> TenGodDateScanRow:
    """把关系扫描行降维成十神行。

    十神、分组、角色、匹配状态全部取自 ``day_stem_verdict``，
    不从 ``ten_gods`` 列表或矩阵事件重新推导。
    """
    verdict = result.day_stem_verdict
    if verdict is None:
        return TenGodDateScanRow(
            stock_code=result.stock_code,
            name=result.name,
            exchange=result.exchange,
            availability=result.availability,
            unavailable=list(result.unavailable),
            relation_group=result.metrics.group,
        )
    return TenGodDateScanRow(
        stock_code=result.stock_code,
        name=result.name,
        exchange=result.exchange,
        day_master=verdict.day_master,
        day_stem=verdict.day_stem,
        ten_god=verdict.ten_god,
        ten_god_group=verdict.ten_god_group or TEN_GOD_GROUP.get(verdict.ten_god, ""),
        day_stem_wuxing=verdict.day_stem_wuxing,
        wuxing_role=verdict.wuxing_role,
        verdict=verdict.verdict,
        is_yong_or_xi=verdict.is_yong_or_xi,
        reason=verdict.reason,
        relation_types=list(result.relation_types),
        s_raw=result.metrics.S_raw,
        v_raw=result.metrics.V_raw,
        u_raw=result.metrics.U_raw,
        relation_group=result.metrics.group,
        availability=result.availability,
        unavailable=list(result.unavailable),
    )


def _matches(row: TenGodDateScanRow, request: TenGodDateScanRequest) -> bool:
    """五个条件全部是 AND；过滤发生在分页之前。"""
    if request.ten_god and row.ten_god != request.ten_god:
        return False
    if request.ten_god_group and row.ten_god_group != request.ten_god_group:
        return False
    if request.wuxing_role and row.wuxing_role != request.wuxing_role:
        return False
    if request.verdict and row.verdict != request.verdict:
        return False
    if request.relation_type and request.relation_type not in row.relation_types:
        return False
    return True


def _sort_rows(rows: list[TenGodDateScanRow], sort: str) -> list[TenGodDateScanRow]:
    if sort == "ten_god":
        order = {god: idx for idx, god in enumerate(TEN_GODS)}
        return sorted(rows, key=lambda row: (order.get(row.ten_god, len(order)), row.stock_code))
    if sort in {"s", "v", "u"}:
        field = f"{sort.upper()}_raw"

        def metric_key(row: TenGodDateScanRow) -> tuple[int, int, str]:
            value = getattr(row, field)
            # 未知（None）必须与真实的 0 分开排序，不能塌成同一个键
            if value is None:
                return (1, 0, row.stock_code)
            return (0, -value, row.stock_code)

        return sorted(rows, key=metric_key)
    return sorted(rows, key=lambda row: row.stock_code)


def _count_by(rows: list[TenGodDateScanRow], attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.availability != "ok":
            continue
        key = getattr(row, attribute) or "未定"
        counts[key] = counts.get(key, 0) + 1
    return counts


def scan_market_by_ten_god(db: Session, request: TenGodDateScanRequest) -> TenGodDateScanResponse:
    """执行 日期 → 全市场 十神扫描。"""
    _validate_request(request)
    membership, universe_mode, universe_as_of = resolve_universe(db, request)
    key = _cache_key(request, membership)

    def compute() -> dict[str, Any]:
        when = datetime(request.date.year, request.date.month, request.date.day, EVALUATION_HOUR)
        snapshot = CalendarEngine().snapshot(when)
        profiles = _load_profiles(db, membership.member_codes, request)  # type: ignore[arg-type]
        names = _load_names(db, membership.member_codes)
        bazi = BaziEngine()
        rows = [
            _row_from_result(build_stock_relation_result(
                code,
                names.get(code, ("", ""))[0],
                names.get(code, ("", ""))[1],
                _resolve_natal(code, profiles.get(code), request, bazi),  # type: ignore[arg-type]
                snapshot,
                include_matrix=False,
            ))
            for code in membership.member_codes
        ]
        return {"rows": rows, "fallback": sum(1 for row in rows if row.availability != "ok")}

    cached, hit = TEN_GOD_SCAN_CACHE.get_or_compute(key + ("all",), compute)
    all_rows: list[TenGodDateScanRow] = list(cached["rows"])
    valid_rows = [row for row in all_rows if row.availability == "ok"]

    filtered = [row for row in all_rows if _matches(row, request)]
    filtered = _sort_rows(filtered, request.sort)
    page = filtered[request.offset: request.offset + request.limit]

    warnings: list[Warning_] = [Warning_(
        code="TEN_GOD_SCAN_STRUCTURAL_ONLY",
        message=(
            "流日十神由 ten_god(股票日主, 目标日日干) 确定性计算，是结构分类而非收益预测；"
            "十神与喜用匹配独立，「正财」不等于「适合」。"
        ),
        severity="info",
    )]
    if universe_mode == UNIVERSE_MODE_LATEST_KNOWN:
        warnings.append(Warning_(
            code="TEN_GOD_FUTURE_UNIVERSE_FROZEN",
            message=_FUTURE_UNIVERSE_ASSUMPTION.format(universe_as_of=universe_as_of.isoformat()),
            severity="warning",
        ))
    if cached["fallback"]:
        warnings.append(Warning_(
            code="TEN_GOD_SCAN_PROFILE_UNAVAILABLE",
            message=(
                f"{cached['fallback']} 只股票缺少指定出生档案，ten_god 返回空、"
                "未用 0 或默认十神冒充。"
            ),
            severity="warning",
        ))
    for item in membership.warnings:
        warnings.append(Warning_(code="PIT_UNIVERSE_WARNING", message=item.reason, severity="warning"))

    return TenGodDateScanResponse(
        scan_id=_scan_id(key),
        target_date=request.date,
        versions=TenGodDateScanVersions(
            ten_god_rule_version=settings.ten_god_rule_version,
            calendar_engine_version=settings.calendar_engine_version,
            bazi_engine_version=settings.bazi_engine_version,
            relation_rule_version=settings.relation_rule_version,
            relation_matrix_schema_version=settings.relation_matrix_schema_version,
            birth_basis=request.birth_basis,
            birth_profile_version=request.birth_profile_version,
            universe_version=request.universe,
            universe_digest=membership.digest,
        ),
        universe_mode=universe_mode,
        universe_as_of=universe_as_of,
        future_universe_assumption=(
            _FUTURE_UNIVERSE_ASSUMPTION.format(universe_as_of=universe_as_of.isoformat())
            if universe_mode == UNIVERSE_MODE_LATEST_KNOWN else ""
        ),
        stock_total=len(membership.member_codes),
        valid_scan_count=len(valid_rows),
        filtered_count=len(filtered),
        returned_count=len(page),
        offset=request.offset,
        limit=request.limit,
        ten_god_counts=_count_by(all_rows, "ten_god"),
        ten_god_group_counts=_count_by(all_rows, "ten_god_group"),
        verdict_counts=_count_by(all_rows, "verdict"),
        wuxing_role_counts=_count_by(all_rows, "wuxing_role"),
        filtered_ten_god_counts=_count_by(filtered, "ten_god"),
        rows=page,
        warnings=warnings,
        cache=cache_descriptor(key, hit),
    )


__all__ = [
    "TEN_GOD_SCAN_CACHE",
    "TenGodScanError",
    "resolve_universe",
    "scan_market_by_ten_god",
]
