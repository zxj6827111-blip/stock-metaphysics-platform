"""Phase 4E · 全市场中性化（真实 size/value）：``phase4-neutralization-v1``。

这是什么，不是什么
------------------
**是**：在**全市场** universe（``v4-full``，6,104 只）上，用**真实总市值与逐日 PIT 估值**
（``phase4-exposures-v2``）重做市场 / 板块 / 风格中性化，与 Phase 3E 并排报告。

**不是**：不是 Phase 3E 的替代品，也不修改 Phase 3 的任何结论。差异清单：

===========================  ==================================  ==================================
                             Phase 3E（冻结）                      Phase 4E（本次）
===========================  ==================================  ==================================
universe                     ``v2-phase3a`` 500 只                 ``v4-full`` 6,104 只
校准                         ``cal-v1``（TRAIN=500 只）            ``cal-v2``（TRAIN=全市场）
size 口径                    20 日均成交额对数（流动性代理）        **log(total_mv)** 真实总市值
value 口径                   **不可得**                            1/pe_ttm、1/pb（逐日 PIT）
流动性                       无                                    ``turnover_free_20d``
事件定义（objects/logic）     **完全相同**（同一份注册表）          **完全相同**（不新增假设）
===========================  ==================================  ==================================

**纪律**：假设与对象定义一个字都没改（``config/phase3d_hypothesis_registry.yaml``），
所以本阶段不是"换一套假设再搜"，而是"同一套假设、更强的控制变量、更大的样本"。
``cal-v2`` 是**新版本号**，不覆盖 ``cal-v1``；退市股（308 只）没有估值 →
它们的 size/value 为 NaN，由覆盖比例如实披露。

产物
----
    data/phase4_universe/phase4_neutralization_results.csv
    data/phase4_universe/phase4_neutralization_meta.json
    data/phase4_universe/phase4_label_cache.parquet      （标签缓存，重跑免采集）
    docs/phase4-neutralization-size-value.md

用法::

    python scripts/phase4_neutralization.py                  # 全量
    python scripts/phase4_neutralization.py --limit 200      # 冒烟
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market.providers.vendor_parquet import (  # noqa: E402
    VENDOR_DATA_VERSION,
    VendorParquetProvider,
)
from src.research.labels.horizon_returns import (  # noqa: E402
    HORIZONS,
    PRIMARY_HORIZON,
    BenchmarkSeries,
    compute_forward_returns,
)
from src.research.labels.panel import load_benchmark  # noqa: E402
from src.research.neutralization.benchmark import attach_market_excess  # noqa: E402
from src.research.neutralization.dataset import build_object_wide  # noqa: E402
from src.research.neutralization.exposures import zscore_cross_section  # noqa: E402
from src.research.neutralization.exposures_v2 import (  # noqa: E402
    EXPOSURE_VERSION_V2,
    STYLE_EXPOSURE_COLUMNS_V2,
    exposure_availability_v2,
)
from src.research.neutralization.industry import attach_segment  # noqa: E402
from src.research.neutralization.runner import (  # noqa: E402
    answer_questions,
    run_neutralization,
)
from src.research.oos.calibration_freeze import (  # noqa: E402
    CALIBRATION_VERSION,
    freeze_for,
)
from src.research.oos.registry import load_hypothesis_registry  # noqa: E402
from src.research.oos.runner import (  # noqa: E402
    assert_no_out_of_scope,
    attach_calibration,
    build_observation_panel,
)
from src.research.oos.splits import (  # noqa: E402
    OOS,
    TRAIN,
    VALIDATION,
    default_split,
)

UNIVERSE_VERSION = "v4-full"
CACHE_DIR = ROOT / "data" / "phase4_cache"
OUT_DIR = ROOT / "data" / "phase4_universe"
VENDOR_DIR = ROOT / "data" / "vendor"
DOCS_DIR = ROOT / "docs"
HYPOTHESIS_REGISTRY_PATH = ROOT / "config" / "phase3d_hypothesis_registry.yaml"
LABEL_CACHE = OUT_DIR / "phase4_label_cache.parquet"
#: Phase 4 的校准与中性化版本号（新版本，不覆盖 cal-v1 / phase3e-*）
CALIBRATION_VERSION_V2 = "cal-v2"
NEUTRALIZATION_VERSION_V2 = "phase4-neutralization-v1"
#: 三个出生模型（与 Phase 3B 相同的版本后缀）
MODEL_VERSIONS: dict[str, str] = {
    "listing_open_v1": "v1-phase3b-listing_open",
    "listing_close_v1": "v1-phase3b-listing_close",
    "ipo_approx_v1": "v1-phase3b-ipo_approx",
}


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_panel() -> dict:
    """读取合并面板（优先 merged_panel.pkl，否则现场合并分片）。"""
    merged = CACHE_DIR / "merged_panel.pkl"
    if not merged.is_file():
        raise SystemExit(
            f"缺少合并面板：{merged}\n请先运行："
            "python scripts/phase4_collect_panel.py --merge"
        )
    with merged.open("rb") as handle:
        return pickle.load(handle)


def build_label_panel_v4(
    provider: VendorParquetProvider, codes: list[str], as_ofs: list[date],
) -> tuple[pd.DataFrame, dict]:
    """用供应商行情 + 后复权因子 + SQLite 基准构造全市场标签。"""
    if LABEL_CACHE.is_file():
        cached = pd.read_parquet(LABEL_CACHE)
        cached["as_of"] = pd.to_datetime(cached["as_of"]).dt.date
        cached["trade_date"] = pd.to_datetime(cached["trade_date"]).dt.date
        log(f"复用标签缓存：{len(cached):,} 行")
        return cached, {"cache": "hit", "label_rows": int(len(cached))}

    benchmark: BenchmarkSeries = load_benchmark()
    rows: list[dict] = []
    missing_return: dict[str, int] = {}
    started = time.time()
    for order, code in enumerate(codes):
        if order % 500 == 0:
            log(f"标签 {order}/{len(codes)} … 行数 {len(rows):,} "
                f"({time.time() - started:.0f}s)")
        try:
            bars = provider.bars_frame(code)
        except Exception:  # noqa: BLE001
            continue
        if bars.empty:
            continue
        try:
            factors = provider.adj_factors(code, date(1990, 1, 1), date(2100, 1, 1))
        except Exception:  # noqa: BLE001
            factors = None
        produced = compute_forward_returns(
            bars, as_ofs, stock_code=code, horizons=HORIZONS,
            adj_factors=factors, benchmark=benchmark,
        )
        if not produced:
            missing_return[code] = 1
        rows.extend(produced)
    labels = pd.DataFrame(rows)
    if labels.empty:
        raise SystemExit("标签为空：检查 as_of 网格与供应商数据日期范围")
    labels["as_of"] = pd.to_datetime(labels["as_of"]).dt.date
    labels["trade_date"] = pd.to_datetime(labels["trade_date"]).dt.date
    keep = [
        "stock_code", "as_of", "trade_date", *[f"ret_{h}d" for h in HORIZONS],
        *[f"bench_ret_{h}d" for h in HORIZONS],
        *[f"excess_return_{h}d" for h in HORIZONS],
        "label_version",
    ]
    labels = labels[[column for column in keep if column in labels.columns]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(LABEL_CACHE, index=False, compression="zstd")
    meta = {
        "cache": "built",
        "label_rows": int(len(labels)),
        "codes_without_labels": len(missing_return),
        "label_version": str(labels["label_version"].iloc[0]),
    }
    log(f"标签构建完成：{len(labels):,} 行；无标签股票 {len(missing_return)} 只")
    return labels, meta


def load_board_map() -> dict[str, str]:
    import sqlite3

    connection = sqlite3.connect(ROOT / "data" / "smp.sqlite3")
    try:
        rows = connection.execute(
            "select stock_code, board from universe_memberships "
            "where universe_version = ?",
            (UNIVERSE_VERSION,),
        ).fetchall()
    finally:
        connection.close()
    return {str(code): str(board or "") for code, board in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 4E 全市场中性化")
    parser.add_argument("--limit", type=int, default=0, help="冒烟：只用前 N 只股票")
    parser.add_argument("--skip-labels", action="store_true")
    args = parser.parse_args()

    started = time.time()
    split = default_split(calibration_version=CALIBRATION_VERSION)
    registry = load_hypothesis_registry(HYPOTHESIS_REGISTRY_PATH)
    log(f"假设注册表：{registry.version}，{len(registry.hypotheses)} 个对象")

    payload = load_panel()
    log(
        f"面板分片：{payload.get('universe_version')} codes={len(payload['codes'])} "
        f"rows={len(payload['rows']):,} failures={payload.get('failures')}"
    )
    panel_raw = build_observation_panel(payload["rows"], split)
    assert_no_out_of_scope(panel_raw, split)
    codes = sorted(panel_raw["stock_code"].unique())
    if args.limit:
        codes = codes[: args.limit]
        panel_raw = panel_raw[panel_raw["stock_code"].isin(codes)]
    log(f"面板观测：{len(panel_raw):,} 行 / {len(codes):,} 只 / 分区 "
        f"{panel_raw['partition'].value_counts().to_dict()}")

    # --- cal-v2：只 fit 全市场 TRAIN ---
    freeze = freeze_for(CALIBRATION_VERSION)  # cal-v1 的冻结窗口即训练窗口定义
    train = panel_raw[panel_raw["partition"] == TRAIN].copy()
    from src.research.calibration import ResearchCalibrationLayer

    layer = ResearchCalibrationLayer(
        value_col="opinion_score", group_cols=("engine", "birth_model"),
        date_col="as_of", partition_col="partition",
        calibration_version=CALIBRATION_VERSION_V2, fit_partition=TRAIN,
        fit_max_as_of=split.train_end,
    ).fit(train)
    fit_max = pd.to_datetime(train["as_of"]).dt.date.max()
    freeze.assert_fit_within_train(fit_max_as_of=fit_max)
    from src.research.oos.walk_forward import calibration_fit_hash

    calibration_audit = {
        "calibration_version": CALIBRATION_VERSION_V2,
        "parent_version": CALIBRATION_VERSION,
        "fit_scope": "TRAIN_ONLY",
        "fit_max_as_of": fit_max.isoformat(),
        "train_end": split.train_end.isoformat(),
        "fit_row_count": int(len(train)),
        "fit_group_count": len(layer.groups),
        "calibration_fit_hash": calibration_fit_hash(layer),
        "difference_vs_cal_v1": (
            "v1 在 500 只上拟合、v2 在全市场 6,104 只上拟合；"
            "阈值（P25/P75）因此不同，两者不可混用。"
        ),
    }
    log(f"cal-v2 fit：groups={len(layer.groups)} hash={calibration_audit['calibration_fit_hash']}")
    calibrated = attach_calibration(panel_raw, layer)

    # --- 对象宽表 ---
    models = tuple(
        model for model in MODEL_VERSIONS if model in set(calibrated["birth_model"].unique())
    )
    wide = build_object_wide(calibrated, registry, birth_models=models)
    wide["partition"] = [split.partition_of(value) for value in wide["as_of"]]
    wide = wide[wide["partition"].isin((TRAIN, VALIDATION, OOS))].reset_index(drop=True)
    log(f"对象宽表：{len(wide):,} 行 × {len(registry.hypotheses)} 对象 × {len(models)} 模型")

    # --- 标签 ---
    provider = VendorParquetProvider(VENDOR_DIR)
    if args.skip_labels and LABEL_CACHE.is_file():
        labels, label_meta = build_label_panel_v4(provider, codes, [])
    else:
        as_ofs = sorted({date.fromisoformat(str(value)) for value in payload["dates"]})
        labels, label_meta = build_label_panel_v4(provider, codes, as_ofs)
    merged = wide.merge(labels, on=["stock_code", "as_of"], how="left")
    log(f"join 标签后：{len(merged):,} 行；有 20D 超额的行 "
        f"{int(merged['excess_return_20d'].notna().sum()):,}")

    # --- 暴露 v2（估值快照 + 供应商行情）---
    snapshot_path = VENDOR_DIR / "valuation_snapshots.parquet"
    if not snapshot_path.is_file():
        raise SystemExit(f"缺少估值快照：{snapshot_path}（先跑 phase4_build_valuation_snapshots.py）")
    snapshots = pd.read_parquet(snapshot_path)
    snapshots["as_of"] = pd.to_datetime(snapshots["as_of"]).dt.date
    vendored = snapshots[["as_of", "stock_code", "total_mv", "pe_ttm", "pb", "turnover_free"]].copy()
    vendored["size_log_market_cap"] = np.where(
        vendored["total_mv"] > 0, np.log(vendored["total_mv"].where(vendored["total_mv"] > 0)), np.nan,
    )
    vendored["value_ep"] = (1.0 / vendored["pe_ttm"].where(vendored["pe_ttm"] > 0))
    vendored["value_bp"] = (1.0 / vendored["pb"].where(vendored["pb"] > 0))
    vendored["turnover_free_20d"] = pd.to_numeric(vendored["turnover_free"], errors="coerce")
    merged = merged.merge(
        vendored[[
            "as_of", "stock_code", "size_log_market_cap", "value_ep", "value_bp",
            "turnover_free_20d",
        ]],
        on=["as_of", "stock_code"], how="left",
    )
    # momentum / volatility：复用 Phase 4A 的价格类暴露（从 Parquet 按需计算由 4B 负责；
    # 这里直接用 SQLite 侧已有的同口径实现，避免读 6,104 只 × 68 点的重复成本）
    from src.research.neutralization.exposures import compute_stock_exposures  # noqa: PLC0415

    exposure_as_ofs = sorted(set(merged["as_of"]))
    price_rows: list[dict] = []
    for order, code in enumerate(codes):
        if order % 1000 == 0:
            log(f"价格类暴露 {order}/{len(codes)} …")
        try:
            bars = provider.bars_frame(code)
        except Exception:  # noqa: BLE001
            continue
        if bars.empty:
            continue
        try:
            factors = provider.adj_factors(code, date(1990, 1, 1), date(2100, 1, 1))
        except Exception:  # noqa: BLE001
            factors = None
        price_rows.extend(
            compute_stock_exposures(
                bars, exposure_as_ofs, adj_factors=factors, stock_code=code,
            )
        )
    price = pd.DataFrame(price_rows)[[
        "stock_code", "as_of", "momentum_60d", "momentum_120d",
        "volatility_20d", "volatility_60d",
    ]]
    merged = merged.merge(price, on=["stock_code", "as_of"], how="left")
    merged = zscore_cross_section(merged, STYLE_EXPOSURE_COLUMNS_V2)
    merged = attach_segment(merged, load_board_map())
    merged = attach_market_excess(merged, split.horizons)

    exposure_meta = {
        "exposure_version": EXPOSURE_VERSION_V2,
        "source_data_version": VENDOR_DATA_VERSION,
        "availability": exposure_availability_v2().to_dict(),
        "columns": {
            column: {
                "usable": int(merged[column].notna().sum()),
                "missing": int(merged[column].isna().sum()),
                "coverage_ratio": round(float(merged[column].notna().mean()), 6),
            }
            for column in STYLE_EXPOSURE_COLUMNS_V2 if column in merged.columns
        },
    }
    log("暴露覆盖率：" + ", ".join(
        f"{key}={value['coverage_ratio']}" for key, value in exposure_meta["columns"].items()
    ))

    # --- 中性化 ---
    from dataclasses import make_dataclass

    Dataset = make_dataclass(  # noqa: N806 - 轻量容器，只为满足 run_neutralization 的接口
        "Phase4Dataset",
        [("frame", object), ("registry", object), ("birth_models", tuple),
         ("split", object), ("calibration_audit", dict)],
    )
    dataset = Dataset(
        frame=merged, registry=registry, birth_models=models,
        split=split, calibration_audit=calibration_audit,
    )
    outcome = run_neutralization(
        dataset=dataset,
        horizons=split.horizons,
        primary_horizon=PRIMARY_HORIZON,
        include_date_effect=True,
        exposure_columns=STYLE_EXPOSURE_COLUMNS_V2,
        neutralization_version=NEUTRALIZATION_VERSION_V2,
    )
    log(f"中性化结果：{len(outcome.rows)} 行")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(outcome.rows).to_csv(
        OUT_DIR / "phase4_neutralization_results.csv", index=False, encoding="utf-8-sig",
    )
    meta = {
        "run_version": NEUTRALIZATION_VERSION_V2,
        "generated_at": datetime.now().isoformat(),
        "universe_version": UNIVERSE_VERSION,
        "vendor_data_version": VENDOR_DATA_VERSION,
        "split_version": split.split_version,
        "calibration": calibration_audit,
        "label_meta": label_meta,
        "exposures": exposure_meta,
        "segments": sorted({str(v) for v in merged.get("segment", pd.Series(dtype=str)).unique()}),
        "row_count": len(outcome.rows),
        "stock_count": int(merged["stock_code"].nunique()),
        "questions": answer_questions(outcome.rows, primary_horizon=PRIMARY_HORIZON),
        "scope_note": (
            "本结果是 Phase 4 的全市场口径（v4-full / cal-v2 / phase4-exposures-v2），"
            "与 Phase 3E（v2-phase3a / cal-v1 / phase3e-exposures-v1）**不可混用**，"
            "必须在报告中并排出现。事件与对象定义与 Phase 3 完全相同（同一注册表）。"
        ),
    }
    (OUT_DIR / "phase4_neutralization_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    log(f"写入 {OUT_DIR / 'phase4_neutralization_results.csv'}")
    log(f"完成，用时 {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
