"""Phase 3F · 置换检验与 bootstrap 置信区间（GOAL §4.3 / §4.4）。

为什么置换必须**按日期分层**
-----------------------------
Phase 3D 已经实证：黄历的方向是「日历开关」—— 同一天要么几乎全体命中、
要么几乎全体不命中。若在整个面板上随机抽同样数量的位置（不保留每日命中数量），
抽到的集合与真实集合的**日期构成完全不同**，于是对照测的是"日期构成差异"
而不是"股票选择能力"，真实集合看起来会显著更差。

本模块的置换把随机化限制在**同一个 as_of 内部**：每个日期的命中数量被严格保留，
只打乱"哪些股票命中"。这正是 GOAL §4.7 提到的 ``gate-v2`` 协议改进项，
也是 Phase 3D 已预登记的未来改进方向。

bootstrap 同理：重采样单位是**日期**，不是行。行级 bootstrap 会把
"同一天 300 只股票"当成 300 个独立样本，得出虚假的窄置信区间。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: 默认置换次数（GOAL §4.4：至少 1000，性能允许时 5000）
DEFAULT_PERMUTATION_COUNT = 1000
#: 默认 bootstrap 次数
DEFAULT_BOOTSTRAP_COUNT = 2000

#: 置换协议版本
PERMUTATION_VERSION = "phase3f-date-stratified-permutation-v1"
#: bootstrap 协议版本
BOOTSTRAP_VERSION = "phase3f-date-block-bootstrap-v1"


@dataclass(frozen=True)
class PermutationResult:
    """一次日期分层置换检验的结果。"""

    statistic: float | None
    observed_control_means: tuple[float, ...]
    p_value_upper: float | None
    p_value_lower: float | None
    p_value_two_sided: float | None
    permutation_count: int
    permutation_seed: int
    date_count: int
    event_count: int
    permutation_version: str = PERMUTATION_VERSION

    def to_dict(self) -> dict:
        return {
            "permutation_version": self.permutation_version,
            "statistic": self.statistic,
            "permutation_count": self.permutation_count,
            "permutation_seed": self.permutation_seed,
            "date_count": self.date_count,
            "event_count": self.event_count,
            "p_value_upper": self.p_value_upper,
            "p_value_lower": self.p_value_lower,
            "p_value_two_sided": self.p_value_two_sided,
            "control_mean": (
                round(float(np.mean(self.observed_control_means)), 8)
                if self.observed_control_means else None
            ),
            "control_std": (
                round(float(np.std(self.observed_control_means, ddof=1)), 8)
                if len(self.observed_control_means) > 1 else None
            ),
        }


def _date_blocks(frame: pd.DataFrame, date_col: str) -> list[np.ndarray]:
    """把行号按 ``as_of`` 分组（保持原行序），供分层置换使用。"""
    order = np.argsort(frame[date_col].to_numpy(), kind="mergesort")
    dates = frame[date_col].to_numpy()[order]
    blocks: list[np.ndarray] = []
    start = 0
    for position in range(1, len(dates) + 1):
        if position == len(dates) or dates[position] != dates[start]:
            blocks.append(order[start:position])
            start = position
    return blocks


def permutation_test(
    frame: pd.DataFrame,
    hit_col: str,
    value_col: str,
    *,
    date_col: str = "as_of",
    permutation_count: int = DEFAULT_PERMUTATION_COUNT,
    seed: int = 0,
) -> PermutationResult:
    """日期分层置换检验。

    统计量 = 日期等权平均的 ``mean(value | hit) − mean(value | not hit)``。
    零假设 = 在每个 ``as_of`` 内部命中标签可交换（保留每日命中数量）。

    单侧 p：
        ``p_upper`` 检验"真实集合优于随机"（GOAL 的 positive 方向），
        ``p_lower`` 检验"真实集合劣于随机"。
    双侧 p 采用 ``2 * min(p_upper, p_lower)`` 截断到 1。
    """
    if permutation_count < 1:
        raise ValueError("permutation_count 必须 >= 1")
    if frame is None or len(frame) == 0 or hit_col not in frame.columns:
        return PermutationResult(None, (), None, None, None, 0, seed, 0, 0)

    values = pd.to_numeric(frame[value_col], errors="coerce").to_numpy(dtype=float)
    hits = frame[hit_col].astype(bool).to_numpy()
    finite = np.isfinite(values)
    if not finite.any():
        return PermutationResult(None, (), None, None, None, 0, seed, 0, 0)

    work = frame.loc[finite].copy()
    work["__value"] = values[finite]
    work["__hit"] = hits[finite]
    blocks = _date_blocks(work, date_col)
    block_values = [work["__value"].to_numpy(dtype=float)[block] for block in blocks]
    block_hits = [work["__hit"].to_numpy(dtype=bool)[block] for block in blocks]
    block_sizes = [int(block_hit.sum()) for block_hit in block_hits]

    observed = _date_weighted_difference(block_values, block_hits)
    if observed is None:
        return PermutationResult(None, (), None, None, None, 0, seed, 0, int(hits.sum()))

    rng = np.random.default_rng(seed)
    controls = np.empty(permutation_count, dtype=float)
    for draw in range(permutation_count):
        block_statistics: list[float] = []
        for block_index, values_block in enumerate(block_values):
            size = block_sizes[block_index]
            count = len(values_block)
            if size == 0 or size == count:
                block_statistics.append(float(values_block.mean()))
                continue
            order = rng.permutation(count)
            picked = values_block[order[:size]]
            rest = values_block[order[size:]]
            block_statistics.append(float(picked.mean() - rest.mean()))
        controls[draw] = float(np.mean(block_statistics))

    # +1 修正是标准的"包含观测值本身"的做法，避免 p=0 的伪精确
    upper = float((np.sum(controls >= observed) + 1) / (permutation_count + 1))
    lower = float((np.sum(controls <= observed) + 1) / (permutation_count + 1))
    two_sided = min(1.0, 2.0 * min(upper, lower))
    return PermutationResult(
        statistic=round(float(observed), 8),
        observed_control_means=tuple(float(value) for value in controls),
        p_value_upper=round(upper, 8),
        p_value_lower=round(lower, 8),
        p_value_two_sided=round(two_sided, 8),
        permutation_count=permutation_count,
        permutation_seed=seed,
        date_count=len(blocks),
        event_count=int(sum(block_sizes)),
    )


def _date_weighted_difference(
    block_values: list[np.ndarray], block_hits: list[np.ndarray],
) -> float | None:
    """日期等权平均的 (命中均值 − 未命中均值)；无可判定日期返回 None。"""
    statistics: list[float] = []
    for values_block, hits_block in zip(block_values, block_hits, strict=True):
        picked = values_block[hits_block]
        rest = values_block[~hits_block]
        if len(picked) == 0 or len(rest) == 0:
            continue
        statistics.append(float(picked.mean() - rest.mean()))
    if not statistics:
        return None
    return float(np.mean(statistics))


@dataclass(frozen=True)
class BootstrapResult:
    """date-block bootstrap 置信区间。"""

    point_estimate: float | None
    ci_lower: float | None
    ci_upper: float | None
    confidence: float
    bootstrap_count: int
    bootstrap_seed: int
    date_count: int
    crosses_zero: bool | None
    bootstrap_version: str = BOOTSTRAP_VERSION

    def to_dict(self) -> dict:
        return {
            "bootstrap_version": self.bootstrap_version,
            "point_estimate": self.point_estimate,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "confidence": self.confidence,
            "bootstrap_count": self.bootstrap_count,
            "bootstrap_seed": self.bootstrap_seed,
            "date_count": self.date_count,
            "crosses_zero": self.crosses_zero,
        }


def date_block_bootstrap(
    frame: pd.DataFrame,
    value_col: str,
    *,
    statistic: str = "mean",
    date_col: str = "as_of",
    hit_col: str | None = None,
    bootstrap_count: int = DEFAULT_BOOTSTRAP_COUNT,
    confidence: float = 0.95,
    seed: int = 0,
) -> BootstrapResult:
    """按日期重采样的 bootstrap 置信区间。

    ``statistic``：
        ``"mean"``      —— 值列的日期等权均值
        ``"difference"``—— 需要 ``hit_col``：日期等权平均的命中−未命中差
    """
    if frame is None or len(frame) == 0 or value_col not in frame.columns:
        return BootstrapResult(None, None, None, confidence, 0, seed, 0, None)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence 必须在 (0, 1) 内")

    values = pd.to_numeric(frame[value_col], errors="coerce")
    work = frame.assign(__value=values).dropna(subset=["__value"])
    if work.empty:
        return BootstrapResult(None, None, None, confidence, 0, seed, 0, None)
    if statistic == "difference":
        if hit_col is None:
            raise ValueError("statistic='difference' 需要 hit_col")
        work = work.assign(__hit=work[hit_col].astype(bool))

    date_keys = sorted(work[date_col].unique())
    per_date: list[dict] = []
    for key in date_keys:
        group = work[work[date_col] == key]
        entry = {"values": group["__value"].to_numpy(dtype=float)}
        if statistic == "difference":
            hits = group["__hit"].to_numpy(dtype=bool)
            entry["hits"] = hits
        per_date.append(entry)

    def _stat(bundle: list[dict]) -> float | None:
        statistics: list[float] = []
        for entry in bundle:
            if statistic == "mean":
                statistics.append(float(entry["values"].mean()))
            else:
                picked = entry["values"][entry["hits"]]
                rest = entry["values"][~entry["hits"]]
                if len(picked) == 0 or len(rest) == 0:
                    continue
                statistics.append(float(picked.mean() - rest.mean()))
        return float(np.mean(statistics)) if statistics else None

    point = _stat(per_date)
    if point is None:
        return BootstrapResult(None, None, None, confidence, 0, seed, len(per_date), None)

    rng = np.random.default_rng(seed)
    n_dates = len(per_date)
    draws = np.empty(bootstrap_count, dtype=float)
    valid = 0
    for _draw in range(bootstrap_count):
        indices = rng.integers(0, n_dates, size=n_dates)
        value = _stat([per_date[index] for index in indices])
        if value is None:
            continue
        draws[valid] = value
        valid += 1
    draws = draws[:valid]
    if valid == 0:
        return BootstrapResult(round(point, 8), None, None, confidence, 0, seed, n_dates, None)

    lower_q = (1.0 - confidence) / 2.0
    upper_q = 1.0 - lower_q
    lower = float(np.quantile(draws, lower_q))
    upper = float(np.quantile(draws, upper_q))
    return BootstrapResult(
        point_estimate=round(point, 8),
        ci_lower=round(lower, 8),
        ci_upper=round(upper, 8),
        confidence=confidence,
        bootstrap_count=int(valid),
        bootstrap_seed=seed,
        date_count=n_dates,
        crosses_zero=bool(lower <= 0.0 <= upper),
    )


__all__ = [
    "BOOTSTRAP_VERSION",
    "DEFAULT_BOOTSTRAP_COUNT",
    "DEFAULT_PERMUTATION_COUNT",
    "PERMUTATION_VERSION",
    "BootstrapResult",
    "PermutationResult",
    "date_block_bootstrap",
    "permutation_test",
]
