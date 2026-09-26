from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from time import perf_counter
from zoneinfo import ZoneInfo

import pytest

from src.core.constants import STEM_YANG
from src.core.orchestration.stock_fortune import StockFortuneEngine
from src.core.orchestration.stock_fortune_scan import (
    RequestScopedCalendarSnapshotCache,
    StockFortuneCrossSectionScanner,
)
from src.core.orchestration.stock_fortune_timeline import StockFortuneTimelineEngine
from src.core.relations.ten_god import hidden_stems_with_gods, ten_god_ref
from src.core.schemas.bazi import (
    BaziChart,
    BaziLuckCyclePeriod,
    DayMasterAnalysis,
    HiddenStem,
    PatternAnalysis,
    Pillar,
    RelationHit,
    TemporalPillar,
    WuxingStrength,
    YongShenAnalysis,
)
from src.core.schemas.calendar import (
    CalendarSnapshot,
    GanZhi,
    LunarDate,
    SolarDate,
)
from src.core.schemas.common import Assumption, Availability, Exchange, SourceRef, VariantMode
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservationResolution,
    FortuneAvailability,
    FortuneBirthBasis,
    FortuneContextKind,
    FortuneLuckCycleEvidence,
    FortuneRelationCategory,
    FortuneRelationComponent,
    FortuneRelationEvent,
    FortuneRelationFilter,
    FortuneRelationParticipant,
    FortuneRelationScope,
    FortuneScanTemporalMode,
    FortuneTenGodFilter,
    FortuneTenGodLayer,
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    FortuneTemporalResolutionStatus,
    FortuneTimelineDateMode,
    NatalPillarAvailability,
    StockFortuneBirthProfile,
    StockFortuneEvaluationRequest,
    StockFortuneIdentity,
    StockFortuneScanRequest,
    StockFortuneScanTarget,
    StockFortuneScanUniverse,
    StockFortuneTimelineRequest,
)
from src.core.stock.trading_calendar import TradingCalendar


SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeCalendar:
    def __init__(self) -> None:
        self.calls: list[datetime] = []

    def snapshot(self, when: datetime) -> CalendarSnapshot:
        self.calls.append(when)
        return CalendarSnapshot(
            engine_version="calendar-test-v1",
            solar=SolarDate(
                date=when.date(), timestamp=when, year=when.year, month=when.month,
                day=when.day, hour=when.hour, minute=when.minute,
            ),
            lunar=LunarDate(year=2024, month=10, day=15, text="测试农历"),
            year_ganzhi=GanZhi.from_text("甲辰"),
            month_ganzhi=GanZhi.from_text("乙亥"),
            day_ganzhi=GanZhi.from_text("癸未"),
            hour_ganzhi=GanZhi.from_text("己未"),
            assumptions=["测试历法假设"],
            source=SourceRef(source="test-calendar"),
        )


class FakeArtifactWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def persist_chart_artifact(self, **kwargs) -> str:
        engine_id = kwargs["engine_id"]
        stable = json.dumps(
            {
                "engine_id": engine_id,
                "symbol": kwargs["symbol"],
                "as_of": kwargs["as_of"].isoformat(),
                "input": kwargs["input_payload"],
                "raw": kwargs["raw_chart"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.calls.append((engine_id, dict(kwargs["raw_chart"])))
        return f"{engine_id}-{hashlib.sha256(stable).hexdigest()[:16]}"


def _pillar(position: str, value: str, day_master: str) -> Pillar:
    ganzhi = GanZhi.from_text(value)
    hidden = [
        HiddenStem(
            stem=item.stem,
            ten_god=item.ten_god,
            wuxing=item.wuxing,
            weight=item.weight or 0.0,
            rank=item.rank,
        )
        for item in hidden_stems_with_gods(day_master, ganzhi.branch)
    ]
    return Pillar(
        position=position,
        ganzhi=ganzhi,
        stem_ten_god=("日主" if position == "day" else ten_god_ref(day_master, ganzhi.stem).ten_god),
        hidden_stems=hidden,
        hidden_ten_gods=[item.ten_god for item in hidden],
    )


def _temporal(kind: str, ganzhi: GanZhi, day_master: str) -> TemporalPillar:
    return TemporalPillar(
        kind=kind,
        label=ganzhi.text,
        ganzhi=ganzhi,
        stem_ten_god=ten_god_ref(day_master, ganzhi.stem).ten_god,
        branch_ten_gods=[
            item.ten_god for item in hidden_stems_with_gods(day_master, ganzhi.branch)
        ],
    )


class FakeBazi:
    metadata = type("Metadata", (), {"engine_version": "bazi-test-v1"})()

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.cycle = BaziLuckCyclePeriod(
            index=2,
            start_year=2020,
            end_year=2029,
            start_age=32,
            end_age=41,
            ganzhi="乙巳",
            start_at=datetime(2020, 1, 2, 9, 0, tzinfo=SHANGHAI),
            end_at=datetime(2030, 1, 2, 9, 0, tzinfo=SHANGHAI),
        )

    def build_chart(
        self,
        *,
        birth_datetime: datetime,
        as_of: datetime,
        variant_mode: VariantMode,
        stock_code: str,
        natal_snapshot: CalendarSnapshot,
        reference_snapshot: CalendarSnapshot,
    ) -> BaziChart:
        self.calls.append(
            {
                "birth_datetime": birth_datetime,
                "as_of": as_of,
                "variant_mode": variant_mode,
                "natal_snapshot": natal_snapshot,
                "reference_snapshot": reference_snapshot,
            }
        )
        day_master = "丙"
        year = _pillar("year", "甲子", day_master)
        month = _pillar("month", "乙丑", day_master)
        day = _pillar("day", "丙寅", day_master)
        hour = _pillar("hour", "丁卯", day_master)
        return BaziChart(
            stock_code=stock_code,
            birth_datetime=birth_datetime,
            year_pillar=year,
            month_pillar=month,
            day_pillar=day,
            hour_pillar=hour,
            day_master=day_master,
            day_master_wuxing="火",
            wuxing=WuxingStrength(),
            day_master_analysis=DayMasterAnalysis(
                day_master=day_master,
                day_master_wuxing="火",
                day_master_yang=STEM_YANG[day_master],
            ),
            pattern=PatternAnalysis(primary="测试格", category="测试"),
            yong_shen=YongShenAnalysis(),
            relations=[
                RelationHit(
                    relation_type="六合",
                    positions=["year", "month"],
                    branches_or_stems=["子", "丑"],
                    note="原局年支子与月支丑六合",
                )
            ],
            current_year_pillar=_temporal(
                "year", reference_snapshot.year_ganzhi, day_master
            ),
            current_month_pillar=_temporal(
                "month", reference_snapshot.month_ganzhi, day_master
            ),
            current_day_pillar=_temporal(
                "day", reference_snapshot.day_ganzhi, day_master
            ),
            assumptions=[
                Assumption(
                    key="bazi.variant_mode",
                    value=variant_mode.value,
                    reason="显式方向兼容参数",
                    impact="仅用于大运研究上下文",
                )
            ],
            engine_id="bazi",
            engine_version="bazi-test-v1",
            config_version="cfg-test",
            calculated_at=datetime.now(tz=SHANGHAI),
            availability=Availability.OK,
            source=SourceRef(source="test-bazi"),
        )

    def build_luck_cycle_periods(
        self,
        birth_datetime: datetime,
        variant_mode: VariantMode,
    ) -> list[BaziLuckCyclePeriod]:
        assert variant_mode in {VariantMode.FORWARD, VariantMode.REVERSE}
        return [self.cycle]


def _profile(precision: BirthTimePrecision = BirthTimePrecision.INFERRED):
    if precision == BirthTimePrecision.DATE_ONLY:
        return StockFortuneBirthProfile(
            symbol="600519",
            exchange=Exchange.SSE,
            first_trade_date=date(2010, 1, 4),
            first_trade_resolution=FirstTradeObservationResolution.DAILY_BAR,
            birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
            birth_datetime=None,
            timezone="Asia/Shanghai",
            birth_time_precision=precision,
            source=SourceRef(source="verified-daily-provider"),
            source_version="daily-bars-v1",
        )
    birth = datetime(1988, 1, 4, 9, 30, tzinfo=SHANGHAI)
    inferred = precision == BirthTimePrecision.INFERRED
    return StockFortuneBirthProfile(
        symbol="600519",
        exchange=Exchange.SSE,
        first_trade_date=birth.date(),
        first_trade_resolution=(
            FirstTradeObservationResolution.DAILY_BAR
            if inferred
            else FirstTradeObservationResolution.TRADE
        ),
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        first_trade_datetime=None if inferred else birth,
        birth_datetime=birth,
        timezone="Asia/Shanghai",
        birth_time_precision=precision,
        source=SourceRef(source="verified-market-provider"),
        source_version="market-source-v1",
        market_session_version="a-share-session-v1",
        config_version="cfg-test",
        assumptions=(
            [
                {
                    "key": "fortune.birth.market_session_open",
                    "value": "09:30:00 Asia/Shanghai",
                    "reason": "测试中的 F2 显式推定",
                    "impact": "推定时间仍须标记 INFERRED",
                }
            ]
            if inferred
            else []
        ),
    )


def _request(
    profile: StockFortuneBirthProfile | None = None,
    *,
    temporal: FortuneTemporalInput | None = None,
    include_luck_evidence: bool = True,
) -> StockFortuneEvaluationRequest:
    return StockFortuneEvaluationRequest(
        stock_identity=StockFortuneIdentity(
            symbol="600519",
            exchange=Exchange.SSE,
            name="测试证券",
            source=SourceRef(source="stock-master"),
        ),
        birth_profile=profile or _profile(),
        evaluation_context=temporal
        or FortuneTemporalInput(
            kind=FortuneTemporalInputKind.EXACT_DATETIME,
            target_datetime=datetime(2025, 1, 10, 10, 30, tzinfo=SHANGHAI),
        ),
        evaluation_source=SourceRef(source="test-input"),
        luck_cycle_evidence=(
            FortuneLuckCycleEvidence(
                first_day_yinyang="阳",
                observation_date=date(2024, 11, 15),
                is_trading_day=True,
                source=SourceRef(source="stock_master.first_day_yinyang"),
                source_version="stock-master-first-day-v1",
                market_session_version="a-share-session-v1",
            )
            if include_luck_evidence
            else None
        ),
        market_session_version="a-share-session-v1",
        config_version="cfg-test",
    )


def test_snapshot_contract_complete_and_replayable_without_runtime_clock() -> None:
    calendar = FakeCalendar()
    bazi = FakeBazi()
    writer = FakeArtifactWriter()
    engine = StockFortuneEngine(writer, calendar=calendar, bazi=bazi)
    request = _request()

    snapshot = engine.evaluate(request)
    replay = engine.evaluate(request)

    assert snapshot.availability == FortuneAvailability.AVAILABLE
    assert snapshot.temporal_resolution.status == FortuneTemporalResolutionStatus.RESOLVED
    assert snapshot.natal_context.pillars.availability == NatalPillarAvailability.FOUR_PILLARS
    assert {item.position for item in snapshot.natal_context.hidden_stems} == {
        "year", "month", "day", "hour"
    }
    assert snapshot.luck_cycle_context.direction is not None
    assert snapshot.luck_cycle_context.current_cycle is not None
    assert snapshot.luck_cycle_context.cycle_index == 2
    assert snapshot.luck_cycle_context.stem == "乙"
    assert snapshot.luck_cycle_context.branch == "巳"
    assert snapshot.annual_context.pillar == GanZhi.from_text("甲辰")
    assert snapshot.monthly_context.pillar == GanZhi.from_text("乙亥")
    assert snapshot.daily_context.pillar == GanZhi.from_text("癸未")
    assert snapshot.ten_god_context.availability == FortuneAvailability.AVAILABLE
    assert len(snapshot.ten_god_context.natal) == 4
    assert snapshot.ten_god_context.annual is not None
    assert snapshot.ten_god_context.monthly is not None
    assert snapshot.ten_god_context.daily is not None
    assert snapshot.ten_god_context.hidden_stems
    assert len(snapshot.natal_context.hidden_stems) == len(
        snapshot.ten_god_context.hidden_stems
    )
    assert snapshot.relation_context.relation_count == len(snapshot.relation_context.events)
    assert any(
        event.source.context == FortuneContextKind.DAYUN
        and event.target.context == FortuneContextKind.NATAL
        for event in snapshot.relation_context.events
    )
    assert "calculated_at" not in snapshot.raw_chart["bazi"]
    provenance_components = {item.component for item in snapshot.provenance}
    assert {
        "stock_identity",
        "birth_profile",
        "evaluation_time",
        "calendar",
        "bazi",
        "luck_cycle",
        "ten_god",
        "relation",
    } <= provenance_components
    assert all(item.source_version and item.rule_version for item in snapshot.provenance)
    bazi_provenance = next(
        item for item in snapshot.provenance if item.component == "bazi"
    )
    assert any(item.key == "bazi.variant_mode" for item in bazi_provenance.assumptions)
    assert any(item.key == "bazi.variant_mode" for item in snapshot.assumptions)
    calendar_provenance = next(
        item for item in snapshot.provenance if item.component == "calendar"
    )
    assert calendar_provenance.assumptions[0].value == "测试历法假设"
    assert snapshot.chart_artifact_ids == replay.chart_artifact_ids
    assert snapshot.model_dump(mode="json") == replay.model_dump(mode="json")
    assert len(snapshot.chart_artifact_ids) == 2
    assert {call[0] for call in writer.calls} == {"calendar", "bazi"}
    assert calendar.calls.count(datetime(2025, 1, 10, 10, 30)) == 2
    for field_name in snapshot.rule_versions.model_fields:
        assert getattr(snapshot.rule_versions, field_name)


def test_inferred_birth_is_preserved_without_claiming_first_trade_time() -> None:
    engine = StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi())
    snapshot = engine.evaluate(_request(_profile(BirthTimePrecision.INFERRED)))

    assert snapshot.birth_profile.birth_time_precision == BirthTimePrecision.INFERRED
    assert snapshot.birth_profile.first_trade_datetime is None
    assert snapshot.natal_context.availability == FortuneAvailability.AVAILABLE


def test_missing_luck_evidence_keeps_other_contexts_and_marks_relations_partial() -> None:
    snapshot = StockFortuneEngine(
        FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi()
    ).evaluate(_request(include_luck_evidence=False))

    assert snapshot.availability == FortuneAvailability.PARTIAL
    assert snapshot.natal_context.availability == FortuneAvailability.AVAILABLE
    assert snapshot.ten_god_context.availability == FortuneAvailability.AVAILABLE
    assert snapshot.luck_cycle_context.availability == FortuneAvailability.UNAVAILABLE
    assert snapshot.luck_cycle_context.current_cycle is None
    assert snapshot.relation_context.availability == FortuneAvailability.PARTIAL
    assert snapshot.relation_context.events


def test_date_only_birth_keeps_flow_context_but_does_not_fill_birth_time() -> None:
    bazi = FakeBazi()
    snapshot = StockFortuneEngine(
        FakeArtifactWriter(), calendar=FakeCalendar(), bazi=bazi
    ).evaluate(_request(_profile(BirthTimePrecision.DATE_ONLY)))

    assert snapshot.availability == FortuneAvailability.PARTIAL
    assert snapshot.birth_profile.birth_datetime is None
    assert snapshot.natal_context.availability == FortuneAvailability.UNAVAILABLE
    assert "birth_datetime" in snapshot.luck_cycle_context.unavailability_reason
    assert snapshot.annual_context.availability == FortuneAvailability.AVAILABLE
    assert "bazi" not in snapshot.raw_chart
    assert len(snapshot.chart_artifact_ids) == 1
    assert bazi.calls == []
    assert any(warning.code == "FORTUNE_NATAL_BIRTH_TIME_UNAVAILABLE" for warning in snapshot.warnings)


def test_civil_date_only_evaluation_returns_time_required_without_calendar_calls() -> None:
    calendar = FakeCalendar()
    bazi = FakeBazi()
    request = _request(
        temporal=FortuneTemporalInput(
            kind=FortuneTemporalInputKind.CIVIL_DATE_ONLY,
            target_date=date(2025, 1, 10),
        )
    )
    snapshot = StockFortuneEngine(
        FakeArtifactWriter(), calendar=calendar, bazi=bazi
    ).evaluate(request)

    assert snapshot.availability == FortuneAvailability.UNAVAILABLE
    assert snapshot.temporal_resolution.status == FortuneTemporalResolutionStatus.TIME_REQUIRED
    assert snapshot.evaluation_time is None
    assert snapshot.temporal_context is None
    assert snapshot.natal_context.availability == FortuneAvailability.UNAVAILABLE
    assert calendar.calls == []
    assert bazi.calls == []
    assert snapshot.chart_artifact_ids == []


def test_luck_cycle_uses_half_open_cycle_transition_boundaries() -> None:
    bazi = FakeBazi()
    engine = StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=bazi)
    request = _request()
    luck = engine._resolve_luck_cycle(
        request,
        birth_year_stem="甲",
        evaluation_time=datetime(2025, 1, 10, 10, 30, tzinfo=SHANGHAI),
    )
    cycle = bazi.cycle
    birth_at = datetime(1988, 1, 4, 9, 30, tzinfo=SHANGHAI)
    mode = VariantMode.FORWARD

    before, _ = engine._resolve_current_cycle(
        luck,
        birth_at=birth_at,
        evaluation_time=cycle.start_at - timedelta(seconds=1),
        variant_mode=mode,
    )
    at_start, _ = engine._resolve_current_cycle(
        luck,
        birth_at=birth_at,
        evaluation_time=cycle.start_at,
        variant_mode=mode,
    )
    at_end, _ = engine._resolve_current_cycle(
        luck,
        birth_at=birth_at,
        evaluation_time=cycle.end_at,
        variant_mode=mode,
    )

    assert before.current_cycle is None
    assert at_start.current_cycle is not None
    assert at_end.current_cycle is None
    assert at_start.start_basis.startswith("lunar-python-1.4.8")
    assert at_start.period_rule_version == "fortune-dayun-period-lunar-python-1.4.8-v1"


class StaticTradingCalendarProvider:
    def __init__(self, calendar: TradingCalendar) -> None:
        self.calendar = calendar

    def for_exchange(self, exchange: str) -> TradingCalendar:
        return self.calendar


def _timeline_request(
    start: date,
    end: date | None = None,
    *,
    date_mode: FortuneTimelineDateMode = FortuneTimelineDateMode.ALL_CALENDAR_DAYS,
    evaluation_time: time = time(12, 0),
    **overrides,
) -> StockFortuneTimelineRequest:
    snapshot_request = _request()
    return StockFortuneTimelineRequest(
        stock_identity=snapshot_request.stock_identity,
        birth_profile=snapshot_request.birth_profile,
        start_date=start,
        end_date=end or start,
        date_mode=date_mode,
        evaluation_time=evaluation_time,
        luck_cycle_evidence=snapshot_request.luck_cycle_evidence,
        include_month_segments=False,
        **overrides,
    )


def _scan_target(symbol: str, profile: StockFortuneBirthProfile | None = None) -> StockFortuneScanTarget:
    base = profile or _profile()
    return StockFortuneScanTarget(
        stock_identity=StockFortuneIdentity(
            symbol=symbol,
            exchange=Exchange.SSE,
            name=f"测试证券 {symbol}",
            source=SourceRef(source="test-stock-master"),
        ),
        birth_profile=base.model_copy(update={"symbol": symbol}),
        luck_cycle_evidence=_request().luck_cycle_evidence,
    )


def _scan_request(
    targets: list[StockFortuneScanTarget],
    *,
    ten_god_filters: list[FortuneTenGodFilter] | None = None,
    relation_filters: list[FortuneRelationFilter] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> StockFortuneScanRequest:
    return StockFortuneScanRequest(
        temporal_mode=FortuneScanTemporalMode.DATE_SCAN_NOON,
        evaluation_date=date(2025, 1, 10),
        universe=StockFortuneScanUniverse(
            version="test-universe-v1",
            source=SourceRef(source="test-universe"),
            targets=targets,
        ),
        ten_god_filters=ten_god_filters or [],
        relation_filters=relation_filters or [],
        limit=limit,
        offset=offset,
    )


def test_f4_timeline_stable_context_and_replay_are_deterministic() -> None:
    calendar = FakeCalendar()
    bazi = FakeBazi()
    engine = StockFortuneTimelineEngine(
        StockFortuneEngine(FakeArtifactWriter(), calendar=calendar, bazi=bazi)
    )
    request = _timeline_request(date(2025, 1, 10), date(2025, 1, 12))

    first = engine.build(request)
    replay = engine.build(request)

    assert [point.date for point in first.points] == [
        date(2025, 1, 10), date(2025, 1, 11), date(2025, 1, 12)
    ]
    assert first.model_dump(mode="json") == replay.model_dump(mode="json")
    assert len(first.stable_context.natal_ten_gods) == 4
    assert first.stable_context.hidden_stem_ten_gods
    assert len(first.stable_context.chart_artifact_ids) == 2
    assert first.rule_versions.snapshot_rule_version
    assert {item.component for item in first.provenance} >= {
        "stock_identity", "birth_profile", "evaluation_time", "calendar", "bazi", "ten_god", "relation"
    }
    assert len(bazi.calls) == 2  # 每次 Timeline 只建一次原局，不按日期重复
    assert all(point.availability == FortuneAvailability.AVAILABLE for point in first.points)


def test_f4_timeline_ten_god_filters_keep_each_layer_explicit() -> None:
    engine = StockFortuneTimelineEngine(
        StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi())
    )
    baseline = engine.build(_timeline_request(date(2025, 1, 10)))
    point = baseline.points[0]

    for layer, observation in (
        (FortuneTenGodLayer.ANNUAL, point.annual_ten_god),
        (FortuneTenGodLayer.MONTHLY, point.monthly_ten_god),
        (FortuneTenGodLayer.DAILY, point.daily_ten_god),
    ):
        assert observation is not None
        filtered = engine.build(
            _timeline_request(
                date(2025, 1, 10),
                ten_god_filters=[FortuneTenGodFilter(layer=layer, ten_god=observation.display_label)],
            )
        )
        assert [item.date for item in filtered.points] == [date(2025, 1, 10)]

    # 日柱的展示标签为“日主”，筛选语义必须读其 TenGodRef（比肩），不是展示标签。
    natal_day = next(item for item in baseline.stable_context.natal_ten_gods if item.position == "day")
    assert natal_day.stem is not None
    natal_filtered = engine.build(
        _timeline_request(
            date(2025, 1, 10),
            ten_god_filters=[
                FortuneTenGodFilter(layer=FortuneTenGodLayer.NATAL, position="day", ten_god=natal_day.stem.ten_god)
            ],
        )
    )
    assert len(natal_filtered.points) == 1

    unmatched = engine.build(
        _timeline_request(
            date(2025, 1, 10),
            ten_god_filters=[
                FortuneTenGodFilter(
                    layer=FortuneTenGodLayer.DAILY,
                    ten_god=next(
                        value
                        for value in ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印")
                        if value != point.daily_ten_god.display_label
                    ),
                )
            ],
        )
    )
    assert unmatched.points == []
    assert unmatched.availability == FortuneAvailability.AVAILABLE

    hidden = baseline.stable_context.hidden_stem_ten_gods[0]
    hidden_filtered = engine.build(
        _timeline_request(
            date(2025, 1, 10),
            ten_god_filters=[
                FortuneTenGodFilter(
                    layer=FortuneTenGodLayer.HIDDEN_STEM,
                    position=hidden.pillar,
                    hidden_stem=hidden.stem.stem,
                    ten_god=hidden.stem.ten_god,
                )
            ],
        )
    )
    assert len(hidden_filtered.points) == 1


def test_f4_timeline_relation_filter_matches_structured_participants() -> None:
    engine = StockFortuneTimelineEngine(
        StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi())
    )
    baseline = engine.build(_timeline_request(date(2025, 1, 10)))
    event = next(
        item
        for item in baseline.points[0].relation_events
        if item.relation_type == "六合"
        and item.source.context == FortuneContextKind.MONTH
        and item.target.context == FortuneContextKind.NATAL
        and item.target.pillar == "day"
    )
    condition = FortuneRelationFilter(
        relation_type=event.relation_type,
        source_context=event.source.context,
        source_pillar=event.source.pillar,
        target_context=event.target.context,
        target_pillar=event.target.pillar,
        source_component=event.source.component,
        target_component=event.target.component,
    )

    filtered = engine.build(
        _timeline_request(date(2025, 1, 10), relation_filters=[condition])
    )
    assert len(filtered.points) == 1
    match = next(
        item for item in filtered.points[0].relation_events
        if item.relation_type == condition.relation_type
    )
    assert match.source.context == condition.source_context
    assert match.source.pillar == condition.source_pillar == "month"
    assert match.target.context == condition.target_context == FortuneContextKind.NATAL
    assert match.target.pillar == condition.target_pillar == "day"


