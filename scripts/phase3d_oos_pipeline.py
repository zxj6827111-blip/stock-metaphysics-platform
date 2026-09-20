"""Phase 3D OOS / Walk-forward 研究管线（主驱动）。

一条命令完成：
    1. 并行采集观测面板（主面板 / 月度 OOS 子面板 / 出生平移 ±7 天对照面板）
    2. 从 canonical 行情 + TuShare adj_factor 推导未来收益标签（ret + excess ×4 horizon）
    3. 固定 holdout：TRAIN 冻结 cal-v1 → Validation / OOS 只 transform
    4. 18 个预注册假设 × 3 出生模型：分区统计 + 诊断 + 4 类负对照 + OOS 状态门
    5. 扩窗 walk-forward（逐 fold 重拟合，P0 规则）
    6. 重叠窗口敏感性（月度 OOS 子面板）
    7. 产物：CSV/JSON 研究记录 + 三份方法学/结果文档

**本脚本会真实读取 OOS 收益标签**，因此运行后必须在实验登记中写入
``oos_used=True``；重复运行需带 ``--reuse-cache`` 以免再次采集，
但 OOS 的"一次性"语义由登记表承担，不由缓存承担。

用法::

    python scripts/phase3d_oos_pipeline.py --parallel 8
    python scripts/phase3d_oos_pipeline.py --reuse-cache --skip-collect
"""

from __future__ import annotations

import argparse
import json
import pickle
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.db.base import get_session_factory  # noqa: E402
from src.db.models import MarketBarDailyRow, UniverseMembershipRow  # noqa: E402
from src.research.labels.horizon_returns import (  # noqa: E402
    DEFAULT_BENCHMARK_CODE,
    HORIZONS,
    BenchmarkSeries,
    compute_forward_returns,
    label_frame,
)
from src.research.oos.calibration_freeze import CALIBRATION_VERSION, FREEZE_V1  # noqa: E402
from src.research.oos.gates import gate_thresholds  # noqa: E402
from src.research.oos.registry import (  # noqa: E402
    ExperimentRecord,
    load_hypothesis_registry,
    new_experiment_id,
    persist_experiments,
    utc_timestamp,
    write_experiment_registry_csv,
    write_registry_json,
)
from src.research.oos.runner import (  # noqa: E402
    PanelError,
    assert_no_out_of_scope,
    attach_calibration,
    build_observation_panel,
    direction_matrix,
    event_frame,
    overlap_block,
    run_hypothesis,
)
from src.research.oos.splits import (  # noqa: E402
    LABEL_VERSION,
    OOS,
    TRAIN,
    UNIVERSE_VERSION,
    VALIDATION,
    default_split,
)
from src.research.oos.walk_forward import (  # noqa: E402
    MIN_TRAIN_YEARS,
    expanding_folds,
    run_walk_forward,
)

BAR_SOURCE = "astockdata_composite_none"
BENCHMARK_CODE = "IDX000300"
CACHE_DIR = ROOT / "data" / "phase3_universe" / "phase3d_cache"
OUT_DIR = ROOT / "data" / "phase3_universe"
DOCS_DIR = ROOT / "docs"
HYPOTHESIS_REGISTRY_PATH = ROOT / "config" / "phase3d_hypothesis_registry.yaml"
#: 出生平移对照面板采集范围（OOS 区间）
SHIFT_FROM = "2023-01-01"
#: 月度 OOS 子面板范围（重叠敏感性）
MONTHLY_FROM = "2023-01-01"
#: ADJ_FACTOR 快照（主 + 退市补丁；并集覆盖全部 500 只）
ADJ_SNAPSHOTS = (
    "tsfactor_20260731T221443_49624041",
    "tsfactor_20260806T110553_91dc1a9e",
)
ASTOCKDATA_FACTOR_ROOT = Path(
    __import__("os").environ.get("SMP_ASTOCKDATA_ROOT", r"E:\AStockData")
) / "factors" / "tushare" / "adj_factor"


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------


def _launch_collector(command: list[str], log_path: Path):  # type: ignore[no-untyped-def]
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(  # noqa: S603 - 固定 argv，无 shell
        command, cwd=str(ROOT), stdout=handle, stderr=subprocess.STDOUT,
    )
    return process, handle


