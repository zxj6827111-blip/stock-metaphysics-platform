"""Fortune 出生资料的最小派生与精度分级。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.core.schemas.common import Assumption, Exchange, SourceRef
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FORTUNE_BIRTH_PROFILE_VERSION,
    FortuneBirthBasis,
    NatalPillarAvailability,
    StockFortuneBirthProfile,
)
from src.core.stock.exchange_sessions import resolve_session


FORTUNE_LISTING_OPEN_RULE_VERSION = "fortune-listing-open-inference-v1"


def infer_a_share_listing_open_profile(
    *,
    symbol: str,
    exchange: Exchange,
    listing_date: date,
    listing_source: SourceRef,
    source_version: str,
    confidence: float | None,
    config_version: str,
) -> StockFortuneBirthProfile:
    """用已配置的交易所开盘时刻推定出生时间，不伪称实际首笔成交。"""

    if exchange not in {Exchange.SSE, Exchange.SZSE, Exchange.BSE}:
        raise ValueError("A 股上市开盘推定必须明确交易所，UNKNOWN 不可推定")

    session, matched_key = resolve_session(exchange, on_date=listing_date)
    timezone = ZoneInfo(session.timezone)
    inferred_at = datetime.combine(listing_date, session.open_time, tzinfo=timezone)
    assumptions = [
        Assumption(
            key="fortune.birth.market_first_trade.date",
            value=listing_date.isoformat(),
            reason="当前只有上市日期；此推定把该日期作为首个公开交易日",
            impact="若上市日与首个正式交易日不一致，出生日期与后续盘面都需重算",
        ),
        Assumption(
            key="fortune.birth.market_first_trade.time",
            value=f"inferred_exchange_open:{session.open_time.isoformat()}",
            reason="缺少首笔实际成交时间，使用版本化交易时段配置中的开盘时刻",
            impact="这是 INFERRED 时间，不是历史成交事实；真实首笔成交证据可覆盖",
        ),
    ]
    return StockFortuneBirthProfile(
        symbol=symbol,
        exchange=exchange,
        listing_date=listing_date,
        first_trade_datetime=None,
        birth_basis=FortuneBirthBasis.MARKET_FIRST_TRADE,
        birth_datetime=inferred_at,
        timezone=session.timezone,
        birth_time_precision=BirthTimePrecision.INFERRED,
        source=SourceRef(
            source="derived:a_share_listing_open",
            extra={
                "listing_source": listing_source.source,
                "listing_source_extra": listing_source.extra,
                "session_source": session.source,
                "session_lookup_key": matched_key,
            },
        ),
        source_version=source_version,
        confidence=confidence,
        birth_profile_version=FORTUNE_BIRTH_PROFILE_VERSION,
        rule_version=FORTUNE_LISTING_OPEN_RULE_VERSION,
        config_version=config_version,
        assumptions=assumptions,
    )


def natal_pillar_availability(
    precision: BirthTimePrecision,
) -> NatalPillarAvailability:
    """只按时间精度声明可用柱数，不负责排盘或推造缺失时辰。"""

    if precision in {BirthTimePrecision.EXACT, BirthTimePrecision.INFERRED}:
        return NatalPillarAvailability.FOUR_PILLARS
    if precision == BirthTimePrecision.DATE_ONLY:
        return NatalPillarAvailability.THREE_PILLARS
    return NatalPillarAvailability.UNAVAILABLE
