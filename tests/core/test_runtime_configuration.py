"""研究运行配置必须默认 fail closed。"""

from src.core.config import Settings


def test_synthetic_market_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK", raising=False)

    settings = Settings(_env_file=None)

    assert settings.allow_synthetic_market_fallback is False


def test_offline_snapshot_without_security_certification_is_not_high_grade():
    from types import SimpleNamespace

    from src.market.providers.offline import OfflineMarketDataProvider

    provider = object.__new__(OfflineMarketDataProvider)
    provider._meta = SimpleNamespace(
        available=True,
        fetched_at="2026-09-20T10:00:00+08:00",
        source_label="verified-import-origin",
        payload={"quality_problems": [], "request_window": {"end": "2026-09-20"}},
    )
    status = provider.status_descriptor()

    assert status["data_quality_grade"] == "C"
    assert status["cutoff_date"] is None
    assert status["research_eligible"] is False
