"""Phase 3E · 横截面统计与中性化测试。

重点验证三件事：
1. 统计量在**构造得出**的数据上取到解析值（不是"跑通就行"）；
2. 常量横截面、样本不足等退化情形返回 None 而非 0；
3. ``controlled_hit_coefficient`` 真的控制住了暴露 —— 造一个"效应完全来自风格"的数据，
   控制后系数必须塌回 0。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.neutralization import cross_section as xs


def test_spearman_rank_ic_perfect_monotone() -> None:
    scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    values = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
    assert xs.spearman_rank_ic(scores, values) == pytest.approx(1.0, abs=1e-8)
    assert xs.spearman_rank_ic(scores, -values) == pytest.approx(-1.0, abs=1e-8)


def test_spearman_rank_ic_constant_returns_none() -> None:
    """常量序列没有秩信息 → 必须返回 None（不得填 0 冒充"无相关"）。"""
    assert xs.spearman_rank_ic(pd.Series([1.0, 1.0, 1.0]), pd.Series([0.1, 0.2, 0.3])) is None
    assert xs.spearman_rank_ic(pd.Series([1.0, 2.0]), pd.Series([0.1, 0.2])) is None  # 样本过少


def test_date_equal_weighted_mean_gives_dates_equal_weight() -> None:
    """两个日期样本量相差 10 倍，date-clustered 均值必须按日期等权。"""
    frame = pd.DataFrame({
        "as_of": [date(2021, 1, 1)] * 10 + [date(2021, 2, 1)],
        "value": [0.10] * 10 + [0.00],
    })
    stats = xs.date_equal_weighted_mean(frame, "value")
    assert stats["pooled_mean"] == pytest.approx(0.10 * 10 / 11, abs=1e-9)
    assert stats["date_mean"] == pytest.approx(0.05, abs=1e-9)
    assert stats["date_count"] == 2
    assert stats["row_count"] == 11


def test_long_short_spread_is_within_date_then_averaged() -> None:
    frame = pd.DataFrame({
        "as_of": [date(2021, 1, 1)] * 6 + [date(2021, 2, 1)] * 6,
        "hit": ([True] * 3 + [False] * 3) * 2,
        "value": [0.10] * 3 + [0.00] * 3 + [0.02, 0.04, 0.00] + [0.00, 0.02, 0.01],
    })
    spread = xs.long_short_spread(frame, "hit", "value")
    # 第 1 日差距 0.10，第 2 日差距 (0.02-0.01)=0.01 → 日期等权平均 0.055
    assert spread["long_short_spread"] == pytest.approx(0.055, abs=1e-9)
    assert spread["spread_dates"] == 2
    assert spread["hit_mean"] == pytest.approx((0.10 + 0.02) / 2, abs=1e-9)


def test_style_neutralize_removes_linear_exposure_exactly() -> None:
    """y 恰好是暴露的线性函数时，残差必须 ≈ 0（说明正交化真的生效）。"""
    rng = np.random.default_rng(5)
    rows = []
    for day_index in range(4):
        exposure = rng.normal(0, 1, 40)
        noise_free = 0.5 * exposure
        rows.append(pd.DataFrame({
            "as_of": [date(2021, 1 + day_index, 1)] * 40,
            "exposure": exposure,
            "y": noise_free,
        }))
    frame = pd.concat(rows, ignore_index=True)
    out, diag = xs.style_neutralize(frame, "y", ["exposure"], min_stocks=20)
    residuals = out["style_residual"].dropna()
    assert len(residuals) == len(frame)
    assert float(np.abs(residuals).max()) < 1e-9
    assert diag["style_r2_mean"] == pytest.approx(1.0, abs=1e-9)


def test_style_neutralize_marks_unavailable_rows() -> None:
    """暴露缺失的行不得被插补；必须显式标为不可用。"""
    frame = pd.DataFrame({
        "as_of": [date(2021, 1, 1)] * 30,
        "exposure": [float(index) for index in range(29)] + [np.nan],
        "y": [float(index) for index in range(30)],
    })
    out, _diag = xs.style_neutralize(frame, "y", ["exposure"], min_stocks=20)
    assert int(out["style_residual_available"].sum()) == 29
    assert pd.isna(out["style_residual"].iloc[-1])


def test_controlled_hit_coefficient_absorbs_pure_style_effect() -> None:
    """造一个"命中组只是高暴露"的世界：控制暴露后系数必须塌回 ~0。

    这是 Q-E5 的方法学核心：如果真实效应只是风格暴露，那么
    ``controlled_hit_coefficient`` 会接近 0，而 long-short 看起来很大。
    """
    rng = np.random.default_rng(13)
    rows = []
    for day_index in range(6):
        exposure = rng.normal(0, 1, 60)
        hit = exposure > 0.0  # 命中完全由暴露决定
        y = 0.03 * exposure  # 收益完全由暴露决定
        rows.append(pd.DataFrame({
            "as_of": [date(2021, 1 + day_index, 1)] * 60,
            "exposure": exposure,
            "hit": hit,
            "y": y,
        }))
    frame = pd.concat(rows, ignore_index=True)
    spread = xs.long_short_spread(frame, "hit", "y")
    controlled = xs.controlled_hit_coefficient(frame, "y", "hit", ["exposure"], min_stocks=20)
    assert spread["long_short_spread"] > 0.01, "未控制时看起来有正效应"
    assert abs(controlled["hit_coefficient"]) < 1e-6, "控制暴露后效应应消失"
    assert controlled["hit_coefficient_dates"] == 6


def test_controlled_hit_coefficient_keeps_genuine_effect() -> None:
    """命中带来独立于暴露的收益时，控制后系数必须保留。"""
    rng = np.random.default_rng(17)
    rows = []
    for day_index in range(6):
        exposure = rng.normal(0, 1, 60)
        hit = np.zeros(60, dtype=bool)
        hit[rng.choice(60, 30, replace=False)] = True
        y = 0.03 * exposure + 0.05 * hit
        rows.append(pd.DataFrame({
            "as_of": [date(2021, 1 + day_index, 1)] * 60,
            "exposure": exposure,
            "hit": hit,
            "y": y,
        }))
    frame = pd.concat(rows, ignore_index=True)
    controlled = xs.controlled_hit_coefficient(frame, "y", "hit", ["exposure"], min_stocks=20)
    assert controlled["hit_coefficient"] == pytest.approx(0.05, abs=1e-6)


def test_per_date_rank_ic_skips_constant_dates() -> None:
    """命中在某个日期恒为 0 时该日的秩相关无定义，必须被跳过而不是记 0。"""
    rows = []
    for day_index in range(3):
        hit = [1.0, 1.0, 0.0, 0.0, 0.0]
        y = [0.09, 0.08, 0.03, 0.02, 0.01]
        rows.append(pd.DataFrame({
            "as_of": [date(2021, 1 + day_index, 1)] * 5, "score": hit, "y": y,
        }))
    frame = pd.concat(rows, ignore_index=True)
    stats = xs.per_date_rank_ic(frame, "score", "y")
    assert stats["rank_ic_dates"] == 3
    assert stats["rank_ic_mean"] > 0.8

    constant = frame.copy()
    constant["score"] = 1.0
    stats2 = xs.per_date_rank_ic(constant, "score", "y")
    assert stats2["rank_ic_dates"] == 0
    assert stats2["rank_ic_mean"] is None


def test_group_returns_reports_missing_groups_as_absent() -> None:
    frame = pd.DataFrame({
        "as_of": [date(2021, 1, 1)] * 12,
        "group": ["a"] * 6 + ["b"] * 6,
        "value": [0.01, 0.02, 0.03, 0.01, 0.02, 0.03,
                  -0.01, -0.02, -0.03, -0.01, -0.02, -0.03],
    })
    stats = xs.group_returns(frame, "group", "value")
    assert stats["a"]["date_mean"] == pytest.approx(0.02, abs=1e-9)
    assert stats["b"]["date_mean"] == pytest.approx(-0.02, abs=1e-9)
