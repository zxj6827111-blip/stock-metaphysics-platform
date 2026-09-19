"""紫微因子测试（Phase 2B）。

覆盖
----
* 定义完整性（数量、命名空间、必填字段、免责声明）；
* 计算确定性、可用性契约（不可用必须 unavailable，禁止填 0）；
* 方向语义（数量型因子中性；传统吉凶只作研究变量）；
* **variant 影响范围**（只有声明为 variant-sensitive 的因子可以随 variant 变化）；
* 与 Phase 1 因子的隔离（ID 不冲突、rule_version 独立）；
* "股票—宫位映射是研究假设"这一声明被机器校验。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.core.config import settings
from src.core.schemas.common import Direction
from src.core.schemas.ziwei import ZiweiChart
from src.factors.registry.definitions import (
    ALL_DEFINITIONS,
    DEFINITION_INDEX,
    PHASE1_DEFINITION_INDEX,
)
from src.factors.ziwei.compute import compute_ziwei_factors, ziwei_rule_version
from src.factors.ziwei.definitions import (
    ALL_ZIWEI_DEFINITIONS,
    KEY_PALACES,
    SECONDARY_PALACES,
    VARIANT_SENSITIVE_FACTOR_IDS,
    ZIWEI_DEFINITION_INDEX,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ziwei"
AS_OF = datetime(2024, 11, 15, 14, 32)

#: 肯定式涨跌断言（否定式如"不代表股价一定上涨"是允许的）
FORBIDDEN_ASSERTIONS = ("必涨", "一定上涨", "保证上涨", "必然上涨", "必跌", "股价会涨", "稳赚")


def load(name: str) -> ZiweiChart:
    return ZiweiChart.model_validate(
        json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def fwd() -> ZiweiChart:
    return load("600519-listing-forward")


def rev() -> ZiweiChart:
    return load("600519-listing-reverse")


# ---------------------------------------------------------------------------
# 1. 定义完整性
# ---------------------------------------------------------------------------


class TestZiweiDefinitionRegistry:
    def test_factor_count_in_required_range(self):
        """任务要求 30–50 个紫微因子。"""
        assert 30 <= len(ALL_ZIWEI_DEFINITIONS) <= 50, len(ALL_ZIWEI_DEFINITIONS)

    def test_all_ids_use_z_prefix_and_are_unique(self):
        ids = [d.factor_id for d in ALL_ZIWEI_DEFINITIONS]
        assert all(i.startswith("Z_") for i in ids)
        assert len(ids) == len(set(ids))

    def test_no_id_collision_with_phase1_factors(self):
        overlap = set(ZIWEI_DEFINITION_INDEX) & set(PHASE1_DEFINITION_INDEX)
        assert not overlap, f"紫微因子与 Phase 1 因子 ID 冲突：{overlap}"

    def test_all_registered_in_global_index(self):
        for d in ALL_ZIWEI_DEFINITIONS:
            assert DEFINITION_INDEX[d.factor_id] is d
        assert len(ALL_DEFINITIONS) == len(PHASE1_DEFINITION_INDEX) + len(ALL_ZIWEI_DEFINITIONS)

    def test_engine_is_ziwei(self):
        for d in ALL_ZIWEI_DEFINITIONS:
            assert str(d.engine) == "ziwei", d.factor_id

    def test_rule_score_meaning_disclaims_return_prediction(self):
        for d in ALL_ZIWEI_DEFINITIONS:
            assert d.rule_score_meaning, d.factor_id
            assert "不代表预期收益率" in d.rule_score_meaning, d.factor_id
            assert "不代表上涨概率" in d.rule_score_meaning, d.factor_id

    def test_definitions_have_definition_computation_and_requires(self):
        for d in ALL_ZIWEI_DEFINITIONS:
            assert len(d.definition) >= 20, f"{d.factor_id} 定义过短"
            assert d.computation, f"{d.factor_id} 缺少计算说明"
            assert d.requires, f"{d.factor_id} 未声明依赖的盘面字段"
            assert d.normalized_hint, f"{d.factor_id} 缺少归一化说明"

    def test_rule_version_is_ziwei_scoped(self):
        for d in ALL_ZIWEI_DEFINITIONS:
            assert d.rule_version == settings.ziwei_factor_rule_version
            assert d.rule_version != settings.factor_rule_version, (
                "紫微因子必须使用独立 rule_version，不能复用八字的 v1.x"
            )

    def test_no_affirmative_price_assertions_in_definitions(self):
        for d in ALL_ZIWEI_DEFINITIONS:
            text = d.definition + d.computation + d.raw_unit + d.normalized_hint
            for bad in FORBIDDEN_ASSERTIONS:
                assert bad not in text, f"{d.factor_id} 出现肯定式断言 {bad!r}"

    def test_stock_mapping_is_labelled_as_research_assumption(self):
        """『财帛宫 = 资金』这类映射必须显式标注为研究假设，不得写成传统定论。"""
        mapped = [d for d in ALL_ZIWEI_DEFINITIONS if "research_mapping" in d.tags]
        assert mapped, "缺少带 research_mapping 标记的宫位映射因子"
        for d in mapped:
            assert "研究映射" in d.definition, d.factor_id
            assert settings.ziwei_stock_mapping_version in d.definition or "假设" in d.definition, (
                f"{d.factor_id} 未说明映射属于研究假设"
            )
        # 关键宫映射必须覆盖 财帛 / 官禄 / 迁移
        for palace in ("财帛宫", "官禄宫", "迁移宫"):
            assert any(palace in d.definition for d in mapped), f"缺少 {palace} 的映射因子"

    def test_namespaces_cover_required_groups(self):
        prefixes = {d.factor_id.rsplit("_", 1)[0] for d in ALL_ZIWEI_DEFINITIONS}
        for required in (
            "Z_LIFE", "Z_FIN", "Z_CAREER", "Z_MOVE", "Z_MUTAGEN",
            "Z_TRINE", "Z_YEAR", "Z_MONTH", "Z_DAY", "Z_DECADE", "Z_AGE",
        ):
            assert required in prefixes, f"缺少因子命名空间 {required}"

    def test_key_palaces_are_the_four_research_positions(self):
        assert set(KEY_PALACES) == {"命宫", "财帛", "官禄", "迁移"}
        assert set(SECONDARY_PALACES).issubset({"福德", "田宅"})

    def test_variant_sensitive_ids_exist(self):
        for fid in VARIANT_SENSITIVE_FACTOR_IDS:
            assert fid in ZIWEI_DEFINITION_INDEX, f"{fid} 未定义"
            assert ZIWEI_DEFINITION_INDEX[fid].factor_id == fid


# ---------------------------------------------------------------------------
# 2. 计算
# ---------------------------------------------------------------------------


class TestZiweiFactorComputation:
    def test_computes_every_defined_factor(self):
        obs = compute_ziwei_factors(fwd(), AS_OF, stock_code="600519", variant="forward")
        assert {o.factor_id for o in obs} == set(ZIWEI_DEFINITION_INDEX)
        assert len(obs) == len(ALL_ZIWEI_DEFINITIONS)

    def test_no_unavailable_on_a_complete_chart(self):
        """完整盘面不应产生任何 unavailable —— 否则说明接线有缺口。"""
        obs = compute_ziwei_factors(fwd(), AS_OF, stock_code="600519", variant="forward")
        bad = [o.factor_id for o in obs if o.availability != "ok"]
        assert not bad, f"完整盘面下出现不可用因子：{bad}"

    def test_normalized_values_within_range(self):
        for name in ("600519-listing-forward", "000001-listing-forward", "2020-haishi", "1999-late-zishi"):
            chart = load(name)
            variant = str(chart.variant_mode)
            for o in compute_ziwei_factors(chart, AS_OF, stock_code="X", variant=variant):
                if o.normalized_value is not None:
                    assert -1.0 <= o.normalized_value <= 1.0, (
                        f"{o.factor_id} normalized_value 越界：{o.normalized_value}"
                    )

    def test_rule_scores_within_range(self):
        for o in compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward"):
            assert 0.0 <= o.rule_score <= 10.0, f"{o.factor_id} rule_score 越界"

    def test_confidence_within_range(self):
        for o in compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward"):
            assert 0.0 <= o.confidence <= 1.0

    def test_engine_version_points_to_ziwei_engine(self):
        for o in compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward"):
            assert o.engine_version == settings.ziwei_engine_version
            assert "iztro" in o.engine_version

    def test_rule_version_carries_variant_suffix(self):
        fwd_obs = compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward")
        rev_obs = compute_ziwei_factors(rev(), AS_OF, stock_code="X", variant="reverse")
        assert {o.rule_version for o in fwd_obs} == {"zv1.fwd"}
        assert {o.rule_version for o in rev_obs} == {"zv1.rev"}
        assert ziwei_rule_version("forward") != ziwei_rule_version("reverse")

    def test_explanations_never_assert_price_direction(self):
        for o in compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward"):
            for bad in FORBIDDEN_ASSERTIONS:
                assert bad not in o.explanation, f"{o.factor_id} 解释含违规断言 {bad!r}"

    def test_reproducible(self):
        a = compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward")
        b = compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward")
        da = [o.model_dump(mode="json", exclude={"computed_at"}) for o in a]
        db = [o.model_dump(mode="json", exclude={"computed_at"}) for o in b]
        assert da == db

    def test_output_sorted_by_factor_id(self):
        obs = compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward")
        assert [o.factor_id for o in obs] == sorted(o.factor_id for o in obs)

    def test_no_negative_zero(self):
        """-0.0 会在序列化/比较中制造假差异，必须归一成 0.0。"""
        for o in compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward"):
            if o.normalized_value is not None:
                assert str(o.normalized_value) != "-0.0", o.factor_id

    def test_missing_palace_makes_whole_set_unavailable(self):
        """盘面结构被破坏时，**整组**因子必须是 unavailable，而不是 0 分。

        为什么是整组而不是"只影响涉及该宫的因子"：
        紫微的计算全部建立在"index 即坐标"上。宫数不对或 index 错位时，
        其余因子虽然能算出数字，但那个数字对应的宫位已经错了 ——
        一个"看起来正常但坐标错位"的结果，比明确的 unavailable 危险得多。
        """
        chart = fwd().model_copy(deep=True)
        chart.palaces = [p for p in chart.palaces if p.name != "财帛"]
        obs = compute_ziwei_factors(chart, AS_OF, stock_code="X", variant="forward")
        assert len(obs) == len(ALL_ZIWEI_DEFINITIONS)
        for o in obs:
            assert o.availability == "unavailable", o.factor_id
            assert o.normalized_value is None, o.factor_id
            assert o.rule_score == 0.0, o.factor_id
            assert o.warnings, o.factor_id
            assert "结构非法" in o.explanation

    def test_index_misalignment_makes_whole_set_unavailable(self):
        """index 与位置错位（坐标契约被破坏）同样必须整组 unavailable。"""
        chart = fwd().model_copy(deep=True)
        chart.palaces[3].index = 7
        obs = compute_ziwei_factors(chart, AS_OF, stock_code="X", variant="forward")
        assert all(o.availability == "unavailable" for o in obs)
        assert all("坐标系契约" in o.explanation for o in obs)

    def test_missing_soul_palace_trine_yields_unavailable(self):
        chart = fwd().model_copy(deep=True)
        chart.soul_palace_index = -1
        obs = {o.factor_id: o for o in compute_ziwei_factors(
            chart, AS_OF, stock_code="X", variant="forward",
        )}
        assert obs["Z_TRINE_001"].availability == "unavailable"

    def test_variant_mismatch_guard(self):
        with pytest.raises(ValueError) as exc:
            compute_ziwei_factors(fwd(), AS_OF, variant="reverse")
        assert "variant" in str(exc.value)
        assert "ADR-0010" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. variant 影响范围（ADR-0010 的机器校验）
# ---------------------------------------------------------------------------


class TestVariantImpactIsBounded:
    """只有声明为 variant-sensitive 的因子才允许随 variant 变化。

    这是一条**强不变量**：如果未来某次改动让别的因子也跟着变，
    说明有人在盘面之外引入了方向依赖 —— 那会让"两套 variant"变成
    "两套互不相干的模型"，研究结论将无法解释。
    """

    def test_only_declared_factors_differ_between_variants(self):
        fwd_obs = {o.factor_id: o for o in compute_ziwei_factors(
            fwd(), AS_OF, stock_code="X", variant="forward")}
        rev_obs = {o.factor_id: o for o in compute_ziwei_factors(
            rev(), AS_OF, stock_code="X", variant="reverse")}

        differ = {
            fid for fid in fwd_obs
            if fwd_obs[fid].normalized_value != rev_obs[fid].normalized_value
        }
        undeclared = differ - set(VARIANT_SENSITIVE_FACTOR_IDS)
        assert not undeclared, (
            f"以下因子随 variant 变化但未声明为 variant-sensitive：{sorted(undeclared)}。"
            "variant 只影响大限/小限顺逆与长生十二神顺逆（见 calculation-differences D4）。"
        )

    def test_declared_variant_sensitive_factors_are_tagged(self):
        for fid in VARIANT_SENSITIVE_FACTOR_IDS:
            d = ZIWEI_DEFINITION_INDEX[fid]
            assert "variant敏感" in d.tags, f"{fid} 未在 tags 中标注 variant敏感"
            assert "variant" in d.definition or "随 variant" in d.definition

    def test_non_variant_factors_are_stable(self):
        """至少要有相当数量的因子在两个 variant 间保持一致 —— 否则"两套盘"退化为两个模型。"""
        fwd_obs = {o.factor_id: o for o in compute_ziwei_factors(
            fwd(), AS_OF, stock_code="X", variant="forward")}
        rev_obs = {o.factor_id: o for o in compute_ziwei_factors(
            rev(), AS_OF, stock_code="X", variant="reverse")}
        same = sum(1 for fid in fwd_obs
                   if fwd_obs[fid].normalized_value == rev_obs[fid].normalized_value)
        assert same >= len(fwd_obs) - len(VARIANT_SENSITIVE_FACTOR_IDS) - 2, (
            "variant 之间的差异超出了声明的范围"
        )


# ---------------------------------------------------------------------------
# 4. 方向语义
# ---------------------------------------------------------------------------


class TestDirectionSemantics:
    def test_count_and_index_factors_are_neutral(self):
        """数量型 / 结构编码型因子的 direction 必须为中性的传统纪律。"""
        neutral_expected = {
            "Z_LIFE_002", "Z_LIFE_006", "Z_LIFE_007",
            "Z_FIN_002", "Z_CAREER_002",
            "Z_TRINE_005",
            "Z_YEAR_001", "Z_YEAR_004", "Z_YEAR_005", "Z_YEAR_006",
            "Z_MONTH_001", "Z_MONTH_004", "Z_MONTH_005",
            "Z_DAY_001", "Z_DAY_004", "Z_DAY_005",
        }
        for fid in neutral_expected:
            assert ZIWEI_DEFINITION_INDEX[fid].default_direction == Direction.NEUTRAL, fid

    def test_malefic_factors_are_negative_and_lucky_positive(self):
        for fid in ("Z_LIFE_004", "Z_FIN_003", "Z_CAREER_003", "Z_MOVE_002",
                    "Z_TRINE_003", "Z_YEAR_003", "Z_MONTH_003", "Z_DAY_003",
                    "Z_DECADE_002", "Z_AGE_002", "Z_MUTAGEN_006", "Z_MUTAGEN_004"):
            assert ZIWEI_DEFINITION_INDEX[fid].default_direction == Direction.NEGATIVE, fid
        for fid in ("Z_LIFE_003", "Z_LIFE_005", "Z_TRINE_002", "Z_TRINE_004",
                    "Z_MUTAGEN_001", "Z_MUTAGEN_005", "Z_FIN_004"):
            assert ZIWEI_DEFINITION_INDEX[fid].default_direction == Direction.POSITIVE, fid

    def test_observation_direction_matches_definition(self):
        for o in compute_ziwei_factors(fwd(), AS_OF, stock_code="X", variant="forward"):
            expected = ZIWEI_DEFINITION_INDEX[o.factor_id].default_direction
            assert int(o.direction) == int(expected), f"{o.factor_id} direction 与定义不一致"


# ---------------------------------------------------------------------------
# 5. 质量审计（activation / null / 区分度）
# ---------------------------------------------------------------------------


class TestZiweiFactorQuality:
    """紫微因子质量审计（口径见 src/factors/ziwei/audit.py）。

    样本覆盖两个维度，否则区分度结论是假的：
      * **横截面**：不同出生时刻 → 不同命宫/星曜结构；
      * **时间截面**：同一只股票在不同 as_of → 不同流年/流月/流日。
    """

    SAMPLE_CHARTS = [
        "600519-listing-forward", "000001-listing-forward", "300750-listing-forward",
        "2024-lichun-zishi", "1999-late-zishi", "2016-choushi", "2020-haishi",
        "600519-listing-reverse",
    ]
    SAMPLE_DATES = [
        datetime(2024, 11, 15, 14, 32),
        datetime(2025, 3, 20, 14, 32),
        datetime(2023, 7, 7, 14, 32),
    ]

    def _rows(self) -> list[dict]:
        rows: list[dict] = []
        for name in self.SAMPLE_CHARTS:
            chart = load(name)
            variant = str(chart.variant_mode)
            for as_of in self.SAMPLE_DATES:
                for o in compute_ziwei_factors(chart, as_of, stock_code=name, variant=variant):
                    rows.append({
                        "factor_id": o.factor_id,
                        "normalized_value": o.normalized_value,
                        "direction": int(o.direction),
                        "availability": o.availability,
                    })
        return rows

    def _audit(self):  # type: ignore[no-untyped-def]
        from src.factors.ziwei.audit import audit_many

        return audit_many(self._rows())

    def test_audit_reports_every_factor(self):
        assert {a.factor_id for a in self._audit()} == set(ZIWEI_DEFINITION_INDEX)

    def test_sample_size_per_factor(self):
        expected = len(self.SAMPLE_CHARTS) * len(self.SAMPLE_DATES)
        for a in self._audit():
            assert a.sample_count == expected, a.factor_id

    def test_null_rate_is_zero_on_complete_charts(self):
        for a in self._audit():
            assert a.null_rate == 0.0, f"{a.factor_id} 在完整盘面上出现空值"

    def test_metrics_are_populated(self):
        """审计必须给出任务书列出的全部指标，不能只给一部分。"""
        for a in self._audit():
            d = a.as_dict()
            for key in ("sample_count", "null_rate", "activation_rate",
                        "unique_value_count", "direction_distribution", "mean", "std"):
                assert key in d, f"{a.factor_id} 缺少指标 {key}"
            assert a.mean is not None and a.std is not None
            assert sum(a.direction_distribution.values()) == a.sample_count

    def test_continuous_factors_are_not_misflagged_by_activation(self):
        """连续型因子取值几乎永不落在 0 上，**不得**用 activation_rate 判其低区分度。

        这是 Phase 2 审计口徑与 Phase 1 的关键差异（见 audit.py 模块文档）。
        """
        for a in self._audit():
            if a.kind != "continuous":
                continue
            if "LOW_DISCRIMINATION_FACTOR" in a.flags:
                assert a.std == 0.0, (
                    f"{a.factor_id} 是连续型因子且 std={a.std}，"
                    "却被标记 LOW_DISCRIMINATION —— 审计口径错误"
                )

    def test_constant_factors_are_few_and_disclosed(self):
        """恒定因子必须被识别，且数量有上界。

        恒定本身是**如实结果**（例如 `Z_YEAR_001` 流年命宫位阶只由年份决定，
        横向不携带个股信息），不是缺陷；隐瞒才是缺陷。
        """
        audit = self._audit()
        constant = [a for a in audit if "CONSTANT_FACTOR" in a.flags]
        assert len(constant) / len(audit) <= 0.15, (
            f"{len(constant)}/{len(audit)} 个因子恒定：{[a.factor_id for a in constant]}"
        )

    def test_low_discrimination_flags_are_actionable(self):
        """被标记的因子必须带可读指标，能直接写进质量报告。"""
        for a in self._audit():
            if a.flags:
                assert a.sample_count > 0 and a.activation_rate is not None
                assert a.factor_id in ZIWEI_DEFINITION_INDEX

    def test_duplicate_detection_runs(self):
        """相关性 > 0.98 必须被识别为疑似重复（可能合法，但必须披露）。"""
        from src.factors.ziwei.audit import pairwise_correlations

        rows = self._rows()
        series: dict[str, list[float | None]] = {}
        for r in rows:
            series.setdefault(r["factor_id"], []).append(r["normalized_value"])
        pairs = pairwise_correlations(series)
        for p in pairs:
            assert abs(p["pearson"]) > 0.98
            assert p["a"] != p["b"]
        # 结果本身可以为空（没有重复是好事），但函数必须能跑通并返回结构正确的列表
        assert isinstance(pairs, list)
