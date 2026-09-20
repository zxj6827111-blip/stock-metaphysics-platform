"""Phase 3E · 风格暴露测试（含防未来数据泄漏硬断言）。"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.research.neutralization.exposures import (
    EXPOSURE_VERSION,
    MARKET_CAP_UNAVAILABLE,
    SIZE_PROXY_LIQUIDITY_AMOUNT,
    STYLE_EXPOSURE_COLUMNS,
    VALUE_FACTOR_UNAVAILABLE,
    build_exposure_panel,
    compute_stock_exposures,
    exposure_availability,
    zscore_cross_section,
)


def _business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _bars(days: list[date], closes: list[float], amounts: list[float] | None = None) -> pd.DataFrame:
    return pd.DataFrame({
        "trade_date": days,
        "close": closes,
        "amount": amounts if amounts is not None else [1_000_000.0] * len(days),
    })


def test_momentum_matches_manual_window() -> None:
    """momentum_60d 必须严格等于 trailing 60 个交易日的累计收益。"""
    days = _business_days(date(2020, 1, 1), 200)
    closes = list(np.linspace(10.0, 30.0, 200))
    as_of = days[-1]
    rows = compute_stock_exposures(_bars(days, closes), [as_of], stock_code="X")
    assert len(rows) == 1
    row = rows[0]
    expected = closes[-1] / closes[-61] - 1.0
    assert row["momentum_60d"] == pytest.approx(expected, abs=1e-8)
    assert row["momentum_120d"] == pytest.approx(closes[-1] / closes[-121] - 1.0, abs=1e-8)
    assert row["bar_date"] == as_of


def test_momentum_unavailable_when_history_too_short() -> None:
    """历史不足时必须为 None（不得填 0 冒充）。"""
    days = _business_days(date(2020, 1, 1), 30)
    rows = compute_stock_exposures(_bars(days, [10.0] * 30), [days[-1]], stock_code="X")
    assert rows[0]["momentum_60d"] is None
    assert rows[0]["momentum_120d"] is None


def test_volatility_uses_log_returns_of_window() -> None:
    days = _business_days(date(2020, 1, 1), 80)
    rng = np.random.default_rng(7)
    closes = 10.0 * np.exp(np.cumsum(rng.normal(0, 0.02, 80)))
    rows = compute_stock_exposures(_bars(days, list(closes)), [days[-1]], stock_code="X")
    log_ret = np.diff(np.log(closes[-21:]))
    assert rows[0]["volatility_20d"] == pytest.approx(float(log_ret.std(ddof=1)), abs=1e-8)


def test_exposures_are_frozen_against_future_bars() -> None:
    """核心防泄漏断言：改写 as_of 之后的 bar，暴露值必须**逐位不变**。

    这不是"人工检查"，而是把未来数据篡改成极端值后做等价比较 ——
    任何一处不小心用到未来 bar（窗口越界、ffill 到未来、索引偏移）都会被抓住。
    """
    days = _business_days(date(2020, 1, 1), 300)
    rng = np.random.default_rng(11)
    closes = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.015, 300)))
    amounts = rng.uniform(1e5, 1e8, 300)
    original = _bars(days, list(closes), list(amounts))
    as_of = days[199]

    tampered = original.copy()
    future = tampered["trade_date"] > as_of
    tampered.loc[future, "close"] = tampered.loc[future, "close"] * 1000.0
    tampered.loc[future, "amount"] = tampered.loc[future, "amount"] * 1000.0

    base_rows = compute_stock_exposures(original, [as_of], stock_code="X")
    tampered_rows = compute_stock_exposures(tampered, [as_of], stock_code="X")
    assert base_rows == tampered_rows
    for column in STYLE_EXPOSURE_COLUMNS:
        assert base_rows[0][column] is not None


def test_bar_index_and_date_reflect_last_visible_bar() -> None:
    """as_of 落在非交易日时，窗口末端必须回退到之前的最后一个交易日。"""
    days = _business_days(date(2020, 1, 1), 100)
    weekend = days[50]
    while weekend.weekday() != 5:  # 找到一个周六
        weekend += timedelta(days=1)
    assert weekend.weekday() == 5
    bars = [day for day in days if day <= weekend]
    rows = compute_stock_exposures(
        _bars(bars, [10.0] * len(bars)), [weekend], stock_code="X",
    )
    assert rows[0]["bar_date"] == bars[-1]
    assert rows[0]["bar_date"] < weekend


def test_amount_proxy_uses_mean_of_window() -> None:
    days = _business_days(date(2020, 1, 1), 60)
    amounts = [float(100 * (index + 1)) for index in range(60)]
    rows = compute_stock_exposures(
        _bars(days, [10.0] * 60, amounts), [days[-1]], stock_code="X",
    )
    expected = float(np.log1p(np.mean(amounts[-20:])))
    assert rows[0]["size_proxy_log_amount_20d"] == pytest.approx(expected, abs=1e-8)
    assert rows[0]["size_proxy_status"] == SIZE_PROXY_LIQUIDITY_AMOUNT
    assert rows[0]["market_cap_status"] == MARKET_CAP_UNAVAILABLE


def test_availability_records_size_and_value_gaps() -> None:
    """不可用维度必须显式出现在可得性记录里，不能被静默省略。"""
    availability = exposure_availability()
    payload = availability.to_dict()
    assert payload["size_status"] == SIZE_PROXY_LIQUIDITY_AMOUNT
    assert payload["value_status"] == VALUE_FACTOR_UNAVAILABLE
    assert payload["unavailable_dimensions"]["value"] == VALUE_FACTOR_UNAVAILABLE
    assert payload["unavailable_dimensions"]["size_market_cap"] == MARKET_CAP_UNAVAILABLE
    assert payload["exposure_version"] == EXPOSURE_VERSION


def test_build_exposure_panel_reports_coverage() -> None:
    days = _business_days(date(2020, 1, 1), 200)
    bars = {"A": _bars(days, list(np.linspace(10, 20, 200))),
            "B": _bars(days[:40], [10.0] * 40)}
    frame, meta = build_exposure_panel(bars, [days[-1]])
    assert len(frame) == 2
    assert meta["stock_count"] == 2
    full = frame[frame["stock_code"] == "A"].iloc[0]
    short = frame[frame["stock_code"] == "B"].iloc[0]
    assert full["momentum_120d"] is not None
    # DataFrame 化之后缺失表现为 NaN（仍然不是 0，不会被误当有效暴露）
    assert pd.isna(short["momentum_120d"])
    assert meta["columns"]["momentum_120d"]["usable"] == 1
    assert 0.0 < meta["columns"]["momentum_120d"]["coverage_ratio"] < 1.0


def test_zscore_cross_section_is_per_date_and_none_for_constant() -> None:
    frame = pd.DataFrame({
        "as_of": [date(2021, 1, 1)] * 3 + [date(2021, 2, 1)] * 3,
        "momentum_60d": [1.0, 2.0, 3.0, 5.0, 5.0, 5.0],
    })
    out = zscore_cross_section(frame, ["momentum_60d"])
    first = out[out["as_of"] == date(2021, 1, 1)]["z_momentum_60d"].tolist()
    assert first[1] == pytest.approx(0.0, abs=1e-12)
    assert first[0] < 0 < first[2]
    second = out[out["as_of"] == date(2021, 2, 1)]["z_momentum_60d"].tolist()
    assert all(pd.isna(value) for value in second), "常量截面必须是 NaN，不能是 0"