def collect_panels(args: argparse.Namespace) -> dict[str, list[Path]]:
    """并行采集四套面板（主 / 月度 OOS / 平移 ±7）。返回 label → 分片文件列表。"""
    plans = {
        "main": dict(date_from="2010-01-01", date_to=args.date_to,
                     step_months=str(args.step_months), birth_shift_days="0"),
        "monthly_oos": dict(date_from=MONTHLY_FROM, date_to=args.date_to,
                            step_months="1", birth_shift_days="0"),
        "shift_minus": dict(date_from=SHIFT_FROM, date_to=args.date_to,
                            step_months=str(args.step_months), birth_shift_days="-7"),
        "shift_plus": dict(date_from=SHIFT_FROM, date_to=args.date_to,
                           step_months=str(args.step_months), birth_shift_days="7"),
    }
    shards: dict[str, list[Path]] = {}
    for label, plan in plans.items():
        outputs = [CACHE_DIR / f"{label}_shard{index:02d}.pkl" for index in range(args.parallel)]
        shards[label] = outputs
        pending = [
            (index, out) for index, out in enumerate(outputs)
            if not (args.reuse_cache and out.exists())
        ]
        if not pending:
            print(f"[{label}] 全部分片已存在，跳过", flush=True)
            continue
        running: list[tuple[int, subprocess.Popen, object, float]] = []
        for index, out in pending:
            if len(running) >= args.parallel:
                oldest = running.pop(0)
                _reap(label, *oldest)
            command = [
                sys.executable, str(ROOT / "scripts" / "phase3d_collect_panel.py"),
                "--date-from", plan["date_from"], "--date-to", plan["date_to"],
                "--step-months", plan["step_months"],
                "--birth-shift-days", plan["birth_shift_days"],
                "--shard-index", str(index), "--shard-count", str(args.parallel),
                "--out", str(out),
            ]
            process, handle = _launch_collector(
                command, CACHE_DIR / f"{label}_shard{index:02d}.log"
            )
            running.append((index, process, handle, time.time()))
        for entry in running:
            _reap(label, *entry)
    return shards


def _reap(label: str, index: int, process: subprocess.Popen, handle, started: float) -> None:  # type: ignore[no-untyped-def]
    code = process.wait()
    handle.close()
    if code != 0:
        raise RuntimeError(
            f"[{label}] shard {index} 失败（退出码 {code}）；见 "
            f"{CACHE_DIR / f'{label}_shard{index:02d}.log'}"
        )
    print(f"[{label}] shard {index} 完成（{time.time() - started:.0f}s）", flush=True)


def _shard_paths(label: str, count: int) -> list[Path]:
    return [CACHE_DIR / f"{label}_shard{index:02d}.pkl" for index in range(count)]


def _discover_shards(label: str) -> list[Path]:
    """按文件名发现该面板的全部已有分片（排序稳定）。

    不能按 ``range(parallel)`` 硬拼路径：分片数量取决于**当初采集时**的并行度，
    用不同 ``--parallel`` 重跑会静默只用一半股票集合。这里按实际存在的文件发现，
    并在合并后校验股票总数。
    """
    return sorted(CACHE_DIR.glob(f"{label}_shard*.pkl"))


def merge_shards(paths: list[Path]) -> dict:
    """合并分片：股票集合不得重叠、采样日期/平移口径必须一致。"""
    payloads = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("rb") as handle:
            payloads.append(pickle.load(handle))
    if not payloads:
        raise RuntimeError("没有可用分片")
    base = payloads[0]
    codes: list[str] = []
    rows: list[dict] = []
    failures: Counter = Counter()
    per_date: Counter = Counter()
    for payload in payloads:
        if payload["universe_version"] != UNIVERSE_VERSION:
            raise ValueError("分片 universe_version 不一致")
        if payload["dates"] != base["dates"]:
            raise ValueError("分片采样日期不一致")
        if payload["birth_shift_days"] != base["birth_shift_days"]:
            raise ValueError("分片出生平移口径不一致")
        overlap = set(codes) & set(payload["codes"])
        if overlap:
            raise ValueError(f"分片股票重叠：{sorted(overlap)[:5]}")
        codes.extend(payload["codes"])
        rows.extend(payload["rows"])
        failures.update(payload.get("failures", {}))
        per_date.update(payload.get("per_date_row_count", {}))
    return {
        "universe_version": base["universe_version"],
        "codes": sorted(codes),
        "dates": base["dates"],
        "rows": rows,
        "birth_shift_days": base["birth_shift_days"],
        "step_months": base["step_months"],
        "date_from": base["date_from"],
        "date_to": base["date_to"],
        "failures": dict(failures),
        "ziwei_unavailable_reason": "; ".join(
            p.get("ziwei_unavailable_reason", "") for p in payloads
            if p.get("ziwei_unavailable_reason")
        ),
        "engine_versions": base.get("engine_versions", {}),
        "per_date_row_count": dict(per_date),
    }


# ---------------------------------------------------------------------------
# 标签
# ---------------------------------------------------------------------------


def adj_factor_index() -> dict[str, Path]:
    """``stock_code -> adj_factor csv``（主快照优先，退市补丁兜底）。"""
    index: dict[str, Path] = {}
    for snapshot in reversed(ADJ_SNAPSHOTS):  # 先写补丁，再被主快照覆盖
        directory = ASTOCKDATA_FACTOR_ROOT / snapshot
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            code = path.stem.split(".")[0]
            index[code] = path
    return index


def load_adj_factors(code: str, index: dict[str, Path], cache: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    if code in cache:
        return cache[code]
    path = index.get(code)
    if path is None:
        cache[code] = None
        return None
    frame = pd.read_csv(path, dtype={"trade_date": str, "adj_factor": float})
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], format="%Y%m%d")
    frame = frame.rename(columns={"adj_factor": "factor"})[["trade_date", "factor"]]
    cache[code] = frame
    return frame


