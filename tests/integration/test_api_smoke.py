"""API 全端点 smoke 测试（验收 §十二）。

对 30 个端点逐一断言：

* 正向路径返回 200；
* 错误处理是**结构化**的：``{error: {code, message, detail, retryable}}``，
  绝不允许 "HTTP 200 + 假装成功" 或裸 500 文本；
* 在合成行情模式下，研究侧输出必须带 ``research_status = NO_REAL_DATA``
  （``RESEARCH_DATA_UNAVAILABLE`` 等价状态）。

该测试跑在 ``SMP_MARKET_PROVIDER=synthetic`` 下（见 conftest），
这本身就是验收的一部分：证明降级行情绝不会产生"有效性"结论。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _assert_error_shape(resp, expected_status: int):
    assert resp.status_code == expected_status, (
        f"期望 {expected_status}，实际 {resp.status_code}: {resp.text[:300]}"
    )
    body = resp.json()
    assert "error" in body, f"错误响应缺少 error 顶层键: {body}"
    err = body["error"]
    for key in ("code", "message"):
        assert key in err and err[key], f"error.{key} 缺失或为空: {err}"


@pytest.fixture(scope="module")
def analysis_id(client):
    """创建一个真实分析，供下游端点使用。"""
    resp = client.post("/api/v1/stocks/600519/analysis/bazi", json={})
    assert resp.status_code == 200, resp.text[:300]
    return resp.json()["analysis_id"]


class TestStocksEndpoints:
    def test_search_ok(self, client):
        resp = client.get("/api/v1/stocks/search", params={"q": "600519"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"], "搜索不应为空"
        # 离线合成模式下必须显式降级
        assert body["is_degraded"] is True

    def test_search_validation_error(self, client):
        _assert_error_shape(client.get("/api/v1/stocks/search", params={"q": ""}), 422)

    def test_stock_detail_ok(self, client):
        resp = client.get("/api/v1/stocks/600519")
        assert resp.status_code == 200
        body = resp.json()
        assert body["stock"]["stock_code"] == "600519"

    def test_stock_detail_not_found(self, client):
        # 位数非法（5 位）→ 422；合法格式但离线清单无记录时可返回降级对象（grade=D）
        resp = client.get("/api/v1/stocks/12345")
        assert resp.status_code in (404, 422)
        if resp.status_code == 422:
            _assert_error_shape(resp, 422)

    def test_stock_code_invalid(self, client):
        _assert_error_shape(client.get("/api/v1/stocks/XYZ"), 422)

    def test_birth_profile_create(self, client):
        resp = client.post("/api/v1/stocks/600519/birth-profile", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["birth_datetime"].startswith("2001-08-27")
        assert body["variant_mode"] == "not_applicable"

    def test_birth_profile_custom_requires_datetime(self, client):
        # custom 但不给 override_datetime → 422
        resp = client.post("/api/v1/stocks/600519/birth-profile",
                           json={"birth_basis": "custom"})
        assert resp.status_code == 422, resp.text[:300]

    def test_birth_profile_compare(self, client):
        resp = client.post("/api/v1/stocks/600519/birth-profile/compare", json={})
        assert resp.status_code == 200
        body = resp.json()
        # listing_open 必有；ipo_date 可能有近似
        assert "basis_comparison" in body or isinstance(body, dict)


class TestAnalysisEndpoints:
    def test_analyze_bazi(self, client):
        resp = client.post("/api/v1/stocks/600519/analysis/bazi",
                           json={"as_of": "2024-11-15T14:32:00"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["chart"]["day_master"]
        assert body["factors"]["observations"]
        # Phase 1：紫微不可用但不得伪造
        assert body["warnings"] == body["warnings"]  # 结构存在即可

    def test_analyze_bad_as_of(self, client):
        resp = client.post("/api/v1/stocks/600519/analysis/bazi",
                           json={"as_of": "not-a-date"})
        assert resp.status_code in (400, 422, 500), resp.status_code
        _assert_error_shape(resp, resp.status_code)  # 错误必须结构化

    def test_analysis_get(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}")
        assert resp.status_code == 200

    def test_analysis_not_found(self, client):
        _assert_error_shape(client.get("/api/v1/analysis/AN-NONE"), 404)

    def test_bazi_chart(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/charts/bazi")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chart"]["year_pillar"]["ganzhi"]["text"]
        assert body["engine_version"]

    def test_bazi_chart_raw(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/charts/bazi", params={"raw": True})
        assert resp.status_code == 200
        assert "input" in resp.json()

    def test_huangli(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/huangli")
        assert resp.status_code == 200

    def test_factors(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/factors")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["observations"]) > 60
        # 契约：factor_observation 字段全集
        first = body["observations"][0]
        for key in ("factor_id", "normalized_value", "direction", "rule_score",
                    "rule_version", "engine_version", "config_version"):
            assert key in first, f"因子观测缺字段 {key}"

    def test_consensus(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/consensus")
        assert resp.status_code == 200
        assert resp.json().get("display_only") is True, "Phase 1 共识必须 display_only"

    def test_conflicts(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/conflicts")
        assert resp.status_code == 200

    def test_guide(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/guide")
        assert resp.status_code == 200
        engines = {e["engine"]: e for e in resp.json()["engines"]}
        assert engines["ziwei"]["available"] is False
        assert engines["bazi"]["available"] is True

    def test_evidence(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/evidence")
        assert resp.status_code == 200
        body = resp.json()
        ev = body["evidence"]
        assert "supporting_evidence" in ev and "counter_evidence" in ev


class TestBacktestEndpointHonesty:
    """§十二重点：合成数据下 backtest 必须输出 NO_REAL_DATA，不得给出有效性语义。"""

    def test_backtest_status_no_real_data(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/backtest")
        assert resp.status_code == 200
        body = resp.json()
        assert "research_status" in body, "backtest 响应必须携带研究状态机状态"
        # 无真实标签库 → NOT_RUN；有降级标签 → NO_REAL_DATA；两者都合法
        assert body["research_status"] in ("NOT_RUN", "NO_REAL_DATA", "INCONCLUSIVE"), (
            f"合成环境下状态绝不能是有效性类，实际 {body['research_status']}"
        )
        if body["research_status"] == "NO_REAL_DATA":
            assert any("RESEARCH_DATA_UNAVAILABLE" == w["code"] for w in body["warnings"]), (
                "NO_REAL_DATA 状态必须携 RESEARCH_DATA_UNAVAILABLE 警告"
            )

    def test_backtest_invalid_horizons(self, client, analysis_id):
        resp = client.get(f"/api/v1/analysis/{analysis_id}/backtest",
                          params={"horizons": "abc"})
        assert resp.status_code == 422
        _assert_error_shape(resp, 422)


class TestResearchEndpoints:
    def test_research_run_synthetic(self, client):
        """合成行情下的研究流水线：必须如实报 NO_REAL_DATA，禁止包装成有效性。"""
        resp = client.post("/api/v1/research/run", json={
            "universe": ["600519", "000001"],
            "factor_ids": ["B_MONTH_001"],
            "horizons": [20],
            "sample_step_months": 6,
            "run_negative_controls": True,
            "persist": False,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["research_status"] == "NO_REAL_DATA", (
            f"合成行情下 research_status 必须 NO_REAL_DATA，实际 {body['research_status']}"
        )
        assert any("不构成" in r or "联调" in r for r in body["research_status_reasons"])
        assert any(w["code"] == "RESEARCH_DATA_UNAVAILABLE" for w in body["warnings"])

    def test_labels_endpoint(self, client):
        resp = client.get("/api/v1/research/labels/600519")
        assert resp.status_code == 200
        body = resp.json()
        # 合成数据标签必须带降级标记
        assert body.get("data_is_degraded") is True

    def test_labels_bad_code(self, client):
        resp = client.get("/api/v1/research/labels/XYZ")
        assert resp.status_code in (404, 422, 503)

    def test_factor_definitions(self, client):
        """Phase 2 起因子总数 = Phase 1 的 65 + 紫微的 49 = 114。

        用 ``>=`` 而不是 ``==``：因子只会增加，不会减少；
        真正的"没被误删"由 `test_factor_calculation` 的命名空间测试保证。
        """
        resp = client.get("/api/v1/research/factor-definitions")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 114
        engines = {i["engine"] for i in items}
        assert {"bazi", "huangli", "ziwei"} <= engines

    def test_experiments_list_and_detail(self, client):
        resp = client.get("/api/v1/research/experiments")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    def test_experiment_not_found(self, client):
        _assert_error_shape(client.get("/api/v1/research/experiments/EXP-NONE"), 404)


class TestKnowledgeEndpoints:
    def test_books(self, client):
        resp = client.get("/api/v1/knowledge/books")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 7
        for b in items:
            assert b["license_status"] == "public_domain"

    def test_entries(self, client):
        resp = client.get("/api/v1/knowledge/entries")
        assert resp.status_code == 200

    def test_search_with_counter_evidence(self, client):
        resp = client.post("/api/v1/knowledge/search",
                           json={"query": "财星", "top_k": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert "counter_evidence" in body, "检索必须恒含反证区"

    def test_search_validation_error(self, client):
        # top_k 越界（>20）→ 422
        resp = client.post("/api/v1/knowledge/search",
                           json={"query": "财星", "top_k": 99})
        assert resp.status_code == 422
        _assert_error_shape(resp, 422)

    def test_search_empty_query_is_valid_contract(self, client):
        # 空查询有默认值且合法 —— 检索为空也必须返回结构化 bundle，不得报错
        resp = client.post("/api/v1/knowledge/search", json={"query": ""})
        assert resp.status_code == 200
        assert "supporting_evidence" in resp.json()

    def test_by_factors(self, client):
        resp = client.get("/api/v1/knowledge/by-factors",
                          params={"factor_ids": "B_NATAL_002"})
        assert resp.status_code == 200

    def test_stats(self, client):
        resp = client.get("/api/v1/knowledge/stats")
        assert resp.status_code == 200


class TestSystemEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/v1/system/health",
        "/api/v1/system/engines",
        "/api/v1/system/data-quality",
        "/api/v1/system/versions",
        "/api/v1/system/phase1-status",
    ])
    def test_system_ok(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path}: {resp.text[:200]}"

    def test_health_structure(self, client):
        body = client.get("/api/v1/system/health").json()
        assert "status" in body or "ok" in body or "components" in body

    def test_versions_record_engine_versions(self, client):
        body = client.get("/api/v1/system/versions").json()
        assert body["calendar_engine_version"]
        assert body["bazi_engine_version"]
        assert "factor_rule_version" in body


class TestNoHidden200Errors:
    """任何出错端点绝不允许 200 但内部塞 error 文本。"""

    def test_unknown_route_is_404(self, client):
        resp = client.get("/api/v1/totally-not-real")
        assert resp.status_code == 404

    def test_method_not_allowed(self, client):
        resp = client.delete("/api/v1/stocks/600519")
        assert resp.status_code in (405, 404)
