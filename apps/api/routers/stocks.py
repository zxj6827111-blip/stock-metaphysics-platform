"""``/api/v1/stocks`` 路由。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.deps import db_session, get_analysis_service, get_market, parse_as_of
from apps.api.errors import InvalidRequestError, NotFoundError
from src.core.orchestration.analysis_service import AnalysisService
from src.core.schemas.analysis import StockSearchItem, StockSearchResponse
from src.core.schemas.common import BirthBasis, Exchange, VariantMode, Warning_
from src.core.schemas.stock import (
    BirthProfileCreateRequest,
    StockBirthProfile,
    StockMaster,
)
from src.core.stock import codes
from src.core.stock.birth_profile import build_birth_profile

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


class BirthProfileRequest(BaseModel):
    """创建出生档案请求。"""

    birth_basis: BirthBasis = Field(
        default=BirthBasis.LISTING_OPEN,
        description="出生基准。Phase 1 默认 listing_open；其余为预留候选。",
    )
    variant_mode: VariantMode = Field(
        default=VariantMode.NOT_APPLICABLE,
        description="运限顺逆变体。股票无性别 → 默认 not_applicable，禁止自动填男/女。",
    )
    override_datetime: datetime | None = Field(
        default=None, description="仅当 birth_basis=custom 时使用"
    )
    exchange_override: Exchange | None = None
    persist: bool = Field(default=True, description="是否写入 stock_birth_profile 表")


class StockDetail(BaseModel):
    stock: StockMaster
    birth_profile: StockBirthProfile | None = None
    session_key: str = ""
    warnings: list[Warning_] = Field(default_factory=list)


@router.get("/search", response_model=StockSearchResponse, summary="搜索股票")
def search_stocks(
    q: str = Query(..., min_length=1, description="代码 / 名称 / 拼音片段"),
    limit: int = Query(20, ge=1, le=100),
    market=Depends(get_market),
) -> StockSearchResponse:
    """按代码或名称搜索 A 股股票。"""
    results = market.search(q, limit=limit)
    items = [
        StockSearchItem(
            stock_code=s.stock_code,
            wind_code=s.wind_code,
            name=s.name,
            exchange=str(s.exchange),
            board=s.board,
            listing_date=s.listing_date.isoformat() if s.listing_date else "",
        )
        for s in results
    ]
    return StockSearchResponse(
        items=items,
        total=len(items),
        query=q,
        source=market.provider_id,
        is_degraded=market.provider_id == "synthetic_demo",
        warnings=[] if market.provider_id != "synthetic_demo" else [
            Warning_(
                code="MARKET_SYNTHETIC_PROVIDER",
                message="当前运行在离线合成数据模式（SMP_MARKET_PROVIDER=synthetic），股票资料来自内置清单。",
                severity="warning",
            )
        ],
    )


@router.get("/{code}", response_model=StockDetail, summary="获取股票详情")
def get_stock(
    code: str,
    as_of: str | None = Query(None, description="分析基准时间，用于读取对应出生档案"),
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
) -> StockDetail:
    """获取股票基础资料，并附带已持久化的出生档案（若存在）。"""
    try:
        code, exchange, board, wind = codes.parse(code)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc

    warnings: list[Warning_] = []
    stock = service.load_stock(db, code)
    if stock is None:
        stock = market.get_stock(code)
        if not stock.name and stock.exchange == Exchange.UNKNOWN:
            raise NotFoundError(f"无法识别股票代码 {code}")
        if stock.data_quality.notes:
            warnings.extend(
                Warning_(code="STOCK_DATA_DEGRADED", message=n, severity="warning")
                for n in stock.data_quality.notes
            )
        try:
            service.upsert_stock(db, stock)
            db.commit()
        except Exception:  # noqa: BLE001 - 落库失败不应阻塞查询
            db.rollback()

    profile = service.load_birth_profile(db, code)
    session_key = profile.evidence.lookup_key if profile else ""

    return StockDetail(stock=stock, birth_profile=profile, session_key=session_key, warnings=warnings)


@router.post("/{code}/birth-profile", response_model=StockBirthProfile,
             summary="构造 / 刷新股票出生档案")
def create_birth_profile(
    code: str,
    payload: BirthProfileRequest | None = None,
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
) -> StockBirthProfile:
    """构造股票出生档案。

    默认模型 ``listing_open``：
    上市首个正式交易日 + 该交易所 session 的正式开盘时刻 + Asia/Shanghai。

    开盘时刻来自 ``exchange_session_calendar``，**不硬编码 09:30**。
    """
    req = payload or BirthProfileRequest()
    try:
        code, exchange, board, wind = codes.parse(code)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc

    stock = service.load_stock(db, code) or market.get_stock(code)
    if stock.exchange == Exchange.UNKNOWN and exchange != Exchange.UNKNOWN:
        stock.exchange = exchange
        stock.board = board or stock.board
        stock.wind_code = wind

    # 用真实行情校验"首个交易日"（若行情可得）；失败则退回周末规则
    is_trading_day = None
    if stock.listing_date is not None:
        try:

            history = market.get_daily_bars(
                code, stock.listing_date, stock.listing_date.replace(year=stock.listing_date.year + 1)
            )
            known_days = {b.trade_date for b in history.bars}
            if known_days:
                is_trading_day = lambda d: d in known_days  # noqa: E731
        except Exception:  # noqa: BLE001 - 行情不可用时仍可构造（质量降级）
            is_trading_day = None

    profile = build_birth_profile(
        stock,
        BirthProfileCreateRequest(
            birth_basis=req.birth_basis,
            variant_mode=req.variant_mode,
            override_datetime=req.override_datetime,
            exchange_override=req.exchange_override,
        ),
        is_trading_day=is_trading_day,
    )

    if req.persist:
        try:
            service.upsert_stock(db, stock)
            service.save_birth_profile(db, profile)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            raise InvalidRequestError(f"出生档案落库失败: {exc}") from exc

    return profile


@router.post("/{code}/birth-profile/compare", summary="对比不同出生基准")
def compare_birth_baselines(
    code: str,
    as_of: str | None = Query(None),
    market=Depends(get_market),
) -> dict:
    """并排展示不同出生基准（listing_open / custom）的推导结果。

    这是 Phase 2 做"出生模型回测比较"的接口雏形。
    """
    try:
        code, _exchange, _board, _wind = codes.parse(code)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc

    stock = market.get_stock(code)
    results: list[dict] = []
    for basis in (BirthBasis.LISTING_OPEN, BirthBasis.IPO_DATE):
        try:
            p = build_birth_profile(stock, BirthProfileCreateRequest(birth_basis=basis))
            results.append({
                "birth_basis": basis.value,
                "ok": True,
                "birth_datetime": p.birth_datetime.isoformat(),
                "quality": p.data_quality.model_dump(mode="json"),
                "evidence": p.evidence.model_dump(mode="json"),
            })
        except Exception as exc:  # noqa: BLE001 - 部分基准必然不可用，如实返回
            results.append({
                "birth_basis": basis.value,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            })

    return {
        "stock_code": code,
        "as_of": parse_as_of(as_of).isoformat(),
        "baselines": results,
        "note": (
            "不同出生基准的优劣必须由历史回测决定（见 docs/methodology.md），"
            "本接口不预设哪一种正确。"
        ),
    }
