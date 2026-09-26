"""A 股 MarketSession Adapter；传统时辰仍只由 CalendarEngine 计算。"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.core.schemas.common import Exchange
from src.core.schemas.fortune import MarketSessionAssessment, MarketSessionStatus
from src.core.schemas.stock import ExchangeSession
from src.core.stock.exchange_sessions import resolve_session


class AShareMarketSessionAdapter:
    """按 A 股正常时段分类；未知交易日时不推断开市。"""

    source = "a_share_session_adapter"
    source_version = "a-share-session-v1"
    timezone = "Asia/Shanghai"
    morning = (time(9, 30), time(11, 30))
    afternoon = (time(13, 0), time(15, 0))
    supported_exchanges = {Exchange.SSE, Exchange.SZSE, Exchange.BSE}

    def __init__(
        self,
        *,
        morning: tuple[time, time] | None = None,
        afternoon: tuple[time, time] | None = None,
        source_version: str | None = None,
    ) -> None:
        self._morning = morning or self.morning
        self._afternoon = afternoon or self.afternoon
        if self._morning[1] > self._afternoon[0]:
            raise ValueError("A 股 session 区间不得重叠")
        if self._morning[1] <= self._morning[0] or self._afternoon[1] <= self._afternoon[0]:
            raise ValueError("A 股 session 区间必须在同一自然日内递增")
        if self._afternoon[0] < self._morning[0]:
            raise ValueError("A 股下午 session 必须晚于上午 session")
        self.source_version = source_version or self.source_version

    def classify(
        self,
        target_at: datetime,
        exchange: Exchange,
        *,
        is_trading_day: bool | None,
    ) -> MarketSessionAssessment:
        if target_at.tzinfo is None or target_at.utcoffset() is None:
            raise ValueError("target_at 必须带时区")
        if exchange not in self.supported_exchanges:
            raise ValueError("A 股时段 Adapter 需要明确 SSE/SZSE/BSE 交易所")

        local_at = target_at.astimezone(ZoneInfo(self.timezone))
        local_time = local_at.timetz().replace(tzinfo=None)
        if local_at.weekday() >= 5:
            if is_trading_day is True:
                raise ValueError("A 股周末与交易日证据冲突，必须先核对交易日来源")
            return self._assessment(
                local_at,
                exchange,
                MarketSessionStatus.CLOSED,
                False,
                "自然周末；自然日历照常由 CalendarEngine 计算",
            )
        if is_trading_day is False:
            return self._assessment(
                local_at, exchange, MarketSessionStatus.CLOSED, False, "交易日数据标记为非交易日"
            )
        if self._morning[1] <= local_time < self._afternoon[0]:
            status = (
                MarketSessionStatus.BREAK
                if is_trading_day is True
                else MarketSessionStatus.UNKNOWN
            )
            return self._assessment(
                local_at,
                exchange,
                status,
                False,
                "午间时段没有连续交易；只有确认交易日后才标记 BREAK，传统午时由 CalendarEngine 独立提供",
            )

        in_session = any(
            start <= local_time < end
            for start, end in (self._morning, self._afternoon)
        )
        if not in_session:
            return self._assessment(
                local_at, exchange, MarketSessionStatus.CLOSED, False, "时刻不在 A 股连续交易区间"
            )
        if is_trading_day is None:
            return self._assessment(
                local_at, exchange, MarketSessionStatus.UNKNOWN, None, "缺少该自然日是否开市的交易日历证据"
            )
        return self._assessment(
            local_at, exchange, MarketSessionStatus.CONTINUOUS_TRADING, True, "交易日且处于连续交易区间"
        )

    def resolve_open_session(
        self,
        exchange: Exchange,
        on_date: date,
    ) -> tuple[ExchangeSession, str]:
        """按冻结配置解析指定交易所与日期的开盘锚点。"""

        if exchange not in self.supported_exchanges:
            raise ValueError("A 股时段 Adapter 需要明确 SSE/SZSE/BSE 交易所")
        return resolve_session(exchange, on_date=on_date)

    def _assessment(
        self,
        target_at: datetime,
        exchange: Exchange,
        status: MarketSessionStatus,
        tradable: bool | None,
        reason: str,
    ) -> MarketSessionAssessment:
        return MarketSessionAssessment(
            exchange=exchange,
            target_at=target_at,
            status=status,
            tradable=tradable,
            source=self.source,
            source_version=self.source_version,
            reason=reason,
        )