@pytest.mark.parametrize(
    ("relation_type", "component", "category"),
    [
        ("天干五合", FortuneRelationComponent.STEM, FortuneRelationCategory.COMBINATION),
        ("天干克", FortuneRelationComponent.STEM, FortuneRelationCategory.OTHER),
        ("天干相冲", FortuneRelationComponent.STEM, FortuneRelationCategory.CLASH),
        ("六合", FortuneRelationComponent.BRANCH, FortuneRelationCategory.COMBINATION),
        ("六冲", FortuneRelationComponent.BRANCH, FortuneRelationCategory.CLASH),
        ("相刑", FortuneRelationComponent.BRANCH, FortuneRelationCategory.PUNISHMENT),
        ("三刑", FortuneRelationComponent.BRANCH, FortuneRelationCategory.PUNISHMENT),
        ("自刑", FortuneRelationComponent.BRANCH, FortuneRelationCategory.PUNISHMENT),
        ("相害", FortuneRelationComponent.BRANCH, FortuneRelationCategory.HARM),
        ("六破", FortuneRelationComponent.BRANCH, FortuneRelationCategory.BREAK),
    ],
)
def test_f4_structured_relation_filter_supports_catalog_types(
    relation_type: str,
    component: FortuneRelationComponent,
    category: FortuneRelationCategory,
) -> None:
    source_value, target_value = (
        ("甲", "己") if component == FortuneRelationComponent.STEM else ("子", "午")
    )
    source = FortuneRelationParticipant(
        context=FortuneContextKind.DAY,
        pillar="day",
        component=component,
        value=source_value,
    )
    target = FortuneRelationParticipant(
        context=FortuneContextKind.NATAL,
        pillar="year",
        component=component,
        value=target_value,
    )
    event = FortuneRelationEvent(
        category=category,
        relation_type=relation_type,
        source=source,
        target=target,
        participants=[
            f"day:day:{component.value}:{source_value}",
            f"natal:year:{component.value}:{target_value}",
        ],
        scope=FortuneRelationScope.TEMPORAL_TO_NATAL,
        rule_version="test-relation-v1",
    )
    condition = FortuneRelationFilter(
        relation_type=relation_type,
        source_context=FortuneContextKind.DAY,
        source_pillar="day",
        target_context=FortuneContextKind.NATAL,
        target_pillar="year",
        source_component=component,
        target_component=component,
    )

    assert StockFortuneTimelineEngine._matches_relation(event, condition)
    assert not StockFortuneTimelineEngine._matches_relation(
        event, condition.model_copy(update={"target_pillar": "month"})
    )


