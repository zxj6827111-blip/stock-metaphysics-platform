"""Independently audit a W4 limited-scope panel's artifacts and return labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ID = "w4-certified-002561-20120223-20180514-v3-path-risk"
DEFAULT_W2_ROOT = ROOT / "artifacts" / "w2-data-certification-20260927-full-06"
DEFAULT_CERTIFICATE = ROOT / "artifacts" / "w2-limited-scope-002561-2012-2018" / "scope_certificate.json"
DEFAULT_DATABASE = ROOT / "data" / "research-closure-runtime" / "runtime" / "smp.sqlite3"
DEFAULT_DATASET_ROOT = ROOT / "data" / "research_datasets"
DEFAULT_MARKET_ROOT = Path("E:/AStockData/datasets/market_data")
DEFAULT_BENCHMARK = ROOT / "data" / "import" / "bars" / "IDX000300.csv"
DEFAULT_BENCHMARK_META = ROOT / "data" / "import" / "_meta.json"
SAMPLE_DATES = ("2012-02-23", "2015-04-29", "2018-05-14")
HORIZONS = (1, 5, 10, 20, 60)
MANIFEST_DIGEST_FIELDS = (
    "shard_key", "status", "input_digest", "source_digest", "row_count",
    "features_sha256", "outcomes_sha256", "error_code", "error_type",
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.research.certified_scopes import CERTIFIED_DATASET_PINS, certified_scope_state


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
        raw_highs = raw["high"].astype(np.float64)
        raw_lows = raw["low"].astype(np.float64)
        factor_dates = factor["trade_date"].astype(np.int64)
        factors = factor["adj_factor"].astype(np.float64)
    return (
        dict(zip(raw_dates.tolist(), raw_closes.tolist(), strict=True)),
        dict(zip(raw_dates.tolist(), raw_highs.tolist(), strict=True)),
        dict(zip(raw_dates.tolist(), raw_lows.tolist(), strict=True)),
        dict(zip(factor_dates.tolist(), factors.tolist(), strict=True)),
    )


def _audit_returns(
    outcomes: pd.DataFrame,
    certificate: dict[str, Any],
    market_root: Path,
    w2_root: Path,
    benchmark_file: Path,
) -> dict[str, Any]:
    input_versions = certificate["input_versions"]
    if _sha256(benchmark_file) != input_versions["benchmark_file_sha256"]:
        raise ValueError("benchmark CSV SHA-256 与证书不一致")
    raw_close, _raw_high, _raw_low, factor = _load_raw_and_factor(market_root, w2_root, certificate)
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
    valid_windows = 0
    benchmark_windows = 0
    samples: list[dict[str, Any]] = []
    for _, row in outcomes.iterrows():
        sample_date = str(row["research_date"])
        start_day = date.fromisoformat(sample_date)
        start_key = int(start_day.strftime("%Y%m%d"))
        if start_key not in indexes:
            raise ValueError(f"独立复算日期未进入 raw 与 W4：{sample_date}")
        start_index = indexes[start_key]
        for horizon in HORIZONS:
            end_index = start_index + horizon
            stock_available = end_index < len(dates)
            end_key = dates[end_index] if stock_available else None
            start_factor = factor.get(start_key)
            end_factor = factor.get(end_key) if end_key is not None else None
            stock_available = stock_available and start_factor is not None and end_factor is not None
            if stock_available:
                stock_available = all(
                    np.isfinite(value) and value > 0
                    for value in (raw_close[start_key], raw_close[end_key], start_factor, end_factor)
                )
            stock_return = (
                (raw_close[end_key] * end_factor) / (raw_close[start_key] * start_factor) - 1.0
                if stock_available else None
            )
            benchmark_available = (
                end_key is not None and start_key in benchmark_close and end_key in benchmark_close
                and benchmark_close[start_key] > 0 and benchmark_close[end_key] > 0
            )
            benchmark_return = (
                benchmark_close[end_key] / benchmark_close[start_key] - 1.0
                if benchmark_available else None
            )
            stock_value = None if stock_return is None else round(stock_return, 6)
            benchmark_value = None if benchmark_return is None else round(benchmark_return, 6)
            excess_value = (
                None if stock_return is None or benchmark_return is None
                else round(stock_return - benchmark_return, 6)
            )
            label_end_date = (
                date(end_key // 10000, (end_key // 100) % 100, end_key % 100)
                if stock_available and end_key is not None else None
            )
            expected_values = {
                f"horizon_available_{horizon}d": stock_available,
                f"ret_{horizon}d": stock_value,
                f"bench_ret_{horizon}d": benchmark_value,
                f"excess_return_{horizon}d": excess_value,
                f"label_end_date_{horizon}d": label_end_date,
            }
            for field, expected in expected_values.items():
                actual = row[field]
                if isinstance(expected, bool):
                    matches = bool(actual) == expected
                elif expected is None:
                    matches = pd.isna(actual)
                else:
                    matches = not pd.isna(actual) and actual == expected
                if not matches:
                    raise ValueError(
                        f"独立复算不一致：{sample_date} {field} stored={actual!r} calculated={expected!r}"
                    )
            valid_windows += int(stock_available)
            benchmark_windows += int(benchmark_available)
            if sample_date in SAMPLE_DATES:
                samples.append({"research_date": sample_date, "horizon": horizon, **expected_values})
    return {
        "valid_return_windows_checked": valid_windows,
        "benchmark_windows_checked": benchmark_windows,
        "samples": samples,
    }


def _audit_path_metrics(
    outcomes: pd.DataFrame,
    raw_close: dict[int, float],
    raw_high: dict[int, float],
    raw_low: dict[int, float],
    factor: dict[int, float],
) -> dict[str, Any]:
    dates = sorted(raw_close)
    indexes = {value: index for index, value in enumerate(dates)}
    checked = {
        str(horizon): {"max_favorable_move": 0, "max_adverse_move": 0, "max_drawdown": 0}
        for horizon in HORIZONS
    }
    samples: list[dict[str, Any]] = []
    for _, row in outcomes.iterrows():
        research_date = str(row["research_date"])
        start_key = int(date.fromisoformat(research_date).strftime("%Y%m%d"))
        if start_key not in indexes:
            raise ValueError(f"独立路径复算日期未进入 raw：{research_date}")
        start_index = indexes[start_key]
        for horizon in HORIZONS:
            end_index = start_index + horizon
            if end_index >= len(dates):
                raise ValueError(f"认证标签窗口超出 raw bars：{research_date}/{horizon}D")
            window_keys = dates[start_index:end_index + 1]
            future_keys = window_keys[1:]
            adjusted_closes = [
                raw_close.get(day, np.nan) * (factor.get(day) if factor.get(day) is not None else np.nan)
                for day in window_keys
            ]
            adjusted_highs = [
                raw_high.get(day, np.nan) * (factor.get(day) if factor.get(day) is not None else np.nan)
                for day in future_keys
            ]
            adjusted_lows = [
                raw_low.get(day, np.nan) * (factor.get(day) if factor.get(day) is not None else np.nan)
                for day in future_keys
            ]
            if not np.isfinite(adjusted_closes).all() or min(adjusted_closes) <= 0:
                raise ValueError(f"认证收盘路径包含无效值：{research_date}/{horizon}D")
            base_close = adjusted_closes[0]
            expected = {
                f"max_favorable_move_{horizon}d": (
                    round(max(adjusted_highs) / base_close - 1, 6)
                    if len(adjusted_highs) == horizon and np.isfinite(adjusted_highs).all() and min(adjusted_highs) > 0
                    else None
                ),
                f"max_adverse_move_{horizon}d": (
                    round(min(adjusted_lows) / base_close - 1, 6)
                    if len(adjusted_lows) == horizon and np.isfinite(adjusted_lows).all() and min(adjusted_lows) > 0
                    else None
                ),
                f"max_drawdown_{horizon}d": round(max(
                    1.0 - value / peak
                    for peak, value in zip(np.maximum.accumulate(adjusted_closes), adjusted_closes, strict=True)
                ), 6),
            }
            for field, expected_value in expected.items():
                actual = row[field]
                matches = pd.isna(actual) if expected_value is None else not pd.isna(actual) and actual == expected_value
                if not matches:
                    raise ValueError(
                        f"独立路径复算不一致：{research_date} {field} stored={actual!r} calculated={expected_value!r}"
                    )
                if expected_value is not None:
                    checked[str(horizon)][field.removesuffix(f"_{horizon}d")] += 1
            if research_date in SAMPLE_DATES:
                samples.append({"research_date": research_date, **expected})
    return {"metric_values_checked": checked, "sample_rows": samples}


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
    pin = CERTIFIED_DATASET_PINS.get(args.dataset_id)
    if pin is None or manifest.get("dataset_id") != args.dataset_id:
        raise ValueError("W4 dataset 身份没有本地证书登记")
    digest_rows = [
        {key: shard.get(key) for key in MANIFEST_DIGEST_FIELDS}
        for shard in sorted(manifest.get("shards", []), key=lambda item: str(item.get("shard_key", "")))
    ]
    calculated_digest = _canonical_sha256({
        "schema_version": manifest.get("schema_version"),
        "dataset_id": args.dataset_id,
        "metadata": manifest.get("metadata", {}),
        "shards": digest_rows,
        "missing_shards": manifest.get("missing_shards", []),
    })
    if manifest.get("dataset_digest") != calculated_digest:
        raise ValueError("W4 manifest digest 复算不一致")
    certification_status, certification_reason, checked_pin = certified_scope_state(manifest)
    if certification_status != "CERTIFIED_LIMITED_SCOPE" or checked_pin != pin:
        raise ValueError(f"W4 证书绑定检查失败：{certification_status} {certification_reason}")
    if (
        certificate.get("certificate_id") != pin.scope_certificate_id
        or certificate.get("certificate_sha256") != pin.scope_certificate_sha256
        or manifest["metadata"].get("input_versions", {}).get("scope_certificate_sha256") != certificate.get("certificate_sha256")
    ):
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
    raw_close, raw_high, raw_low, factor = _load_raw_and_factor(
        args.market_root.resolve(strict=True), args.w2_root.resolve(strict=True), certificate,
    )
    path_audit = _audit_path_metrics(outcomes, raw_close, raw_high, raw_low, factor)
    print(json.dumps({
        "dataset_id": manifest["dataset_id"],
        "dataset_digest": manifest["dataset_digest"],
        "schema_version": manifest["schema_version"],
        "row_count": len(features),
        "feature_shards": manifest["complete_shard_count"],
        "outcome_shards": manifest["complete_shard_count"],
        "certification_status": certification_status,
        "certification_reason": certification_reason,
        "scope_certificate_id": pin.scope_certificate_id,
        "scope_certificate_sha256": pin.scope_certificate_sha256,
        "research_scope": {
            "stock_code": pin.stock_code,
            "exchange": pin.exchange,
            "date_from": pin.date_from,
            "date_to": pin.date_to,
        },
        "horizon_coverage": horizon_coverage,
        "chart_artifact_audit": artifact_audit,
        "independent_return_audit": {"tolerance": 0, **return_audit},
        "independent_path_metric_audit": {"tolerance": 0, **path_audit},
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
