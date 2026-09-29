"""多模型编排遇到核心历法故障时必须保留可用引擎结果。"""

from __future__ import annotations

from datetime import datetime

from src.core.orchestration.analysis_service import AnalysisService
from src.core.schemas.common import Availability
from src.core.stock.birth_profile import build_birth_profile
from src.core.schemas.stock import BirthProfileCreateRequest
from src.engines.calendar.calendar_engine import CalendarCalculationError


class _FailingHuangli:
    engine_version = "huangli-test-v1"

    def snapshot(self, *_args, **_kwargs):
        raise CalendarCalculationError("jieqi.previous.time", "test source unavailable")


class _FailingCalendar:
    engine_version = "calendar-test-v1"

    def snapshot(self, *_args, **_kwargs):
        raise CalendarCalculationError("day_ganzhi", "test source unavailable")


def _inputs(market):
    stock = market.get_stock("600519")
    profile = build_birth_profile(stock, BirthProfileCreateRequest())
    return stock, profile


def test_huangli_failure_does_not_discard_available_bazi(db_session, market):
    stock, profile = _inputs(market)
    response = AnalysisService(huangli=_FailingHuangli()).run_multi_analysis(
        db_session,
        stock=stock,
        birth_profile=profile,
        as_of=datetime(2024, 11, 15, 14, 32),
        persist=False,
    )

    assert response.bazi_chart is not None
    assert response.huangli is None
    assert response.opinions["bazi"].availability == Availability.OK
    assert response.opinions["bazi"].score is not None
    assert response.opinions["huangli"].availability == Availability.UNAVAILABLE
    assert response.opinions["huangli"].score is None
    assert any(w.code == "HUANGLI_UNAVAILABLE" for w in response.warnings)


def test_calendar_failure_returns_no_fabricated_charts_or_scores(db_session, market):
    stock, profile = _inputs(market)
    response = AnalysisService(calendar=_FailingCalendar()).run_multi_analysis(
        db_session,
        stock=stock,
        birth_profile=profile,
        as_of=datetime(2024, 11, 15, 14, 32),
        persist=False,
    )

    assert response.bazi_chart is None
    assert response.huangli is None
    assert response.factors.observations == []
    for engine in ("bazi", "huangli"):
        assert response.opinions[engine].availability == Availability.UNAVAILABLE
        assert response.opinions[engine].score is None
    assert any(w.code == "BAZI_UNAVAILABLE" for w in response.warnings)
    assert any(w.code == "HUANGLI_UNAVAILABLE" for w in response.warnings)
