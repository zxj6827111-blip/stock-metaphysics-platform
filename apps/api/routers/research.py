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
    get_market,
)
from apps.api.errors import InvalidRequestError, NotFoundError
from src.core.config import settings
from src.core.orchestration.analysis_service import AnalysisService, direction_from_score
from src.core.orchestration.date_relation_scan import (
    relation_detail,
    scan_market_by_date,
    scope_descriptor,
)
from src.core.relations.date_relation import build_date_relation_fingerprint
from src.core.schemas.common import VariantMode, Warning_
from src.core.schemas.consensus import (
    ConsensusResearchRequest,
    ConsensusResearchResult,
)
from src.core.schemas.market import (
    EventStudyRequest,
    EventStudyResult,
    LabelSet,
    NegativeControlKind,
    NegativeControlReport,
)
from src.core.schemas.relation import (
    RELATION_CATALOG,
    DateRelationFingerprint,
    DateScanRequest,
    DateScanResponse,
    RelationCatalogFactorMeta,
    RelationCatalogGroup,
    RelationCatalogResponse,
)
from src.core.schemas.relation_study import RelationStudyRequest, RelationStudyResponse
from src.core.schemas.stock import BirthProfileCreateRequest, StockBirthProfile
from src.core.stock.birth_profile import build_birth_profile
from src.core.stock.exchange_sessions import ex_value
from src.db.models import BacktestExperimentRow, BacktestResultRow
from src.engines.base import EngineContext
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.engines.huangli.huangli_engine import HuangliEngine
from src.engines.ziwei.ziwei_engine import ZiweiUnavailableError
from src.factors.registry.compute import compute_factor_set
from src.factors.registry.definitions import DEFINITION_INDEX, RELATION_DEFINITION_INDEX
from src.research.pipeline import ResearchPipeline, month_starts, new_experiment_id

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
    #: 研究状态机输出：合成/降级数据时恒为 NO_REAL_DATA（Phase 1.1 P0-1）
    research_status: str = "NOT_RUN"
    research_status_reasons: list[str] = Field(default_factory=list)
    data_source: dict = Field(default_factory=dict)


@router.get(
    "/date-relations/{target_date}",
    response_model=DateRelationFingerprint,
    summary="获取指定日期的关系指纹",
)
def get_date_relation_fingerprint(target_date: date, hour: int | None = Query(None, ge=0, le=23)) -> DateRelationFingerprint:
    """只计算日期模板，不读取股票池。"""
    when = datetime.combine(target_date, datetime.min.time()).replace(hour=hour if hour is not None else 12)
    return build_date_relation_fingerprint(CalendarEngine().snapshot(when))


@router.post(
    "/date-scan",
    response_model=DateScanResponse,
    summary="指定日期×全市场股票关系扫描",
)
def run_date_relation_scan(payload: DateScanRequest, db: Session = Depends(db_session)) -> DateScanResponse:
    try:
        return scan_market_by_date(db, payload)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc


@router.get(
    "/relation-catalog",
    response_model=RelationCatalogResponse,
    summary="关系类型目录（前端唯一来源）",
)
def relation_catalog() -> RelationCatalogResponse:
    """返回后端承认的关系类型全集与关系研究因子元数据。

    前端（择日关系扫描 / 关系历史研究）必须以此构建筛选项，
    不得再维护第二份手写关系清单 —— 那正是「后端能算、下拉选不到」漂移的根因。
    """
    return RelationCatalogResponse(
        relation_rule_version=settings.relation_rule_version,
        relation_matrix_schema_version=settings.relation_matrix_schema_version,
        groups=[RelationCatalogGroup(label=label, items=list(items)) for label, items in RELATION_CATALOG.items()],
        factors={
            factor_id: RelationCatalogFactorMeta(
                factor_id=factor_id,
                name=definition.name,
                definition=definition.definition,
                computation=definition.computation,
                rule_version=definition.rule_version,
            )
            for factor_id, definition in RELATION_DEFINITION_INDEX.items()
        },
    )


