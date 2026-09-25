"""Fortune Engine 与现有历法、市场时段及研究层之间的端口。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Mapping, Protocol, Sequence

from src.core.schemas.calendar import CalendarSnapshot
from src.core.schemas.common import Exchange
from src.core.schemas.fortune import FirstTradeObservation, MarketSessionAssessment
from src.core.schemas.stock import ExchangeSession


class FirstTradeProvider(Protocol):
    """只提供首次成交的观测证据，不负责推定出生时刻。"""

    def observe_first_trade(self, symbol: str) -> FirstTradeObservation: ...


class CalendarSnapshotProvider(Protocol):
    """只接受项目自己的 CalendarSnapshot，不暴露第三方历法对象。"""

    def snapshot(self, when: datetime) -> CalendarSnapshot: ...


class MarketSessionAdapter(Protocol):
    """解析版本化 session 锚点，并把时刻分类为独立的市场状态。"""

    def resolve_open_session(
        self,
        exchange: Exchange,
        on_date: date,
    ) -> tuple[ExchangeSession, str]: ...

    def classify(
        self,
        target_at: datetime,
        exchange: Exchange,
        *,
        is_trading_day: bool | None,
    ) -> MarketSessionAssessment: ...


class MarketContext(Protocol):
    """预留的市场上下文：不进入 F1 规则因子，也不改写传统术数结果。"""

    @property
    def as_of(self) -> datetime: ...

    @property
    def source_versions(self) -> Mapping[str, str]: ...

    @property
    def facts(self) -> Mapping[str, object]: ...


class MarketContextProvider(Protocol):
    def get_context(self, *, as_of: datetime) -> MarketContext: ...


class HistoricalFinancialEvidence(Protocol):
    """独立金融统计证据；不能回写 Fortune 规则或 RuleScore。"""

    @property
    def research_status(self) -> str: ...

    @property
    def evidence_refs(self) -> Sequence[str]: ...


class HistoricalFinancialEvidenceProvider(Protocol):
    def evaluate(
        self,
        *,
        factor_ids: Sequence[str],
        start_at: datetime,
        end_at: datetime,
        as_of: datetime,
    ) -> HistoricalFinancialEvidence: ...