def test_f4_trading_days_require_known_calendar_evidence() -> None:
    trading_days = frozenset(
        {date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 9), date(2025, 1, 10)}
    )
    provider = StaticTradingCalendarProvider(
        TradingCalendar(exchange="SSE", _days=trading_days, loaded=True)
    )
    engine = StockFortuneTimelineEngine(
        StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi()),
        trading_calendar_provider=provider,
    )
    request = _timeline_request(
        date(2025, 1, 6),
        date(2025, 1, 12),
        date_mode=FortuneTimelineDateMode.TRADING_DAYS_ONLY,
    )

    timeline = engine.build(request)

    assert [item.date for item in timeline.points] == sorted(trading_days)
    assert all(item.trading_day is True for item in timeline.points)
    assert all(item.trading_calendar_source == "observed_index_days" for item in timeline.points)
    assert timeline.trading_calendar.confirmed_trading_days == 4
    assert timeline.trading_calendar.confirmed_closed_days == 1
    assert timeline.trading_calendar.unknown_days == 2
    assert any(item.code == "TRADING_CALENDAR_COVERAGE_INCOMPLETE" for item in timeline.warnings)


def test_f4_trading_only_returns_empty_when_calendar_is_unverified() -> None:
    provider = StaticTradingCalendarProvider(
        TradingCalendar(exchange="SSE", loaded=False, load_error="test missing calendar")
    )
    engine = StockFortuneTimelineEngine(
        StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi()),
        trading_calendar_provider=provider,
    )
    timeline = engine.build(
        _timeline_request(
            date(2025, 1, 6),
            date_mode=FortuneTimelineDateMode.TRADING_DAYS_ONLY,
        )
    )

    assert timeline.points == []
    assert timeline.availability == FortuneAvailability.PARTIAL
    assert timeline.trading_calendar.unknown_days == 1
    assert any(item.code == "TRADING_CALENDAR_FALLBACK_REJECTED" for item in timeline.warnings)


