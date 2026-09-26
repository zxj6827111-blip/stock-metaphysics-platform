"""Stock Fortune V1 F4 research endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.deps import db_session
from apps.api.errors import InvalidRequestError
from src.core.orchestration.stock_fortune import (
    DatabaseFortuneChartArtifactWriter,
    StockFortuneEngine,
)
from src.core.orchestration.stock_fortune_scan import StockFortuneCrossSectionScanner
from src.core.orchestration.stock_fortune_timeline import StockFortuneTimelineEngine
from src.core.schemas.fortune import (
    StockFortuneScanRequest,
    StockFortuneScanResponse,
    StockFortuneTimeline,
    StockFortuneTimelineRequest,
)

router = APIRouter(prefix="/api/v1/research/fortune", tags=["research", "stock-fortune"])


@router.post(
    "/timeline",
    response_model=StockFortuneTimeline,
    summary="股票 → Fortune 历史/未来时间轴",
)
def stock_fortune_timeline(
    payload: StockFortuneTimelineRequest,
    db: Session = Depends(db_session),
) -> StockFortuneTimeline:
    """返回 stable context + 日期变化点；不会持久化每日完整 Snapshot。"""
    try:
        engine = StockFortuneEngine(DatabaseFortuneChartArtifactWriter(db))
        result = StockFortuneTimelineEngine(engine).build(payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise InvalidRequestError(str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post(
    "/scan",
    response_model=StockFortuneScanResponse,
    summary="日期 → 显式股票集合的 Fortune 条件扫描",
)
def stock_fortune_cross_section_scan(
    payload: StockFortuneScanRequest,
    db: Session = Depends(db_session),
) -> StockFortuneScanResponse:
    """扫描显式版本化股票集合；条件与排序只描述结构，不代表投资建议。"""
    try:
        result = StockFortuneCrossSectionScanner(
            DatabaseFortuneChartArtifactWriter(db)
        ).scan(payload)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise InvalidRequestError(str(exc)) from exc
    except Exception:
        db.rollback()
        raise


__all__ = ["router"]
