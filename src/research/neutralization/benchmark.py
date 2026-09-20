"""Phase 3E · 市场中性化（benchmark 与 market excess）。

为什么单独一个模块
------------------
Phase 1 起 ``excess_return`` 就存在，但它散落在标签层；Phase 3E 要求把
"个股收益 − 基准收益"提升为**可审计的研究口径**：基准是谁、为什么是它、
能不能做市值分层映射、不可用时如何显式声明。这些必须是一等公民，
而不是埋在某个脚本的局部变量里。

基准可得性（2026-09-20 实测）
-----------------------------
canonical 快照（``astockdata_composite_none``）内**只有** ``IDX000300``（沪深 300），
不存在中证 500 / 中证 1000 等其它宽基。因此：

* 全局统一使用 ``IDX000300`` 作为基准；
* GOAL §3E-1 希望的"大盘股 → 沪深 300 / 中小盘 → 中证 500"分层映射
  **结构上不可得** → 显式状态 ``BENCHMARK_SPLIT_UNAVAILABLE``；
* 不得用"某个不存在的指数"或自建等权组合冒充中证 500 —— 那会引入
  一个与预注册口径不同的基准，事后无法解释差异来源。

纪律
----
* 本模块**不重新计算收益**：``ret_Nd`` / ``bench_ret_Nd`` / ``excess_return_Nd``
  由 ``src/research/labels/horizon_returns.py`` 统一产出（同一日历区间、同一复权口径）。
  本模块只做重命名、校验与汇总。
* ``market_excess_return`` 与 ``excess_return_Nd`` **恒等**（同一列的两个名字），
  保留双名是为了让报告同时满足"标签口径"与"中性化口径"两套术语。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.research.labels.horizon_returns import DEFAULT_BENCHMARK_CODE, HORIZONS

#: 市场中性化口径版本
MARKET_NEUTRAL_VERSION = "phase3e-market-neutral-v1"
#: canonical 快照内可得的全部基准
AVAILABLE_BENCHMARKS: tuple[str, ...] = ("IDX000300",)
#: GOAL §3E-1 期望做分层映射所需的指数（结构性不可得）
REQUIRED_FOR_SPLIT_MAPPING: tuple[str, ...] = ("IDX000300", "IDX000905")
#: 基准映射状态
BENCHMARK_SPLIT_UNAVAILABLE = "BENCHMARK_SPLIT_UNAVAILABLE"
BENCHMARK_UNIFIED = "BENCHMARK_UNIFIED"


@dataclass(frozen=True)
class BenchmarkPolicy:
    """基准选择策略的显式记录（写入产物与报告）。"""

    benchmark_code: str
    status: str
    mapping_rule: str
    available_benchmarks: tuple[str, ...]
    required_for_split_mapping: tuple[str, ...]

    @property
    def is_split_mapped(self) -> bool:
        return self.status == BENCHMARK_UNIFIED and all(
            code in self.available_benchmarks for code in self.required_for_split_mapping
        )

    def to_dict(self) -> dict:
        return {
            "market_neutral_version": MARKET_NEUTRAL_VERSION,
            "benchmark_code": self.benchmark_code,
            "benchmark_status": self.status,
            "mapping_rule": self.mapping_rule,
            "available_benchmarks": list(self.available_benchmarks),
            "required_for_split_mapping": list(self.required_for_split_mapping),
            "split_mapping_available": self.is_split_mapped,
        }


def benchmark_policy() -> BenchmarkPolicy:
    """默认策略：统一基准 + 显式声明分层映射不可得。

    "统一基准"意味着大中小盘股票共用同一条指数收益：这是一个**已声明的方法学选择**，
    不是疏漏。它的已知偏差是：当小盘股与沪深 300 走势背离时，超额收益里会混入
    规模暴露 —— 这正是 §3E-3 用 style controls 单独量化 size 的原因。
    """
    return BenchmarkPolicy(
        benchmark_code="IDX000300",
        status=BENCHMARK_SPLIT_UNAVAILABLE,
        mapping_rule=(
            "统一使用沪深 300（IDX000300）作为全部股票的基准；"
            "不做市值分层映射（中证 500 IDX000905 不在 canonical 快照内）。"
            "偏差方向已知：规模暴露会混入超额收益，由 style controls 的 size 维度单独量化。"
        ),
        available_benchmarks=AVAILABLE_BENCHMARKS,
        required_for_split_mapping=REQUIRED_FOR_SPLIT_MAPPING,
    )


def market_neutral_columns(horizon: int) -> tuple[str, str, str]:
    """持有期 ``horizon`` 对应的 (raw_return, benchmark_return, market_excess_return) 列名。"""
    if horizon not in HORIZONS:
        raise ValueError(f"未注册的持有期 {horizon}；已注册：{list(HORIZONS)}")
    return (f"ret_{horizon}d", f"bench_ret_{horizon}d", f"excess_return_{horizon}d")


def attach_market_excess(frame: pd.DataFrame, horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """把标签列重命名为市场中性化口径（追加列，不覆盖原始列）。

    输出列：``raw_return_{h}d`` / ``benchmark_return_{h}d`` / ``market_excess_return_{h}d``。
    三者与 ``ret_hd`` / ``bench_ret_hd`` / ``excess_return_hd`` 是同一数据。
    """
    out = frame.copy()
    for horizon in horizons:
        raw, bench, excess = market_neutral_columns(horizon)
        missing = [column for column in (raw, bench, excess) if column not in out.columns]
        if missing:
            raise ValueError(f"标签面板缺少市场中性化所需字段：{missing}")
        out[f"raw_return_{horizon}d"] = pd.to_numeric(out[raw], errors="coerce")
        out[f"benchmark_return_{horizon}d"] = pd.to_numeric(out[bench], errors="coerce")
        out[f"market_excess_return_{horizon}d"] = pd.to_numeric(out[excess], errors="coerce")
    return out


def _finite(values: pd.Series) -> np.ndarray:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    return arr[np.isfinite(arr)]


def market_neutral_summary(frame: pd.DataFrame, horizon: int) -> dict:
    """一个事件集合在持有期 ``horizon`` 的市场中性化摘要。

    ``market_excess_return`` 本身就是市场中性化后的效应量：它已经把同一日历区间内的
    基准收益扣除。``mean_raw_return`` 与 ``mean_benchmark_return`` 必须同时报告，
    否则无法区分"个股涨"与"市场涨"。
    """
    if frame is None or len(frame) == 0:
        return {
            "horizon": horizon, "sample_count": 0,
            "mean_raw_return": None, "mean_benchmark_return": None,
            "mean_market_excess_return": None,
            "median_market_excess_return": None, "std_market_excess_return": None,
            "market_excess_up_rate": None,
        }
    raw = _finite(frame[f"raw_return_{horizon}d"])
    bench = _finite(frame[f"benchmark_return_{horizon}d"])
    excess = _finite(frame[f"market_excess_return_{horizon}d"])
    n = int(len(excess))
    return {
        "horizon": horizon,
        "sample_count": n,
        "mean_raw_return": round(float(raw.mean()), 6) if len(raw) else None,
        "mean_benchmark_return": round(float(bench.mean()), 6) if len(bench) else None,
        "mean_market_excess_return": round(float(excess.mean()), 6) if n else None,
        "median_market_excess_return": round(float(np.median(excess)), 6) if n else None,
        "std_market_excess_return": round(float(excess.std(ddof=1)), 6) if n > 1 else None,
        "market_excess_up_rate": round(float((excess > 0).mean()), 6) if n else None,
    }


__all__ = [
    "AVAILABLE_BENCHMARKS",
    "BENCHMARK_SPLIT_UNAVAILABLE",
    "BENCHMARK_UNIFIED",
    "DEFAULT_BENCHMARK_CODE",
    "MARKET_NEUTRAL_VERSION",
    "REQUIRED_FOR_SPLIT_MAPPING",
    "BenchmarkPolicy",
    "attach_market_excess",
    "benchmark_policy",
    "market_neutral_columns",
    "market_neutral_summary",
]