def load_bars_by_code(codes: list[str]) -> dict[str, pd.DataFrame]:
    factory = get_session_factory()
    out: dict[str, pd.DataFrame] = {}
    with factory() as db:
        for start in range(0, len(codes), 100):
            chunk = codes[start:start + 100]
            rows = db.execute(
                select(
                    MarketBarDailyRow.stock_code, MarketBarDailyRow.trade_date,
                    MarketBarDailyRow.close, MarketBarDailyRow.is_degraded,
                ).where(
                    MarketBarDailyRow.stock_code.in_(chunk),
                    MarketBarDailyRow.source == BAR_SOURCE,
                ).order_by(MarketBarDailyRow.stock_code, MarketBarDailyRow.trade_date)
            ).all()
            frame = pd.DataFrame(rows, columns=["stock_code", "trade_date", "close", "is_degraded"])
            for code, group in frame.groupby("stock_code", sort=False):
                out[str(code)] = group.reset_index(drop=True)
    return out


def load_benchmark() -> BenchmarkSeries:
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(MarketBarDailyRow.trade_date, MarketBarDailyRow.close).where(
                MarketBarDailyRow.stock_code == BENCHMARK_CODE
            ).order_by(MarketBarDailyRow.trade_date)
        ).all()
    frame = pd.DataFrame(rows, columns=["trade_date", "close"])
    return BenchmarkSeries.from_frame(frame, code=DEFAULT_BENCHMARK_CODE)


def build_label_panel(
    bars: dict[str, pd.DataFrame], sample_dates: list[date],
) -> tuple[pd.DataFrame, dict]:
    index = adj_factor_index()
    factor_cache: dict[str, pd.DataFrame | None] = {}
    benchmark = load_benchmark()
    rows: list[dict] = []
    coverage_totals: Counter = Counter()
    per_code: list[dict] = []
    for code, frame in bars.items():
        coverage: dict = {}
        produced = compute_forward_returns(
            frame, sample_dates, stock_code=code, horizons=HORIZONS,
            adj_factors=load_adj_factors(code, index, factor_cache),
            benchmark=benchmark,
            is_degraded=bool(frame["is_degraded"].any()),
            coverage_out=coverage,
        )
        rows.extend(produced)
        for key in ("raw_rows", "matched_rows", "filled_rows", "uncovered_rows"):
            coverage_totals[key] += int(coverage.get(key, 0))
        per_code.append({
            "stock_code": code,
            "label_rows": len(produced),
            "adj_raw_rows": coverage.get("raw_rows", 0),
            "adj_matched_rows": coverage.get("matched_rows", 0),
            "adj_filled_rows": coverage.get("filled_rows", 0),
            "adj_uncovered_rows": coverage.get("uncovered_rows", 0),
            "adj_source": "missing" if code not in index else "provided",
            "has_degraded_bars": bool(frame["is_degraded"].any()),
        })
    labels = label_frame(rows)
    # 标签类型：as_of 是 date，trade_date 保留 date 以便 join
    if not labels.empty:
        labels["as_of"] = pd.to_datetime(labels["as_of"]).dt.date
        labels["trade_date"] = pd.to_datetime(labels["trade_date"]).dt.date
    meta = {
        "label_version": LABEL_VERSION,
        "benchmark_code": BENCHMARK_CODE,
        "adj_snapshots": list(ADJ_SNAPSHOTS),
        "adj_factor_files": len(index),
        "codes_with_adj": sum(1 for code in bars if code in index),
        "codes_without_adj": sum(1 for code in bars if code not in index),
        "coverage_totals": dict(coverage_totals),
        "per_code": per_code,
        "label_rows": int(len(labels)),
        "degraded_codes": sorted(
            code for code, frame in bars.items() if bool(frame["is_degraded"].any())
        ),
    }
    return labels, meta


# ---------------------------------------------------------------------------
# 校准
# ---------------------------------------------------------------------------


def fit_holdout_calibration(panel: pd.DataFrame, split, *, group_cols: tuple[str, ...]):
    """固定 holdout 的 cal-v1：只用 TRAIN（<= train_end）拟合一次。"""
    train = panel[panel["partition"] == TRAIN].copy()
    if train.empty:
        raise PanelError("TRAIN 分区为空，无法拟合 cal-v1")
    from src.research.calibration import ResearchCalibrationLayer

    layer = ResearchCalibrationLayer(
        value_col="opinion_score",
        group_cols=group_cols,
        date_col="as_of",
        partition_col="partition",
        calibration_version=CALIBRATION_VERSION,
        fit_partition=TRAIN,
        fit_max_as_of=split.train_end,
    ).fit(train)
    fit_max = pd.to_datetime(train["as_of"]).dt.date.max()
    FREEZE_V1.assert_holdout_fit(fit_max_as_of=fit_max, target_partition=VALIDATION)
    from src.research.oos.walk_forward import calibration_fit_hash

    audit = {
        "calibration_version": CALIBRATION_VERSION,
        "fit_scope": FREEZE_V1.fit_scope,
        "fit_max_as_of": fit_max.isoformat(),
        "train_end": split.train_end.isoformat(),
        "fit_lag_days_vs_train_end": (split.train_end - fit_max).days,
        "fit_row_count": int(len(train)),
        "fit_group_count": len(layer.groups),
        "calibration_fit_hash": calibration_fit_hash(layer),
        "oos_labels_seen": True,
        "layer_metadata": layer.metadata(),
    }
    return layer, audit