def test_f4_structural_benchmark_one_stock_365_days(capsys, record_property) -> None:
    calendar = FakeCalendar()
    bazi = FakeBazi()
    engine = StockFortuneTimelineEngine(
        StockFortuneEngine(FakeArtifactWriter(), calendar=calendar, bazi=bazi)
    )

    started = perf_counter()
    timeline = engine.build(
        _timeline_request(
            date(2025, 1, 1),
            date(2025, 12, 31),
            include_ten_god_index=False,
        )
    )

    evaluation_calls = [call for call in calendar.calls if call.date().year == 2025]
    assert len(timeline.points) == 365
    assert len({item.date for item in timeline.points}) == 365
    assert len(evaluation_calls) == 365
    assert len(bazi.calls) == 1
    elapsed = perf_counter() - started
    record_property("f4_1_stock_365_days_elapsed_seconds", f"{elapsed:.6f}")
    with capsys.disabled():
        print(f"F4_PERF scenario=1_stock_x_365_days elapsed_seconds={elapsed:.6f}")


def test_f4_cross_section_filters_and_pagination_are_deterministic() -> None:
    targets = [
        _scan_target("600519"),
        _scan_target("000001"),
        _scan_target("000002", _profile(BirthTimePrecision.DATE_ONLY)),
    ]
    evaluator = StockFortuneEngine(FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi())
    sample = evaluator.evaluate(_request())
    daily_god = sample.ten_god_context.daily.display_label
    relation = FortuneRelationFilter(
        relation_type="六合",
        source_context=FortuneContextKind.MONTH,
        source_pillar="month",
        target_context=FortuneContextKind.NATAL,
        target_pillar="day",
        source_component=FortuneRelationComponent.BRANCH,
        target_component=FortuneRelationComponent.BRANCH,
    )
    scanner = StockFortuneCrossSectionScanner(
        FakeArtifactWriter(), calendar=FakeCalendar(), bazi=FakeBazi()
    )
    request = _scan_request(
        targets,
        ten_god_filters=[
            FortuneTenGodFilter(layer=FortuneTenGodLayer.DAILY, ten_god=daily_god)
        ],
        relation_filters=[relation],
        limit=1,
        offset=1,
    )

    response = scanner.scan(request)
    replay = scanner.scan(request)

    assert response.model_dump(mode="json") == replay.model_dump(mode="json")
    assert response.total_examined == 3
    assert response.total_matched == 2
    assert response.total == 2
    assert len(response.items) == 1
    assert response.items[0].symbol == "600519"
    assert [item.kind for item in response.items[0].matched_conditions] == ["ten_god", "relation"]
    assert response.items[0].availability == FortuneAvailability.AVAILABLE
    assert response.items[0].relevant_relation_events

    no_match = scanner.scan(
        _scan_request(
            targets,
            ten_god_filters=[
                FortuneTenGodFilter(
                    layer=FortuneTenGodLayer.DAILY,
                    ten_god=next(god for god in ("比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印") if god != daily_god),
                )
            ],
        )
    )
    assert no_match.total_matched == 0
    assert no_match.items == []


