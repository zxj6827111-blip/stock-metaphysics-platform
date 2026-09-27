"""Stock Fortune Snapshot 的统一编排入口。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.constants import nayin_of
from src.core.fortune.luck_cycle import (
    compatibility_variant_mode,
    resolve_first_day_yinyang_luck_cycle,
)
from src.core.fortune.ports import (
    CalendarSnapshotProvider,
    FortuneChartArtifactWriter,
)
from src.core.fortune.temporal_context import resolve_temporal_input
from src.core.relations.date_relation import relation_events_for_external_pillar
from src.core.relations.ten_god import day_stem_ten_god, hidden_stems_with_gods, ten_god_ref
from src.core.schemas.bazi import BaziChart, BaziLuckCyclePeriod
from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import (
    Assumption,
    SourceRef,
    VariantMode,
    Warning_,
)
from src.core.schemas.fortune import (
    FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION,
    FORTUNE_LUCK_CYCLE_RULE_VERSION,
    FORTUNE_SNAPSHOT_RULE_VERSION,
    FORTUNE_TEMPORAL_RESOLUTION_RULE_VERSION,
    FortuneAvailability,
    FortuneContextKind,
    FortuneDayunPeriod,
    FortuneHiddenStemTenGodObservation,
    FortuneLuckCycleContext,
    FortuneNatalHiddenStem,
    FortuneNatalContext,
    FortuneProvenanceComponent,
    FortuneProvenanceRecord,
    FortuneRelationCategory,
    FortuneRelationComponent,
    FortuneRelationContext,
    FortuneRelationEvent,
    FortuneRelationParticipant,
    FortuneRelationScope,
    FortuneRuleVersions,
    FortuneTemporalPillarContext,
    FortuneTemporalResolution,
    FortuneTemporalResolutionStatus,
    FortuneTenGodContext,
    FortuneTenGodObservation,
    NatalPillarAvailability,
    NatalPillarSet,
    StockFortuneEvaluationRequest,
    StockFortuneSnapshot,
)
from src.core.schemas.ten_god import TenGodHiddenStem
from src.db.models import ChartArtifactRow
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine


class DatabaseFortuneChartArtifactWriter:
    """将稳定盘面写入既有 chart_artifact 表；事务仍由调用方管理。"""

    def __init__(self, db: Session) -> None:
        self._db = db

    def persist_chart_artifact(
        self,
        *,
        engine_id: str,
        engine_version: str,
        symbol: str,
        as_of: datetime,
        input_payload: Mapping[str, object],
        raw_chart: Mapping[str, object],
        assumptions: Sequence[Mapping[str, object]],
        warnings: Sequence[Mapping[str, object]],
        birth_profile_version: str,
        config_version: str,
    ) -> str:
        identity = {
            "engine": engine_id,
            "engine_version": engine_version,
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "input": dict(input_payload),
            "raw_chart": dict(raw_chart),
            "assumptions": [dict(item) for item in assumptions],
            "warnings": [dict(item) for item in warnings],
            "birth_profile_version": birth_profile_version,
            "config_version": config_version,
        }
        canonical = json.dumps(
            identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        chart_id = f"ft-{engine_id[:8]}-{digest[:40]}"
        local_as_of = as_of.astimezone(ZoneInfo(settings.timezone)).replace(tzinfo=None)
        row = self._db.get(ChartArtifactRow, chart_id)
        if row is not None:
            if (
                row.raw_chart != dict(raw_chart)
                or row.input_json != dict(input_payload)
                or row.assumptions_json != [dict(item) for item in assumptions]
                or row.warnings_json != [dict(item) for item in warnings]
                or row.birth_profile_version != birth_profile_version
                or row.config_version != config_version
                or row.engine != engine_id
                or row.engine_version != engine_version
                or row.stock_code != symbol
                or row.as_of != local_as_of
            ):
                raise RuntimeError("deterministic chart_artifact ID collision")
            return chart_id

        self._db.add(
            ChartArtifactRow(
                chart_id=chart_id,
                stock_code=symbol,
                engine=engine_id,
                engine_version=engine_version,
                config_version=config_version,
                birth_profile_version=birth_profile_version,
                as_of=local_as_of,
                input_json=dict(input_payload),
                raw_chart=dict(raw_chart),
                assumptions_json=[dict(item) for item in assumptions],
                warnings_json=[dict(item) for item in warnings],
            )
        )
        self._db.flush()
        return chart_id


class StockFortuneEngine:
    """调用者只需提供股票档案和 evaluation context，不手动拼装底层引擎。"""

    def __init__(
        self,
        artifact_writer: FortuneChartArtifactWriter,
        *,
        calendar: CalendarSnapshotProvider | None = None,
        bazi: BaziEngine | None = None,
    ) -> None:
        self.calendar = calendar or CalendarEngine()
        self.bazi = bazi or BaziEngine(self.calendar)  # type: ignore[arg-type]
        self.artifact_writer = artifact_writer

    def evaluate(self, request: StockFortuneEvaluationRequest) -> StockFortuneSnapshot:
        """构建确定性 Snapshot；不读取价格、收益或系统当前时间。"""

        profile = request.birth_profile
        config_version = request.config_version or profile.config_version or settings.config_version
        market_session_version = (
            request.market_session_version
            or profile.market_session_version
            or (
                request.luck_cycle_evidence.market_session_version
                if request.luck_cycle_evidence
                else ""
            )
        )
        resolution = resolve_temporal_input(
            request.evaluation_context,
            self.calendar,
            timezone=settings.timezone,
            market_session_version=market_session_version,
            config_version=config_version,
        )
        warnings: list[Warning_] = []
        raw_chart: dict[str, object] = {}
        artifact_ids: list[str] = []
        bazi_assumptions: list[Assumption] = []
        temporal_context = resolution.context
        evaluation_time = temporal_context.target_at if temporal_context else None
        unavailable_luck = self._unavailable_luck_cycle(
            resolution.reason or "缺少可用的 evaluation time，无法确定排运观测时点"
        )
        bazi_engine_version = settings.bazi_engine_version
        natal_context = self._unavailable_natal()
        ten_god_context = self._unavailable_ten_god()
        relation_context = self._unavailable_relations()
        dayun_context = unavailable_luck
        annual, monthly, daily = self._unavailable_temporal_contexts()

        if temporal_context is None:
            warnings.append(
                Warning_(
                    code=(
                        "FORTUNE_TIME_"
                        f"{getattr(resolution.status, 'value', resolution.status)}"
                    ),
                    message=resolution.reason or "Evaluation time 尚未解析",
                )
            )
        else:
            assert evaluation_time is not None
            calendar = temporal_context.calendar_snapshot
            annual, monthly, daily = self._temporal_pillars(calendar)
            calendar_payload = calendar.model_dump(mode="json")
            calendar_id = self.artifact_writer.persist_chart_artifact(
                engine_id="calendar",
                engine_version=calendar.engine_version,
                symbol=profile.symbol,
                as_of=evaluation_time,
                input_payload=request.model_dump(mode="json"),
                raw_chart=calendar_payload,
                assumptions=[item.model_dump(mode="json") for item in temporal_context.assumptions],
                warnings=[item.model_dump(mode="json") for item in calendar.warnings],
                birth_profile_version=profile.birth_profile_version,
                config_version=config_version,
            )
            artifact_ids.append(calendar_id)
            raw_chart["calendar"] = calendar_payload

            if profile.birth_datetime is None:
                unavailable_luck = self._unavailable_luck_cycle(
                    "出生档案没有可安全使用的 birth_datetime，不能计算大运"
                )
                dayun_context = unavailable_luck
                warnings.append(
                    Warning_(
                        code="FORTUNE_NATAL_BIRTH_TIME_UNAVAILABLE",
                        message=(
                            "出生精度为 "
                            f"{getattr(profile.birth_time_precision, 'value', profile.birth_time_precision)}，"
                            "没有可安全使用的时刻；"
                            "不构造原局四柱。"
                        ),
                    )
                )
            else:
                birth_timezone = ZoneInfo(profile.timezone)
                birth_at = profile.birth_datetime.astimezone(birth_timezone)
                birth_snapshot = self.calendar.snapshot(birth_at.replace(tzinfo=None))
                luck = self._resolve_luck_cycle(
                    request,
                    birth_year_stem=birth_snapshot.year_ganzhi.stem,
                    evaluation_time=evaluation_time,
                )
                variant_mode = (
                    compatibility_variant_mode(luck)
                    if luck.availability == FortuneAvailability.AVAILABLE
                    else VariantMode.NOT_APPLICABLE
                )
                chart = self.bazi.build_chart(
                    birth_datetime=birth_at,
                    as_of=evaluation_time,
                    variant_mode=variant_mode,
                    stock_code=profile.symbol,
                    natal_snapshot=birth_snapshot,
                    reference_snapshot=calendar,
                )
                bazi_engine_version = chart.engine_version
                bazi_assumptions = chart.assumptions
                dayun_context, dayun_warning = self._resolve_current_cycle(
                    luck,
                    birth_at=birth_at,
                    evaluation_time=evaluation_time,
                    variant_mode=variant_mode,
                )
                if dayun_warning:
                    warnings.append(dayun_warning)
                chart_payload = chart.model_dump(mode="json", exclude={"calculated_at"})
                bazi_id = self.artifact_writer.persist_chart_artifact(
                    engine_id=chart.engine_id,
                    engine_version=chart.engine_version,
                    symbol=profile.symbol,
                    as_of=evaluation_time,
                    input_payload=request.model_dump(mode="json"),
                    raw_chart=chart_payload,
                    assumptions=[item.model_dump(mode="json") for item in chart.assumptions],
                    warnings=[item.model_dump(mode="json") for item in chart.warnings],
                    birth_profile_version=profile.birth_profile_version,
                    config_version=chart.config_version or config_version,
                )
                artifact_ids.append(bazi_id)
                raw_chart["bazi"] = chart_payload
                natal_context = self._natal_context(chart)
                ten_god_context = self._ten_god_context(chart, annual, monthly, daily)
                relation_context = self._relation_context(chart, annual, monthly, daily, dayun_context)
                unavailable_luck = dayun_context
                warnings.extend(chart.warnings)

        if resolution.status == FortuneTemporalResolutionStatus.RESOLVED:
            availability = (
                FortuneAvailability.AVAILABLE
                if (
                    natal_context.availability == FortuneAvailability.AVAILABLE
                    and unavailable_luck.availability == FortuneAvailability.AVAILABLE
                    and unavailable_luck.cycle_availability == FortuneAvailability.AVAILABLE
                    and ten_god_context.availability == FortuneAvailability.AVAILABLE
                    and relation_context.availability == FortuneAvailability.AVAILABLE
                )
                else FortuneAvailability.PARTIAL
            )
        else:
            availability = FortuneAvailability.UNAVAILABLE

        rule_versions = self._rule_versions(
            request,
            temporal_context=temporal_context,
            luck_cycle=unavailable_luck,
            bazi_engine_version=bazi_engine_version,
            config_version=config_version,
            market_session_version=market_session_version,
        )
        provenance = self._provenance(
            request,
            temporal_context=temporal_context,
            natal_chart=raw_chart.get("bazi"),
            bazi_engine_version=bazi_engine_version,
            luck_cycle=unavailable_luck,
            bazi_assumptions=bazi_assumptions,
            ten_god_context=ten_god_context,
            relation_context=relation_context,
        )
        assumptions = [*profile.assumptions, *bazi_assumptions]
        if temporal_context:
            assumptions.extend(temporal_context.assumptions)
            assumptions.extend(self._calendar_assumptions(temporal_context.calendar_snapshot))
        assumptions.extend(unavailable_luck.assumptions)
        return StockFortuneSnapshot(
            stock_identity=request.stock_identity,
            birth_profile=profile,
            evaluation_time=evaluation_time,
            temporal_resolution=resolution,
            temporal_context=temporal_context,
            natal_context=natal_context,
            luck_cycle_context=unavailable_luck,
            annual_context=annual,
            monthly_context=monthly,
            daily_context=daily,
            ten_god_context=ten_god_context,
            relation_context=relation_context,
            provenance=provenance,
            rule_versions=rule_versions,
            availability=availability,
            raw_chart=raw_chart,
            chart_artifact_ids=artifact_ids,
            warnings=warnings,
            assumptions=assumptions,
        )

    @staticmethod
    def _unavailable_natal() -> FortuneNatalContext:
        return FortuneNatalContext(
            availability=FortuneAvailability.UNAVAILABLE,
            pillars=NatalPillarSet(availability=NatalPillarAvailability.UNAVAILABLE),
        )

    @staticmethod
    def _unavailable_luck_cycle(reason: str) -> FortuneLuckCycleContext:
        return FortuneLuckCycleContext(
            availability=FortuneAvailability.UNAVAILABLE,
            direction_basis="first_day_yinyang_proxy+birth_year_stem_polarity",
            unavailability_reason=reason,
            assumptions=[
                Assumption(
                    key="fortune.luck_cycle.unavailable",
                    value=reason,
                    reason="股票没有真实性别；缺少显式且可追溯的研究约定输入时 fail closed",
                    impact="不产生大运方向或当前周期",
                )
            ],
        )

    @staticmethod
    def _unavailable_ten_god() -> FortuneTenGodContext:
        return FortuneTenGodContext(
            availability=FortuneAvailability.UNAVAILABLE,
            rule_version=settings.ten_god_rule_version,
        )

    @staticmethod
    def _unavailable_relations() -> FortuneRelationContext:
        return FortuneRelationContext(
            availability=FortuneAvailability.UNAVAILABLE,
            rule_version=settings.relation_rule_version,
        )

    @staticmethod
    def _unavailable_temporal_contexts() -> tuple[
        FortuneTemporalPillarContext,
        FortuneTemporalPillarContext,
        FortuneTemporalPillarContext,
    ]:
        return tuple(
            FortuneTemporalPillarContext(
                layer=layer,
                availability=FortuneAvailability.UNAVAILABLE,
            )
            for layer in ("annual", "monthly", "daily")
        )  # type: ignore[return-value]

    @staticmethod
    def _temporal_pillars(calendar) -> tuple[
        FortuneTemporalPillarContext,
        FortuneTemporalPillarContext,
        FortuneTemporalPillarContext,
    ]:
        return (
            FortuneTemporalPillarContext(
                layer="annual",
                availability=FortuneAvailability.AVAILABLE,
                pillar=calendar.year_ganzhi,
                source_engine_version=calendar.engine_version,
            ),
            FortuneTemporalPillarContext(
                layer="monthly",
                availability=FortuneAvailability.AVAILABLE,
                pillar=calendar.month_ganzhi,
                source_engine_version=calendar.engine_version,
            ),
            FortuneTemporalPillarContext(
                layer="daily",
                availability=FortuneAvailability.AVAILABLE,
                pillar=calendar.day_ganzhi,
                source_engine_version=calendar.engine_version,
            ),
        )

    @staticmethod
    def _resolve_luck_cycle(
        request: StockFortuneEvaluationRequest,
        *,
        birth_year_stem: str,
        evaluation_time: datetime,
    ) -> FortuneLuckCycleContext:
        evidence = request.luck_cycle_evidence
        if evidence is None:
            return StockFortuneEngine._unavailable_luck_cycle("缺少首日阴阳证据")
        exchange = request.stock_identity.exchange
        if getattr(exchange, "value", exchange) == "UNKNOWN":
            exchange = request.birth_profile.exchange
        return resolve_first_day_yinyang_luck_cycle(
            first_day_yinyang=evidence.first_day_yinyang,
            polarity_observation_date=evidence.observation_date,
            polarity_is_trading_day=evidence.is_trading_day,
            source=evidence.source,
            source_version=evidence.source_version,
            market_session_version=evidence.market_session_version,
            exchange=exchange,
            birth_year_stem=birth_year_stem,
            as_of=evaluation_time,
        )

    def _resolve_current_cycle(
        self,
        luck: FortuneLuckCycleContext,
        *,
        birth_at: datetime,
        evaluation_time: datetime,
        variant_mode: VariantMode,
    ) -> tuple[FortuneLuckCycleContext, Warning_ | None]:
        if luck.availability != FortuneAvailability.AVAILABLE:
            return luck, None
        try:
            periods = self.bazi.build_luck_cycle_periods(birth_at, variant_mode)
        except (ImportError, AttributeError, ValueError) as exc:
            return self._luck_with_unavailable_periods(luck), Warning_(
                code="FORTUNE_LUCK_CYCLE_PERIOD_UNAVAILABLE",
                message=f"大运周期 Adapter 不可用：{type(exc).__name__}",
            )

        fortune_periods = [self._fortune_period(item) for item in periods]
        evaluation_local = evaluation_time.astimezone(birth_at.tzinfo)
        current = next(
            (
                item
                for item in fortune_periods
                if item.start_at <= evaluation_local < item.end_at
            ),
            None,
        )
        if current is None:
            updated = self._luck_with_unavailable_periods(luck)
            updated = FortuneLuckCycleContext.model_validate(
                {
                    **updated.model_dump(mode="python"),
                    "cycle_periods": fortune_periods,
                    "start_basis": (
                        "lunar-python-1.4.8 Yun.getStartSolar + Solar.nextYear(10*n); "
                        "半开区间 [start_at, end_at)"
                    ),
                    "unavailability_reason": "生成的周期范围内没有覆盖 evaluation time 的大运",
                }
            )
            return updated, Warning_(
                code="FORTUNE_CURRENT_LUCK_CYCLE_NOT_COVERED",
                message="已有顺逆约定，但生成的大运周期没有覆盖 evaluation time",
            )

        payload = luck.model_dump(mode="python")
        payload.update(
            {
                "period_rule_version": FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION,
                "start_basis": (
                    "lunar-python-1.4.8 Yun.getStartSolar + Solar.nextYear(10*n); "
                    "半开区间 [start_at, end_at)"
                ),
                "cycle_availability": FortuneAvailability.AVAILABLE,
                "cycle_periods": fortune_periods,
                "current_cycle": current,
                "cycle_index": current.cycle_index,
                "cycle_start": current.start_at,
                "cycle_end": current.end_at,
                "stem": current.ganzhi.stem,
                "branch": current.ganzhi.branch,
            }
        )
        return FortuneLuckCycleContext.model_validate(payload), None

    @staticmethod
    def _luck_with_unavailable_periods(
        luck: FortuneLuckCycleContext,
    ) -> FortuneLuckCycleContext:
        payload = luck.model_dump(mode="python")
        payload.update(
            {
                "period_rule_version": FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION,
                "cycle_availability": FortuneAvailability.UNAVAILABLE,
                "cycle_periods": [],
                "current_cycle": None,
                "cycle_index": None,
                "cycle_start": None,
                "cycle_end": None,
                "stem": None,
                "branch": None,
            }
        )
        return FortuneLuckCycleContext.model_validate(payload)

    @staticmethod
    def _fortune_period(
        period: BaziLuckCyclePeriod,
    ) -> FortuneDayunPeriod:
        return FortuneDayunPeriod(
            cycle_index=period.index,
            start_at=period.start_at,
            end_at=period.end_at,
            start_year=period.start_year,
            end_year=period.end_year,
            start_age=period.start_age,
            end_age=period.end_age,
            ganzhi=GanZhi.from_text(period.ganzhi, nayin=nayin_of(period.ganzhi)),
            rule_version=FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION,
        )

    @staticmethod
    def _natal_context(chart: BaziChart) -> FortuneNatalContext:
        pillar_pairs = (
            ("year", chart.year_pillar),
            ("month", chart.month_pillar),
            ("day", chart.day_pillar),
            ("hour", chart.hour_pillar),
        )
        return FortuneNatalContext(
            availability=FortuneAvailability.AVAILABLE,
            pillars=NatalPillarSet(
                availability=NatalPillarAvailability.FOUR_PILLARS,
                year=chart.year_pillar.ganzhi,
                month=chart.month_pillar.ganzhi,
                day=chart.day_pillar.ganzhi,
                hour=chart.hour_pillar.ganzhi,
            ),
            day_master=chart.day_master,
            day_master_yang=chart.day_master_analysis.day_master_yang,
            day_master_wuxing=chart.day_master_wuxing,
            hidden_stems=[
                FortuneNatalHiddenStem(
                    position=position,
                    branch=pillar.ganzhi.branch,
                    stem=TenGodHiddenStem(
                        stem=item.stem,
                        wuxing=item.wuxing,
                        ten_god=item.ten_god,
                        ten_god_group=ten_god_ref(chart.day_master, item.stem).ten_god_group,
                        rank=item.rank,
                        weight=item.weight,
                    ),
                )
                for position, pillar in pillar_pairs
                for item in hidden_stems_with_gods(chart.day_master, pillar.ganzhi.branch)
            ],
            bazi_engine=chart.engine_id,
            bazi_engine_version=chart.engine_version,
            rule_version=chart.engine_version,
        )

    @staticmethod
    def _ten_god_context(
        chart: BaziChart,
        annual: FortuneTemporalPillarContext,
        monthly: FortuneTemporalPillarContext,
        daily: FortuneTemporalPillarContext,
    ) -> FortuneTenGodContext:
        if any(context.pillar is None for context in (annual, monthly, daily)):
            return StockFortuneEngine._unavailable_ten_god()
        pillar_pairs = (
            ("year", chart.year_pillar),
            ("month", chart.month_pillar),
            ("day", chart.day_pillar),
            ("hour", chart.hour_pillar),
        )
        natal: list[FortuneTenGodObservation] = []
        hidden: list[FortuneHiddenStemTenGodObservation] = []
        for position, pillar in pillar_pairs:
            ref = ten_god_ref(chart.day_master, pillar.ganzhi.stem)
            if position != "day" and pillar.stem_ten_god != ref.ten_god:
                raise ValueError(f"BaziEngine 与 TenGodEngine 的 {position} 干十神不一致")
            natal.append(
                FortuneTenGodObservation(
                    layer="natal",
                    position=position,
                    pillar=pillar.ganzhi,
                    stem=ref,
                    display_label="日主" if position == "day" else ref.ten_god,
                    availability=FortuneAvailability.AVAILABLE,
                    rule_version=settings.ten_god_rule_version,
                )
            )
            hidden_gods = hidden_stems_with_gods(chart.day_master, pillar.ganzhi.branch)
            bazi_hidden = [(item.stem, item.ten_god) for item in pillar.hidden_stems]
            mapped_hidden = [(item.stem, item.ten_god) for item in hidden_gods]
            if bazi_hidden != mapped_hidden:
                raise ValueError(f"BaziEngine 与 TenGodEngine 的 {position} 藏干十神不一致")
            hidden.extend(
                FortuneHiddenStemTenGodObservation(
                    pillar=position,
                    branch=pillar.ganzhi.branch,
                    stem=item,
                    rule_version=settings.ten_god_rule_version,
                )
                for item in hidden_gods
            )

        temporal = []
        for context, chart_pillar, layer in (
            (annual, chart.current_year_pillar, "year"),
            (monthly, chart.current_month_pillar, "month"),
            (daily, chart.current_day_pillar, "day"),
        ):
            if chart_pillar is None or context.pillar is None:
                raise ValueError(f"BaziEngine 缺少流{layer}十神")
            if chart_pillar.ganzhi.text != context.pillar.text:
                raise ValueError(f"BaziEngine 与共享 CalendarSnapshot 的流{layer}干支不一致")
            ref = ten_god_ref(chart.day_master, context.pillar.stem)
            expected = (
                day_stem_ten_god(chart.day_master, context.pillar.stem)
                if layer == "day"
                else ref.ten_god
            )
            hidden_refs = hidden_stems_with_gods(chart.day_master, context.pillar.branch)
            if chart_pillar.stem_ten_god != expected:
                raise ValueError(f"BaziEngine 与 TenGodEngine 的流{layer}十神不一致")
            if chart_pillar.branch_ten_gods != [item.ten_god for item in hidden_refs]:
                raise ValueError(f"BaziEngine 与 TenGodEngine 的流{layer}支藏干十神不一致")
            temporal.append(
                FortuneTenGodObservation(
                    layer=layer,
                    position=layer,
                    pillar=context.pillar,
                    stem=ref,
                    display_label=ref.ten_god,
                    availability=FortuneAvailability.AVAILABLE,
                    rule_version=settings.ten_god_rule_version,
                )
            )
        return FortuneTenGodContext(
            availability=FortuneAvailability.AVAILABLE,
            day_master=chart.day_master,
            natal=natal,
            annual=temporal[0],
            monthly=temporal[1],
            daily=temporal[2],
            hidden_stems=hidden,
            rule_version=settings.ten_god_rule_version,
        )

    @staticmethod
    def _relation_context(
        chart: BaziChart,
        annual: FortuneTemporalPillarContext,
        monthly: FortuneTemporalPillarContext,
        daily: FortuneTemporalPillarContext,
        luck_cycle: FortuneLuckCycleContext,
    ) -> FortuneRelationContext:
        natal = {
            "year": chart.year_pillar.ganzhi,
            "month": chart.month_pillar.ganzhi,
            "day": chart.day_pillar.ganzhi,
        }
        events: list[FortuneRelationEvent] = []
        for hit in chart.relations:
            positions = list(hit.positions)
            if len(positions) < 2:
                continue
            component = StockFortuneEngine._relation_component(hit.relation_type)
            participants = [
                StockFortuneEngine._participant(
                    FortuneContextKind.NATAL,
                    position,
                    component,
                    StockFortuneEngine._pillar_component_value(
                        chart.pillar_by_position(position).ganzhi,
                        component,
                    ),
                )
                for position in positions
            ]
            events.append(
                FortuneRelationEvent(
                    category=StockFortuneEngine._relation_category(hit.relation_type),
                    relation_type=hit.relation_type,
                    source=participants[0],
                    target=participants[1],
                    participants=[StockFortuneEngine._participant_id(item) for item in participants],
                    scope=FortuneRelationScope.NATAL_NATAL,
                    rule_version=settings.relation_rule_version,
                    evidence=[hit.note] if hit.note else [],
                    explanation=hit.note,
                )
            )

        external = (
            (FortuneContextKind.YEAR, "year", annual),
            (FortuneContextKind.MONTH, "month", monthly),
            (FortuneContextKind.DAY, "day", daily),
        )
        for context_kind, pillar_name, context in external:
            if context.pillar is not None:
                events.extend(
                    StockFortuneEngine._external_relation_events(
                        context.pillar,
                        context_kind,
                        pillar_name,
                        natal,
                        chart.day_master,
                    )
                )
        if luck_cycle.current_cycle is not None:
            events.extend(
                StockFortuneEngine._external_relation_events(
                    luck_cycle.current_cycle.ganzhi,
                    FortuneContextKind.DAYUN,
                    "dayun",
                    natal,
                    chart.day_master,
                )
            )
        counts = dict(sorted(Counter(item.relation_type for item in events).items()))
        return FortuneRelationContext(
            availability=(
                FortuneAvailability.AVAILABLE
                if luck_cycle.current_cycle is not None
                else FortuneAvailability.PARTIAL
            ),
            events=events,
            relation_count=len(events),
            relation_type_counts=counts,
            rule_version=settings.relation_rule_version,
        )

    @staticmethod
    def _external_relation_events(
        source_ganzhi: GanZhi,
        source_context: FortuneContextKind,
        source_pillar: str,
        natal: Mapping[str, GanZhi],
        day_master: str,
    ) -> list[FortuneRelationEvent]:
        base_events = relation_events_for_external_pillar(
            source_ganzhi,
            source_pillar,
            natal,
            day_master=day_master,
        )
        wrapped: list[FortuneRelationEvent] = []
        for event in base_events:
            component = StockFortuneEngine._relation_component(event.relation_type)
            source_value = StockFortuneEngine._event_component_value(
                event.source_stem, event.source_branch, source_ganzhi, component
            )
            target_ganzhi = natal[event.target_pillar]
            target_value = StockFortuneEngine._event_component_value(
                event.target_stem, event.target_branch, target_ganzhi, component
            )
            source = StockFortuneEngine._participant(
                source_context, event.source_pillar, component, source_value
            )
            target = StockFortuneEngine._participant(
                FortuneContextKind.NATAL, event.target_pillar, component, target_value
            )
            wrapped.append(
                FortuneRelationEvent(
                    category=StockFortuneEngine._relation_category(event.relation_type),
                    relation_type=event.relation_type,
                    source=source,
                    target=target,
                    participants=[
                        StockFortuneEngine._participant_id(source),
                        StockFortuneEngine._participant_id(target),
                    ],
                    scope=FortuneRelationScope.TEMPORAL_TO_NATAL,
                    rule_version=settings.relation_rule_version,
                    evidence=[event.notes] if event.notes else [],
                    explanation=event.notes,
                )
            )
        return wrapped

    @staticmethod
    def _relation_component(relation_type: str) -> FortuneRelationComponent:
        if relation_type in {"伏吟", "反吟", "天合地合", "天克地冲"}:
            return FortuneRelationComponent.PILLAR
        if relation_type.startswith("天干"):
            return FortuneRelationComponent.STEM
        return FortuneRelationComponent.BRANCH

    @staticmethod
    def _relation_category(relation_type: str) -> FortuneRelationCategory:
        if relation_type in {"天干五合", "六合", "三合", "半合", "三会", "天合地合"}:
            return FortuneRelationCategory.COMBINATION
        if relation_type in {"六冲", "天干相冲", "天克地冲", "反吟"}:
            return FortuneRelationCategory.CLASH
        if relation_type in {"相刑", "三刑", "自刑"}:
            return FortuneRelationCategory.PUNISHMENT
        if relation_type == "相害":
            return FortuneRelationCategory.HARM
        if relation_type == "六破":
            return FortuneRelationCategory.BREAK
        return FortuneRelationCategory.OTHER

    @staticmethod
    def _pillar_component_value(
        ganzhi: GanZhi,
        component: FortuneRelationComponent,
    ) -> str:
        if component == FortuneRelationComponent.STEM:
            return ganzhi.stem
        if component == FortuneRelationComponent.BRANCH:
            return ganzhi.branch
        return ganzhi.text

    @staticmethod
    def _event_component_value(
        stem: str,
        branch: str,
        ganzhi: GanZhi,
        component: FortuneRelationComponent,
    ) -> str:
        if component == FortuneRelationComponent.STEM:
            return stem or ganzhi.stem
        if component == FortuneRelationComponent.BRANCH:
            return branch or ganzhi.branch
        return ganzhi.text

    @staticmethod
    def _participant(
        context: FortuneContextKind,
        pillar: str,
        component: FortuneRelationComponent,
        value: str,
    ) -> FortuneRelationParticipant:
        return FortuneRelationParticipant(
            context=context,
            pillar=pillar,
            component=component,
            value=value,
        )

    @staticmethod
    def _participant_id(participant: FortuneRelationParticipant) -> str:
        return (
            f"{getattr(participant.context, 'value', participant.context)}:{participant.pillar}:"
            f"{getattr(participant.component, 'value', participant.component)}:{participant.value}"
        )

    @staticmethod
    def _rule_versions(
        request: StockFortuneEvaluationRequest,
        *,
        temporal_context,
        luck_cycle: FortuneLuckCycleContext,
        bazi_engine_version: str,
        config_version: str,
        market_session_version: str,
    ) -> FortuneRuleVersions:
        return FortuneRuleVersions(
            snapshot_rule_version=FORTUNE_SNAPSHOT_RULE_VERSION,
            birth_profile_version=request.birth_profile.birth_profile_version,
            birth_rule_version=request.birth_profile.rule_version,
            market_session_version=(
                temporal_context.market_session_version
                if temporal_context and temporal_context.market_session_version
                else market_session_version or "unavailable"
            ),
            temporal_resolution_rule_version=FORTUNE_TEMPORAL_RESOLUTION_RULE_VERSION,
            calendar_engine_version=(
                temporal_context.calendar_snapshot.engine_version
                if temporal_context
                else settings.calendar_engine_version
            ),
            bazi_engine_version=bazi_engine_version,
            luck_cycle_direction_rule_version=luck_cycle.rule_version
            or FORTUNE_LUCK_CYCLE_RULE_VERSION,
            luck_cycle_period_rule_version=luck_cycle.period_rule_version
            or FORTUNE_LUCK_CYCLE_PERIOD_RULE_VERSION,
            ten_god_rule_version=settings.ten_god_rule_version,
            relation_rule_version=settings.relation_rule_version,
            relation_matrix_schema_version=settings.relation_matrix_schema_version,
            config_version=config_version or "unavailable",
        )

    @staticmethod
    def _provenance(
        request: StockFortuneEvaluationRequest,
        *,
        temporal_context,
        natal_chart: object,
        bazi_engine_version: str,
        bazi_assumptions: Sequence[Assumption],
        luck_cycle: FortuneLuckCycleContext,
        ten_god_context: FortuneTenGodContext,
        relation_context: FortuneRelationContext,
    ) -> list[FortuneProvenanceRecord]:
        records = [
            FortuneProvenanceRecord(
                component=FortuneProvenanceComponent.STOCK_IDENTITY,
                source=request.stock_identity.source,
                source_version=request.stock_identity.source_version,
                rule_version="stock-identity-v1",
            ),
            FortuneProvenanceRecord(
                component=FortuneProvenanceComponent.BIRTH_PROFILE,
                source=request.birth_profile.source,
                source_version=request.birth_profile.source_version,
                rule_version=request.birth_profile.rule_version,
                assumptions=request.birth_profile.assumptions,
            ),
            FortuneProvenanceRecord(
                component=FortuneProvenanceComponent.EVALUATION_TIME,
                source=request.evaluation_source,
                source_version=request.evaluation_source_version,
                rule_version=FORTUNE_TEMPORAL_RESOLUTION_RULE_VERSION,
                assumptions=temporal_context.assumptions if temporal_context else [],
            ),
        ]
        if temporal_context:
            snapshot = temporal_context.calendar_snapshot
            records.append(
                FortuneProvenanceRecord(
                    component=FortuneProvenanceComponent.CALENDAR,
                    source=snapshot.source,
                    source_version=snapshot.engine_version,
                    rule_version=snapshot.engine_version,
                    assumptions=StockFortuneEngine._calendar_assumptions(snapshot),
                )
            )
        if natal_chart:
            records.append(
                FortuneProvenanceRecord(
                    component=FortuneProvenanceComponent.BAZI,
                    source=SourceRef(source="smx-bazi-native"),
                    source_version=bazi_engine_version,
                    rule_version=bazi_engine_version,
                    assumptions=list(bazi_assumptions),
                )
            )
        evidence = request.luck_cycle_evidence
        records.append(
            FortuneProvenanceRecord(
                component=FortuneProvenanceComponent.LUCK_CYCLE,
                source=(
                    evidence.source
                    if evidence and evidence.source
                    else luck_cycle.polarity_source
                ),
                source_version=(
                    evidence.source_version
                    if evidence and evidence.source_version.strip()
                    else luck_cycle.polarity_source_version or "unknown"
                ),
                rule_version=luck_cycle.rule_version,
                assumptions=luck_cycle.assumptions,
            )
        )
        records.append(
            FortuneProvenanceRecord(
                component=FortuneProvenanceComponent.TEN_GOD,
                source=SourceRef(source="src.core.relations.ten_god"),
                source_version=ten_god_context.rule_version,
                rule_version=ten_god_context.rule_version,
            )
        )
        records.append(
            FortuneProvenanceRecord(
                component=FortuneProvenanceComponent.RELATION,
                source=SourceRef(source="src.core.relations.date_relation"),
                source_version=relation_context.rule_version,
                rule_version=relation_context.rule_version,
            )
        )
        return records

    @staticmethod
    def _calendar_assumptions(calendar) -> list[Assumption]:
        return [
            Assumption(
                key=f"calendar.assumption.{index}",
                value=value,
                reason="来自 CalendarEngine 对当前历法口径的记录",
                impact="对本次 calendar snapshot 的解释与复算有影响",
            )
            for index, value in enumerate(calendar.assumptions, start=1)
        ]
