"""MarketDataProvider 抽象（architecture §13）。

**硬性约束**

* 业务层只能通过本接口获取行情；**禁止**在业务代码里 ``import akshare``。
* 第三方数据必须归一化成 ``Bar`` / ``StockMaster`` 标准结构。
* 第三方失败时必须：retry → 结构化错误 → 缓存兜底 → 显式降级，
  绝不允许整个应用直接崩溃，也绝不允许把降级数据伪装成真实数据。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.core.schemas.market import BarSeries
from src.core.schemas.stock import StockMaster
from src.market.normalization.errors import MarketDataError  # noqa: F401  便于外部统一捕获


class MarketDataProvider(ABC):
    """行情数据提供者契约。"""

    provider_id: str = "base"

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> list[StockMaster]:
        """按代码 / 名称 / 拼音搜索股票。"""

    @abstractmethod
    def get_stock(self, code: str) -> StockMaster:
        """获取单只股票基础资料。"""

    @abstractmethod
    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "qfq",
    ) -> BarSeries:
        """获取日线行情。"""

    @abstractmethod
    def get_benchmark_bars(
        self,
        index_code: str = "000300",
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "qfq",
    ) -> BarSeries:
        """获取基准指数日线（默认沪深300）。"""

    def close(self) -> None:  # noqa: B027  # 刻意空方法：有资源的子类自行覆盖
        """释放资源。默认无操作。"""