def test_f4_cross_section_structural_benchmark_100_stocks_one_date(capsys, record_property) -> None:
    calendar = FakeCalendar()
    bazi = FakeBazi()
    scanner = StockFortuneCrossSectionScanner(
        FakeArtifactWriter(), calendar=calendar, bazi=bazi
    )
    targets = [_scan_target(f"{600000 + index:06d}") for index in range(100)]

    started = perf_counter()
    response = scanner.scan(_scan_request(targets))
    elapsed = perf_counter() - started

    evaluation_at = datetime(2025, 1, 10, 12, 0)
    assert response.total_examined == 100
    assert len(bazi.calls) == 100  # 每只股票只构造一次稳定原局
    assert calendar.calls.count(evaluation_at) == 1  # 同日流柱共享一个 CalendarSnapshot
    assert len(calendar.calls) == 2  # 再加一份共享的同日出生参考盘
    record_property("f4_100_stocks_1_date_elapsed_seconds", f"{elapsed:.6f}")
    with capsys.disabled():
        print(f"F4_PERF scenario=100_stocks_x_1_date elapsed_seconds={elapsed:.6f}")


def test_f4_calendar_snapshot_cache_is_request_scoped() -> None:
    provider = FakeCalendar()
    cache = RequestScopedCalendarSnapshotCache(provider)
    evaluation_at = datetime(2025, 1, 10, 12, 0)

    cache.begin_request()
    cache.begin_evaluation()
    cache.snapshot(evaluation_at)
    cache.begin_request()
    cache.begin_evaluation()
    cache.snapshot(evaluation_at)

    assert provider.calls == [evaluation_at, evaluation_at]
    assert cache.calls == 1


