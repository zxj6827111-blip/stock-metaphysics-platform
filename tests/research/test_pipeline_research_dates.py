from __future__ import annotations

from datetime import date, datetime, time

from src.core.schemas.factor import FactorObservation
from src.core.schemas.market import LabelSet
from src.core.stock.trading_calendar import TradingCalendar
from src.research.labels.research_date import resolve_research_date
from src.research.pipeline import ResearchPipeline


class _Provider:
    def for_exchange(self, _exchange):
        return TradingCalendar(
            exchange="SSE", _days=frozenset({date(2024, 1, 1), date(2024, 1, 3)}), loaded=True,
        )


def test_pipeline_resolves_anchor_before_factor_and_label_builders():
    seen: list[tuple[str, date]] = []

    def resolve(_code, anchor):
        return resolve_research_date(anchor, "SSE", provider=_Provider())

    def factor_builder(code, research_date, _profile):
        seen.append(("factor", research_date))
        return [FactorObservation(
            factor_id="F", stock_code=code,
            as_of=datetime.combine(research_date, time(15)), trade_date=research_date,
            engine="bazi", category="day", rule_version="r1", engine_version="e1",
        )]

    def label_builder(code, research_date):
        seen.append(("label", research_date))
        return LabelSet(stock_code=code, as_of=research_date, trade_date=research_date)

    observations, labels, warnings = ResearchPipeline().build_panel(
        stocks=["A"], sample_dates=[date(2024, 1, 2)],
        factor_builder=factor_builder, label_builder=label_builder,
        birth_profile_provider=lambda _code, _variant: object(),
        research_date_resolver=resolve,
    )
    assert seen == [("factor", date(2024, 1, 3)), ("label", date(2024, 1, 3))]
    assert observations.iloc[0]["trade_date"] == date(2024, 1, 3)
    assert labels.iloc[0]["trade_date"] == date(2024, 1, 3)
    assert observations.iloc[0]["requested_anchor_date"] == date(2024, 1, 2)
    assert observations.iloc[0]["research_date_source"] == "observed_index_days"
    assert any(w.code == "RESEARCH_DATE_SHIFTED" for w in warnings)


def test_pipeline_skips_samples_when_calendar_falls_back():
    def resolve(_code, anchor):
        from src.core.stock.trading_calendar import TradingCalendarProvider
        return resolve_research_date(anchor, "BSE", provider=TradingCalendarProvider())

    observations, labels, warnings = ResearchPipeline().build_panel(
        stocks=["A"], sample_dates=[date(2024, 1, 2)],
        factor_builder=lambda *_args: [],
        label_builder=lambda *_args: None,
        birth_profile_provider=lambda _code, _variant: object(),
        research_date_resolver=resolve,
    )
    assert observations.empty
    assert labels.empty
    assert any(w.code == "RESEARCH_DATE_UNAVAILABLE" for w in warnings)
