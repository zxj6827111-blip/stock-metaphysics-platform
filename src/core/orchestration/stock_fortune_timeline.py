"""F4 股票 Fortune 时间轴。

时间轴只用 F3 Snapshot Engine 构造一次稳定原局/大运上下文；其余日期复用
CalendarEngine、Ten-God 与 Relation Scan 的既有确定性 helper，不保存每日 Snapshot。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import TEN_GODS, nayin_of
from src.core.fortune.temporal_context import resolve_temporal_input
from src.core.orchestration.stock_fortune import StockFortuneEngine
from src.core.orchestration.ten_god_calendar import segment_boundaries
from src.core.relations.ten_god import ten_god_ref
from src.core.schemas.calendar import CalendarSnapshot, GanZhi
from src.core.schemas.common import Exchange, Warning_
from src.core.schemas.fortune import (
    FortuneAvailability,
    FortuneContextKind,
    FortuneDayunPeriod,
    FortuneRelationEvent,
    FortuneRelationFilter,
    FortuneRelationScope,
    FortuneSolarMonthSegment,
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    FortuneTenGodDateIndex,
    FortuneTenGodFilter,
    FortuneTenGodLayer,
    FortuneTenGodObservation,
    FortuneTimelineAnchorMode,
    FortuneTimelineDateMode,
    FortuneTimelineTenGodIndex,
    FortuneTradingCalendarCoverage,
    StockFortuneEvaluationRequest,
    StockFortuneTimeline,
    StockFortuneTimelinePoint,
    StockFortuneTimelineRequest,
    StockFortuneStableContext,
)
from src.core.stock.trading_calendar import (
    KNOWN_SOURCES,
    TradingCalendarProvider,
    get_trading_calendar_provider,
)


class StockFortuneTimelineError(ValueError):
    """Timeline 输入不满足可验证日期或历法要求。"""


class StockFortuneTimelineEngine:
    def __init__(
        self,
        snapshot_engine: StockFortuneEngine,
        *,
        trading_calendar_provider: TradingCalendarProvider | None = None,
    ) -> None:
        self.snapshot_engine = snapshot_engine
        self.trading_calendar_provider = (
            trading_calendar_provider or get_trading_calendar_provider()
        )

    def build(self, request: StockFortuneTimelineRequest) -> StockFortuneTimeline:
        if request.timezone != settings.timezone:
            raise StockFortuneTimelineError(
                f"timeline timezone 必须与项目历法时区一致：{settings.timezone}"
            )
        calendar_status, calendar_days, date_warnings = self._date_selection(request)
        point_dates = [item[0] for item in calendar_days]

        # 用窗口最后一个可见点建一次 F3 Snapshot。没有可见点时，
        # 用 end_date 的显式 exact-noon 生成稳定原局，不伪装成交易日 point。
        seed_date = point_dates[-1] if point_dates else request.end_date
        seed_request = self._evaluation_request(request, seed_date, force_exact=not point_dates)
        seed = self.snapshot_engine.evaluate(seed_request)
        seed_point_resolution = seed.temporal_resolution
        seed_warnings = list(seed.warnings)
        if seed.temporal_context is None:
            if request.anchor_mode != FortuneTimelineAnchorMode.MARKET_SESSION_DATE:
                raise StockFortuneTimelineError(
                    "exact timeline seed 时间无法解析："
                    f"{seed.temporal_resolution.reason or 'unavailable'}"
                )
            stable_seed = self.snapshot_engine.evaluate(
                self._evaluation_request(request, seed_date, force_exact=True)
            )
            if stable_seed.temporal_context is None:
                raise StockFortuneTimelineError(
                    "MARKET_SESSION_DATE 与 exact-noon 均无法建立稳定上下文"
                )
            seed = stable_seed
            seed_warnings.extend(stable_seed.warnings)
            seed_warnings.append(
                Warning_(
                    code="FORTUNE_TIMELINE_SESSION_ANCHOR_UNAVAILABLE",
                    message=(
                        "最后一个交易日的 session 锚点不可解析；稳定上下文改用该日 exact-noon，"
                        "该交易日不会伪装成已解析的 Timeline point。"
                    ),
                    severity="warning",
                )
            )
        stable = self._stable_context(seed)

        warnings = [*seed_warnings, *date_warnings]
        warnings.append(
            Warning_(
                code="FORTUNE_TIMELINE_STABLE_CONTEXT_ANCHOR",
                message=(
                    "稳定原局与大运规则上下文只构建一次，锚定最后一个可验证时间点；"
                    "没有可验证交易日时锚定请求结束日期，且不生成时间轴点。"
                ),
                severity="info",
            )
        )
        calendar_by_date = {
            day: (trading_day, source)
            for day, trading_day, source in calendar_days
        }
        all_points: list[StockFortuneTimelinePoint] = []
        unresolved_date_count = 0
        for day in point_dates:
            if point_dates and day == seed_date:
                resolution = seed_point_resolution
            else:
                resolution = self._resolve_day(request, day)
            if resolution.context is None:
                unresolved_date_count += 1
                warnings.append(
                    Warning_(
                        code="FORTUNE_TIMELINE_DATE_UNAVAILABLE",
                        message=f"{day.isoformat()} 缺少可验证的时间锚点：{resolution.reason}",
                        severity="warning",
                    )
                )
                continue
            all_points.append(self._point(
                day,
                resolution.context.calendar_snapshot,
                resolution.context.target_at,
                calendar_by_date.get(day),
                stable,
            ))

        points = [
            point
            for point in all_points
            if self._matches_timeline_filters(point, stable, request)
        ]
        if not request.include_relation_events:
            points = [point.model_copy(update={"relation_events": []}) for point in points]

        month_segments: list[FortuneSolarMonthSegment] = []
        if request.include_month_segments and all_points:
            try:
                month_segments = self._month_segments(all_points, stable)
            except (ValueError, RuntimeError) as exc:
                warnings.append(
                    Warning_(
                        code="FORTUNE_MONTH_INDEX_UNAVAILABLE",
                        message=f"精确节气流月索引不可用：{type(exc).__name__}",
                        severity="warning",
                    )
                )

        index = (
            self._ten_god_index(all_points, stable)
            if request.include_ten_god_index
            else None
        )
        if calendar_status.unknown_days:
            warnings.append(
                Warning_(
                    code="TRADING_CALENDAR_COVERAGE_INCOMPLETE",
                    message=(
                        f"请求区间有 {calendar_status.unknown_days} 天没有实测或已公布交易日证据；"
                        "TRADING_DAYS_ONLY 仅包含已确认交易日，未用周末规则补造交易日。"
                    ),
                    severity="warning",
                )
            )
        if request.ten_god_filters or request.relation_filters:
            warnings.append(
                Warning_(
                    code="FORTUNE_TIMELINE_FILTER_IS_STRUCTURAL",
                    message="十神与关系过滤只筛选确定性结构，不代表收益预测、推荐或交易信号。",
                    severity="info",
                )
            )

        availability = (
            FortuneAvailability.AVAILABLE
            if all_points
            and unresolved_date_count == 0
            and calendar_status.unknown_days == 0
            and stable.natal_context.availability == FortuneAvailability.AVAILABLE
            and stable.luck_cycle_availability == FortuneAvailability.AVAILABLE
            else FortuneAvailability.PARTIAL
        )

        return StockFortuneTimeline(
            stock_identity=request.stock_identity,
            birth_context=request.birth_profile,
            stable_context=stable,
            start_date=request.start_date,
            end_date=request.end_date,
            date_mode=request.date_mode,
            anchor_mode=request.anchor_mode,
            timezone=request.timezone,
            ten_god_filters=request.ten_god_filters,
            relation_filters=request.relation_filters,
            include_relation_events=request.include_relation_events,
            include_month_segments=request.include_month_segments,
            include_ten_god_index=request.include_ten_god_index,
            points=points,
            month_segments=month_segments,
            ten_god_index=index,
            trading_calendar=calendar_status,
            availability=availability,
            rule_versions=seed.rule_versions,
            provenance=seed.provenance,
            warnings=self._dedupe_warnings(warnings),
            assumptions=seed.assumptions,
        )

    def _date_selection(
        self, request: StockFortuneTimelineRequest
    ) -> tuple[
        FortuneTradingCalendarCoverage,
        list[tuple[date, bool | None, str]],
        list[Warning_],
    ]:
        exchange = (
            request.stock_identity.exchange
            if request.stock_identity.exchange != Exchange.UNKNOWN
            else request.birth_profile.exchange
        )
        calendar = self.trading_calendar_provider.for_exchange(
            getattr(exchange, "value", exchange)
        )
        observed = calendar.coverage
        published = calendar.published_coverage
        selected: list[tuple[date, bool | None, str]] = []
        known_trading = known_closed = unknown = 0
        sources: set[str] = set()
        warnings: list[Warning_] = []
        day = request.start_date
        while day <= request.end_date:
            query = calendar.is_trading_day(day)
            source = query.source
            value = query.value if source in KNOWN_SOURCES else None
            sources.add(source)
            if value is True:
                known_trading += 1
            elif value is False:
                known_closed += 1
            else:
                unknown += 1
            if request.date_mode == FortuneTimelineDateMode.ALL_CALENDAR_DAYS:
                selected.append((day, value, source))
            elif value is True:
                selected.append((day, value, source))
            day += timedelta(days=1)

        if exchange == Exchange.UNKNOWN:
            warnings.append(
                Warning_(
                    code="TRADING_CALENDAR_EXCHANGE_UNKNOWN",
                    message="证券交易所未知，交易日状态全部保留为 unavailable。",
                    severity="warning",
                )
            )
        if "weekend_rule_fallback" in sources:
            warnings.append(
                Warning_(
                    code="TRADING_CALENDAR_FALLBACK_REJECTED",
                    message="周末规则只作为降级证据；F4 不将其用于筛选 TRADING_DAYS_ONLY。",
                    severity="warning",
                )
            )
        coverage = FortuneTradingCalendarCoverage(
            exchange=getattr(exchange, "value", exchange),
            version_token=calendar.version_token,
            observed_start=observed[0] if observed else None,
            observed_end=observed[1] if observed else None,
            published_start=published[0] if published else None,
            published_end=published[1] if published else None,
            confirmed_trading_days=known_trading,
            confirmed_closed_days=known_closed,
            unknown_days=unknown,
            sources=sorted(sources),
        )
        return coverage, selected, warnings

    def _evaluation_request(
        self,
        request: StockFortuneTimelineRequest,
        day: date,
        *,
        force_exact: bool = False,
    ) -> StockFortuneEvaluationRequest:
        session_version = (
            request.market_session_version
            or request.birth_profile.market_session_version
        )
        config_version = request.config_version or request.birth_profile.config_version
        if (
            not force_exact
            and request.anchor_mode == FortuneTimelineAnchorMode.MARKET_SESSION_DATE
        ):
            exchange = (
                request.stock_identity.exchange
                if request.stock_identity.exchange != Exchange.UNKNOWN
                else request.birth_profile.exchange
            )
            temporal = FortuneTemporalInput(
                kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
                target_date=day,
                exchange=exchange,
                is_trading_day=True,
            )
        else:
            anchor = request.evaluation_time or time(12, 0)
            temporal = FortuneTemporalInput(
                kind=FortuneTemporalInputKind.EXACT_DATETIME,
                target_datetime=datetime.combine(
                    day, anchor, tzinfo=ZoneInfo(request.timezone)
                ),
            )
        return StockFortuneEvaluationRequest(
            stock_identity=request.stock_identity,
            birth_profile=request.birth_profile,
            evaluation_context=temporal,
            evaluation_source=request.evaluation_source,
            evaluation_source_version=request.evaluation_source_version,
            luck_cycle_evidence=request.luck_cycle_evidence,
            market_session_version=session_version,
            config_version=config_version,
        )

    def _resolve_day(self, request, day: date):
        evaluation_request = self._evaluation_request(request, day)
        return resolve_temporal_input(
            evaluation_request.evaluation_context,
            self.snapshot_engine.calendar,
            timezone=request.timezone,
            market_session_version=(
                evaluation_request.market_session_version
                or request.birth_profile.market_session_version
            ),
            config_version=(evaluation_request.config_version or settings.config_version),
        )

    @staticmethod
    def _stable_context(snapshot) -> StockFortuneStableContext:
        luck = snapshot.luck_cycle_context
        natal_events = [
            item
            for item in snapshot.relation_context.events
            if item.scope == FortuneRelationScope.NATAL_NATAL
        ]
        return StockFortuneStableContext(
            source_snapshot_at=snapshot.evaluation_time,
            natal_context=snapshot.natal_context,
            natal_ten_gods=snapshot.ten_god_context.natal,
            hidden_stem_ten_gods=snapshot.ten_god_context.hidden_stems,
            luck_cycle_direction=luck.direction,
            luck_cycle_availability=luck.availability,
            polarity_observed_at=luck.polarity_observed_at,
            luck_cycle_periods=luck.cycle_periods,
            natal_relation_events=natal_events,
            rule_versions=snapshot.rule_versions,
            provenance=snapshot.provenance,
            assumptions=snapshot.assumptions,
            warnings=snapshot.warnings,
            chart_artifact_ids=snapshot.chart_artifact_ids,
        )

    @staticmethod
    def _point(
        day: date,
        calendar: CalendarSnapshot,
        evaluation_at: datetime,
        calendar_query,
        stable: StockFortuneStableContext,
    ) -> StockFortuneTimelinePoint:
        annual, monthly, daily = (
            calendar.year_ganzhi,
            calendar.month_ganzhi,
            calendar.day_ganzhi,
        )
        annual_god = monthly_god = daily_god = None
        events: list[FortuneRelationEvent] = []
        natal = stable.natal_context
        if natal.availability == FortuneAvailability.AVAILABLE and natal.day_master:
            annual_god = StockFortuneTimelineEngine._flow_ten_god(
                "year", annual, natal.day_master
            )
            monthly_god = StockFortuneTimelineEngine._flow_ten_god(
                "month", monthly, natal.day_master
            )
            daily_god = StockFortuneTimelineEngine._flow_ten_god(
                "day", daily, natal.day_master
            )
            natal_pillars = {
                "year": natal.pillars.year,
                "month": natal.pillars.month,
                "day": natal.pillars.day,
            }
            natal_ganzhi = {
                position: pillar
                for position, pillar in natal_pillars.items()
                if pillar is not None
            }
            for context, pillar_name, pillar in (
                (FortuneContextKind.YEAR, "year", annual),
                (FortuneContextKind.MONTH, "month", monthly),
                (FortuneContextKind.DAY, "day", daily),
            ):
                events.extend(
                    StockFortuneEngine._external_relation_events(
                        pillar,
                        context,
                        pillar_name,
                        natal_ganzhi,
                        natal.day_master,
                    )
                )

        luck_period = StockFortuneTimelineEngine._period_for(stable, evaluation_at)
        if (
            luck_period is not None
            and natal.availability == FortuneAvailability.AVAILABLE
            and natal.day_master
        ):
            natal_ganzhi = {
                name: pillar
                for name, pillar in (
                    ("year", natal.pillars.year),
                    ("month", natal.pillars.month),
                    ("day", natal.pillars.day),
                )
                if pillar is not None
            }
            events.extend(
                StockFortuneEngine._external_relation_events(
                    luck_period.ganzhi,
                    FortuneContextKind.DAYUN,
                    "dayun",
                    natal_ganzhi,
                    natal.day_master,
                )
            )

        has_stable_natal = natal.availability == FortuneAvailability.AVAILABLE
        availability = (
            FortuneAvailability.AVAILABLE
            if has_stable_natal
            and stable.luck_cycle_availability == FortuneAvailability.AVAILABLE
            else FortuneAvailability.PARTIAL
        )
        trading_day, source = (None, "unavailable")
        if calendar_query is not None:
            trading_day, source = calendar_query
        if trading_day is None and availability == FortuneAvailability.AVAILABLE:
            availability = FortuneAvailability.PARTIAL
        return StockFortuneTimelinePoint(
            date=day,
            evaluation_datetime=evaluation_at,
            trading_day=trading_day,
            trading_calendar_source=source,
            luck_cycle_ref=luck_period,
            annual_pillar=annual,
            monthly_pillar=monthly,
            daily_pillar=daily,
            annual_ten_god=annual_god,
            monthly_ten_god=monthly_god,
            daily_ten_god=daily_god,
            relation_events=events,
            availability=availability,
        )

    @staticmethod
    def _flow_ten_god(layer: str, pillar: GanZhi, day_master: str) -> FortuneTenGodObservation:
        ref = ten_god_ref(day_master, pillar.stem)
        return FortuneTenGodObservation(
            layer=layer,
            position=layer,
            pillar=pillar,
            stem=ref,
            display_label=ref.ten_god,
            availability=FortuneAvailability.AVAILABLE,
            rule_version=settings.ten_god_rule_version,
        )

    @staticmethod
    def _period_for(
        stable: StockFortuneStableContext, evaluation_at: datetime
    ) -> FortuneDayunPeriod | None:
        if stable.luck_cycle_availability != FortuneAvailability.AVAILABLE:
            return None
        observed_at = stable.polarity_observed_at
        if observed_at is not None and evaluation_at < observed_at:
            return None
        return next(
            (
                item
                for item in stable.luck_cycle_periods
                if item.start_at <= evaluation_at < item.end_at
            ),
            None,
        )

    @staticmethod
    def _matches_timeline_filters(point, stable, request) -> bool:
        for condition in request.ten_god_filters:
            if not StockFortuneTimelineEngine._matches_ten_god(point, stable, condition):
                return False
        for condition in request.relation_filters:
            if not any(
                StockFortuneTimelineEngine._matches_relation(event, condition)
                for event in point.relation_events
            ):
                return False
        return True

    @staticmethod
    def _matches_ten_god(point, stable, condition: FortuneTenGodFilter) -> bool:
        layer = getattr(condition.layer, "value", condition.layer)
        if layer in {
            FortuneTenGodLayer.ANNUAL.value,
            FortuneTenGodLayer.MONTHLY.value,
            FortuneTenGodLayer.DAILY.value,
        }:
            field = {
                FortuneTenGodLayer.ANNUAL.value: point.annual_ten_god,
                FortuneTenGodLayer.MONTHLY.value: point.monthly_ten_god,
                FortuneTenGodLayer.DAILY.value: point.daily_ten_god,
            }[layer]
            return field is not None and field.display_label == condition.ten_god
        if layer == FortuneTenGodLayer.NATAL.value:
            return any(
                item.position == condition.position
                and item.stem is not None
                and item.stem.ten_god == condition.ten_god
                for item in stable.natal_ten_gods
            )
        if layer == FortuneTenGodLayer.HIDDEN_STEM.value:
            return any(
                item.pillar == condition.position
                and item.stem.ten_god == condition.ten_god
                and (condition.hidden_stem is None or item.stem.stem == condition.hidden_stem)
                for item in stable.hidden_stem_ten_gods
            )
        return False

    @staticmethod
    def _matches_relation(event: FortuneRelationEvent, condition: FortuneRelationFilter) -> bool:
        source = event.source
        target = event.target
        return (
            event.relation_type == condition.relation_type
            and getattr(source.context, "value", source.context)
            == getattr(condition.source_context, "value", condition.source_context)
            and source.pillar == condition.source_pillar
            and getattr(target.context, "value", target.context)
            == getattr(condition.target_context, "value", condition.target_context)
            and target.pillar == condition.target_pillar
            and (condition.source_component is None or source.component == condition.source_component)
            and (condition.target_component is None or target.component == condition.target_component)
        )

    @staticmethod
    def _month_segments(
        points: list[StockFortuneTimelinePoint], stable: StockFortuneStableContext
    ) -> list[FortuneSolarMonthSegment]:
        first = points[0].evaluation_datetime
        naive_start = first.astimezone(ZoneInfo(settings.timezone)).replace(tzinfo=None)
        span_days = (points[-1].date - points[0].date).days
        count = max(1, span_days // 28 + 3)
        segments = segment_boundaries(naive_start, count, kind="month")
        day_master = stable.natal_context.day_master
        output: list[FortuneSolarMonthSegment] = []
        tz = ZoneInfo(settings.timezone)
        for segment in segments:
            applicable = [
                point.date
                for point in points
                if segment.start_at <= point.evaluation_datetime.astimezone(tz).replace(tzinfo=None)
                < segment.end_at
            ]
            if not applicable:
                continue
            pillar = GanZhi.from_text(
                segment.ganzhi_text,
                nayin=nayin_of(segment.ganzhi_text),
            )
            month_god = ten_god_ref(day_master, pillar.stem).ten_god if day_master else None
            start_at = segment.start_at.replace(tzinfo=tz) if segment.start_at.tzinfo is None else segment.start_at
            end_at = segment.end_at.replace(tzinfo=tz) if segment.end_at.tzinfo is None else segment.end_at
            months = sorted({f"{item.year:04d}-{item.month:02d}" for item in applicable})
            output.append(
                FortuneSolarMonthSegment(
                    start_at=start_at,
                    end_at=end_at,
                    boundary_jieqi=segment.boundary_jieqi,
                    next_boundary_jieqi=segment.next_boundary_jieqi,
                    monthly_pillar=pillar,
                    monthly_ten_god=month_god,
                    gregorian_months=months,
                    effective_dates=applicable,
                )
            )
        return output

    @staticmethod
    def _ten_god_index(
        points: list[StockFortuneTimelinePoint], stable: StockFortuneStableContext
    ) -> FortuneTimelineTenGodIndex:
        entries = []
        for layer, field in (("year", "annual_ten_god"), ("month", "monthly_ten_god"), ("day", "daily_ten_god")):
            for god in TEN_GODS:
                dates = [
                    point.date
                    for point in points
                    if (item := getattr(point, field)) is not None
                    and item.display_label == god
                ]
                entries.append(FortuneTenGodDateIndex(layer=layer, ten_god=god, dates=dates))
        return FortuneTimelineTenGodIndex(
            entries=entries,
            stable_natal=stable.natal_ten_gods,
            stable_hidden_stems=stable.hidden_stem_ten_gods,
        )

    @staticmethod
    def _dedupe_warnings(warnings: list[Warning_]) -> list[Warning_]:
        seen: set[tuple[str, str]] = set()
        result = []
        for warning in warnings:
            key = (warning.code, warning.message)
            if key not in seen:
                seen.add(key)
                result.append(warning)
        return result


__all__ = ["StockFortuneTimelineEngine", "StockFortuneTimelineError"]
