"""基于真实日线日期构造 Fortune 首笔成交观测的行情 Adapter。"""

from __future__ import annotations

from src.core.schemas.common import MarketDataSource, SourceRef
from src.core.schemas.fortune import (
    FirstTradeObservation,
    FirstTradeObservationResolution,
    FirstTradeObservationStatus,
)
from src.market.normalization.errors import MarketDataError
from src.market.providers.base import MarketDataProvider


class DailyBarFirstTradeProvider:
    """从最早真实日线 bar 提供日期级观测；不推定时间、不读上市元数据。"""

    def __init__(self, market_data: MarketDataProvider, *, source_version: str) -> None:
        if not source_version.strip():
            raise ValueError("日线首笔观测 Adapter 必须显式提供 source_version")
        self._market_data = market_data
        self._source_version = source_version

    def observe_first_trade(self, symbol: str) -> FirstTradeObservation:
        provider_id = getattr(self._market_data, "provider_id", "unknown")
        try:
            series = self._market_data.get_daily_bars(symbol, start=None, end=None)
        except MarketDataError as exc:
            return FirstTradeObservation(
                status=FirstTradeObservationStatus.UNAVAILABLE,
                source=SourceRef(
                    source=f"market-provider:{provider_id}",
                    extra={"error_code": exc.code, "message": exc.message},
                ),
                source_version=self._source_version,
                reason=exc.message,
            )

        source = series.source_ref
        source_name = source.source.strip().lower()
        if (
            series.is_degraded
            or series.source in {MarketDataSource.SYNTHETIC_DEMO, MarketDataSource.UNAVAILABLE}
            or source_name.startswith("synthetic")
        ):
            return FirstTradeObservation(
                status=FirstTradeObservationStatus.UNAVAILABLE,
                source=source,
                source_version=self._source_version,
                reason="降级或合成行情不能作为首个观测交易日期证据",
            )

        dates = [bar.trade_date for bar in series.bars]
        if not dates:
            return FirstTradeObservation(
                status=FirstTradeObservationStatus.UNAVAILABLE,
                source=source,
                source_version=self._source_version,
                reason="行情源没有可验证的日线 bar；不回退到 listing_date 或 IPO 元数据",
            )

        earliest = min(dates)
        return FirstTradeObservation(
            status=FirstTradeObservationStatus.OBSERVED_TRADING_DATE,
            first_trade_date=earliest,
            resolution=FirstTradeObservationResolution.DAILY_BAR,
            source=source.model_copy(
                update={
                    "extra": {
                        **source.extra,
                        "provider_id": provider_id,
                        "observed_bar_count": len(dates),
                        "date_semantics": "earliest_observed_trading_date",
                    }
                }
            ),
            source_version=self._source_version,
            reason="最早日线 bar 只证明最早观测交易日期，不证明首笔成交时刻",
        )
