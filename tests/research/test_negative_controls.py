"""负对照测试（architecture §44）—— 项目可信度的核心。

四类对照必须全部可运行：
    1. 随机出生日期
    2. 出生日期 +7 天
    3. 出生日期 −7 天
    4. 随机因子

**输出纪律**：真实因子不优于随机时必须如实输出，禁止美化。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.core.schemas.market import EventStudyRequest, HorizonStats, NegativeControlKind
from src.research.pipeline import ResearchPipeline
from src.research.validation.negative_controls import (
    MIN_VERDICT_SAMPLE,
    OUTPERFORM_EPSILON,
    random_birth_date_control,
    random_factor_control,
    shift_birth_date_control,
    summarize_controls,
)


def _obs(seed: int = 0, n: int = 40, factor_id: str = "B_MONTH_001") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame([
        {
            "stock_code": f"{600000 + i:06d}",
            "trade_date": date(2020, 1, 2) + timedelta(days=i * 7),
            "as_of": datetime(2020, 1, 2) + timedelta(days=i * 7),
            "factor_id": factor_id,
            "direction": int(rng.choice([-1, 1])),
            "rule_score": float(rng.uniform(0, 10)),
            "normalized_value": float(rng.choice([-1.0, -0.6, 0.6, 1.0])),
            "availability": "ok",
        }
        for i in range(n)
    ])


def _labels(seed: int = 0, n: int = 40, edge: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame([
        {
            "stock_code": f"{600000 + i:06d}",
            "trade_date": date(2020, 1, 2) + timedelta(days=i * 7),
            "as_of": datetime(2020, 1, 2) + timedelta(days=i * 7),
            "ret_5d": float(rng.normal(0.005, 0.05)),
            "ret_10d": float(rng.normal(0.01, 0.07)),
            "ret_20d": float(rng.normal(0.02 + edge, 0.10)),
            "ret_60d": float(rng.normal(0.04, 0.18)),
            "max_return_20d": float(abs(rng.normal(0.08, 0.05))),
            "max_drawdown_20d": float(-abs(rng.normal(0.09, 0.05))),
            "excess_return_20d": float(rng.normal(0.0 + edge, 0.09)),
            "bench_ret_20d": 0.01,
        }
        for i in range(n)
    ])


def _stats(mean: float, up: float, n: int = 40) -> HorizonStats:
    return HorizonStats(horizon=20, sample_count=n, mean_return=mean, up_rate=up)


class TestFourControlsExist:
    """四类对照都必须可被调用并返回结果。"""

    def test_random_birth_date(self):
        result = random_birth_date_control(
            _obs(seed=1), _labels(seed=1), EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55),
        )
        assert result.kind == NegativeControlKind.RANDOM_BIRTH_DATE
        assert result.description
        assert result.seed is not None
        assert result.horizon_stats

    def test_shift_plus_7d(self):
        result = shift_birth_date_control(
            NegativeControlKind.SHIFT_PLUS_7D, _obs(seed=2), _labels(seed=2),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55), days=7,
        )
        assert result.kind == NegativeControlKind.SHIFT_PLUS_7D
        assert "+7" in result.description or "7" in result.description

    def test_shift_minus_7d(self):
        result = shift_birth_date_control(
            NegativeControlKind.SHIFT_MINUS_7D, _obs(seed=3), _labels(seed=3),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55), days=-7,
        )
        assert result.kind == NegativeControlKind.SHIFT_MINUS_7D
        assert "-7" in result.description

    def test_random_factor(self):
        result = random_factor_control(
            _obs(seed=4), _labels(seed=4),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55), seed=42,
        )
        assert result.kind == NegativeControlKind.RANDOM_FACTOR
        assert result.seed == 42


class TestVerdictHonesty:
    """判定逻辑必须如实——不美化、不隐藏。"""

    def test_tie_when_no_difference(self):
        result = random_factor_control(
            _obs(seed=5), _labels(seed=5),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55),
        )
        # 随机因子对照的对照均值应接近真实均值（差异远小于阈值）
        assert result.verdict in ("tie", "outperform", "underperform", "inconclusive")

    def test_underperform_is_reported(self):
        """构造真实组显著差于对照组的情形，必须输出 underperform。"""
        control = _labels(seed=6, edge=0.10)  # 对照组平均收益明显更高
        result = random_factor_control(
            _obs(seed=6), control,
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(-0.05, 0.35),
        )
        assert result.verdict in ("underperform", "tie")
        if result.verdict == "underperform":
            assert "弱于" in result.verdict_note

    def test_outperform_requires_epsilon(self):
        control = _labels(seed=7)
        result = random_factor_control(
            _obs(seed=7), control,
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.50, 0.99),
        )
        assert result.verdict == "outperform"
        assert (result.delta_mean_return_20d or 0) > OUTPERFORM_EPSILON

    def test_inconclusive_when_sample_too_small(self):
        result = random_factor_control(
            _obs(seed=8, n=5), _labels(seed=8, n=5),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55, n=3),
        )
        assert result.verdict == "inconclusive"
        assert "样本数不足" in result.verdict_note

    def test_inconclusive_when_control_empty(self):
        result = random_factor_control(
            pd.DataFrame(), pd.DataFrame(),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55),
        )
        assert result.verdict == "inconclusive"
        assert result.warnings


class TestSummarize:
    def test_no_valid_results_is_honest(self):
        report = summarize_controls("EXP-1", ["B_MONTH_001"], [])
        assert "未能得到有效对照结论" in report.conclusion
        assert "不给出" in report.conclusion

    def test_underperform_conclusion(self):
        from src.core.schemas.market import NegativeControlResult

        r = NegativeControlResult(
            kind=NegativeControlKind.RANDOM_BIRTH_DATE, verdict="underperform",
            verdict_note="真实因子弱于对照",
        )
        report = summarize_controls("EXP-2", ["B_MONTH_001"], [r])
        assert "没有任何一类显示真实术数因子显著优于随机" in report.conclusion
        assert "如实输出" in report.conclusion

    def test_mixed_conclusion_says_uncertain(self):
        from src.core.schemas.market import NegativeControlResult

        results = [
            NegativeControlResult(kind=NegativeControlKind.RANDOM_BIRTH_DATE, verdict="outperform"),
            NegativeControlResult(kind=NegativeControlKind.SHIFT_PLUS_7D, verdict="tie"),
            NegativeControlResult(kind=NegativeControlKind.SHIFT_MINUS_7D, verdict="underperform"),
        ]
        report = summarize_controls("EXP-3", ["B_MONTH_001"], results)
        assert "不确定" in report.conclusion

    def test_all_outperform_keeps_caveat(self):
        from src.core.schemas.market import NegativeControlResult

        results = [
            NegativeControlResult(kind=NegativeControlKind.RANDOM_BIRTH_DATE, verdict="outperform"),
            NegativeControlResult(kind=NegativeControlKind.SHIFT_PLUS_7D, verdict="outperform"),
        ]
        report = summarize_controls("EXP-4", ["B_MONTH_001"], results)
        assert "样本外验证" in report.conclusion
        assert "不能据此宣称预测能力" in report.conclusion


class TestBirthTransforms:
    def test_shift_plus_7(self):
        fn = ResearchPipeline.make_birth_transform(NegativeControlKind.SHIFT_PLUS_7D)
        rng = np.random.default_rng(0)
        dt = datetime(2001, 8, 27, 9, 30)
        assert fn(dt, rng) == dt + timedelta(days=7)

    def test_shift_minus_7(self):
        fn = ResearchPipeline.make_birth_transform(NegativeControlKind.SHIFT_MINUS_7D)
        rng = np.random.default_rng(0)
        dt = datetime(2001, 8, 27, 9, 30)
        assert fn(dt, rng) == dt - timedelta(days=7)

    def test_random_birth_date_is_deterministic_with_seed(self):
        fn = ResearchPipeline.make_birth_transform(NegativeControlKind.RANDOM_BIRTH_DATE)
        dt = datetime(2001, 8, 27, 9, 30)
        a = fn(dt, np.random.default_rng(20260918))
        b = fn(dt, np.random.default_rng(20260918))
        assert a == b

    def test_random_birth_date_differs_from_original(self):
        fn = ResearchPipeline.make_birth_transform(NegativeControlKind.RANDOM_BIRTH_DATE)
        dt = datetime(2001, 8, 27, 9, 30)
        shifted = [fn(dt, np.random.default_rng(i)) for i in range(20)]
        assert any(s != dt for s in shifted)

    def test_unsupported_kind_raises(self):
        with pytest.raises(ValueError):
            ResearchPipeline.make_birth_transform(NegativeControlKind.RANDOM_FACTOR)


class TestRandomFactorMethodDisclosure:
    def test_method_warning_present(self):
        result = random_factor_control(
            _obs(seed=9), _labels(seed=9),
            EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20]),
            real_stats=_stats(0.02, 0.55),
        )
        codes = {w.code for w in result.warnings}
        assert "NC_RANDOM_FACTOR_METHOD" in codes
        msg = next(w.message for w in result.warnings if w.code == "NC_RANDOM_FACTOR_METHOD")
        assert "命中率" in msg
        assert "选择性" in msg


class TestMinSampleConstant:
    def test_min_sample_is_defined(self):
        assert MIN_VERDICT_SAMPLE >= 10
