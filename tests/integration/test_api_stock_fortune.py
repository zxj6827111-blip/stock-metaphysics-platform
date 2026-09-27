"""F4 typed Research API integration smoke tests."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.core.schemas.common import Exchange, SourceRef
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservationResolution,
    FortuneBirthBasis,
    FortuneScanTemporalMode,
    StockFortuneBirthProfile,
    StockFortuneIdentity,
    StockFortuneScanRequest,
    StockFortuneScanTarget,
    StockFortuneScanUniverse,
    StockFortuneTimelineRequest,
)

pytestmark = pytest.mark.integration


def _profile(symbol: str) -> StockFortuneBirthProfile:
    birth_at = datetime.fromisoformat("2001-08-27T09:30:00+08:00")
    return StockFortuneBirthProfile(
        symbol=symbol,
        exchange=Exchange.SSE,
        first_trade_date=date(2001, 8, 27),
        first_trade_datetime=birth_at,
        first_trade_resolution=FirstTradeObservationResolution.TRADE,
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        birth_datetime=birth_at,
        timezone="Asia/Shanghai",
        birth_time_precision=BirthTimePrecision.EXACT,
        source=SourceRef(source="integration-fixture-profile"),
        source_version="integration-profile-v1",
        birth_profile_version="stock-fortune-birth-v2",
        market_session_version="a-share-session-v1",
        config_version="integration-config-v1",
    )


def _identity(symbol: str) -> StockFortuneIdentity:
    return StockFortuneIdentity(
        symbol=symbol,
        exchange=Exchange.SSE,
        name=f"测试证券 {symbol}",
        source=SourceRef(source="integration-fixture-stock-master"),
    )


def test_stock_fortune_timeline_api_returns_typed_stable_and_varying_context(client) -> None:
    request = StockFortuneTimelineRequest(
        stock_identity=_identity("600519"),
        birth_profile=_profile("600519"),
        start_date=date(2025, 1, 10),
        end_date=date(2025, 1, 11),
    )

    response = client.post(
        "/api/v1/research/fortune/timeline",
        json=request.model_dump(mode="json", exclude_computed_fields=True),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract_version"] == "stock-fortune-timeline-v1"
    assert body["stable_context"]["natal_context"]["pillars"]["day"]
    assert [item["date"] for item in body["points"]] == ["2025-01-10", "2025-01-11"]
    assert body["points"][0]["daily_pillar"]["text"]


def test_stock_fortune_cross_section_api_returns_typed_page(client) -> None:
    target = StockFortuneScanTarget(
        stock_identity=_identity("600519"),
        birth_profile=_profile("600519"),
    )
    request = StockFortuneScanRequest(
        temporal_mode=FortuneScanTemporalMode.DATE_SCAN_NOON,
        evaluation_date=date(2025, 1, 10),
        universe=StockFortuneScanUniverse(
            version="integration-universe-v1",
            source=SourceRef(source="integration-explicit-universe"),
            targets=[target],
        ),
        limit=1,
        offset=0,
    )

    response = client.post(
        "/api/v1/research/fortune/scan",
        json=request.model_dump(mode="json", exclude_computed_fields=True),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract_version"] == "stock-fortune-cross-section-v1"
    assert body["total_examined"] == body["total_matched"] == body["total"] == 1
    assert body["limit"] == 1 and body["offset"] == 0
    assert body["items"][0]["symbol"] == "600519"
    assert body["items"][0]["snapshot_ref"]
