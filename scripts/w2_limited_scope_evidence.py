"""Load and re-audit the pinned, single-security W2 observation range."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_BENCHMARK_FILE = ROOT / "data" / "import" / "bars" / "IDX000300.csv"
DEFAULT_BENCHMARK_META = ROOT / "data" / "import" / "_meta.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_jsonl_row(path: Path, key: str, expected: str) -> str:
    with path.open("rb") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get(key)) == expected:
                return hashlib.sha256(line).hexdigest()
    raise KeyError(f"{path.name} 中找不到 {key}={expected}")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"输入必须是 JSON object：{path}")
    return value


def load_scope_evidence(
    *,
    w2_root: Path,
    market_root: Path,
    benchmark_file: Path = DEFAULT_BENCHMARK_FILE,
    benchmark_meta_file: Path = DEFAULT_BENCHMARK_META,
) -> dict[str, Any]:
    """Recompute every physical check used by the limited-scope certificate."""
    from scripts.build_w4_historical_dataset import _load_w2_inputs
    from src.research.scoped_data_certificate import STOCK_CODE, audit_observation_range

    w2_root = w2_root.resolve(strict=True)
    market_root = market_root.resolve(strict=True)
    benchmark_file = benchmark_file.resolve(strict=True)
    benchmark_meta_file = benchmark_meta_file.resolve(strict=True)
    inputs = _load_w2_inputs(w2_root, market_root, STOCK_CODE)
    if inputs["symbol"] != "SZSE.STK.002561" or inputs["scope"].get("security_id") != (
        "dba06cf4-8e33-594d-a077-595dbcb029bd"
    ):
        raise ValueError("W2 identity 与冻结的 SZSE.STK.002561 不一致")

    benchmark_meta = _read_json(benchmark_meta_file)
    if benchmark_meta.get("provider") != "tencent_ifzq_gtimg":
        raise ValueError("沪深 300 benchmark 来源不是冻结的 Tencent snapshot")
    if "000300" not in benchmark_meta.get("benchmarks", []):
        raise ValueError("本机行情 meta 未声明 000300 benchmark")
    benchmark_frame = pd.read_csv(benchmark_file)
    required_benchmark_columns = {"trade_date", "close", "adjust"}
    if not required_benchmark_columns.issubset(benchmark_frame.columns):
        raise ValueError("IDX000300 benchmark CSV 缺少日期、收盘价或复权列")
    if benchmark_frame["trade_date"].duplicated().any():
        raise ValueError("IDX000300 benchmark 存在重复交易日期")
    benchmark_frame["trade_date"] = pd.to_datetime(
        benchmark_frame["trade_date"], format="%Y-%m-%d", errors="raise",
    )
    selected_benchmark = benchmark_frame[
        benchmark_frame["trade_date"].dt.date.between(
            date(2012, 2, 23), date(2018, 8, 7),
        )
    ]
    if not selected_benchmark["adjust"].astype(str).str.lower().eq("none").all():
        raise ValueError("认证区间与最长结果窗口的 000300 必须使用不复权日线")
    if not pd.to_numeric(selected_benchmark["close"], errors="coerce").gt(0).all():
        raise ValueError("认证区间与最长结果窗口的 000300 close 必须为正数")

    corporate_action_file = market_root / "ca_events" / "002561.SZ.json"
    corporate_action_meta_file = market_root / "ca_events" / "_meta.json"
    corporate_action_rows = json.loads(corporate_action_file.read_text(encoding="utf-8"))
    if not isinstance(corporate_action_rows, list):
        raise ValueError("002561 公司行动文件必须是 JSON array")
    corporate_actions = [
        row for row in corporate_action_rows
        if row.get("std_code") == inputs["symbol"]
    ]
    corporate_action_meta = _read_json(corporate_action_meta_file)
    if corporate_action_meta.get("provider") != "DataApi":
        raise ValueError("公司行动台账来源与已记录的 DataApi 不一致")

    scope_file = w2_root / "w2_physical_scope_rows.jsonl"
    raw_audit_file = w2_root / "w2_raw_physical_audit.jsonl"
    factor_audit_file = w2_root / "w2_factor_physical_audit.jsonl"
    symbol = inputs["symbol"]
    input_versions = {
        "w2_manifest_sha256": inputs["w2_manifest_sha256"],
        "w2_scope_row_sha256": _sha256_jsonl_row(scope_file, "symbol", symbol),
        "w2_raw_audit_row_sha256": _sha256_jsonl_row(raw_audit_file, "symbol", symbol),
        "w2_factor_audit_row_sha256": _sha256_jsonl_row(factor_audit_file, "symbol", symbol),
        "reference_calendar_sha256": inputs["calendar_sha256"],
        "raw_manifest_sha256": inputs["raw_manifest_sha256"],
        "raw_blob_sha256": inputs["raw_blob_sha256"],
        "factor_manifest_sha256": inputs["factor_manifest_sha256"],
        "factor_blob_sha256": inputs["factor_blob_sha256"],
        "benchmark_file_sha256": _sha256_file(benchmark_file),
        "benchmark_meta_sha256": _sha256_file(benchmark_meta_file),
        "corporate_action_file_sha256": _sha256_file(corporate_action_file),
        "corporate_action_meta_sha256": _sha256_file(corporate_action_meta_file),
        "raw_dataset_id": str(inputs["raw_manifest"]["dataset_id"]),
        "factor_dataset_id": str(inputs["factor_manifest"]["dataset_id"]),
        "benchmark_code": "000300",
        "benchmark_provider": str(benchmark_meta["provider"]),
        "benchmark_snapshot_at": str(benchmark_meta["fetched_at"]),
        "benchmark_adjustment": "none",
        "corporate_action_provider": str(corporate_action_meta["provider"]),
        "corporate_action_as_of_date": str(corporate_action_meta["as_of_date"]),
        "full_pit_universe_status": str(
            inputs["w2_manifest"]["full_pit_universe_status"]
        ),
    }

    raw_frame = inputs["bars"]
    factor_frame = inputs["factors"]
    benchmark_frame = benchmark_frame.sort_values("trade_date", kind="stable")
    benchmark_frame["close"] = pd.to_numeric(benchmark_frame["close"], errors="coerce")
    audit = audit_observation_range(
        reference_dates=np.asarray(inputs["reference_dates"], dtype=np.int64),
        raw_dates=raw_frame["trade_date"].dt.strftime("%Y%m%d").astype(np.int64).to_numpy(),
        raw_values=raw_frame[["open", "high", "low", "close", "volume", "amount"]]
        .to_numpy(dtype=np.float64),
        factor_dates=factor_frame["trade_date"].dt.strftime("%Y%m%d").astype(np.int64).to_numpy(),
        factor_values=factor_frame["factor"].to_numpy(dtype=np.float64),
        benchmark_dates=benchmark_frame["trade_date"].dt.strftime("%Y%m%d").astype(np.int64).to_numpy(),
        benchmark_closes=benchmark_frame["close"].to_numpy(dtype=np.float64),
        corporate_actions=corporate_actions,
        pit_start=date.fromisoformat(str(inputs["scope"]["pit_effective_start"])),
        pit_end_exclusive=(
            date.fromisoformat(str(inputs["scope"]["pit_effective_end_exclusive"]))
            if inputs["scope"].get("pit_effective_end_exclusive")
            else None
        ),
        evidence_cutoff=inputs["evidence_cutoff"],
    )
    return {
        "inputs": inputs,
        "audit": audit,
        "input_versions": input_versions,
        "benchmark_frame": benchmark_frame,
        "benchmark_meta": benchmark_meta,
        "corporate_action_meta": corporate_action_meta,
        "corporate_actions": corporate_actions,
    }


def verify_certificate_against_current_inputs(
    certificate: dict[str, Any],
    *,
    w2_root: Path,
    market_root: Path,
    benchmark_file: Path = DEFAULT_BENCHMARK_FILE,
    benchmark_meta_file: Path = DEFAULT_BENCHMARK_META,
) -> dict[str, Any]:
    """Reject validly rehashed but stale or mismatched certificate payloads."""
    from src.research.scoped_data_certificate import verify_limited_scope_certificate

    verify_limited_scope_certificate(certificate)
    material = load_scope_evidence(
        w2_root=w2_root,
        market_root=market_root,
        benchmark_file=benchmark_file,
        benchmark_meta_file=benchmark_meta_file,
    )
    certificate_versions = certificate.get("input_versions", {})
    if any(
        certificate_versions.get(key) != value
        for key, value in material["input_versions"].items()
    ):
        raise ValueError("有限范围证书绑定的输入版本与当前 pinned 数据不一致")
    if certificate.get("audit") != material["audit"]:
        raise ValueError("有限范围证书的物理审计与当前重新计算结果不一致")
    inputs = material["inputs"]
    expected_pit = {
        "effective_start": str(inputs["scope"]["pit_effective_start"]),
        "effective_end_exclusive": str(inputs["scope"]["pit_effective_end_exclusive"])
        if inputs["scope"].get("pit_effective_end_exclusive")
        else None,
        "evidence_cutoff": inputs["evidence_cutoff"].isoformat(),
        "verified_listing_date": str(inputs["scope"]["listing_date"]),
    }
    if certificate.get("pit_membership") != expected_pit:
        raise ValueError("有限范围证书 PIT 身份成员日期与当前 W2 scope row 不一致")
    return material


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--certificate",
        type=Path,
        default=ROOT / "artifacts" / "w2-limited-scope-002561-2012-2018" / "scope_certificate.json",
    )
    parser.add_argument(
        "--w2-root",
        type=Path,
        default=ROOT / "artifacts" / "w2-data-certification-20260927-full-06",
    )
    parser.add_argument("--market-root", type=Path, default=Path("E:/AStockData/datasets/market_data"))
    parser.add_argument("--benchmark-file", type=Path, default=DEFAULT_BENCHMARK_FILE)
    parser.add_argument("--benchmark-meta-file", type=Path, default=DEFAULT_BENCHMARK_META)
    args = parser.parse_args()
    certificate = _read_json(args.certificate.resolve(strict=True))
    material = verify_certificate_against_current_inputs(
        certificate,
        w2_root=args.w2_root,
        market_root=args.market_root,
        benchmark_file=args.benchmark_file,
        benchmark_meta_file=args.benchmark_meta_file,
    )
    audit = material["audit"]
    print(json.dumps({
        "certificate_id": certificate["certificate_id"],
        "certificate_sha256": certificate["certificate_sha256"],
        "status": certificate["status"],
        "research_eligible": certificate["research_eligible"],
        "confirmatory_research_eligible": certificate["confirmatory_research_eligible"],
        "research_dates": len(audit["research_dates"]),
        "raw_reference_dates_equal": audit["raw_reference_dates_equal"],
        "factor_reference_dates_equal": audit["factor_reference_dates_equal"],
        "benchmark_reference_dates_equal_through_maturity": audit["benchmark_reference_dates_equal_through_maturity"],
        "corporate_action_count": audit["corporate_action_reconciliation"]["action_count"],
        "full_pit_universe_status": material["inputs"]["w2_manifest"]["full_pit_universe_status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
