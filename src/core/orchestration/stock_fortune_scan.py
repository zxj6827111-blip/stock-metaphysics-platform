"""F4 日期 → 显式股票集合的 Fortune 横截面扫描。"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.fortune.ports import CalendarSnapshotProvider, FortuneChartArtifactWriter
from src.core.schemas.common import Warning_
from src.core.schemas.fortune import (
    FortuneAvailability,
    FortuneRelationScope,
    FortuneScanAvailabilityPolicy,
    FortuneScanSort,
    FortuneScanTemporalMode,
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    FortuneTenGodFilter,
    FortuneTenGodLayer,
    StockFortuneEvaluationRequest,
    StockFortuneMatchedCondition,
    StockFortuneScanItem,
    StockFortuneScanRequest,
    StockFortuneScanResponse,
    StockFortuneScanRuleVersions,
)
from src.core.orchestration.stock_fortune import StockFortuneEngine
from src.core.orchestration.stock_fortune_timeline import (
    StockFortuneTimelineEngine,
)
from src.core.stock.trading_calendar import (
    KNOWN_SOURCES,
    TradingCalendarProvider,
    get_trading_calendar_provider,
)
from src.engines.calendar.calendar_engine import CalendarEngine


class RequestScopedCalendarSnapshotCache:
    """同一扫描请求中，同一日期/时刻只构造一个 CalendarSnapshot。"""

    def __init__(self, provider: CalendarSnapshotProvider) -> None:
        self.provider = provider
        self._evaluation_snapshots = {}
        self._recent_snapshots: OrderedDict[datetime, object] = OrderedDict()
        self._capture_next_snapshot = False
        self._recent_limit = 128
        self.calls = 0

    def begin_request(self) -> None:
        """把日历快照缓存限制在单次扫描请求内。"""
        self._evaluation_snapshots.clear()
        self._recent_snapshots.clear()
        self._capture_next_snapshot = False
        self.calls = 0

    def begin_evaluation(self) -> None:
        """下一次快照调用是本次扫描的日期上下文，应在请求期间固定复用。"""
        self._capture_next_snapshot = True

    def snapshot(self, when: datetime):
        key = when.replace(tzinfo=None) if when.tzinfo is not None else when
        if key in self._evaluation_snapshots:
            self._capture_next_snapshot = False
            return self._evaluation_snapshots[key]
        if key in self._recent_snapshots:
            cached = self._recent_snapshots.pop(key)
            if self._capture_next_snapshot:
                self._evaluation_snapshots[key] = cached
                self._capture_next_snapshot = False
            else:
                self._recent_snapshots[key] = cached
            return cached

        snapshot = self.provider.snapshot(key)
        self.calls += 1
        if self._capture_next_snapshot:
            self._evaluation_snapshots[key] = snapshot
            self._capture_next_snapshot = False
        else:
            self._recent_snapshots[key] = snapshot
            while len(self._recent_snapshots) > self._recent_limit:
                self._recent_snapshots.popitem(last=False)
        return snapshot


class StockFortuneCrossSectionScanner:
    def __init__(
        self,
        artifact_writer: FortuneChartArtifactWriter,
        *,
        calendar: CalendarSnapshotProvider | None = None,
        bazi=None,
        trading_calendar_provider: TradingCalendarProvider | None = None,
    ) -> None:
        self.calendar_cache = RequestScopedCalendarSnapshotCache(calendar or CalendarEngine())
        self.snapshot_engine = StockFortuneEngine(
            artifact_writer,
            calendar=self.calendar_cache,
            bazi=bazi,
        )
        self.trading_calendar_provider = (
            trading_calendar_provider or get_trading_calendar_provider()
        )

    def scan(self, request: StockFortuneScanRequest) -> StockFortuneScanResponse:
        self.calendar_cache.begin_request()
        trading_calendar_source = None
        trading_calendar_version = None
        if request.temporal_mode == FortuneScanTemporalMode.MARKET_SESSION_DATE:
            assert request.evaluation_date is not None and request.exchange is not None
            trading_calendar = self.trading_calendar_provider.for_exchange(
                getattr(request.exchange, "value", request.exchange)
            )
            trading_day = trading_calendar.is_trading_day(request.evaluation_date)
            if trading_day.source not in KNOWN_SOURCES or trading_day.value is not True:
                raise ValueError(
                    "MARKET_SESSION_DATE 必须由已加载的实测/官方日历确认是交易日；"
                    f"当前 source={trading_day.source}, value={trading_day.value}"
                )
            trading_calendar_source = trading_day.source
            trading_calendar_version = trading_calendar.version_token
        items: list[StockFortuneScanItem] = []
        total_examined = 0
        unavailable_count = 0
        evaluation_context = None
        version_paths = {
            "snapshot_rule_versions": "snapshot_rule_version",
            "birth_profile_versions": "birth_profile_version",
            "birth_rule_versions": "birth_rule_version",
            "calendar_engine_versions": "calendar_engine_version",
            "bazi_engine_versions": "bazi_engine_version",
            "luck_cycle_rule_versions": "luck_cycle_direction_rule_version",
            "ten_god_rule_versions": "ten_god_rule_version",
            "relation_rule_versions": "relation_rule_version",
            "config_versions": "config_version",
        }
        version_values = {field: set() for field in version_paths}
        for target in request.universe.targets:
            context = self._temporal_input(request, target)
            evaluation = StockFortuneEvaluationRequest(
                stock_identity=target.stock_identity,
                birth_profile=target.birth_profile,
                evaluation_context=context,
                evaluation_source=request.universe.source,
                evaluation_source_version=request.universe.version,
                luck_cycle_evidence=target.luck_cycle_evidence,
                market_session_version=(
                    request.market_session_version or target.birth_profile.market_session_version
                ),
                config_version=request.config_version or target.birth_profile.config_version,
            )
            self.calendar_cache.begin_evaluation()
            snapshot = self.snapshot_engine.evaluate(evaluation)
            total_examined += 1
            if evaluation_context is None:
                evaluation_context = snapshot.temporal_resolution
            for field, path in version_paths.items():
                version_values[field].add(str(getattr(snapshot.rule_versions, path)))
            if snapshot.availability != FortuneAvailability.AVAILABLE:
                unavailable_count += 1
            if (
                request.availability_policy == FortuneScanAvailabilityPolicy.AVAILABLE_ONLY
                and snapshot.availability != FortuneAvailability.AVAILABLE
            ):
                continue
            matched = self._matched_conditions(snapshot, request)
            if matched is None:
                continue
            relation_events = [
                event
                for event in snapshot.relation_context.events
                if event.scope == FortuneRelationScope.TEMPORAL_TO_NATAL
            ]
            if request.relation_filters:
                relation_events = [
                    event
                    for event in relation_events
                    if any(
                        StockFortuneTimelineEngine._matches_relation(event, condition)
                        for condition in request.relation_filters
                    )
                ]
            items.append(
                StockFortuneScanItem(
                    symbol=target.stock_identity.symbol,
                    name=target.stock_identity.name,
                    matched_conditions=matched,
                    annual_ten_god=self._label(snapshot.ten_god_context.annual),
                    monthly_ten_god=self._label(snapshot.ten_god_context.monthly),
                    daily_ten_god=self._label(snapshot.ten_god_context.daily),
                    relevant_relation_events=relation_events,
                    availability=snapshot.availability,
                    snapshot_ref=(snapshot.chart_artifact_ids[-1] if snapshot.chart_artifact_ids else None),
                    rule_versions=snapshot.rule_versions,
                )
            )

        sort = getattr(request.sort, "value", request.sort)
        if sort == FortuneScanSort.MATCHED_CONDITION_COUNT.value:
            items.sort(key=lambda item: (-len(item.matched_conditions), item.symbol))
        elif sort == FortuneScanSort.RELATION_EVENT_COUNT.value:
            items.sort(key=lambda item: (-len(item.relevant_relation_events), item.symbol))
        else:
            items.sort(key=lambda item: item.symbol)

        total_matched = len(items)
        page = items[request.offset : request.offset + request.limit]
        warnings = [
            Warning_(
                code="FORTUNE_SCAN_UNIVERSE_CALLER_SUPPLIED",
                message=(
                    "扫描只验证请求内显式证券集合及其版本摘要；调用方须提供与研究日期相符的"
                    "点时样本，当前接口不独立证明历史成分股资格。"
                ),
                severity="warning",
            ),
            Warning_(
                code="FORTUNE_SCAN_STRUCTURAL_FILTER",
                message=(
                    "扫描条件只筛选确定性术数结构；排序是研究结果排序，不是收益排序，"
                    "结果不构成推荐或交易信号。"
                ),
                severity="info",
            )
        ]
        if unavailable_count:
            warnings.append(
                Warning_(
                    code="FORTUNE_SCAN_PARTIAL_STOCK_CONTEXT",
                    message=(
                    f"{unavailable_count} / {total_examined} 只证券的 Snapshot 为 partial/unavailable；"
                        "不可用字段保持 null/unavailable，不作为十神或关系筛选命中。"
                    ),
                    severity="warning",
                )
            )
        if trading_calendar_source:
            warnings.append(
                Warning_(
                    code="FORTUNE_SCAN_TRADING_CALENDAR_VERIFIED",
                    message=(
                        "MARKET_SESSION_DATE 已由正式交易日历确认；"
                        f"source={trading_calendar_source}，version={trading_calendar_version}。"
                    ),
                    severity="info",
                )
            )
        if sort != FortuneScanSort.SYMBOL.value:
            warnings.append(
                Warning_(
                    code="FORTUNE_SCAN_SORT_IS_STRUCTURAL",
                    message=f"sort={sort} 仅按结构条件数量/关系事件数量排序，不涉及收益。",
                    severity="info",
                )
            )

        return StockFortuneScanResponse(
            evaluation_context=evaluation_context,
            temporal_mode=request.temporal_mode,
            exchange=request.exchange if trading_calendar_source else None,
            is_trading_day=True if trading_calendar_source else None,
            ten_god_filters=request.ten_god_filters,
            relation_filters=request.relation_filters,
            availability_policy=request.availability_policy,
            sort=request.sort,
            universe_version=request.universe.version,
            universe_source=request.universe.source,
            universe_digest=self._universe_digest(request),
            request_digest=self._request_digest(
                request,
                trading_calendar_source=trading_calendar_source,
                trading_calendar_version=trading_calendar_version,
            ),
            trading_calendar_source=trading_calendar_source,
            trading_calendar_version=trading_calendar_version,
            total_examined=total_examined,
            total_matched=total_matched,
            total=total_matched,
            offset=request.offset,
            limit=request.limit,
            items=page,
            warnings=warnings,
            rule_versions=StockFortuneScanRuleVersions(
                **{field: sorted(values) for field, values in version_values.items()}
            ),
            availability=(
                FortuneAvailability.AVAILABLE
                if total_examined and unavailable_count == 0
                else FortuneAvailability.PARTIAL
            ),
        )

    @staticmethod
    def _temporal_input(request, target) -> FortuneTemporalInput:
        mode = getattr(request.temporal_mode, "value", request.temporal_mode)
        if mode == FortuneScanTemporalMode.EXACT_DATETIME.value:
            return FortuneTemporalInput(
                kind=FortuneTemporalInputKind.EXACT_DATETIME,
                target_datetime=request.evaluation_datetime,
            )
        if mode == FortuneScanTemporalMode.DATE_SCAN_NOON.value:
            return FortuneTemporalInput(
                kind=FortuneTemporalInputKind.EXACT_DATETIME,
                target_datetime=datetime.combine(
                    request.evaluation_date,
                    time(12, 0),
                    tzinfo=ZoneInfo(settings.timezone),
                ),
            )
        return FortuneTemporalInput(
            kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
            target_date=request.evaluation_date,
            exchange=request.exchange,
            is_trading_day=request.is_trading_day,
        )

    @classmethod
    def _matched_conditions(
        cls, snapshot, request: StockFortuneScanRequest
    ) -> list[StockFortuneMatchedCondition] | None:
        result = []
        for condition in request.ten_god_filters:
            if not cls._matches_ten_god(snapshot, condition):
                return None
            layer = getattr(condition.layer, "value", condition.layer)
            result.append(
                StockFortuneMatchedCondition(
                    kind="ten_god",
                    label=f"{layer}={condition.ten_god}",
                    ten_god_filter=condition,
                )
            )
        for condition in request.relation_filters:
            if not any(
                StockFortuneTimelineEngine._matches_relation(event, condition)
                for event in snapshot.relation_context.events
            ):
                return None
            result.append(
                StockFortuneMatchedCondition(
                    kind="relation",
                    label=(
                        f"{condition.source_context}.{condition.source_pillar} → "
                        f"natal.{condition.target_pillar} {condition.relation_type}"
                    ),
                    relation_filter=condition,
                )
            )
        return result

    @staticmethod
    def _matches_ten_god(snapshot, condition: FortuneTenGodFilter) -> bool:
        context = snapshot.ten_god_context
        layer = getattr(condition.layer, "value", condition.layer)
        if layer == FortuneTenGodLayer.ANNUAL.value:
            return StockFortuneCrossSectionScanner._label(context.annual) == condition.ten_god
        if layer == FortuneTenGodLayer.MONTHLY.value:
            return StockFortuneCrossSectionScanner._label(context.monthly) == condition.ten_god
        if layer == FortuneTenGodLayer.DAILY.value:
            return StockFortuneCrossSectionScanner._label(context.daily) == condition.ten_god
        if layer == FortuneTenGodLayer.NATAL.value:
            return any(
                item.position == condition.position
                and item.stem is not None
                and item.stem.ten_god == condition.ten_god
                for item in context.natal
            )
        if layer == FortuneTenGodLayer.HIDDEN_STEM.value:
            return any(
                item.pillar == condition.position
                and item.stem.ten_god == condition.ten_god
                and (condition.hidden_stem is None or item.stem.stem == condition.hidden_stem)
                for item in context.hidden_stems
            )
        return False

    @staticmethod
    def _label(observation) -> str | None:
        if observation is None or observation.availability != FortuneAvailability.AVAILABLE:
            return None
        return observation.display_label

    @staticmethod
    def _universe_digest(request: StockFortuneScanRequest) -> str:
        identity = {
            "version": request.universe.version,
            "source": request.universe.source.model_dump(mode="json"),
            "targets": sorted(
                (item.model_dump(mode="json") for item in request.universe.targets),
                key=lambda item: item["stock_identity"]["symbol"],
            ),
        }
        canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()[:24]

    @classmethod
    def _request_digest(
        cls,
        request: StockFortuneScanRequest,
        *,
        trading_calendar_source: str | None = None,
        trading_calendar_version: str | None = None,
    ) -> str:
        identity = {
            "temporal_mode": getattr(request.temporal_mode, "value", request.temporal_mode),
            "evaluation_date": request.evaluation_date.isoformat() if request.evaluation_date else None,
            "evaluation_datetime": (
                request.evaluation_datetime.isoformat()
                if request.evaluation_datetime
                else None
            ),
            "exchange": getattr(request.exchange, "value", request.exchange),
            "is_trading_day": request.is_trading_day,
            "market_session_version": request.market_session_version,
            "config_version": request.config_version,
            "universe_digest": cls._universe_digest(request),
            "trading_calendar_source": trading_calendar_source,
            "trading_calendar_version": trading_calendar_version,
            "ten_god_filters": [item.model_dump(mode="json") for item in request.ten_god_filters],
            "relation_filters": [item.model_dump(mode="json") for item in request.relation_filters],
            "availability_policy": getattr(
                request.availability_policy, "value", request.availability_policy
            ),
            "sort": getattr(request.sort, "value", request.sort),
            "limit": request.limit,
            "offset": request.offset,
        }
        canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

__all__ = [
    "RequestScopedCalendarSnapshotCache",
    "StockFortuneCrossSectionScanner",
]
