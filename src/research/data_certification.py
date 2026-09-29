"""Vectorized validation helpers for immutable market-data overlays."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

RAW_COLUMNS = ("open", "high", "low", "close", "volume", "amount")


def merge_overlay_arrays(
    base_dates: Sequence[int] | np.ndarray,
    base_values: Sequence[Sequence[float]] | np.ndarray,
    delta_rows: Iterable[Sequence[Any]],
    *,
    value_width: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Merge committed delta rows over a sorted base series without row-wise maps.

    Delta rows replace a base row with the same date.  The caller must select
    only committed batches within the manifest's pinned sequence and watermark.
    """
    dates = np.asarray(base_dates, dtype=np.int64)
    values = np.asarray(base_values, dtype=np.float64)
    if values.size == 0:
        values = np.empty((0, value_width), dtype=np.float64)
    elif values.ndim == 1:
        values = values.reshape((-1, value_width))
    if values.ndim != 2 or values.shape != (len(dates), value_width):
        raise ValueError("base date/value lengths or value width do not match")
    if len(dates) > 1 and np.any(np.diff(dates) <= 0):
        raise ValueError("base dates are duplicated or not strictly increasing")

    parsed_rows = list(delta_rows)
    if parsed_rows:
        delta_dates = np.fromiter((int(row[0]) for row in parsed_rows), dtype=np.int64)
        delta_values = np.asarray(
            [tuple(float(value) for value in row[1:]) for row in parsed_rows],
            dtype=np.float64,
        )
        if delta_values.shape != (len(delta_dates), value_width):
            raise ValueError("delta date/value lengths or value width do not match")
        if len(np.unique(delta_dates)) != len(delta_dates):
            raise ValueError("committed delta contains duplicate dates")

        keep_base = np.ones(len(dates), dtype=bool)
        if len(dates):
            positions = np.searchsorted(dates, delta_dates)
            in_range = positions < len(dates)
            matched = np.zeros(len(positions), dtype=bool)
            matched[in_range] = dates[positions[in_range]] == delta_dates[in_range]
            keep_base[positions[matched]] = False
        dates = np.concatenate((dates[keep_base], delta_dates))
        values = np.concatenate((values[keep_base], delta_values), axis=0)

    order = np.argsort(dates, kind="stable")
    dates, values = dates[order], values[order]
    if len(dates) > 1 and np.any(np.diff(dates) <= 0):
        raise ValueError("merged series has duplicate or unordered dates")
    return dates, values


def validate_overlay_series(
    kind: str,
    dates: Sequence[int] | np.ndarray,
    values: Sequence[Sequence[float]] | np.ndarray,
    *,
    expected_count: int,
    expected_first: int,
    expected_last: int,
) -> dict[str, Any]:
    """Check pinned manifest structure and physical value constraints."""
    if kind not in {"bars", "factor"}:
        raise ValueError("kind must be 'bars' or 'factor'")
    dates_array = np.asarray(dates, dtype=np.int64)
    values_array = np.asarray(values, dtype=np.float64)
    width = len(RAW_COLUMNS) if kind == "bars" else 1
    if values_array.size == 0:
        values_array = np.empty((0, width), dtype=np.float64)
    elif values_array.ndim == 1:
        values_array = values_array.reshape((-1, width))
    if values_array.shape != (len(dates_array), width):
        raise ValueError("date/value lengths or value width do not match")

    errors: list[str] = []
    row_issues: dict[int, list[str]] = {}
    if len(dates_array) == 0:
        errors.append("NO_ROWS")
    else:
        if len(dates_array) > 1 and np.any(np.diff(dates_array) <= 0):
            errors.append("DATES_DUPLICATED_OR_UNSORTED")
        if len(dates_array) != int(expected_count):
            errors.append("ROW_COUNT_MISMATCH")
        if int(dates_array[0]) != int(expected_first) or int(dates_array[-1]) != int(expected_last):
            errors.append("DATE_BOUNDS_MISMATCH")

        finite = np.isfinite(values_array).all(axis=1)
        for index in np.flatnonzero(~finite):
            row_issues[int(dates_array[index])] = ["NON_FINITE_VALUE"]

        if kind == "bars":
            open_, high, low, close, volume, amount = values_array.T
            masks = {
                "NON_POSITIVE_OHLC": np.column_stack((open_, high, low, close)).min(axis=1) <= 0,
                "HIGH_BELOW_COMPONENT": high < np.maximum.reduce((open_, low, close)),
                "LOW_ABOVE_COMPONENT": low > np.minimum.reduce((open_, high, close)),
                "NEGATIVE_VOLUME": volume < 0,
                "NEGATIVE_AMOUNT": amount < 0,
            }
        else:
            factor = values_array[:, 0]
            masks = {"NON_POSITIVE_FACTOR": factor <= 0}

        for code, mask in masks.items():
            for index in np.flatnonzero(mask):
                row_issues.setdefault(int(dates_array[index]), []).append(code)

    invalid_dates = sorted(row_issues)
    status = "FAIL" if errors else ("PARTIAL" if invalid_dates else "PASS")
    valid_dates = [int(value) for value in dates_array if int(value) not in row_issues]
    return {
        "status": status,
        "errors": sorted(set(errors)),
        "row_count": len(dates_array),
        "first_date": int(dates_array[0]) if len(dates_array) else None,
        "last_date": int(dates_array[-1]) if len(dates_array) else None,
        "invalid_row_count": len(invalid_dates),
        "invalid_rows": [
            {"trade_date": str(date), "issues": sorted(row_issues[date])}
            for date in invalid_dates
        ],
        "valid_dates": valid_dates if not errors else [],
    }


