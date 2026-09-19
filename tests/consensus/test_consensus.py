"""ConsensusEngine / ConflictDetector / 共振研究测试（Phase 2C）。

本文件的**核心断言**是三条纪律：

1. **禁止简单平均**：80/20/50 必须判为 MIXED 并保留三个方向，
   而不是被平均成"整体一般"。
2. **共识 ≠ 历史有效**：高共识 + `NO_SIGNAL` 时，解读文案必须同时说明两件事。
3. **共振必须有负对照**：且负对照失效（Jaccard 过高）时必须显式抛出 INVALID_CONTROL。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.core.orchestration.consensus import (
    ConflictDetector,
    ConsensusEngine,
    build_consensus_and_conflict,
)
from src.core.schemas.analysis import MetaphysicsOpinion, ReasonItem
from src.core.schemas.common import Availability, ConsensusLabel, EngineId
from src.core.schemas.consensus import (
    ALL_COMBO_IDS,
    CONFLICT_COMBO_SPECS,
    CONSENSUS_COMBO_SPECS,
    ConsensusResearchRequest,
)
from src.core.schemas.factor import FactorObservation, FactorSet
from src.research.consensus_research import (
    build_consensus_panel,
    build_multiple_testing_warning,
    combo_description,
    combo_mask,
    evaluate_combo,
    run_consensus_research,
)


@pytest.fixture(autouse=True)
def _restore_definition_index():
    """`_obs` 会向全局 DEFINITION_INDEX 注入测试专用因子 —— 用完必须还原，
    否则会污染因子字典与其他测试（本项目对全局状态很敏感）。"""
    from src.factors.registry.definitions import DEFINITION_INDEX

    snapshot = dict(DEFINITION_INDEX)
    yield
    DEFINITION_INDEX.clear()
    DEFINITION_INDEX.update(snapshot)


def opinion(engine: str, direction: int, score: float, conf: float = 0.6,
            reasons: tuple[tuple[str, int], ...] = ()) -> MetaphysicsOpinion:
    """构造一个观点；理由按方向放进 positive/negative。"""
    pos = [ReasonItem(text=t, factor_ids=[f]) for t, f in reasons if direction > 0]
    neg = [ReasonItem(text=t, factor_ids=[f]) for t, f in reasons if direction < 0]
    return MetaphysicsOpinion(
        engine=EngineId(engine), engine_version="v-test",
        availability=Availability.OK, direction=direction,
        score=score, confidence=conf,
        top_positive_reasons=pos, top_negative_reasons=neg,
        factor_ids=[f for _t, f in reasons],
        assumptions=["测试假设"],
    )


def unavailable(engine: str) -> MetaphysicsOpinion:
    return MetaphysicsOpinion(
        engine=EngineId(engine), availability=Availability.UNAVAILABLE,
        direction=0, score=None, confidence=0.0, note="测试：故意不可用",
    )


# ---------------------------------------------------------------------------
# 1. ConsensusEngine
# ---------------------------------------------------------------------------


class TestConsensusEngine:
    engine = ConsensusEngine()

    def test_three_way_agreement_is_positive_consensus(self):
        r = self.engine.compute({
            "bazi": opinion("bazi", 1, 62),
            "ziwei": opinion("ziwei", 1, 60),
            "huangli": opinion("huangli", 1, 61),
        })
        assert r.consensus_class == ConsensusLabel.POSITIVE_CONSENSUS
        assert r.agreement_score == 1.0
        assert r.available_engine_count == 3
        assert r.positive_engine_count == 3

    def test_strong_positive_requires_high_score_and_confidence(self):
        strong = self.engine.compute({
            "bazi": opinion("bazi", 1, 80, 0.8),
            "ziwei": opinion("ziwei", 1, 78, 0.75),
        })
        assert strong.consensus_class == ConsensusLabel.STRONG_POSITIVE_CONSENSUS
        weak_conf = self.engine.compute({
            "bazi": opinion("bazi", 1, 80, 0.3),
            "ziwei": opinion("ziwei", 1, 78, 0.3),
        })
        assert weak_conf.consensus_class == ConsensusLabel.POSITIVE_CONSENSUS

    def test_all_negative_is_negative_consensus(self):
        plain = self.engine.compute({
            "bazi": opinion("bazi", -1, 44, conf=0.4),
            "ziwei": opinion("ziwei", -1, 45, conf=0.4),
        })
        assert plain.consensus_class == ConsensusLabel.NEGATIVE_CONSENSUS
        assert plain.negative_engine_count == 2

        strong = self.engine.compute({
            "bazi": opinion("bazi", -1, 30, conf=0.8),
            "ziwei": opinion("ziwei", -1, 28, conf=0.8),
        })
        assert strong.consensus_class == ConsensusLabel.STRONG_NEGATIVE_CONSENSUS

    def test_never_averages_away_conflict(self):
        """**最关键的一条**：80 / 20 / 50 必须判为 MIXED。

        平均值 50 会让人以为"整体中性"，从而错过"八字强、紫微弱"这一信息。
        """
        r = self.engine.compute({
            "bazi": opinion("bazi", 1, 80),
            "ziwei": opinion("ziwei", -1, 20),
            "huangli": opinion("huangli", 0, 50),
        })
        assert r.consensus_class == ConsensusLabel.MIXED
        assert r.directions == {"bazi": 1, "ziwei": -1, "huangli": 0}
        assert r.positive_engine_count == 1
        assert r.negative_engine_count == 1
        assert r.neutral_engine_count == 1
        assert "MIXED" in str(r.consensus_class)
        # 方向信息必须完整保留，不能被压缩成一个数
        assert set(r.directions.values()) == {1, -1, 0}

    def test_agreement_score_is_not_score_average(self):
        r = self.engine.compute({
            "bazi": opinion("bazi", 1, 95),
            "ziwei": opinion("ziwei", 1, 55),
            "huangli": opinion("huangli", 1, 40),
        })
        # 分数平均 63.3，但方向一致度是 1.0 —— 两者是不同概念
        assert r.agreement_score == 1.0

    def test_unavailable_engine_not_counted_in_denominator(self):
        r = self.engine.compute({
            "bazi": opinion("bazi", 1, 60),
            "huangli": opinion("huangli", 1, 60),
            "ziwei": unavailable("ziwei"),
        })
        assert r.available_engine_count == 2
        assert r.unavailable_engines == ["ziwei"]
        assert "ziwei" not in r.directions

    def test_no_available_engine_is_not_zero_score(self):
        r = self.engine.compute({
            "bazi": unavailable("bazi"),
            "ziwei": unavailable("ziwei"),
        })
        assert r.available_engine_count == 0
        assert r.label_cn == "不可评估"
        assert "0 分" in r.interpretation or "不会用 0 分" in r.interpretation
        assert r.directions == {}

    def test_single_engine_cannot_claim_consensus(self):
        r = self.engine.compute({"bazi": opinion("bazi", 1, 80)})
        assert "单引擎" in r.label_cn
        assert any("单一引擎" in n for n in r.notes)

    # --- 共识 ≠ 历史有效 ---

    @pytest.mark.parametrize("status,needle", [
        ("NOT_RUN", "历史统计未运行"),
        ("NO_SIGNAL", "历史统计未发现稳定信号"),
        ("NO_REAL_DATA", "合成或降级"),
        ("INVALID_CONTROL", "负对照失效"),
        ("INSUFFICIENT_SAMPLE", "样本不足"),
        ("INCONCLUSIVE", "历史证据不足"),
        ("SUPPORTED_IN_SAMPLE", "样本内"),
    ])
    def test_interpretation_always_states_research_status(self, status, needle):
        """无论共识多高，解读都必须同时说明历史统计状态。"""
        r = self.engine.compute(
            {"bazi": opinion("bazi", 1, 90), "ziwei": opinion("ziwei", 1, 88)},
            research_status=status,
        )
        assert needle in r.interpretation, r.interpretation

    def test_high_consensus_with_no_signal_says_so_explicitly(self):
        r = self.engine.compute(
            {"bazi": opinion("bazi", 1, 90), "ziwei": opinion("ziwei", 1, 88),
             "huangli": opinion("huangli", 1, 85)},
            research_status="NO_SIGNAL",
        )
        assert r.consensus_class == ConsensusLabel.STRONG_POSITIVE_CONSENSUS
        assert "术数共识高，但历史统计未发现稳定信号" in r.interpretation
        assert "不代表上涨概率较高" in r.interpretation

    def test_engine_opinions_include_required_contract_fields(self):
        r = self.engine.compute({"bazi": opinion("bazi", 1, 70, reasons=(("理由", "B_NATAL_001"),))})
        payload = r.engine_opinions["bazi"]
        for key in ("engine", "direction", "score", "confidence", "factor_ids",
                    "positive_reasons", "negative_reasons", "research_status",
                    "historical_validity", "data_quality", "assumptions"):
            assert key in payload, key

    def test_notes_explain_agreement_semantics(self):
        r = self.engine.compute({"bazi": opinion("bazi", 1, 70)})
        assert any("方向一致度" in n for n in r.notes)
        assert any("不是各引擎分数的平均" in n for n in r.notes)


# ---------------------------------------------------------------------------
# 2. ConflictDetector
# ---------------------------------------------------------------------------


class TestConflictDetector:
    detector = ConflictDetector()

    def test_opposing_directions_are_major_conflict_with_reasons(self):
        r = self.detector.detect({
            "bazi": opinion("bazi", 1, 80, reasons=(("日主偏强", "B_NATAL_001"),)),
            "ziwei": opinion("ziwei", -1, 25, reasons=(("命宫落陷", "Z_LIFE_001"),)),
            "huangli": opinion("huangli", 0, 50),
        })
        assert r.has_conflict is True
        assert r.conflict_level in ("minor", "major")
        assert set(r.conflicting_engines) >= {"bazi", "ziwei"}
        assert r.major_conflicts, "必须给出冲突明细"
        for c in r.major_conflicts:
            assert c["engine"] and c["direction_label"]
            assert c["reasons"], "每条冲突都必须有可读原因"
        assert any("方向对立" in x for x in r.reasons)
        assert any("不会" in x and "平均" in x for x in r.reasons)

    def test_no_conflict_when_all_agree(self):
        r = self.detector.detect({
            "bazi": opinion("bazi", 1, 70),
            "ziwei": opinion("ziwei", 1, 65),
        })
        assert r.has_conflict is False
        assert r.conflict_level == "none"

    def test_neutral_engine_is_minor_not_major(self):
        r = self.detector.detect({
            "bazi": opinion("bazi", 1, 70),
            "ziwei": opinion("ziwei", 0, 50),
        })
        assert r.has_conflict is True
        assert r.conflict_level == "minor"
        assert r.severity == "minor"

    def test_assumption_conflict_detected_when_engines_share_variant_assumption(self):
        a = opinion("bazi", 1, 70).model_copy(
            update={"assumptions": ["运限方向 variant 在 not_applicable 下不输出大运。"]})
        b = opinion("ziwei", 1, 70).model_copy(
            update={"assumptions": ["股票无真实性别：紫微运限以方向 variant 表达。"]})
        r = self.detector.detect({"bazi": a, "ziwei": b})
        assert r.assumption_conflicts
        assert any("运限方向假设" in c["description"] for c in r.assumption_conflicts)

    def test_factor_conflicts_across_engines_only(self):
        """跨引擎同 tag 反向因子要被识别；同引擎内部不算『模型分歧』。"""
        obs = [
            _obs("T_BAZI_001", EngineId.BAZI, direction=1, normalized=0.8, tags=["测试主题"]),
            _obs("T_ZIWEI_001", EngineId.ZIWEI, direction=-1, normalized=-0.6, tags=["测试主题"]),
            # 同引擎内部的第二个因子（不应产生 conflict pair）
            _obs("T_BAZI_002", EngineId.BAZI, direction=-1, normalized=-0.5, tags=["测试主题"]),
        ]
        fset = FactorSet(stock_code="X", as_of=_AS_OF, observations=obs)
        r = self.detector.detect(
            {"bazi": opinion("bazi", 1, 70), "ziwei": opinion("ziwei", -1, 30)},
            factor_set=fset,
        )
        pairs = {(c["engine_a"], c["engine_b"]) for c in r.factor_conflicts}
        assert ("bazi", "ziwei") in pairs
        assert all(a != b for a, b in pairs)

    def test_time_horizon_conflict_within_engine(self):
        obs = [
            _obs("T_NATAL_001", EngineId.BAZI, 1, 0.8, category="natal", tags=["测试主题"]),
            _obs("T_DAY_001", EngineId.BAZI, -1, -0.8, category="day", tags=["测试主题"]),
        ]
        fset = FactorSet(stock_code="X", as_of=_AS_OF, observations=obs)
        r = self.detector.detect({"bazi": opinion("bazi", 1, 70)}, factor_set=fset)
        assert r.time_horizon_conflicts, "长/短周期方向相反必须被识别"
        assert r.time_horizon_conflicts[0]["engine"] == "bazi"

    def test_historical_conflict_stats_defaults_to_not_run(self):
        r = self.detector.detect({"bazi": opinion("bazi", 1, 70)})
        assert r.historical_conflict_stats == {"status": "NOT_RUN"}
        assert any("NOT_RUN" in n for n in r.notes)


# ---------------------------------------------------------------------------
# 3. 组合定义与掩码
# ---------------------------------------------------------------------------


class TestComboDefinitions:
    def test_all_combos_are_predefined(self):
        assert len(ALL_COMBO_IDS) == 11
        assert "ALL_THREE_POS" in ALL_COMBO_IDS
        assert "BAZI_POS_ZIWEI_NEG" in ALL_COMBO_IDS

    def test_conflict_combos_have_pos_and_neg_engines(self):
        for combo_id, (pos, neg) in CONFLICT_COMBO_SPECS.items():
            assert pos and neg, combo_id
            assert not set(pos) & set(neg), f"{combo_id} 的正负引擎不能重叠"

    def test_consensus_combos_require_only_positives(self):
        for engines in CONSENSUS_COMBO_SPECS.values():
            assert engines

    def test_combo_description_is_readable(self):
        engines, desc = combo_description("ALL_THREE_POS")
        assert set(engines) == {"bazi", "ziwei", "huangli"}
        assert "同向共振" in desc
        _e, cdesc = combo_description("BAZI_POS_ZIWEI_NEG")
        assert "冲突组合" in cdesc

    def test_mask_requires_positives_for_consensus(self):
        dirs = pd.DataFrame({
            "bazi": [1, 1, 1, 0, -1],
            "ziwei": [1, 0, 1, 1, 1],
        })
        mask = combo_mask(dirs, "BAZI_ZIWEI_POS")
        assert mask.tolist() == [True, False, True, False, False]

    def test_mask_requires_opposition_for_conflict(self):
        dirs = pd.DataFrame({
            "bazi": [1, 1, 1, -1],
            "ziwei": [-1, 0, 1, 1],
        })
        mask = combo_mask(dirs, "BAZI_POS_ZIWEI_NEG")
        assert mask.tolist() == [True, False, False, False]

    def test_mask_requires_positive_for_negative_side(self):
        """``BAZI_NEG_ZIWEI_POS`` 要求八字为负、紫微为正。"""
        dirs = pd.DataFrame({"bazi": [-1, 1, -1], "ziwei": [1, 1, -1]})
        assert combo_mask(dirs, "BAZI_NEG_ZIWEI_POS").tolist() == [True, False, False]


# ---------------------------------------------------------------------------
# 4. 共振研究 + 负对照 + 多重比较
# ---------------------------------------------------------------------------


def _panel(seed: int = 0, n: int = 300, edge: float | None = None):
    """构造合成面板（**(stock_code, as_of) 严格唯一** 的网格）。

    ``edge`` 不为 None 时，令「bazi 与 ziwei 同时为正」的样本额外获得 edge 收益 ——
    用于验证"真有效"能被检出（而纯随机不会）。

    注意：样本量必须由**网格规模**决定。早期版本用 ``i % len(stocks)`` 造键，
    去重后实际只剩几十行，导致功效检验永远失败 —— 这类"看起来有 300 行、
    实际只有 30 行"的错位是本项目最需要警惕的一类问题。
    """
    rng = np.random.default_rng(seed)
    stocks = [f"S{i:03d}" for i in range(40)]
    dates = [f"{y}-{m:02d}" for y in range(2018, 2026) for m in range(1, 13)]
    grid = [(c, d) for c in stocks for d in dates]
    if n < len(grid):
        idx = rng.choice(len(grid), size=n, replace=False)
        grid = [grid[i] for i in sorted(idx)]

    rows = []
    for code, as_of in grid:
        b = int(rng.integers(-1, 2))
        z = int(rng.integers(-1, 2))
        h = int(rng.integers(-1, 2))
        ret = float(rng.normal(0.0, 0.1))
        if edge is not None and b > 0 and z > 0:
            ret += edge
        rows.append({
            "stock_code": code, "as_of": as_of,
            "ret_20d": ret, "excess_return_20d": ret,
            "bazi": b, "ziwei": z, "huangli": h,
        })
    df = pd.DataFrame(rows)
    assert not df.duplicated(subset=["stock_code", "as_of"]).any(), "网格键必须唯一"
    panel = df[["stock_code", "as_of", "ret_20d", "excess_return_20d"]]
    dirs = df[["stock_code", "as_of", "bazi", "ziwei", "huangli"]]
    return panel, dirs


class TestConsensusResearch:
    def test_runs_over_all_predefined_combos(self):
        panel, dirs = _panel(0)
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=True),
        )
        assert len(res.combos) == len(ALL_COMBO_IDS)
        assert res.multiple_testing.experiment_count == len(ALL_COMBO_IDS)
        assert res.methodology
        assert res.conclusion

    def test_free_combo_search_is_rejected(self):
        """数据挖掘防护：不允许自定义组合。"""
        panel, dirs = _panel(0)
        with pytest.raises(ValueError) as exc:
            run_consensus_research(
                panel=panel, directions=dirs,
                request=ConsensusResearchRequest(combos=["MY_OWN_COMBO"]),
            )
        assert "不允许自由定义组合" in str(exc.value)

    def test_random_data_does_not_produce_false_outperformance(self):
        """**关键防线**：在纯随机数据上，不应大量出现 "outperform"。

        早期实现用"差值 > 半个标准误"的经验带，在随机数据上 11 个组合里
        能冒出 7 个 "outperform"。改用 Welch t 检验后应回到 5% 名义水平附近。
        """
        total_runs = 0
        wins = 0
        for seed in range(5):
            panel, dirs = _panel(seed)
            res = run_consensus_research(
                panel=panel, directions=dirs,
                request=ConsensusResearchRequest(run_negative_controls=True),
            )
            total_runs += len(res.combos)
            wins += sum(1 for c in res.combos if c.control_result == "outperform")
        rate = wins / total_runs
        assert rate <= 0.15, (
            f"随机数据下 outperform 比例 {rate:.1%} 过高（共 {wins}/{total_runs}）—— "
            "判决门槛过松，会产生假阳性"
        )

    def test_real_edge_is_detectable(self):
        """真有效时应当能被检出 —— 否则说明门槛过严，测试没有鉴别力。

        注意这里刻意用**更大**的面板：随机方向对照会与真实事件集合部分重叠
        （两者激活率相同），效应量小时需要足够样本量才能分辨。
        这正是为什么本项目要求"事件数 < 30 判 INSUFFICIENT_SAMPLE"。
        """
        panel, dirs = _panel(0, n=2400, edge=0.08)
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=True),
        )
        combo = next(c for c in res.combos if c.combo_id == "BAZI_ZIWEI_POS")
        assert combo.control_result == "outperform", (
            f"注入 6% 额外收益后仍判为 {combo.control_result}（p={combo.p_value}）"
        )
        assert combo.research_status == "WEAK_EVIDENCE"
        assert "样本内" in "".join(combo.research_status_reasons)

    def test_negative_control_is_required_for_any_validity_claim(self):
        panel, dirs = _panel(0, edge=0.06)
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=False),
        )
        for c in res.combos:
            if c.event_count:
                assert c.control_result in ("not_run",)
                assert c.research_status == "INCONCLUSIVE"
                assert any("没有负对照" in r for r in c.research_status_reasons)

    def test_jaccard_too_high_yields_invalid_control(self):
        """对照集合与真实集合几乎重合时必须判 INVALID_CONTROL。"""
        n = 200
        panel = pd.DataFrame({
            "stock_code": [f"S{i}" for i in range(n)],
            "as_of": [f"2021-{i % 12 + 1:02d}" for i in range(n)],
            "ret_20d": np.linspace(-0.1, 0.1, n),
            "excess_return_20d": np.linspace(-0.1, 0.1, n),
        })
        # bazi 恒为正 → 打乱后集合几乎不变 → Jaccard 极高
        dirs = pd.DataFrame({
            "stock_code": panel["stock_code"], "as_of": panel["as_of"],
            "bazi": [1] * n, "ziwei": [1] * n, "huangli": [1] * n,
        })
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=True),
        )
        combo = next(c for c in res.combos if c.combo_id == "BAZI_POS")
        assert combo.jaccard_with_real > 0.9
        assert combo.research_status == "INVALID_CONTROL"
        assert combo.control_result == "invalid"
        assert res.overall_research_status == "INVALID_CONTROL"

    def test_insufficient_sample_is_reported_not_hidden(self):
        panel, dirs = _panel(0, n=60)
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=True),
        )
        small = [c for c in res.combos if c.event_count and c.event_count < 30]
        assert small
        for c in small:
            assert c.research_status == "INSUFFICIENT_SAMPLE"
            assert any("统计意义" in r for r in c.research_status_reasons)

    def test_statistics_are_populated(self):
        panel, dirs = _panel(0, edge=0.05)
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=True),
        )
        c = next(x for x in res.combos if x.event_count >= 30)
        assert c.sample_count > 0
        assert c.event_rate is not None and 0 <= c.event_rate <= 1
        assert c.up_rate is not None
        assert c.mean_return is not None
        assert c.control_event_count >= 0
        assert c.t_stat is not None and c.p_value is not None
        assert c.test_method == "welch_t_test_two_sided"

    def test_panel_key_uniqueness_warning(self):
        """重复 (stock_code, as_of) 会让 Jaccard 失真 —— 必须给出警告。"""
        panel = pd.DataFrame({
            "stock_code": ["A", "A"], "as_of": ["2021-01", "2021-01"],
            "ret_20d": [0.01, 0.02], "excess_return_20d": [0.0, 0.01],
        })
        dirs = pd.DataFrame({
            "stock_code": ["A", "A"], "as_of": ["2021-01", "2021-01"],
            "bazi": [1, 1], "ziwei": [1, 1], "huangli": [1, 1],
        })
        res = run_consensus_research(
            panel=panel, directions=dirs,
            request=ConsensusResearchRequest(run_negative_controls=True),
        )
        assert any(w.code == "CONSENSUS_DUPLICATE_PANEL_KEYS" for w in res.warnings)


class TestMultipleTesting:
    def test_low_experiment_count_is_not_flagged(self):
        w = build_multiple_testing_warning(3, 6)
        assert w.warning_level == "none"
        assert "未做组合搜索" in w.message

    def test_many_combos_produce_caution_with_bonferroni(self):
        w = build_multiple_testing_warning(11, 22)
        assert w.warning_level == "caution"
        assert w.bonferroni_alpha == round(0.05 / 11, 6)
        assert "多重比较" in w.message

    def test_very_many_combos_produce_high_warning(self):
        w = build_multiple_testing_warning(30, 60)
        assert w.warning_level == "high"

    def test_selection_method_recorded(self):
        w = build_multiple_testing_warning(11, 22)
        assert w.selection_method
        assert w.experiment_count == 11 and w.parameter_count == 22


class TestPanelBuilder:
    def test_rows_align_strictly_and_drop_missing_labels(self):
        dates = [date(2021, 1, 1), date(2021, 2, 1)]

        def opinion_builder(code, d):
            return {"bazi": 1, "ziwei": -1, "huangli": 0}

        def label_builder(code, d):
            if code == "B" and d.month == 2:
                return None       # 模拟"没有未来数据"
            return _StubLabels(code, d)

        panel, dirs = build_consensus_panel(
            stocks=["A", "B"], sample_dates=dates,
            opinion_builder=opinion_builder, label_builder=label_builder,
        )
        assert len(panel) == len(dirs) == 3
        assert panel["stock_code"].tolist() == dirs["stock_code"].tolist()
        assert panel["as_of"].tolist() == dirs["as_of"].tolist()

    def test_failures_are_recorded_as_warnings_not_silent(self):
        def opinion_builder(code, d):
            raise RuntimeError("引擎炸了")

        def label_builder(code, d):  # pragma: no cover - 不应被调用
            raise AssertionError

        warnings: list = []
        panel, dirs = build_consensus_panel(
            stocks=["A"], sample_dates=[date(2021, 1, 1)],
            opinion_builder=opinion_builder, label_builder=label_builder,
            warnings=warnings,
        )
        assert panel.empty and dirs.empty
        assert warnings and warnings[0].code == "CONSENSUS_OPINION_FAILED"


# ---------------------------------------------------------------------------
# 5. 便捷入口
# ---------------------------------------------------------------------------


class TestBuildConsensusAndConflict:
    def test_returns_both_reports(self):
        cons, conf = build_consensus_and_conflict({
            "bazi": opinion("bazi", 1, 80),
            "ziwei": opinion("ziwei", -1, 20),
        }, research_status="NO_SIGNAL")
        assert cons.consensus_class == ConsensusLabel.MIXED
        assert conf.has_conflict is True
        assert "NO_SIGNAL" in cons.interpretation


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

_AS_OF = pd.Timestamp("2024-11-15").to_pydatetime()


def _obs(factor_id: str, engine: EngineId, direction: int, normalized: float,
         *, category: str = "natal", tags: list[str] | None = None) -> FactorObservation:
    """构造观测，并把 tags 临时注入定义索引（测试内自洽，不改动生产定义）。"""
    from src.core.schemas.factor import FactorCategory
    from src.factors.registry.definitions import DEFINITION_INDEX
    from src.factors.registry.definitions import FactorDefinition as FD

    if factor_id not in DEFINITION_INDEX:
        DEFINITION_INDEX[factor_id] = FD(
            factor_id=factor_id, name=factor_id, engine=engine,
            category=FactorCategory(category), definition="测试因子",
            computation="test", tags=tags or [],
        )
    return FactorObservation(
        factor_id=factor_id, stock_code="X", as_of=_AS_OF,
        engine=engine, category=FactorCategory(category), name=factor_id,
        raw_value=normalized, normalized_value=normalized,
        direction=direction, rule_score=abs(normalized) * 10, confidence=0.8,
        availability="ok", rule_version="test", engine_version="test",
        explanation="测试", computed_at=_AS_OF,
    )


_ = (json, Path, evaluate_combo)


class _StubLabels:
    """最小 LabelSet 替身（只提供面板需要的字段）。"""

    def __init__(self, code: str, d: date) -> None:
        self.stock_code = code
        self.trade_date = d
        self.as_of = d
        self.ret_1d = 0.001
        self.ret_5d = 0.002
        self.ret_10d = 0.003
        self.ret_20d = 0.004
        self.ret_60d = 0.005
        self.excess_return_20d = 0.001
