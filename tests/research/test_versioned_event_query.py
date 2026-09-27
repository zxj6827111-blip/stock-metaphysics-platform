from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd
import pytest

from src.research.event_study.versioned_query import (
    VersionedEventQuery,
    join_versioned_event_frames,
)
from src.research.labels.horizon_returns import compute_forward_returns, label_frame


def _bars(code: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "stock_code": code,
        "trade_date": pd.date_range("2020-01-01", periods=len(closes), freq="B"),
        "close": closes,
    })


def _query(**updates) -> VersionedEventQuery:
    values = {
        "stock_codes": ("A",),
        "date_from": date(2020, 1, 1),
        "date_to": date(2020, 1, 2),
        "factor_ids": ("F",),
        "activation": "positive",
        "research_time": time(15, 0),
        "direction_filter": 1,
        "min_rule_score": 5.0,
        "engine_version": "engine-v2",
        "rule_version": "rule-v3",
        "config_version": "config-v1",
        "label_version": "w3-hfq-adjfactor-v2",
        "bar_version": "bars-v2",
        "factor_data_version": "factors-v2",
        "price_basis": "raw_times_factor",
    }
    values.update(updates)
    return VersionedEventQuery(**values)


def test_two_stock_multi_date_join_is_scoped_and_preserves_unavailable_labels():
    # A 在第二根日线上发生 1:2 拆股；调整收益应为 0，而不是 -50%。
    a = _bars("A", [100.0, 50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0, 58.0])
    a_factors = pd.DataFrame({
        "trade_date": a["trade_date"].drop(index=2).reset_index(drop=True),
        "factor": [1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0],
    })
    b = _bars("B", [20.0 + i for i in range(22)])
    b_factors = pd.DataFrame({"trade_date": b["trade_date"], "factor": 1.0})
    a_rows = compute_forward_returns(
        a, [date(2020, 1, 1), date(2020, 1, 2)], stock_code="A",
        horizons=(1, 5, 20), adj_factors=a_factors,
        bar_version="bars-v2", factor_version="factors-v2",
    )
    b_rows = compute_forward_returns(
        b, [date(2020, 1, 1)], stock_code="B", horizons=(1, 5, 20),
        adj_factors=b_factors, bar_version="bars-v2", factor_version="factors-v2",
    )
    labels = pd.DataFrame([
        *label_frame(a_rows).to_dict("records"),
        *label_frame(b_rows).to_dict("records"),
    ])
    legacy_label = labels.iloc[[0]].copy()
    legacy_label["label_version"] = "legacy-v1"
    legacy_label["ret_1d"] = 0.99
    labels = pd.concat([labels, legacy_label], ignore_index=True)

    obs = pd.DataFrame([
        {"stock_code": code, "trade_date": day, "factor_id": "F", "direction": 1,
         "as_of": datetime.combine(day, time(15, 0)),
         "rule_score": 8.0, "normalized_value": 1.0,
         "engine_version": "engine-v2", "rule_version": "rule-v3", "config_version": "config-v1"}
        for code, day in (
            ("A", date(2020, 1, 1)), ("A", date(2020, 1, 2)), ("B", date(2020, 1, 1)),
        )
    ] + [{
        "stock_code": "A", "trade_date": date(2020, 1, 1), "factor_id": "F",
        "as_of": datetime.combine(date(2020, 1, 1), time(15, 0)),
        "direction": 1, "rule_score": 8.0, "normalized_value": 1.0,
        "engine_version": "engine-old", "rule_version": "rule-v3", "config_version": "config-v1",
    }])
    joined = join_versioned_event_frames(obs, labels, _query())

    assert joined["stock_code"].tolist() == ["A", "A"]
    first = joined[joined["trade_date"] == date(2020, 1, 1)].iloc[0]
    assert first["ret_1d"] == pytest.approx(0.0)
    assert pd.isna(first["ret_5d"])  # 期间缺一个因子日，不退回原始价格
    assert pd.isna(first["ret_20d"])  # 窗口不完整，保持不可用
    assert bool(first["horizon_available_1d"])
    assert not bool(first["horizon_available_5d"])


def test_duplicate_observation_key_fails_closed():
    obs = pd.DataFrame([
        {"stock_code": "A", "trade_date": date(2020, 1, 1), "factor_id": "F",
         "as_of": datetime.combine(date(2020, 1, 1), time(15, 0)),
         "direction": 1, "rule_score": 8.0, "normalized_value": 1.0,
         "engine_version": "engine-v2", "rule_version": "rule-v3", "config_version": "config-v1"}
    ] * 2)
    labels = pd.DataFrame(columns=[
        "stock_code", "trade_date", "label_version", "bar_version", "factor_version",
        "price_basis",
    ])
    with pytest.raises(ValueError, match="重复身份"):
        join_versioned_event_frames(obs, labels, _query())


def test_duplicate_label_key_fails_closed():
    obs = pd.DataFrame(columns=[
        "stock_code", "as_of", "trade_date", "factor_id", "direction", "rule_score",
        "normalized_value", "engine_version", "rule_version", "config_version",
    ])
    labels = pd.DataFrame([{
        "stock_code": "A", "trade_date": date(2020, 1, 1),
        "label_version": "w3-hfq-adjfactor-v2", "bar_version": "bars-v2",
        "factor_version": "factors-v2", "price_basis": "raw_times_factor",
    }] * 2)
    with pytest.raises(ValueError, match="重复股票/日期键"):
        join_versioned_event_frames(obs, labels, _query())


def test_query_requires_scope_conditions_and_versions():
    with pytest.raises(ValueError, match="显式指定至少一只股票"):
        _query(stock_codes=()).validate()
    with pytest.raises(ValueError, match="缺少计算、标签或数据版本"):
        _query(label_version="").validate()
    with pytest.raises(ValueError, match="raw_times_factor"):
        _query(price_basis="already_hfq").validate()
    with pytest.raises(ValueError, match="15:00"):
        _query(research_time=time(12, 0)).validate()