# ---------------------------------------------------------------------------
# 结果落盘
# ---------------------------------------------------------------------------


def experiment_row(outcome, spec, split, git_sha: str, capture: dict) -> dict:  # type: ignore[no-untyped-def]
    oos = outcome.partitioned[OOS]
    val = outcome.partitioned[VALIDATION]
    train = outcome.partitioned[TRAIN]
    gate = outcome.gate.to_dict() if outcome.gate else {}
    status = gate.get("status", "EXPLORATORY_NOT_GATED")
    controls = {c["control_kind"]: c for c in outcome.controls}
    position = controls.get("random_event_position", {})
    return {
        "experiment_id": new_experiment_id(spec.hypothesis_id, outcome.birth_model),
        "hypothesis_id": spec.hypothesis_id,
        "object_id": spec.object_id,
        "birth_model": outcome.birth_model,
        "direction_source": spec.direction_source,
        "logic": spec.logic,
        "expected_direction": spec.expected_direction,
        "primary_horizon": spec.primary_horizon,
        "split_version": split.split_version,
        "split_fingerprint": split.fingerprint(),
        "calibration_version": outcome.calibration_audit.get("calibration_version"),
        "calibration_fit_hash": outcome.calibration_audit.get("calibration_fit_hash"),
        "status": status,
        "pending_fdr": gate.get("pending_fdr", None),
        "train_event_count": train["event_count"],
        "train_pool_count": train.get("pool_count"),
        "train_positive_rate": train.get("positive_rate"),
        "validation_event_count": val["event_count"],
        "validation_pool_count": val.get("pool_count"),
        "validation_positive_rate": val.get("positive_rate"),
        "oos_event_count": oos["event_count"],
        "oos_pool_count": oos.get("pool_count"),
        "oos_positive_rate": oos.get("positive_rate"),
        "oos_hit_rate_min": oos["hit_concentration"].get("min_rate"),
        "oos_hit_rate_max": oos["hit_concentration"].get("max_rate"),
        "oos_hit_rate_std": oos["hit_concentration"].get("std_rate"),
        "oos_dates_above_60pct": oos["hit_concentration"].get("dates_above_high"),
        "oos_dates_below_5pct": oos["hit_concentration"].get("dates_below_low"),
        "oos_sample_count": oos["sample_count"],
        "oos_eligible_stock_count": oos["eligible_stock_count"],
        "oos_coverage_start": oos["coverage_start"],
        "oos_coverage_end": oos["coverage_end"],
        "train_mean_excess_return": train["mean_excess_return"],
        "validation_mean_excess_return": val["mean_excess_return"],
        "oos_mean_return": oos["mean_return"],
        "oos_mean_excess_return": oos["mean_excess_return"],
        "oos_up_rate": oos["up_rate"],
        "oos_excess_up_rate": oos["excess_up_rate"],
        "oos_sign": oos["sign"],
        "validation_sign": val["sign"],
        "overlap_ratio": outcome.overlap.get("overlap_ratio"),
        "non_overlapping_event_count": outcome.overlap["non_overlapping_events"]["event_count"],
        "non_overlapping_mean_excess_return": outcome.overlap["non_overlapping_events"]["mean_excess_return"],
        "positive_year_ratio": outcome.year_stability.get("positive_year_ratio"),
        "sign_consistency": outcome.year_stability.get("sign_consistency"),
        "year_count": outcome.year_stability.get("year_count"),
        "top_1_contribution": outcome.stock_dependency.get("top_1_contribution"),
        "top_5_contribution": outcome.stock_dependency.get("top_5_contribution"),
        "loo_sign_flip_count": outcome.stock_dependency.get("loo_sign_flip_count"),
        "loo_mean_min": outcome.stock_dependency.get("loo_mean_min"),
        "loo_mean_max": outcome.stock_dependency.get("loo_mean_max"),
        "stock_count": outcome.stock_dependency.get("stock_count"),
        "single_name_dependent": outcome.stock_dependency.get("single_name_dependent"),
        "control_jaccard": position.get("jaccard_with_real"),
        "control_mean_excess_return": position.get("mean_excess_return"),
        "control_p_value": position.get("p_value"),
        "control_p_value_lower": position.get("p_value_lower"),
        "control_event_count": position.get("event_count"),
        "gate_version": gate.get("gate_version", ""),
        "git_sha": git_sha,
        "dataset_version": split.dataset_version,
        "universe_version": split.universe_version,
        "label_version": LABEL_VERSION,
        "factor_rule_version": capture.get("factor_rule_version", ""),
        "bazi_engine_version": capture.get("bazi_engine_version", ""),
        "ziwei_engine_version": capture.get("ziwei_engine_version", ""),
        "huangli_engine_version": capture.get("huangli_engine_version", ""),
        "warnings": " | ".join(outcome.warnings),
    }