def classify_observed_date_gaps(
    reference_dates: Sequence[int] | np.ndarray,
    raw_dates: Sequence[int] | np.ndarray,
    factor_dates: Sequence[int] | np.ndarray,
    *,
    invalid_raw_dates: Sequence[int] | np.ndarray,
    invalid_factor_dates: Sequence[int] | np.ndarray,
    start_date: int,
    end_date_exclusive: int,
) -> dict[str, Any]:
    """Compare one identity with a pinned reference date set, never assume suspensions.

    The reference can be an independent observed-index date set or a
    same-feed fallback. Missing raw/factor rows remain unexplained until
    suspension/status history can account for them.
    """
    arrays = {
        "reference_dates": np.asarray(reference_dates, dtype=np.int64),
        "raw_dates": np.asarray(raw_dates, dtype=np.int64),
        "factor_dates": np.asarray(factor_dates, dtype=np.int64),
    }
    for label, values in arrays.items():
        if len(values) > 1 and np.any(np.diff(values) <= 0):
            raise ValueError(f"{label} must be strictly increasing")
    if start_date >= end_date_exclusive:
        return {
            "status": "NO_PIT_WINDOW",
            "candidate_date_count": 0,
            "available_candidate_date_count": 0,
            "unavailable_candidate_date_count": 0,
            "available_interval_count": 0,
            "unavailable_interval_count": 0,
            "raw_unavailable_candidate_date_count": 0,
            "factor_unavailable_candidate_date_count": 0,
            "raw_unavailable_date_samples": [],
            "factor_unavailable_date_samples": [],
            "reference_calendar_index_ranges": [],
        }

    all_reference = arrays["reference_dates"]
    window_start = int(np.searchsorted(all_reference, start_date, side="left"))
    window_end = int(np.searchsorted(all_reference, end_date_exclusive, side="left"))
    reference = all_reference[window_start:window_end]
    invalid_raw = np.asarray(invalid_raw_dates, dtype=np.int64)
    invalid_factor = np.asarray(invalid_factor_dates, dtype=np.int64)
    raw_present = np.isin(reference, arrays["raw_dates"], assume_unique=True)
    factor_present = np.isin(reference, arrays["factor_dates"], assume_unique=True)
    raw_invalid = np.isin(reference, invalid_raw, assume_unique=True)
    factor_invalid = np.isin(reference, invalid_factor, assume_unique=True)
    raw_unavailable = ~raw_present | raw_invalid
    factor_unavailable = ~factor_present | factor_invalid
    codes = (
        (~raw_present).astype(np.uint8)
        | (raw_invalid.astype(np.uint8) << 1)
        | ((~factor_present).astype(np.uint8) << 2)
        | (factor_invalid.astype(np.uint8) << 3)
    )
    if len(codes):
        boundaries = np.flatnonzero(
            np.concatenate(([True], codes[1:] != codes[:-1], [True]))
        )
        ranges = [
            [window_start + int(left), window_start + int(right), int(codes[left])]
            for left, right in zip(boundaries[:-1], boundaries[1:], strict=True)
        ]
    else:
        ranges = []
    available = codes == 0
    available_interval_count = sum(code == 0 for _, _, code in ranges)
    unavailable_interval_count = len(ranges) - available_interval_count
    raw_unavailable_dates = reference[raw_unavailable]
    factor_unavailable_dates = reference[factor_unavailable]
    if not len(reference):
        status = "NO_CANDIDATE_DATES_IN_PIT_WINDOW"
    elif raw_unavailable_dates.size or factor_unavailable_dates.size:
        status = "GAPS_PRESENT_AGAINST_REFERENCE_DATE_SET"
    else:
        status = "NO_GAPS_AGAINST_REFERENCE_DATE_SET"
    return {
        "status": status,
        "candidate_date_count": int(len(reference)),
        "available_candidate_date_count": int(np.count_nonzero(available)),
        "unavailable_candidate_date_count": int(len(reference) - np.count_nonzero(available)),
        "available_interval_count": int(available_interval_count),
        "unavailable_interval_count": int(unavailable_interval_count),
        "raw_unavailable_candidate_date_count": int(len(raw_unavailable_dates)),
        "factor_unavailable_candidate_date_count": int(len(factor_unavailable_dates)),
        "raw_unavailable_date_samples": [str(value) for value in raw_unavailable_dates[:5]],
        "factor_unavailable_date_samples": [str(value) for value in factor_unavailable_dates[:5]],
        "reference_calendar_index_ranges": ranges,
    }
