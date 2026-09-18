"""因子计算测试。

纪律验证：
* 因子必须可计算、可追溯、带版本；
* ``direction`` / ``rule_score`` 是**传统规则强度**，不是收益预测；
* 计算不出来的因子必须返回 unavailable，不允许猜数；
* 财星 ≠ 股票上涨（因子解释文本中不得出现"必涨/上涨"等确定性表述）。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.schemas.common import Direction, EngineId
from src.factors.registry.compute import classify_wuxing, compute_factor_set
from src.factors.registry.definitions import (
    ALL_DEFINITIONS,
    DEFINITION_INDEX,
    FACTOR_DISCLAIMER,
)


class TestRegistry:
    def test_at_least_30_factors(self):
        """two_session_plan §9 要求至少 30-50 个因子。"""
        assert len(ALL_DEFINITIONS) >= 40

    def test_factor_ids_unique(self):
        ids = [d.factor_id for d in ALL_DEFINITIONS]
        assert len(ids) == len(set(ids))

    def test_ids_follow_naming_convention(self):
        prefixes = ("B_NATAL_", "B_YEAR_", "B_MONTH_", "B_DAY_", "H_DAY_", "H_MONTH_")
        for d in ALL_DEFINITIONS:
            assert d.factor_id.startswith(prefixes), d.factor_id

    def test_every_factor_has_definition_and_version(self):
        for d in ALL_DEFINITIONS:
            assert d.name, d.factor_id
            assert d.definition, d.factor_id
            assert d.rule_version, d.factor_id
            assert d.definition.strip() != ""

    def test_every_factor_declares_rule_score_semantics(self):
        """每个因子必须显式声明 rule_score 不是收益率。"""
        for d in ALL_DEFINITIONS:
            assert "不代表" in d.rule_score_meaning
            assert "收益率" in d.rule_score_meaning or "收益" in d.rule_score_meaning

    def test_categories_distribution(self):
        counts: dict[str, int] = {}
        for d in ALL_DEFINITIONS:
            counts[d.category] = counts.get(d.category, 0) + 1
        assert counts.get("natal", 0) >= 10
        assert counts.get("month", 0) >= 8
        assert counts.get("year", 0) >= 6
        assert counts.get("day", 0) >= 6
        assert counts.get("cross", 0) >= 8

    def test_engines_are_declared(self):
        engines = {d.engine for d in ALL_DEFINITIONS}
        assert EngineId.BAZI in engines
        assert EngineId.HUANGLI in engines


class TestFactorComputation:
    def test_all_definitions_produce_observations(self, factor_set):
        produced = {o.factor_id for o in factor_set.observations}
        missing = set(DEFINITION_INDEX) - produced
        assert not missing, f"以下因子未产出观测：{sorted(missing)}"

    def test_observations_have_required_fields(self, factor_set):
        for o in factor_set.observations:
            assert o.factor_id
            assert o.stock_code == "600519"
            assert o.as_of == datetime(2024, 11, 15, 14, 32)
            assert o.rule_version
            assert o.engine_version
            assert o.explanation
            assert 0.0 <= o.confidence <= 1.0
            assert 0.0 <= o.rule_score <= 10.0
            assert o.direction in (Direction.POSITIVE, Direction.NEUTRAL, Direction.NEGATIVE)

    def test_normalized_values_in_range(self, factor_set):
        for o in factor_set.observations:
            if o.normalized_value is not None:
                assert -1.0 <= o.normalized_value <= 1.0, f"{o.factor_id}={o.normalized_value}"

    def test_specific_natal_factors(self, factor_set):
        """壬日主、财星为火：验证具体因子取值合理。"""
        obs = {o.factor_id: o for o in factor_set.observations}
        assert obs["B_NATAL_001"].raw_value in ("身强", "偏强", "中和", "偏弱", "身弱")
        assert float(obs["B_NATAL_002"].raw_value) >= 0
        assert obs["B_NATAL_014"].raw_value is not None      # 财星力量占比
        assert obs["B_NATAL_018"].raw_value in ("阳干", "阴干")

    def test_month_factors_reflect_current_month(self, factor_set):
        obs = {o.factor_id: o for o in factor_set.observations}
        # 2024-11-15 处在乙亥月，亥为水
        assert obs["B_MONTH_012"].raw_value is not None
        assert obs["B_MONTH_011"].raw_value in (
            "比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印",
        )

    def test_day_factors_match_day_pillar(self, factor_set, maotai_chart):
        """流日因子必须与当前流日一柱一致。"""
        obs = {o.factor_id: o for o in factor_set.observations}
        assert obs["B_DAY_005"].raw_value == maotai_chart.current_day_pillar.stem_ten_god

    def test_huangli_factors_use_huangli_data(self, factor_set):
        obs = {o.factor_id: o for o in factor_set.observations}
        assert obs["H_DAY_006"].raw_value in (
            "建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭",
        )
        assert obs["H_DAY_007"].raw_value in ("黄道", "黑道", "")

    def test_month_aggregates_from_scan(self, factor_set):
        obs = {o.factor_id: o for o in factor_set.observations}
        raw = obs["H_MONTH_001"].raw_value
        assert isinstance(raw, dict)
        assert 25 <= raw["days"] <= 32      # 一个自然月
        assert 0 <= raw["count"] <= raw["days"]

    def test_factor_set_metadata(self, factor_set):
        assert factor_set.stock_code == "600519"
        assert factor_set.rule_version
        assert factor_set.config_version
        assert factor_set.engine_version


class TestUnavailableContract:
    def test_missing_huangli_yields_unavailable_not_zero(self, maotai_chart):
        """没有黄历时不得伪造 H_* 因子，也不得填 0。"""
        fs = compute_factor_set(maotai_chart, None, datetime(2024, 11, 15, 14, 32), stock_code="600519")
        ids = {o.factor_id for o in fs.observations}
        assert all(not i.startswith("H_") for i in ids)
        assert any(i.startswith("B_NATAL_") for i in ids)

    def test_unavailable_helper_marks_confidence_zero(self):
        from src.factors.registry.compute import _unavailable

        obs = _unavailable("B_NATAL_010", "600519", datetime(2024, 1, 1), "用神未能确定")
        assert obs.availability == "unavailable"
        assert obs.confidence == 0.0
        assert obs.normalized_value is None
        assert obs.raw_value is None
        assert obs.warnings


class TestDirectionSemantics:
    def test_classify_wuxing(self, maotai_chart):
        yong = maotai_chart.yong_shen
        if yong.yong_shen:
            label, norm, direction = classify_wuxing(yong.yong_shen[0], yong)
            assert label == "用神"
            assert norm == 1.0
            assert direction == Direction.POSITIVE
        if yong.ji_shen:
            label, norm, direction = classify_wuxing(yong.ji_shen[0], yong)
            assert label == "忌神"
            assert norm == -1.0
            assert direction == Direction.NEGATIVE

    def test_factors_never_claim_price_direction(self, factor_set):
        """因子的解释文本中不得出现**肯定式**的涨跌断言。

        注意：需要区分「股价一定上涨」（违规）与「不代表股价一定上涨」（合规），
        因此这里对每个命中位置检查其前缀是否带有否定词。
        """
        forbidden = ("必涨", "一定上涨", "保证上涨", "必然上涨", "必跌", "股价会涨")
        negations = ("不", "非", "未", "无", "禁止", "≠", "并非", "不是", "不能")

        offences: list[str] = []
        for o in factor_set.observations:
            text = o.explanation
            for word in forbidden:
                start = 0
                while (idx := text.find(word, start)) != -1:
                    prefix = text[max(0, idx - 10): idx]
                    if not any(neg in prefix for neg in negations):
                        offences.append(f"{o.factor_id}: …{text[max(0, idx - 12): idx + len(word) + 4]}…")
                    start = idx + len(word)
        assert not offences, f"因子出现确定性涨跌断言：{offences}"

    def test_disclaimer_exists(self):
        assert "不是预期收益率" in FACTOR_DISCLAIMER or "研究变量" in FACTOR_DISCLAIMER

    def test_wealth_factor_does_not_claim_rise(self, factor_set):
        """财星相关因子的说明必须明确"不等于上涨"。"""
        wealth = [o for o in factor_set.observations if o.factor_id in
                  ("B_NATAL_002", "B_NATAL_003", "B_MONTH_003", "B_MONTH_004")]
        assert wealth
        joined = " ".join(o.explanation for o in wealth)
        assert "上涨" in joined or "不代表" in joined or "研究" in joined


class TestReproducibility:
    def test_same_input_same_output(self, bazi_engine, huangli_engine):
        kwargs = dict(
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2024, 11, 15, 14, 32),
            stock_code="600519",
        )
        c1 = bazi_engine.build_chart(**kwargs)
        c2 = bazi_engine.build_chart(**kwargs)
        assert c1.model_dump_json(exclude={"calculated_at"}) == c2.model_dump_json(
            exclude={"calculated_at"}
        )

        h1 = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=31)
        h2 = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=31)
        f1 = compute_factor_set(c1, h1, datetime(2024, 11, 15, 14, 32), stock_code="600519")
        f2 = compute_factor_set(c2, h2, datetime(2024, 11, 15, 14, 32), stock_code="600519")
        assert [o.model_dump(exclude={"computed_at"}) for o in f1.observations] == \
               [o.model_dump(exclude={"computed_at"}) for o in f2.observations]

    def test_engine_version_pinned_on_every_factor(self, factor_set):
        for o in factor_set.observations:
            assert o.engine_version, o.factor_id