def partition_rows(outcome, spec) -> list[dict]:  # type: ignore[no-untyped-def]
    rows: list[dict] = []
    for partition, stats in outcome.partitioned.items():
        for horizon, values in stats["by_horizon"].items():
            rows.append({
                "hypothesis_id": spec.hypothesis_id,
                "object_id": spec.object_id,
                "birth_model": outcome.birth_model,
                "direction_source": spec.direction_source,
                "partition": partition,
                "horizon": horizon,
                "event_count": stats["event_count"],
                "pool_count": stats.get("pool_count"),
                "positive_rate": stats.get("positive_rate"),
                "sample_count": values.get("sample_count"),
                "eligible_stock_count": stats["eligible_stock_count"],
                "coverage_start": stats["coverage_start"],
                "coverage_end": stats["coverage_end"],
                "mean_return": values.get("mean_return"),
                "median_return": values.get("median_return"),
                "std_return": values.get("std_return"),
                "up_rate": values.get("up_rate"),
                "mean_excess_return": values.get("mean_excess_return"),
                "excess_up_rate": values.get("excess_up_rate"),
                "mean_bench_return": values.get("mean_bench_return"),
            })
    return rows


def concentration_rows(outcome, spec) -> list[dict]:  # type: ignore[no-untyped-def]
    rows: list[dict] = []
    for partition, stats in outcome.partitioned.items():
        item = stats.get("hit_concentration", {})
        rows.append({
            "hypothesis_id": spec.hypothesis_id,
            "object_id": spec.object_id,
            "birth_model": outcome.birth_model,
            "direction_source": spec.direction_source,
            "partition": partition,
            "event_count": stats["event_count"],
            "pool_count": stats.get("pool_count"),
            "positive_rate": stats.get("positive_rate"),
            **item,
        })
    return rows


def control_rows(outcome, spec, split) -> list[dict]:  # type: ignore[no-untyped-def]
    rows: list[dict] = []
    for control in outcome.controls:
        rows.append({
            "hypothesis_id": spec.hypothesis_id,
            "birth_model": outcome.birth_model,
            "partition": OOS,
            "direction_source": spec.direction_source,
            "split_version": split.split_version,
            **control,
            "warnings": " | ".join(control.get("warnings", [])),
        })
    return rows


def year_rows(outcome, spec) -> list[dict]:  # type: ignore[no-untyped-def]
    rows: list[dict] = []
    for item in outcome.year_stability.get("years", []):
        rows.append({
            "hypothesis_id": spec.hypothesis_id,
            "birth_model": outcome.birth_model,
            "partition": OOS,
            "direction_source": spec.direction_source,
            **item,
        })
    return rows


def contribution_rows(outcome, spec) -> list[dict]:  # type: ignore[no-untyped-def]
    rows: list[dict] = []
    for item in outcome.stock_dependency.get("stock_contribution_distribution", [])[:20]:
        rows.append({
            "hypothesis_id": spec.hypothesis_id,
            "birth_model": outcome.birth_model,
            "rank_within_experiment": len(rows) + 1,
            **item,
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _gate_check_value(gate: dict, name: str):  # type: ignore[no-untyped-def]
    for item in gate.get("checks", []):
        if item.get("name") == name:
            return item.get("value")
    return None


def universe_composition() -> dict:
    """universe 的在市 / 退市构成（生存者偏差披露用）。"""
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(
                UniverseMembershipRow.status, func.count(UniverseMembershipRow.id),
            ).where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION
            ).group_by(UniverseMembershipRow.status)
        ).all()
    return {str(status): int(count) for status, count in rows}


