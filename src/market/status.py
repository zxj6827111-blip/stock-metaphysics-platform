"""共享的行情来源、快照边界与研究资格描述。"""

from __future__ import annotations

from src.core.config import settings
from src.market.providers.base import MarketDataProvider


def describe_market_data(provider: MarketDataProvider | None = None) -> dict:
    """返回实际 Provider 的状态；初始化失败时显式返回 unavailable。"""
    try:
        if provider is None:
            from src.market.providers.akshare_provider import get_market_provider

            provider = get_market_provider()
        descriptor = provider.status_descriptor()
        return {"configured_provider": settings.market_provider, **descriptor}
    except Exception as exc:  # noqa: BLE001 - 状态接口本身必须能报告 Provider 故障
        return {
            "configured_provider": settings.market_provider,
            "provider_id": settings.market_provider,
            "data_version": None,
            "snapshot_at": None,
            "cutoff_date": None,
            "cutoff_basis": "unavailable",
            "data_quality_grade": "D",
            "is_degraded": None,
            "research_eligible": False,
            "status": "unavailable",
            "notes": [f"Provider 状态不可读取：{type(exc).__name__}: {exc}"],
        }


def current_market_data_version(provider: MarketDataProvider | None = None) -> str:
    """用于结果版本戳的来源版本；没有来源证明时返回空串，不伪造版本。"""
    descriptor = describe_market_data(provider)
    value = descriptor.get("data_version")
    return str(value) if value else ""
