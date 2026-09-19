"""Phase 3B · BirthModel 模块单测（``src/research/birth_models.py``）。

目标（对照 GOAL §3B-1）
=======================
* 4 个 Birth Model 全部已注册
* ``birth_datetime`` 对同一股票不同模型应产生**不同的值**（listing_open ≠ listing_close ≠ ipo_approx）
* ``company_foundation`` 数据源不可得时必须返回 ``None`` 并挂 ``reason``
* 本模块**不依赖真实网络 / 数据库**

泄漏纪律（§3B / §17）
====================
* 任何 birth model 的 birth_datetime 必须``<= list_date_close``(即不应晚于 after-market）
* 启发式 approximations 必须显式 ``approximated=True``
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.research.birth_models import (
    BirthModel,
    BirthModelBuild,
    BirthModelId,
    build_birth,
    get_birth_model,
    list_birth_models,
)


class TestBirthModelRegistry:
    def test_four_models_registered(self):
        models = list_birth_models()
        ids = {m.model_id for m in models}
        assert BirthModelId.LISTING_OPEN in ids
        assert BirthModelId.LISTING_CLOSE in ids
        assert BirthModelId.IPO_DATE_APPROX in ids
        assert BirthModelId.COMPANY_FOUNDATION in ids
        assert len(models) == 4

    def test_get_birth_model_by_id(self):
        m = get_birth_model(BirthModelId.LISTING_OPEN)
        assert m.model_id == BirthModelId.LISTING_OPEN
        assert m.version

    def test_every_model_has_version_string(self):
        for m in list_birth_models():
            assert m.version.startswith("v"), f"{m.model_id} 缺 version"
            assert "phase3b" in m.version or m.model_id == BirthModelId.COMPANY_FOUNDATION


class TestBuildChronology:
    """出生时刻的、跨模型相对一致性。"""

    LIST_DATE = date(2001, 8, 27)

    def test_listing_open_is_0930(self):
        b = build_birth(BirthModelId.LISTING_OPEN, list_date=self.LIST_DATE)
        assert b.birth_datetime is not None
        assert b.birth_datetime.date() == self.LIST_DATE
        assert (b.birth_datetime.hour, b.birth_datetime.minute) == (9, 30)

    def test_listing_close_is_1500(self):
        b = build_birth(BirthModelId.LISTING_CLOSE, list_date=self.LIST_DATE)
        assert b.birth_datetime is not None
        assert b.birth_datetime.date() == self.LIST_DATE
        assert (b.birth_datetime.hour, b.birth_datetime.minute) == (15, 0)

    def test_ipo_approx_is_7_days_before(self):
        b = build_birth(BirthModelId.IPO_DATE_APPROX, list_date=self.LIST_DATE)
        assert b.birth_datetime is not None
        assert b.birth_datetime.date() == date(2001, 8, 20)
        assert b.approximated is True

    def test_open_close_differ_in_hour(self):
        """两模型在同一 list_date 上必须产生不同 birth_datetime。"""
        o = build_birth(BirthModelId.LISTING_OPEN, list_date=self.LIST_DATE).birth_datetime
        c = build_birth(BirthModelId.LISTING_CLOSE, list_date=self.LIST_DATE).birth_datetime
        assert o != c
        assert o.date() == c.date()  # 同日
        assert o.hour != c.hour      # 不同时


class TestUnavailableModels:
    """``company_foundation`` 数据源不可得 → 必须返回 None + reason，不得伪造。"""

    def test_company_foundation_returns_none(self):
        b = build_birth(BirthModelId.COMPANY_FOUNDATION, list_date=date(2001, 8, 27))
        assert b.birth_datetime is None
        assert "UNAVAILABLE" in b.reason.upper() or "不可得" in b.reason
        assert b.data_quality_grade == "D"
        assert b.data_quality_score == 0.0

    def test_null_list_date_returns_unavailable(self):
        b = build_birth(BirthModelId.LISTING_OPEN, list_date=None)
        assert b.birth_datetime is None
        assert b.data_quality_grade == "D"


class TestNoFutureLeakage:
    """birth_datetime 不得晚于 list_date 当日收盘。"""

    def test_birth_not_later_than_close_of_listing_day(self):
        d = date(2020, 6, 10)
        for mid in [BirthModelId.LISTING_OPEN, BirthModelId.LISTING_CLOSE]:
            b = build_birth(mid, list_date=d)
            assert b.birth_datetime is not None
            close_of_day = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=b.birth_datetime.tzinfo)
            assert b.birth_datetime <= close_of_day

    def test_ipo_approx_older_than_list(self):
        d = date(2020, 6, 10)
        b = build_birth(BirthModelId.IPO_DATE_APPROX, list_date=d)
        assert b.birth_datetime is not None
        assert b.birth_datetime.date() < d
