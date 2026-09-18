"""``/api/v1/research`` 路由：研究流水线、标签、负对照。"""

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
)
from apps.api.errors import InvalidRequestError, NotFoundError
from src.core.config import settings
from src.core.orchestration.analysis_service import AnalysisService
from src.core.schemas.common import BirthBasis, VariantMode, Warning_
from src.core.schemas.market import (
    EventStudyRequest,
    EventStudyResult,
    LabelSet,
    NegativeControlKind,
    NegativeControlReport,
)
from src.core.schemas.stock import BirthProfileCreateRequest, StockBirthProfile
from src.db.models import BacktestExperimentRow, BacktestResultRow
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.huangli.huangli_engine import HuangliEngine
from src.factors.registry.compute import compute_factor_set
from src.factors.registry.definitions import DEFINITION_INDEX
from src.knowledge.retrieval.provider import build_query_from_factors
from src.research.pipeline import ResearchPipeline, new_experiment_id
from src.core.stock.birth_profile import build_birth_profile
from src.core.stock.exchange_sessions import ex_value

router = APIRouter(prefix="/api/v1/research", tags=["research"])

DEFAULT_UNIVERSE = [
    "600519", "000001", "300750", "600036", "000858",
    "601318", "002594", "688981", "600000", "601899",
]


class ResearchRunRequest(BaseModel):
    universe: list[str] = Field(default_factory=lambda: list(DEFAULT_UNIVERSE),
                               description="股票池；默认 10 只跨交易所/板块样本科")
    factor_ids: list[str] = Field(default_factory=lambda: ["B_MONTH_001", "B_MONTH_002", "H_DAY_001"],
                                  description="目标因子")
    horizons: list[int] = Field(default_factory=lambda: [5, 10, 20, 60])
    sample_step_months: int = Field(default=3, ge=1, le=12, description="as_of 采样间隔（月）")
    date_from: date | None = None
    date_to: date | None = None
    run_negative_controls: bool = Field(default=True, description="是否执行四类负对照")
    persist: bool = True


class ResearchRunResponse(BaseModel):
    experiment_id: str
    event_study: EventStudyResult
    negative_controls: NegativeControlReport | None = None
    panel_stats: dict = Field(default_factory=dict)
    warnings: list[Warning_] = Field(default_factory=list)
    duration_ms: int = 0


def _build_helpers(market, service: AnalysisService):
    """构造研究流水线所需的三个回调。

    黄历快照只依赖 ``as_of``（与个股无关），因此在同一次研究运行内按日期缓存，
    避免对每个股票重复扫描整月自然日。
    """
    bazi = BaziEngine()
    huangli = HuangliEngine()
    cache: dict[tuple[str, str], StockBirthProfile] = {}
    huangli_cache: dict[str, object] = {}

    def birth_profile_provider(code: str, variant: str | None) -> StockBirthProfile:
        key = (code, variant or "real")
        if key in cache:
            return cache[key]
        stock = market.get_stock(code)
        profile = build_birth_profile(stock, BirthProfileCreateRequest())
        cache[key] = profile
        return profile

    def factor_builder(code: str, as_of_date: date, profile: StockBirthProfile):
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 0, 0)
        hl_key = as_of_date.isoformat()
        hl = huangli_cache.get(hl_key)
        if hl is None:
            hl = huangli.snapshot(as_of, days=31)
            huangli_cache[hl_key] = hl
        chart = bazi.build_chart(
            birth_datetime=profile.birth_datetime.replace(tzinfo=None),
            as_of=as_of,
            variant_mode=VariantMode(profile.variant_mode),
            stock_code=code,
        )
        fset = compute_factor_set(chart, hl, as_of, stock_code=code)  # type: ignore[arg-type]
        return fset.observations

    return birth_profile_provider, factor_builder, bazi