def git_sha() -> str:
    try:
        out = subprocess.run(  # noqa: S603 - 固定参数
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def run(args: argparse.Namespace) -> int:
    started = time.time()
    split = default_split(calibration_version=CALIBRATION_VERSION)
    sha = git_sha()
    registry = load_hypothesis_registry(HYPOTHESIS_REGISTRY_PATH)
    print(f"split={split.split_version} fingerprint={split.fingerprint()} sha={sha}", flush=True)
    print(f"hypotheses={len(registry.hypotheses)} git_sha={sha}", flush=True)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    panel_labels = ("main", "monthly_oos", "shift_minus", "shift_plus")
    if args.skip_collect:
        shards = {label: _discover_shards(label) for label in panel_labels}
        missing = [label for label, paths in shards.items() if not paths]
        if missing:
            raise RuntimeError(f"以下面板没有可用分片，无法跳过采集：{missing}")
    else:
        collect_panels(args)
        shards = {label: _discover_shards(label) for label in panel_labels}

    print("合并分片 …", flush=True)
    main_payload = merge_shards(shards["main"])
    monthly_payload = merge_shards(shards["monthly_oos"])
    shift_payloads = {
        "-7": merge_shards(shards["shift_minus"]),
        "7": merge_shards(shards["shift_plus"]),
    }
    expected_codes = sum(universe_composition().values())
    if len(main_payload["codes"]) != expected_codes:
        raise RuntimeError(
            f"主面板股票数 {len(main_payload['codes'])} != universe 成员数 "
            f"{expected_codes}：分片缺失或不完整（禁止在缺股票的面板上做研究）"
        )
    print(
        f"main rows={len(main_payload['rows'])} codes={len(main_payload['codes'])} "
        f"dates={len(main_payload['dates'])} failures={main_payload['failures']}",
        flush=True,
    )

    # --- 面板 ---
    panel_raw = build_observation_panel(main_payload["rows"], split)
    assert_no_out_of_scope(panel_raw, split)
    monthly_raw = build_observation_panel(monthly_payload["rows"], split)
    shift_panels: dict[str, pd.DataFrame] = {}
    for key, payload in shift_payloads.items():
        shift_panel = build_observation_panel(payload["rows"], split)
        shift_panels[key] = shift_panel

    # --- 标签 ---
    codes = main_payload["codes"]
    print(f"读取行情并计算标签（{len(codes)} 只）…", flush=True)
    bars = load_bars_by_code(codes)
    all_dates = sorted({
        date.fromisoformat(value) for value in main_payload["dates"]
    } | {
        date.fromisoformat(value) for value in monthly_payload["dates"]
    })
    labels, label_meta = build_label_panel(bars, all_dates)
    print(
        f"标签 {label_meta['label_rows']} 行；缺 adj 的股票 "
        f"{label_meta['codes_without_adj']} 只；未覆盖除权行 "
        f"{label_meta['coverage_totals'].get('uncovered_rows', 0)}",
        flush=True,
    )
    data_problems: list[str] = []
    if label_meta["degraded_codes"]:
        data_problems.append(f"降级行情 {len(label_meta['degraded_codes'])} 只")
    data_is_real = not label_meta["degraded_codes"]

    # --- cal-v1（只 fit TRAIN） ---
    calibration, calibration_audit = fit_holdout_calibration(
        panel_raw, split, group_cols=("engine", "birth_model"),
    )
    print(
        f"cal-v1 fit: groups={calibration_audit['fit_group_count']} "
        f"hash={calibration_audit['calibration_fit_hash']}",
        flush=True,
    )
    calibrated_panel = attach_calibration(panel_raw, calibration)
    shift_calibrated = {
        key: attach_calibration(frame, calibration) for key, frame in shift_panels.items()
    }

    capture = {
        "factor_rule_version": settings.factor_rule_version,
        "bazi_engine_version": main_payload["engine_versions"].get("bazi", ""),
        "ziwei_engine_version": main_payload["engine_versions"].get("ziwei", ""),
        "huangli_engine_version": main_payload["engine_versions"].get("huangli", ""),
    }

    # --- 固定 holdout 实验 ---
    result_rows: list[dict] = []
    partition_all: list[dict] = []
    control_all: list[dict] = []
    concentration_all: list[dict] = []
    year_all: list[dict] = []
    contribution_all: list[dict] = []
    experiment_records: list[ExperimentRecord] = []
    outcomes: list[tuple[object, object]] = []
    total = len(registry.hypotheses) * len(registry.hypotheses[0].birth_models)
    done = 0
    for spec in registry.hypotheses:
        for birth_model in spec.birth_models:
            outcome = run_hypothesis(
                calibrated_panel=calibrated_panel,
                labels=labels,
                split=split,
                spec=spec,
                birth_model=birth_model,
                calibration_audit=calibration_audit,
                shifted_panels=shift_calibrated,
                data_is_real=data_is_real,
                data_problems=data_problems,
                permutation_draws=args.permutation_draws,
            )
            outcomes.append((spec, outcome))
            row = experiment_row(outcome, spec, split, sha, capture)
            result_rows.append(row)
            partition_all.extend(partition_rows(outcome, spec))
            control_all.extend(control_rows(outcome, spec, split))
            concentration_all.extend(concentration_rows(outcome, spec))
            year_all.extend(year_rows(outcome, spec))
            contribution_all.extend(contribution_rows(outcome, spec))
            gate = outcome.gate.to_dict() if outcome.gate else {}
            oos = outcome.partitioned[OOS]
            experiment_records.append(ExperimentRecord(
                experiment_id=row["experiment_id"],
                hypothesis_id=spec.hypothesis_id,
                git_sha=sha,
                dataset_version=split.dataset_version,
                universe_version=split.universe_version,
                birth_model_version=birth_model,
                factor_version=settings.factor_rule_version,
                calibration_version=CALIBRATION_VERSION,
                split_version=split.split_version,
                train_period=f"{split.train_start}..{split.train_end}",
                validation_period=f"{split.validation_start}..{split.validation_end}",
                oos_period=f"{split.oos_start}..{split.oos_end}",
                horizon=spec.primary_horizon,
                parameters={
                    "logic": spec.logic,
                    "direction_source": spec.direction_source,
                    "expected_direction": spec.expected_direction,
                    "engines": list(spec.engines),
                    "birth_models": list(spec.birth_models),
                    "horizons": list(spec.horizons),
                    "benchmark_code": BENCHMARK_CODE,
                    "permutation_draws": args.permutation_draws,
                    "split_fingerprint": split.fingerprint(),
                    "calibration_fit_hash": calibration_audit["calibration_fit_hash"],
                    "gate_version": gate.get("gate_version", ""),
                    "methodology": "Phase 3D fixed holdout OOS pipeline",
                },
                random_seed=settings.negative_control_seed,
                created_at=utc_timestamp(),
                result_status=row["status"],
                result_reasons=tuple(gate.get("reasons", [])),
                metrics={
                    "event_count": oos["event_count"],
                    "sample_count": oos["sample_count"],
                    "mean_return": oos["mean_return"],
                    "mean_excess_return": oos["mean_excess_return"],
                    "median_return": oos["median_return"],
                    "std_return": oos["std_return"],
                    "up_rate": oos["up_rate"],
                    "excess_up_rate": oos["excess_up_rate"],
                    "cohen_d": _gate_check_value(gate, "G6_effect_size_nonzero"),
                    "welch_p": None,
                    "permutation_p": row["control_p_value"],
                    "pending_fdr": gate.get("pending_fdr"),
                    "gate_version": gate.get("gate_version", ""),
                },
                oos_used=True,
            ))
            done += 1
            print(
                f"[{done}/{total}] {spec.hypothesis_id}::{birth_model} "
                f"OOS n={oos['sample_count']} excess={oos['mean_excess_return']} "
                f"status={row['status']}",
                flush=True,
            )

    # --- walk-forward（逐 fold 重拟合） ---
    print("walk-forward …", flush=True)
    folds = expanding_folds(split, min_train_years=MIN_TRAIN_YEARS)
    wf_specs = [
        spec for spec in registry.hypotheses
        if spec.direction_source == "calibrated"
        and spec.object_id in {
            "bazi_calibrated", "ziwei_calibrated", "huangli_calibrated",
            "all_three_calibrated",
        }
    ]
    wf_rows: list[dict] = []
    for spec in wf_specs:
        for birth_model in spec.birth_models:
            def evaluator(fold, test_frame, _spec=spec, _model=birth_model):  # type: ignore[no-untyped-def]
                events = event_frame(
                    direction_matrix(
                        test_frame, _spec, birth_model=_model, source=_spec.direction_source
                    ),
                    labels,
                )
                if not events.empty:
                    events = events.copy()
                    events["partition"] = [
                        split.partition_of(v) for v in events["as_of"]
                    ]
                horizon = _spec.primary_horizon
                stats: dict = {}
                for h in _spec.horizons:
                    column = f"excess_return_{h}d"
                    values = (
                        pd.to_numeric(events[column], errors="coerce").dropna()
                        if len(events) and column in events.columns
                        else pd.Series(dtype=float)
                    )
                    stats[f"horizon_{h}d_sample_count"] = int(len(values))
                    stats[f"horizon_{h}d_mean_excess_return"] = (
                        round(float(values.mean()), 6) if len(values) else None
                    )
                excess = (
                    pd.to_numeric(events[f"excess_return_{horizon}d"], errors="coerce").dropna()
                    if len(events) else pd.Series(dtype=float)
                )
                control_mean = None
                control_p = None
                if len(excess):
                    rng = np.random.default_rng(
                        settings.negative_control_seed + fold.test_year
                    )
                    label_column = f"excess_return_{horizon}d"
                    # 对照池必须与 fold 的测试期同区间：用全历史池会让测试年自身的
                    # 市场环境差异被误读成"击败对照"。
                    as_of_dates = pd.to_datetime(labels["as_of"]).dt.date
                    fold_pool = labels[
                        (as_of_dates >= fold.test_start) & (as_of_dates <= fold.test_end)
                    ]
                    pool = pd.to_numeric(
                        fold_pool[label_column], errors="coerce"
                    ).dropna().to_numpy(dtype=float)
                    draws = np.asarray([
                        pool[rng.choice(len(pool), size=min(len(excess), len(pool)),
                                        replace=False)].mean()
                        for _ in range(200)
                    ]) if len(pool) else np.asarray([])
                    if draws.size:
                        control_mean = round(float(draws.mean()), 6)
                        control_p = float(
                            (np.sum(draws >= float(excess.mean())) + 1) / (draws.size + 1)
                        )
                status = "NOT_RUN"
                if len(excess):
                    status = (
                        "OUTPERFORM_CONTROL"
                        if control_mean is not None
                        and float(excess.mean()) > control_mean
                        and (control_p or 1.0) < 0.05
                        else "NO_SIGNAL"
                    )
                return {
                    "stock_count": int(events["stock_code"].nunique()) if len(events) else 0,
                    "event_count": int(len(events)),
                    "sample_count": int(len(excess)),
                    "mean_excess_return": round(float(excess.mean()), 6) if len(excess) else None,
                    "up_rate": round(float((excess > 0).mean()), 6) if len(excess) else None,
                    "sign": int(np.sign(float(excess.mean()))) if len(excess) else 0,
                    "negative_control_mean_excess_return": control_mean,
                    "negative_control_p_value": control_p,
                    "research_status": status,
                    **stats,
                }

            result = run_walk_forward(
                calibrated_panel, folds, evaluator,
                value_col="opinion_score", group_cols=("engine", "birth_model"),
            )
            for record in result.folds:
                wf_rows.append({
                    "hypothesis_id": spec.hypothesis_id,
                    "birth_model": birth_model,
                    "direction_source": spec.direction_source,
                    "split_version": split.split_version,
                    **record,
                })

    # --- 重叠敏感性（月度 OOS 子面板） ---
    print("重叠敏感性（月度 OOS 子面板）…", flush=True)
    overlap_rows: list[dict] = []
    monthly_calibrated = attach_calibration(monthly_raw, calibration)
    overlap_objects = {
        "bazi_raw", "bazi_calibrated", "ziwei_calibrated", "huangli_calibrated",
        "all_three_calibrated",
    }
    for spec in registry.hypotheses:
        if spec.object_id not in overlap_objects:
            continue
        monthly_panel = (
            monthly_calibrated if spec.direction_source == "calibrated" else monthly_raw
        )
        for birth_model in spec.birth_models:
            events = event_frame(
                direction_matrix(
                    monthly_panel, spec, birth_model=birth_model,
                    source=spec.direction_source,
                ),
                labels,
            )
            if not events.empty:
                events = events.copy()
                events["partition"] = [split.partition_of(v) for v in events["as_of"]]
                events = events[events["partition"] == OOS]
            block = overlap_block(events, spec.primary_horizon)
            overlap_rows.append({
                "hypothesis_id": spec.hypothesis_id,
                "object_id": spec.object_id,
                "birth_model": birth_model,
                "direction_source": spec.direction_source,
                "panel": "monthly_oos",
                "horizon": spec.primary_horizon,
                "event_count": block["all_events"]["event_count"],
                "mean_excess_return_all": block["all_events"]["mean_excess_return"],
                "overlap_ratio": block["overlap_ratio"],
                "non_overlapping_event_count": block["non_overlapping_events"]["event_count"],
                "mean_excess_return_non_overlapping":
                    block["non_overlapping_events"]["mean_excess_return"],
                "up_rate_all": block["all_events"]["up_rate"],
                "up_rate_non_overlapping": block["non_overlapping_events"]["up_rate"],
            })

    # --- 产物 ---
    print("写入产物 …", flush=True)
    write_csv(OUT_DIR / "phase3d_oos_results.csv", result_rows)
    write_csv(OUT_DIR / "phase3d_oos_partition_stats.csv", partition_all)
    write_csv(OUT_DIR / "phase3d_oos_controls.csv", control_all)
    write_csv(OUT_DIR / "phase3d_oos_hit_concentration.csv", concentration_all)
    write_csv(OUT_DIR / "phase3d_oos_year_stability.csv", year_all)
    write_csv(OUT_DIR / "phase3d_stock_contribution_top20.csv", contribution_all)
    write_csv(OUT_DIR / "phase3d_walkforward_results.csv", wf_rows)
    write_csv(OUT_DIR / "phase3d_overlap_sensitivity.csv", overlap_rows)
    write_experiment_registry_csv(
        experiment_records, OUT_DIR / "phase3d_experiment_registry.csv"
    )
    write_registry_json(
        {
            "hypothesis_registry": registry.to_dict(),
            "registry_path": str(HYPOTHESIS_REGISTRY_PATH.relative_to(ROOT)),
            "gate_thresholds": gate_thresholds(),
            "split": split.to_dict(),
            "calibration_freeze": FREEZE_V1.to_dict(),
        },
        OUT_DIR / "phase3d_hypothesis_registry.json",
    )
    write_registry_json(
        {
            "freeze": FREEZE_V1.to_dict(),
            "holdout_fit": {
                k: v for k, v in calibration_audit.items() if k != "layer_metadata"
            },
            "layer": calibration_audit["layer_metadata"],
            "label": {k: v for k, v in label_meta.items() if k != "per_code"},
        },
        OUT_DIR / "phase3d_calibration_freeze.json",
    )
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha,
        "split": split.to_dict(),
        "gate_thresholds": gate_thresholds(),
        "calibration": {
            k: v for k, v in calibration_audit.items() if k != "layer_metadata"
        },
        "labels": {k: v for k, v in label_meta.items() if k != "per_code"},
        "universe_composition": universe_composition(),
        "panel": {
            "main_rows": int(len(panel_raw)),
            "main_dates": len(main_payload["dates"]),
            "main_codes": len(main_payload["codes"]),
            "monthly_rows": int(len(monthly_raw)),
            "monthly_dates": len(monthly_payload["dates"]),
            "shift_dates": len(shift_payloads["-7"]["dates"]),
            "failures": main_payload["failures"],
            "engine_versions": main_payload["engine_versions"],
            "ziwei_unavailable_reason": main_payload["ziwei_unavailable_reason"],
        },
        "experiment_count": len(experiment_records),
        "hypothesis_count": len(registry.hypotheses),
        "walkforward_fold_count": len(folds),
        "walkforward_row_count": len(wf_rows),
        "status_counts": dict(Counter(row["status"] for row in result_rows)),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    write_registry_json(summary, OUT_DIR / "phase3d_run_summary.json")

    if args.persist_db:
        written = persist_experiments(experiment_records)
        print(f"已写入 backtest_experiment: {written} 条", flush=True)

    print(f"完成，用时 {time.time() - started:.0f}s", flush=True)
    print(json.dumps(summary["status_counts"], ensure_ascii=False), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3D OOS / walk-forward 研究管线")
    parser.add_argument("--parallel", type=int, default=8, help="采集并行进程数")
    parser.add_argument("--step-months", type=int, default=3, help="主面板采样步长（月）")
    parser.add_argument("--date-to", default="2026-08-14")
    parser.add_argument("--permutation-draws", type=int, default=200)
    parser.add_argument("--reuse-cache", action="store_true", help="复用已存在的分片")
    parser.add_argument("--skip-collect", action="store_true", help="完全跳过采集（只用缓存）")
    parser.add_argument("--persist-db", action="store_true", help="把实验登记写进 backtest_experiment")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
