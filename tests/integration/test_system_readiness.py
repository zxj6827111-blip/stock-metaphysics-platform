"""v2 就绪状态区分核心依赖与可降级组件。"""

from __future__ import annotations

from apps.api.deps import db_session
from apps.api.main import app
from apps.api.routers import system
from src.core.schemas.common import Availability
from src.engines.ziwei.transport import HttpZiweiTransport
from src.engines.ziwei.ziwei_engine import ZiweiEngine


def test_readiness_fails_when_migrations_are_not_current(client, monkeypatch):
    monkeypatch.setattr(system, "_migration_status", lambda _db: {
        "status": "not_ready", "required": True,
        "current_revision": "old", "heads": ["head"],
        "reason": "数据库迁移版本未到唯一 Alembic head。",
    })

    response = client.get("/api/v2/system/readiness")
    body = response.json()

    assert response.status_code == 503
    assert body["ready"] is False
    assert body["status"] == "not_ready"
    assert body["components"]["database"]["status"] == "ready"
    assert body["components"]["migrations"]["status"] == "not_ready"
    assert "ziwei_service" in body["components"]
    assert body["components"]["research_data"]["research_eligible"] is False


def test_optional_components_are_reported_without_failing_core_readiness(client, monkeypatch):
    monkeypatch.setattr(system, "_migration_status", lambda _db: {
        "status": "ready", "required": True,
        "current_revision": "head", "heads": ["head"], "reason": "",
    })

    class UnavailableZiwei:
        availability = Availability.UNAVAILABLE
        transport_name = "test-unavailable"

        @staticmethod
        def unavailable_reason():
            return "injected Ziwei transport failure"

        @staticmethod
        def runtime_health():
            return False, "injected Ziwei transport failure"

    monkeypatch.setattr(system, "ZiweiEngine", UnavailableZiwei)

    response = client.get("/api/v2/system/readiness")
    body = response.json()

    assert response.status_code == 200
    assert body["ready"] is True
    assert body["status"] in {"ready", "degraded"}
    assert body["components"]["ziwei_service"]["required"] is False
    assert body["components"]["ziwei_service"]["status"] == "degraded"
    assert body["components"]["ziwei_service"]["available"] is False
    assert body["components"]["research_data"]["required"] is False

    # v1 health remains a liveness probe and keeps its existing response.
    health = client.get("/api/v1/system/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


def test_readiness_probes_configured_http_ziwei_service(client, monkeypatch):
    monkeypatch.setattr(system, "_migration_status", lambda _db: {
        "status": "ready", "required": True,
        "current_revision": "head", "heads": ["head"], "reason": "",
    })

    class HealthResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok"}

    import httpx

    def healthy_get(url, *, timeout):
        assert url == "http://127.0.0.1:8100/health"
        assert timeout <= 1
        return HealthResponse()

    monkeypatch.setattr(httpx, "get", healthy_get)
    monkeypatch.setattr(
        system, "ZiweiEngine",
        lambda: ZiweiEngine(HttpZiweiTransport("http://127.0.0.1:8100")),
    )

    response = client.get("/api/v2/system/readiness")
    body = response.json()

    assert response.status_code == 200
    assert body["components"]["ziwei_service"]["status"] == "ready"
    assert body["components"]["ziwei_service"]["available"] is True
    assert body["components"]["ziwei_service"]["reason"] == ""


def test_readiness_marks_configured_but_unreachable_http_ziwei_as_degraded(client, monkeypatch):
    monkeypatch.setattr(system, "_migration_status", lambda _db: {
        "status": "ready", "required": True,
        "current_revision": "head", "heads": ["head"], "reason": "",
    })

    import httpx

    def unreachable_get(_url, *, timeout):
        assert timeout <= 1
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", unreachable_get)
    monkeypatch.setattr(
        system, "ZiweiEngine",
        lambda: ZiweiEngine(HttpZiweiTransport("http://127.0.0.1:8100")),
    )

    response = client.get("/api/v2/system/readiness")
    body = response.json()

    assert response.status_code == 200
    assert body["ready"] is True
    assert body["components"]["ziwei_service"]["status"] == "degraded"
    assert body["components"]["ziwei_service"]["available"] is False
    assert body["components"]["ziwei_service"]["reason"] == "紫微服务健康检查失败：ConnectError"


def test_engine_status_uses_http_health_probe(client, monkeypatch):
    import httpx

    def unreachable_get(_url, *, timeout):
        assert timeout <= 1
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", unreachable_get)
    monkeypatch.setattr(
        system, "ZiweiEngine",
        lambda: ZiweiEngine(HttpZiweiTransport("http://127.0.0.1:8100")),
    )

    body = client.get("/api/v1/system/engines").json()
    ziwei = next(engine for engine in body["engines"] if engine["engine_id"] == "ziwei")

    assert ziwei["available"] is False
    assert "ConnectError" in ziwei["unavailable_reason"]


def test_readiness_fails_when_database_is_unavailable(client):
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable for test")

    def broken_database():
        yield BrokenSession()

    app.dependency_overrides[db_session] = broken_database
    try:
        response = client.get("/api/v2/system/readiness")
    finally:
        app.dependency_overrides.pop(db_session, None)

    body = response.json()
    assert response.status_code == 503
    assert body["ready"] is False
    assert body["components"]["database"]["status"] == "not_ready"
    assert body["components"]["migrations"]["status"] == "blocked"


def test_market_versions_and_quality_expose_provider_and_cutoff(client):
    versions = client.get("/api/v1/system/versions").json()
    report = client.get("/api/v1/system/data-quality").json()

    assert versions["market_data_version"] == "synthetic-demo-v1"
    assert versions["market_data_source"] == "synthetic_demo"
    assert versions["market_data_cutoff_date"] is None
    assert report["market_data"]["research_eligible"] is False
    assert report["market_data"]["cutoff_date"] is None
    bars = next(item for item in report["items"] if item["key"] == "market_bar_daily")
    assert bars["grade"] == "D"
    assert bars["source"] == "synthetic_demo"
    assert bars["version"] == "synthetic-demo-v1"


def test_market_status_endpoints_report_provider_initialization_failure(client, monkeypatch):
    from src.market.providers import akshare_provider

    def fail_provider():
        raise FileNotFoundError("provider configuration unavailable")

    monkeypatch.setattr(akshare_provider, "get_market_provider", fail_provider)

    versions = client.get("/api/v1/system/versions")
    report = client.get("/api/v1/system/data-quality")

    assert versions.status_code == 200
    assert versions.json()["market_data_version"] == ""
    assert versions.json()["market_data_cutoff_date"] is None
    assert report.status_code == 200
    assert report.json()["market_data"]["status"] == "unavailable"
    assert report.json()["market_data"]["research_eligible"] is False

    class BrokenStatusProvider:
        @staticmethod
        def status_descriptor():
            raise RuntimeError("provider status metadata malformed")

    monkeypatch.setattr(akshare_provider, "get_market_provider", BrokenStatusProvider)
    report = client.get("/api/v1/system/data-quality")
    assert report.status_code == 200
    assert report.json()["market_data"]["status"] == "unavailable"
    assert report.json()["market_data"]["data_version"] is None
