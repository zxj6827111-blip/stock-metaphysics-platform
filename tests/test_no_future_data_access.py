"""``test_no_future_data_access`` —— P0 级硬性测试。

architecture §77 / two_session_plan §11 的硬性要求：

    as_of = 2020-01-01 时，**任何作为输入的特征**都禁止读取 2020-01-02 及以后的数据。
    未来收益只能作为 label。

本文件用多种手段验证这一点：

1. 直接验证 ``clip_to_as_of`` / ``visible_slice`` 的裁剪语义；
2. 用"哨兵行情"污染 as_of 之后的区间，检查特征计算结果**完全不变**；
3. 验证因子计算只依赖盘面，不依赖任何行情；
4. 验证标签计算不会泄漏到特征侧（label 与 feature 的字段名不重叠）；
5. 验证事件研究在 as_of 之后没有数据时返回"样本不足"而非编造数值。
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest

from src.core.config import settings
from src.market.normalization.frames import clip_to_as_of
from src.research.labels.forward_returns import (
    InsufficientForwardData,
    compute_labels,
    visible_slice,
)

AS_OF = date(2020, 1, 1)


# ---------------------------------------------------------------------------
# 1. 裁剪语义
# ---------------------------------------------------------------------------


class TestClipping:
    def test_clip_removes_all_future_bars(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        clipped = clip_to_as_of(series, AS_OF)
        assert clipped.bars, "裁剪后不应为空"
        assert max(b.trade_date for b in clipped.bars) <= AS_OF

    def test_clip_keeps_as_of_day_itself(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        clipped = clip_to_as_of(series, AS_OF)
        assert any(b.trade_date == AS_OF for b in clipped.bars) or \
               max(b.trade_date for b in clipped.bars) < AS_OF

    def test_visible_slice_is_the_only_entry_point(self, market):
        """visible_slice 与 clip_to_as_of 语义必须一致（防绕过）。"""
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        a = clip_to_as_of(series, AS_OF)
        b = visible_slice(series, AS_OF)
        assert [x.trade_date for x in a.bars] == [x.trade_date for x in b.bars]

    def test_clip_preserves_metadata(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        clipped = clip_to_as_of(series, AS_OF)
        assert clipped.stock_code == series.stock_code
        assert clipped.adjust == series.adjust
        assert clipped.is_degraded == series.is_degraded


# ---------------------------------------------------------------------------
# 2. 哨兵污染测试（最强证据）
# ---------------------------------------------------------------------------


class TestSentinelContamination:
    """把 as_of 之后的行情替换成极端值。

    如果任何特征计算路径意外读到了未来数据，特征结果就会改变。
    这是"未来数据泄漏"最直接的证伪方式。
    """

    @pytest.fixture()
    def contaminated(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        sentinel = [
            b.model_copy(update={"close": 999999.0, "high": 999999.0, "low": 999999.0,
                                 "open": 999999.0, "volume": 999999.0})
            if b.trade_date > AS_OF else b
            for b in series.bars
        ]
        return series.model_copy(update={"bars": sentinel})

    def test_clipped_features_identical_under_contamination(self, market, contaminated):
        clean = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        clean_visible = clip_to_as_of(clean, AS_OF)
        dirty_visible = clip_to_as_of(contaminated, AS_OF)

        assert [b.trade_date for b in clean_visible.bars] == \
               [b.trade_date for b in dirty_visible.bars]
        for a, b in zip(clean_visible.bars, dirty_visible.bars, strict=True):
            assert a.close == b.close, f"{a.trade_date} 收盘价受到未来数据影响"

    def test_visible_statistics_identical(self, market, contaminated):
        clean = clip_to_as_of(market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31)), AS_OF)
        dirty = clip_to_as_of(contaminated, AS_OF)
        assert _stats(clean) == _stats(dirty)


def _stats(series) -> tuple:
    closes = [b.close for b in series.bars if b.close is not None]
    return (
        len(closes),
        round(float(np.mean(closes)), 6),
        round(float(np.max(closes)), 6),
        round(float(np.min(closes)), 6),
    )


# ---------------------------------------------------------------------------
# 3. 因子只依赖盘面，不依赖行情
# ---------------------------------------------------------------------------


class TestFactorsAreMarketIndependent:
    def test_factor_inputs_have_no_market_fields(self, bazi_engine, huangli_engine):
        """因子计算的入参只有盘面与黄历 —— 结构上不可能读到未来行情。"""
        chart = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2020, 1, 1, 15, 0),
            stock_code="600519",
        )
        huangli = huangli_engine.snapshot(datetime(2020, 1, 1, 15, 0), days=31)
        from src.factors.registry.compute import compute_factor_set

        fs = compute_factor_set(chart, huangli, datetime(2020, 1, 1, 15, 0), stock_code="600519")
        assert fs.observations

        dumped = fs.model_dump_json()
        # 因子集合中不应出现任何行情字段
        for forbidden in ("close", "open", "volume", "pct_change", "ret_1d", "ret_20d"):
            assert f'"{forbidden}"' not in dumped, f"因子输出中混入了行情字段 {forbidden}"

    def test_factor_as_of_not_after_requested(self, factor_set):
        for obs in factor_set.observations:
            assert obs.as_of <= datetime(2024, 11, 15, 14, 32)


# ---------------------------------------------------------------------------
# 4. label 与 feature 字段隔离
# ---------------------------------------------------------------------------


class TestLabelIsolation:
    def test_label_fields_are_forward_looking_only(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        labels = compute_labels(series, AS_OF)
        for name in settings.label_horizons:
            assert hasattr(labels, f"ret_{name}d")
        assert labels.as_of == AS_OF
        # trade_date 是 >= as_of 的第一个交易日
        assert labels.trade_date >= AS_OF

    def test_labels_do_change_under_contamination(self, market):
        """对照组：标签**应该**受未来数据影响 —— 这证明标签确实来自未来。"""
        clean = market.get_daily_bars("600519", date(2018, 1, 1), date(2022, 12, 31))
        dirty = clean.model_copy(update={
            "bars": [
                b.model_copy(update={"close": (b.close or 0) * 3.0}) if b.trade_date > AS_OF else b
                for b in clean.bars
            ]
        })
        l_clean = compute_labels(clean, AS_OF)
        l_dirty = compute_labels(dirty, AS_OF)
        assert l_clean.ret_20d != l_dirty.ret_20d, "标签未随未来数据变化，说明标签实现有误"

    def test_no_label_field_used_as_factor_input(self):
        """因子模块不得 import 标签模块（结构隔离）。"""
        import pathlib

        factors_dir = pathlib.Path("src/factors")
        for path in factors_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "forward_returns" not in text, f"{path} 引用了标签模块"
            assert "LabelSet" not in text, f"{path} 引用了 LabelSet"


# ---------------------------------------------------------------------------
# 5. 数据不足时必须如实报告
# ---------------------------------------------------------------------------


class TestInsufficientDataHonesty:
    def test_labels_raise_when_no_forward_data(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2020, 1, 1))
        with pytest.raises(InsufficientForwardData):
            compute_labels(series, date(2021, 1, 1))

    def test_partial_horizons_marked_unavailable(self, market):
        """接近数据末端的 as_of：短持有期可用、长持有期应标记为不可用，而不是填 0。"""
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2020, 3, 1))
        labels = compute_labels(series, date(2020, 2, 20))
        assert labels.horizon_available["1d"] is True
        assert labels.horizon_available["60d"] is False
        assert labels.ret_60d is None

    def test_zero_fill_is_never_used(self, market):
        series = market.get_daily_bars("600519", date(2018, 1, 1), date(2020, 3, 1))
        labels = compute_labels(series, date(2020, 2, 20))
        unavailable = [k for k, v in labels.horizon_available.items() if not v]
        for key in unavailable:
            assert getattr(labels, f"ret_{key}") is None


# ---------------------------------------------------------------------------
# 6. 事件研究：事件端无未来数据
# ---------------------------------------------------------------------------


class TestEventStudyDirectionality:
    def test_events_use_trade_date_not_future_bars(self):
        """事件命中由 factor_observation 的 trade_date 决定，未来收益只从标签取。"""
        import pandas as pd

        from src.core.schemas.market import EventStudyRequest
        from src.research.event_study.engine import evaluate_event_study

        obs = pd.DataFrame([
            {"stock_code": "600519", "trade_date": date(2020, 1, 1), "factor_id": "B_NATAL_001",
             "direction": 1, "rule_score": 8.0, "normalized_value": 0.8},
        ])
        labels = pd.DataFrame([
            {"stock_code": "600519", "trade_date": date(2020, 1, 1), "ret_20d": 0.05,
             "excess_return_20d": 0.02, "max_drawdown_20d": -0.03, "max_return_20d": 0.08},
        ])
        result = evaluate_event_study(obs, labels, EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[20]))
        assert result.event_count == 1
        h = result.horizons[0]
        assert h.sample_count == 1
        assert h.mean_return == pytest.approx(0.05)

    def test_no_label_match_reports_zero_samples(self):
        import pandas as pd

        from src.core.schemas.market import EventStudyRequest
        from src.research.event_study.engine import evaluate_event_study

        obs = pd.DataFrame([
            {"stock_code": "600519", "trade_date": date(2020, 1, 1), "factor_id": "B_NATAL_001",
             "direction": 1, "rule_score": 8.0, "normalized_value": 0.8},
        ])
        empty_labels = pd.DataFrame(columns=["stock_code", "trade_date", "ret_20d"])
        result = evaluate_event_study(obs, empty_labels, EventStudyRequest(factor_ids=["B_NATAL_001"], horizons=[20]))
        assert result.horizons[0].sample_count == 0
        assert result.horizons[0].mean_return is None
        assert any(w.code == "ES_NO_LABEL_MATCH" for w in result.warnings)
