"""Independently audit a W4 limited-scope panel's artifacts and return labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ID = "w4-certified-002561-20120223-20180514-v2-label-ends"
DEFAULT_W2_ROOT = ROOT / "artifacts" / "w2-data-certification-20260927-full-06"
DEFAULT_CERTIFICATE = ROOT / "artifacts" / "w2-limited-scope-002561-2012-2018" / "scope_certificate.json"
DEFAULT_DATABASE = ROOT / "data" / "w8-local-runtime" / "smp.sqlite3"
DEFAULT_DATASET_ROOT = ROOT / "data" / "research_datasets"
DEFAULT_MARKET_ROOT = Path("E:/AStockData/datasets/market_data")
DEFAULT_BENCHMARK = ROOT / "data" / "import" / "bars" / "IDX000300.csv"
DEFAULT_BENCHMARK_META = ROOT / "data" / "import" / "_meta.json"
SAMPLE_DATES = ("2012-02-23", "2015-04-29", "2018-05-14")
HORIZONS = (1, 5, 20)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"预期 JSON object：{path}")
    return value


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _decode_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _load_shards(dataset_dir: Path, manifest: dict[str, Any], field: str, digest_field: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for shard in manifest["shards"]:
        relative = Path(str(shard[field]))
        path = (dataset_dir / relative).resolve(strict=True)
        if not path.is_relative_to(dataset_dir.resolve()):
            raise ValueError(f"分片路径越出数据集目录：{relative}")
        if _sha256(path) != shard[digest_field]:
            raise ValueError(f"分片 SHA-256 不匹配：{relative}")
        frames.append(pd.read_parquet(path))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _audit_artifacts(features: pd.DataFrame, database: Path) -> dict[str, Any]:
    expected: dict[str, str] = {}
    for raw_ids, raw_digests in zip(
        features["chart_artifact_ids_json"], features["chart_artifact_digests_json"], strict=True
    ):
        artifact_ids = _decode_json(raw_ids)
        artifact_digests = _decode_json(raw_digests)
        if len(artifact_ids) != 3 or set(artifact_ids) != set(artifact_digests):
            raise ValueError("W4 每行必须引用三个且仅三个带 digest 的 chart artifact")
        for artifact_id, digest in artifact_digests.items():
            previous = expected.setdefault(str(artifact_id), str(digest))
            if previous != digest:
                raise ValueError(f"同一 chart artifact 引用出现不同 digest：{artifact_id}")

    db_uri = f"file:{database.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(db_uri, uri=True)
    connection.row_factory = sqlite3.Row
    checked = 0
    try:
        ids = list(expected)
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT chart_id,stock_code,engine,engine_version,config_version,"
                f"birth_profile_version,as_of,input_json,raw_chart,assumptions_json,warnings_json "
                f"FROM chart_artifact WHERE chart_id IN ({placeholders})",
                batch,
            ).fetchall()
            if len(rows) != len(batch):
                raise ValueError(f"SQLite chart_artifact 行缺失：需要 {len(batch)}，实际 {len(rows)}")
            for row in rows:
                local_as_of = datetime.fromisoformat(str(row["as_of"]))
                as_of = local_as_of.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
                canonical_record = {
                    "chart_id": str(row["chart_id"]),
                    "engine_id": str(row["engine"]),
                    "engine_version": str(row["engine_version"]),
                    "symbol": str(row["stock_code"]),
                    "as_of": as_of,
                    "input_payload": _decode_json(row["input_json"]),
                    "raw_chart": _decode_json(row["raw_chart"]),
                    "assumptions": _decode_json(row["assumptions_json"]),
                    "warnings": _decode_json(row["warnings_json"]),
                    "birth_profile_version": str(row["birth_profile_version"]),
                    "config_version": str(row["config_version"]),
                }
                actual = _canonical_sha256(canonical_record)
                if actual != expected[str(row["chart_id"])]:
                    raise ValueError(f"chart_artifact canonical payload digest 不匹配：{row['chart_id']}")
                checked += 1
    finally:
        connection.close()
    return {"referenced_artifact_count": len(expected), "sqlite_payloads_checked": checked, "mismatches": 0}


def _load_raw_and_factor(market_root: Path, w2_root: Path, certificate: dict[str, Any]) -> tuple[dict[int, float], dict[int, float]]:
    w2 = _read_json(w2_root / "w2_data_certification_manifest.json")
    input_versions = certificate["input_versions"]
    for path, key in ((w2_root / "w2_data_certification_manifest.json", "w2_manifest_sha256"),):
        if _sha256(path) != input_versions[key]:
            raise ValueError(f"W2 输入 SHA-256 与证书不一致：{key}")

    raw_info = w2["raw_overlay"]
    factor_info = w2["factor_overlay"]
    raw_manifest_path = market_root / "manifests" / raw_info["manifest_file"]
    factor_manifest_path = market_root / "manifests" / factor_info["manifest_file"]
    if _sha256(raw_manifest_path) != input_versions["raw_manifest_sha256"]:
        raise ValueError("raw manifest SHA-256 与证书不一致")
    if _sha256(factor_manifest_path) != input_versions["factor_manifest_sha256"]:
        raise ValueError("factor manifest SHA-256 与证书不一致")
    raw_manifest = _read_json(raw_manifest_path)
    factor_manifest = _read_json(factor_manifest_path)
    symbol = "SZSE.STK.002561"
    raw_entries = [entry for entry in raw_manifest["symbols"] if entry.get("symbol") == symbol]
    factor_entries = [entry for entry in factor_manifest["symbols"] if entry.get("symbol") == symbol]
    if len(raw_entries) != 1 or len(factor_entries) != 1:
        raise ValueError("pinned overlay 中的 002561 identity 必须唯一")
    raw_hash = str(raw_entries[0]["blob_sha256"])
    factor_hash = str(factor_entries[0]["blob_sha256"])
    if raw_hash != input_versions["raw_blob_sha256"] or factor_hash != input_versions["factor_blob_sha256"]:
        raise ValueError("raw/factor blob identity 与证书不一致")
    raw_path = market_root / "blobs" / f"{raw_hash}.npz"
    factor_path = market_root / "blobs" / f"{factor_hash}.npz"
    if _sha256(raw_path) != raw_hash or _sha256(factor_path) != factor_hash:
        raise ValueError("raw/factor content-addressed blob SHA-256 不匹配")
    with np.load(raw_path, allow_pickle=False) as raw, np.load(factor_path, allow_pickle=False) as factor:
        raw_dates = raw["trade_date"].astype(np.int64)
        raw_closes = raw["close"].astype(np.float64)
        factor_dates = factor["trade_date"].astype(np.int64)
        factors = factor["adj_factor"].astype(np.float64)
    return dict(zip(raw_dates.tolist(), raw_closes.tolist(), strict=True)), dict(
        zip(factor_dates.tolist(), factors.tolist(), strict=True)
    )


def _audit_returns(
    outcomes: pd.DataFrame,
    certificate: dict[str, Any],
    market_root: Path,
    w2_root: Path,
    benchmark_file: Path,
) -> list[dict[str, Any]]:
    input_versions = certificate["input_versions"]
    if _sha256(benchmark_file) != input_versions["benchmark_file_sha256"]:
        raise ValueError("benchmark CSV SHA-256 与证书不一致")
    raw_close, factor = _load_raw_and_factor(market_root, w2_root, certificate)
    benchmark = pd.read_csv(benchmark_file)
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], format="%Y-%m-%d", errors="raise")
    if benchmark["trade_date"].duplicated().any() or not benchmark["adjust"].astype(str).str.lower().eq("none").all():
        raise ValueError("benchmark 需唯一日期且全为 adjustment=none")
    benchmark_close = {
        int(day.strftime("%Y%m%d")): float(close)
        for day, close in zip(benchmark["trade_date"], benchmark["close"], strict=True)
    }
    dates = sorted(raw_close)
    indexes = {value: index for index, value in enumerate(dates)}
    outcome_by_date = {str(row["research_date"]): row for _, row in outcomes.iterrows()}
    results: list[dict[str, Any]] = []
    for sample_date in SAMPLE_DATES:
        start_day = date.fromisoformat(sample_date)
        start_key = int(start_day.strftime("%Y%m%d"))
        if start_key not in indexes or sample_date not in outcome_by_date:
            raise ValueError(f"独立复算样本日期未进入 raw 与 W4：{sample_date}")
        start_index = indexes[start_key]
        row = outcome_by_date[sample_date]
        for horizon in HORIZONS:
            end_index = start_index + horizon
            end_key = dates[end_index]
            start_factor = factor.get(start_key)
            end_factor = factor.get(end_key)
            if start_factor is None or end_factor is None:
                raise ValueError(f"复算端点缺少同日因子：{sample_date}/{horizon}D")
            stock_return = (raw_close[end_key] * end_factor) / (raw_close[start_key] * start_factor) - 1.0
            benchmark_return = benchmark_close[end_key] / benchmark_close[start_key] - 1.0
            stock_value = round(stock_return, 6)
            benchmark_value = round(benchmark_return, 6)
            excess_value = round(stock_return - benchmark_return, 6)
            expected_values = {
                f"ret_{horizon}d": stock_value,
                f"bench_ret_{horizon}d": benchmark_value,
                f"excess_return_{horizon}d": excess_value,
                f"label_end_date_{horizon}d": date(
                    end_key // 10000, (end_key // 100) % 100, end_key % 100
                ),
            }
            for field, expected in expected_values.items():
                actual = row[field]
                if actual != expected:
                    raise ValueError(
                        f"独立复算不一致：{sample_date} {field} stored={actual!r} calculated={expected!r}"
                    )
            results.append({"research_date": sample_date, "horizon": horizon, **expected_values})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--certificate", type=Path, default=DEFAULT_CERTIFICATE)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--w2-root", type=Path, default=DEFAULT_W2_ROOT)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--benchmark-file", type=Path, default=DEFAULT_BENCHMARK)
    args = parser.parse_args()

    dataset_dir = (args.dataset_root / args.dataset_id).resolve(strict=True)
    manifest = _read_json(dataset_dir / "manifest.json")
    certificate = _read_json(args.certificate.resolve(strict=True))
    if manifest["dataset_id"] != args.dataset_id or manifest["dataset_digest"] != (
        "d024ef9e2084563ce1dd3d1ce61f9dcf48daf15d49f93f2c96eb95d58156ac99"
    ):
        raise ValueError("W4 dataset identity/digest 与冻结限域版本不一致")
    if manifest["metadata"].get("input_versions", {}).get("scope_certificate_sha256") != certificate.get("certificate_sha256"):
        raise ValueError("W4 manifest 未绑定当前 W2 scope certificate")
    if manifest["metadata"].get("research_eligible") is not True or manifest["metadata"].get("confirmatory_research_eligible") is not False:
        raise ValueError("W4 exploratory eligibility flags 与已审阅口径不一致")
    features = _load_shards(dataset_dir, manifest, "features_path", "features_sha256")
    outcomes = _load_shards(dataset_dir, manifest, "outcomes_path", "outcomes_sha256")
    if len(features) != 1513 or len(outcomes) != 1513:
        raise ValueError("限域 W4 feature/outcome 行数应各为 1,513")
    if features["research_date"].duplicated().any() or outcomes["research_date"].duplicated().any():
        raise ValueError("W4 research_date 重复")
    artifact_audit = _audit_artifacts(features, args.database)
    horizon_coverage = {
        str(horizon): {
            "available": int(outcomes[f"horizon_available_{horizon}d"].sum()),
            "return_values": int(outcomes[f"ret_{horizon}d"].notna().sum()),
            "benchmark_values": int(outcomes[f"bench_ret_{horizon}d"].notna().sum()),
            "excess_values": int(outcomes[f"excess_return_{horizon}d"].notna().sum()),
        }
        for horizon in (1, 5, 10, 20, 60)
    }
    if any(
        metrics != {"available": 1513, "return_values": 1513, "benchmark_values": 1513, "excess_values": 1513}
        for metrics in horizon_coverage.values()
    ):
        raise ValueError(f"W4 horizon/benchmark 覆盖与限域发布口径不符：{horizon_coverage}")
    return_audit = _audit_returns(
        outcomes, certificate, args.market_root.resolve(strict=True), args.w2_root.resolve(strict=True),
        args.benchmark_file.resolve(strict=True),
    )
    print(json.dumps({
        "dataset_id": manifest["dataset_id"],
        "dataset_digest": manifest["dataset_digest"],
        "row_count": len(features),
        "feature_shards": manifest["complete_shard_count"],
        "outcome_shards": manifest["complete_shard_count"],
        "horizon_coverage": horizon_coverage,
        "chart_artifact_audit": artifact_audit,
        "independent_return_audit": {"rows_checked": len(return_audit), "tolerance": 0, "results": return_audit},
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
