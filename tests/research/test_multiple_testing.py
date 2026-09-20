"""Phase 3F · 多重检验 / 置换 / bootstrap / gate-v2 测试。

最重要的一条回归：**日期分层置换必须能识破"日期选择器"**
------------------------------------------------------------------
Phase 3D 实测发现黄历事件集合近似"挑选日期"。若置换在全池随机抽同样数量的位置，
就会把"日期构成差异"误当成"股票选择能力"，从而给出虚假的显著。
本文件用构造数据验证：一个纯粹的日期选择器事件集合在日期分层置换下**不显著**，
而在朴素的池化置换下会显著 —— 这就是必须分层的实证理由。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.multipletesting.families import (
    FamilyContractError,
    FamilyRegistry,
    FamilySpec,
    load_family_registry,
)
from src.research.multipletesting.fdr import (
    apply_family_correction,
    benjamini_hochberg,
)
from src.research.multipletesting.gate_v2 import (
    GATE_V2_VERSION,
    evaluate_gate_v2,
    gate_v2_thresholds,
)
from src.research.multipletesting.resample import (
    date_block_bootstrap,
    permutation_test,
)
from src.research.multipletesting.robustness import (
    ROBUSTNESS_DIMENSION_UNAVAILABLE,
    compute_market_regimes,
    consecutive_window_overlap,
    evaluate_dimensions,
)
from src.research.status import ResearchStatus

FAMILY_CONFIG = "config/phase3f_multiple_testing_families.yaml"


# ---------------------------------------------------------------------------
# BH-FDR
# ---------------------------------------------------------------------------


def _bh_reference(p_values: list[float], alpha: float) -> list[float]:
    """独立参考实现（朴素 O(m²)）—— 用来交叉验证被广泛使用的 step-up 公式。"""
    m = len(p_values)
    out: list[float] = []
    for value in p_values:
        candidates = [
            m * other / rank
            for rank, other in enumerate(sorted(p_values), start=1)
            if other >= value
        ]
        out.append(min(1.0, min(candidates)))
    return out


def test_benjamini_hochberg_matches_reference_implementation() -> None:
    rng = np.random.default_rng(3)
    for _trial in range(20):
        values = sorted(rng.uniform(0.0001, 1.0, 12).tolist())
        rng.shuffle(values)
        got = benjamini_hochberg(values, 0.05)
        expected = _bh_reference(values, 0.05)
        for left, right in zip(got, expected, strict=True):
            assert left == pytest.approx(right, abs=1e-12)


def test_benjamini_hochberg_is_monotone_and_bounded() -> None:
    values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216,
              0.222, 0.251, 0.269, 0.275, 0.34]
    q_values = benjamini_hochberg(values, 0.05)
    assert all(0.0 <= value <= 1.0 for value in q_values if value is not None)
    ordered = [value for _p, value in sorted(zip(values, q_values, strict=True))]
    assert all(
        ordered[index] <= ordered[index + 1] + 1e-12 for index in range(len(ordered) - 1)
    ), "q 值必须随 p 单调不减（step-up 单调化）"


def test_benjamini_hochberg_classic_example_rejects_four() -> None:
    """BH 1995 的经典例子：α=0.05 时恰好拒绝 4 个假设。"""
    values = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344, 0.0459,
              0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.0000]
    q_values = benjamini_hochberg(values, 0.05)
    assert sum(1 for value in q_values if value is not None and value <= 0.05) == 4
    assert q_values[0] == pytest.approx(0.0015, abs=1e-9)


def test_benjamini_hochberg_rejects_bad_alpha() -> None:
    with pytest.raises(ValueError):
        benjamini_hochberg([0.01], 0.0)
    with pytest.raises(ValueError):
        benjamini_hochberg([0.01], 1.0)


def test_apply_family_correction_reports_all_four_numbers() -> None:
    rows = [
        {"hypothesis_id": "A", "raw_p_value": 0.001},
        {"hypothesis_id": "B", "raw_p_value": 0.02},
        {"hypothesis_id": "C", "raw_p_value": 0.5},
        {"hypothesis_id": "D", "raw_p_value": None},
    ]
    result = apply_family_correction(rows, family_id="fam", alpha=0.05, mt_version="mt-v1")
    assert result.evaluable_count == 3
    assert result.missing_count == 1
    assert result.rows[0]["bonferroni_threshold"] == pytest.approx(0.05 / 3)
    assert result.rows[3]["fdr_q_value"] is None
    assert result.rows[3]["raw_p_value_missing"] is True
    assert all(row["family_id"] == "fam" for row in result.rows)
    # 原始 p 不得被改写
    assert [row["raw_p_value"] for row in result.rows] == [0.001, 0.02, 0.5, None]


def test_apply_family_correction_does_not_mutate_input() -> None:
    rows = [{"hypothesis_id": "A", "raw_p_value": 0.01}]
    apply_family_correction(rows, family_id="fam", alpha=0.05)
    assert "fdr_q_value" not in rows[0]


# ---------------------------------------------------------------------------
# 假设族
# ---------------------------------------------------------------------------


def test_frozen_family_config_covers_every_hypothesis() -> None:
    """真实的冻结配置必须覆盖 3D 注册表的全部 18 个假设（无遗漏、无重复）。"""
    from src.research.oos.registry import load_hypothesis_registry

    families = load_family_registry(FAMILY_CONFIG)
    hypotheses = load_hypothesis_registry("config/phase3d_hypothesis_registry.yaml")
    families.validate_against(tuple(hypotheses.ids()))
    assert families.mt_version == "mt-v1"
    assert families.final_results_seen_at_freeze is False
    assert set(family.family_id for family in families.families) == {
        "bazi", "ziwei", "huangli", "consensus", "conflict", "birth_model_comparison",
    }
    assert families.by_id("conflict").gated is False
    assert families.by_id("conflict").tails == "two_sided"


def test_family_registry_rejects_duplicate_membership() -> None:
    registry = FamilyRegistry(
        mt_version="mt-v1", frozen_at="2026-09-20", final_results_seen_at_freeze=False,
        alpha=0.05,
        families=(
            FamilySpec(family_id="a", description="", gated=True, tails="one_sided",
                       hypothesis_ids=("H1",)),
            FamilySpec(family_id="b", description="", gated=True, tails="one_sided",
                       hypothesis_ids=("H1",)),
        ),
    )
    with pytest.raises(FamilyContractError, match="归属族数量"):
        registry.family_of("H1")


def test_family_registry_rejects_unassigned_hypothesis() -> None:
    registry = FamilyRegistry(
        mt_version="mt-v1", frozen_at="2026-09-20", final_results_seen_at_freeze=False,
        alpha=0.05,
        families=(
            FamilySpec(family_id="a", description="", gated=True, tails="one_sided",
                       hypothesis_ids=("H1",)),
        ),
    )
    with pytest.raises(FamilyContractError, match="没有归属任何族"):
        registry.validate_against(("H1", "H2"))


def test_family_registry_rejects_unknown_hypothesis_reference() -> None:
    registry = FamilyRegistry(
        mt_version="mt-v1", frozen_at="2026-09-20", final_results_seen_at_freeze=False,
        alpha=0.05,
        families=(
            FamilySpec(family_id="a", description="", gated=True, tails="one_sided",
                       hypothesis_ids=("H9",)),
        ),
    )
    with pytest.raises(FamilyContractError, match="未注册的假设"):
        registry.validate_against(("H1",))


# ---------------------------------------------------------------------------
# 置换检验
# ---------------------------------------------------------------------------


def _date_selector_frame(
    *,
    hit_dates: tuple[int, ...],
    date_count: int = 10,
    stocks: int = 60,
    hit_fraction: float = 0.9,
) -> pd.DataFrame:
    """构造"日期选择器"：命中与否基本由日期决定。

    ``hit_fraction=1.0`` 即纯选择器（某些日期全命中、其余全不命中）。
    ``hit_fraction<1`` 保留少量横截面变化，但**日内**命中组与未命中组的
    收益分布完全相同 —— 因此日内没有任何真实信息。
    """
    rows = []
    for day_index in range(date_count):
        # 命中日的市场整体更好 → 池化置换会误判为"有选股能力"
        drift = 0.02 if day_index in hit_dates else -0.02
        cut = int(round(stocks * hit_fraction))
        for stock_index in range(stocks):
            hit = (day_index in hit_dates) and stock_index < cut
            if day_index not in hit_dates:
                hit = stock_index >= stocks - (stocks - cut) and cut < stocks
            rows.append({
                "as_of": date(2023, 1 + day_index, 3),
                "stock_code": f"{stock_index:06d}",
                "hit": bool(hit),
                "market_excess_return_20d": drift + 0.001 * (stock_index % 7),
            })
    return pd.DataFrame(rows)


def _pooled_permutation_p(frame: pd.DataFrame, draws: int, seed: int = 7) -> float:
    """朴素池化置换（**错误**口径，仅用于对比）：在全池随机抽同样数量的行。

    这段参考实现故意写在测试里，用来证明"分层 vs 不分层"确实会给出不同结论。
    """
    values = frame["market_excess_return_20d"].to_numpy(dtype=float)
    hits = frame["hit"].to_numpy(dtype=bool)
    observed = float(values[hits].mean() - values[~hits].mean())
    rng = np.random.default_rng(seed)
    total = int(hits.sum())
    count = 0
    for _draw in range(draws):
        picked = rng.choice(len(values), size=total, replace=False)
        mask = np.zeros(len(values), dtype=bool)
        mask[picked] = True
        statistic = float(values[mask].mean() - values[~mask].mean())
        if statistic >= observed:
            count += 1
    return (count + 1) / (draws + 1)


def test_date_stratified_permutation_does_not_flag_a_date_selector() -> None:
    """核心回归：日期选择器在**分层**置换下不显著，而在**池化**置换下显著。

    这正是 Phase 3D 黄历结论的方法学根源：不保留每日命中数量的对照
    会把"日期构成差异"当成"选股能力"。
    """
    frame = _date_selector_frame(hit_dates=(0, 1), hit_fraction=0.9)
    result = permutation_test(
        frame, "hit", "market_excess_return_20d", permutation_count=400, seed=7,
    )
    # 同一日期内命中与未命中的收益分布几乎相同 → 统计量 ~0（远小于 0.02 的日期间漂移）
    assert abs(result.statistic) < 1e-3
    assert result.p_value_upper > 0.1
    assert result.p_value_two_sided > 0.1
    # 池化口径（错误做法）会给出显著
    pooled_p = _pooled_permutation_p(frame, draws=400)
    assert pooled_p < 0.05, "池化置换确实会误判 —— 这就是必须分层的原因"


def test_pure_date_selector_has_no_within_date_information() -> None:
    """100% / 0% 命中的纯选择器：日内没有任何命中与未命中的对照，
    统计量必须被判为"不可判定"（None），而不是 0 或显著。"""
    frame = _date_selector_frame(hit_dates=(0, 1), hit_fraction=1.0)
    result = permutation_test(
        frame, "hit", "market_excess_return_20d", permutation_count=100, seed=7,
    )
    assert result.statistic is None
    assert result.p_value_upper is None
    assert result.permutation_count == 0


def test_permutation_detects_a_genuine_within_date_effect() -> None:
    """同一日期内命中股确实更好时，置换必须能识别。"""
    rng = np.random.default_rng(11)
    rows = []
    for day_index in range(10):
        for stock_index in range(60):
            hit = stock_index % 2 == 0
            rows.append({
                "as_of": date(2023, 1 + day_index, 3),
                "stock_code": f"{stock_index:06d}",
                "hit": hit,
                "market_excess_return_20d": (0.03 if hit else 0.0) + rng.normal(0, 0.01),
            })
    frame = pd.DataFrame(rows)
    result = permutation_test(frame, "hit", "market_excess_return_20d", permutation_count=400, seed=5)
    assert result.statistic > 0.02
    assert result.p_value_upper < 0.01
    assert result.p_value_lower > 0.9


def test_permutation_preserves_per_date_hit_counts() -> None:
    """置换必须严格保留每个日期的命中数量（这正是分层的意思）。"""
    frame = _date_selector_frame(
        hit_dates=(0, 1), date_count=6, stocks=20, hit_fraction=0.75,
    )
    result = permutation_test(frame, "hit", "market_excess_return_20d", permutation_count=50, seed=1)
    assert result.permutation_count == 50
    assert result.date_count == 6
    # 2 个命中日期 × 15 只 + 4 个非命中日期 × 5 只
    assert result.event_count == 2 * 15 + 4 * 5


def test_permutation_is_reproducible_with_same_seed() -> None:
    frame = _date_selector_frame(
        hit_dates=(0, 1), date_count=6, stocks=20, hit_fraction=0.75,
    )
    first = permutation_test(frame, "hit", "market_excess_return_20d", permutation_count=100, seed=42)
    second = permutation_test(frame, "hit", "market_excess_return_20d", permutation_count=100, seed=42)
    assert first.to_dict() == second.to_dict()


def test_permutation_rejects_bad_draw_count() -> None:
    with pytest.raises(ValueError):
        permutation_test(pd.DataFrame(), "hit", "y", permutation_count=0)


def test_permutation_returns_none_on_degenerate_input() -> None:
    frame = pd.DataFrame({
        "as_of": [date(2023, 1, 3)] * 6,
        "hit": [True, True, True, False, False, False],
        "value": [0.1] * 6,
    })
    result = permutation_test(frame, "hit", "value", permutation_count=50, seed=1)
    # 命中与未命中的值相同 → 统计量 0，但仍是可判定的
    assert result.statistic == pytest.approx(0.0, abs=1e-12)

    empty = permutation_test(pd.DataFrame(), "hit", "value", permutation_count=50, seed=1)
    assert empty.p_value_upper is None
    assert empty.permutation_count == 0


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


def test_bootstrap_ci_covers_point_estimate() -> None:
    rng = np.random.default_rng(23)
    rows = []
    for day_index in range(20):
        for stock_index in range(30):
            rows.append({
                "as_of": date(2023, 1 + day_index % 12, 3 + day_index // 12),
                "stock_code": f"{stock_index:06d}",
                "value": rng.normal(0.0, 0.05),
            })
    frame = pd.DataFrame(rows)
    result = date_block_bootstrap(frame, "value", bootstrap_count=500, seed=9)
    assert result.ci_lower <= result.point_estimate <= result.ci_upper
    assert result.date_count == 20
    assert result.crosses_zero is True


def test_bootstrap_difference_matches_manual_point_estimate() -> None:
    frame = pd.DataFrame({
        "as_of": [date(2023, 1, 3)] * 4 + [date(2023, 2, 3)] * 4,
        "hit": [True, True, False, False] * 2,
        "value": [0.10, 0.10, 0.00, 0.00, 0.04, 0.04, 0.00, 0.00],
    })
    result = date_block_bootstrap(
        frame, "value", statistic="difference", hit_col="hit", bootstrap_count=200, seed=3,
    )
    assert result.point_estimate == pytest.approx(0.07, abs=1e-9)
    assert result.ci_lower is not None and result.ci_upper is not None
    assert result.ci_lower <= 0.07 <= result.ci_upper


def test_bootstrap_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        date_block_bootstrap(pd.DataFrame({"value": [1.0], "as_of": [date(2023, 1, 1)]}),
                             "value", confidence=1.5)


def test_bootstrap_needs_hit_col_for_difference() -> None:
    frame = pd.DataFrame({"as_of": [date(2023, 1, 3)], "value": [0.1]})
    with pytest.raises(ValueError):
        date_block_bootstrap(frame, "value", statistic="difference")


# ---------------------------------------------------------------------------
# 稳健性
# ---------------------------------------------------------------------------


def test_market_regime_uses_only_past_benchmark_prices() -> None:
    """市场状态只能由 as_of 当日及之前的基准价格决定。"""
    from datetime import timedelta

    days = [date(2023, 1, 2) + timedelta(days=index) for index in range(200)]
    closes = [100.0 + index for index in range(200)]  # 单调上涨
    regimes = compute_market_regimes([days[100], days[150]], tuple(days), tuple(closes), window=60)
    assert regimes[days[100]] == "up"
    assert regimes[days[150]] == "up"
    # 历史不足窗口的日期不产生标签
    early = compute_market_regimes([days[10]], tuple(days), tuple(closes), window=60)
    assert early == {}


def test_consecutive_window_overlap_detects_quarterly_grid() -> None:
    """季度网格对 20D 持有期不重叠；日频网格必然重叠。"""
    from datetime import timedelta

    calendar = tuple(date(2023, 1, 2) + timedelta(days=index) for index in range(400))
    quarterly = pd.DataFrame({
        "as_of": [calendar[0], calendar[63], calendar[126]], "hit": [True] * 3,
    })
    result = consecutive_window_overlap(quarterly, calendar_dates=calendar, horizon=20)
    assert result["overlap_ratio"] == 0.0

    daily = pd.DataFrame({"as_of": list(calendar[:5]), "hit": [True] * 5})
    result_daily = consecutive_window_overlap(daily, calendar_dates=calendar, horizon=20)
    assert result_daily["overlap_ratio"] == 1.0


def test_robustness_dimensions_mark_unavailable_explicitly() -> None:
    """测不了的维度必须显式标记，不能静默省略成"通过"。"""
    frame = pd.DataFrame({
        "as_of": [date(2023, 1, 3)] * 80 + [date(2024, 1, 3)] * 80,
        "stock_code": [f"{index:06d}" for index in range(160)],
        "hit": [True] * 40 + [False] * 40 + [True] * 40 + [False] * 40,
        "market_excess_return_20d": [0.01] * 160,
    })
    results = evaluate_dimensions(frame, calendar_dates=None)
    by_dimension = {item.dimension: item for item in results}
    assert by_dimension["segment"].status == ROBUSTNESS_DIMENSION_UNAVAILABLE
    assert by_dimension["universe_subset"].status == ROBUSTNESS_DIMENSION_UNAVAILABLE
    assert by_dimension["market_regime"].status == ROBUSTNESS_DIMENSION_UNAVAILABLE
    assert by_dimension["adj_snapshot"].status == ROBUSTNESS_DIMENSION_UNAVAILABLE
    assert by_dimension["non_overlapping"].status == ROBUSTNESS_DIMENSION_UNAVAILABLE
    # year 维度是可判定的
    assert by_dimension["year"].status == "OK"
    assert by_dimension["year"].sign_agreement == 1.0


def test_robustness_sign_agreement_marks_instability() -> None:
    rows = []
    for year_index, sign in enumerate((1, -1, 1, -1)):
        for stock_index in range(80):
            rows.append({
                "as_of": date(2020 + year_index, 6, 1),
                "stock_code": f"{stock_index:06d}",
                "hit": stock_index < 40,
                "market_excess_return_20d": 0.01 * sign,
            })
    frame = pd.DataFrame(rows)
    results = evaluate_dimensions(frame, calendar_dates=None)
    year = next(item for item in results if item.dimension == "year")
    assert year.status == "OK"
    assert year.sign_agreement == pytest.approx(0.5, abs=1e-9)
    assert year.stable is False


# ---------------------------------------------------------------------------
# gate-v2
# ---------------------------------------------------------------------------


def _gate_kwargs(**overrides) -> dict:  # type: ignore[no-untyped-def]
    """一份"全部条件都通过"的基准输入，便于逐项破坏后验证 gate 反应。"""
    base: dict = {
        "experiment_id": "MT3F--H--m",
        "oos_stats": {
            "event_count": 500, "sample_count": 480,
            "mean_market_excess_return": 0.05, "cohen_d": 0.20,
        },
        "validation_stats": {"event_count": 300, "mean_market_excess_return": 0.04},
        "controls": [
            {"kind": "random_event_position", "mean_excess_return": 0.00,
             "jaccard_with_real": 0.10, "decisive": True},
            {"kind": "random_birth_assignment", "mean_excess_return": 0.005,
             "jaccard_with_real": None, "decisive": True},
        ],
        "year_stability": {"year_count": 4, "positive_year_ratio": 0.75,
                            "sign_consistency": 1.0},
        "stock_dependency": {"top_1_contribution": 0.10, "loo_sign_flip_count": 0},
        "calibration_audit": {"fit_max_as_of": "2018-10-01", "fit_scope": "TRAIN_ONLY",
                               "calibration_fit_hash": "abc"},
        "multiple_testing": {"family_id": "bazi", "family_test_count": 6,
                              "raw_p_value": 0.002, "fdr_q_value": 0.01, "fdr_pass": True},
        "bootstrap": {"point_estimate": 0.05, "ci_lower": 0.01, "ci_upper": 0.09,
                       "crosses_zero": False},
        "permutation": {"p_value_upper": 0.003, "permutation_count": 5000,
                         "permutation_seed": 1},
        "neutralization": {"hit_date_mean_market_excess": 0.05,
                            "style_neutral_hit_mean": 0.04,
                            "segment_neutral_hit_mean": 0.045,
                            "segment_available": True},
        "horizon": 20,
        "is_gated": True,
        "data_is_real": True,
        "gate_v1_status": "OOS_CANDIDATE_SUPPORTED",
    }
    base.update(overrides)
    return base


def test_gate_v2_all_conditions_pass_unlocks_supported_out_of_sample() -> None:
    result = evaluate_gate_v2(**_gate_kwargs())
    assert result.status == ResearchStatus.SUPPORTED_OUT_OF_SAMPLE
    assert result.gate_version == GATE_V2_VERSION
    assert result.fdr_applied is True
    assert result.pending_fdr is False
    assert not [item for item in result.checks if item.blocking and not item.passed]


def test_gate_v2_all_thresholds_are_frozen_and_reported() -> None:
    thresholds = gate_v2_thresholds()
    assert thresholds["alpha"] == 0.05
    assert thresholds["min_permutation_count"] == 1000
    assert thresholds["bootstrap_confidence"] == 0.95
    assert thresholds["min_mean_meaningful_effect"] == 0.02
    assert thresholds["max_status_phase3f"] == "SUPPORTED_OUT_OF_SAMPLE"


@pytest.mark.parametrize(
    ("override", "expected_name"),
    [
        ({"oos_stats": {"event_count": 50, "sample_count": 40,
                        "mean_market_excess_return": 0.05, "cohen_d": 0.2}},
         "A_oos_event_count"),
        ({"multiple_testing": {"family_id": "bazi", "family_test_count": 6,
                               "raw_p_value": 0.02, "fdr_q_value": 0.4, "fdr_pass": False}},
         "F_fdr_pass"),
        ({"bootstrap": {"point_estimate": 0.05, "ci_lower": -0.01, "ci_upper": 0.09,
                        "crosses_zero": True}}, "G_bootstrap_ci_excludes_zero"),
        ({"permutation": {"p_value_upper": 0.20, "permutation_count": 5000,
                          "permutation_seed": 1}}, "H_date_stratified_permutation"),
        ({"year_stability": {"year_count": 4, "positive_year_ratio": 0.25,
                             "sign_consistency": 0.5}}, "I_year_stability"),
        ({"stock_dependency": {"top_1_contribution": 0.9, "loo_sign_flip_count": 3}},
         "J_not_single_name_driven"),
        ({"neutralization": {"hit_date_mean_market_excess": 0.05,
                             "style_neutral_hit_mean": 0.001,
                             "segment_neutral_hit_mean": 0.045,
                             "segment_available": True}},
         "K_not_style_or_segment_driven"),
        ({"data_is_real": False}, "L_data_quality_clean"),
        ({"oos_stats": {"event_count": 500, "sample_count": 480,
                        "mean_market_excess_return": 0.005, "cohen_d": 0.005}},
         "E_effect_size_nonzero_and_meaningful"),
    ],
)
def test_gate_v2_refuses_to_unlock_when_any_condition_fails(
    override: dict, expected_name: str,
) -> None:
    """只要任一关键条件失败，就绝不能解锁 SUPPORTED_OUT_OF_SAMPLE。"""
    result = evaluate_gate_v2(**_gate_kwargs(**override))
    assert result.status != ResearchStatus.SUPPORTED_OUT_OF_SAMPLE
    failed = {item.name for item in result.checks if item.blocking and not item.passed}
    assert expected_name in failed or expected_name.startswith("L") and not result.checks


def test_gate_v2_invalid_control_short_circuits_to_invalid_control() -> None:
    result = evaluate_gate_v2(**_gate_kwargs(controls=[
        {"kind": "shifted_birth_date_plus_7d", "mean_excess_return": 0.0,
         "jaccard_with_real": 0.95, "decisive": True},
    ]))
    assert result.status == ResearchStatus.INVALID_CONTROL


def test_gate_v2_no_signal_when_control_beats_real() -> None:
    result = evaluate_gate_v2(**_gate_kwargs(controls=[
        {"kind": "random_event_position", "mean_excess_return": 0.10,
         "jaccard_with_real": 0.1, "decisive": True},
    ]))
    assert result.status == ResearchStatus.NO_SIGNAL


def test_gate_v2_direction_mismatch_is_inconclusive() -> None:
    result = evaluate_gate_v2(**_gate_kwargs(
        validation_stats={"event_count": 300, "mean_market_excess_return": -0.04},
    ))
    assert result.status == ResearchStatus.INCONCLUSIVE


def test_gate_v2_never_unlocks_exploratory_hypotheses() -> None:
    """探索性（冲突）对象即使所有数值都漂亮也不能解锁。"""
    result = evaluate_gate_v2(**_gate_kwargs(is_gated=False))
    assert result.status == ResearchStatus.EXPLORATORY_NOT_GATED
    assert result.status != ResearchStatus.SUPPORTED_OUT_OF_SAMPLE
    assert result.pending_fdr is False


def test_gate_v2_keeps_gate_v1_status_for_side_by_side_reporting() -> None:
    """两版协议必须并排报告：v2 结果不得覆盖 v1 的原始状态。"""
    result = evaluate_gate_v2(**_gate_kwargs())
    payload = result.to_dict()
    assert payload["gate_v1_status"] == "OOS_CANDIDATE_SUPPORTED"
    assert payload["gate_version"] == GATE_V2_VERSION
