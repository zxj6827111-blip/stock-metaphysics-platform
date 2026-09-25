from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.constants import STEM_YANG
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
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    FortuneTemporalResolutionStatus,
    NatalPillarAvailability,
    StockFortuneBirthProfile,
    StockFortuneEvaluationRequest,
    StockFortuneIdentity,
)
from src.core.orchestration.stock_fortune import StockFortuneEngine


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
