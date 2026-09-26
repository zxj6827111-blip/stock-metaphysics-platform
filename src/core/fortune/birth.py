"""Fortune 首笔成交观测、出生时刻解析与精度分级。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.core.fortune.market_sessions import AShareMarketSessionAdapter
from src.core.fortune.ports import MarketSessionAdapter
from src.core.schemas.common import Assumption, Exchange
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservation,
    FirstTradeObservationResolution,
    FirstTradeObservationStatus,
    FORTUNE_BIRTH_PROFILE_VERSION,
    FORTUNE_BIRTH_RESOLUTION_RULE_VERSION,
    FORTUNE_MARKET_SESSION_POLICY_VERSION,
    FortuneBirthBasis,
    NatalPillarAvailability,
    StockFortuneBirthProfile,
)


def resolve_market_first_trade_profile(
    *,
    symbol: str,
    exchange: Exchange,
    observation: FirstTradeObservation,
    listing_date: date | None,
    config_version: str,
    market_session_version: str,
    market_session_adapter: MarketSessionAdapter | None = None,
) -> StockFortuneBirthProfile:
    """解析 FirstTradeProvider 的观测；绝不以 listing_date 补齐缺失观测。"""

    shared = {
        "symbol": symbol,
        "exchange": exchange,
        "listing_date": listing_date,
        "birth_basis": FortuneBirthBasis.MARKET_FIRST_TRADE,
        "source": observation.source,
        "source_version": observation.source_version,
        "birth_profile_version": FORTUNE_BIRTH_PROFILE_VERSION,
        "rule_version": FORTUNE_BIRTH_RESOLUTION_RULE_VERSION,
        "config_version": config_version,
    }

    if observation.status == FirstTradeObservationStatus.UNAVAILABLE:
        return StockFortuneBirthProfile(
            **shared,
            first_trade_datetime=None,
            first_trade_date=None,
            first_trade_resolution=FirstTradeObservationResolution.UNKNOWN,
            birth_datetime=None,
            timezone=observation.timezone,
            birth_time_precision=BirthTimePrecision.UNKNOWN,
            assumptions=[
                Assumption(
                    key="fortune.birth.first_trade_unavailable",
                    value=observation.reason,
                    reason="没有可靠首个交易日期或已验证首笔观测时间",
                    impact="不从 listing_date、IPO 元数据或任意时间回填出生时刻",
                )
            ],
        )

    if observation.status == FirstTradeObservationStatus.VERIFIED_DATETIME:
        assert observation.first_trade_datetime is not None
        assert observation.first_trade_date is not None
        precision = (
            BirthTimePrecision.MINUTE
            if observation.resolution == FirstTradeObservationResolution.MINUTE_BAR
            else BirthTimePrecision.EXACT
        )
        return StockFortuneBirthProfile(
            **shared,
            first_trade_datetime=observation.first_trade_datetime,
            first_trade_date=observation.first_trade_date,
            first_trade_resolution=observation.resolution,
            birth_datetime=observation.first_trade_datetime,
            timezone=observation.timezone,
            birth_time_precision=precision,
        )

    assert observation.first_trade_date is not None
    if exchange not in {Exchange.SSE, Exchange.SZSE, Exchange.BSE}:
        return _date_only_profile(
            shared=shared,
            observation=observation,
            reason="存在可靠日线日期，但交易所未知或没有对应 market-session 配置",
        )
    if not market_session_version.strip() or not config_version.strip():
        return _date_only_profile(
            shared=shared,
            observation=observation,
            reason="存在可靠日线日期，但缺少可追溯的交易时段配置版本",
        )

    try:
        session_adapter = market_session_adapter or AShareMarketSessionAdapter()
        session, matched_key = session_adapter.resolve_open_session(
            exchange, observation.first_trade_date
        )
        timezone = ZoneInfo(session.timezone)
    except (FileNotFoundError, LookupError, ValueError, KeyError):
        return _date_only_profile(
            shared=shared,
            observation=observation,
            reason="存在可靠日线日期，但无法解析该日期适用的交易时段",
        )

    inferred_at = datetime.combine(
        observation.first_trade_date,
        session.open_time,
        tzinfo=timezone,
    )
    market_version = (
        f"{FORTUNE_MARKET_SESSION_POLICY_VERSION}:"
        f"{market_session_version}:{config_version}"
    )
    source = observation.source.model_copy(
        update={
            "extra": {
                **observation.source.extra,
                "birth_datetime_method": "market_session_open_inferred",
                "observation_resolution": getattr(
                    observation.resolution, "value", str(observation.resolution)
                ),
                "session_source": session.source,
                "session_lookup_key": matched_key,
                "market_session_version": market_version,
            }
        }
    )
    assumptions = [
        Assumption(
            key="fortune.birth.first_trade_date",
            value=observation.first_trade_date.isoformat(),
            reason="该日期来自真实日线 bar 的最早可观测日期，不代表已观测到首笔成交时间",
            impact="若日线源的历史覆盖不完整，出生日期与后续排盘需要按新来源重算",
        ),
        Assumption(
            key="fortune.birth.market_session_open",
            value=f"{session.open_time.isoformat()} {session.timezone}",
            reason="用该日期适用的版本化交易时段开盘时刻解析出生时间",
            impact="结果是 INFERRED birth datetime；first_trade_datetime 仍为空",
        ),
    ]
    return StockFortuneBirthProfile(
        **{**shared, "source": source},
        first_trade_datetime=None,
        first_trade_date=observation.first_trade_date,
        first_trade_resolution=observation.resolution,
        birth_datetime=inferred_at,
        timezone=session.timezone,
        birth_time_precision=BirthTimePrecision.INFERRED,
        market_session_version=market_version,
        assumptions=assumptions,
    )


def _date_only_profile(
    *,
    shared: dict[str, object],
    observation: FirstTradeObservation,
    reason: str,
) -> StockFortuneBirthProfile:
    assumptions = [
        Assumption(
            key="fortune.birth.first_trade_date",
            value=observation.first_trade_date.isoformat() if observation.first_trade_date else "",
            reason="日线只提供最早可观测交易日期",
            impact="缺少已版本化 session 时刻，因此不生成时柱或 birth datetime",
        ),
    ]
    source = observation.source.model_copy(
        update={
            "extra": {
                **observation.source.extra,
                "birth_datetime_method": "date_only",
                "resolution_note": reason,
            }
        }
    )
    return StockFortuneBirthProfile(
        **{**shared, "source": source},
        first_trade_datetime=None,
        first_trade_date=observation.first_trade_date,
        first_trade_resolution=observation.resolution,
        birth_datetime=None,
        timezone=observation.timezone,
        birth_time_precision=BirthTimePrecision.DATE_ONLY,
        assumptions=assumptions,
    )


def natal_pillar_availability(
    precision: BirthTimePrecision,
) -> NatalPillarAvailability:
    """只按时间精度声明可用柱数，不负责排盘或推造缺失时辰。"""

    if precision in {
        BirthTimePrecision.EXACT,
        BirthTimePrecision.MINUTE,
        BirthTimePrecision.INFERRED,
    }:
        return NatalPillarAvailability.FOUR_PILLARS
    if precision == BirthTimePrecision.DATE_ONLY:
        return NatalPillarAvailability.THREE_PILLARS
    return NatalPillarAvailability.UNAVAILABLE
