"""Phase 3D 端到端冒烟测试（小样本，不落正式产物）。

用法::

    python scripts/phase3d_smoke.py [--codes 30] [--step-months 12]

它跑通：采集 → 标签 → cal-v1 → 假设 → 负对照 → 状态门 → walk-forward，
用小样本与少量置换次数验证管线连通性；**不写** phase3d_* 正式产物。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import phase3d_oos_pipeline as pipe  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3D 冒烟测试")
    parser.add_argument("--codes", type=int, default=30)
    parser.add_argument("--step-months", type=int, default=12)
    parser.add_argument("--draws", type=int, default=40)
    args = parser.parse_args()
    started = time.time()

    split = pipe.default_split(calibration_version=pipe.CALIBRATION_VERSION)
    registry = pipe.load_hypothesis_registry(pipe.HYPOTHESIS_REGISTRY_PATH)

    # 1) 采集（单进程、小样本）
    dates = pipe.__dict__  # noqa: F841 - 仅防误用
    from phase3d_collect_panel import PanelCollector, load_profiles, load_universe, sample_dates

    codes, eligibility = load_universe(limit=args.codes)
    profiles = load_profiles(codes)
    collector = PanelCollector(
        codes, profiles, eligibility=eligibility, birth_shift_days=0, skip_ziwei=False
    )
    sample = sample_dates(date(2010, 1, 1), date(2026, 8, 14), args.step_months)
    rows: list[dict] = []
    for as_of in sample:
        rows.extend(collector.compute_date(as_of))
    print(f"采集 {len(rows)} 行 / {len(sample)} 个 as_of / {len(codes)} 只", flush=True)

    panel_raw = pipe.build_observation_panel(rows, split)
    pipe.assert_no_out_of_scope(panel_raw, split)

    # 2) 标签
    bars = pipe.load_bars_by_code(codes)
    labels, label_meta = pipe.build_label_panel(bars, sample)
    print(f"标签 {label_meta['label_rows']} 行", flush=True)

    # 3) cal-v1
    calibration, audit = pipe.fit_holdout_calibration(
        panel_raw, split, group_cols=("engine", "birth_model")
    )
    print(f"cal-v1 hash={audit['calibration_fit_hash']} rows={audit['fit_row_count']}", flush=True)
    calibrated = pipe.attach_calibration(panel_raw, calibration)

    # 4) 前 3 个假设 × 第一个出生模型
    from src.research.oos.runner import run_hypothesis

    for spec in registry.hypotheses[:3]:
        birth_model = spec.birth_models[0]
        outcome = run_hypothesis(
            calibrated_panel=calibrated, labels=labels, split=split, spec=spec,
            birth_model=birth_model, calibration_audit=audit,
            permutation_draws=args.draws,
        )
        oos = outcome.partitioned["OOS"]
        print(
            f"{spec.hypothesis_id}::{birth_model} OOS events={oos['event_count']} "
            f"sample={oos['sample_count']} excess={oos['mean_excess_return']} "
            f"status={outcome.gate.status.value if outcome.gate else 'EXPLORATORY'}",
            flush=True,
        )
        for control in outcome.controls:
            print(
                f"    control {control['control_kind']}: n={control['event_count']} "
                f"jaccard={control['jaccard_with_real']} delta={control['delta_mean_excess_vs_real']} "
                f"p={control['p_value']}",
                flush=True,
            )
    print(f"冒烟完成，用时 {time.time() - started:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
