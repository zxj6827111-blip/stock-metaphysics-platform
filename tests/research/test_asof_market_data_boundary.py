"""Red Team 扩展 §八-1/2/5：行情与基准的 as_of 边界。

新增覆盖面（超出既有 test_no_future_data_access.py 的哨兵污染法）：

1. 股票基础资料的 point-in-time 检查 —— 名称/行业等字段是"当前资料"，
   必须被显式标注而非假装历史时点值；
2. benchmark 数据的 as_of 边界；
3. 未来收益只能作为 label —— 标签绝不允许回流到特征侧；
4. 事件研究面板中观测侧绝不允许引用 as_of 之后的行情。
"""

from __future__ import annotations

from datetime import date

from src.market.normalization.frames import clip_to_as_of
from src.research.labels.forward_returns import compute_labels

AS_OF = date(2021, 6, 30)


class TestBenchmarkBoundary:
    """基准指数同样受 as_of 隔离约束；超额收益只能用作标签。"""

    def test_benchmark_clipped_correctly(self, market):
        bench = market.get_benchmark_bars("000300", date(2019, 1, 1), date(2023, 1, 1))
        clipped = clip_to_as_of(bench, AS_OF)
        assert clipped.bars
        assert max(b.trade_date for b in clipped.bars) <= AS_OF

    def test_excess_return_uses_only_forward_benchmark(self, market):
        """超额收益 = 股票未来收益 − 基准未来收益。

        反向对照：污染 as_of 之后的基准数据必须改变 excess_return_20d
        （这证明超额来自"未来基准"——它是标签的一部分，不是特征）。
        """
        series = market.get_daily_bars("600519", date(2019, 1, 1), date(2023, 1, 1))
        bench = market.get_benchmark_bars("000300", date(2019, 1, 1), date(2023, 1, 1))

        dirty_bench = bench.model_copy(update={
            "bars": [
                b.model_copy(update={"close": (b.close or 0) * 5.0}) if b.trade_date > AS_OF else b
                for b in bench.bars
            ]
        })
        clean_labels = compute_labels(series, AS_OF, benchmark_series=bench)
        dirty_labels = compute_labels(series, AS_OF, benchmark_series=dirty_bench)
        assert clean_labels.bench_ret_20d != dirty_labels.bench_ret_20d, (
            "基准未来数据污染后 bench_ret_20d 未变化 —— 超额收益计算异常"
        )
        # 但股票侧收益不受基准污染影响
        assert clean_labels.ret_20d == dirty_labels.ret_20d


class TestStockMasterPointInTime:
    """股票基础资料（名称/行业）是"当前时点"信息，研究引用时必须显式标注。"""

    def test_stock_master_marked_as_current_snapshot(self, market):
        stock = market.get_stock("600519")
        # StockMaster.source 必须携带来源，不得裸奔
        assert stock.source is not None and stock.source.source
        # 系统在 schema 层不把 stock 基础资料伪装成历史时点值：
        # as_of 相关字段只存在于因子/标签/盘面，不在 StockMaster 上
        assert not hasattr(stock, "as_of"), "StockMaster 不应携带 as_of 字段（误导性）"

    def test_listing_date_before_as_of_is_used_consistently(self, market):
        stock = market.get_stock("601318")
        assert stock.listing_date is not None and stock.listing_date < AS_OF


class TestMarketBarsNeverFlowIntoFeatures:
    """行情 bar 永远不得进入因子观测。"""

    def test_observation_rows_have_no_price_columns(self):
        from src.core.schemas.factor import FactorObservation
        from src.research.pipeline import _observation_rows

        obs = FactorObservation(
            factor_id="B_NATAL_001", stock_code="600519",
            as_of=__import__("datetime").datetime(2024, 1, 1),
            engine="bazi", category="natal", name="日主强弱",
            raw_value="身强", normalized_value=1.0, direction=1,
            rule_score=10.0, confidence=0.9,
            rule_version="v1", evidence=[], explanation="x",
        )
        rows = _observation_rows([obs])
        forbidden = {"close", "open", "high", "low", "volume", "pct_change",
                     "ret_1d", "ret_5d", "ret_20d", "excess_return_20d"}
        assert not (set(rows[0]) & forbidden), f"观测行混入行情字段: {set(rows[0]) & forbidden}"

    def test_panel_join_key_is_trade_date_only(self):
        """面板连接键只能是 (stock_code, trade_date)，不能携带任何前视字段。"""
        import inspect

        from src.research.pipeline import _align_observation_trade_dates

        src = inspect.getsource(_align_observation_trade_dates)
        for forbidden in ("close", "ret_20d", "volume"):
            assert forbidden not in src, f"对齐函数读取了行情字段 {forbidden}"
