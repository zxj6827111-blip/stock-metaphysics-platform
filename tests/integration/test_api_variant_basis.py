"""``variant_basis=first_day_yinyang`` 的 HTTP 契约（ADR-0014）。

锁定三件事：

* 请求字段是**新增**的（`variant_basis`，默认 `explicit`）—— 既有请求体一字不改也照常工作；
* 按首日阴阳推导时，推导结果必须落到响应的出生档案与盘面上（variant_mode / assumptions / da_yun）；
* 缺首日数据时**不默认**（§2.4），冲突请求必须显式报错而不是静默取一个方向。
"""

from __future__ import annotations

from datetime import date


def _seed_stock(db_session, code: str, *, yinyang: str | None, pct: float | None) -> None:
    from src.db.models import StockMasterRow

    row = db_session.get(StockMasterRow, code)
    if row is None:
        row = StockMasterRow(stock_code=code, source="test")
        db_session.add(row)
    row.name = f"测试标的{code}"
    row.exchange = "SSE"
    row.board = "主板"
    row.listing_date = date(2001, 8, 27)
    row.first_day_pct_chg = pct
    row.first_day_yinyang = yinyang
    db_session.flush()
    db_session.commit()


class TestVariantBasisContract:
    def test_yin_stock_derives_reverse_and_emits_da_yun(self, client, db_session):
        _seed_stock(db_session, "600888", yinyang="阴", pct=-0.108696)
        r = client.post(
            "/api/v1/stocks/600888/analysis/bazi",
            json={
                "as_of": "2024-11-15T14:32:00",
                "variant_basis": "first_day_yinyang",
                "persist": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["birth_profile"]["variant_mode"] == "reverse"
        assert "首日涨跌标识「阴」" in body["birth_profile"]["variant_note"]
        keys = {a["key"] for a in body["birth_profile"]["assumptions"]}
        assert {"birth.variant_basis", "birth.variant_mode"} <= keys
        chart = body["chart"]
        assert chart["variant_mode"] == "reverse"
        assert len(chart["da_yun"]) == 10
        assert sum(1 for d in chart["da_yun"] if d["is_current"]) == 1
        assert "假设" in chart["da_yun_note"]

    def test_missing_first_day_data_is_reported_not_defaulted(self, client, db_session):
        _seed_stock(db_session, "600999", yinyang=None, pct=None)
        r = client.post(
            "/api/v1/stocks/600999/analysis/bazi",
            json={
                "as_of": "2024-11-15T14:32:00",
                "variant_basis": "first_day_yinyang",
                "persist": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["birth_profile"]["variant_mode"] == "not_applicable"
        assert "缺上市首日涨跌标识" in body["birth_profile"]["variant_note"]
        assert body["chart"]["da_yun"] == []

    def test_conflicting_request_is_rejected(self, client, db_session):
        _seed_stock(db_session, "600777", yinyang="阳", pct=0.0301)
        r = client.post(
            "/api/v1/stocks/600777/analysis/bazi",
            json={
                "as_of": "2024-11-15T14:32:00",
                "variant_basis": "first_day_yinyang",
                "variant_mode": "forward",
                "persist": False,
            },
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "BIRTH_PROFILE_ERROR"

    def test_explicit_request_unchanged(self, client, db_session):
        """既有请求体（只有 variant_mode）语义不变：不会因为库里有阴阳就自动推导。"""
        _seed_stock(db_session, "600666", yinyang="阳", pct=0.0301)
        r = client.post(
            "/api/v1/stocks/600666/analysis/bazi",
            json={"as_of": "2024-11-15T14:32:00", "persist": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["birth_profile"]["variant_mode"] == "not_applicable"
        assert body["chart"]["da_yun"] == []

    def test_ziwei_endpoint_rejects_derived_basis(self, client, db_session):
        """紫微方向的来源口径属 ADR-0010：本轮不接入首日阴阳推导。"""
        _seed_stock(db_session, "600555", yinyang="阳", pct=0.0301)
        r = client.post(
            "/api/v1/stocks/600555/analysis/ziwei",
            json={
                "as_of": "2024-11-15T14:32:00",
                "variant_basis": "first_day_yinyang",
                "variant_mode": "forward",
                "persist": False,
            },
        )
        assert r.status_code == 422, r.text
        assert "不接受 variant_basis" in r.json()["error"]["message"]
