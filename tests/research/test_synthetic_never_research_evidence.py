"""P0-1 验收测试：合成/降级行情绝不能被包装成研究证据。

验收要求（原文）
----------------
只要 ``is_degraded = true`` 或 ``data_source = synthetic``：

* 任何结果不得被标记为 empirical_validated / historically_validated /
  statistically_supported；
* 必须明确输出 ``RESEARCH_DATA_UNAVAILABLE`` 或等价状态；
* 状态机唯一允许的状态是 ``NO_REAL_DATA``；
* 若违反 → P0 BUG。

本文件同时测试"反向对照"：真实数据路径必须**能**走到更高状态，
否则门禁形同虚设（把一切都打成 NO_REAL_DATA 的懦夫实现不算通过）。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.core.schemas.market import EventStudyRequest
from src.research.status import ResearchStatus, assess_research_status


def _toy_real_result():
    """样本充足、时间覆盖合理的事件研究结果。"""
    from src.research.event_study.engine import evaluate_event_study

    obs = pd.DataFrame([
        {"stock_code": f"{600000 + i:06d}", "trade_date": date(2020, 1, 2) if i % 2
         else date(2020, 1, 3), "factor_id": "B_MONTH_001",
         "direction": 1, "rule_score": 8.0, "normalized_value": 1.0}
        for i in range(60)
    ])
    labels = pd.DataFrame([
        {"stock_code": f"{600000 + i:06d}", "trade_date": date(2020, 1, 2) if i % 2
         else date(2020, 1, 3),
         "ret_5d": 0.01, "ret_10d": 0.015, "ret_20d": 0.02 - (i % 5) * 0.01,
         "ret_60d": 0.04, "excess_return_20d": 0.01 - (i % 3) * 0.01,
         "max_drawdown_20d": -0.05, "max_return_20d": 0.08}
        for i in range(60)
    ])
    return evaluate_event_study(
        obs, labels, EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[5, 20])
    )


class TestSyntheticNeverProducesEvidence:
    def test_synthetic_panel_forces_no_real_data(self):
        result = _toy_real_result()
        assessment = assess_research_status(result, None, data_is_real=False)
        assert assessment.status == ResearchStatus.NO_REAL_DATA
        assert assessment.data_is_real is False
        assert any("不构成" in r or "联调" in r for r in assessment.reasons)

    def test_degraded_benchmark_also_blocks(self):
        result = _toy_real_result()
        assessment = assess_research_status(
            result, None, data_is_real=False,
            data_problems=["benchmark:000300 degraded"],
        )
        assert assessment.status == ResearchStatus.NO_REAL_DATA

    def test_status_machine_never_emits_out_of_sample(self):
        """Phase 1 的状态机绝不允许产出 SUPPORTED_OUT_OF_SAMPLE。"""
        from src.research.validation.negative_controls import summarize_controls

        result = _toy_real_result()
        # 构造一个"完美"的负对照报告（全部 outperform）
        from src.core.schemas.market import NegativeControlKind, NegativeControlResult

        controls = [
            NegativeControlResult(
                kind=k, verdict="outperform",
                real_mean_return_20d=0.03, control_mean_return_20d=0.005,
                jaccard_with_real=0.2,
            )
            for k in NegativeControlKind
        ]
        report = summarize_controls("EXP-X", ["B_MONTH_001"], controls)
        assessment = assess_research_status(result, report, data_is_real=True)
        assert assessment.status != ResearchStatus.SUPPORTED_OUT_OF_SAMPLE

    def test_real_data_can_advance_beyond_no_real_data(self):
        """反向对照：真实数据路径不被门禁误伤。"""
        result = _toy_real_result()
        assessment = assess_research_status(result, None, data_is_real=True)
        # 没有负对照时最多 INCONCLUSIVE；绝不能被误判为 NO_REAL_DATA
        assert assessment.status == ResearchStatus.INCONCLUSIVE
        assert assessment.data_is_real is True


class TestNoSignalHonesty:
    def test_underperform_yields_no_signal(self):
        from src.core.schemas.market import NegativeControlKind, NegativeControlResult
        from src.research.validation.negative_controls import summarize_controls

        result = _toy_real_result()
        controls = [
            NegativeControlResult(
                kind=k, verdict=v,
                real_mean_return_20d=0.01, control_mean_return_20d=0.02,
                real_up_rate_20d=0.5, control_up_rate_20d=0.6,
                jaccard_with_real=0.3,
            )
            for k, v in zip(NegativeControlKind,
                            ("underperform", "tie", "tie", "underperform"), strict=True)
        ]
        report = summarize_controls("EXP-X", ["B_MONTH_001"], controls)
        assessment = assess_research_status(result, report, data_is_real=True)
        assert assessment.status == ResearchStatus.NO_SIGNAL

    def test_control_overlap_flags_independence(self):
        """Jaccard > 0.9 的对照必须触发 NEGATIVE_CONTROL_NOT_INDEPENDENT + INVALID_CONTROL。"""
        from src.research.validation.negative_controls import random_birth_date_control

        # 构造真实/对照完全相同的面板（模拟历史上"事件集合完全相同"的失效场景）
        events = [
            {"stock_code": f"{600519 - i:06d}", "trade_date": date(2020, 1, 2),
             "factor_id": "B_MONTH_001", "direction": 1, "rule_score": 8.0,
             "normalized_value": 1.0, "availability": "ok"}
            for i in range(40)
        ]
        obs = pd.DataFrame(events)
        labels = pd.DataFrame([
            {"stock_code": f"{600519 - i:06d}", "trade_date": date(2020, 1, 2),
             "ret_20d": 0.01, "ret_5d": 0.01, "ret_10d": 0.02, "ret_60d": 0.03}
            for i in range(40)
        ])
        req = EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20])

        from src.research.event_study.engine import extract_event_keys

        real_keys = extract_event_keys(obs, req)
        from src.research.event_study.engine import evaluate_event_study

        real = evaluate_event_study(obs, labels, req)
        real_stats = next(h for h in real.horizons if h.horizon == 20)

        result = random_birth_date_control(obs, labels, req, real_stats=real_stats,
                                           real_keys=real_keys)
        assert result.jaccard_with_real == pytest.approx(1.0)
        assert any(w.code == "NEGATIVE_CONTROL_NOT_INDEPENDENT" for w in result.warnings)

        from src.research.validation.negative_controls import summarize_controls

        report = summarize_controls(real.experiment_id, req.factor_ids, [result])
        assessment = assess_research_status(real, report, data_is_real=True)
        assert assessment.status == ResearchStatus.INVALID_CONTROL


class TestNegativeControlDiagnosticsFields:
    """负对照输出必须携带事件集合诊断（不能只说 tie，要告诉研究者为什么）。"""

    def test_diagnostics_present(self):
        from src.core.schemas.market import NegativeControlKind
        from src.research.event_study.engine import extract_event_keys
        from src.research.validation.negative_controls import shift_birth_date_control

        obs = pd.DataFrame([
            {"stock_code": f"{600519 - i:06d}", "trade_date": date(2020, 1, 2) if i % 2
             else date(2020, 1, 3),
             "factor_id": "B_MONTH_001", "direction": 1 if i % 3 else -1,
             "rule_score": 5.0, "normalized_value": float((i % 3) - 1), "availability": "ok"}
            for i in range(60)
        ])
        labels = pd.DataFrame([
            {"stock_code": f"{600519 - i:06d}", "trade_date": date(2020, 1, 2) if i % 2
             else date(2020, 1, 3),
             "ret_20d": 0.01 * (i % 5), "ret_5d": 0.005, "ret_10d": 0.008, "ret_60d": 0.02}
            for i in range(60)
        ])
        req = EventStudyRequest(factor_ids=["B_MONTH_001"], horizons=[20])
        from src.research.event_study.engine import evaluate_event_study

        real = evaluate_event_study(obs, labels, req)
        real_stats = next(h for h in real.horizons if h.horizon == 20)
        real_keys = extract_event_keys(obs, req)

        # 改变对照组的激活模式（模拟重排盘后的对照观测）
        control_obs = obs.copy()
        control_obs["normalized_value"] = control_obs["normalized_value"].shift(1).fillna(0.0)

        result = shift_birth_date_control(
            NegativeControlKind.SHIFT_PLUS_7D, control_obs, labels, req,
            real_stats=real_stats, days=7, real_keys=real_keys,
        )
        assert result.event_count is not None
        assert result.real_event_count == len(real_keys)
        assert result.overlap_with_real is not None
        assert result.jaccard_with_real is not None and 0.0 <= result.jaccard_with_real <= 1.0
