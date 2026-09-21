"""新增黄历 / 逐日时间窗口端点的 HTTP 契约测试。

这些端点服务于「黄历 / 日课详情」页的两个新区块与时间窗口的逐日视图：

* ``GET /huangli/outlook`` —— 未来 N 个**交易日**黄历；
* ``GET /huangli/performance`` —— 日课分类的历史表现（描述性统计）；
* ``GET /timeline/days`` —— as_of 之后连续交易日的逐日三模型结果。

同时锁定 API 版本纪律：只**新增**端点，未改动任何既有路径或字段
（既有 ``/huangli`` 仍返回已保存的快照，不被新端点遮蔽）。
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def analysis_id(client) -> str:
    # 这些端点都要按 analysis_id 读回记录，因此必须落库（persist=True）
    resp = client.post(
        "/api/v1/stocks/600519/analysis/multi",
        json={"as_of": "2024-11-15T14:32:00", "variant_mode": "forward", "persist": True},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["analysis_id"]


class TestExistingContractUnchanged:
    def test_huangli_snapshot_endpoint_still_returns_saved_chart(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/huangli")
        assert r.status_code == 200
        body = r.json()
        # 仍是"已保存的黄历快照"契约（新端点不得遮蔽它）
        assert {"chart_id", "engine_version", "config_version", "as_of", "huangli"} <= set(body)
        assert "days" not in body  # outlook 的字段不得混进来

    def test_timeline_months_and_weeks_unchanged(self, client, analysis_id):
        for path, key in (("months?months=2", "months"), ("weeks?weeks=2", "weeks")):
            r = client.get(f"/api/v1/analysis/{analysis_id}/timeline/{path}")
            assert r.status_code == 200, r.text
            body = r.json()
            assert key in body
            assert body["aggregation_version"]


class TestHuangliOutlook:
    def test_trading_days_mode(self, client, analysis_id):
        r = client.get(
            f"/api/v1/analysis/{analysis_id}/huangli/outlook?mode=trading_days&days=20"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["returned_days"] == 20
        assert body["class_rule"]["third_category_supported"] is False
        assert body["class_rule_version"]
        for card in body["days"]:
            assert card["is_trading_day"] is True
            assert card["class_label_cn"] in (None, "吉", "凶")
            assert card["class_label_cn"] != "平"
        assert body["cache"]["hit"] in (True, False)

    def test_month_mode_groups(self, client, analysis_id):
        r = client.get(
            f"/api/v1/analysis/{analysis_id}/huangli/outlook?mode=months&months=3"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["month_groups"]) == 3
        flat = [d for g in body["month_groups"] for d in g["dates"]]
        assert flat == [d["date"] for d in body["days"]]

    def test_second_call_is_served_from_cache(self, client, analysis_id):
        url = f"/api/v1/analysis/{analysis_id}/huangli/outlook?mode=trading_days&days=5"
        first = client.get(url).json()
        second = client.get(url).json()
        assert first["days"] == second["days"]
        assert second["cache"]["hit"] is True

    def test_invalid_mode_rejected(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/huangli/outlook?mode=weekly")
        assert r.status_code == 422

    def test_unknown_analysis_returns_structured_404(self, client):
        r = client.get("/api/v1/analysis/NOPE/huangli/outlook")
        assert r.status_code == 404
        assert "error" in r.json() or "detail" in r.json()


class TestHuangliPerformance:
    def test_default_window(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/huangli/performance")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["performance_version"]
        assert body["horizon"] == 1
        # 合成行情下可能没有该标的的本地日线 —— 两种情况都必须有明确说明
        if body["unavailable_reason"]:
            assert body["warnings"]
            assert body["groups"] == []
        else:
            assert body["sample_rule_cn"]
            assert body["overlap"]["total_samples"] >= 0
            assert "不是净值" in body["series"]["metric_cn"]

    def test_unsupported_horizon_rejected(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/huangli/performance?horizon=2")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_REQUEST"

    def test_custom_window_requires_start(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/huangli/performance?window=custom")
        # 项目统一的 InvalidRequestError → 422 + 结构化错误体
        assert r.status_code == 422
        body = r.json()
        assert body["error"]["code"] == "INVALID_REQUEST"
        assert "start" in body["error"]["message"]


class TestTimelineDays:
    def test_days_endpoint(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/timeline/days?days=5")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["requested_days"] == 5
        assert body["returned_days"] <= 5
        assert body["daily_version"]
        assert body["days"], body.get("warnings")
        dates = [d["trade_date"] for d in body["days"]]
        assert dates == sorted(dates)
        # 不可用引擎的分数为 null，不是 0
        for d in body["days"]:
            for key in ("bazi_score", "ziwei_score", "huangli_score"):
                assert d[key] is None or d[key] > 0

    def test_days_clamped(self, client, analysis_id):
        r = client.get(f"/api/v1/analysis/{analysis_id}/timeline/days?days=999")
        assert r.status_code == 422  # 超出 le=60

    def test_days_cache_roundtrip(self, client, analysis_id):
        url = f"/api/v1/analysis/{analysis_id}/timeline/days?days=3"
        first = client.get(url).json()
        second = client.get(url).json()
        assert first["days"] == second["days"]
        assert second["cache"]["hit"] is True
