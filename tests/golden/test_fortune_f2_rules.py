from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.fortune.luck_cycle import (
    compatibility_variant_mode,
    resolve_first_day_yinyang_luck_cycle,
)
from src.core.schemas.common import Exchange, SourceRef, VariantMode
from src.core.schemas.fortune import (
    CompatibilityGender,
    FortuneAvailability,
    FortunePolarity,
    FORTUNE_LUCK_CYCLE_RULE_VERSION,
    LuckCycleDirection,
)

pytestmark = pytest.mark.golden


@pytest.mark.parametrize(
    (
        "first_day_yinyang",
        "birth_year_stem",
        "polarity",
        "compatibility_gender",
        "direction",
        "variant_mode",
    ),
    [
        (
            "阳", "甲", FortunePolarity.YANG, CompatibilityGender.MALE,
            LuckCycleDirection.FORWARD, VariantMode.FORWARD,
        ),
        (
            "阳", "乙", FortunePolarity.YANG, CompatibilityGender.MALE,
            LuckCycleDirection.REVERSE, VariantMode.FORWARD,
        ),
        (
            "阴", "甲", FortunePolarity.YIN, CompatibilityGender.FEMALE,
            LuckCycleDirection.REVERSE, VariantMode.REVERSE,
        ),
        (
            "阴", "乙", FortunePolarity.YIN, CompatibilityGender.FEMALE,
            LuckCycleDirection.FORWARD, VariantMode.REVERSE,
        ),
    ],
)
def test_stock_luck_cycle_research_convention_golden(
    first_day_yinyang,
    birth_year_stem,
    polarity,
    compatibility_gender,
    direction,
    variant_mode,
) -> None:
    source = SourceRef(
        source="stock_master.first_day_yinyang",
        extra={"semantic": "first session close direction"},
    )
    kwargs = dict(
        first_day_yinyang=first_day_yinyang,
        polarity_observation_date=date(2024, 11, 15),
        polarity_is_trading_day=True,
        source=source,
        source_version="stock-master-first-day-v1",
        market_session_version="a-share-session-v1:v1",
        exchange=Exchange.SSE,
        birth_year_stem=birth_year_stem,
        as_of=datetime(2024, 11, 15, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    result = resolve_first_day_yinyang_luck_cycle(**kwargs)
    replay = resolve_first_day_yinyang_luck_cycle(**kwargs)

    assert result.availability == FortuneAvailability.AVAILABLE
    assert result.polarity == polarity
    assert result.compatibility_gender == compatibility_gender
    assert result.direction == direction
    assert result.rule_version == FORTUNE_LUCK_CYCLE_RULE_VERSION
    assert result.market_session_version == (
        "fortune-market-session-anchor-v1:a-share-session-v1:v1"
    )
    assert result.polarity_observation_date == date(2024, 11, 15)
    assert result.polarity_observed_at == datetime(
        2024, 11, 15, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert compatibility_variant_mode(result) == variant_mode
    assert result.assumptions
    assert result.model_dump(mode="json") == replay.model_dump(mode="json")
