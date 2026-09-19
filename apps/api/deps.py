"""FastAPI 依赖注入。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.orchestration.analysis_service import AnalysisService
from src.db.base import get_db
from src.knowledge.retrieval.provider import get_knowledge_provider
from src.market.providers.akshare_provider import get_market_provider
from src.research.backtest.provider import get_backtest_provider


def db_session() -> Iterator[Session]:
    yield from get_db()


@lru_cache(maxsize=1)
def _analysis_service() -> AnalysisService:
    return AnalysisService()


def get_analysis_service() -> AnalysisService:
    return _analysis_service()


def get_market():
    """行情提供者。

    ``SMP_MARKET_PROVIDER=synthetic`` 时返回离线合成源，
    用于无网络环境与自动化测试。
    """
    return get_market_provider()


def get_knowledge():
    return get_knowledge_provider()


def get_backtest():
    return get_backtest_provider()


def parse_as_of(as_of: str | None) -> datetime:
    """解析 ``as_of`` 参数；缺省为当前时间。

    支持 ``YYYY-MM-DD`` / ``YYYY-MM-DDTHH:MM:SS`` / 带时区的 ISO 字符串。

    注意（验收修正）：as_of 解析失败是**客户端输入错误**（4xx），
    绝不能返回 502（502 暗示上游行情服务故障，会误导调用方重试与排障）。
    """
    if not as_of:
        return datetime.now().replace(microsecond=0)
    raw = as_of.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        from apps.api.errors import InvalidRequestError

        raise InvalidRequestError(
            f"无法解析 as_of 参数: {as_of!r}（需要 ISO8601，如 2024-11-15T14:32:00）"
        ) from None
    # 统一成 naive 本地时间（Asia/Shanghai）
    if dt.tzinfo is not None:
        from zoneinfo import ZoneInfo

        dt = dt.astimezone(ZoneInfo(settings.timezone)).replace(tzinfo=None)
    return dt.replace(microsecond=0)


__all__ = [
    "db_session", "get_analysis_service", "get_market", "get_knowledge",
    "get_backtest", "parse_as_of", "Depends",
]
