"""Phase 3E 中性化管线（市场 / 行业 / 风格）+ 黄历日期效应。

一条命令完成：
    1. 组装研究数据集（复用 Phase 3D 缓存分片 + cal-v1 冻结校准 + 统一标签）
    2. 计算风格暴露（momentum / volatility / 流动性规模代理；value 与真实市值显式不可用）
    3. 市场中性（个股 − 沪深 300，同一日历区间）、板块控制、风格正交化
    4. 横截面统计（date-clustered RankIC / 分组收益 / long-short / 回归系数）
    5. 黄历日期效应分析（把"500 只股票"折叠成"16 个日期"的 P0 统计修正）
    6. 产出 CSV / JSON + 逐日日期表

**本脚本不修改任何 Phase 3D 结果**：它是叠加在 3D 冻结协议之上的一层分析，
事件定义、分区、校准版本、持有期全部照搬 3D。

用法::

    python scripts/phase3e_neutralization.py
    python scripts/phase3e_neutralization.py --limit-stocks 40   # 冒烟
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

from src.research.neutralization.dataset import (  # noqa: E402
    build_research_dataset,
)
from src.research.neutralization.runner import (  # noqa: E402
    answer_questions,
    run_neutralization,
)
from src.research.oos.calibration_freeze import CALIBRATION_VERSION  # noqa: E402
from src.research.oos.registry import load_hypothesis_registry  # noqa: E402
from src.research.oos.splits import default_split  # noqa: E402

CACHE_DIR = ROOT / "data" / "phase3_universe" / "phase3d_cache"
OUT_DIR = ROOT / "data" / "phase3_universe"
HYPOTHESIS_REGISTRY_PATH = ROOT / "config" / "phase3d_hypothesis_registry.yaml"


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"wrote {path} rows={len(rows)}", flush=True)


def git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001 - 无 git 时如实标记
        return "UNKNOWN"


def run(args: argparse.Namespace) -> int:
    started = time.time()
    split = default_split(calibration_version=CALIBRATION_VERSION)
    registry = load_hypothesis_registry(HYPOTHESIS_REGISTRY_PATH)
    sha = git_sha()
    print(f"sha={sha} split={split.split_version} hypotheses={len(registry.hypotheses)}", flush=True)

    def progress(message: str) -> None:
        print(f"[{time.time() - started:6.0f}s] {message}", flush=True)

    if args.limit_stocks:
        # 冒烟模式：只读前 N 只股票的分片行，不写正式产物
        progress(f"冒烟模式：限制 {args.limit_stocks} 只股票")
        import pickle

        from src.research.neutralization.dataset import merge_shards

        payload = merge_shards(sorted(CACHE_DIR.glob("main_shard[0-9][0-9].pkl"))[:1])
        codes = set(payload["codes"][: args.limit_stocks])
        payload = {**payload, "rows": [row for row in payload["rows"] if row["stock_code"] in codes],
                   "codes": sorted(codes)}
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        with (tmp / "main_shard00.pkl").open("wb") as handle:
            pickle.dump(payload, handle)
        dataset = build_research_dataset(
            cache_dir=tmp, registry=registry, split=split,
            with_exposures=not args.skip_exposures, progress=progress,
        )
    else:
        dataset = build_research_dataset(
            cache_dir=CACHE_DIR, registry=registry, split=split,
            with_exposures=not args.skip_exposures, progress=progress,
        )
    progress(
        f"数据集：rows={len(dataset.frame)} objects={len(dataset.object_ids)} "
        f"models={list(dataset.birth_models)}"
    )
    print(
        f"cal-v1 fit hash={dataset.calibration_audit['calibration_fit_hash']} "
        f"fit_max_as_of={dataset.calibration_audit['fit_max_as_of']}",
        flush=True,
    )
    if dataset.exposure_meta:
        for column, stats in dataset.exposure_meta.get("columns", {}).items():
            print(f"  exposure {column}: coverage={stats['coverage_ratio']}", flush=True)
    print(f"  labels={len(dataset.labels)} degraded={len(dataset.label_meta.get('degraded_codes', []))}")

    progress("执行中性化分析 …")
    outcome = run_neutralization(
        dataset=dataset,
        horizons=split.horizons,
        primary_horizon=split.primary_horizon,
        include_date_effect=not args.skip_date_effect,
    )
    progress(f"中性化行数：{len(outcome.rows)}")

    answers = answer_questions(outcome.rows, primary_horizon=split.primary_horizon)

    meta = {
        "neutralization_version": outcome.meta["neutralization_version"],
        "git_sha": sha,
        "generated_at": pd.Timestamp.now().isoformat(),
        "split_version": split.split_version,
        "split_fingerprint": split.fingerprint(),
        "calibration_version": CALIBRATION_VERSION,
        "calibration_fit_hash": dataset.calibration_audit["calibration_fit_hash"],
        "calibration_fit_max_as_of": dataset.calibration_audit["fit_max_as_of"],
        "label_version": split.label_version,
        "universe_version": split.universe_version,
        "dataset_version": split.dataset_version,
        "hypothesis_registry_version": registry.version,
        "hypothesis_count": len(registry.hypotheses),
        "oos_labels_seen_at_registration": registry.oos_labels_seen_at_registration,
        "object_count": len(dataset.object_ids),
        "birth_models": list(dataset.birth_models),
        "row_count": len(outcome.rows),
        "label_rows": int(len(dataset.labels)),
        "label_meta_summary": {
            key: value for key, value in dataset.label_meta.items() if key != "per_code"
        },
        "benchmark": outcome.meta["benchmark"],
        "exposures": outcome.meta["exposures"],
        "industry": outcome.meta["industry"],
        "segments": outcome.meta["segments"],
        "questions": answers,
    }

    if args.limit_stocks:
        progress("冒烟模式：不写正式产物")
        print(json.dumps(answers, ensure_ascii=False, indent=2)[:3000], flush=True)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_DIR / "phase3e_neutralization_results.csv", outcome.rows)
    (OUT_DIR / "phase3e_neutralization_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    print(f"wrote {OUT_DIR / 'phase3e_neutralization_meta.json'}", flush=True)

    for name, table in outcome.date_tables.items():
        path = OUT_DIR / f"phase3e_huangli_dates__{name}.csv"
        table.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"wrote {path} rows={len(table)}", flush=True)

    exposure_rows = [
        {"column": column, **stats}
        for column, stats in (dataset.exposure_meta.get("columns") or {}).items()
    ]
    if exposure_rows:
        write_csv(OUT_DIR / "phase3e_exposure_coverage.csv", exposure_rows)

    print(f"完成，用时 {time.time() - started:.0f}s", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3E 中性化管线")
    parser.add_argument("--limit-stocks", type=int, default=0, help="冒烟：只取前 N 只股票")
    parser.add_argument("--skip-exposures", action="store_true", help="跳过风格暴露（调试）")
    parser.add_argument("--skip-date-effect", action="store_true", help="跳过日期效应（调试）")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
