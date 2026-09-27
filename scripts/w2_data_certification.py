"""Physically audit a pinned raw + adjustment-factor overlay for W2.

The source manifests, content-addressed blobs, and delta database are opened
read-only. Generated audit files go to a new local artifacts directory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_MARKET_ROOT = Path("E:/AStockData/datasets/market_data")
DEFAULT_FORTUNE_ARTIFACTS = ROOT.parent / "stock-metaphysics-fortune-v1" / "artifacts" / "f5b1"
DEFAULT_RAW_MANIFEST = (
    DEFAULT_MARKET_ROOT / "manifests" /
    "overlay_v1_l2_composite_r3_tushare_none_1d_20260814_f8d20d528543_wm20260924_seq00000005.json"
)
DEFAULT_FACTOR_MANIFEST = (
    DEFAULT_MARKET_ROOT / "manifests" /
    "overlay_v1_factor_r3_tushare_adjfactor_1d_20260814_a4a1109b4c91_wm20260924_seq00000006.json"
)
DEFAULT_OBSERVED_INDEX_CALENDARS = {
    "SSE": ROOT / "data" / "import" / "calendar" / "SSE.csv",
    "SZSE": ROOT / "data" / "import" / "calendar" / "SZSE.csv",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path.name}")
    return value


def _read_observed_index_calendar(path: Path, *, exchange: str) -> tuple[np.ndarray, dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "trade_date" not in reader.fieldnames:
            raise ValueError(f"{exchange} observed calendar must contain trade_date")
        parsed = [
            date.fromisoformat(str(row.get("trade_date") or ""))
            for row in reader
        ]
    values = np.asarray(
        [value.year * 10000 + value.month * 100 + value.day for value in parsed],
        dtype=np.int64,
    )
    if not len(values):
        raise ValueError(f"{exchange} observed calendar is empty")
    if len(values) > 1 and np.any(np.diff(values) <= 0):
        raise ValueError(f"{exchange} observed calendar is duplicated or unsorted")
    return values, {
        "source_type": "observed_index_days",
        "provider": "tencent_ifzq_gtimg",
        "source_url": "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        "generator": "scripts/fetch_market_import.py; CALENDAR_SOURCES",
        "source_file_name": path.name,
        "source_file_sha256": _sha256(path),
        "source_file_row_count": len(values),
        "source_file_first_date": str(int(values[0])),
        "source_file_last_date": str(int(values[-1])),
        "independent_from_pinned_raw_overlay": True,
        "is_official_exchange_calendar": False,
    }


def _unique_entries(document: dict[str, Any], *, label: str) -> dict[str, dict[str, Any]]:
    rows = document.get("symbols")
    if not isinstance(rows, list):
        raise ValueError(f"{label} manifest is missing symbols[]")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("symbol"):
            raise ValueError(f"{label} manifest contains an invalid symbol row")
        symbol = str(row["symbol"])
        if symbol in result:
            raise ValueError(f"{label} manifest contains duplicate symbol: {symbol}")
        result[symbol] = row
    if document.get("symbol_count") is not None and int(document["symbol_count"]) != len(result):
        raise ValueError(f"{label} manifest symbol_count mismatch")
    return result


def _fetch_deltas(
    connection: duckdb.DuckDBPyConnection,
    manifest: dict[str, Any],
    symbols: list[str],
    *,
    kind: str,
) -> dict[str, list[tuple[Any, ...]]]:
    result: dict[str, list[tuple[Any, ...]]] = {symbol: [] for symbol in symbols}
    if not symbols:
        return result
    table = "daily_bars" if kind == "bars" else "adj_factors"
    value_cols = (
        "d.open, d.high, d.low, d.close, d.volume, d.amount"
        if kind == "bars" else "d.adj_factor"
    )
    seq = int(manifest.get("delta_commit_seq") or 0) if kind == "bars" else int(manifest.get("factor_commit_seq") or 0)
    watermark = int(manifest.get("delta_watermark") or 0) if kind == "bars" else int(manifest.get("factor_watermark") or 0)
    adjustment = "none" if kind == "bars" else "adj_factor"
    placeholders = ",".join("?" for _ in symbols)
    query = f"""
        SELECT d.symbol, d.trade_date, {value_cols}, d.batch_seq, d.batch_id
        FROM {table} d
        JOIN sync_batches b ON b.batch_id=d.batch_id AND b.store_id=d.store_id
        WHERE d.store_id=? AND d.symbol IN ({placeholders})
          AND d.batch_seq<=? AND d.watermark<=?
          AND b.commit_seq<=? AND b.watermark<=? AND b.status='committed'
          AND b.kind=? AND b.adjustment=? AND b.period='1d'
          AND b.base_dataset_id=?
        QUALIFY ROW_NUMBER() OVER (
          PARTITION BY d.symbol, d.trade_date
          ORDER BY d.batch_seq DESC, d.batch_id DESC
        ) = 1
        ORDER BY d.symbol, d.trade_date
    """
    parameters = [
        manifest.get("delta_store_id"), *symbols, seq, watermark, seq, watermark,
        kind, adjustment, manifest.get("base_dataset_id"),
    ]
    for row in connection.execute(query, parameters).fetchall():
        result[str(row[0])].append((row[1], *row[2:-2]))
    return result


def _read_base(
    market_root: Path,
    entry: dict[str, Any] | None,
    *,
    kind: str,
) -> tuple[np.ndarray, np.ndarray]:
    width = 6 if kind == "bars" else 1
    if not entry:
        return np.empty((0,), dtype=np.int64), np.empty((0, width), dtype=np.float64)
    blob_sha = str(entry.get("blob_sha256") or "").strip()
    if not blob_sha:
        return np.empty((0,), dtype=np.int64), np.empty((0, width), dtype=np.float64)
    if len(blob_sha) != 64 or any(char not in "0123456789abcdef" for char in blob_sha):
        raise ValueError("invalid blob SHA-256")
    path = market_root / "blobs" / f"{blob_sha}.npz"
    if not path.is_file():
        raise ValueError("missing content-addressed blob")
    if _sha256(path) != blob_sha:
        raise ValueError("blob SHA-256 mismatch")
    columns = ("open", "high", "low", "close", "volume", "amount") if kind == "bars" else ("adj_factor",)
    with np.load(path, allow_pickle=False) as archive:
        required = {"trade_date", *columns}
        if not required.issubset(archive.files):
            raise ValueError(f"blob schema missing {sorted(required - set(archive.files))}")
        dates = np.asarray(archive["trade_date"], dtype=np.int64)
        vectors = [np.asarray(archive[name], dtype=np.float64) for name in columns]
    if any(len(vector) != len(dates) for vector in vectors):
        raise ValueError("base date/value lengths do not match")
    values = np.column_stack(vectors) if vectors else np.empty((len(dates), 0), dtype=np.float64)
    return dates, values


def _audit_one(
    market_root: Path,
    entry: dict[str, Any] | None,
    delta_rows: list[tuple[Any, ...]],
    *,
    kind: str,
) -> tuple[dict[str, Any], np.ndarray]:
    from src.research.data_certification import merge_overlay_arrays, validate_overlay_series

    width = 6 if kind == "bars" else 1
    if not entry:
        return {"status": "MISSING", "errors": ["NO_MANIFEST_ENTRY"], "invalid_rows": []}, np.empty((0,), dtype=np.int64)
    try:
        base_dates, base_values = _read_base(market_root, entry, kind=kind)
        dates, values = merge_overlay_arrays(base_dates, base_values, delta_rows, value_width=width)
        declared_quality = str(entry.get("quality", "")).lower()
        report = validate_overlay_series(
            kind,
            dates,
            values,
            expected_count=int(entry.get("row_count") or -1),
            expected_first=int(entry.get("first_date") or -1),
            expected_last=int(entry.get("last_date") or -1),
        )
        if declared_quality != "ok":
            report["errors"] = sorted(set(report["errors"] + ["MANIFEST_QUALITY_NOT_OK"]))
            report["status"] = "FAIL"
            report["valid_dates"] = []
        report.update({"blob_sha256": entry.get("blob_sha256"), "quality": entry.get("quality")})
        return report, dates
    except Exception as exc:
        return {
            "status": "FAIL",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "invalid_rows": [],
            "invalid_row_count": 0,
            "valid_dates": [],
        }, np.empty((0,), dtype=np.int64)


def _observed_raw_date_unions(
    connection: duckdb.DuckDBPyConnection,
    market_root: Path,
    symbols: list[str],
    raw_entries: dict[str, dict[str, Any]],
    raw_manifest: dict[str, Any],
    securities: dict[str, dict[str, Any]],
    batch_size: int,
) -> dict[str, np.ndarray]:
    """Build a feed-derived date union; this is not an official calendar."""
    unions: dict[str, set[int]] = {}
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    for batch_number, offset in enumerate(range(0, len(symbols), batch_size), start=1):
        batch = symbols[offset:offset + batch_size]
        deltas = _fetch_deltas(connection, raw_manifest, batch, kind="bars")
        for symbol in batch:
            exchange = str(securities[symbol].get("exchange") or "").strip().upper()
            if not exchange:
                raise ValueError(f"SecurityMaster exchange missing for {symbol}")
            report, _ = _audit_one(
                market_root, raw_entries.get(symbol), deltas[symbol], kind="bars"
            )
            observed_dates = report.get("valid_dates", [])
            unions.setdefault(exchange, set()).update(int(value) for value in observed_dates)
        print(
            f"W2 observed-date union batch {batch_number}/{total_batches}; "
            f"securities={min(offset + len(batch), len(symbols))}/{len(symbols)}",
            flush=True,
        )
    return {
        exchange: np.asarray(sorted(values), dtype=np.int64)
        for exchange, values in sorted(unions.items())
    }


def _build_reference_date_sets(
    raw_date_unions: dict[str, np.ndarray],
    calendar_paths: dict[str, Path],
    *,
    raw_manifest: dict[str, Any],
    raw_manifest_path: Path,
    cutoff: date,
    full_pit_universe: bool,
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]], dict[str, np.ndarray], dict[str, dict[str, Any]]]:
    cutoff_int = _date_int(cutoff)
    raw_as_of = {
        exchange: values[values <= cutoff_int]
        for exchange, values in raw_date_unions.items()
    }
    reference_dates: dict[str, np.ndarray] = {}
    sources: dict[str, dict[str, Any]] = {}
    comparisons: dict[str, dict[str, Any]] = {}
    for exchange in sorted(set(raw_as_of) | set(calendar_paths)):
        raw_dates = raw_as_of.get(exchange, np.empty((0,), dtype=np.int64))
        if exchange in calendar_paths:
            full_calendar, source = _read_observed_index_calendar(
                calendar_paths[exchange],
                exchange=exchange,
            )
            dates = full_calendar[full_calendar <= cutoff_int]
            if not len(dates):
                raise ValueError(f"{exchange} observed calendar has no dates through PIT cutoff")
            source.update({
                "effective_cutoff": cutoff.isoformat(),
                "effective_date_count": len(dates),
                "effective_first_date": str(int(dates[0])),
                "effective_last_date": str(int(dates[-1])),
            })
        else:
            dates = raw_dates
            source = {
                "source_type": "pinned_raw_overlay_date_union",
                "provider": raw_manifest.get("dataset_id"),
                "source_file_name": raw_manifest_path.name,
                "source_file_sha256": _sha256(raw_manifest_path),
                "source_file_row_count": len(dates),
                "source_file_first_date": str(int(dates[0])) if len(dates) else None,
                "source_file_last_date": str(int(dates[-1])) if len(dates) else None,
                "effective_cutoff": cutoff.isoformat(),
                "effective_date_count": len(dates),
                "effective_first_date": str(int(dates[0])) if len(dates) else None,
                "effective_last_date": str(int(dates[-1])) if len(dates) else None,
                "independent_from_pinned_raw_overlay": False,
                "is_official_exchange_calendar": False,
            }
        reference_dates[exchange] = dates
        sources[exchange] = source
        if full_pit_universe:
            reference_only = np.setdiff1d(dates, raw_dates, assume_unique=True)
            raw_only = np.setdiff1d(raw_dates, dates, assume_unique=True)
            comparisons[exchange] = {
                "status": "FULL_PIT_UNION_COMPARISON",
                "reference_dates_absent_from_raw_overlay_union_count": len(reference_only),
                "raw_overlay_union_dates_absent_from_reference_count": len(raw_only),
                "reference_only_samples": [str(value) for value in reference_only[:5]],
                "raw_overlay_only_samples": [str(value) for value in raw_only[:5]],
            }
        else:
            comparisons[exchange] = {
                "status": "SAMPLE_ONLY_NOT_COMPARABLE_TO_FULL_EXCHANGE_CALENDAR",
                "reference_dates_absent_from_raw_overlay_union_count": None,
                "raw_overlay_union_dates_absent_from_reference_count": None,
                "reference_only_samples": [],
                "raw_overlay_only_samples": [],
            }
    return reference_dates, sources, raw_as_of, comparisons


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _date_int(value: date) -> int:
    return value.year * 10000 + value.month * 100 + value.day


def _audit_batch(
    connection: duckdb.DuckDBPyConnection,
    market_root: Path,
    symbols: list[str],
    raw_entries: dict[str, dict[str, Any]],
    factor_entries: dict[str, dict[str, Any]],
    raw_manifest: dict[str, Any],
    factor_manifest: dict[str, Any],
    securities: dict[str, dict[str, Any]],
    memberships: dict[str, dict[str, Any]],
    reference_date_sets: dict[str, np.ndarray],
    cutoff: date,
) -> list[dict[str, Any]]:
    raw_deltas = _fetch_deltas(connection, raw_manifest, symbols, kind="bars")
    factor_deltas = _fetch_deltas(connection, factor_manifest, symbols, kind="factor")
    output: list[dict[str, Any]] = []
    for symbol in symbols:
        raw_report, raw_dates = _audit_one(
            market_root, raw_entries.get(symbol), raw_deltas[symbol], kind="bars"
        )
        factor_report, factor_dates = _audit_one(
            market_root, factor_entries.get(symbol), factor_deltas[symbol], kind="factor"
        )
        scope = _scope_row(
            {"raw": raw_report, "factor": factor_report},
            securities[symbol],
            memberships[symbol],
            cutoff=cutoff,
            raw_dates=raw_dates,
            factor_dates=factor_dates,
            reference_date_set=reference_date_sets.get(
                str(securities[symbol].get("exchange") or "").strip().upper(),
                np.empty((0,), dtype=np.int64),
            ),
        )
        raw_report.pop("valid_dates", None)
        factor_report.pop("valid_dates", None)
        output.append({
            "symbol": symbol,
            "raw": raw_report,
            "factor": factor_report,
            "scope": scope,
        })
    return output


def _scope_row(
    audit: dict[str, Any],
    security: dict[str, Any],
    membership: dict[str, Any],
    *,
    cutoff: date,
    raw_dates: np.ndarray,
    factor_dates: np.ndarray,
    reference_date_set: np.ndarray,
) -> dict[str, Any]:
    from src.research.data_certification import classify_observed_date_gaps

    symbol = str(security["symbol"])
    raw, factor = audit["raw"], audit["factor"]
    reasons: list[str] = []
    if raw["status"] not in {"PASS", "PARTIAL"}:
        reasons.append("RAW_NOT_PHYSICALLY_AVAILABLE")
    if factor["status"] not in {"PASS", "PARTIAL"}:
        reasons.append("FACTOR_NOT_PHYSICALLY_AVAILABLE")
    listing = date.fromisoformat(str(security["listing_date"]))
    start = max(listing, date.fromisoformat(str(membership["effective_start"])))
    end = min(_to_date(membership.get("effective_end")) or (cutoff + timedelta(days=1)), cutoff + timedelta(days=1))
    if listing > cutoff:
        reasons.append("LISTING_AFTER_PIT_EVIDENCE_CUTOFF")
    if start >= end:
        reasons.append("NO_PIT_MEMBERSHIP_WITHIN_EVIDENCE_CUTOFF")

    usable_dates: list[int] = []
    raw_invalid_dates = np.asarray(
        [int(row["trade_date"]) for row in raw.get("invalid_rows", [])], dtype=np.int64
    )
    factor_invalid_dates = np.asarray(
        [int(row["trade_date"]) for row in factor.get("invalid_rows", [])], dtype=np.int64
    )
    verified_raw_dates = raw_dates if raw["status"] in {"PASS", "PARTIAL"} else np.empty((0,), dtype=np.int64)
    verified_factor_dates = factor_dates if factor["status"] in {"PASS", "PARTIAL"} else np.empty((0,), dtype=np.int64)
    valid_raw_dates = np.setdiff1d(verified_raw_dates, raw_invalid_dates, assume_unique=True)
    valid_factor_dates = np.setdiff1d(verified_factor_dates, factor_invalid_dates, assume_unique=True)
    reference_start, reference_end = _date_int(start), _date_int(end)
    if start < end:
        reference_window = reference_date_set[
            (reference_date_set >= reference_start) & (reference_date_set < reference_end)
        ]
    else:
        reference_window = np.empty((0,), dtype=np.int64)
    raw_in_pit = valid_raw_dates[
        (valid_raw_dates >= reference_start) & (valid_raw_dates < reference_end)
    ] if start < end else np.empty((0,), dtype=np.int64)
    factor_in_pit = valid_factor_dates[
        (valid_factor_dates >= reference_start) & (valid_factor_dates < reference_end)
    ] if start < end else np.empty((0,), dtype=np.int64)
    raw_outside_reference = np.setdiff1d(raw_in_pit, reference_window, assume_unique=True)
    factor_outside_reference = np.setdiff1d(factor_in_pit, reference_window, assume_unique=True)
    reference_gap_audit = classify_observed_date_gaps(
        reference_date_set,
        verified_raw_dates,
        verified_factor_dates,
        invalid_raw_dates=raw_invalid_dates,
        invalid_factor_dates=factor_invalid_dates,
        start_date=reference_start,
        end_date_exclusive=reference_end,
    )
    if (
        raw["status"] in {"PASS", "PARTIAL"}
        and factor["status"] in {"PASS", "PARTIAL"}
        and len(raw_dates)
        and len(factor_dates)
        and start < end
        and listing <= cutoff
    ):
        common = np.intersect1d(
            valid_raw_dates,
            valid_factor_dates,
            assume_unique=True,
        )
        usable_dates = [
            int(value)
            for value in np.intersect1d(common, reference_window, assume_unique=True)
        ]
    if reference_gap_audit["available_candidate_date_count"] != len(usable_dates):
        raise ValueError(
            f"reference-calendar availability disagrees with raw/factor intersection for {symbol}"
        )
    if not usable_dates:
        reasons.append("NO_VALID_RAW_FACTOR_DATE_OVERLAP")
    if len(raw_outside_reference):
        reasons.append("RAW_DATES_OUTSIDE_REFERENCE_DATE_SET")
    if len(factor_outside_reference):
        reasons.append("FACTOR_DATES_OUTSIDE_REFERENCE_DATE_SET")

    factor_first = factor.get("first_date")
    raw_first = raw.get("first_date")
    late_factor_start = bool(raw_first and factor_first and factor_first > raw_first)
    max_calendar_gap = None
    if len(usable_dates) > 1:
        days = [date(int(value) // 10000, int(value) // 100 % 100, int(value) % 100) for value in usable_dates]
        max_calendar_gap = max((right - left).days for left, right in zip(days, days[1:], strict=False))
    return {
        "security_id": security["security_id"],
        "symbol": symbol,
        "exchange": str(security.get("exchange") or "").strip().upper(),
        "listing_date": security["listing_date"],
        "delisting_date_exclusive": membership.get("effective_end"),
        "pit_effective_start": membership["effective_start"],
        "pit_effective_end_exclusive": membership.get("effective_end"),
        "evidence_cutoff": cutoff.isoformat(),
        "raw_status": raw["status"],
        "factor_status": factor["status"],
        "factor_starts_after_raw": late_factor_start,
        "raw_manifest_first": raw.get("first_date"),
        "raw_manifest_last": raw.get("last_date"),
        "factor_manifest_first": factor.get("first_date"),
        "factor_manifest_last": factor.get("last_date"),
        "usable_start": str(usable_dates[0]) if usable_dates else None,
        "usable_end": str(usable_dates[-1]) if usable_dates else None,
        "usable_common_date_count": len(usable_dates),
        "max_calendar_gap_days": max_calendar_gap,
        "gap_classification": "REQUIRES_SUSPENSION_AND_STATUS_CROSSCHECK",
        "reference_date_gap_audit": reference_gap_audit,
        "raw_dates_outside_reference_count": len(raw_outside_reference),
        "raw_dates_outside_reference_samples": [str(value) for value in raw_outside_reference[:5]],
        "factor_dates_outside_reference_count": len(factor_outside_reference),
        "factor_dates_outside_reference_samples": [str(value) for value in factor_outside_reference[:5]],
        "raw_excluded_rows": raw.get("invalid_rows", []),
        "factor_excluded_rows": factor.get("invalid_rows", []),
        "has_verified_common_dates": bool(usable_dates),
        "confirmatory_research_eligible": False,
        "reasons": sorted(set(reasons)),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--security-master", type=Path, default=DEFAULT_FORTUNE_ARTIFACTS / "security_master.json")
    parser.add_argument("--pit-v2", type=Path, default=DEFAULT_FORTUNE_ARTIFACTS / "pit_universe_dataset_v2.json")
    parser.add_argument("--raw-manifest", type=Path, default=DEFAULT_RAW_MANIFEST)
    parser.add_argument("--factor-manifest", type=Path, default=DEFAULT_FACTOR_MANIFEST)
    parser.add_argument("--delta-database", type=Path, default=DEFAULT_MARKET_ROOT / "delta" / "market_delta.duckdb")
    parser.add_argument("--sse-index-calendar", type=Path, default=DEFAULT_OBSERVED_INDEX_CALENDARS["SSE"])
    parser.add_argument("--szse-index-calendar", type=Path, default=DEFAULT_OBSERVED_INDEX_CALENDARS["SZSE"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--max-symbols", type=int, default=None, help="run a deterministic prefix only; output is never a full certificate")
    args = parser.parse_args()

    market_root = args.market_root.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT / "artifacts"):
        parser.error("output-dir must be under this project's ignored artifacts/ directory")
    if output_dir.exists():
        parser.error(f"refusing to overwrite existing output directory: {output_dir}")
    if args.batch_size < 1 or args.batch_size > 500:
        parser.error("batch-size must be between 1 and 500")
    if args.max_symbols is not None and args.max_symbols < 1:
        parser.error("max-symbols must be positive")
    input_paths = (
        args.security_master,
        args.pit_v2,
        args.raw_manifest,
        args.factor_manifest,
        args.delta_database,
        args.sse_index_calendar,
        args.szse_index_calendar,
    )
    for path in input_paths:
        if not path.is_file():
            parser.error(f"input file does not exist: {path}")

    master = _json(args.security_master)
    pit = _json(args.pit_v2)
    raw_manifest = _json(args.raw_manifest)
    factor_manifest = _json(args.factor_manifest)
    security_rows = master.get("rows")
    membership_rows = pit.get("rows")
    if not isinstance(security_rows, list) or not isinstance(membership_rows, list):
        parser.error("SecurityMaster or PIT v2 rows[] missing")
    securities = {str(row["symbol"]): row for row in security_rows}
    memberships = {str(row["symbol"]): row for row in membership_rows}
    if len(securities) != len(security_rows) or len(memberships) != len(membership_rows):
        parser.error("duplicate symbol in SecurityMaster or PIT v2")
    if set(securities) != set(memberships):
        parser.error("SecurityMaster and PIT v2 symbol sets differ")
    if pit.get("security_master_digest") != master.get("dataset_digest"):
        parser.error("PIT v2 is not pinned to this SecurityMaster digest")

    raw_entries = _unique_entries(raw_manifest, label="raw overlay")
    factor_entries = _unique_entries(factor_manifest, label="factor overlay")
    all_symbols = sorted(securities)
    symbols = all_symbols[:args.max_symbols] if args.max_symbols is not None else all_symbols
    output_dir.mkdir(parents=True)
    connection = duckdb.connect(str(args.delta_database.resolve(strict=True)), read_only=True)
    total_batches = (len(symbols) + args.batch_size - 1) // args.batch_size
    cutoff = date.fromisoformat(str(pit["evidence_cutoff"]))
    raw_date_unions = _observed_raw_date_unions(
        connection,
        market_root,
        symbols,
        raw_entries,
        raw_manifest,
        securities,
        args.batch_size,
    )
    raw_manifest_sha256 = _sha256(args.raw_manifest)
    reference_date_sets, reference_sources, raw_date_sets_asof, calendar_comparisons = (
        _build_reference_date_sets(
            raw_date_unions,
            {
                "SSE": args.sse_index_calendar,
                "SZSE": args.szse_index_calendar,
            },
            raw_manifest=raw_manifest,
            raw_manifest_path=args.raw_manifest,
            cutoff=cutoff,
            full_pit_universe=args.max_symbols is None,
        )
    )
    reference_payload = {
        exchange: [int(value) for value in values]
        for exchange, values in reference_date_sets.items()
    }
    raw_union_payload = {
        exchange: [int(value) for value in values]
        for exchange, values in raw_date_sets_asof.items()
    }
    reference_calendar_digest = hashlib.sha256(
        json.dumps(reference_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    raw_union_digest = hashlib.sha256(
        json.dumps(raw_union_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    reference_calendar_path = output_dir / "w2_exchange_reference_dates.json"
    reference_calendar = {
        "schema_version": "w2-exchange-reference-dates-v1",
        "definition": "SSE/SZSE use pinned Tencent observed-index dates; exchanges without an independent local calendar use the pinned raw overlay date union",
        "evidence_cutoff": cutoff.isoformat(),
        "reference_calendar_digest": reference_calendar_digest,
        "raw_overlay_union_digest": raw_union_digest,
        "raw_manifest_dataset_id": raw_manifest.get("dataset_id"),
        "raw_manifest_sha256": raw_manifest_sha256,
        "exchanges": {
            exchange: {
                "reference_source": reference_sources[exchange],
                "reference_date_count": len(reference_date_sets[exchange]),
                "reference_first_date": (
                    str(int(reference_date_sets[exchange][0]))
                    if len(reference_date_sets[exchange]) else None
                ),
                "reference_last_date": (
                    str(int(reference_date_sets[exchange][-1]))
                    if len(reference_date_sets[exchange]) else None
                ),
                "reference_dates": [int(value) for value in reference_date_sets[exchange]],
                "raw_overlay_union_date_count": len(raw_date_sets_asof.get(exchange, [])),
                "raw_overlay_union_dates": [
                    int(value) for value in raw_date_sets_asof.get(exchange, [])
                ],
                "source_comparison": calendar_comparisons[exchange],
            }
            for exchange in reference_date_sets
        },
    }
    _write_json(reference_calendar_path, reference_calendar)
    raw_counts: Counter[str] = Counter()
    factor_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    reference_gap_status_counts: Counter[str] = Counter()
    reference_raw_unavailable_dates = 0
    reference_factor_unavailable_dates = 0
    reference_available_intervals = 0
    reference_unavailable_intervals = 0
    raw_dates_outside_reference = 0
    factor_dates_outside_reference = 0
    reference_identity_counts: Counter[str] = Counter()
    reference_common_date_identity_counts: Counter[str] = Counter()
    eligible = 0
    raw_path = output_dir / "w2_raw_physical_audit.jsonl"
    factor_path = output_dir / "w2_factor_physical_audit.jsonl"
    scope_path = output_dir / "w2_physical_scope_rows.jsonl"
    try:
        with raw_path.open("x", encoding="utf-8", newline="\n") as raw_stream, \
                factor_path.open("x", encoding="utf-8", newline="\n") as factor_stream, \
                scope_path.open("x", encoding="utf-8", newline="\n") as scope_stream:
            for batch_number, offset in enumerate(range(0, len(symbols), args.batch_size), start=1):
                batch = symbols[offset:offset + args.batch_size]
                batch_rows = _audit_batch(
                    connection,
                    market_root,
                    batch,
                    raw_entries,
                    factor_entries,
                    raw_manifest,
                    factor_manifest,
                    securities,
                    memberships,
                    reference_date_sets,
                    cutoff,
                )
                for row in batch_rows:
                    raw_counts[row["raw"]["status"]] += 1
                    factor_counts[row["factor"]["status"]] += 1
                    for reason in row["scope"]["reasons"]:
                        reason_counts[reason] += 1
                    gap_audit = row["scope"]["reference_date_gap_audit"]
                    exchange = row["scope"]["exchange"]
                    row["scope"]["reference_calendar_digest"] = reference_calendar_digest
                    row["scope"]["reference_calendar_source_type"] = reference_sources[exchange]["source_type"]
                    row["scope"]["reference_calendar_independent_from_raw_overlay"] = reference_sources[exchange][
                        "independent_from_pinned_raw_overlay"
                    ]
                    source_type = str(reference_sources[exchange]["source_type"])
                    reference_identity_counts[source_type] += 1
                    if row["scope"]["has_verified_common_dates"]:
                        reference_common_date_identity_counts[source_type] += 1
                    reference_gap_status_counts[gap_audit["status"]] += 1
                    reference_raw_unavailable_dates += int(
                        gap_audit["raw_unavailable_candidate_date_count"]
                    )
                    reference_factor_unavailable_dates += int(
                        gap_audit["factor_unavailable_candidate_date_count"]
                    )
                    reference_available_intervals += int(gap_audit["available_interval_count"])
                    reference_unavailable_intervals += int(gap_audit["unavailable_interval_count"])
                    raw_dates_outside_reference += int(row["scope"]["raw_dates_outside_reference_count"])
                    factor_dates_outside_reference += int(
                        row["scope"]["factor_dates_outside_reference_count"]
                    )
                    eligible += int(row["scope"]["has_verified_common_dates"])
                    raw_stream.write(json.dumps({"symbol": row["symbol"], **row["raw"]}, ensure_ascii=False) + "\n")
                    factor_stream.write(json.dumps({"symbol": row["symbol"], **row["factor"]}, ensure_ascii=False) + "\n")
                    scope_stream.write(json.dumps(row["scope"], ensure_ascii=False) + "\n")
                raw_stream.flush()
                factor_stream.flush()
                scope_stream.flush()
                print(
                    f"W2 overlay audit batch {batch_number}/{total_batches}; "
                    f"securities={min(offset + len(batch), len(symbols))}/{len(symbols)}; "
                    f"verified_reference_common_date_identities={eligible}",
                    flush=True,
                )
    finally:
        connection.close()

    manifest = {
        "schema_version": "w2-data-certification-manifest-v1",
        "certification_status": (
            "SAMPLE_ONLY" if args.max_symbols is not None
            else ("PHYSICAL_SCOPE_LIMITED" if eligible else "BLOCKED")
        ),
        "full_pit_universe_status": "COVERAGE_INCOMPLETE",
        "confirmatory_research_eligibility": "NOT_GRANTED_BY_DATA_PHYSICAL_AUDIT",
        "audit_scope": "PREFIX_SAMPLE" if args.max_symbols is not None else "FULL_PIT",
        "audit_limit": args.max_symbols,
        "audited_identity_count": len(symbols),
        "generated_on": date.today().isoformat(),
        "security_master": {
            "dataset_version": master.get("dataset_version"),
            "dataset_digest": master.get("dataset_digest"),
            "file_sha256": _sha256(args.security_master),
            "security_count": len(securities),
        },
        "pit_universe": {
            "dataset_version": pit.get("dataset_version"),
            "dataset_digest": pit.get("dataset_digest"),
            "file_sha256": _sha256(args.pit_v2),
            "evidence_cutoff": cutoff.isoformat(),
            "security_count": len(memberships),
            "rule_version": pit.get("rule_version"),
        },
        "raw_overlay": {
            "dataset_id": raw_manifest.get("dataset_id"),
            "manifest_file": args.raw_manifest.name,
            "manifest_sha256": _sha256(args.raw_manifest),
            "declared_watermark": raw_manifest.get("delta_watermark"),
            "commit_sequence": raw_manifest.get("delta_commit_seq"),
            "physical_status_counts": dict(sorted(raw_counts.items())),
        },
        "factor_overlay": {
            "dataset_id": factor_manifest.get("dataset_id"),
            "manifest_file": args.factor_manifest.name,
            "manifest_sha256": _sha256(args.factor_manifest),
            "declared_watermark": factor_manifest.get("factor_watermark"),
            "commit_sequence": factor_manifest.get("factor_commit_seq"),
            "physical_status_counts": dict(sorted(factor_counts.items())),
        },
        "scope": {
            "pit_identity_count": len(securities),
            "audited_identity_count": len(symbols),
            "identities_with_verified_common_dates": eligible,
            "identities_without_verified_common_dates": len(symbols) - eligible,
            "exclusion_reason_counts": dict(sorted(reason_counts.items())),
            "reference_date_gap_status_counts": dict(sorted(reference_gap_status_counts.items())),
            "reference_calendar_raw_unavailable_date_count": reference_raw_unavailable_dates,
            "reference_calendar_factor_unavailable_date_count": reference_factor_unavailable_dates,
            "reference_calendar_available_interval_count": reference_available_intervals,
            "reference_calendar_unavailable_interval_count": reference_unavailable_intervals,
            "raw_date_outside_reference_calendar_count": raw_dates_outside_reference,
            "factor_date_outside_reference_calendar_count": factor_dates_outside_reference,
            "identity_counts_by_reference_source": dict(sorted(reference_identity_counts.items())),
            "identities_with_common_dates_by_reference_source": dict(
                sorted(reference_common_date_identity_counts.items())
            ),
            "reference_calendar_interval_code_bits": {
                "1": "RAW_MISSING",
                "2": "RAW_INVALID",
                "4": "FACTOR_MISSING",
                "8": "FACTOR_INVALID",
                "combined": "bitwise OR of applicable flags; code 0 means raw and factor are both physically valid",
            },
            "usable_interval_semantics": "exact common valid raw/factor dates intersected with the pinned per-exchange reference date set, within PIT membership and evidence cutoff",
            "unclassified_gaps": "SSE/SZSE use an independent Tencent observed-index date set; BSE falls back to the pinned raw overlay date union. These are not official exchange calendars, and suspension/ST status is not cross-checked.",
            "corporate_action_semantics": "raw adjustment=none with same-date positive TuShare adj_factor; no factor is imputed.",
        },
        "reference_calendar": {
            "artifact": reference_calendar_path.name,
            "file_sha256": _sha256(reference_calendar_path),
            "reference_calendar_digest": reference_calendar_digest,
            "raw_overlay_union_digest": raw_union_digest,
            "sources_by_exchange": reference_sources,
            "source_comparisons_by_exchange": calendar_comparisons,
            "exchange_date_counts": {
                exchange: len(values) for exchange, values in reference_date_sets.items()
            },
        },
        "artifacts": {
            "raw_audit": raw_path.name,
            "factor_audit": factor_path.name,
            "scope_rows": scope_path.name,
            "reference_calendar": reference_calendar_path.name,
        },
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _write_json(output_dir / "w2_data_certification_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if args.max_symbols is not None or eligible == len(securities) else 2


if __name__ == "__main__":
    raise SystemExit(main())
