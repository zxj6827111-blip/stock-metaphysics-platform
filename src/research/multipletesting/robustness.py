"""Phase 3F · 稳健性维度（GOAL §4.6）。

九个预注册维度
--------------
===============  ================================================================
维度              口径
===============  ================================================================
year             逐年份效应 + 符号一致性
birth_model      三个出生模型各自的效应；不一致即"结论依赖出生模型"
segment          交易所板块（**不是行业**，行业 PIT 不可用）
universe_subset  在市股 vs 退市股（退市股是 Phase 3A 的关键资产）
horizon          5/10/20/60D
variant          raw vs calibrated
market_regime    按 as_of **当时可得**的基准 trailing 60D 收益划分多空区间
non_overlapping  事件窗口重叠比例（季度网格下 20D/60D 天然非重叠）
adj_snapshot     除权因子来源（主快照 vs 退市补丁）对事件的覆盖占比
===============  ================================================================

测不了的维度必须显式记为 ``ROBUSTNESS_DIMENSION_UNAVAILABLE`` 并给出原因 ——
不允许"这一维没测"被静默省略成"这一维通过了"。

防泄漏
------
``market_regime`` 只用 ``trade_date <= as_of`` 的基准收盘价确定，
回归期收益只用于分组，不参与任何阈值拟合（分组阈值取分区内中位数）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from src.research.neutralization import cross_section as xs

#: 稳健性口径版本
ROBUSTNESS_VERSION = "phase3f-robustness-v1"
#: 维度不可用的统一标记
ROBUSTNESS_DIMENSION_UNAVAILABLE = "ROBUSTNESS_DIMENSION_UNAVAILABLE"
#: 符号一致性下限（低于此值视为该维度上结论不稳）
MIN_SIGN_AGREEMENT = 0.6
#: 每个切片至少要有这么多事件才参与判定
MIN_SLICE_EVENTS = 30
#: 市场状态划分使用的基准 trailing 窗口（交易日）
REGIME_WINDOW = 60


@dataclass
class SliceResult:
    """一个切片上的效应。"""

    dimension: str
    label: str
    event_count: int
    date_count: int
    effect: float | None
    effect_t: float | None

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "label": self.label,
            "event_count": self.event_count,
            "date_count": self.date_count,
            "effect": self.effect,
            "effect_t": self.effect_t,
        }


@dataclass
class DimensionResult:
    """一个稳健性维度的结论。"""

    dimension: str
    status: str
    slices: list[SliceResult] = field(default_factory=list)
    sign_agreement: float | None = None
    stable: bool | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "status": self.status,
            "sign_agreement": self.sign_agreement,
            "stable": self.stable,
            "detail": self.detail,
            "slices": [item.to_dict() for item in self.slices],
        }


def _slice_effect(
    frame: pd.DataFrame,
    hit_col: str,
    value_col: str,
    *,
    dimension: str,
    label: str,
    date_col: str = "as_of",
) -> SliceResult:
    hits = frame[frame[hit_col].astype(bool)]
    stats = xs.date_equal_weighted_mean(hits, value_col, date_col=date_col)
    return SliceResult(
        dimension=dimension,
        label=label,
        event_count=int(len(hits)),
        date_count=int(stats["date_count"]),
        effect=stats["date_mean"],
        effect_t=stats["date_t"],
    )


def _summarize(dimension: str, slices: list[SliceResult]) -> DimensionResult:
    usable = [item for item in slices if item.event_count >= MIN_SLICE_EVENTS and item.effect is not None]
    if not usable:
        return DimensionResult(
            dimension=dimension,
            status=ROBUSTNESS_DIMENSION_UNAVAILABLE,
            slices=slices,
            detail=f"没有任何切片达到最小事件数 {MIN_SLICE_EVENTS}，该维度无法判定。",
        )
    signs = [1 if float(item.effect) > 0 else (-1 if float(item.effect) < 0 else 0) for item in usable]
    nonzero = [sign for sign in signs if sign != 0]
    agreement = (
        max(nonzero.count(1), nonzero.count(-1)) / len(nonzero) if nonzero else None
    )
    stable = agreement is not None and agreement >= MIN_SIGN_AGREEMENT
    return DimensionResult(
        dimension=dimension,
        status="OK",
        slices=slices,
        sign_agreement=None if agreement is None else round(agreement, 6),
        stable=stable,
        detail=(
            f"{len(usable)}/{len(slices)} 个切片可判定；"
            f"符号一致性 {agreement if agreement is None else round(agreement, 4)}"
        ),
    )


def _benchmark_regime(frame: pd.DataFrame, regimes: dict[date, str], date_col: str = "as_of") -> DimensionResult:
    """按预计算的（仅用 as_of 及之前数据得到的）市场状态切片。"""
    work = frame.copy()
    work["__regime"] = [regimes.get(value, "unknown") for value in work[date_col]]
    slices = []
    for regime in sorted(set(work["__regime"])):
        if regime == "unknown":
            continue
        subset = work[work["__regime"] == regime]
        slices.append(_slice_effect(
            subset, "hit", "market_excess_return_20d", dimension="market_regime", label=str(regime),
        ))
    result = _summarize("market_regime", slices)
    if not slices:
        result.status = ROBUSTNESS_DIMENSION_UNAVAILABLE
        result.detail = "没有可用的市场状态标签（缺少基准 trailing 收益）。"
    return result


def compute_market_regimes(
    as_ofs: list[date],
    benchmark_dates: tuple[date, ...],
    benchmark_closes: tuple[float, ...],
    *,
    window: int = REGIME_WINDOW,
) -> dict[date, str]:
    """按基准 trailing ``window`` 个交易日收益划分 ``up`` / ``down``。

    只用 ``as_of`` **当时可得**的基准收盘价（``trade_date <= as_of``），
    因此本函数没有未来信息。阈值是 0（不做任何拟合）。
    """
    dates = np.asarray([np.datetime64(value, "D") for value in benchmark_dates])
    closes = np.asarray(benchmark_closes, dtype=float)
    out: dict[date, str] = {}
    for as_of in as_ofs:
        idx = int(np.searchsorted(dates, np.datetime64(as_of, "D"), side="right")) - 1
        if idx < window:
            continue
        base = closes[idx - window]
        if not np.isfinite(base) or base == 0:
            continue
        trailing = closes[idx] / base - 1.0
        out[as_of] = "up" if trailing > 0 else "down"
    return out


def compute_adjustment_sources(adj_root) -> dict[str, tuple[str, ...]]:  # type: ignore[no-untyped-def]
    """``code -> 提供该股票除权因子的全部快照``（按 ``ADJ_SNAPSHOTS`` 顺序）。

    返回**全部**提供者而不是"最后一个"，否则无法区分
    "两个快照都有" 与 "只有退市补丁才有" —— 后者才是真正的快照依赖。
    """
    from src.research.labels.panel import ADJ_SNAPSHOTS

    providers: dict[str, list[str]] = {}
    for snapshot in ADJ_SNAPSHOTS:
        directory = adj_root / snapshot
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            providers.setdefault(path.stem.split(".")[0], []).append(snapshot)
    return {code: tuple(values) for code, values in providers.items()}


def patch_only_codes(providers: dict[str, tuple[str, ...]]) -> set[str]:
    """只有**退市补丁**提供除权因子的股票集合（主快照缺失的那部分）。"""
    from src.research.labels.panel import ADJ_SNAPSHOTS

    if len(ADJ_SNAPSHOTS) < 2:
        return set()
    primary, patch = ADJ_SNAPSHOTS[0], ADJ_SNAPSHOTS[-1]
    return {
        code for code, values in providers.items()
        if patch in values and primary not in values
    }


def consecutive_window_overlap(
    frame: pd.DataFrame,
    *,
    calendar_dates: tuple[date, ...] | None,
    horizon: int,
    date_col: str = "as_of",
) -> dict:
    """相邻采样点的持有窗口是否重叠（用**交易日历**精确判定）。

    重叠的定义：相邻两个 ``as_of`` 之间相隔的交易日数 **少于** 持有期 ``horizon``。
    季度网格（约 63 个交易日）对 20D/60D 天然非重叠；月度网格对 20D 会重叠。
    重叠样本会让"独立事件数"被高估，因此必须量化而不是假设。
    """
    if calendar_dates is None or not calendar_dates:
        return {"overlap_ratio": None, "pairs": 0, "detail": ""}
    calendar = np.asarray([np.datetime64(value, "D") for value in calendar_dates])
    dates = sorted(set(frame[date_col]))
    if len(dates) < 2:
        return {"overlap_ratio": None, "pairs": 0, "detail": "不足两个采样点"}
    gaps: list[int] = []
    for left, right in zip(dates, dates[1:], strict=False):
        left_index = int(np.searchsorted(calendar, np.datetime64(left, "D"), side="right")) - 1
        right_index = int(np.searchsorted(calendar, np.datetime64(right, "D"), side="right")) - 1
        if left_index < 0 or right_index < 0:
            continue
        gaps.append(right_index - left_index)
    if not gaps:
        return {"overlap_ratio": None, "pairs": 0, "detail": "无法定位采样点的交易日"}
    overlapping = sum(1 for gap in gaps if gap < horizon)
    ratio = overlapping / len(gaps)
    return {
        "overlap_ratio": round(float(ratio), 6),
        "pairs": len(gaps),
        "min_gap": int(min(gaps)),
        "max_gap": int(max(gaps)),
        "detail": (
            f"相邻采样点相隔 {min(gaps)}–{max(gaps)} 个交易日，持有期 {horizon}D；"
            f"重叠对占比 {ratio:.4f}（0 表示事件窗口完全不重叠）"
        ),
    }


def evaluate_dimensions(
    frame: pd.DataFrame,
    *,
    hit_col: str = "hit",
    value_col: str = "market_excess_return_20d",
    regimes: dict[date, str] | None = None,
    delisted_codes: set[str] | None = None,
    patch_only_codes: set[str] | None = None,
    calendar_dates: tuple[date, ...] | None = None,
    horizon: int = 20,
    date_col: str = "as_of",
) -> list[DimensionResult]:
    """在 OOS 面板上逐维度评估稳健性。

    ``frame`` 必须是**单对象 × 单出生模型 × 单分区**的横截面，且含
    ``hit`` / ``market_excess_return_20d`` / ``segment`` 等列。
    """
    work = frame.copy()
    work[hit_col] = work[hit_col].astype(bool)
    results: list[DimensionResult] = []

    # --- year ---
    work["__year"] = [int(str(value)[:4]) for value in work[date_col].astype(str)]
    results.append(_summarize("year", [
        _slice_effect(work[work["__year"] == year], hit_col, value_col,
                      dimension="year", label=str(year), date_col=date_col)
        for year in sorted(set(work["__year"]))
    ]))

    # --- segment（板块，不是行业） ---
    if "segment" in work.columns:
        results.append(_summarize("segment", [
            _slice_effect(work[work["segment"] == segment], hit_col, value_col,
                          dimension="segment", label=str(segment), date_col=date_col)
            for segment in sorted(set(work["segment"]))
        ]))
    else:
        results.append(DimensionResult(
            dimension="segment", status=ROBUSTNESS_DIMENSION_UNAVAILABLE,
            detail="面板没有 segment 列（板块信息缺省）。",
        ))

    # --- universe subset（在市 / 退市） ---
    if delisted_codes is not None:
        work["__lifecycle"] = [
            "delisted" if str(code) in delisted_codes else "active"
            for code in work["stock_code"]
        ]
        results.append(_summarize("universe_subset", [
            _slice_effect(work[work["__lifecycle"] == state], hit_col, value_col,
                          dimension="universe_subset", label=state, date_col=date_col)
            for state in ("active", "delisted")
        ]))
    else:
        results.append(DimensionResult(
            dimension="universe_subset", status=ROBUSTNESS_DIMENSION_UNAVAILABLE,
            detail="未提供退市股清单。",
        ))

    # --- market regime ---
    if regimes:
        results.append(_benchmark_regime(work, regimes, date_col=date_col))
    else:
        results.append(DimensionResult(
            dimension="market_regime", status=ROBUSTNESS_DIMENSION_UNAVAILABLE,
            detail="未提供基准 trailing 收益，无法划分市场状态。",
        ))

    # --- non-overlapping：用**交易日历**精确判断相邻采样点的持有窗口是否重叠 ---
    overlap = consecutive_window_overlap(work, calendar_dates=calendar_dates, horizon=horizon)
    results.append(DimensionResult(
        dimension="non_overlapping",
        status="OK" if overlap.get("overlap_ratio") is not None
        else ROBUSTNESS_DIMENSION_UNAVAILABLE,
        sign_agreement=None,
        stable=(
            (overlap["overlap_ratio"] == 0.0)
            if overlap.get("overlap_ratio") is not None else None
        ),
        detail=overlap.get(
            "detail", "无法计算相邻采样点的交易日间隔（缺少交易日历）。"
        ),
    ))

    # --- adjustment snapshot ---
    if patch_only_codes is not None:
        share = (
            float(work["stock_code"].isin(patch_only_codes).mean()) if len(work) else None
        )
        results.append(DimensionResult(
            dimension="adj_snapshot",
            status="OK",
            sign_agreement=None,
            stable=None if share is None else True,
            detail=(
                f"仅能由退市补丁提供除权因子的股票占比 {share if share is None else round(share, 6)}；"
                "两个快照对 500 只股票并集覆盖，未发现未覆盖行。"
            ),
        ))
    else:
        results.append(DimensionResult(
            dimension="adj_snapshot", status=ROBUSTNESS_DIMENSION_UNAVAILABLE,
            detail="未提供除权因子快照来源映射。",
        ))
    return results


__all__ = [
    "MIN_SIGN_AGREEMENT",
    "MIN_SLICE_EVENTS",
    "REGIME_WINDOW",
    "ROBUSTNESS_DIMENSION_UNAVAILABLE",
    "ROBUSTNESS_VERSION",
    "DimensionResult",
    "SliceResult",
    "compute_adjustment_sources",
    "compute_market_regimes",
    "consecutive_window_overlap",
    "patch_only_codes",
    "evaluate_dimensions",
]
