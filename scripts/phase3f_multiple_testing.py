"""Phase 3F 多重检验 / 稳健性管线。

一条命令完成：
    1. 复用 3E 的研究数据集（同一份标签、同一份 cal-v1、同一套事件定义）
    2. 对 3D 的 54 个实验逐条做日期分层置换检验（默认 5000 次）
    3. date-block bootstrap 置信区间（mean / hit−non-hit 差）
    4. 效应量（mean difference / Cohen's d / RankIC）
    5. 九个稳健性维度 + 出生模型对比族
    6. 族内 BH-FDR（``mt-v1`` 冻结族定义）+ Bonferroni
    7. ``gate-v2``（A–L）：唯一允许解锁 SUPPORTED_OUT_OF_SAMPLE 的路径
    8. 与 ``gate-v1``（3D）**并排**输出，不覆盖 3D 记录

用法::

    python scripts/phase3f_multiple_testing.py
    python scripts/phase3f_multiple_testing.py --permutation-draws 1000 --smoke
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.research.labels import panel as label_panel  # noqa: E402
from src.research.multipletesting.families import load_family_registry  # noqa: E402
from src.research.multipletesting.gate_v2 import gate_v2_thresholds  # noqa: E402
from src.research.multipletesting.robustness import (  # noqa: E402
    compute_adjustment_sources,
    compute_market_regimes,
    patch_only_codes,
)
from src.research.multipletesting.runner import (  # noqa: E402
    MULTIPLE_TESTING_RUN_VERSION,
    PRIMARY_HORIZON,
    _load_3d_controls,
    _load_3d_results,
    _load_3e_neutralization,
    run_multiple_testing,
)
from src.research.neutralization.dataset import build_research_dataset  # noqa: E402
from src.research.oos.calibration_freeze import CALIBRATION_VERSION  # noqa: E402
from src.research.oos.gates import GATE_VERSION as GATE_V1_VERSION  # noqa: E402
from src.research.oos.registry import load_hypothesis_registry  # noqa: E402
from src.research.oos.splits import default_split  # noqa: E402

CACHE_DIR = ROOT / "data" / "phase3_universe" / "phase3d_cache"
OUT_DIR = ROOT / "data" / "phase3_universe"
HYPOTHESIS_REGISTRY_PATH = ROOT / "config" / "phase3d_hypothesis_registry.yaml"
FAMILY_REGISTRY_PATH = ROOT / "config" / "phase3f_multiple_testing_families.yaml"
CONTROLS_3D_PATH = OUT_DIR / "phase3d_oos_controls.csv"
RESULTS_3D_PATH = OUT_DIR / "phase3d_oos_results.csv"
NEUTRALIZATION_3E_PATH = OUT_DIR / "phase3e_neutralization_results.csv"
ASTOCKDATA_FACTOR_ROOT = label_panel.ASTOCKDATA_FACTOR_ROOT


def git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def load_delisted_codes(universe_version: str) -> set[str]:
    """退市股清单（用于 universe_subset 稳健性维度）。"""
    import sqlite3

    from src.db.models import UniverseMembershipRow  # noqa: F401 - 仅用于导入校验
    from src.research.oos.splits import UNIVERSE_VERSION as default_version

    db_path = ROOT / "data" / "smp.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "select stock_code from universe_memberships "
            "where universe_version = ? and status = 'delisted'",
            (universe_version or default_version,),
        ).fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def run(args: argparse.Namespace) -> int:
    started = time.time()
    split = default_split(calibration_version=CALIBRATION_VERSION)
    hypothesis_registry = load_hypothesis_registry(HYPOTHESIS_REGISTRY_PATH)
    family_registry = load_family_registry(FAMILY_REGISTRY_PATH)
    family_registry.validate_against(tuple(hypothesis_registry.ids()))
    sha = git_sha()
    print(
        f"sha={sha} mt_version={family_registry.mt_version} "
        f"families={len(family_registry.families)} hypotheses={len(hypothesis_registry.hypotheses)}",
        flush=True,
    )

    def progress(message: str) -> None:
        print(f"[{time.time() - started:6.0f}s] {message}", flush=True)

    cache_dir = CACHE_DIR
    limit = args.limit_stocks
    temp_dir = None
    if limit:
        import pickle
        import tempfile

        from src.research.neutralization.dataset import merge_shards

        progress(f"冒烟模式：限制 {limit} 只股票")
        payload = merge_shards(sorted(CACHE_DIR.glob("main_shard[0-9][0-9].pkl"))[:1])
        codes = set(payload["codes"][:limit])
        payload = {
            **payload,
            "rows": [row for row in payload["rows"] if row["stock_code"] in codes],
            "codes": sorted(codes),
        }
        temp_dir = Path(tempfile.mkdtemp())
        with (temp_dir / "main_shard00.pkl").open("wb") as handle:
            pickle.dump(payload, handle)
        cache_dir = temp_dir

    dataset = build_research_dataset(
        cache_dir=cache_dir, registry=hypothesis_registry, split=split, progress=progress,
    )
    progress(
        f"数据集 rows={len(dataset.frame)} objects={len(dataset.object_ids)} "
        f"models={list(dataset.birth_models)}"
    )

    frames = dataset.frame
    oos_codes = sorted(frames[frames["partition"] == "OOS"]["stock_code"].unique())
    benchmark = label_panel.load_benchmark()
    regimes = compute_market_regimes(
        sorted(set(frames["as_of"])), benchmark.dates, benchmark.closes,
    )
    progress(f"市场状态标签：{len(regimes)} 个 as_of（up/down）")

    adjustment_sources = compute_adjustment_sources(ASTOCKDATA_FACTOR_ROOT)
    patch_only = patch_only_codes(adjustment_sources)
    delisted = load_delisted_codes(split.universe_version)
    progress(f"退市股 {len(delisted)} 只；退市补丁独有除权因子 {len(patch_only)} 只")

    controls_3d = _load_3d_controls(CONTROLS_3D_PATH)
    results_3d = _load_3d_results(RESULTS_3D_PATH)
    neutralization_3e = _load_3e_neutralization(NEUTRALIZATION_3E_PATH)
    progress(
        f"读取 3D 产物：对照组 {len(controls_3d)}、实验 {len(results_3d)}；"
        f"3E 中性化 {len(neutralization_3e)}"
    )
    if not controls_3d or not results_3d:
        raise RuntimeError(
            "缺少 Phase 3D 产物（phase3d_oos_controls.csv / phase3d_oos_results.csv）；"
            "3F 必须读取 3D 的负对照与原始状态，不得自行重算替代。"
        )

    outcome = run_multiple_testing(
        dataset=dataset,
        registry=family_registry,
        controls_3d=controls_3d,
        results_3d=results_3d,
        neutralization_3e=neutralization_3e,
        permutation_count=args.permutation_draws,
        bootstrap_count=args.bootstrap_draws,
        base_seed=args.seed,
        calendar_dates=benchmark.dates,
        regimes=regimes,
        delisted_codes=delisted,
        patch_only_codes=patch_only,
        contrast_permutation_count=args.permutation_draws,
        progress=progress,
    )
    progress(f"实验行 {len(outcome.experiment_rows)}；稳健性行 {len(outcome.robustness_rows)}")

    meta = {
        **outcome.meta,
        "run_version": MULTIPLE_TESTING_RUN_VERSION,
        "git_sha": sha,
        "generated_at": pd.Timestamp.now().isoformat(),
        "split_version": split.split_version,
        "split_fingerprint": split.fingerprint(),
        "calibration_version": CALIBRATION_VERSION,
        "calibration_fit_hash": dataset.calibration_audit["calibration_fit_hash"],
        "label_version": split.label_version,
        "universe_version": split.universe_version,
        "dataset_version": split.dataset_version,
        "hypothesis_registry_version": hypothesis_registry.version,
        "gate_v1_version": GATE_V1_VERSION,
        "gate_v2_thresholds": gate_v2_thresholds(),
        "primary_horizon": PRIMARY_HORIZON,
        "delisted_stock_count": len(delisted),
        "patch_only_adj_codes": len(patch_only),
        "oos_stock_count": len(oos_codes),
        "market_regime_dates": {str(key): value for key, value in sorted(regimes.items())},
    }

    if args.smoke:
        progress("冒烟模式：不写正式产物")
        print(json.dumps(outcome.meta["family_summaries"], ensure_ascii=False, indent=2)[:4000])
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(outcome.experiment_rows).to_csv(
        OUT_DIR / "phase3f_multiple_testing_results.csv", index=False, encoding="utf-8-sig",
    )
    pd.DataFrame(outcome.robustness_rows).to_csv(
        OUT_DIR / "phase3f_robustness_slices.csv", index=False, encoding="utf-8-sig",
    )
    family_rows: list[dict] = []
    for summary in outcome.family_summaries:
        for row in summary["rows"]:
            family_rows.append({
                "family_id": summary["family_id"],
                "alpha": summary["alpha"],
                "mt_version": summary["mt_version"],
                "family_test_count": summary["evaluable_count"],
                "hypothesis_id": row.get("hypothesis_id"),
                "object_id": row.get("object_id"),
                "birth_model": row.get("birth_model"),
                "raw_p_value": row.get("raw_p_value"),
                "p_value_test": row.get("p_value_test"),
                "bonferroni_threshold": row.get("bonferroni_threshold"),
                "bonferroni_pass": row.get("bonferroni_pass"),
                "fdr_q_value": row.get("fdr_q_value"),
                "fdr_pass": row.get("fdr_pass"),
                "gate_v1_status": row.get("gate_v1_status"),
                "gate_v2_status": row.get("gate_v2_status"),
            })
    pd.DataFrame(family_rows).to_csv(
        OUT_DIR / "phase3f_family_correction.csv", index=False, encoding="utf-8-sig",
    )
    (OUT_DIR / "phase3f_run_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    print(f"wrote {OUT_DIR / 'phase3f_run_summary.json'}", flush=True)

    # --- 控制台摘要 ---
    experiment_frame = pd.DataFrame(outcome.experiment_rows)
    gated = experiment_frame[experiment_frame["family_gated"] == True]  # noqa: E712
    print("\n=== 族内校正摘要 ===", flush=True)
    for summary in outcome.family_summaries:
        print(
            f"  {summary['family_id']:26s} m={summary['evaluable_count']:3d} "
            f"min_p={summary['min_raw_p']} "
            f"bonferroni_pass={summary['bonferroni_pass_count']} "
            f"fdr_pass={summary['fdr_pass_count']}",
            flush=True,
        )
    print("\n=== gate-v2 状态分布（正式 gate 实验）===", flush=True)
    print(gated["gate_v2_status"].value_counts().to_dict(), flush=True)
    print("\n=== gate-v1（3D 原始）状态分布 ===", flush=True)
    print(gated["gate_v1_status"].value_counts().to_dict(), flush=True)
    print(f"\n完成，用时 {time.time() - started:.0f}s", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3F 多重检验 / 稳健性管线")
    parser.add_argument("--permutation-draws", type=int, default=5000)
    parser.add_argument("--bootstrap-draws", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--limit-stocks", type=int, default=0, help="冒烟：只取前 N 只股票")
    parser.add_argument("--smoke", action="store_true", help="冒烟：不写正式产物")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
