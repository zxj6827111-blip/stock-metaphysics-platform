"""``/api/v1/research/ten-gods`` 路由：十神系统 V1（``ten-god-v1``）。

为什么是独立 router 而不是往 ``routers/research.py`` 里加端点
-----------------------------------------------------------
``/api/v1/**`` 的既有契约不得无版本号修改（AGENTS.md §2.3）。十神端点是**加法**，
单独成文件可以完全不碰 research.py，既避免破坏已公开契约，也把与并行 UI 分支
的冲突面降到零。前缀仍挂在 ``/api/v1/research`` 下，保持研究域的路径一致性。

所有筛选枚举由 ``/catalog`` 下发；前端不得再维护第二份十神/十神组/喜用清单。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.deps import db_session
from apps.api.errors import InvalidRequestError, NotFoundError
from src.core.config import settings
from src.core.orchestration.ten_god_calendar import TenGodCalendarError, build_stock_ten_god_calendar
from src.core.orchestration.ten_god_date_scan import scan_market_by_ten_god
from src.core.relations.ten_god import catalog_response
from src.core.schemas.ten_god import (
    DEFAULT_DAYS,
    DEFAULT_MONTHS,
    DEFAULT_YEARS,
    TenGodCatalogResponse,
    TenGodDateScanRequest,
    TenGodDateScanResponse,
    TenGodStockCalendarResponse,
)

router = APIRouter(prefix="/api/v1/research/ten-gods", tags=["research", "ten-god"])


@router.get(
    "/catalog",
    response_model=TenGodCatalogResponse,
    summary="十神目录（前端唯一枚举来源）",
)
def ten_god_catalog() -> TenGodCatalogResponse:
    """十神 / 十神组 / 五行角色 / 匹配状态全集与算法方向自描述。

    目录同时显式声明：3×3「日期 × 股票」关系矩阵不是传统十神的权威来源。
    """
    return catalog_response()


@router.get(
    "/stocks/{code}/calendar",
    response_model=TenGodStockCalendarResponse,
    summary="股票 → 未来十神时历（原局 / 流年 / 流月 / 流日）",
)
def stock_ten_god_calendar(
    code: str,
    start_date: date | None = Query(None, description="窗口起始日，缺省为今天"),
    years: int = Query(DEFAULT_YEARS, ge=0, le=30, description="流年段数（含当前生效段）"),
    months: int = Query(DEFAULT_MONTHS, ge=0, le=60, description="流月段数（按十二节换月）"),
    days: int = Query(DEFAULT_DAYS, ge=0, le=730, description="自然日数，底层始终全算"),
    view: str = Query("all", pattern="^(all|trading)$", description="trading 只是显示过滤"),
    ten_god: str | None = Query(None, description="流日十神筛选"),
    ten_god_group: str | None = Query(None, description="十神组筛选"),
    wuxing_role: str | None = Query(None, description="五行角色筛选"),
    verdict: str | None = Query(None, description="喜用匹配筛选"),
    birth_basis: str = Query(settings.canonical_birth_basis),
    birth_profile_version: str = Query(settings.canonical_birth_profile_version),
    db: Session = Depends(db_session),
) -> TenGodStockCalendarResponse:
    """五类十神全部相对**股票自己的日干（固定日主）**计算。

    流年按立春换柱、流月按十二节换柱，边界是给定的精确交节时刻（半开区间）。
    """
    try:
        return build_stock_ten_god_calendar(
            db, code,
            start_date=start_date, years=years, months=months, days=days, view=view,
            ten_god=ten_god, ten_god_group=ten_god_group,
            wuxing_role=wuxing_role, verdict=verdict,
            birth_basis=birth_basis, birth_profile_version=birth_profile_version,
        )
    except TenGodCalendarError as exc:
        message = str(exc)
        if "出生档案" in message:
            raise NotFoundError(message) from exc
        raise InvalidRequestError(message) from exc
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc


@router.post(
    "/date-scan",
    response_model=TenGodDateScanResponse,
    summary="指定日期 × 全市场十神扫描（可按十神/十神组/喜用筛选）",
)
def run_ten_god_date_scan(
    payload: TenGodDateScanRequest, db: Session = Depends(db_session)
) -> TenGodDateScanResponse:
    """权威流日十神 = ``ten_god(股票日主, 目标日日干)``。

    与 ``POST /api/v1/research/date-scan`` 的区别只在筛选维度：本端点可按
    十神 / 十神组 / 五行角色 / 匹配状态过滤，且 ``relation_type`` 是可选的
    AND 复合条件。两个端点对同一股票同一天给出完全相同的十神结果。
    """
    try:
        return scan_market_by_ten_god(db, payload)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
