from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.core.orchestration.stock_fortune import StockFortuneEngine
from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import Exchange, SourceRef, VariantMode
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservationResolution,
    FortuneAvailability,
    FortuneBirthBasis,
    FortuneContextKind,
    FortuneRelationComponent,
    FortuneRelationScope,
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    StockFortuneBirthProfile,
    StockFortuneEvaluationRequest,
    StockFortuneIdentity,
)
from src.core.relations.date_relation import relation_events_for_external_pillar
from src.engines.calendar.calendar_engine import CalendarEngine
from src.engines.bazi.bazi_engine import BaziEngine


pytestmark = pytest.mark.golden
SHANGHAI = ZoneInfo("Asia/Shanghai")


class MemoryArtifactWriter:
    def persist_chart_artifact(self, **kwargs) -> str:
        return f"golden-{kwargs['engine_id']}-{kwargs['symbol']}-{kwargs['as_of']:%Y%m%d%H%M%S}"


def _date_only_profile() -> StockFortuneBirthProfile:
    return StockFortuneBirthProfile(
        symbol="600519",
        exchange=Exchange.SSE,
        first_trade_date=date(2010, 1, 4),
        first_trade_resolution=FirstTradeObservationResolution.DAILY_BAR,
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        birth_datetime=None,
        timezone="Asia/Shanghai",
        birth_time_precision=BirthTimePrecision.DATE_ONLY,
        source=SourceRef(source="verified-daily-provider"),
        source_version="daily-bars-v1",
    )


def _request(evaluation: FortuneTemporalInput) -> StockFortuneEvaluationRequest:
    return StockFortuneEvaluationRequest(
        stock_identity=StockFortuneIdentity(
            symbol="600519",
            exchange=Exchange.SSE,
            source=SourceRef(source="golden-stock-master"),
        ),
        birth_profile=_date_only_profile(),
        evaluation_context=evaluation,
        evaluation_source=SourceRef(source="golden-input"),
        market_session_version="a-share-session-v1",
        config_version=settings.config_version,
    )


@pytest.mark.parametrize("hour, minute", [(22, 59), (23, 0), (23, 1)])
def test_snapshot_reuses_calendar_exact_day_boundary(hour: int, minute: int) -> None:
    calendar = CalendarEngine()
    when = datetime(2024, 11, 15, hour, minute, tzinfo=SHANGHAI)
    snapshot = StockFortuneEngine(MemoryArtifactWriter(), calendar=calendar).evaluate(
        _request(
            FortuneTemporalInput(
                kind=FortuneTemporalInputKind.EXACT_DATETIME,
                target_datetime=when,
            )
        )
    )
    expected = calendar.snapshot(when.replace(tzinfo=None))

    assert snapshot.evaluation_time == when
    assert snapshot.daily_context.pillar == expected.day_ganzhi
    assert snapshot.temporal_context is not None
    assert snapshot.temporal_context.flow_hour == expected.hour_ganzhi
    assert snapshot.natal_context.availability == FortuneAvailability.UNAVAILABLE


def test_market_session_date_is_explicitly_inferred_at_versioned_open() -> None:
    snapshot = StockFortuneEngine(
        MemoryArtifactWriter(), calendar=CalendarEngine()
    ).evaluate(
        _request(
            FortuneTemporalInput(
                kind=FortuneTemporalInputKind.MARKET_SESSION_DATE,
                target_date=date(2024, 11, 15),
                exchange=Exchange.SSE,
                is_trading_day=True,
            )
        )
    )

    assert snapshot.temporal_context is not None
    assert snapshot.temporal_context.temporal_resolution == "market_session_inferred"
    assert snapshot.evaluation_time == datetime(2024, 11, 15, 9, 30, tzinfo=SHANGHAI)
    assert snapshot.temporal_context.assumptions


def test_luck_cycle_periods_are_replayable_for_both_explicit_directions() -> None:
    engine = BaziEngine(CalendarEngine())
    birth = datetime(2001, 8, 27, 9, 30, tzinfo=SHANGHAI)

    forward = engine.build_luck_cycle_periods(birth, VariantMode.FORWARD, count=4)
    forward_replay = engine.build_luck_cycle_periods(birth, VariantMode.FORWARD, count=4)
    reverse = engine.build_luck_cycle_periods(birth, VariantMode.REVERSE, count=4)

    assert len(forward) == len(reverse) == 4
    assert [item.model_dump(mode="json") for item in forward] == [
        item.model_dump(mode="json") for item in forward_replay
    ]
    assert forward[0].ganzhi != reverse[0].ganzhi
    for periods in (forward, reverse):
        assert [item.index for item in periods] == [1, 2, 3, 4]
        assert all(item.start_at < item.end_at for item in periods)
        assert all(
            periods[index].end_at == periods[index + 1].start_at
            for index in range(len(periods) - 1)
        )


@pytest.mark.parametrize(
    "relation_type,source_text,target_text,component,source_value,target_value",
    [
        ("天干五合", "甲子", "己丑", FortuneRelationComponent.STEM, "甲", "己"),
        ("天干相冲", "甲子", "庚寅", FortuneRelationComponent.STEM, "甲", "庚"),
        ("天干克", "甲子", "戊辰", FortuneRelationComponent.STEM, "甲", "戊"),
        ("六合", "甲子", "乙丑", FortuneRelationComponent.BRANCH, "子", "丑"),
        ("六冲", "甲子", "丙午", FortuneRelationComponent.BRANCH, "子", "午"),
        ("相刑", "甲寅", "丙巳", FortuneRelationComponent.BRANCH, "寅", "巳"),
        ("相害", "甲子", "丙未", FortuneRelationComponent.BRANCH, "子", "未"),
        ("六破", "甲子", "丙酉", FortuneRelationComponent.BRANCH, "子", "酉"),
    ],
)
def test_supported_relation_events_keep_exact_source_and_target(
    relation_type: str,
    source_text: str,
    target_text: str,
    component: FortuneRelationComponent,
    source_value: str,
    target_value: str,
) -> None:
    source = GanZhi.from_text(source_text)
    target = GanZhi.from_text(target_text)
    natal = {
        "year": target,
        "month": GanZhi.from_text("乙卯"),
        "day": GanZhi.from_text("丙辰"),
    }
    raw_events = relation_events_for_external_pillar(
        source,
        "day",
        natal,
        day_master="丙",
    )
    events = StockFortuneEngine._external_relation_events(
        source,
        FortuneContextKind.DAY,
        "day",
        natal,
        "丙",
    )
    matching = [item for item in events if item.relation_type == relation_type]

    assert any(item.relation_type == relation_type for item in raw_events)
    assert matching
    assert matching[0].source.context == FortuneContextKind.DAY
    assert matching[0].source.pillar == "day"
    assert matching[0].source.component == component
    assert matching[0].source.value == source_value
    assert matching[0].target.context == FortuneContextKind.NATAL
    assert matching[0].target.pillar == "year"
    assert matching[0].target.component == component
    assert matching[0].target.value == target_value
    assert matching[0].scope == FortuneRelationScope.TEMPORAL_TO_NATAL
    assert matching[0].rule_version == settings.relation_rule_version
