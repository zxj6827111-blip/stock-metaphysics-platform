"""API 集成测试 —— 覆盖 two_session_plan §16 要求的全部端点。

必须验证：
* 9 个 Phase 1 端点全部可调用；
* OpenAPI 可访问；
* 错误返回结构化 JSON（不抛裸 traceback）；
* 紫微不可用返回 unavailable，**不是 0 分**；
* 落库可追溯（chart_artifact / factor_observation）。
"""

from __future__ import annotations

import pytest

PHASE1_ENDPOINTS = [
    ("GET", "/api/v1/stocks/search?q=600519"),
    ("GET", "/api/v1/stocks/600519"),
    ("POST", "/api/v1/stocks/600519/birth-profile"),
]

ANALYSIS_ID: str | None = None


@pytest.fixture(scope="module")
def analysis_id(client) -> str:
    """执行一次完整分析，供后续端点复用。"""
    resp = client.post(
        "/api/v1/stocks/600519/analysis/bazi",
        json={"as_of": "2024-11-15T14:32:00"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["analysis_id"]


class TestSystemEndpoints:
    def test_health(self, client):
        r = client.get("/api/v1/system/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        # Phase 2 起 phase 标记升级（Phase 1 为 "phase1"）
        assert body["phase"] == "phase2"

    def test_engines_lists_all_six(self, client):
        """六类引擎必须全部登记（Phase 1 → Phase 2 的语义变化见注释）。

        * liuyao / qimen 恒为不可用（本版本不实现）；
        * 紫微已实现：``available`` 反映**排盘服务真实可达性**。
          可用时必须带版本号；不可用时必须带可解释原因，禁止静默。
        """
        r = client.get("/api/v1/system/engines")
        assert r.status_code == 200
        engines = {e["engine_id"]: e for e in r.json()["engines"]}
        assert set(engines) == {"calendar", "huangli", "bazi", "ziwei", "liuyao", "qimen"}
        assert engines["calendar"]["available"] is True
        assert engines["huangli"]["available"] is True
        assert engines["bazi"]["available"] is True
        assert engines["liuyao"]["available"] is False
        assert engines["qimen"]["available"] is False
        if engines["ziwei"]["available"]:
            assert engines["ziwei"]["engine_version"].startswith("iztro-")
        else:
            assert engines["ziwei"]["unavailable_reason"]
            assert "0 分" in engines["ziwei"]["unavailable_reason"]

    def test_versions(self, client):
        r = client.get("/api/v1/system/versions")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "birth_profile_version", "calendar_engine_version", "huangli_engine_version",
            "bazi_engine_version", "factor_rule_version", "config_version",
            "knowledge_version", "market_data_version",
        ):
            assert body[key], f"缺少版本号 {key}"

    def test_phase1_status(self, client):
        r = client.get("/api/v1/system/phase1-status")
        assert r.status_code == 200
        body = r.json()
        assert body["completed"]
        assert body["not_implemented_phase2"]
        assert any("紫微" in x for x in body["not_implemented_phase2"])
        assert any("投资建议" in d for d in body["disclaimers"])

    def test_data_quality(self, client):
        r = client.get("/api/v1/system/data-quality")
        assert r.status_code == 200
        body = r.json()
        assert body["overall_grade"] in ("A", "B", "C", "D")
        assert len(body["items"]) >= 4

    def test_openapi_available(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        for required in (
            "/api/v1/stocks/search",
            "/api/v1/stocks/{code}",
            "/api/v1/stocks/{code}/birth-profile",
            "/api/v1/stocks/{code}/analysis/bazi",
            "/api/v1/analysis/{analysis_id}/charts/bazi",
            "/api/v1/analysis/{analysis_id}/huangli",
            "/api/v1/analysis/{analysis_id}/factors",
            "/api/v1/analysis/{analysis_id}/backtest",
            "/api/v1/analysis/{analysis_id}/evidence",
        ):
            assert required in paths, f"OpenAPI 缺少 {required}"


class TestStockEndpoints:
    def test_search(self, client):
        r = client.get("/api/v1/stocks/search", params={"q": "600519"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 1
        assert body["items"][0]["stock_code"] == "600519"

    def test_search_by_name(self, client):
        r = client.get("/api/v1/stocks/search", params={"q": "茅台"})
        assert r.status_code == 200
        assert any(i["stock_code"] == "600519" for i in r.json()["items"])

    def test_search_empty_query_rejected(self, client):
        r = client.get("/api/v1/stocks/search", params={"q": ""})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_get_stock(self, client):
        r = client.get("/api/v1/stocks/600519")
        assert r.status_code == 200
        stock = r.json()["stock"]
        assert stock["stock_code"] == "600519"
        assert stock["exchange"] == "SSE"

    def test_get_stock_invalid_code(self, client):
        r = client.get("/api/v1/stocks/abc")
        assert r.status_code in (400, 422)
        assert "error" in r.json()

    def test_birth_profile_default_listing_open(self, client):
        r = client.post("/api/v1/stocks/600519/birth-profile", json={"birth_basis": "listing_open"})
        assert r.status_code == 200
        body = r.json()
        assert body["birth_basis"] == "listing_open"
        assert body["timezone"] == "Asia/Shanghai"
        assert body["variant_mode"] == "not_applicable"
        assert body["evidence"]["lookup_key"].startswith("SSE")
        assert body["assumptions"]
        assert body["birth_profile_version"]

    def test_birth_profile_unsupported_basis_returns_structured_error(self, client):
        r = client.post(
            "/api/v1/stocks/600519/birth-profile",
            json={"birth_basis": "company_foundation"},
        )
        assert r.status_code == 422
        body = r.json()
        assert body["error"]["code"] == "BIRTH_PROFILE_ERROR"
        assert "猜测" in body["error"]["message"] or "未接入" in body["error"]["message"]

    def test_birth_baseline_compare(self, client):
        r = client.post("/api/v1/stocks/600519/birth-profile/compare")
        assert r.status_code == 200
        baselines = r.json()["baselines"]
        by_key = {b["birth_basis"]: b for b in baselines}
        assert by_key["listing_open"]["ok"] is True
        assert "回测" in r.json()["note"]


class TestAnalysisEndpoints:
    def test_bazi_analysis_returns_full_chain(self, client, analysis_id):
        r = client.post(
            "/api/v1/stocks/600519/analysis/bazi",
            json={"as_of": "2024-11-15T14:32:00"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["analysis_id"]
        assert body["chart"]["year_pillar"]["ganzhi"]["text"] == "辛巳"
        assert body["chart"]["day_pillar"]["ganzhi"]["text"] == "壬戌"
        assert len(body["factors"]["observations"]) >= 40
        assert body["opinion"]["engine"] == "bazi"
        assert body["birth_profile"]["birth_basis"] == "listing_open"
        assert body["versions"]["engine_version"]

    def test_charts_bazi(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/charts/bazi")
        assert r.status_code == 200
        body = r.json()
        assert body["chart"]["day_master"] == "壬"
        assert body["engine_version"]

    def test_charts_bazi_raw_mode(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/charts/bazi", params={"raw": True})
        assert r.status_code == 200
        body = r.json()
        assert body["input"]
        assert body["assumptions"] is not None
        assert body["calculated_at"]

    def test_huangli(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/huangli")
        assert r.status_code == 200
        body = r.json()
        assert body["huangli"]["primary"]["day_ganzhi"]
        assert body["engine_version"]

    def test_factors(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/factors")
        assert r.status_code == 200
        body = r.json()
        assert len(body["observations"]) >= 40
        assert body["rule_version"]

    def test_factors_filtered_by_direction(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/factors", params={"direction": 1})
        assert r.status_code == 200
        for o in r.json()["observations"]:
            assert o["direction"] == 1

    def test_factors_filtered_by_engine(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/factors", params={"engine": "huangli"})
        assert r.status_code == 200
        for o in r.json()["observations"]:
            assert o["engine"] == "huangli"

    def test_evidence_includes_counter(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
        assert r.status_code == 200
        body = r.json()
        assert "disclaimer" in body
        ev = body["evidence"]
        assert ev["supporting_evidence"] or ev["counter_evidence"]
        assert ev["retrieval_method"]
        for item in ev["supporting_evidence"] + ev["counter_evidence"]:
            assert item["book"]
            assert item["original_text"]
            assert item["provenance"]
            assert item["license_status"] == "public_domain"

    def test_backtest_returns_structured_result(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/backtest")
        assert r.status_code == 200
        body = r.json()
        assert "horizons" in body
        assert body["methodology"]
        # 没有历史样本时必须为 0，且不得伪造数值
        for h in body["horizons"]:
            if h["sample_count"] == 0:
                assert h["mean_return"] is None

    def test_consensus_is_display_only(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/consensus")
        assert r.status_code == 200
        body = r.json()
        assert body["display_only"] is True
        assert "ziwei" in body["unavailable_engines"]
        assert "ziwei" not in body["directions"]
        assert "展示层" in body["note"] or "Phase 1" in body["note"]

    def test_conflicts(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/conflicts")
        assert r.status_code == 200
        assert r.json()["display_only"] is True

    def test_guide_marks_ziwei_unavailable(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/guide")
        assert r.status_code == 200
        engines = {e["engine"]: e for e in r.json()["engines"]}
        assert engines["ziwei"]["available"] is False
        assert engines["bazi"]["available"] is True

    def test_analysis_not_found(self, client):
        r = client.get("/api/v1/analysis/AN-DOES-NOT-EXIST/factors")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"

    def test_analysis_run_detail(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["stock_code"] == "600519"
        assert body["engine"] if "engine" in body else True


class TestZiweiNeverFaked:
    """紫微永远不会被伪造：既不会用 0 分冒充，也不会默认填性别。

    Phase 2 起紫微引擎已实现，但**本类测试仍然有效**：
    `analysis/bazi` 的默认 `variant_mode=not_applicable`，
    而紫微需要显式方向 —— 因此该端点下紫微依然必须是 unavailable。
    """

    def test_opinion_unavailable_not_zero(self, client):
        r = client.post(
            "/api/v1/stocks/600519/analysis/bazi",
            json={"as_of": "2024-11-15T14:32:00"},
        )
        assert r.status_code == 200
        body = r.json()
        # bazi 端点只返回八字 opinion；紫微的不可用状态在 consensus/guide 中体现
        aid = body["analysis_id"]
        consensus = client.get(f"/api/v1/analysis/{aid}/consensus").json()
        assert "ziwei" in consensus["unavailable_engines"]
        assert "ziwei" not in consensus["directions"], "不可用引擎不得出现在方向表里"

        guide = client.get(f"/api/v1/analysis/{aid}/guide").json()
        ziwei = next(e for e in guide["engines"] if e["engine"] == "ziwei")
        assert ziwei["available"] is False
        # 原因必须说明"为什么没有紫微"，而不是含糊其辞
        assert "紫微" in ziwei["reason"]
        assert "variant_mode" in ziwei["reason"] or "服务不可用" in ziwei["reason"]

    def test_ziwei_endpoint_refuses_default_gender(self, client):
        """紫微端点不得接受 not_applicable —— 否则等于偷偷选了一个方向。"""
        r = client.post(
            "/api/v1/stocks/600519/analysis/ziwei",
            json={"as_of": "2024-11-15T14:32:00", "variant_mode": "not_applicable"},
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_REQUEST"
        assert "variant_mode" in r.json()["error"]["message"]


class TestKnowledgeEndpoints:
    def test_books(self, client):
        r = client.get("/api/v1/knowledge/books")
        assert r.status_code == 200
        assert r.json()["total"] >= 5

    def test_entries(self, client):
        r = client.get("/api/v1/knowledge/entries", params={"limit": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] >= 30
        assert len(body["items"]) <= 10

    def test_search_returns_both_stances(self, client):
        r = client.post(
            "/api/v1/knowledge/search",
            json={"query": "财星 财多身弱", "topics": ["财星"], "top_k": 5},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["counter_evidence"], "检索必须返回反证"

    def test_search_by_factors(self, client):
        r = client.get("/api/v1/knowledge/by-factors", params={"factor_ids": "B_NATAL_002,B_NATAL_016"})
        assert r.status_code == 200
        assert r.json()["query"]["factor_ids"] == ["B_NATAL_002", "B_NATAL_016"]

    def test_stats(self, client):
        r = client.get("/api/v1/knowledge/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["entries"] >= 30
        assert body["by_license_status"].get("public_domain", 0) == body["entries"]


class TestFactorDictionary:
    def test_dictionary(self, client):
        r = client.get("/api/v1/factor-dictionary")
        assert r.status_code == 200
        body = r.json()
        assert body["total_all"] >= 40
        assert "不是预期收益率" in body["disclaimer"]
        for item in body["items"][:5]:
            assert item["factor_id"]
            assert item["definition"]
            assert item["rule_version"]


class TestResearchEndpoints:
    def test_labels(self, client):
        r = client.get("/api/v1/research/labels/600519", params={"as_of": "2021-06-01"})
        assert r.status_code == 200
        body = r.json()
        assert body["as_of"] == "2021-06-01"
        assert "ret_20d" in body

    def test_factor_definitions(self, client):
        r = client.get("/api/v1/research/factor-definitions")
        assert r.status_code == 200
        assert r.json()["total"] >= 40

    def test_run_research_pipeline(self, client):
        """端到端研究流水线：面板 → 事件研究 → 四类负对照。"""
        r = client.post(
            "/api/v1/research/run",
            json={
                "universe": ["600519", "000001", "300750"],
                "factor_ids": ["B_MONTH_001", "B_MONTH_002"],
                "horizons": [5, 20],
                "sample_step_months": 6,
                "date_from": "2021-01-01",
                "date_to": "2024-06-30",
                "run_negative_controls": True,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["experiment_id"]
        assert body["event_study"]["methodology"]
        nc = body["negative_controls"]
        assert nc is not None
        kinds = {r_["kind"] for r_ in nc["results"]}
        assert kinds == {"random_birth_date", "shift_plus_7d", "shift_minus_7d", "random_factor"}
        assert nc["conclusion"]
        for res in nc["results"]:
            assert res["verdict"] in ("outperform", "tie", "underperform", "inconclusive")
            assert res["verdict_note"]

    def test_experiments_listed(self, client):
        r = client.get("/api/v1/research/experiments")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_experiment_detail(self, client):
        listing = client.get("/api/v1/research/experiments").json()
        exp_id = listing["items"][0]["experiment_id"]
        r = client.get(f"/api/v1/research/experiments/{exp_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["experiment"]["experiment_id"] == exp_id
        assert "real" in body["results_by_variant"]


class TestTraceability:
    def test_chart_artifact_persisted(self, client, analysis_id):
        """原始盘面必须落库，并带版本信息。"""
        r = client.get(f"/api/v1/analysis/{analysis_id}/charts/bazi", params={"raw": True})
        body = r.json()
        assert body["chart_id"]
        assert body["engine"] == "bazi"
        assert body["engine_version"]
        assert body["config_version"]
        assert body["birth_profile_version"]
        assert body["raw_chart"]["day_master"]

    def test_factor_observations_persisted(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/factors")
        obs = r.json()["observations"]
        assert obs
        for o in obs[:5]:
            assert o["engine_version"]
            assert o["rule_version"]
            assert o["as_of"]