@router.post("/run", response_model=ResearchRunResponse, summary="运行研究流水线")
def run_research(
    payload: ResearchRunRequest,
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
    backtest=Depends(get_backtest),
) -> ResearchRunResponse:
    """执行端到端研究：构建面板 → 事件研究 → 四类负对照。

    **防未来数据泄漏**：每个 as_of 的因子只使用该时刻及之前的信息，
    标签只使用 as_of 之后的数据；两者在面板中以 (stock_code, trade_date) 对齐。
    """
    import time as _time

    from src.research.pipeline import month_starts
    from src.research.labels.forward_returns import compute_labels
    from src.research.event_study.engine import build_labels_frame, build_observations_frame

    started = _time.perf_counter()
    warnings: list[Warning_] = []
    pipeline = ResearchPipeline(backtest)

    date_from = payload.date_from or date.fromisoformat(settings.market_history_start)
    date_to = payload.date_to or date.today()
    sample_dates = month_starts(date_from, date_to, step_months=payload.sample_step_months)[-24:]
    if not sample_dates:
        raise InvalidRequestError("采样日期为空，请检查 date_from / date_to")

    # --- 行情与标签 ---
    series_cache: dict[str, object] = {}
    bench = None
    try:
        bench = market.get_benchmark_bars(settings.benchmark_index_code, date_from, date_to)
    except Exception as exc:  # noqa: BLE001
        warnings.append(Warning_(
            code="RESEARCH_BENCHMARK_UNAVAILABLE",
            message=f"基准指数不可用，超额收益将为空：{type(exc).__name__}: {exc}",
            severity="warning",
        ))

    def label_builder(code: str, as_of_date: date):
        if code not in series_cache:
            series_cache[code] = market.get_daily_bars(code, date_from, date_to)
        series = series_cache[code]
        return compute_labels(series, as_of_date, benchmark_series=bench,  # type: ignore[arg-type]
                              benchmark_code=settings.benchmark_index_code)

    birth_provider, factor_builder, _bazi = _build_helpers(market, service)

    observations, labels, panel_warnings = pipeline.build_panel(
        stocks=payload.universe,
        sample_dates=sample_dates,
        factor_builder=factor_builder,
        label_builder=label_builder,
        birth_profile_provider=birth_provider,
    )
    warnings.extend(panel_warnings)

    experiment_id = new_experiment_id("EXP")
    request = EventStudyRequest(
        factor_ids=payload.factor_ids,
        horizons=payload.horizons,
        benchmark_code=settings.benchmark_index_code,
    )
    real_result = pipeline.run_event_study(observations, labels, request)
    real_result.experiment_id = experiment_id

    # --- 负对照 ---
    control_report: NegativeControlReport | None = None
    if payload.run_negative_controls:
        control_panels: dict[str, tuple] = {}
        for kind in (
            NegativeControlKind.RANDOM_BIRTH_DATE,
            NegativeControlKind.SHIFT_PLUS_7D,
            NegativeControlKind.SHIFT_MINUS_7D,
        ):
            transform = ResearchPipeline.make_birth_transform(kind)
            obs_c, labels_c, warns_c = pipeline.build_panel(
                stocks=payload.universe,
                sample_dates=sample_dates,
                factor_builder=factor_builder,
                label_builder=label_builder,
                birth_profile_provider=birth_provider,
                birth_transform=transform,
                variant=kind.value,
            )
            warnings.extend(warns_c)
            control_panels[str(kind)] = (obs_c, labels_c)

        control_report = pipeline.run_negative_controls(
            real_result,
            control_panels=control_panels,  # type: ignore[arg-type]
            observations=observations,
            labels=labels,
            request=request,
        )

    duration_ms = int((_time.perf_counter() - started) * 1000)

    if payload.persist:
        _persist_experiment(db, experiment_id, payload, real_result, control_report, observations)
        db.commit()

    return ResearchRunResponse(
        experiment_id=experiment_id,
        event_study=real_result,
        negative_controls=control_report,
        panel_stats={
            "universe": payload.universe,
            "sample_dates": [d.isoformat() for d in sample_dates],
            "observation_rows": int(len(observations)),
            "label_rows": int(len(labels)),
            "benchmark_available": bench is not None,
        },
        warnings=warnings,
        duration_ms=duration_ms,
    )


