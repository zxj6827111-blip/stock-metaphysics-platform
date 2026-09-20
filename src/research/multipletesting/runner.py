"""Phase 3F · 多重检验与稳健性执行器。

一条流水线做的事
----------------
对 Phase 3D 的 **54 个实验**（18 假设 × 3 出生模型）逐条：

1. 日期分层置换检验（≥1000 次，默认 5000） → ``raw_p_value``
2. 效应量（mean difference / Cohen's d / RankIC）
3. date-block bootstrap 置信区间
4. 跨年份稳定性、单一股票依赖
5. 九个稳健性维度
6. 从 3D 产物读取负对照结论（**不重算、不改写** 3D 结果）
7. 从 3E 产物读取风格/板块中性化结论
8. 族内 BH-FDR + Bonferroni
9. ``gate-v2``（A–L）判定；同时保留 ``gate-v1`` 的原始状态

关于"不修改 Phase 3D 结果"
--------------------------
3D 的 54 条实验状态、对照统计、OOS 统计全部来自磁盘上的 3D 产物，本模块只读。
3F 产出的是**新增列**（q 值、bootstrap、置换、稳健性、gate-v2），
两条状态并排输出，禁止用 3F 的结果覆盖 3D 的记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.research.multipletesting import robustness as rb
from src.research.multipletesting.families import FamilyRegistry
from src.research.multipletesting.fdr import apply_family_correction
from src.research.multipletesting.gate_v2 import evaluate_gate_v2
from src.research.multipletesting.resample import (
    DEFAULT_PERMUTATION_COUNT,
    date_block_bootstrap,
    permutation_test,
)
from src.research.neutralization import cross_section as xs
from src.research.oos.diagnostics import cohens_d, stock_dependency
from src.research.oos.splits import OOS, VALIDATION
from src.research.status import ResearchStatus

#: 3F 研究口径版本
MULTIPLE_TESTING_RUN_VERSION = "phase3f-run-v1"
#: 主持有期（与 3D 一致：20D）
PRIMARY_HORIZON = 20


@dataclass
class MultipleTestingOutcome:
    """3F 一次运行的完整结果。"""

    experiment_rows: list[dict] = field(default_factory=list)
    robustness_rows: list[dict] = field(default_factory=list)
    family_summaries: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def _seed_for(base_seed: int, *parts: str) -> int:
    """由实验标识派生稳定种子（可复现，且不同实验不共用同一随机序列）。"""
    payload = "|".join([str(base_seed), *parts]).encode("utf-8")
    import hashlib

    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        return np.asarray([], dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _effect_size(frame: pd.DataFrame, hit_col: str, value_col: str) -> dict:
    """命中 vs 未命中的效应量（与 3D 同口径的 Cohen's d）。"""
    hits = frame[frame[hit_col].astype(bool)]
    rest = frame[~frame[hit_col].astype(bool)]
    a = _numeric(hits, value_col)
    b = _numeric(rest, value_col)
    if len(a) == 0 or len(b) == 0:
        return {"hit_mean": None, "non_hit_mean": None, "mean_difference": None, "cohen_d": None}
    return {
        "hit_mean": round(float(a.mean()), 8),
        "non_hit_mean": round(float(b.mean()), 8),
        "mean_difference": round(float(a.mean() - b.mean()), 8),
        "cohen_d": cohens_d(a.tolist(), b.tolist()),
    }


def _load_3d_controls(path: Path) -> dict[tuple[str, str], list[dict]]:
    """读取 3D 负对照结论（只读；按 (hypothesis_id, birth_model) 归组，仅 OOS）。"""
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    frame = frame[frame["partition"] == OOS]
    grouped: dict[tuple[str, str], list[dict]] = {}
    for (hypothesis_id, birth_model), group in frame.groupby(["hypothesis_id", "birth_model"]):
        grouped[(str(hypothesis_id), str(birth_model))] = group.to_dict("records")
    return grouped