@router.post(
    "/relation-study",
    response_model=RelationStudyResponse,
    summary="运行关系类型历史 Event Study",
)
def run_relation_study_endpoint(
    payload: RelationStudyRequest,
    db: Session = Depends(db_session),
    market=Depends(get_market),
) -> RelationStudyResponse:
    """关系结构只作为无方向研究因子，复用既有 Event Study 与负对照。"""
    from src.research.relation_runner import run_relation_study

    try:
        run = run_relation_study(db, market, payload)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    # 因子定义来源（RELATION_DEFINITION_INDEX）：随响应回显，便于审计"这个因子是什么口径"。
    definition = RELATION_DEFINITION_INDEX.get(run.response.factor_id)
    if definition is not None:
        run.response.factor_definition = {
            "factor_id": definition.factor_id,
            "name": definition.name,
            "definition": definition.definition,
            "computation": definition.computation,
            "rule_score_meaning": definition.rule_score_meaning,
            "rule_version": definition.rule_version,
            "tags": list(definition.tags),
        }
    if payload.persist:
        _persist_relation_experiment(db, payload, run)
        db.commit()
    return run.response


@router.get(
    "/date-scan/{scan_id}/stocks/{code}",
    summary="获取单只股票的 3×3 日期关系矩阵与流日判定",
)
def get_date_relation_detail(
    scan_id: str,
    code: str,
    target_date: date = Query(..., description="扫描日期"),
    universe: str = Query("v4-full"),
    birth_basis: str = Query("listing_open"),
    birth_profile_version: str = Query("v2-phase4b-listing_open"),
    relation_rule_version: str = Query(None, description="缺省取 settings.relation_rule_version"),
    db: Session = Depends(db_session),
) -> dict:
    """返回 3×3 矩阵（流年/月/日 × 股票年/月/日）与 day_stem_verdict。

    scan_id 用于审计，参数仍显式重建口径；矩阵目标列不含股票时柱，
    但喜用神结论来自完整四柱原局。
    """
    request = DateScanRequest(
        date=target_date,
        universe=universe,
        birth_basis=birth_basis,
        birth_profile_version=birth_profile_version,
        relation_rule_version=relation_rule_version or settings.relation_rule_version,
        limit=1,
    )
    try:
        row = relation_detail(db, request, code)
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    return {
        "scan_id": scan_id,
        "target_date": target_date,
        "scope": scope_descriptor().model_dump(mode="json"),
        "versions": {
            "relation_rule_version": settings.relation_rule_version,
            "relation_matrix_schema_version": settings.relation_matrix_schema_version,
            "fingerprint_version": settings.relation_fingerprint_version,
            "bazi_engine_version": settings.bazi_engine_version,
            "calendar_engine_version": settings.calendar_engine_version,
        },
        "row": row.model_dump(mode="json", by_alias=True),
    }


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

    from src.research.labels.forward_returns import compute_labels

    started = _time.perf_counter()
    warnings: list[Warning_] = []
    pipeline = ResearchPipeline(backtest)

    date_from = payload.date_from or date.fromisoformat(settings.market_history_start)
    date_to = payload.date_to or date.today()
    sample_dates = month_starts(date_from, date_to, step_months=payload.sample_step_months)[-24:]
    if not sample_dates:
        raise InvalidRequestError("采样日期为空，请检查 date_from / date_to")

    # --- 行情与标签 ---
    # 记录每只序列的降级状态：合成/降级行情不得产出"研究证据"（P0-1）
    series_cache: dict[str, object] = {}
    series_meta: dict[str, dict] = {}
    computed_label_objs: list = []

    bench = None
    bench_meta = {"is_degraded": False, "source": ""}
    try:
        bench = market.get_benchmark_bars(settings.benchmark_index_code, date_from, date_to)
        bench_meta = {
            "is_degraded": bool(getattr(bench, "is_degraded", False)),
            "source": str(getattr(getattr(bench, "source_ref", None), "source", "") or ""),
        }
    except Exception as exc:  # noqa: BLE001
        warnings.append(Warning_(
            code="RESEARCH_BENCHMARK_UNAVAILABLE",
            message=f"基准指数不可用，超额收益将为空：{type(exc).__name__}: {exc}",
            severity="warning",
        ))

    def label_builder(code: str, as_of_date: date):
        if code not in series_cache:
            series_cache[code] = market.get_daily_bars(code, date_from, date_to)
            s = series_cache[code]
            series_meta[code] = {
                "is_degraded": bool(getattr(s, "is_degraded", False)),
                "source": str(getattr(getattr(s, "source_ref", None), "source", "") or ""),
            }
        series = series_cache[code]
        labels = compute_labels(series, as_of_date, benchmark_series=bench,  # type: ignore[arg-type]
                                benchmark_code=settings.benchmark_index_code)
        computed_label_objs.append(labels)
        return labels

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

    # --- P0-1：研究状态机判定（合成/降级数据 → NO_REAL_DATA，禁止产出有效性语义） ---
    from src.research.status import assess_research_status

    degraded_codes = sorted([c for c, m in series_meta.items() if m["is_degraded"]])
    if bench_meta["is_degraded"]:
        degraded_codes.append(f"benchmark:{settings.benchmark_index_code}")
    data_is_real = not degraded_codes
    if not data_is_real:
        warnings.append(Warning_(
            code="RESEARCH_DATA_UNAVAILABLE",
            message=(
                "本次运行的行情为合成或降级数据（"
                + ", ".join(degraded_codes[:10])
                + ("..." if len(degraded_codes) > 10 else "")
                + "）。所有统计仅用于系统联调，不构成任何历史有效性证据。"
            ),
            severity="error",
        ))

    assessment = assess_research_status(
        real_result, control_report,
        data_is_real=data_is_real,
        data_problems=[f"降级/合成来源: {c}" for c in degraded_codes[:20]],
    )
    real_result.research_status = assessment.status.value
    real_result.research_status_reasons = assessment.reasons
    real_result.data_source = {
        "provider": getattr(market, "provider_id", ""),
        "is_real": data_is_real,
        "degraded_codes": degraded_codes,
        "benchmark_degraded": bool(bench_meta["is_degraded"]),
    }

    if payload.persist:
        # 标签写穿透（含数据来源与降级标记；合成数据的标签会被打上 is_degraded=True）
        # 注意：四个面板（真实 + 三类对照）会重复计算同一批标签，先去重再写库。
        from src.research.labels.store import upsert_label

        unique_labels = {
            (lab.stock_code, lab.as_of, lab.benchmark_code, lab.data_source): lab
            for lab in computed_label_objs
        }
        for lab in unique_labels.values():
            upsert_label(db, lab)
        _persist_experiment(
            db, experiment_id, payload, real_result, control_report, observations,
            status=assessment.status.value,
        )
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
        research_status=assessment.status.value,
        research_status_reasons=assessment.reasons,
        data_source=real_result.data_source or {},
    )


