"""W5 版本化研究 API；v1 路由及其响应保持不变。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.api.deps import db_session, get_market
from apps.api.errors import EngineUnavailableError, InvalidRequestError, NotFoundError
from src.core.config import settings
from src.core.fortune.birth import resolve_market_first_trade_profile
from src.core.orchestration.stock_fortune import (
    DatabaseFortuneChartArtifactWriter,
    StockFortuneEngine,
)
from src.core.orchestration.stock_fortune_scan import StockFortuneCrossSectionScanner
from src.core.orchestration.stock_fortune_timeline import StockFortuneTimelineEngine
from src.core.schemas.common import SourceRef
from src.core.schemas.fortune import (
    FortuneScanTemporalMode,
    StockFortuneBirthProfile,
    StockFortuneIdentity,
    StockFortuneScanRequest,
    StockFortuneScanTarget,
    StockFortuneScanUniverse,
    StockFortuneTimelineRequest,
)
from src.core.schemas.research_v2 import (
    ExperimentReportV2Response,
    FortuneScanV2Request,
    FortuneScanV2Response,
    FortuneTimelineV2Request,
    FortuneTimelineV2Response,
    HistoricalDatasetV2Response,
    HistoricalEventStudyV2Request,
    HistoricalEventStudyV2Response,
)
from src.market.providers.fortune_first_trade import DailyBarFirstTradeProvider
from src.research.historical_dataset_event_study import (
    get_historical_dataset_v2,
    read_experiment_report,
    run_historical_event_study_v2,
)
from src.research.universe.point_in_time import PointInTimeUniverse
from src.research.universe.snapshot_metadata import resolve_universe_evidence_as_of

router = APIRouter(prefix="/api/v2/research", tags=["research-v2"])
_MAX_SCAN_MEMBERS = 5000


def _market_version(market) -> str:
    provider_id = str(getattr(market, "provider_id", "unknown") or "unknown")
    try:
        descriptor = market.status_descriptor()
    except Exception:  # noqa: BLE001 - 状态读取失败不能伪造可信版本
        descriptor = {}
    version = descriptor.get("data_version") if isinstance(descriptor, dict) else None
    if version and str(version).strip().lower() not in {"", "unknown", "unavailable"}:
        return str(version).strip()
    configured_version = str(settings.market_data_version or "unknown").strip()
    return f"{provider_id}:{configured_version}"


def _resolve_identity_and_birth_profile(
    stock_code: str,
    market,
    *,
    config_version: str,
    market_session_version: str,
) -> tuple[StockFortuneIdentity, StockFortuneBirthProfile, str]:
    if config_version != settings.config_version:
        raise InvalidRequestError(
            "请求 config_version 与当前实例配置不一致",
            detail=f"requested={config_version}; active={settings.config_version}",
        )
    stock = market.get_stock(stock_code)
    market_data_version = _market_version(market)
    first_trade = DailyBarFirstTradeProvider(
        market, source_version=market_data_version,
    ).observe_first_trade(stock.stock_code)
    birth_profile = resolve_market_first_trade_profile(
        symbol=stock.stock_code,
        exchange=stock.exchange,
        observation=first_trade,
        listing_date=stock.listing_date,
        config_version=config_version,
        market_session_version=market_session_version,
    )
    identity = StockFortuneIdentity(
        symbol=stock.stock_code,
        exchange=stock.exchange,
        name=stock.name,
        source=stock.source,
        source_version=market_data_version,
    )
    return identity, birth_profile, market_data_version


@router.post(
    "/fortune/timeline",
    response_model=FortuneTimelineV2Response,
    summary="按证券代码与日期服务端解析 Fortune 时间轴（v2）",
)
def stock_fortune_timeline_v2(
    payload: FortuneTimelineV2Request,
    db: Session = Depends(db_session),
    market=Depends(get_market),
) -> FortuneTimelineV2Response:
    try:
        identity, birth_profile, market_data_version = _resolve_identity_and_birth_profile(
            payload.stock_code,
            market,
            config_version=payload.config_version,
            market_session_version=payload.market_session_version,
        )
        request = StockFortuneTimelineRequest(
            stock_identity=identity,
            birth_profile=birth_profile,
            start_date=payload.start_date,
            end_date=payload.end_date,
            date_mode=payload.date_mode,
            anchor_mode=payload.anchor_mode,
            evaluation_time=payload.evaluation_time,
            timezone=payload.timezone,
            evaluation_source=SourceRef(
                source=f"market-provider:{getattr(market, 'provider_id', 'unknown')}"
            ),
            evaluation_source_version="research-api-v2",
            market_session_version=payload.market_session_version,
            config_version=payload.config_version,
            ten_god_filters=payload.ten_god_filters,
            relation_filters=payload.relation_filters,
            include_relation_events=payload.include_relation_events,
            include_month_segments=payload.include_month_segments,
            include_ten_god_index=payload.include_ten_god_index,
        )
        result = StockFortuneTimelineEngine(
            StockFortuneEngine(DatabaseFortuneChartArtifactWriter(db))
        ).build(request)
        db.commit()
        return FortuneTimelineV2Response(
            resolved_versions={
                "market_data_version": market_data_version,
                "birth_profile_version": birth_profile.birth_profile_version,
                "birth_rule_version": birth_profile.rule_version,
                "market_session_version": birth_profile.market_session_version or payload.market_session_version,
                "config_version": payload.config_version,
            },
            timeline=result,
        )
    except ValueError as exc:
        db.rollback()
        raise InvalidRequestError(str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post(
    "/fortune/scan",
    response_model=FortuneScanV2Response,
    summary="从服务端 PIT universe 扫描 Fortune 条件（v2）",
)
def stock_fortune_scan_v2(
    payload: FortuneScanV2Request,
    db: Session = Depends(db_session),
    market=Depends(get_market),
) -> FortuneScanV2Response:
    if payload.config_version != settings.config_version:
        raise InvalidRequestError(
            "请求 config_version 与当前实例配置不一致",
            detail=f"requested={payload.config_version}; active={settings.config_version}",
        )

    evidence = resolve_universe_evidence_as_of(db, payload.universe_version)
    if not evidence.available or evidence.as_of is None:
        raise InvalidRequestError(
            "universe 缺少可核验的点时来源证据",
            detail=evidence.detail,
        )
    if payload.evaluation_date > evidence.as_of:
        raise InvalidRequestError(
            "evaluation_date 超出 universe 证据截止日",
            detail=f"evidence_as_of={evidence.as_of.isoformat()}",
        )

    universe = PointInTimeUniverse.load(
        db, payload.universe_version, snapshot_at=payload.evaluation_date,
    )
    snapshot = universe.at_exclusive_delist(payload.evaluation_date)
    if not snapshot.member_codes:
        raise InvalidRequestError("所选 universe/date 没有符合 PIT v2 的成员")
    if len(snapshot.member_codes) > _MAX_SCAN_MEMBERS:
        raise InvalidRequestError(
            "PIT universe 成员超过单次 Fortune 扫描上限",
            detail=f"member_count={len(snapshot.member_codes)}; max={_MAX_SCAN_MEMBERS}",
        )

    targets: list[StockFortuneScanTarget] = []
    unresolved_codes: list[str] = []
    for code in snapshot.member_codes:
        try:
            identity, profile, _ = _resolve_identity_and_birth_profile(
                code,
                market,
                config_version=payload.config_version,
                market_session_version=payload.market_session_version,
            )
        except Exception:  # noqa: BLE001 - 不静默缩小 universe
            unresolved_codes.append(code)
            continue
        targets.append(StockFortuneScanTarget(
            stock_identity=identity,
            birth_profile=profile,
        ))
    if unresolved_codes:
        raise EngineUnavailableError(
            "PIT universe 中部分证券资料或首日观测不可用，扫描未执行",
            detail=f"unresolved_count={len(unresolved_codes)}; sample={unresolved_codes[:10]}",
        )

    f4_request = StockFortuneScanRequest(
        temporal_mode=FortuneScanTemporalMode.DATE_SCAN_NOON,
        evaluation_date=payload.evaluation_date,
        universe=StockFortuneScanUniverse(
            version=payload.universe_version,
            source=SourceRef(
                source=evidence.source,
                extra={
                    "evidence_as_of": evidence.as_of.isoformat(),
                    "membership_digest": snapshot.digest,
                    "pit_rule_version": "pit-list-inclusive-delist-exclusive-v2",
                },
            ),
            targets=targets,
        ),
        ten_god_filters=payload.ten_god_filters,
        relation_filters=payload.relation_filters,
        availability_policy=payload.availability_policy,
        sort=payload.sort,
        limit=payload.limit,
        offset=payload.offset,
        market_session_version=payload.market_session_version,
        config_version=payload.config_version,
    )
    try:
        result = StockFortuneCrossSectionScanner(
            DatabaseFortuneChartArtifactWriter(db)
        ).scan(f4_request)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise InvalidRequestError(str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return FortuneScanV2Response(
        pit_evidence={
            "universe_version": payload.universe_version,
            "evidence_available": evidence.available,
            "evidence_as_of": evidence.as_of,
            "evidence_source": evidence.source,
            "evidence_detail": evidence.detail,
            "snapshot_date": payload.evaluation_date,
            "snapshot_digest": snapshot.digest,
            "member_count": len(snapshot.member_codes),
        },
        scan=result,
    )


@router.post(
    "/event-study",
    response_model=HistoricalEventStudyV2Response,
    summary="按 W4 dataset、明确条件與版本查询历史事件（v2）",
)
def historical_event_study_v2(
    payload: HistoricalEventStudyV2Request,
) -> HistoricalEventStudyV2Response:
    try:
        return run_historical_event_study_v2(
            settings.data_dir / "research_datasets",
            payload,
            minimum_sample=settings.min_event_sample_size,
        )
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 不向客户端泄漏本地路径或 SQL
        raise EngineUnavailableError(
            "历史数据集查询失败",
            detail=type(exc).__name__,
        ) from exc


@router.get(
    "/datasets/{dataset_id}",
    response_model=HistoricalDatasetV2Response,
    summary="读取 W4 历史数据集 provenance 与认证范围（v2）",
)
def historical_dataset_v2(dataset_id: str) -> HistoricalDatasetV2Response:
    try:
        return get_historical_dataset_v2(settings.data_dir / "research_datasets", dataset_id)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 本地文件/Parquet 损坏统一安全失败
        raise EngineUnavailableError("历史数据集 manifest 或分片不可用", detail=type(exc).__name__) from exc


@router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentReportV2Response,
    summary="读取 W6 版本化实验报告（v2）",
)
def research_experiment_v2(experiment_id: str) -> ExperimentReportV2Response:
    try:
        report, digest = read_experiment_report(settings.data_dir, experiment_id)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidRequestError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - 避免把本机路径返回调用方
        raise EngineUnavailableError("实验报告文件不可用", detail=type(exc).__name__) from exc
    return ExperimentReportV2Response(
        experiment_id=experiment_id,
        report_digest=digest,
        report=report,
    )


__all__ = ["router"]
