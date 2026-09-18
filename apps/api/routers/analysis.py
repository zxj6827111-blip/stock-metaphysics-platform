"""``/api/v1/analysis`` 与 ``/api/v1/stocks/{code}/analysis`` 路由。"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.deps import (
    db_session,
    get_analysis_service,
    get_backtest,
    get_knowledge,
    get_market,
    parse_as_of,
)
from apps.api.errors import InvalidRequestError, NotFoundError
from src.core.config import settings
from src.core.orchestration.analysis_service import AnalysisService
from src.core.schemas.analysis import (
    AnalysisRun,
    BaziAnalysisResponse,
    ConsensusSnapshot,
    ConflictSnapshot,
)
from src.core.schemas.common import BirthBasis, Exchange, VariantMode
from src.core.schemas.factor import FactorSet
from src.core.schemas.market import EventStudyRequest, EventStudyResult
from src.core.schemas.stock import BirthProfileCreateRequest, StockMaster
from src.core.stock import codes
from src.core.stock.birth_profile import build_birth_profile
from src.factors.registry.definitions import DEFINITION_INDEX
from src.knowledge.retrieval.provider import build_query_from_factors

router = APIRouter(tags=["analysis"])


class BaziAnalysisRequest(BaseModel):
    """八字分析请求。"""

    as_of: str | None = Field(
        default=None,
        description="分析基准时间（ISO8601）。该时刻之后的数据不得作为输入特征。",
        examples=["2024-11-15T14:32:00"],
    )
    horizon: str = Field(default="20d", description="预测/研究窗口标签")
    birth_basis: BirthBasis = BirthBasis.LISTING_OPEN
    variant_mode: VariantMode = VariantMode.NOT_APPLICABLE
    huangli_days: int = Field(default=31, ge=1, le=120, description="黄历扫描自然日数")
    persist: bool = True


def _resolve_stock(db: Session, market, service: AnalysisService, code: str) -> StockMaster:
    try:
        code, exchange, board, wind = codes.parse(code)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc

    stock = service.load_stock(db, code)
    if stock is None or not stock.name or stock.listing_date is None:
        fetched = market.get_stock(code)
        stock = fetched if fetched.name else (stock or fetched)
        if stock.exchange == Exchange.UNKNOWN:
            stock.exchange = exchange
            stock.board = board
        if not stock.wind_code:
            stock.wind_code = wind
    return stock


@router.post(
    "/api/v1/stocks/{code}/analysis/bazi",
    response_model=BaziAnalysisResponse,
    summary="执行八字分析（含黄历与因子）",
    tags=["stocks"],
)
def analyze_bazi(
    code: str,
    payload: BaziAnalysisRequest | None = None,
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
) -> BaziAnalysisResponse:
    """股票代码 → 出生档案 → 历法 → 黄历 → 八字原盘 → 因子 → 落库。

    * 紫微斗数在 Phase 1 **未实现**，不返回任何伪造结果。
    * 所有结果记录 engine_version / config_version / birth_profile_version。
    """
    req = payload or BaziAnalysisRequest()
    as_of = parse_as_of(req.as_of)

    stock = _resolve_stock(db, market, service, code)

    is_trading_day = None
    if stock.listing_date is not None:
        try:
            history = market.get_daily_bars(
                stock.stock_code, stock.listing_date,
                date(min(stock.listing_date.year + 1, date.today().year), stock.listing_date.month, 1),
            )
            known = {b.trade_date for b in history.bars}
            if known:
                is_trading_day = lambda d: d in known  # noqa: E731
        except Exception:  # noqa: BLE001
            is_trading_day = None

    profile = build_birth_profile(
        stock,
        BirthProfileCreateRequest(
            birth_basis=req.birth_basis,
            variant_mode=req.variant_mode,
        ),
        is_trading_day=is_trading_day,
    )

    response = service.run_bazi_analysis(
        db,
        stock=stock,
        birth_profile=profile,
        as_of=as_of,
        horizon=req.horizon,
        huangli_days=req.huangli_days,
        persist=req.persist,
    )
    if req.persist:
        db.commit()
    return response


@router.get("/api/v1/analysis/{analysis_id}", response_model=AnalysisRun,
            summary="获取分析运行上下文")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisRun:
    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    return run


@router.get("/api/v1/analysis/{analysis_id}/charts/bazi", summary="获取八字原始盘面")
def get_bazi_chart(
    analysis_id: str,
    raw: bool = Query(False, description="true 时返回未加工的原盘（含 assumptions/warnings）"),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    """八字原始盘面（一等数据）。"""
    artifact = service.load_raw_chart(db, analysis_id, "bazi")
    if artifact is None:
        raise NotFoundError(f"未找到 {analysis_id} 的八字盘面")
    if raw:
        return artifact
    return {
        "chart_id": artifact["chart_id"],
        "engine": artifact["engine"],
        "engine_version": artifact["engine_version"],
        "config_version": artifact["config_version"],
        "birth_profile_version": artifact["birth_profile_version"],
        "as_of": artifact["as_of"],
        "chart": artifact["raw_chart"],
        "warnings": artifact["warnings"],
    }


@router.get("/api/v1/analysis/{analysis_id}/huangli", summary="获取黄历")
def get_huangli(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    artifact = service.load_raw_chart(db, analysis_id, "huangli")
    if artifact is None:
        raise NotFoundError(f"未找到 {analysis_id} 的黄历记录")
    return {
        "chart_id": artifact["chart_id"],
        "engine_version": artifact["engine_version"],
        "config_version": artifact["config_version"],
        "as_of": artifact["as_of"],
        # raw_huangli 就是 HuangliSnapshot 的 raw 字段内容
        "huangli": artifact["raw_chart"],
    }


@router.get("/api/v1/analysis/{analysis_id}/factors", response_model=FactorSet,
            summary="获取因子集合")
def get_factors(
    analysis_id: str,
    direction: int | None = Query(None, ge=-1, le=1, description="只看 direction=+1/-1/0"),
    engine: str | None = Query(None, description="bazi / huangli"),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> FactorSet:
    factor_set = service.load_factor_set(db, analysis_id)
    if factor_set is None:
        raise NotFoundError(f"未找到 {analysis_id} 的因子观测")
    if direction is not None:
        factor_set.observations = [o for o in factor_set.observations if int(o.direction) == direction]
    if engine:
        factor_set.observations = [o for o in factor_set.observations if str(o.engine) == engine]
    return factor_set


@router.get("/api/v1/analysis/{analysis_id}/consensus", response_model=ConsensusSnapshot,
            summary="获取展示层共识快照")
def get_consensus(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> ConsensusSnapshot:
    """**展示层**共识快照。

    Phase 1 未实现正式 ConsensusEngine；``display_only`` 恒为 ``true``。
    不可用引擎（如紫微）不会被按 0 分计入聚合。
    """
    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    return run.consensus or ConsensusSnapshot(note="共识快照不可用")


@router.get("/api/v1/analysis/{analysis_id}/conflicts", response_model=ConflictSnapshot,
            summary="获取展示层分歧快照")
def get_conflicts(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> ConflictSnapshot:
    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    return run.conflict or ConflictSnapshot(note="分歧快照不可用")


@router.get("/api/v1/analysis/{analysis_id}/evidence", summary="获取古籍证据包")
def get_evidence(
    analysis_id: str,
    top_k: int = Query(6, ge=1, le=20),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
    knowledge=Depends(get_knowledge),
) -> dict:
    """返回**同时包含支持证据与反证**的古籍证据包。"""
    factor_set = service.load_factor_set(db, analysis_id)
    if factor_set is None:
        raise NotFoundError(f"未找到 {analysis_id} 的因子观测")

    # 选取绝对值最大的若干因子作为检索驱动
    ranked = sorted(
        [o for o in factor_set.observations if o.normalized_value is not None],
        key=lambda o: -abs(o.normalized_value or 0.0),
    )[:10]
    factor_ids = [o.factor_id for o in ranked]

    query = build_query_from_factors(factor_ids)
    query.top_k = top_k
    bundle = knowledge.search(query)

    return {
        "analysis_id": analysis_id,
        "driver_factors": [
            {"factor_id": o.factor_id, "name": o.name,
             "normalized_value": o.normalized_value, "direction": int(o.direction)}
            for o in ranked
        ],
        "evidence": bundle.model_dump(mode="json"),
        "disclaimer": (
            "古籍条文只说明传统术数的说法，**不构成对股票收益的任何判断**。"
            "本系统同时检索支持与相反观点，以避免『先有结论后找古籍』。"
        ),
    }


@router.get("/api/v1/analysis/{analysis_id}/backtest", response_model=EventStudyResult,
            summary="获取历史验证（事件研究）")
def get_backtest(
    analysis_id: str,
    horizons: str = Query("5,10,20,60", description="持有期，逗号分隔"),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
    backtest=Depends(get_backtest),
) -> EventStudyResult:
    """对本次分析涉及的因子，在**已积累的因子观测与标签库**上执行事件研究。

    如果库里还没有足够的历史观测/标签，会返回 0 样本并附带明确说明，
    **不会**给出任何看似精确的虚假统计。
    """
    from sqlalchemy import select

    from src.db.models import FactorObservationRow
    from src.research.event_study.engine import (
        build_labels_frame,
        build_observations_frame,
    )
    from src.db.models import MarketBarDailyRow

    factor_set = service.load_factor_set(db, analysis_id)
    if factor_set is None:
        raise NotFoundError(f"未找到 {analysis_id} 的因子观测")

    try:
        hs = [int(h) for h in horizons.split(",") if h.strip()]
    except ValueError as exc:
        raise InvalidRequestError(f"horizons 参数非法: {horizons}") from exc

    # 只使用高度相关的核心因子做检索驱动（避免 65 个因子全上导致样本爆炸）
    driver_ids = [o.factor_id for o in sorted(
        factor_set.observations, key=lambda o: -o.rule_score
    )[:8]]

    obs_rows = db.execute(
        select(FactorObservationRow).where(FactorObservationRow.factor_id.in_(driver_ids))
    ).scalars().all()
    observations = build_observations_frame([r.to_dict() for r in obs_rows])

    labels_rows = _load_label_rows(db)
    labels = build_labels_frame(labels_rows)

    request = EventStudyRequest(
        factor_ids=driver_ids,
        horizons=hs,
        benchmark_code=settings.benchmark_index_code,
    )
    result = backtest.evaluate_factor(observations, labels, request)
    result.methodology += (
        f"  数据来源：factor_observation 表（{len(observations)} 行）与本地标签库"
        f"（{len(labels)} 行）。若样本为 0，说明尚未运行研究流水线（POST /api/v1/research/run）。"
    )
    return result


def _load_label_rows(db: Session) -> list[dict]:
    """从本地行情缓存还原标签集合（每只股票每季度采样一次 as_of）。"""
    from sqlalchemy import select

    from src.db.models import MarketBarDailyRow
    from src.market.normalization.frames import build_series
    from src.research.labels.forward_returns import compute_labels
    from src.research.pipeline import month_starts

    import pandas as pd

    codes_rows = db.execute(
        select(MarketBarDailyRow.stock_code, MarketBarDailyRow.is_benchmark)
        .distinct()
    ).all()
    stock_codes = [c for c, is_b in codes_rows if not is_b]
    if not stock_codes:
        return []

    def _frame(code: str) -> pd.DataFrame:
        rows = db.execute(
            select(MarketBarDailyRow).where(MarketBarDailyRow.stock_code == code)
            .order_by(MarketBarDailyRow.trade_date)
        ).scalars().all()
        return pd.DataFrame([{
            "trade_date": r.trade_date, "open": r.open, "high": r.high, "low": r.low,
            "close": r.close, "volume": r.volume, "amount": r.amount,
            "turnover": r.turnover, "pct_change": r.pct_change, "adjust": r.adjust,
        } for r in rows])

    bench_df = _frame(settings.benchmark_index_code)
    bench = build_series(settings.benchmark_index_code, bench_df) if len(bench_df) else None

    out: list[dict] = []
    for code in stock_codes:
        df = _frame(code)
        if len(df) < 80:
            continue
        series = build_series(code, df)
        start, end = series.bars[0].trade_date, series.bars[-1].trade_date
        for as_of_date in month_starts(start, end, step_months=3):
            try:
                labels = compute_labels(series, as_of_date, benchmark_series=bench,
                                        benchmark_code=settings.benchmark_index_code)
            except Exception:  # noqa: BLE001 - 数据不足属预期
                continue
            out.append({
                "stock_code": labels.stock_code,
                "trade_date": labels.trade_date,
                "as_of": labels.as_of,
                "ret_1d": labels.ret_1d, "ret_5d": labels.ret_5d, "ret_10d": labels.ret_10d,
                "ret_20d": labels.ret_20d, "ret_60d": labels.ret_60d,
                "max_return_20d": labels.max_return_20d,
                "max_drawdown_20d": labels.max_drawdown_20d,
                "excess_return_20d": labels.excess_return_20d,
                "bench_ret_20d": labels.bench_ret_20d,
            })
    return out


@router.get("/api/v1/factor-dictionary", summary="因子字典")
def factor_dictionary(
    category: str | None = Query(None),
    engine: str | None = Query(None),
) -> dict:
    """列出全部因子定义（含 rule_score 语义声明）。"""
    items = list(DEFINITION_INDEX.values())
    if category:
        items = [d for d in items if d.category == category]
    if engine:
        items = [d for d in items if str(d.engine) == engine]

    by_category: dict[str, int] = {}
    for d in DEFINITION_INDEX.values():
        key = str(d.category)
        by_category[key] = by_category.get(key, 0) + 1

    return {
        "total": len(items),
        "total_all": len(DEFINITION_INDEX),
        "by_category": by_category,
        "items": [d.model_dump(mode="json") for d in items],
        "disclaimer": (
            "因子 direction / rule_score 表达的是**传统规则认为的方向与强度**，"
            "不是预期收益率，也不是上涨概率。财星 ≠ 股票上涨；三合 ≠ 股票上涨。"
        ),
        "rule_version": settings.factor_rule_version,
    }


@router.get("/api/v1/analysis/{analysis_id}/guide", summary="分析导航与可用性说明")
def analysis_guide(analysis_id: str, db: Session = Depends(db_session),
                   service: AnalysisService = Depends(get_analysis_service)) -> dict:
    """给前端的可用性说明：哪些引擎可用、哪些不可用（Phase 1 紫微不可用）。"""
    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    return {
        "analysis_id": analysis_id,
        "engines": [
            {"engine": "calendar", "display_name": "历法引擎", "available": True,
             "engine_version": settings.calendar_engine_version},
            {"engine": "huangli", "display_name": "黄历引擎", "available": True,
             "engine_version": settings.huangli_engine_version},
            {"engine": "bazi", "display_name": "八字引擎", "available": True,
             "engine_version": settings.bazi_engine_version},
            {"engine": "ziwei", "display_name": "紫微斗数引擎", "available": False,
             "engine_version": "",
             "reason": "Phase 2 实现。当前不提供任何紫微结果，也不以 0 分参与聚合。"},
            {"engine": "liuyao", "display_name": "六爻引擎", "available": False,
             "engine_version": "", "reason": "仅预留接口"},
            {"engine": "qimen", "display_name": "奇门遁甲引擎", "available": False,
             "engine_version": "", "reason": "仅预留接口"},
        ],
        "phase": settings.phase,
    }


__all__ = ["router"]