def _persist_experiment(db: Session, experiment_id: str, payload: ResearchRunRequest,
                        real_result, control_report, observations) -> None:
    from sqlalchemy import delete

    db.execute(delete(BacktestResultRow).where(BacktestResultRow.experiment_id == experiment_id))
    if db.get(BacktestExperimentRow, experiment_id) is None:
        db.add(BacktestExperimentRow(
            experiment_id=experiment_id, kind="event_study",
            name=f"事件研究 {','.join(payload.factor_ids)}",
            factor_ids_json=payload.factor_ids, logic="any",
            universe_json=payload.universe, horizons_json=payload.horizons,
            date_from=payload.date_from, date_to=payload.date_to,
            benchmark_code=settings.benchmark_index_code,
            params_json={"sample_step_months": payload.sample_step_months,
                         "run_negative_controls": payload.run_negative_controls},
            methodology=real_result.methodology,
            seed=settings.negative_control_seed,
            status="completed",
        ))

    for h in real_result.horizons:
        db.add(BacktestResultRow(
            experiment_id=experiment_id, variant="real", horizon=h.horizon,
            sample_count=h.sample_count, up_rate=h.up_rate, excess_up_rate=h.excess_up_rate,
            mean_return=h.mean_return, median_return=h.median_return, std_return=h.std_return,
            mean_excess_return=h.mean_excess_return, max_drawdown=h.max_drawdown,
            mean_max_return=h.mean_max_return, extra_json={"note": h.note},
        ))

    if control_report is not None:
        for r in control_report.results:
            for h in r.horizon_stats:
                db.add(BacktestResultRow(
                    experiment_id=experiment_id, variant=ex_value(r.kind), horizon=h.horizon,
                    sample_count=h.sample_count, up_rate=h.up_rate, excess_up_rate=h.excess_up_rate,
                    mean_return=h.mean_return, median_return=h.median_return,
                    std_return=h.std_return, mean_excess_return=h.mean_excess_return,
                    max_drawdown=h.max_drawdown, mean_max_return=h.mean_max_return,
                    extra_json={"verdict": r.verdict, "note": r.verdict_note},
                ))
    db.flush()


@router.get("/labels/{code}", response_model=LabelSet, summary="获取个股未来收益标签")
def get_labels(
    code: str,
    as_of: date | None = Query(None, description="特征基准日"),
    market=Depends(get_market),
) -> LabelSet:
    """计算某只股票在 ``as_of`` 的未来收益标签。

    **这些字段只能作为预测目标（label），绝不能作为 as_of 时刻的输入特征。**
    """
    from src.research.labels.forward_returns import InsufficientForwardData, compute_labels

    as_of_date = as_of or date.today()
    start = date(max(as_of_date.year - 1, 2000), 1, 1)
    end = date(min(as_of_date.year + 1, date.today().year), 12, 31)

    series = market.get_daily_bars(code, start, end)
    try:
        bench = market.get_benchmark_bars(settings.benchmark_index_code, start, end)
    except Exception:  # noqa: BLE001
        bench = None

    try:
        return compute_labels(series, as_of_date, benchmark_series=bench,
                              benchmark_code=settings.benchmark_index_code)
    except InsufficientForwardData as exc:
        raise NotFoundError(str(exc)) from exc


@router.get("/factor-definitions", summary="因子定义列表（研究向）")
def factor_definitions(category: str | None = None) -> dict:
    items = list(DEFINITION_INDEX.values())
    if category:
        items = [d for d in items if str(d.category) == category]
    return {"total": len(items), "items": [d.model_dump(mode="json") for d in items]}


@router.get("/experiments", summary="历史研究实验列表")
def list_experiments(db: Session = Depends(db_session), limit: int = Query(20, ge=1, le=100)) -> dict:
    from sqlalchemy import desc, select

    rows = db.execute(
        select(BacktestExperimentRow).order_by(desc(BacktestExperimentRow.created_at)).limit(limit)
    ).scalars().all()
    return {
        "total": len(rows),
        "items": [
            {
                "experiment_id": r.experiment_id, "kind": r.kind, "name": r.name,
                "factor_ids": r.factor_ids_json, "universe": r.universe_json,
                "created_at": r.created_at.isoformat(), "status": r.status,
            }
            for r in rows
        ],
    }


@router.get("/experiments/{experiment_id}", summary="研究实验详情")
def get_experiment(experiment_id: str, db: Session = Depends(db_session)) -> dict:
    from sqlalchemy import select

    exp = db.get(BacktestExperimentRow, experiment_id)
    if exp is None:
        raise NotFoundError(f"实验不存在: {experiment_id}")
    results = db.execute(
        select(BacktestResultRow).where(BacktestResultRow.experiment_id == experiment_id)
    ).scalars().all()

    grouped: dict[str, list[dict]] = {}
    for r in results:
        grouped.setdefault(r.variant, []).append({
            "horizon": r.horizon, "sample_count": r.sample_count, "up_rate": r.up_rate,
            "mean_return": r.mean_return, "median_return": r.median_return,
            "mean_excess_return": r.mean_excess_return, "max_drawdown": r.max_drawdown,
            "excess_up_rate": r.excess_up_rate, "extra": r.extra_json,
        })

    return {
        "experiment": {
            "experiment_id": exp.experiment_id, "kind": exp.kind, "name": exp.name,
            "factor_ids": exp.factor_ids_json, "universe": exp.universe_json,
            "horizons": exp.horizons_json, "methodology": exp.methodology,
            "seed": exp.seed, "created_at": exp.created_at.isoformat(),
        },
        "results_by_variant": grouped,
    }