def _load_3d_results(path: Path) -> dict[tuple[str, str], dict]:
    """读取 3D 每个实验的原始状态与 OOS 统计（只读）。"""
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    out: dict[tuple[str, str], dict] = {}
    for _index, row in frame.iterrows():
        out[(str(row["hypothesis_id"]), str(row["birth_model"]))] = row.to_dict()
    return out


def _load_3e_neutralization(path: Path) -> dict[tuple[str, str], dict]:
    """读取 3E 中性化结论（只读；仅 OOS 主持有期）。"""
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    frame = frame[(frame["partition"] == OOS) & (frame["horizon"] == PRIMARY_HORIZON)]
    out: dict[tuple[str, str], dict] = {}
    for _index, row in frame.iterrows():
        out[(str(row["object_id"]), str(row["birth_model"]))] = row.to_dict()
    return out


def _controls_for_gate(rows: list[dict]) -> list[dict]:
    """把 3D 对照行转成 gate-v2 需要的形状。"""
    normalised: list[dict] = []
    for row in rows:
        normalised.append({
            "kind": row.get("control_kind"),
            "mean_excess_return": row.get("mean_excess_return"),
            "jaccard_with_real": row.get("jaccard_with_real"),
            "decisive": bool(row.get("decisive")) if not pd.isna(row.get("decisive")) else False,
            "p_value": row.get("p_value"),
            "verdict": row.get("verdict"),
        })
    return normalised


def _year_stability_from_frame(frame: pd.DataFrame, value_col: str) -> dict:
    """逐年份统计（复用 3D diagnostics 的口径）。"""
    work = frame.copy()
    work["__value"] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna(subset=["__value"])
    if work.empty:
        return {"year_count": 0, "positive_year_ratio": None, "sign_consistency": None}
    work["year"] = [int(str(value)[:4]) for value in work["as_of"].astype(str)]
    year_means: dict[int, float] = {}
    for year, group in work.groupby("year"):
        year_means[int(year)] = float(group["__value"].mean())
    signs = [1 if value > 0 else (-1 if value < 0 else 0) for value in year_means.values()]
    nonzero = [sign for sign in signs if sign != 0]
    return {
        "year_count": len(year_means),
        "positive_year_ratio": (
            round(sum(1 for value in year_means.values() if value > 0) / len(year_means), 6)
            if year_means else None
        ),
        "sign_consistency": (
            round(max(nonzero.count(1), nonzero.count(-1)) / len(nonzero), 6)
            if nonzero else None
        ),
        "per_year": {str(key): round(value, 8) for key, value in sorted(year_means.items())},
    }


def _stock_dependency_from_frame(frame: pd.DataFrame, hit_col: str, value_col: str) -> dict:
    """单一股票依赖诊断（复用 3D diagnostics 的实现）。"""
    hits = frame[frame[hit_col].astype(bool)].copy()
    if hits.empty or "stock_code" not in hits.columns:
        return {
            "top_1_contribution": None, "top_5_contribution": None,
            "loo_sign_flip_count": 0, "loo_mean_min": None, "loo_mean_max": None,
            "stock_count": 0,
        }
    return stock_dependency(hits, PRIMARY_HORIZON, return_col=value_col)


