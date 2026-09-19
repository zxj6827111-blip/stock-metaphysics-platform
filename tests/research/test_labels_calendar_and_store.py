"""标签与 Backtest 验收（§七）：交易日语义、停牌对齐、标签持久化。

关键口径断言：

* ``ret_5d`` 的第 5 是**第 5 个交易bar**，不是自然日；
* 股票停牌期间，超额收益的基准窗口必须与股票实际跨越的**日历区间**对齐
  （此前的实现是对"基准第 20 根 bar"，停牌长时会口径错配）；
* 标签写库后重读，结果逐字段一致（幂等）；
* 缺失数据不填 0。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.core.schemas.market import Bar, BarSeries
from src.research.labels.forward_returns import compute_labels


def _series(code: str, days: list[date], closes: list[float]) -> BarSeries:
    bars = [
        Bar(trade_date=d, open=c, high=c * 1.01, low=c * 0.99, close=c,
            volume=1e6, amount=c * 1e6, adjust="hfq")
        for d, c in zip(days, closes, strict=True)
    ]
    return BarSeries(stock_code=code, bars=bars, adjust="hfq", is_degraded=False)


def _trading_days(start: date, n: int) -> list[date]:
    days = []
    cur = start
    while len(days) < n:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


class TestTradingDaySemantics:
    def test_ret_5d_is_five_trading_sessions_not_calendar_days(self):
        days = _trading_days(date(2024, 1, 8), 30)  # 周一开始
        prices = [100.0] + [100.0 + i for i in range(1, 30)]
        series = _series("600519", days, prices)
        labels = compute_labels(series, date(2024, 1, 8), benchmark_series=None)
        # 第 5 个交易日的 close = 100+5 = 105 → ret_5d = 5%
        assert labels.ret_5d == pytest.approx(0.05, abs=1e-6)
        # 检查天数：第 5 根 bar 距 as_of（周一）应是下一个周一（跨周末）
        assert labels.trade_date == date(2024, 1, 8)
        target_bar_date = days[5]
        assert (target_bar_date - days[0]).days == 7, f"5 个交易日跨越 7 个自然日: {target_bar_date}"

    def test_suspension_gap_aligned_for_benchmark(self):
        """停牌 10 天的股票，其 20D 窗口跨越 30+ 自然日，基准必须按同一日历区间算。"""
        stock_days = _trading_days(date(2024, 1, 8), 15)
        gap_days = [d + timedelta(days=30) for d in _trading_days(date(2024, 2, 6), 10)]
        stock_days = stock_days + gap_days  # 中间刻意隔 30 天 ≈ 停牌
        assert len(stock_days) == 25
        prices = [100.0] * 15 + [110.0] * 10
        series = _series("600519", stock_days, prices)

        bench_days = _trading_days(date(2024, 1, 8), 80)
        bench_prices = [2000.0 * (1 + 0.001 * i) for i in range(80)]
        bench = _series("000300", bench_days, bench_prices)

        labels = compute_labels(series, date(2024, 1, 8), benchmark_series=bench)
        assert labels.ret_20d == pytest.approx(0.10, abs=1e-6)
        assert labels.bench_ret_20d is not None
        # 股票 20D 窗口结束于 stock_days[20]，基准必须涨到同一日历日，
        # 而不是基准自己的第 20 根 bar（那样窗口会短约 10 个交易日）。
        end_date = stock_days[20]
        b_start = next(i for i, d in enumerate(bench_days) if d >= date(2024, 1, 8))
        b_end = next(i for i, d in enumerate(bench_days) if d >= end_date)
        expected_bench = bench_prices[b_end] / bench_prices[b_start] - 1.0
        assert labels.bench_ret_20d == pytest.approx(expected_bench, abs=1e-6)

    def test_missing_forward_data_never_zero_filled(self):
        days = _trading_days(date(2024, 1, 8), 10)
        series = _series("600519", days, [100.0] * 10)
        labels = compute_labels(series, date(2024, 1, 8), benchmark_series=None)
        assert labels.ret_20d is None
        assert labels.horizon_available["20d"] is False


class TestLabelPersistence:
    def test_upsert_round_trip(self, db_session):
        from src.research.labels.store import load_label_rows, upsert_label

        days = _trading_days(date(2024, 1, 8), 80)
        series = _series("900001", days, [100.0 + i for i in range(80)])
        series.source_ref.source = "tencent_hfq_import"
        labels = compute_labels(series, date(2024, 1, 8), benchmark_series=None)
        labels.data_source = "tencent_hfq_import"
        upsert_label(db_session, labels, data_snapshot="2026-09-18")
        db_session.flush()

        rows, meta = load_label_rows(db_session, benchmark_code="000300")
        mine = [r for r in rows if r["stock_code"] == "900001"]
        assert len(mine) == 1, f"应只有 1 行 900001 标签，实际 {len(mine)}"
        assert mine[0]["ret_20d"] == pytest.approx(labels.ret_20d or 0)
        assert "900001" not in meta["degraded_codes"]

    def test_synthetic_label_marked_degraded(self, db_session):
        from src.research.labels.store import load_label_rows, upsert_label

        days = _trading_days(date(2024, 1, 8), 80)
        series = _series("900002", days, [100.0 + i for i in range(80)])
        # 模拟合成数据：污染 series
        series = series.model_copy(update={"is_degraded": True})
        series.source_ref.source = "synthetic_demo"
        labels = compute_labels(series, date(2024, 1, 8), benchmark_series=None)
        assert labels.data_is_degraded is True
        upsert_label(db_session, labels)
        db_session.flush()

        rows, meta = load_label_rows(db_session, benchmark_code="000300")
        assert "900002" in meta["degraded_codes"]

    def test_upsert_is_idempotent_same_snapshot(self, db_session):
        from src.db.models import ForwardLabelRow
        from src.research.labels.store import upsert_label

        days = _trading_days(date(2024, 1, 8), 80)
        series = _series("900003", days, [100.0 + i for i in range(80)])
        labels = compute_labels(series, date(2024, 1, 8), benchmark_series=None)
        labels.data_source = "tencent_hfq_import"
        upsert_label(db_session, labels, data_snapshot="s1")
        upsert_label(db_session, labels, data_snapshot="s1")  # 同键重复写 → 必须幂等
        db_session.flush()
        count = db_session.query(ForwardLabelRow).filter_by(
            stock_code="900003", label_source="tencent_hfq_import").count()
        assert count == 1, "同一快照重复写必须幂等"
