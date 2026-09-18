"""行情层结构化错误类型。

设计目标：所有第三方失败都能被转换成**可展示、可诊断**的结构化错误，
而不是把 traceback 抛给用户。
"""

from __future__ import annotations


class MarketDataError(Exception):
    """行情层基础错误。"""

    code = "MARKET_ERROR"
    http_status = 502

    def __init__(self, message: str, *, detail: str = "", retryable: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.retryable = retryable

    def to_payload(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
                "retryable": self.retryable,
                "source": "market",
            }
        }


class ProviderUnavailableError(MarketDataError):
    """第三方数据源不可达（网络/代理/限流）。"""

    code = "MARKET_PROVIDER_UNAVAILABLE"
    http_status = 503


class SymbolNotFoundError(MarketDataError):
    """股票代码无法识别或不存在。"""

    code = "STOCK_NOT_FOUND"
    http_status = 404

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message, detail=detail, retryable=False)


class InsufficientDataError(MarketDataError):
    """数据不足（如新上市股票历史太短）。"""

    code = "MARKET_INSUFFICIENT_DATA"
    http_status = 422

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message, detail=detail, retryable=False)


class FutureDataAccessError(MarketDataError):
    """检测到未来数据泄漏 —— 这是 P0 级错误，必须直接失败。"""

    code = "FUTURE_DATA_ACCESS"
    http_status = 500

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message, detail=detail, retryable=False)
