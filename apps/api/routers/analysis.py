"""``/api/v1/analysis`` 与 ``/api/v1/stocks/{code}/analysis`` 路由。"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Response
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
    ConflictSnapshot,
    ConsensusSnapshot,
    MultiAnalysisResponse,
    ZiweiAnalysisResponse,
)
from src.core.schemas.common import (
    Availability,
    BirthBasis,
    EngineId,
    Exchange,
    VariantMode,
    VersionStamp,
    Warning_,
)
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


class MultiAnalysisRequest(BaziAnalysisRequest):
    """多模型综合研判请求（八字 + 紫微 + 黄历）。

    与 `/analysis/bazi` 的唯一语义差别：``variant_mode`` 同时决定
    **八字大运顺逆**与**紫微大限顺行/逆行**，且必须显式给出
    （紫微不接受 ``not_applicable``，见 ADR-0010）。
    """


class ZiweiAnalysisRequest(BaziAnalysisRequest):
    """紫微分析请求。

    ``variant_mode`` 必须显式指定 ``forward`` / ``reverse`` / ``both``：
    股票没有真实性别，紫微运限无法由性别推导，系统**不会**提供默认值。
    """


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


@router.post(
    "/api/v1/stocks/{code}/analysis/ziwei",
    response_model=ZiweiAnalysisResponse,
    summary="执行紫微斗数分析（需要显式方向 variant）",
    tags=["stocks"],
)
def analyze_ziwei(
    code: str,
    payload: ZiweiAnalysisRequest | None = None,
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
) -> ZiweiAnalysisResponse:
    """股票代码 → 出生档案 → 紫微十二宫原盘 → 落库。

    **必须**显式指定 `variant_mode`：`forward`（顺行）/ `reverse`（逆行）/ `both`。

    股票没有真实性别，紫微的运限顺逆无法由性别推导；系统**不会**偷偷用男命或女命。
    `both` 会产出两套盘面并分别落库，**不会先平均**（ADR-0010）。
    """
    req = payload or ZiweiAnalysisRequest()
    as_of = parse_as_of(req.as_of)

    if req.variant_mode == VariantMode.NOT_APPLICABLE:
        raise InvalidRequestError(
            "紫微分析必须显式指定 variant_mode=forward（顺行）或 reverse（逆行）或 both。"
            "股票没有真实性别，系统不提供任何默认性别假设（ADR-0010）。"
        )

    stock = _resolve_stock(db, market, service, code)
    profile = build_birth_profile(
        stock,
        BirthProfileCreateRequest(birth_basis=req.birth_basis, variant_mode=req.variant_mode),
    )

    charts, chart_ids, warnings = service.build_ziwei_charts(
        db, stock=stock, birth_profile=profile, as_of=as_of,
        variant_mode=req.variant_mode, persist=req.persist,
    )
    if not charts:
        # 故障隔离：紫微不可用是**已知状态**而非服务器错误，返回可解释的信息
        from src.engines.ziwei.ziwei_engine import ZiweiUnavailableError as _ZU

        reason = service.ziwei.unavailable_reason() or "紫微排盘未产出任何结果"
        _ = _ZU  # 保持异常类型可被调用方引用
        analysis_id = f"AN-{as_of.strftime('%Y%m%d%H%M%S')}-{stock.stock_code}-ziwei-na"
        if req.persist:
            db.commit()
        return ZiweiAnalysisResponse(
            analysis_id=analysis_id, stock=stock, birth_profile=profile,
            variant_mode=str(req.variant_mode), charts={}, chart_artifact_ids={},
            versions=VersionStamp(
                config_version=settings.config_version,
                birth_profile_version=profile.birth_profile_version,
                computed_at=datetime.now(),
            ),
            assumptions=[
                "股票无真实性别：紫微运限以方向 variant（顺行/逆行）表达，不默认男女。",
            ],
            warnings=[Warning_(code="ZIWEI_UNAVAILABLE", message=reason, severity="warning"), *warnings],
        )

    # 因子：紫微因子命名空间（Phase 2B）—— 目前为空，观点如实返回 unavailable
    from src.core.schemas.factor import FactorSet

    factor_set = FactorSet(
        stock_code=stock.stock_code, as_of=as_of,
        engine_version=settings.ziwei_engine_version,
        rule_version=settings.ziwei_factor_rule_version,
        config_version=settings.config_version, observations=[],
    )
    opinions = {
        key: service.build_opinion(
            EngineId.ZIWEI, factor_set, settings.ziwei_engine_version,
            unavailable_reason=(
                "紫微盘面已产出，但紫微因子层尚未在本版本接入，"
                "观点分数返回 null（不使用 0 分代替）。"
            ),
        )
        for key in charts
    }

    analysis_id = f"AN-{as_of.strftime('%Y%m%d%H%M%S')}-{stock.stock_code}-{uuid.uuid4().hex[:6]}"
    if req.persist:
        db.commit()

    return ZiweiAnalysisResponse(
        analysis_id=analysis_id,
        stock=stock,
        birth_profile=profile,
        variant_mode=str(req.variant_mode),
        charts={k: v.model_dump(mode="json") for k, v in charts.items()},  # type: ignore[attr-defined]
        chart_artifact_ids=chart_ids,
        factors=factor_set,
        opinions=opinions,
        versions=VersionStamp(
            engine_version=settings.ziwei_engine_version,
            rule_version=settings.ziwei_factor_rule_version,
            config_version=settings.config_version,
            birth_profile_version=profile.birth_profile_version,
            knowledge_version=settings.knowledge_version,
            market_data_version=settings.market_data_version,
            computed_at=datetime.now(),
        ),
        assumptions=[
            "股票无真实性别：紫微运限以方向 variant（顺行/逆行）表达，不默认男女。",
            "顺行/逆行 variant 的差异**仅限于大限/小限顺逆与长生十二神顺逆**，"
            "十二宫、星曜、四化、流年流月流日与 variant 无关 —— 两者不是两条独立证据。",
        ],
        warnings=warnings,
    )


@router.post(
    "/api/v1/stocks/{code}/analysis/multi",
    response_model=MultiAnalysisResponse,
    summary="多模型综合研判（八字 + 紫微 + 黄历 → 三个独立观点 + 共识 + 分歧）",
    tags=["stocks"],
)
def analyze_multi(
    code: str,
    payload: MultiAnalysisRequest | None = None,
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
) -> MultiAnalysisResponse:
    """Phase 2 综合研判的唯一数据源。

    * 三个模型**各自独立**产出观点（只消费自己的因子命名空间）；
    * 紫微不可用时其余模型照常工作，共识的可用引擎数相应降低；
    * **禁止用平均分掩盖分歧**；
    * 共识只表示"模型之间方向一致程度"，不表示"历史有效"。
    """
    req = payload or MultiAnalysisRequest()
    as_of = parse_as_of(req.as_of)
    stock = _resolve_stock(db, market, service, code)
    profile = build_birth_profile(
        stock,
        BirthProfileCreateRequest(birth_basis=req.birth_basis, variant_mode=req.variant_mode),
    )
    response = service.run_multi_analysis(
        db, stock=stock, birth_profile=profile, as_of=as_of,
        horizon=req.horizon, huangli_days=req.huangli_days, persist=req.persist,
    )
    if req.persist:
        db.commit()
    return response


@router.get("/api/v1/analysis/{analysis_id}/charts/ziwei", summary="获取紫微原始盘面")
def get_ziwei_charts(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    """按 variant 返回紫微盘面（``both`` 模式下返回两套，**不合并**）。"""
    charts = service.load_ziwei_charts(db, analysis_id)
    if not charts:
        raise NotFoundError(f"未找到 {analysis_id} 的紫微盘面（可能未启用紫微或服务不可用）")
    return {
        "analysis_id": analysis_id,
        "variants": list(charts.keys()),
        "charts": charts,
        "note": (
            "每个 variant 的盘面**分别保存**，系统不会对两套盘面取平均。"
            "顺行/逆行变体的差异仅限于大限/小限顺逆与长生十二神顺逆。"
        ),
    }


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

    labels_rows, label_meta = _load_label_rows(db)
    labels = build_labels_frame(labels_rows)

    request = EventStudyRequest(
        factor_ids=driver_ids,
        horizons=hs,
        benchmark_code=settings.benchmark_index_code,
    )
    result = backtest.evaluate_factor(observations, labels, request)

    # --- P0-1：研究状态机 ---
    # 该端点不运行负对照，状态上限为 INCONCLUSIVE；含降级/合成标签 → NO_REAL_DATA。
    from src.research.status import assess_research_status

    data_is_real = not label_meta["degraded_codes"]
    assessment = assess_research_status(
        result, None,
        data_is_real=data_is_real,
        data_problems=[f"标签含降级/合成来源: {c}" for c in label_meta["degraded_codes"][:10]],
    )
    result.research_status = assessment.status.value
    result.research_status_reasons = assessment.reasons
    result.data_source = {
        "label_rows": label_meta["total"],
        "degraded_codes": label_meta["degraded_codes"],
        "label_sources": label_meta["label_sources"],
        "is_real": data_is_real,
    }
    if not data_is_real:
        result.warnings.append(Warning_(
            code="RESEARCH_DATA_UNAVAILABLE",
            message=(
                "标签库中含合成/降级行情来源，本次历史验证仅用于系统联调，"
                "不构成任何历史有效性证据。"
            ),
            severity="error",
        ))

    result.methodology += (
        f"  数据来源：factor_observation 表（{len(observations)} 行）与 forward_label 标签库"
        f"（{len(labels)} 行，来源 {label_meta['label_sources']}）。"
        f"研究状态：{assessment.status.value}。"
        "若样本为 0，说明尚未运行研究流水线（POST /api/v1/research/run）或标签库为空。"
    )
    db.commit()  # 提交可能的标签写穿透
    return result


def _load_label_rows(db: Session) -> tuple[list[dict], dict]:
    """加载标签：优先 ``forward_label`` 持久化表；为空时从行情缓存计算并写穿透。

    Returns:
        ``(rows, meta)``；``meta`` 含 ``degraded_codes`` / ``label_sources`` / ``total``。
    """
    import pandas as pd
    from sqlalchemy import select

    from src.db.models import MarketBarDailyRow
    from src.market.normalization.frames import build_series
    from src.research.labels.forward_returns import compute_labels
    from src.research.labels.store import load_label_rows, upsert_label
    from src.research.pipeline import month_starts

    stored, meta = load_label_rows(db, benchmark_code=settings.benchmark_index_code)
    if stored:
        return stored, meta

    degraded_codes: set[str] = set()
    sources: dict[str, int] = {}

    codes_rows = db.execute(
        select(MarketBarDailyRow.stock_code, MarketBarDailyRow.is_benchmark)
        .distinct()
    ).all()
    stock_codes = [c for c, is_b in codes_rows if not is_b]
    if not stock_codes:
        return [], {"total": 0, "degraded_codes": [], "label_sources": {}}

    def _frame(code: str) -> tuple[pd.DataFrame, bool, str]:
        rows = db.execute(
            select(MarketBarDailyRow).where(MarketBarDailyRow.stock_code == code)
            .order_by(MarketBarDailyRow.trade_date)
        ).scalars().all()
        degraded = any(r.is_degraded for r in rows)
        source = rows[0].source if rows else ""
        return pd.DataFrame([{
            "trade_date": r.trade_date, "open": r.open, "high": r.high, "low": r.low,
            "close": r.close, "volume": r.volume, "amount": r.amount,
            "turnover": r.turnover, "pct_change": r.pct_change, "adjust": r.adjust,
        } for r in rows]), degraded, source

    bench_df, bench_degraded, _ = _frame(settings.benchmark_index_code)
    bench = build_series(settings.benchmark_index_code, bench_df, is_degraded=bench_degraded) \
        if len(bench_df) else None
    if bench_degraded:
        degraded_codes.add(f"benchmark:{settings.benchmark_index_code}")

    out: list[dict] = []
    for code in stock_codes:
        df, degraded, source = _frame(code)
        if len(df) < 80:
            continue
        if degraded:
            degraded_codes.add(code)
        series = build_series(code, df, is_degraded=degraded,
                              source_name=source or "cache")
        start, end = series.bars[0].trade_date, series.bars[-1].trade_date
        for as_of_date in month_starts(start, end, step_months=3):
            try:
                labels = compute_labels(series, as_of_date, benchmark_series=bench,
                                        benchmark_code=settings.benchmark_index_code)
            except Exception:  # noqa: BLE001 - 数据不足属预期
                continue
            # 写穿透：下一次同口径请求毫秒级返回
            upsert_label(db, labels)
            sources[labels.data_source or source or "unknown"] = \
                sources.get(labels.data_source or source or "unknown", 0) + 1
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
    return out, {
        "total": len(out),
        "degraded_codes": sorted(degraded_codes),
        "label_sources": sources,
    }


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
    """给前端的可用性说明：**本次分析**中哪些引擎真的产出了结果。

    ``available`` 的语义是"该引擎在本次分析中是否可用并完成"，
    而不是"引擎在系统里是否存在"。因此紫微服务正常但本次
    ``variant_mode=not_applicable`` 时，这里仍是 ``false``，并给出准确原因。
    """
    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")

    completed = {str(e) for e in (run.engines_completed or [])}
    ziwei_charts = service.load_ziwei_charts(db, analysis_id)
    ziwei_variants = sorted(ziwei_charts.keys())
    ziwei_service_ok = service.ziwei.availability == Availability.OK

    if ziwei_variants:
        ziwei_available, ziwei_reason = True, ""
    elif not ziwei_service_ok:
        ziwei_available, ziwei_reason = False, (
            f"紫微排盘服务不可用：{service.ziwei.unavailable_reason()}。"
            "其余引擎不受影响；紫微不以 0 分参与任何聚合。"
        )
    else:
        ziwei_available, ziwei_reason = False, (
            "本次分析未启用紫微（variant_mode 不是 forward/reverse/both）。"
            "紫微运限需要显式的顺行/逆行方向；股票无真实性别，"
            "系统不提供默认性别假设（ADR-0010）。"
        )

    return {
        "analysis_id": analysis_id,
        "engines": [
            {"engine": "calendar", "display_name": "历法引擎", "available": True,
             "engine_version": settings.calendar_engine_version},
            {"engine": "huangli", "display_name": "黄历引擎",
             "available": "huangli" in completed,
             "engine_version": settings.huangli_engine_version},
            {"engine": "bazi", "display_name": "八字引擎",
             "available": "bazi" in completed,
             "engine_version": settings.bazi_engine_version},
            {"engine": "ziwei", "display_name": "紫微斗数引擎",
             "available": ziwei_available,
             "engine_version": settings.ziwei_engine_version if ziwei_available else "",
             "variants": ziwei_variants,
             "reason": ziwei_reason},
            {"engine": "liuyao", "display_name": "六爻引擎", "available": False,
             "engine_version": "", "reason": "仅预留接口（本版本不实现）"},
            {"engine": "qimen", "display_name": "奇门遁甲引擎", "available": False,
             "engine_version": "", "reason": "仅预留接口（本版本不实现）"},
        ],
        "phase": settings.phase,
    }


__all__ = ["router"]


# ---------------------------------------------------------------------------
# Phase 2C/2D：观点、时间窗口
# ---------------------------------------------------------------------------


@router.get("/api/v1/analysis/{analysis_id}/opinions", summary="获取各引擎独立观点")
def get_opinions(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    """返回本次分析中**每个引擎各自的**观点。

    三个观点互相独立（各自只消费自己的因子命名空间）；
    不可用引擎的 `score` 为 `null` 且不计入共识分母。

    `research_status` 与 `score` 必须分开阅读：
    分数是传统规则强度，`research_status` 才是历史验证结论。
    """
    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    opinions = run.opinions or {}
    return {
        "analysis_id": analysis_id,
        "opinions": {k: v.model_dump(mode="json") for k, v in opinions.items()},
        "available_engines": sorted(
            k for k, v in opinions.items() if v.availability == Availability.OK
        ),
        "unavailable_engines": sorted(
            k for k, v in opinions.items() if v.availability != Availability.OK
        ),
        "disclaimer": (
            "opinion.score 是该术数**内部规则强度**指标，不是上涨概率、不是预期收益率。"
            "历史有效性由 research_status 与研究流水线回答，两者必须分开阅读。"
        ),
    }


class TimelineRequest(BaseModel):
    """时间窗口请求。"""

    months: int = Field(default=12, ge=1, le=24)
    weeks: int = Field(default=12, ge=1, le=52)
    variant_mode: VariantMode = VariantMode.FORWARD
    persist: bool = False


@router.get(
    "/api/v1/analysis/{analysis_id}/timeline/months",
    summary="未来 12 个月时间窗口（逐月独立三模型观点 + 共识）",
)
def get_timeline_months(
    analysis_id: str,
    months: int = Query(12, ge=1, le=24),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    """逐月窗口。

    **每个月独立**携带 bazi / ziwei / huangli / consensus / conflict /
    research_status / data_quality —— 不是一个综合数字。
    所有窗口基于**实际交易日**（交易所日历），不退化回自然日。
    """
    from src.core.orchestration.timeline import build_time_windows

    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    if run.birth_profile is None:
        raise InvalidRequestError("该分析记录缺少出生档案，无法构建时间窗口。")

    variant = _resolve_timeline_variant(run)
    response = build_time_windows(
        stock_code=run.stock_code,
        as_of=run.as_of,
        birth_datetime=run.birth_profile.birth_datetime.replace(tzinfo=None),
        months=months, weeks=0,
        variant_mode=variant,
        exchange=str(run.birth_profile.exchange),
        service=service,
    )
    return {
        "analysis_id": analysis_id,
        "stock_code": run.stock_code,
        "as_of": response.as_of.isoformat(),
        "variant_mode": response.variant_mode,
        "aggregation_version": response.aggregation_version,
        "months": [m.model_dump(mode="json") for m in response.months],
        "research_status": response.research_status,
        "research_status_reasons": response.research_status_reasons,
        "methodology": response.methodology,
        "warnings": [w.model_dump(mode="json") for w in response.warnings],
    }


@router.get(
    "/api/v1/analysis/{analysis_id}/timeline/weeks",
    summary="未来 12 周时间窗口（交易日流日结果聚合，禁止发明『流周』）",
)
def get_timeline_weeks(
    analysis_id: str,
    weeks: int = Query(12, ge=1, le=52),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
) -> dict:
    """逐周窗口。

    **传统术数没有『流周』这一层**：周度由该周内**交易日**的流日结果聚合而来，
    并同时给出 mean / median / min / max / positive_day_ratio / weighted_mean，
    避免用一个平均数掩盖分布。聚合口径版本化在 `aggregation_version`。
    """
    from src.core.orchestration.timeline import build_time_windows

    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")
    if run.birth_profile is None:
        raise InvalidRequestError("该分析记录缺少出生档案，无法构建时间窗口。")

    variant = _resolve_timeline_variant(run)
    response = build_time_windows(
        stock_code=run.stock_code,
        as_of=run.as_of,
        birth_datetime=run.birth_profile.birth_datetime.replace(tzinfo=None),
        months=0, weeks=weeks,
        variant_mode=variant,
        exchange=str(run.birth_profile.exchange),
        service=service,
    )
    return {
        "analysis_id": analysis_id,
        "stock_code": run.stock_code,
        "as_of": response.as_of.isoformat(),
        "variant_mode": response.variant_mode,
        "aggregation_version": response.aggregation_version,
        "weeks": [w.model_dump(mode="json") for w in response.weeks],
        "research_status": response.research_status,
        "research_status_reasons": response.research_status_reasons,
        "methodology": response.methodology,
        "warnings": [w.model_dump(mode="json") for w in response.warnings],
    }


def _resolve_timeline_variant(run: AnalysisRun) -> VariantMode:
    """时间窗口的 variant 来源：本次分析用的那一个。

    若分析用的是 ``not_applicable``（Phase 1 默认），时间窗口需要显式方向 ——
    这里退回 ``forward`` **并写入 warning**，绝不静默。
    """
    raw = ""
    if run.birth_profile is not None:
        raw = str(run.birth_profile.variant_mode or "")
    if raw in ("forward", "reverse", "both"):
        return VariantMode.FORWARD if raw == "both" else VariantMode(raw)
    return VariantMode.FORWARD


# ---------------------------------------------------------------------------
# Phase 2E：EvidenceBundle / AI Narrator / 报告导出
# ---------------------------------------------------------------------------


def _bundle_for(
    db: Session, service: AnalysisService, analysis_id: str, knowledge,
):
    from src.core.orchestration.evidence import (
        build_evidence_bundle,
        load_historical_stats,
    )
    from src.core.schemas.evidence import EvidenceMarketQuality

    run = service.load_analysis(db, analysis_id)
    if run is None:
        raise NotFoundError(f"分析记录不存在: {analysis_id}")

    extras = service.load_analysis_extras(db, analysis_id)
    huangli = extras.get("huangli")
    bazi = service.load_raw_chart(db, analysis_id, "bazi")
    ziwei_charts = service.load_ziwei_charts(db, analysis_id)

    hist = load_historical_stats(db, run.stock_code)
    status = run.consensus.research_status if run.consensus else "NOT_RUN"
    reasons: list[str] = []
    if run.consensus is not None:
        reasons = list(run.consensus.historical_consensus_stats.get("reasons", []) or [])

    market_quality = EvidenceMarketQuality(
        source=str(run.versions.market_data_version or ""),
        is_degraded=False,
        is_real=True,
        bar_rows=int(hist.get("rows", 0) or 0),
        notes=["行情来源见 versions.market_data_version；降级数据会在 warnings 中显式标注。"],
    )

    return build_evidence_bundle(
        run=run,
        ziwei_charts=ziwei_charts,
        raw_bazi_chart=(bazi or {}).get("raw_chart") if bazi else None,
        raw_huangli=huangli,
        knowledge=knowledge,
        historical_stats=hist,
        research_status=status,
        research_status_reasons=reasons,
        market_quality=market_quality,
    )


@router.get("/api/v1/analysis/{analysis_id}/evidence-bundle",
            summary="获取 EvidenceBundle（AI 解释层唯一允许读取的数据）")
def get_evidence_bundle(
    analysis_id: str,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
    knowledge=Depends(get_knowledge),
) -> dict:
    """结构化证据包。

    **这是 AI Narrator 唯一允许读取的数据源。** bundle 里的每一个数字都来自
    确定性代码；任何不在 bundle 里的数字，解释层都不许说。

    古籍部分强制同时包含 `classical_support` 与 `classical_counter_evidence`。
    """
    bundle = _bundle_for(db, service, analysis_id, knowledge)
    return bundle.model_dump(mode="json")


class NarrativeRequest(BaseModel):
    prefer_llm: bool = Field(
        default=True,
        description="是否优先使用 LLM；未配置 API Key 时自动退回确定性模板",
    )


@router.post("/api/v1/analysis/{analysis_id}/narrative",
             summary="生成 AI 结构化解释（只能解释，不得计算）")
def post_narrative(
    analysis_id: str,
    payload: NarrativeRequest | None = None,
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
    knowledge=Depends(get_knowledge),
) -> dict:
    """生成研究报告文本。

    * **默认走确定性模板**（无需 API Key，可离线、可复现）；
    * 配置了 `SMP_LLM_API_KEY` 且 `prefer_llm=true` 时才走 LLM；
    * **无论哪条路径，输出都必须通过 `NarratorValidator`**：
      禁止词、状态一致性、数值一致性三项检查；
    * LLM 输出未通过守卫时**不静默采用**，而是退回模板并说明原因。
    """
    from src.narrator.narrator import Narrator

    req = payload or NarrativeRequest()
    bundle = _bundle_for(db, service, analysis_id, knowledge)
    result = Narrator().narrate(bundle, prefer_llm=req.prefer_llm)
    return {
        "analysis_id": analysis_id,
        "mode": result.mode,
        "llm_requested": result.llm_requested,
        "fallback_reason": result.fallback_reason,
        "passed_guard": result.passed_guard,
        "guard_summary": result.guard.summary() if result.guard else "",
        "guard_violations": (
            [
                {"kind": v.kind, "detail": v.detail, "severity": v.severity}
                for v in result.guard.violations
            ] if result.guard else []
        ),
        "sections": result.sections,
        "text": result.text,
        "research_status": bundle.research_status,
        "disclaimer": (
            "本解释只复述 EvidenceBundle 中的确定性结果，不重新排盘、不修改分数、"
            "不修改研究状态、不编造古籍、不隐藏冲突。"
        ),
    }


@router.get("/api/v1/analysis/{analysis_id}/report",
            summary="导出研究报告（Markdown / HTML）")
def get_report(
    analysis_id: str,
    fmt: str = Query("markdown", alias="format", pattern="^(markdown|html)$"),
    db: Session = Depends(db_session),
    service: AnalysisService = Depends(get_analysis_service),
    knowledge=Depends(get_knowledge),
) -> Response:
    """导出包含版本 / 假设 / 限制 / ResearchStatus / 负对照的完整报告。"""
    from src.core.orchestration.report import render_report

    bundle = _bundle_for(db, service, analysis_id, knowledge)
    content, media_type, filename = render_report(bundle, fmt=fmt)
    return Response(
        content=content,
        media_type=media_type,
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )
