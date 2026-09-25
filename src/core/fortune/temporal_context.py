"""通过唯一 CalendarSnapshot 组装 Fortune 时间上下文。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.fortune.market_sessions import AShareMarketSessionAdapter
from src.core.fortune.ports import CalendarSnapshotProvider, MarketSessionAdapter
from src.core.schemas.common import Assumption, Exchange
from src.core.schemas.fortune import (
    FORTUNE_MARKET_SESSION_POLICY_VERSION,
    FortuneTemporalInput,
    FortuneTemporalInputKind,
    FortuneTemporalResolution,
    FortuneTemporalResolutionMethod,
    FortuneTemporalResolutionStatus,
    TemporalFortuneContext,
)


def build_temporal_context(
    target_at: datetime,
    calendar_provider: CalendarSnapshotProvider,
    *,
    timezone: str = "Asia/Shanghai",
) -> TemporalFortuneContext:
    """历法只调用一次；年月日时全部由同一个快照提供。"""

    if target_at.tzinfo is None or target_at.utcoffset() is None:
        raise ValueError("target_at 必须带时区")
    local_at = target_at.astimezone(ZoneInfo(timezone))
    snapshot = calendar_provider.snapshot(local_at.replace(tzinfo=None))
    return TemporalFortuneContext(
        target_at=local_at,
        timezone=timezone,
        calendar_snapshot=snapshot,
    )


def resolve_temporal_input(
    temporal_input: FortuneTemporalInput,
    calendar_provider: CalendarSnapshotProvider,
    *,
    timezone: str = "Asia/Shanghai",
    market_session_version: str = "",
    config_version: str = "",
    market_session_adapter: MarketSessionAdapter | None = None,
) -> FortuneTemporalResolution:
    """把三种调用语义显式解析；纯自然日期绝不静默补时。"""

    if temporal_input.kind == FortuneTemporalInputKind.CIVIL_DATE_ONLY:
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.TIME_REQUIRED,
            requested_date=temporal_input.target_date,
            reason="纯自然日期不能在 23:00 日界规则下代表唯一全天四柱",
        )

    if temporal_input.kind == FortuneTemporalInputKind.EXACT_DATETIME:
        assert temporal_input.target_datetime is not None
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.RESOLVED,
            context=build_temporal_context(
                temporal_input.target_datetime,
                calendar_provider,
                timezone=timezone,
            ),
        )

    if temporal_input.is_trading_day is None:
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.TIME_REQUIRED,
            requested_date=temporal_input.target_date,
            reason="MARKET_SESSION_DATE 缺少该日期为交易日的证据",
        )
    if temporal_input.is_trading_day is False:
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.NON_TRADING_DAY,
            requested_date=temporal_input.target_date,
            reason="指定日期不是已确认的交易日，不能使用市场开盘时刻锚定",
        )
    if temporal_input.target_date is not None and temporal_input.target_date.weekday() >= 5:
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.UNAVAILABLE,
            requested_date=temporal_input.target_date,
            reason="周末日期与 is_trading_day=true 的证据冲突",
        )
    if not market_session_version.strip() or not config_version.strip():
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.UNAVAILABLE,
            requested_date=temporal_input.target_date,
            reason="缺少可追溯的 market-session 或 config 版本",
        )

    assert temporal_input.target_date is not None
    exchange = temporal_input.exchange
    assert exchange is not None
    if exchange not in {Exchange.SSE, Exchange.SZSE, Exchange.BSE}:
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.UNAVAILABLE,
            requested_date=temporal_input.target_date,
            reason="当前 market-session date resolver 只支持 A 股交易所",
        )

    try:
        session_adapter = market_session_adapter or AShareMarketSessionAdapter()
        session, matched_key = session_adapter.resolve_open_session(
            exchange, temporal_input.target_date
        )
        local_at = datetime.combine(
            temporal_input.target_date,
            session.open_time,
            tzinfo=ZoneInfo(session.timezone),
        )
    except (FileNotFoundError, LookupError, ValueError, KeyError):
        return FortuneTemporalResolution(
            input_kind=temporal_input.kind,
            status=FortuneTemporalResolutionStatus.UNAVAILABLE,
            requested_date=temporal_input.target_date,
            reason="无法解析该日期适用的交易所开盘时刻",
        )

    local_at = local_at.astimezone(ZoneInfo(timezone))
    snapshot = calendar_provider.snapshot(local_at.replace(tzinfo=None))
    version = (
        f"{FORTUNE_MARKET_SESSION_POLICY_VERSION}:"
        f"{market_session_version}:{config_version}"
    )
    context = TemporalFortuneContext(
        target_at=local_at,
        timezone=timezone,
        calendar_snapshot=snapshot,
        temporal_resolution=FortuneTemporalResolutionMethod.MARKET_SESSION_INFERRED,
        market_session_version=version,
        assumptions=[
            Assumption(
                key="fortune.temporal.market_session_anchor",
                value=f"{session.open_time.isoformat()} {session.timezone}",
                reason="调用方明确提供交易日场景；时间锚点来自版本化交易所 session 配置",
                impact="该时间为 MARKET_SESSION_INFERRED，不是 exact datetime 或全自然日语义",
            ),
            Assumption(
                key="fortune.temporal.market_session_source",
                value=f"{session.source} ({matched_key})",
                reason="记录开盘时刻的配置来源与解析键",
                impact=f"market session version={version}",
            ),
        ],
    )
    return FortuneTemporalResolution(
        input_kind=temporal_input.kind,
        status=FortuneTemporalResolutionStatus.RESOLVED,
        context=context,
        requested_date=temporal_input.target_date,
    )
