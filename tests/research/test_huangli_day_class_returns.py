"""黄历分类历史表现：用**可手工核验的小样本**锁定统计口径。

研究结论最怕"算错了但看起来合理"。因此这里不用随机数据，
而是构造一组收盘价，使每类样本的持有期收益是精确可控的常数，
再断言均值 / 中位数 / 上涨占比 / 独立样本量逐个数字都对得上。

同时锁定三条纪律：
* 标签不完整或标签结束日超过基准日的样本**必须被剔除**（不是填 0）；
* 多日持有期必须披露重叠与互不重叠的有效样本量；
* **不得**出现净值 / 累计收益 / 策略收益这类字段（当前没有组合规则）。
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from src.core.stock.trading_calendar import get_trading_calendar_provider
from src.engines.huangli.huangli_engine import HuangliEngine
from src.research.huangli import day_class_returns as mod


@pytest.fixture()
def engine() -> HuangliEngine:
    return HuangliEngine()


def _trading_days(start: date, count: int) -> list[date]:
    cal = get_trading_calendar_provider().for_exchange("SSE")
    out: list[date] = []
    cursor = start
    while len(out) < count:
        if cal.is_trading_day(cursor).value is True:
            out.append(cursor)
        cursor += timedelta(days=1)
    return out


def _closes_for(days: list[date], engine: HuangliEngine, up: float, down: float) -> list[float]:
    """按"当天的分类"决定下一个交易日的涨跌幅，从而使标签可手工核验。"""
    closes = [100.0]
    for d in days[:-1]:
        info = mod._class_of_date(d.isoformat(), engine)
        ratio = up if info[0] == "auspicious" else down
        closes.append(closes[-1] * (1.0 + ratio))
    return closes


def _patch_loader(monkeypatch, days: list[date], closes: list[float]) -> None:
    frame = pd.DataFrame({"trade_date": days, "close": closes})
    frame.attrs["adj_factors"] = None
    monkeypatch.setattr(
        mod, "load_stock_bars",
        lambda code: (frame, {
            "adjust": "hfq", "source": "test_fixture",
            "return_basis_cn": "测试用后复权收盘价之比", "adj_factor_snapshot": None,
            "adj_factor_uncovered_rows": 0, "unavailable_reason": "",
        }),
    )
    monkeypatch.setattr(mod, "_load_benchmark", lambda code=mod.BENCHMARK_CODE: (None, "测试不提供基准"))


def test_1d_stats_match_hand_computed_values(monkeypatch, engine):
    days = _trading_days(date(2024, 11, 18), 21)
    closes = _closes_for(days, engine, up=0.01, down=-0.02)
    _patch_loader(monkeypatch, days, closes)

    as_of = datetime.combine(days[-1], datetime.min.time()).replace(hour=15)
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=as_of, window="custom",
        horizon=1, start=days[0].isoformat(), end=days[-1].isoformat(), engine=engine,
    )

    # 样本 = days[:-1]（最后一天没有次日收益）；类别由引擎给出
    expected_counts = {"auspicious": 0, "inauspicious": 0}
    for d in days[:-1]:
        expected_counts[mod._class_of_date(d.isoformat(), engine)[0]] += 1
    assert out["overlap"]["total_samples"] == len(days) - 1
    assert out["overlap"]["total_samples"] == sum(expected_counts.values())

    groups = {g["class_code"]: g for g in out["groups"]}
    # 吉日全部 +1.00%，凶日全部 -2.00% —— 均值/中位数/上涨占比都是精确值
    assert groups["auspicious"]["n"] == expected_counts["auspicious"]
    assert groups["auspicious"]["mean"] == pytest.approx(0.01, abs=1e-9)
    assert groups["auspicious"]["median"] == pytest.approx(0.01, abs=1e-9)
    assert groups["auspicious"]["up_share"] == pytest.approx(1.0, abs=1e-9)
    assert groups["inauspicious"]["mean"] == pytest.approx(-0.02, abs=1e-9)
    assert groups["inauspicious"]["up_share"] == pytest.approx(0.0, abs=1e-9)
    # 1 日持有期不存在重叠
    assert out["overlap"]["overlap_ratio"] == 0.0
    assert out["overlap"]["independent_samples"] == out["overlap"]["total_samples"]
    # 基准不可用时不得给超额数字
    assert out["labels"]["benchmark_available"] is False
    assert all(g["mean_excess"] is None for g in out["groups"])


def test_multi_day_horizon_uses_the_h_teenth_subsequent_bar(monkeypatch, engine):
    """5 日持有期 = 该股票自己的第 5 根后续 bar（停牌不填补）。"""
    days = _trading_days(date(2024, 11, 18), 30)
    closes = [100.0 * (1.001 ** i) for i in range(len(days))]  # 每日 +0.1%
    _patch_loader(monkeypatch, days, closes)

    as_of = datetime.combine(days[-1], datetime.min.time()).replace(hour=15)
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=as_of, window="custom",
        horizon=5, start=days[0].isoformat(), end=days[-1].isoformat(), engine=engine,
    )
    expected = closes[5] / closes[0] - 1.0
    for group in out["groups"]:
        assert group["mean"] == pytest.approx(expected, abs=1e-6), group["class_label_cn"]
    # 重叠披露
    assert out["overlap"]["overlap_ratio"] == pytest.approx(0.8)
    assert out["overlap"]["independent_samples"] < out["overlap"]["total_samples"]
    assert "重叠" in out["overlap"]["independent_note_cn"]


def test_samples_after_as_of_are_excluded(monkeypatch, engine):
    """标签结束日超过基准日的样本必须剔除 —— 这是防未来信息泄漏的核心断言。"""
    days = _trading_days(date(2024, 11, 18), 30)
    closes = [100.0 * (1.001 ** i) for i in range(len(days))]
    _patch_loader(monkeypatch, days, closes)

    cut = days[15]
    as_of = datetime.combine(cut, datetime.min.time()).replace(hour=15)
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=as_of, window="custom",
        horizon=5, start=days[0].isoformat(), end=cut.isoformat(), engine=engine,
    )
    # 有效样本 = days[:16-5] 共 11 个（索引 0..10，标签结束于 5..15）
    assert out["overlap"]["total_samples"] == 11
    # 纳入样本的最后一个标签结束日必须 ≤ 分析基准日
    assert out["labels"]["label_cutoff"] == cut.isoformat()
    assert out["labels"]["label_cutoff"] <= as_of.date().isoformat()
    assert out["window"]["effective_end"] == cut.isoformat()
    # data_cutoff 描述的是"本地行情新到哪一天"，可以晚于基准日（它只是数据新鲜度）
    assert out["labels"]["data_cutoff"] == days[-1].isoformat()
    # 被剔除的都是"标签不完整"
    assert out["labels"]["n_dropped_incomplete_label"] == 5
    for group in out["groups"]:
        assert group["n"] <= 11


def test_no_strategy_nav_fields_are_produced(monkeypatch, engine):
    """当前没有组合规则 → 不得产出净值 / 累计收益 / 策略收益。"""
    days = _trading_days(date(2024, 11, 18), 21)
    closes = _closes_for(days, engine, up=0.01, down=-0.02)
    _patch_loader(monkeypatch, days, closes)
    as_of = datetime.combine(days[-1], datetime.min.time()).replace(hour=15)
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=as_of, window="custom",
        horizon=1, start=days[0].isoformat(), end=days[-1].isoformat(), engine=engine,
    )
    def _keys(obj) -> set[str]:
        if isinstance(obj, dict):
            return set(obj) | {k for v in obj.values() for k in _keys(v)}
        if isinstance(obj, list):
            return {k for v in obj for k in _keys(v)}
        return set()

    keys = _keys(out)
    for forbidden in ("nav", "nav_series", "cumulative_return", "equity_curve",
                      "strategy_return", "sharpe", "max_drawdown"):
        assert forbidden not in keys, f"不应出现 {forbidden} 字段"
    # 序列口径必须自述"不是净值"
    assert "不是净值" in out["series"]["metric_cn"]
    assert out["series"]["metric_cn"].startswith("纵轴为")
    assert "不是策略回测" in out["limitations_cn"][0]


def test_missing_bars_reports_unavailable_not_zero(monkeypatch):
    monkeypatch.setattr(
        mod, "load_stock_bars",
        lambda code: (pd.DataFrame(columns=["trade_date", "close"]), {
            "adjust": None, "source": None, "return_basis_cn": "",
            "adj_factor_snapshot": None, "adj_factor_uncovered_rows": 0,
            "unavailable_reason": f"本地行情库中没有 {code} 的日线。",
        }),
    )
    out = mod.build_day_class_performance(
        stock_code="NOPE", as_of=datetime(2024, 11, 15, 15), window="1y", horizon=1,
    )
    assert out["groups"] == []
    assert out["unavailable_reason"]
    assert any(w["code"] == "HUANGLI_PERF_NO_BARS" for w in out["warnings"])


def test_window_before_listing_reports_unavailable(monkeypatch, engine):
    days = _trading_days(date(2024, 11, 18), 21)
    _patch_loader(monkeypatch, days, [100.0 + i for i in range(len(days))])
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=datetime(2020, 1, 10, 15), window="1y", horizon=1, engine=engine,
    )
    assert out["unavailable_reason"]
    assert out["groups"] == []


def test_custom_window_requires_start():
    with pytest.raises(ValueError):
        mod.build_day_class_performance(
            stock_code="600519", as_of=datetime(2024, 11, 15, 15), window="custom", horizon=1,
        )


def test_unsupported_horizon_rejected():
    with pytest.raises(ValueError):
        mod.build_day_class_performance(
            stock_code="600519", as_of=datetime(2024, 11, 15, 15), horizon=2,
        )


def test_expanding_series_is_not_a_nav(monkeypatch, engine):
    """序列值 = 截至该日的扩展均值；早期样本少时必须显式给出计数。"""
    days = _trading_days(date(2024, 11, 18), 25)
    closes = _closes_for(days, engine, up=0.02, down=-0.01)
    _patch_loader(monkeypatch, days, closes)
    as_of = datetime.combine(days[-1], datetime.min.time()).replace(hour=15)
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=as_of, window="custom",
        horizon=1, start=days[0].isoformat(), end=days[-1].isoformat(), engine=engine,
    )
    series = out["series"]
    assert len(series["dates"]) == out["overlap"]["total_samples"]
    for cls, values in series["by_class"].items():
        counts = series["counts_by_class"][cls]
        assert len(values) == len(counts) == len(series["dates"])
        # 每个点都是"该类别截至该日的样本均值"，不是累计乘积
        seen: list[float] = []
        for i, value in enumerate(values):
            if counts[i] == 0:
                assert value is None
                continue
            # 该类别在第 i 个位置是否新增样本，取决于当天分类
            if counts[i] > (counts[i - 1] if i else 0):
                seen.append(0.02 if cls == "auspicious" else -0.01)
            assert value == pytest.approx(statistics.fmean(seen), abs=1e-6)


def test_key_findings_are_objective_and_disclaim_causality(monkeypatch, engine):
    days = _trading_days(date(2024, 11, 18), 25)
    closes = _closes_for(days, engine, up=0.02, down=-0.01)
    _patch_loader(monkeypatch, days, closes)
    as_of = datetime.combine(days[-1], datetime.min.time()).replace(hour=15)
    out = mod.build_day_class_performance(
        stock_code="TEST", as_of=as_of, window="custom",
        horizon=1, start=days[0].isoformat(), end=days[-1].isoformat(), engine=engine,
    )
    texts = " ".join(f["text_cn"] for f in out["key_findings"])
    assert "描述性" in texts
    assert "因果" in texts
    for forbidden in ("必涨", "一定上涨", "保证上涨", "建议买", "建议卖", "择时有效"):
        assert forbidden not in texts