def _persist_relation_experiment(db: Session, payload: RelationStudyRequest, run) -> None:
    """将关系研究摘要写入通用实验表，供历史实验页复用。"""
    from src.db.models import BacktestExperimentRow, BacktestResultRow
    from src.research.status import ResearchStatus

    factor_id = run.response.factor_id
    first_status = run.response.splits[0].research_status if run.response.splits else ResearchStatus.NOT_RUN.value
    exp = db.get(BacktestExperimentRow, run.response.experiment_id)
    if exp is None:
        db.add(BacktestExperimentRow(
            experiment_id=run.response.experiment_id,
            kind="relation_event_study",
            name=f"关系研究 {payload.relation_type} × {','.join(str(h) for h in payload.horizons)}D",
            factor_ids_json=[factor_id],
            logic="any",
            universe_json=payload.stock_codes or [payload.universe],
            horizons_json=payload.horizons,
            date_from=run.response.date_from,
            date_to=run.response.date_to,
            benchmark_code=settings.benchmark_index_code,
            params_json={
                "relation_type": payload.relation_type,
                "universe_version": payload.universe,
                "direction": 0,
                "splits": [split.model_dump(mode="json") for split in run.response.splits],
                "data_source": run.response.data_source,
                # v3 口径登记：以后必须能区分"这个实验是按 3×4 老关系还是 3×3 day-only 新关系跑的"。
                "relation_rule_version": run.response.relation_rule_version,
                "relation_matrix_schema_version": run.response.relation_matrix_schema_version,
                "aggregate_scope": run.response.aggregate_scope,
                "matrix_target_scope": run.response.matrix_target_scope,
                "yongshen_basis": run.response.yongshen_basis,
                "evaluation_time": run.response.evaluation_time,
                "timezone": run.response.timezone,
                "multiplicity_scope": run.response.multiplicity_scope,
                "p_value_control_kind": run.response.p_value_control_kind,
                "sample_step_months": payload.sample_step_months,
                "stock_scope": "full_universe" if not payload.stock_codes else "explicit_stock_codes",
                "stock_codes": list(payload.stock_codes),
                "run_negative_controls": payload.run_negative_controls,
            },
            methodology=run.response.methodology,
            seed=settings.negative_control_seed,
            status=first_status,
        ))
    for split in run.response.splits:
        for stat in split.horizons:
            db.add(BacktestResultRow(
                experiment_id=run.response.experiment_id,
                variant=split.name.lower(),
                horizon=stat.horizon,
                sample_count=stat.sample_count,
                up_rate=stat.up_rate,
                mean_return=stat.mean_return,
                median_return=stat.median_return,
                mean_excess_return=stat.mean_excess_return,
                max_drawdown=stat.max_drawdown,
                extra_json={
                    "relation_type": payload.relation_type,
                    "p_value": stat.p_value,
                    "q_value": stat.q_value,
                    "control_mean_return": stat.control_mean_return,
                    "control_up_rate": stat.control_up_rate,
                    "research_status": split.research_status,
                },
            ))
    db.flush()


