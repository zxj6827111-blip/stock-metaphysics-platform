"""Phase 3E · 黄历日期效应（P0 统计修正）与基准 / 行业可得性测试。

最重要的断言：**"日期选择器"结构不能被当成 N 个独立事件。**
构造一个"命中完全由日期决定"的数据集，验证：
* 有效样本量等于**日期数**，不是行数；
* 命中日 vs 非命中日的差异在日期层面度量；
* 当日命中比例（``hit_share``）作为连续度量被保留。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.neutralization.benchmark import (
    AVAILABLE_BENCHMARKS,
    BENCHMARK_SPLIT_UNAVAILABLE,
    attach_market_excess,
    benchmark_policy,
    market_neutral_summary,
)
from src.research.neutralization.date_effect import (
    DATE_EFFECT_VERSION,
    build_date_table,
    date_effect_analysis,
)
from src.research.neutralization.industry import (
    INDUSTRY_CLASSIFICATION_UNAVAILABLE,
    POINT_IN_TIME_INDUSTRY_UNAVAILABLE,
    UnavailableIndustryProvider,
    attach_segment,
    segment_neutralize,
)


def _cross_section(
    *, date_count: int = 8, stocks_per_date: int = 30, hit_dates: tuple[int, ...] = (0, 1),
) -> pd.DataFrame:
    """构造"日期选择器"数据：某些日期几乎全体命中，其余日期几乎不命中。"""
    rows = []
    for day_index in range(date_count):
        is_hit_date = day_index in hit_dates
        for stock_index in range(stocks_per_date):
            hit = is_hit_date and stock_index < stocks_per_date - 2
            # 命中日的当日收益更高（制造一个真实的"日期效应"）
            raw = 0.02 if is_hit_date else -0.01
            rows.append({
                "as_of": date(2023, 1 + day_index, 2),
                "stock_code": f"{stock_index:06d}",
                "hit": hit,
                "raw_return_20d": raw,
                "benchmark_return_20d": 0.005,
                "market_excess_return_20d": raw - 0.005,
            })
    return pd.DataFrame(rows)


def test_date_table_folds_rows_into_dates() -> None:
    frame = _cross_section()
    table = build_date_table(frame, "hit", 20)
    assert len(table) == 8, "每个 as_of 一行"
    assert table["stock_count"].tolist() == [30] * 8
    assert table["hit_count"].tolist()[0] == 28
    assert table["hit_share"].iloc[1] == pytest.approx(28 / 30, abs=1e-6)
    assert table["hit_share"].iloc[2] == 0.0
    assert table["market_excess"].iloc[0] == pytest.approx(0.015, abs=1e-9)
    assert table["market_return"].iloc[0] == pytest.approx(0.005, abs=1e-9)


def test_date_effect_sample_size_is_dates_not_rows() -> None:
    """核心断言：事件行数 240，但有效样本量必须是 8 个日期。"""
    frame = _cross_section()
    effect = date_effect_analysis(frame, "hit", 20)
    assert effect["date_count"] == 8
    assert effect["event_row_count_vs_date_count"]["raw_row_count"] == 240
    assert effect["event_row_count_vs_date_count"]["dates"] == 8
    assert effect["stock_count_per_date"] == {"mean": 30.0, "min": 30, "max": 30}
    assert effect["date_clustered"]["date_count"] == 8


def test_date_effect_separates_hit_dates_from_others() -> None:
    frame = _cross_section(hit_dates=(0, 1))
    effect = date_effect_analysis(frame, "hit", 20)
    assert effect["hit_dates"]["date_count"] == 2
    assert effect["non_hit_dates"]["date_count"] == 6
    assert effect["hit_dates"]["market_excess_mean"] == pytest.approx(0.015, abs=1e-9)
    assert effect["non_hit_dates"]["market_excess_mean"] == pytest.approx(-0.015, abs=1e-9)
    assert effect["date_clustered_difference"]["difference"] == pytest.approx(0.03, abs=1e-9)
    # 两个日期的"组内"方差为 0 → Welch t 无定义，必须返回 None 而不是 inf
    assert effect["date_clustered_difference"]["welch_t"] is None
    assert effect["hit_share_slope"]["slope"] is not None


def test_date_effect_returns_empty_when_no_date_has_enough_stocks() -> None:
    frame = _cross_section(stocks_per_date=5)
    effect = date_effect_analysis(frame, "hit", 20, min_stocks=20)
    assert effect["date_count"] == 0
    assert effect["market_excess"] is None
    assert effect["date_effect_version"] == DATE_EFFECT_VERSION


def test_date_effect_slope_tracks_hit_share() -> None:
    """命中比例越高、当日超额越高 → 斜率必须为正。"""
    rows = []
    shares = [0.0, 0.25, 0.5, 0.75, 1.0]
    for day_index, share in enumerate(shares):
        for stock_index in range(40):
            hit = stock_index < int(round(share * 40))
            rows.append({
                "as_of": date(2023, 1 + day_index, 2),
                "stock_code": f"{stock_index:06d}",
                "hit": hit,
                "raw_return_20d": 0.01 * share,
                "benchmark_return_20d": 0.0,
                "market_excess_return_20d": 0.01 * share,
            })
    frame = pd.DataFrame(rows)
    effect = date_effect_analysis(frame, "hit", 20)
    assert effect["hit_share_slope"]["slope"] == pytest.approx(0.01, abs=1e-6)
    assert effect["hit_share_slope"]["t"] > 0


# ---------------------------------------------------------------------------
# 基准
# ---------------------------------------------------------------------------


def test_benchmark_policy_declares_split_mapping_unavailable() -> None:
    policy = benchmark_policy()
    assert policy.status == BENCHMARK_SPLIT_UNAVAILABLE
    assert policy.is_split_mapped is False
    assert policy.benchmark_code == "IDX000300"
    assert "IDX000905" in policy.required_for_split_mapping
    assert "IDX000905" not in AVAILABLE_BENCHMARKS
    assert policy.to_dict()["split_mapping_available"] is False


def test_attach_market_excess_keeps_raw_columns() -> None:
    frame = pd.DataFrame({
        "ret_20d": [0.10, 0.20],
        "bench_ret_20d": [0.02, 0.03],
        "excess_return_20d": [0.08, 0.17],
    })
    out = attach_market_excess(frame, horizons=(20,))
    assert out["raw_return_20d"].tolist() == [0.10, 0.20]
    assert out["benchmark_return_20d"].tolist() == [0.02, 0.03]
    assert out["market_excess_return_20d"].tolist() == pytest.approx([0.08, 0.17])
    # 原始标签列不得被改名或覆盖
    assert "ret_20d" in out.columns and "excess_return_20d" in out.columns


def test_market_neutral_summary_reports_all_three_legs() -> None:
    frame = pd.DataFrame({
        "raw_return_20d": [0.10, -0.05],
        "benchmark_return_20d": [0.02, 0.01],
        "market_excess_return_20d": [0.08, -0.06],
    })
    summary = market_neutral_summary(frame, 20)
    assert summary["mean_raw_return"] == pytest.approx(0.025, abs=1e-6)
    assert summary["mean_benchmark_return"] == pytest.approx(0.015, abs=1e-6)
    assert summary["mean_market_excess_return"] == pytest.approx(0.01, abs=1e-6)
    assert summary["sample_count"] == 2


def test_market_neutral_summary_empty_returns_none() -> None:
    summary = market_neutral_summary(pd.DataFrame(), 20)
    assert summary["sample_count"] == 0
    assert summary["mean_market_excess_return"] is None


# ---------------------------------------------------------------------------
# 行业 / 板块
# ---------------------------------------------------------------------------


def test_industry_provider_refuses_to_classify() -> None:
    provider = UnavailableIndustryProvider()
    status = provider.status()
    payload = status.to_dict()
    assert status.status == INDUSTRY_CLASSIFICATION_UNAVAILABLE
    assert status.point_in_time_available is False
    assert payload["neutralization_available"] is False
    assert payload["strict_industry_neutral_backtest_allowed"] is False
    assert POINT_IN_TIME_INDUSTRY_UNAVAILABLE in status.detail
    with pytest.raises(NotImplementedError):
        provider.classify(date(2023, 1, 1))


def test_segment_is_labelled_as_board_not_industry() -> None:
    status = UnavailableIndustryProvider().status().to_dict()
    assert status["segment_control"] == "SEGMENT_CONTROL_BOARD"
    assert "chinext" in status["segment_labels"]
    # 板块标签必须是"交易所板块"而不是行业名 —— 防止读者把 segment 当 industry
    assert status["segment_labels"]["sse_main"] == "上交所主板"
    assert status["segment_labels"]["chinext"] == "创业板"


def test_attach_segment_and_demean() -> None:
    frame = pd.DataFrame({
        "stock_code": ["a", "b", "c", "d", "e", "f"],
        "as_of": [date(2023, 1, 2)] * 6,
        "market_excess_return_20d": [0.10, 0.12, 0.14, -0.10, -0.12, -0.14],
    })
    board_map = {"a": "sse_main", "b": "sse_main", "c": "sse_main",
                 "d": "chinext", "e": "chinext", "f": "chinext"}
    segmented = attach_segment(frame, board_map)
    assert segmented["segment"].tolist() == ["sse_main"] * 3 + ["chinext"] * 3
    neutral = segment_neutralize(segmented, "market_excess_return_20d")
    assert neutral["segment_neutral_value"].iloc[0] == pytest.approx(0.10 - 0.12, abs=1e-9)
    assert neutral["segment_size"].iloc[0] == 3


def test_attach_segment_does_not_guess_unknown_codes() -> None:
    frame = pd.DataFrame({"stock_code": ["zzz"], "as_of": [date(2023, 1, 2)]})
    out = attach_segment(frame, {})
    assert out["segment"].tolist() == ["unknown"]


def test_segment_demean_ignores_too_small_groups() -> None:
    frame = pd.DataFrame({
        "stock_code": ["a", "b", "c"],
        "as_of": [date(2023, 1, 2)] * 3,
        "segment": ["sse_main", "sse_main", "star"],
        "value": [1.0, 2.0, 3.0],
    })
    out = segment_neutralize(frame, "value", min_members=3)
    assert out["segment_neutral_value"].isna().all(), "小组不得参与去均值"


def test_segment_size_is_reported_even_when_neutralization_skipped() -> None:
    frame = pd.DataFrame({
        "stock_code": ["a", "b"],
        "as_of": [date(2023, 1, 2)] * 2,
        "segment": ["star", "star"],
        "value": [1.0, np.nan],
    })
    out = segment_neutralize(frame, "value", min_members=2)
    assert out["segment_size"].tolist() == [2, 2]


def test_binary_split_is_marked_degenerate_when_every_date_has_hits() -> None:
    """实测情形：黄历在 OOS 每个日期都至少有 1 个命中。

    此时"命中日 vs 非命中日"没有对照可言，必须显式标记退化，
    并把可解释性交给中位数切分与连续斜率 —— 不能把"全部日期"当作命中日组。
    """
    rows = []
    shares = [0.10, 0.20, 0.30, 0.40, 0.50, 0.90]
    for day_index, share in enumerate(shares):
        for stock_index in range(40):
            rows.append({
                "as_of": date(2023, 1 + day_index, 2),
                "stock_code": f"{stock_index:06d}",
                "hit": stock_index < int(round(share * 40)),
                "raw_return_20d": 0.001 * share,
                "benchmark_return_20d": 0.0,
                "market_excess_return_20d": 0.001 * share,
            })
    effect = date_effect_analysis(pd.DataFrame(rows), "hit", 20)
    assert effect["binary_split_usable"] is False
    assert effect["hit_dates"] is None and effect["non_hit_dates"] is None
    assert effect["date_clustered_difference"]["difference"] is None
    assert "退化" in effect["binary_split_note"]
    # 中位数切分仍然可用
    split = effect["median_split"]
    assert split is not None
    assert split["above_median"]["date_count"] == 3
    assert split["below_median"]["date_count"] == 3
    # 中位数 0.35 → 上组 [0.40,0.50,0.90] 均值 0.0006，下组 [0.10,0.20,0.30] 均值 0.0002
    assert split["median_hit_share"] == pytest.approx(0.35, abs=1e-6)
    assert split["difference"] == pytest.approx(0.0004, abs=1e-9)


def test_binary_split_is_usable_when_some_date_has_zero_hits() -> None:
    frame = _cross_section(date_count=6, hit_dates=(0, 1))
    effect = date_effect_analysis(frame, "hit", 20)
    assert effect["binary_split_usable"] is True
    assert "可用" in effect["binary_split_note"]
    assert effect["median_split"] is not None
