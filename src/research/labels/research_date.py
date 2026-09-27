"""新研究路径的交易观察日期解析。

研究锚点必须由实测或已交叉核验的交易所日历确认。对非交易日向后对齐时，
返回中保留原锚点、落点、来源和日历指纹，调用方必须把该映射纳入产物。
未知交易所、日历越界及周末规则降级均 fail closed。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.core.stock.trading_calendar import (
    KNOWN_SOURCES,
    TradingCalendarProvider,
    get_trading_calendar_provider,
)


@dataclass(frozen=True)
class ResearchDateResolution:
    requested_date: date
    research_date: date | None
    exchange: str
    source: str
    calendar_version: str
    status: str
    reason: str = ""

    @property
    def available(self) -> bool:
        return self.research_date is not None and self.source in KNOWN_SOURCES


def resolve_research_date(
    requested_date: date,
    exchange: str,
    *,
    provider: TradingCalendarProvider | None = None,
) -> ResearchDateResolution:
    """解析到当日或之后首个已验证交易日；不接受日历降级猜测。"""
    exchange_key = str(exchange or "UNKNOWN").strip().upper()
    calendar = (provider or get_trading_calendar_provider()).for_exchange(exchange_key)
    query = calendar.next_trading_day(requested_date)
    if query.value is None or query.source not in KNOWN_SOURCES:
        return ResearchDateResolution(
            requested_date=requested_date,
            research_date=None,
            exchange=exchange_key,
            source=query.source,
            calendar_version=calendar.version_token,
            status="UNAVAILABLE",
            reason=query.degraded_reason or "无已验证的交易日期证据",
        )
    resolved = query.value
    return ResearchDateResolution(
        requested_date=requested_date,
        research_date=resolved,
        exchange=exchange_key,
        source=query.source,
        calendar_version=calendar.version_token,
        status="EXACT" if resolved == requested_date else "SHIFTED",
        reason=query.degraded_reason,
    )


__all__ = ["ResearchDateResolution", "resolve_research_date"]
