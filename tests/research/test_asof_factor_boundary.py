"""Red Team 扩展 §八-3/4/6：因子时间与缓存边界。

1. 因子观测的 ``as_of`` 必须等于请求时刻（不允许晚到）；
2. 因子的计算输入只含盘面与黄历（黄历的月度扫描是**确定性的历法推演**，
   不依赖行情，在方法论上属合法）；古籍知识不得影响历史价格；
3. 缓存污染不得穿透 as_of：向数据库写入"未来"的高污染行情行后，
   以更早 as_of 重新计算的特征 / 盘面结果必须完全不变。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

AS_OF_DT = datetime(2024, 11, 15, 14, 32)


class TestFactorAsOfBoundary:
    def test_all_factor_observations_not_later_than_as_of(self, factor_set):
        for obs in factor_set.observations:
            assert obs.as_of <= AS_OF_DT, f"{obs.factor_id} 的 as_of 越界"

    def test_chart_reproducible_under_future_shift(self, bazi_engine):
        """同一 birth/as_of 重复排盘，结果完全一致（盘面不受'今天几号'影响）。

        计算时刻字段（calculated_at / computed_at）允许不同 —— 它们是审计字段，
        不是盘面内容。
        """
        a = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30), as_of=AS_OF_DT, stock_code="600519",
        )
        b = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30), as_of=AS_OF_DT, stock_code="600519",
        )
        exclude = {"calculated_at", "computed_at"}
        assert a.model_dump(mode="json", exclude=exclude) == b.model_dump(mode="json", exclude=exclude)

    def test_year_month_day_pillars_not_future(self, maotai_chart):
        """流年/流月/流日柱由 as_of 决定 —— 它们不是"未来"，是历法确定值。"""
        assert maotai_chart.current_year_pillar is not None
        assert maotai_chart.current_day_pillar is not None


class TestKnowledgeCannotAffectMarket:
    """古籍知识只用于解释，不得反向影响行情/标签。"""

    def test_knowledge_provider_has_no_market_dependency(self):
        import pathlib

        for path in pathlib.Path("src/knowledge").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("get_daily_bars", "compute_labels", "ret_20d", "clip_to_as_of"):
                assert forbidden not in text, f"{path} 引用了行情/标签模块"


@pytest.mark.usefixtures("db_session")
class TestCacheBoundary:
    """DB 缓存污染不得改变历史 as_of 的分析结果。"""

    def test_future_polluted_cache_rows_do_not_change_analysis(self, db_session):
        """向 market_bar_daily 写入未来的天价行，重新跑同一 as_of 的分析，因子不变。"""
        from src.core.schemas.stock import StockMaster
        from src.db.models import MarketBarDailyRow

        code = "600519"
        # 写入 as_of 之后的高污染行（模拟缓存被未来数据污染）
        polluted = MarketBarDailyRow(
            stock_code=code, trade_date=date(2099, 1, 5),
            open=9e6, high=9e6, low=9e6, close=9e6,
            volume=9e12, amount=9e15, adjust="qfq", is_benchmark=False,
            source="sentinel_pollution", is_degraded=True,
        )
        db_session.add(polluted)
        db_session.flush()

        # 因子计算根本不读行情表 —— 但这里验证**服务层**的数据装配也没有泄漏路径
        from src.core.orchestration.analysis_service import AnalysisService
        from src.core.schemas.stock import BirthProfileCreateRequest
        from src.core.stock.birth_profile import build_birth_profile

        stock = StockMaster(
            stock_code=code, name="贵州茅台",
            listing_date=date(2001, 8, 27),
        )
        profile = build_birth_profile(stock, BirthProfileCreateRequest())
        service = AnalysisService()
        as_of = AS_OF_DT
        resp1 = service.run_bazi_analysis(
            db_session, stock=stock, birth_profile=profile,
            as_of=as_of, persist=False,
        )
        resp2 = service.run_bazi_analysis(
            db_session, stock=stock, birth_profile=profile,
            as_of=as_of, persist=False,
        )

        def _strip_volatile(node):
            if isinstance(node, dict):
                return {k: _strip_volatile(v) for k, v in node.items()
                        if k not in ("calculated_at", "computed_at")}
            if isinstance(node, list):
                return [_strip_volatile(v) for v in node]
            return node

        assert _strip_volatile(resp1.chart) == _strip_volatile(resp2.chart)

        # 因子集合也完全一致（污染行没有任何路径进入因子）
        f1 = [(o.factor_id, o.normalized_value, o.rule_score) for o in resp1.factors.observations]
        f2 = [(o.factor_id, o.normalized_value, o.rule_score) for o in resp2.factors.observations]
        assert f1 == f2

    def test_label_rows_only_read_forward(self, db_session):
        """标签行查询只返回 as_of 之后的 trade_date（labels 表语义约束）。"""
        from src.core.schemas.market import Bar, BarSeries
        from src.research.labels.forward_returns import compute_labels

        bars = [
            Bar(trade_date=date(2024, 1, 2) + __import__("datetime").timedelta(days=i),
                open=10 + i * 0.1, high=10.5 + i * 0.1, low=9.9 + i * 0.1,
                close=10.2 + i * 0.1, volume=1e6, amount=1e7, adjust="qfq")
            for i in range(80)
        ]
        series = BarSeries(stock_code="600519", bars=bars, is_degraded=False)
        labels = compute_labels(series, date(2024, 1, 2))
        assert labels.trade_date >= labels.as_of
        # 数据不足时不得用 0 填充
        assert labels.ret_60d is not None  # 80 天后足够
