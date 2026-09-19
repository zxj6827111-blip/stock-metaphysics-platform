"""P0-3 验收测试：真实组与负对照组的事件集合必须有区分度。

历史教训（docs/methodology.md §7.1）
-----------------------------------
最初的实现里，"命中"只代表"这个因子被计算过"：真实组与对照组的事件集合
完全相同，所有负对照都是 tie —— 看起来干净，实则是方法失效。

本文件直接断言：

    real_event_set != shuffled_birth_event_set
    real_event_set != shifted_plus_7_event_set
    real_event_set != shifted_minus_7_event_set

并报告各集合的 Jaccard 相似度（> 0.9 视为对照失效）。

注意：这里使用合成行情**仅为标签服务** —— 本测试检验的是"事件定义是否有
区分度"这一方法论属性，与行情真伪无关（命盘重算不依赖行情）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.core.schemas.common import VariantMode
from src.core.schemas.market import EventStudyRequest, NegativeControlKind
from src.core.schemas.stock import BirthProfileCreateRequest, StockMaster
from src.core.stock.birth_profile import build_birth_profile
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.huangli.huangli_engine import HuangliEngine
from src.factors.registry.compute import compute_factor_set
from src.research.event_study.engine import extract_event_keys
from src.research.pipeline import ResearchPipeline, month_starts

#: 样本覆盖 两个交易所 / 主板 / 创业板 / 科创板
UNIVERSE_META = {
    "600519": ("贵州茅台", date(2001, 8, 27), "SSE"),
    "000001": ("平安银行", date(1991, 4, 3), "SZSE"),
    "300750": ("宁德时代", date(2018, 6, 11), "SZSE"),
    "688981": ("中芯国际", date(2020, 7, 16), "SSE"),
    "601318": ("中国平安", date(2007, 3, 1), "SSE"),
}

TARGET_FACTORS = ["B_MONTH_003", "B_NATAL_003", "H_DAY_001"]


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


@pytest.fixture(scope="module")
def panels():
    """构建真实组 + 三类出生时间对照组的因子观测面板。"""
    bazi = BaziEngine()
    huangli = HuangliEngine()
    pipeline = ResearchPipeline()

    def birth_profile_provider(code: str, variant: str | None):
        name, listing, exchange = UNIVERSE_META[code]
        stock = StockMaster(
            stock_code=code, name=name, exchange=exchange,
            listing_date=listing, wind_code=f"{code}.{exchange[:2]}",
        )
        return build_birth_profile(stock, BirthProfileCreateRequest())

    def factor_builder(code: str, as_of_date: date, profile):
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 0, 0)
        hl = huangli.snapshot(as_of, days=31)
        chart = bazi.build_chart(
            birth_datetime=profile.birth_datetime.replace(tzinfo=None),
            as_of=as_of,
            variant_mode=VariantMode(profile.variant_mode),
            stock_code=code,
        )
        return compute_factor_set(chart, hl, as_of, stock_code=code).observations

    def label_builder(code: str, as_of_date: date):
        """事件集合测试不需要真实标签；返回最小占位（对齐后被剔除不影响键集合）。

        事件键由观测侧决定；标签只用于 pipeline 的 as_of→trade_date 对齐。
        这里直接用观测日期做近似对齐键。
        """
        from src.core.schemas.market import LabelSet

        return LabelSet(stock_code=code, as_of=as_of_date, trade_date=as_of_date)

    sample_dates = month_starts(date(2019, 1, 1), date(2023, 12, 1), step_months=3)
    out = {}
    for variant, kind in [
        ("real", None),
        ("random_birth_date", NegativeControlKind.RANDOM_BIRTH_DATE),
        ("shift_plus_7d", NegativeControlKind.SHIFT_PLUS_7D),
        ("shift_minus_7d", NegativeControlKind.SHIFT_MINUS_7D),
    ]:
        transform = (
            ResearchPipeline.make_birth_transform(kind) if kind is not None else None
        )
        obs_df, _, _ = pipeline.build_panel(
            stocks=list(UNIVERSE_META),
            sample_dates=sample_dates,
            factor_builder=factor_builder,
            label_builder=label_builder,
            birth_profile_provider=birth_profile_provider,
            birth_transform=transform,
            variant=variant,
        )
        out[variant] = obs_df
    return out


class TestEventSetsAreDistinct:
    """真实组与各对照组的事件集合必须真正不同（区分度的直接证明）。"""

    @pytest.mark.parametrize("factor_id", TARGET_FACTORS)
    def test_real_vs_shifted_birth_event_sets(self, panels, factor_id):
        request = EventStudyRequest(factor_ids=[factor_id], activation="nonzero")
        real = extract_event_keys(panels["real"], request)
        shuffled = extract_event_keys(panels["random_birth_date"], request)
        plus7 = extract_event_keys(panels["shift_plus_7d"], request)
        minus7 = extract_event_keys(panels["shift_minus_7d"], request)

        assert real, f"{factor_id} 真实事件集合为空（activation 过滤后无事件）"

        # 硬性要求：集合必须不相等
        assert real != shuffled, (
            f"{factor_id}: 随机出生日对照的事件集合与真实组完全相同 —— "
            "activation 语义失效，负对照方法失效"
        )
        assert real != plus7, f"{factor_id}: +7 天对照事件集合与真实组完全相同"
        assert real != minus7, f"{factor_id}: -7 天对照事件集合与真实组完全相同"

        # 区分度量化：Jaccard 相似度不得接近 1
        for label, ctrl in (("random", shuffled), ("+7d", plus7), ("-7d", minus7)):
            j = _jaccard(real, ctrl)
            assert j < 0.95, (
                f"{factor_id} {label} 对照与真实事件集合 Jaccard={j:.3f} ≥ 0.95，"
                "区分度不足，对照近乎失效"
            )

    def test_event_keys_are_dated(self, panels):
        """事件键必须携带具体日期，而非只有股票维度。"""
        request = EventStudyRequest(factor_ids=["B_MONTH_003"], activation="nonzero")
        real = extract_event_keys(panels["real"], request)
        assert real
        for code, td in real:
            assert isinstance(code, str) and code
            assert td is not None, "事件键缺少日期维度"

    def test_b_month_003_event_timestamps_actually_move(self, panels):
        """+7 天以后，B_MONTH_003 的事件时间戳必须真实变化（按股票逐个核对）。

        注意：跨股票聚合的日期集合可能掩盖变化（同一日期可被其他股票激活），
        因此必须比较每只股票的日期集合，而非全局日期并集。
        """
        request = EventStudyRequest(factor_ids=["B_MONTH_003"], activation="nonzero")

        def per_stock(keys: set) -> dict[str, set]:
            out: dict[str, set] = {}
            for code, td in keys:
                out.setdefault(code, set()).add(td)
            return out

        real = per_stock(extract_event_keys(panels["real"], request))
        plus7 = per_stock(extract_event_keys(panels["shift_plus_7d"], request))
        minus7 = per_stock(extract_event_keys(panels["shift_minus_7d"], request))

        moved_plus = [c for c in UNIVERSE_META if real.get(c, set()) != plus7.get(c, set())]
        moved_minus = [c for c in UNIVERSE_META if real.get(c, set()) != minus7.get(c, set())]
        assert moved_plus, "B_MONTH_003：+7 天后所有股票的事件日期集合均未变化"
        assert moved_minus, "B_MONTH_003：-7 天后所有股票的事件日期集合均未变化"


class TestActivationStats:
    """activation_rate 统计必须存在且能识别低区分度因子。"""

    def test_activation_stats_present(self, panels):
        from src.research.event_study.engine import compute_activation_stats

        request = EventStudyRequest(factor_ids=TARGET_FACTORS, activation="nonzero")
        stats, _warnings = compute_activation_stats(panels["real"], request)
        for fid in TARGET_FACTORS:
            assert fid in stats
            assert 0.0 <= stats[fid]["activation_rate"] <= 1.0
            assert stats[fid]["total"] > 0

    def test_constant_factor_flagged_low_discrimination(self):
        """几乎恒激活的因子必须触发 LOW_DISCRIMINATION_FACTOR。"""
        import pandas as pd

        from src.research.event_study.engine import compute_activation_stats

        base = date(2024, 1, 1)
        obs = pd.DataFrame([
            {"stock_code": "600519",
             "trade_date": base + timedelta(days=i),
             "factor_id": "FAKE_HOT", "direction": 1, "rule_score": 8.0,
             "normalized_value": 1.0}
            for i in range(200)
        ])
        stats, warnings = compute_activation_stats(
            obs, EventStudyRequest(factor_ids=["FAKE_HOT"], activation="nonzero")
        )
        assert stats["FAKE_HOT"]["activation_rate"] == 1.0
        assert any(w.code == "LOW_DISCRIMINATION_FACTOR" for w in warnings)

    def test_nearly_silent_factor_flagged(self):
        import pandas as pd

        from src.research.event_study.engine import compute_activation_stats

        base = date(2024, 1, 1)
        obs = pd.DataFrame([
            {"stock_code": "600519",
             "trade_date": base + timedelta(days=i),
             "factor_id": "FAKE_COLD", "direction": 0, "rule_score": 0.1 * i,
             "normalized_value": 0.0 if i else 1.0}
            for i in range(300)
        ])
        stats, warnings = compute_activation_stats(
            obs, EventStudyRequest(factor_ids=["FAKE_COLD"], activation="nonzero")
        )
        assert stats["FAKE_COLD"]["activation_rate"] < 0.005
        assert any(w.code == "LOW_DISCRIMINATION_FACTOR" for w in warnings)