def _birth_model_contrasts(
    dataset,  # type: ignore[no-untyped-def]
    registry: FamilyRegistry,
    *,
    contrast_permutation_count: int = 2000,
    base_seed: int = 20260920,
) -> list[dict]:
    """出生模型对比族的检验（配对、按日期）。

    对每个单引擎对象、每对出生模型：在每个 ``as_of`` 上分别计算两模型的命中均值，
    取差值，再跨日期做**配对 t 检验**（自由度 = 有效日期数 − 1）。
    双侧 p；零假设 = "换出生模型不改变结论"。
    """
    family = registry.by_id("birth_model_comparison")
    rows: list[dict] = []
    for object_id in family.comparison_objects:
        for model_a, model_b in family.birth_model_pairs:
            frame_a = dataset.object_frame(object_id, model_a, OOS)
            frame_b = dataset.object_frame(object_id, model_b, OOS)
            value_col = f"market_excess_return_{PRIMARY_HORIZON}d"
            per_date_a: dict[object, float] = {}
            per_date_b: dict[object, float] = {}
            for key, group in frame_a.groupby("as_of"):
                hits = group[group["hit"]]
                values = pd.to_numeric(hits[value_col], errors="coerce").dropna()
                if len(values):
                    per_date_a[key] = float(values.mean())
            for key, group in frame_b.groupby("as_of"):
                hits = group[group["hit"]]
                values = pd.to_numeric(hits[value_col], errors="coerce").dropna()
                if len(values):
                    per_date_b[key] = float(values.mean())
            common = sorted(set(per_date_a) & set(per_date_b))
            if len(common) < 3:
                rows.append({
                    "hypothesis_id": f"BMC-{object_id}-{model_a}-vs-{model_b}",
                    "object_id": object_id,
                    "birth_model": f"{model_a}|{model_b}",
                    "comparison_pair": [model_a, model_b],
                    "date_count": len(common),
                    "mean_effect_a": None, "mean_effect_b": None,
                    "mean_paired_difference": None,
                    "raw_p_value": None,
                    "p_value_test": "birth_model_sign_flip_permutation",
                    "note": "共同日期不足 3 个，无法做配对检验",
                })
                continue
            differences = np.asarray(
                [per_date_a[key] - per_date_b[key] for key in common], dtype=float,
            )
            mean_diff = float(differences.mean())
            p_value = _sign_flip_p(
                differences, draws=contrast_permutation_count,
                seed=_seed_for(base_seed, object_id, model_a, model_b, "bmc"),
            )
            rows.append({
                "hypothesis_id": f"BMC-{object_id}-{model_a}-vs-{model_b}",
                "object_id": object_id,
                "birth_model": f"{model_a}|{model_b}",
                "comparison_pair": [model_a, model_b],
                "date_count": len(common),
                "mean_effect_a": round(float(np.mean(list(per_date_a[key] for key in common))), 8),
                "mean_effect_b": round(float(np.mean(list(per_date_b[key] for key in common))), 8),
                "mean_paired_difference": round(mean_diff, 8),
                "raw_p_value": p_value,
                "p_value_test": "birth_model_sign_flip_permutation",
                "note": "拒绝零假设 = 结论对出生模型敏感",
            })
    return rows


def _sign_flip_p(differences: np.ndarray, *, draws: int, seed: int) -> float | None:
    """配对差的**符号翻转置换**双侧 p 值。

    零假设 = 两个出生模型的效应没有系统性差异 → 每个日期的配对差关于 0 对称，
    因此可以对每个日期独立随机翻转符号。这是精确检验，不依赖正态或 t 近似，
    也不需要引入 scipy。
    """
    if len(differences) == 0:
        return None
    observed = abs(float(differences.mean()))
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.asarray([-1.0, 1.0]), size=(draws, len(differences)))
    permuted = np.abs(signs @ differences / len(differences))
    p_value = float((np.sum(permuted >= observed) + 1) / (draws + 1))
    return round(min(1.0, p_value), 8)


