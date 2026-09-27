from __future__ import annotations

import numpy as np
import pytest

from src.research.data_certification import (
    classify_observed_date_gaps,
    merge_overlay_arrays,
    validate_overlay_series,
)


def test_merge_overlay_replaces_base_and_returns_sorted_dates() -> None:
    dates, values = merge_overlay_arrays(
        [20240102, 20240104],
        [[10.0], [40.0]],
        [(20240103, 30.0), (20240104, 41.0)],
        value_width=1,
    )

    assert dates.tolist() == [20240102, 20240103, 20240104]
    assert values[:, 0].tolist() == [10.0, 30.0, 41.0]


def test_merge_overlay_rejects_duplicate_dates_in_pinned_inputs() -> None:
    with pytest.raises(ValueError, match="base dates"):
        merge_overlay_arrays([20240102, 20240102], [[1.0], [2.0]], [], value_width=1)
    with pytest.raises(ValueError, match="delta contains duplicate"):
        merge_overlay_arrays([], np.empty((0, 1)), [(20240102, 1.0), (20240102, 2.0)], value_width=1)


def test_raw_audit_keeps_strict_ohlc_bound_failures_visible() -> None:
    result = validate_overlay_series(
        "bars",
        [20240102, 20240103],
        [
            [10.0, 11.0, 9.0, 10.5, 100.0, 1000.0],
            [10.0, 10.4, 9.0, 10.5, 100.0, 1000.0],
        ],
        expected_count=2,
        expected_first=20240102,
        expected_last=20240103,
    )

    assert result["status"] == "PARTIAL"
    assert result["invalid_rows"] == [
        {"trade_date": "20240103", "issues": ["HIGH_BELOW_COMPONENT"]}
    ]
    assert result["valid_dates"] == [20240102]


def test_factor_audit_rejects_non_positive_or_non_finite_values() -> None:
    result = validate_overlay_series(
        "factor",
        [20240102, 20240103],
        [[1.0], [0.0]],
        expected_count=2,
        expected_first=20240102,
        expected_last=20240103,
    )

    assert result["status"] == "PARTIAL"
    assert result["invalid_rows"] == [
        {"trade_date": "20240103", "issues": ["NON_POSITIVE_FACTOR"]}
    ]


def test_observed_date_union_reports_gaps_without_calling_them_suspensions() -> None:
    result = classify_observed_date_gaps(
        [20240101, 20240102, 20240103, 20240104, 20240105],
        [20240102, 20240103, 20240105],
        [20240102, 20240103, 20240104],
        invalid_raw_dates=[20240105],
        invalid_factor_dates=[],
        start_date=20240102,
        end_date_exclusive=20240105,
    )

    assert result["status"] == "GAPS_PRESENT_AGAINST_REFERENCE_DATE_SET"
    assert result["candidate_date_count"] == 3
    assert result["available_candidate_date_count"] == 2
    assert result["unavailable_candidate_date_count"] == 1
    assert result["raw_unavailable_candidate_date_count"] == 1
    assert result["factor_unavailable_candidate_date_count"] == 0
    assert result["raw_unavailable_date_samples"] == ["20240104"]
    assert result["reference_calendar_index_ranges"] == [[1, 3, 0], [3, 4, 1]]


def test_observed_date_union_respects_pit_window_and_invalid_factor_rows() -> None:
    result = classify_observed_date_gaps(
        [20240101, 20240102, 20240103],
        [20240101, 20240102, 20240103],
        [20240101, 20240102, 20240103],
        invalid_raw_dates=[],
        invalid_factor_dates=[20240102],
        start_date=20240102,
        end_date_exclusive=20240104,
    )

    assert result["candidate_date_count"] == 2
    assert result["raw_unavailable_candidate_date_count"] == 0
    assert result["factor_unavailable_candidate_date_count"] == 1
    assert result["factor_unavailable_date_samples"] == ["20240102"]
    assert result["reference_calendar_index_ranges"] == [[1, 2, 8], [2, 3, 0]]


def test_observed_date_union_returns_empty_status_outside_pit_window() -> None:
    result = classify_observed_date_gaps(
        [20240102],
        [20240102],
        [20240102],
        invalid_raw_dates=[],
        invalid_factor_dates=[],
        start_date=20240103,
        end_date_exclusive=20240103,
    )

    assert result["status"] == "NO_PIT_WINDOW"
    assert result["candidate_date_count"] == 0
    assert result["reference_calendar_index_ranges"] == []