def _persist_experiment(db: Session, experiment_id: str, payload: ResearchRunRequest,
                        real_result, control_report, observations, *,
                        status: str = "completed") -> None:
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
            # 状态直接反映研究可信度（如 NO_REAL_DATA），拒绝把降级数据标成 completed
            status=status,
        ))

    for h in real_result.horizons:
        db.add(BacktestResultRow(
            experiment_id=experiment_id, variant="real", horizon=h.horizon,
            sample_count=h.sample_count, up_rate=h.up_rate, excess_up_rate=h.excess_up_rate,
            mean_return=h.mean_return, median_return=h.median_return, std_return=h.std_return,
            mean_excess_return=h.mean_excess_return, max_drawdown=h.max_drawdown,
            mean_max_return=h.mean_max_return,
            extra_json={"note": h.note, "research_status": status},
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
                    extra_json={
                        "verdict": r.verdict, "note": r.verdict_note,
                        "research_status": status,
                        "jaccard_with_real": r.jaccard_with_real,
                        "overlap_with_real": r.overlap_with_real,
                        "event_count": r.event_count,
                    },
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

    from src.core.stock import codes as _codes

    try:
        normalized = _codes.normalize_code(code)
    except ValueError as exc:
        raise InvalidRequestError(f"无法解析股票代码: {code!r}") from exc

    series = market.get_daily_bars(normalized, start, end)
    try:
        bench = market.get_benchmark_bars(settings.benchmark_index_code, start, end)
    except Exception:  # noqa: BLE001
        bench = None

    try:
        return compute_labels(series, as_of_date, benchmark_series=bench,
                              benchmark_code=settings.benchmark_index_code)
    except InsufficientForwardData as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc


@router.get("/factor-definitions", summary="因子定义列表（研究向）")
def factor_definitions(category: str | None = None) -> dict:
    items = list(DEFINITION_INDEX.values())
    if category:
        items = [d for d in items if str(d.category) == category]
    return {"total": len(items), "items": [d.model_dump(mode="json") for d in items]}


@router.get("/experiments", summary="历史研究实验列表")
def list_experiments(
    db: Session = Depends(db_session),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    kind: str | None = Query(None),
    status: str | None = Query(None),
    sort: str = Query("created_at", pattern="^(created_at|kind|status)$"),
) -> dict:
    from sqlalchemy import desc, func, select

    query = select(BacktestExperimentRow)
    count_query = select(func.count()).select_from(BacktestExperimentRow)
    if kind:
        query = query.where(BacktestExperimentRow.kind == kind)
        count_query = count_query.where(BacktestExperimentRow.kind == kind)
    if status:
        query = query.where(BacktestExperimentRow.status == status)
        count_query = count_query.where(BacktestExperimentRow.status == status)
    order_column = getattr(BacktestExperimentRow, sort)
    rows = db.execute(query.order_by(desc(order_column)).offset(offset).limit(limit)).scalars().all()
    total = int(db.execute(count_query).scalar_one())
    return {
        "total": total,
        "filtered_count": total,
        "returned_count": len(rows),
        "query": {"limit": limit, "offset": offset, "kind": kind, "status": status, "sort": sort},
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
            "status": exp.status, "date_from": exp.date_from.isoformat() if exp.date_from else None,
            "date_to": exp.date_to.isoformat() if exp.date_to else None,
            "benchmark_code": exp.benchmark_code, "params": exp.params_json or {},
        },
        "results_by_variant": grouped,
    }


# ---------------------------------------------------------------------------
# 多模型共振 / 冲突研究（Phase 2C）
# ---------------------------------------------------------------------------


@router.post(
    "/consensus",
    response_model=ConsensusResearchResult,
    summary="多模型共振 / 冲突的历史研究（含独立负对照 + 多重比较警告）",
)
def run_consensus_research_endpoint(
    payload: ConsensusResearchRequest,
    db: Session = Depends(db_session),
    market=Depends(get_market),
    service: AnalysisService = Depends(get_analysis_service),
) -> ConsensusResearchResult:
    """研究「三模型共振 / 冲突」在真实历史数据上是否有统计支持。

    **纪律**

    * 只允许研究**预定义**的组合（见 `src/core/schemas/consensus.py`），
      不支持自由组合搜索（数据挖掘防护）；
    * 共振必须与**随机模型方向**对照 —— "三个模型都说好"本身不是证据；
    * 组合数超过阈值时产出多重比较警告（含 Bonferroni 参考阈值）；
    * 结论以 `ResearchStatus` 状态机输出，`NO_SIGNAL` 是合法且常见的结果。
    """
    import time as _time

    from src.core.schemas.consensus import ConsensusResearchRequest  # noqa: F401
    from src.research.consensus_research import (
        build_consensus_panel,
        month_sample_dates,
        run_consensus_research,
    )
    from src.research.labels.forward_returns import compute_labels

    started = _time.perf_counter()
    warnings: list[Warning_] = []

    universe = payload.universe or DEFAULT_UNIVERSE[:6]
    sample_dates = month_sample_dates(
        payload.date_from, payload.date_to, payload.sample_step_months,
    )
    if not sample_dates:
        raise InvalidRequestError("采样日期区间为空，请检查 date_from / date_to。")

    date_from = date.fromisoformat(payload.date_from)
    date_to = date.fromisoformat(payload.date_to)
    horizon = payload.horizon

    bazi = BaziEngine()
    huangli = HuangliEngine()
    variant = VariantMode(payload.variant_mode)
    profile_cache: dict[str, StockBirthProfile] = {}
    series_cache: dict[str, object] = {}
    huangli_cache: dict[str, object] = {}
    degraded_codes: set[str] = set()

    try:
        bench = market.get_benchmark_bars(settings.benchmark_index_code, date_from, date_to)
    except Exception as exc:  # noqa: BLE001
        bench = None
        warnings.append(Warning_(
            code="RESEARCH_BENCHMARK_UNAVAILABLE",
            message=f"基准指数不可用，超额收益将为空：{type(exc).__name__}: {exc}",
            severity="warning",
        ))

    def opinion_builder(code: str, as_of_date: date):
        """该时刻的三模型方向（只读 as_of 及之前的盘面）。"""
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 0, 0)
        if code not in profile_cache:
            profile_cache[code] = build_birth_profile(
                market.get_stock(code), BirthProfileCreateRequest(variant_mode=variant),
            )
        profile = profile_cache[code]

        hl_key = as_of_date.isoformat()
        hl = huangli_cache.get(hl_key)
        if hl is None:
            hl = huangli.snapshot(as_of, days=31)
            huangli_cache[hl_key] = hl

        chart = bazi.build_chart(
            birth_datetime=profile.birth_datetime.replace(tzinfo=None),
            as_of=as_of, variant_mode=variant, stock_code=code,
        )

        ziwei_chart = None
        try:
            ziwei_chart = service.ziwei.calculate_chart(
                EngineContext(stock_code=code, as_of=as_of),
                birth_datetime=profile.birth_datetime.replace(tzinfo=None),
                as_of=as_of, variant_mode=variant,
            )
        except ZiweiUnavailableError as exc:
            warnings.append(Warning_(
                code="CONSENSUS_ZIWEI_UNAVAILABLE",
                message=f"{code}@{as_of_date} 紫微不可用：{exc}",
                severity="warning",
            ))

        fset = compute_factor_set(
            chart, hl, as_of, stock_code=code, ziwei_chart=ziwei_chart,  # type: ignore[arg-type]
        )
        dirs: dict[str, int] = {}
        for engine, prefix in (
            ("bazi", "B_"), ("huangli", "H_"), ("ziwei", "Z_"),
        ):
            obs = [
                o for o in fset.observations
                if o.factor_id.startswith(prefix) and o.availability == "ok"
            ]
            if not obs:
                continue
            weights = [max(o.confidence, 1e-6) for o in obs]
            vals = [o.normalized_value or 0.0 for o in obs]
            wsum = sum(weights)
            raw = sum(v * w for v, w in zip(vals, weights, strict=True)) / wsum if wsum else 0.0
            score = max(0.0, min(100.0, 50.0 + raw * 50.0))
            dirs[engine] = direction_from_score(score)
        return dirs

    def label_builder(code: str, as_of_date: date):
        if code not in series_cache:
            series = market.get_daily_bars(code, date_from, date_to)
            series_cache[code] = series
            if bool(getattr(series, "is_degraded", False)):
                degraded_codes.add(code)
        return compute_labels(
            series_cache[code], as_of_date,  # type: ignore[arg-type]
            benchmark_series=bench, benchmark_code=settings.benchmark_index_code,
        )

    panel, directions = build_consensus_panel(
        stocks=universe, sample_dates=sample_dates,
        opinion_builder=opinion_builder, label_builder=label_builder, warnings=warnings,
    )

    result = run_consensus_research(
        panel=panel, directions=directions, request=payload, warnings=warnings,
        data_source={
            "rows": int(len(panel)),
            "universes": len(universe),
            "sample_dates": len(sample_dates),
            "degraded_codes": sorted(degraded_codes),
            "is_real": not degraded_codes,
            "market_provider": getattr(market, "provider_id", ""),
            "variant_mode": payload.variant_mode,
            "horizon": horizon,
        },
    )

    if degraded_codes:
        result.overall_research_status = "NO_REAL_DATA"
        result.overall_reasons = [
            "样本中含合成或降级行情来源，本结果仅用于系统联调，不构成任何历史有效性证据。"
        ]
        result.warnings.append(Warning_(
            code="RESEARCH_DATA_UNAVAILABLE",
            message=f"以下股票使用合成/降级行情：{', '.join(sorted(degraded_codes))}",
            severity="error",
        ))

    if payload.persist:
        db.commit()
    result.methodology += f"  组合数 {len(result.combos)}，参数数 {result.multiple_testing.parameter_count}。"
    _ = started
    return result