def run_multiple_testing(
    *,
    dataset,  # type: ignore[no-untyped-def]
    registry: FamilyRegistry,
    controls_3d: dict[tuple[str, str], list[dict]],
    results_3d: dict[tuple[str, str], dict],
    neutralization_3e: dict[tuple[str, str], dict],
    permutation_count: int = DEFAULT_PERMUTATION_COUNT,
    bootstrap_count: int = 2000,
    base_seed: int = 20260920,
    calendar_dates: tuple[date, ...] | None = None,
    regimes: dict[date, str] | None = None,
    delisted_codes: set[str] | None = None,
    patch_only_codes: set[str] | None = None,
    contrast_permutation_count: int = 2000,
    progress=None,  # type: ignore[no-untyped-def]
) -> MultipleTestingOutcome:
    """对全部注册假设 × 出生模型执行 3F 分析。"""
    value_col = f"market_excess_return_{PRIMARY_HORIZON}d"
    experiment_rows: list[dict] = []
    robustness_rows: list[dict] = []

    specs = list(dataset.registry.hypotheses)
    index = 0
    for spec in specs:
        family_id = registry.family_of(spec.hypothesis_id)
        family = registry.by_id(family_id)
        for birth_model in dataset.birth_models:
            index += 1
            if progress and index % 10 == 0:
                progress(f"[{index}/{len(specs) * len(dataset.birth_models)}] {spec.object_id}/{birth_model}")
            frame = dataset.object_frame(spec.object_id, birth_model, OOS)
            frame = frame[pd.to_numeric(frame[value_col], errors="coerce").notna()]
            row: dict = {
                "run_version": MULTIPLE_TESTING_RUN_VERSION,
                "mt_version": registry.mt_version,
                "family_id": family_id,
                "family_gated": family.gated,
                "tails": family.tails,
                "hypothesis_id": spec.hypothesis_id,
                "object_id": spec.object_id,
                "engines": "+".join(spec.engines),
                "direction_source": spec.direction_source,
                "logic": spec.logic,
                "expected_direction": spec.expected_direction,
                "birth_model": birth_model,
                "partition": OOS,
                "horizon": PRIMARY_HORIZON,
                "eligible_row_count": int(len(frame)),
                "event_count": int(frame["hit"].sum()) if len(frame) else 0,
            }
            if frame.empty or int(frame["hit"].sum()) == 0:
                row["raw_p_value"] = None
                row["p_value_test"] = "unavailable_no_events"
                experiment_rows.append(row)
                continue

            # --- 置换（日期分层） ---
            permutation = permutation_test(
                frame, "hit", value_col,
                permutation_count=permutation_count,
                seed=_seed_for(base_seed, spec.hypothesis_id, birth_model, "perm"),
            )
            row["raw_p_value"] = (
                permutation.p_value_upper if family.tails == "one_sided"
                else permutation.p_value_two_sided
            )
            row["p_value_upper"] = permutation.p_value_upper
            row["p_value_lower"] = permutation.p_value_lower
            row["p_value_two_sided"] = permutation.p_value_two_sided
            row["p_value_test"] = (
                "date_stratified_permutation_one_sided"
                if family.tails == "one_sided"
                else "date_stratified_permutation_two_sided"
            )
            row["permutation_count"] = permutation.permutation_count
            row["permutation_seed"] = permutation.permutation_seed
            row["permutation_date_count"] = permutation.date_count
            row["permutation_statistic"] = permutation.statistic
            row["permutation_control_mean"] = permutation.to_dict()["control_mean"]
            row["permutation_control_std"] = permutation.to_dict()["control_std"]

            # --- 效应量 ---
            row.update(_effect_size(frame, "hit", value_col))
            row["event_rank_ic_mean"] = xs.per_date_rank_ic(
                frame.assign(__hit=frame["hit"].astype(float)), "__hit", value_col,
            )["rank_ic_mean"]

            # --- bootstrap ---
            boot_difference = date_block_bootstrap(
                frame, value_col, statistic="difference", hit_col="hit",
                bootstrap_count=bootstrap_count,
                seed=_seed_for(base_seed, spec.hypothesis_id, birth_model, "boot_diff"),
            )
            boot_mean = date_block_bootstrap(
                frame, value_col, statistic="mean", bootstrap_count=bootstrap_count,
                seed=_seed_for(base_seed, spec.hypothesis_id, birth_model, "boot_mean"),
            )
            for prefix, boot in (("difference", boot_difference), ("hit_mean", boot_mean)):
                row[f"bootstrap_{prefix}_point"] = boot.point_estimate
                row[f"bootstrap_{prefix}_ci_lower"] = boot.ci_lower
                row[f"bootstrap_{prefix}_ci_upper"] = boot.ci_upper
                row[f"bootstrap_{prefix}_crosses_zero"] = boot.crosses_zero
            row["bootstrap_confidence"] = boot_difference.confidence
            row["bootstrap_count"] = boot_difference.bootstrap_count
            row["bootstrap_seed"] = boot_difference.bootstrap_seed

            # --- 年份 / 单一股票 ---
            years = _year_stability_from_frame(frame, value_col)
            row["year_count"] = years["year_count"]
            row["positive_year_ratio"] = years["positive_year_ratio"]
            row["sign_consistency"] = years["sign_consistency"]
            dependency = _stock_dependency_from_frame(frame, "hit", value_col)
            row["top_1_contribution"] = dependency.get("top_1_contribution")
            row["loo_sign_flip_count"] = dependency.get("loo_sign_flip_count")

            # --- 3D 对照（只读） ---
            controls = _controls_for_gate(controls_3d.get((spec.hypothesis_id, birth_model), []))
            row["control_count"] = len(controls)
            row["control_decisive_count"] = sum(1 for item in controls if item["decisive"])
            row["gate_v1_status"] = str(
                (results_3d.get((spec.hypothesis_id, birth_model), {}) or {}).get("status", "")
            )
            row["gate_v1_mean_excess_return"] = (
                results_3d.get((spec.hypothesis_id, birth_model), {}) or {}
            ).get("oos_mean_excess_return")
            row["gate_v1_oos_event_count"] = (
                results_3d.get((spec.hypothesis_id, birth_model), {}) or {}
            ).get("oos_event_count")

            # --- 3E 中性化（只读） ---
            neutral = neutralization_3e.get((spec.object_id, birth_model), {}) or {}
            row["style_neutral_hit_mean"] = neutral.get("style_neutral_hit_mean")
            row["segment_neutral_hit_mean"] = neutral.get("segment_neutral_hit_mean")
            row["segment_available"] = neutral.get("segment_available")
            row["hit_date_mean_market_excess"] = neutral.get("hit_date_mean_market_excess")

            # --- 稳健性维度 ---
            dimensions = rb.evaluate_dimensions(
                frame, hit_col="hit", value_col=value_col,
                regimes=regimes,
                delisted_codes=delisted_codes,
                patch_only_codes=patch_only_codes,
                calendar_dates=calendar_dates,
                horizon=PRIMARY_HORIZON,
            )
            for dimension in dimensions:
                robustness_rows.append({
                    "run_version": MULTIPLE_TESTING_RUN_VERSION,
                    "hypothesis_id": spec.hypothesis_id,
                    "object_id": spec.object_id,
                    "birth_model": birth_model,
                    **dimension.to_dict(),
                })
            row["robustness_unavailable_dimensions"] = ",".join(
                item.dimension for item in dimensions
                if item.status == rb.ROBUSTNESS_DIMENSION_UNAVAILABLE
            )
            row["robustness_unstable_dimensions"] = ",".join(
                item.dimension for item in dimensions
                if item.status == "OK" and item.stable is False
            )

            experiment_rows.append(row)

    # --- 出生模型对比族 ---
    contrasts = _birth_model_contrasts(
        dataset, registry,
        contrast_permutation_count=contrast_permutation_count,
        base_seed=base_seed,
    )

    # --- 族内校正 ---
    family_summaries: list[dict] = []
    corrected_rows: list[dict] = []
    for family in registry.families:
        members = [
            row for row in experiment_rows
            if row.get("family_id") == family.family_id
        ]
        if family.family_id == "birth_model_comparison":
            members = [
                {**row, "family_id": family.family_id, "family_gated": family.gated}
                for row in contrasts
            ]
        result = apply_family_correction(
            members, family_id=family.family_id, alpha=registry.alpha,
            mt_version=registry.mt_version,
        )
        corrected_rows.extend(result.rows)
        family_summaries.append(result.to_dict())

    # --- gate-v2 ---
    for row in corrected_rows:
        key = (row.get("hypothesis_id"), row.get("birth_model"))
        spec = next(
            (item for item in specs if item.hypothesis_id == key[0]), None,
        )
        if spec is None or row.get("family_id") == "birth_model_comparison":
            # 出生模型对比族与探索性族都不进入单向解锁路径
            row["gate_v2_status"] = (
                ResearchStatus.EXPLORATORY_NOT_GATED.value
                if row.get("family_gated") is False
                else "NOT_APPLICABLE"
            )
            continue
        controls = _controls_for_gate(controls_3d.get(key, []))
        gate = evaluate_gate_v2(
            experiment_id=f"MT3F--{key[0]}--{key[1]}",
            oos_stats={
                "event_count": row.get("event_count"),
                "sample_count": row.get("eligible_row_count"),
                "mean_market_excess_return": row.get("hit_date_mean_market_excess"),
                "cohen_d": row.get("cohen_d"),
            },
            validation_stats=_validation_stats(dataset, spec.object_id, key[1]),
            controls=controls,
            year_stability={
                "year_count": row.get("year_count"),
                "positive_year_ratio": row.get("positive_year_ratio"),
                "sign_consistency": row.get("sign_consistency"),
            },
            stock_dependency={
                "top_1_contribution": row.get("top_1_contribution"),
                "loo_sign_flip_count": row.get("loo_sign_flip_count"),
            },
            calibration_audit=dataset.calibration_audit,
            multiple_testing={
                "family_id": row.get("family_id"),
                "family_test_count": row.get("family_test_count"),
                "raw_p_value": row.get("raw_p_value"),
                "fdr_q_value": row.get("fdr_q_value"),
                "fdr_pass": row.get("fdr_pass"),
            },
            bootstrap={
                "point_estimate": row.get("bootstrap_hit_mean_point"),
                "ci_lower": row.get("bootstrap_hit_mean_ci_lower"),
                "ci_upper": row.get("bootstrap_hit_mean_ci_upper"),
                "crosses_zero": row.get("bootstrap_hit_mean_crosses_zero"),
            },
            permutation={
                "p_value_upper": row.get("p_value_upper"),
                "permutation_count": row.get("permutation_count"),
                "permutation_seed": row.get("permutation_seed"),
            },
            neutralization={
                "hit_date_mean_market_excess": row.get("hit_date_mean_market_excess"),
                "style_neutral_hit_mean": row.get("style_neutral_hit_mean"),
                "segment_neutral_hit_mean": row.get("segment_neutral_hit_mean"),
                "segment_available": row.get("segment_available"),
            },
            horizon=PRIMARY_HORIZON,
            is_gated=bool(row.get("family_gated", True)),
            gate_v1_status=str(row.get("gate_v1_status") or ""),
        )
        row["gate_v2_status"] = gate.status.value
        row["gate_v2_reasons"] = " | ".join(gate.reasons)
        row["gate_v2_failed_checks"] = ",".join(
            item.name for item in gate.checks if item.blocking and not item.passed
        )
        row["gate_v2_checks"] = len(gate.checks)

    meta = {
        "run_version": MULTIPLE_TESTING_RUN_VERSION,
        "mt_version": registry.mt_version,
        "families": registry.to_dict(),
        "permutation_count": permutation_count,
        "bootstrap_count": bootstrap_count,
        "base_seed": base_seed,
        "experiment_count": len(corrected_rows),
        "family_summaries": family_summaries,
    }
    return MultipleTestingOutcome(
        experiment_rows=corrected_rows,
        robustness_rows=robustness_rows,
        family_summaries=family_summaries,
        meta=meta,
    )


def _validation_stats(dataset, object_id: str, birth_model: str) -> dict:  # type: ignore[no-untyped-def]
    frame = dataset.object_frame(object_id, birth_model, VALIDATION)
    value_col = f"market_excess_return_{PRIMARY_HORIZON}d"
    if frame.empty:
        return {"event_count": 0, "sample_count": 0, "mean_market_excess_return": None}
    hits = frame[frame["hit"]]
    values = pd.to_numeric(hits[value_col], errors="coerce").dropna()
    return {
        "event_count": int(len(hits)),
        "sample_count": int(len(frame)),
        "mean_market_excess_return": (
            round(float(values.mean()), 8) if len(values) else None
        ),
    }


__all__ = [
    "MULTIPLE_TESTING_RUN_VERSION",
    "PRIMARY_HORIZON",
    "MultipleTestingOutcome",
    "run_multiple_testing",
]