def test_f4_market_session_scan_requires_verified_trading_calendar() -> None:
    target = _scan_target("600519")
    base = _scan_request([target])
    request = StockFortuneScanRequest(
        temporal_mode=FortuneScanTemporalMode.MARKET_SESSION_DATE,
        evaluation_date=date(2025, 1, 10),
        exchange=Exchange.SSE,
        is_trading_day=True,
        universe=base.universe,
        market_session_version="test-session-v1",
        config_version="cfg-test",
    )
    known_calendar = StaticTradingCalendarProvider(
        TradingCalendar(exchange="SSE", _days=frozenset({date(2025, 1, 10)}), loaded=True)
    )
    scanner = StockFortuneCrossSectionScanner(
        FakeArtifactWriter(),
        calendar=FakeCalendar(),
        bazi=FakeBazi(),
        trading_calendar_provider=known_calendar,
    )

    response = scanner.scan(request)

    assert response.trading_calendar_source == "observed_index_days"
    assert response.trading_calendar_version
    assert any(item.code == "FORTUNE_SCAN_TRADING_CALENDAR_VERIFIED" for item in response.warnings)

    unavailable = StaticTradingCalendarProvider(
        TradingCalendar(exchange="SSE", loaded=False, load_error="no calendar")
    )
    rejected = StockFortuneCrossSectionScanner(
        FakeArtifactWriter(),
        calendar=FakeCalendar(),
        bazi=FakeBazi(),
        trading_calendar_provider=unavailable,
    )
    with pytest.raises(ValueError, match="必须由已加载的实测/官方日历确认"):
        rejected.scan(request)
