"""API 层结构化错误与异常处理。

所有错误统一返回：

```json
{"error": {"code": "...", "message": "...", "detail": "...", "retryable": true}}
```

禁止把 traceback 直接暴露给前端。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.stock.birth_profile import BirthProfileError
from src.market.normalization.errors import MarketDataError

logger = logging.getLogger("smp.api")


class ApiError(Exception):
    """业务层通用错误。"""

    code = "API_ERROR"
    http_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, detail: str = "", retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.retryable = retryable


class NotFoundError(ApiError):
    code = "NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND


class EngineUnavailableError(ApiError):
    code = "ENGINE_UNAVAILABLE"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message, detail=detail, retryable=True)


class InvalidRequestError(ApiError):
    code = "INVALID_REQUEST"
    http_status = 422


def _payload(code: str, message: str, detail: str = "", retryable: bool = False,
             extra: dict[str, Any] | None = None) -> dict:
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "detail": detail,
            "retryable": retryable,
        }
    }
    if extra:
        body["error"]["context"] = extra
    return body


def install_exception_handlers(app: FastAPI) -> None:
    """注册统一异常处理。"""

    @app.exception_handler(MarketDataError)
    async def _market_error(_request: Request, exc: MarketDataError) -> JSONResponse:
        logger.warning("market error: %s | %s", exc.message, exc.detail)
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.detail, exc.retryable),
        )

    @app.exception_handler(BirthProfileError)
    async def _birth_error(_request: Request, exc: BirthProfileError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload("BIRTH_PROFILE_ERROR", str(exc), retryable=False),
        )

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_payload(exc.code, exc.message, exc.detail, exc.retryable),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(
                "VALIDATION_ERROR",
                "请求参数校验失败",
                detail=str(exc.errors()[:5]),
                retryable=False,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(
                f"HTTP_{exc.status_code}",
                str(exc.detail),
                retryable=exc.status_code >= 500,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload(
                "INTERNAL_ERROR",
                "服务内部错误，已记录日志",
                detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            ),
        )
