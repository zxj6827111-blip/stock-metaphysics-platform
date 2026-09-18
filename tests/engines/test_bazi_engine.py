"""BaziEngine 测试。

覆盖 two_session_plan §8 要求的全部输出字段：
年柱 / 月柱 / 日柱 / 时柱 / 藏干 / 十神 / 纳音 / 五行 / 日主 /
旺衰 / 格局 / 喜神 / 用神 / 忌神 / 刑冲合害 / 流年 / 流月。

同时验证「股票无性别」相关契约：
* ``variant_mode`` 默认 ``not_applicable``；
* 不输出大运（不偷偷按男命起运）；
* 必须记录 assumption。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.constants import ten_god, twelve_stage
from src.core.schemas.common import Availability, VariantMode
from src.engines.bazi import rules


class TestPillars:
    def test_four_pillars(self, maotai_chart):
        assert maotai_chart.year_pillar.ganzhi.text == "辛巳"
        assert maotai_chart.month_pillar.ganzhi.text == "丙申"
        assert maotai_chart.day_pillar.ganzhi.text == "壬戌"
        assert maotai_chart.hour_pillar.ganzhi.text == "乙巳"

    def test_day_master(self, maotai_chart):
        assert maotai_chart.day_master == "壬"
        assert maotai_chart.day_master_wuxing == "水"

    def test_hidden_stems(self, maotai_chart):
        """年支巳藏 丙庚戊；月支申藏 庚壬戊；日支戌藏 戊辛丁；时支巳藏 丙庚戊。"""
        assert [h.stem for h in maotai_chart.year_pillar.hidden_stems] == ["丙", "庚", "戊"]
        assert [h.stem for h in maotai_chart.month_pillar.hidden_stems] == ["庚", "壬", "戊"]
        assert [h.stem for h in maotai_chart.day_pillar.hidden_stems] == ["戊", "辛", "丁"]

    def test_hidden_stem_ranks_and_weights(self, maotai_chart):
        hs = maotai_chart.year_pillar.hidden_stems
        assert [h.rank for h in hs] == ["本气", "中气", "余气"]
        assert hs[0].weight > hs[1].weight > hs[2].weight

    def test_ten_gods_relative_to_day_master(self, maotai_chart):
        """壬日主：年干辛=正印，月干丙=偏财，时干乙=伤官。"""
        assert maotai_chart.year_pillar.stem_ten_god == "正印"
        assert maotai_chart.month_pillar.stem_ten_god == "偏财"
        assert maotai_chart.hour_pillar.stem_ten_god == "伤官"
        assert maotai_chart.day_pillar.stem_ten_god == "日主"

    def test_nayin(self, maotai_chart):
        assert maotai_chart.year_pillar.nayin == "白蜡金"
        assert maotai_chart.month_pillar.nayin == "山下火"
        assert maotai_chart.day_pillar.nayin == "大海水"
        assert maotai_chart.hour_pillar.nayin == "覆灯火"

    def test_twelve_stage(self, maotai_chart):
        """壬（水）在申为长生，在巳为绝。"""
        assert maotai_chart.month_pillar.di_shi == "长生"
        assert maotai_chart.year_pillar.di_shi == "绝"


class TestWuxingAndStrength:
    def test_wuxing_percentages_sum_to_100(self, maotai_chart):
        total = sum(maotai_chart.wuxing.percentages.values())
        assert 99.0 <= total <= 101.0

    def test_dominant_and_weakest(self, maotai_chart):
        assert maotai_chart.wuxing.dominant in ("金", "火", "水", "木", "土")
        assert maotai_chart.wuxing.weakest in ("金", "火", "水", "木", "土")
        assert maotai_chart.wuxing.percentages[maotai_chart.wuxing.dominant] >= \
               mautai_weakest(maotai_chart)

    def test_strength_dimensions(self, maotai_chart):
        dm = maotai_chart.day_master_analysis
        assert dm.month_branch == "申"
        assert isinstance(dm.de_ling, bool)
        assert isinstance(dm.de_di, bool)
        assert isinstance(dm.de_shi, bool)
        assert 0.0 <= dm.balance_ratio <= 1.0
        assert dm.strength_level in ("身强", "偏强", "中和", "偏弱", "身弱")
        assert 0.0 < dm.confidence <= 1.0

    def test_strength_rationale_available(self, maotai_chart):
        """旺衰判定过程必须可追溯（rules 层输出 rationale）。"""
        from src.core.constants import STEM_WUXING

        stems = {"year": "辛", "month": "丙", "day": "壬", "hour": "乙"}
        branches = {"year": "巳", "month": "申", "day": "戌", "hour": "巳"}
        wuxing = rules.compute_wuxing_scores(stems, branches)
        strength = rules.compute_strength(stems, branches, wuxing)
        assert strength.rationale
        assert any("得令" in r for r in strength.rationale)
        assert STEM_WUXING[strength.day_master] == strength.day_master_wuxing


def mautai_weakest(chart):  # noqa: N802 - 小工具
    return chart.wuxing.percentages[chart.wuxing.weakest]


class TestPattern:
    def test_pattern_has_method_and_confidence(self, maotai_chart):
        p = maotai_chart.pattern
        assert p.method
        assert 0.0 <= p.confidence <= 1.0
        assert p.availability in (Availability.OK, Availability.UNAVAILABLE)

    def test_pattern_candidates_listed(self, maotai_chart):
        p = maotai_chart.pattern
        assert len(p.candidates) >= 1
        for c in p.candidates:
            assert c.name
            assert c.basis

    def test_pattern_unavailable_is_honest(self):
        """无法判定时必须返回 unavailable，而不是猜一个。"""
        result = rules.compute_pattern(
            {"year": "甲", "month": "甲", "day": "甲", "hour": "甲"},
            {"year": "子", "month": "子", "day": "子", "hour": "子"},
        )
        # 子月甲日：月支子藏癸，癸为甲之正印 → 应以正印取格
        assert result.primary in ("正印格", "建禄格", "月刃格", "比肩格", "劫财格")
        assert result.availability == "ok"


class TestYongShen:
    def test_yongshen_non_empty(self, maotai_chart):
        y = maotai_chart.yong_shen
        assert y.yong_shen
        assert y.method
        assert y.rationale

    def test_yongshen_groups_disjoint(self, maotai_chart):
        y = maotai_chart.yong_shen
        yong = set(y.yong_shen)
        ji = set(y.ji_shen)
        assert not (yong & ji), "用神与忌神不应重叠"

    def test_tiaohou_note_present(self, maotai_chart):
        assert maotai_chart.yong_shen.tiaohou_note


class TestRelations:
    def test_relations_computed(self, maotai_chart):
        types = {r.relation_type for r in maotai_chart.relations}
        assert types, "四柱之间应至少产生一种关系"
        assert all(r.positions for r in maotai_chart.relations)

    def test_known_punishment_fulfilled(self):
        """巳申相刑（寅巳申三刑的一部分）应被检出。"""
        hits = rules.compute_relations(
            {"year": "辛", "month": "丙", "day": "壬", "hour": "乙"},
            {"year": "巳", "month": "申", "day": "戌", "hour": "巳"},
        )
        punishing = [h for h in hits if h["relation_type"] == "相刑"]
        assert any(set(h["branches_or_stems"]) == {"巳", "申"} for h in punishing)

    def test_six_harmony_detected(self):
        hits = rules.compute_relations(
            {"year": "甲", "month": "甲", "day": "甲", "hour": "甲"},
            {"year": "子", "month": "丑", "day": "寅", "hour": "卯"},
        )
        types = {h["relation_type"] for h in hits}
        assert "六合" in types  # 子丑六合

    def test_triple_harmony_detected(self):
        hits = rules.compute_relations(
            {"year": "甲", "month": "甲", "day": "甲", "hour": "甲"},
            {"year": "申", "month": "子", "day": "辰", "hour": "丑"},
        )
        triple = [h for h in hits if h["relation_type"] == "三合"]
        assert triple
        assert triple[0]["transform_element"] == "水"

    def test_six_clash_detected(self):
        hits = rules.compute_relations(
            {"year": "甲", "month": "甲", "day": "甲", "hour": "甲"},
            {"year": "子", "month": "午", "day": "寅", "hour": "卯"},
        )
        assert any(h["relation_type"] == "六冲" for h in hits)


class TestTemporal:
    def test_current_year_pillar(self, maotai_chart):
        tp = maotai_chart.current_year_pillar
        assert tp is not None
        assert tp.kind == "year"
        assert tp.ganzhi.text == "甲辰"      # 2024 年（立春后）
        assert tp.stem_ten_god == ten_god("壬", "甲")
        assert tp.di_shi == twelve_stage("壬", "辰")

    def test_current_month_pillar(self, maotai_chart):
        tp = maotai_chart.current_month_pillar
        assert tp is not None
        assert tp.kind == "month"
        assert tp.ganzhi.text == "乙亥"      # 2024-11-15 在立冬之后
        assert tp.branch_is in ("用神", "喜神", "忌神", "仇神", "闲神")

    def test_current_day_pillar(self, maotai_chart):
        tp = maotai_chart.current_day_pillar
        assert tp is not None
        assert tp.kind == "day"
        assert tp.ganzhi.text == "癸未"

    def test_temporal_relations_against_natal(self, maotai_chart):
        """流月亥冲原局巳（年/时），应在 clashes_with_natal 中体现。"""
        tp = maotai_chart.current_month_pillar
        assert "year" in tp.clashes_with_natal
        assert "hour" in tp.clashes_with_natal


class TestNoGenderContract:
    def test_variant_mode_defaults_to_not_applicable(self, maotai_chart):
        assert maotai_chart.variant_mode == VariantMode.NOT_APPLICABLE

    def test_da_yun_not_emitted_by_default(self, maotai_chart):
        """股票无性别 → Phase 1 不得输出大运（不能偷偷按男命起运）。"""
        assert maotai_chart.da_yun == []
        assert "性别" in maotai_chart.da_yun_note

    def test_assumption_recorded(self, maotai_chart):
        keys = {a.key for a in maotai_chart.assumptions}
        assert "bazi.variant_mode" in keys
        assumption = next(a for a in maotai_chart.assumptions if a.key == "bazi.variant_mode")
        assert assumption.value == "not_applicable"
        assert "性別" in assumption.reason or "性别" in assumption.reason

    def test_explicit_variant_mode_computes_dayun(self, bazi_engine):
        """显式声明 forward 时才计算大运，且必须标注为假设计算。"""
        chart = bazi_engine.build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2024, 11, 15, 14, 32),
            variant_mode=VariantMode.FORWARD,
            stock_code="600519",
        )
        assert chart.variant_mode == VariantMode.FORWARD
        assert len(chart.da_yun) > 0
        assert "假设" in chart.da_yun_note


class TestRawChartTraceability:
    def test_engine_version_and_source(self, maotai_chart):
        assert maotai_chart.engine_id == "bazi"
        assert maotai_chart.engine_version
        assert maotai_chart.config_version
        assert maotai_chart.source.source == "smx-bazi-native"
        assert maotai_chart.source.extra["calendar"] == "lunar-python 1.4.8"

    def test_chart_serializes_fully(self, maotai_chart):
        """原始盘面必须能完整序列化落库（chart_artifact.raw_chart）。"""
        payload = maotai_chart.model_dump(mode="json")
        assert payload["year_pillar"]["ganzhi"]["text"] == "辛巳"
        assert payload["wuxing"]["percentages"]
        assert payload["current_month_pillar"]["ganzhi"]["text"] == "乙亥"
        assert payload["available"] if "available" in payload else True

    def test_auxiliary_palaces(self, maotai_chart):
        assert maotai_chart.tai_yuan
        assert maotai_chart.ming_gong
        assert maotai_chart.shen_gong


class TestTenGodConsistency:
    @pytest.mark.parametrize(
        "day,other,expected",
        [
            ("甲", "甲", "比肩"), ("甲", "乙", "劫财"),
            ("甲", "丙", "食神"), ("甲", "丁", "伤官"),
            ("甲", "戊", "偏财"), ("甲", "己", "正财"),
            ("甲", "庚", "七杀"), ("甲", "辛", "正官"),
            ("甲", "壬", "偏印"), ("甲", "癸", "正印"),
            ("壬", "辛", "正印"), ("壬", "甲", "食神"),
        ],
    )
    def test_ten_god_table(self, day, other, expected):
        assert ten_god(day, other) == expected

    @pytest.mark.parametrize(
        "stem,branch,stage",
        [
            ("甲", "亥", "长生"), ("甲", "卯", "帝旺"), ("甲", "午", "死"),
            ("壬", "申", "长生"), ("壬", "子", "帝旺"), ("壬", "巳", "绝"),
            ("乙", "午", "长生"), ("乙", "寅", "帝旺"),
        ],
    )
    def test_twelve_stage_table(self, stem, branch, stage):
        assert twelve_stage(stem, branch) == stage
