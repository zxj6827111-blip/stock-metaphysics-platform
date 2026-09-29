from __future__ import annotations

import hashlib
import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.research.scoped_data_certificate import (
    END_DATE,
    SECURITY_ID,
    START_DATE,
    SYMBOL,
    audit_observation_range,
    build_limited_scope_certificate,
    verify_limited_scope_certificate,
)


def _observation_inputs() -> dict:
    weekdays = pd.bdate_range(START_DATE, END_DATE)
    research_indexes = np.linspace(0, len(weekdays) - 1, 1513, dtype=int)
    research_dates = weekdays[research_indexes]
    future_weekdays = pd.bdate_range(
        pd.Timestamp(END_DATE) + pd.Timedelta(days=1),
        date(2018, 8, 7),
    )
    future_dates = future_weekdays[:59].append(
        pd.DatetimeIndex([pd.Timestamp(date(2018, 8, 7))])
    )
    assert len(research_dates) == 1513
    assert research_dates[0].date() == START_DATE
    assert research_dates[-1].date() == END_DATE
    assert len(future_dates) == 60
    all_dates = research_dates.append(future_dates)
    date_ints = all_dates.strftime("%Y%m%d").astype(np.int64).to_numpy()
    reference = date_ints.copy()
    raw_values = np.tile(np.asarray([10.0, 10.5, 9.5, 10.0, 1000.0, 10000.0]), (len(reference), 1))
    return {
        "reference_dates": reference,
        "raw_dates": date_ints.copy(),
        "raw_values": raw_values,
        "factor_dates": date_ints.copy(),
        "factor_values": np.ones(len(date_ints), dtype=np.float64),
        "benchmark_dates": date_ints.copy(),
        "benchmark_closes": np.full(len(date_ints), 3000.0, dtype=np.float64),
        "corporate_actions": [],
        "pit_start": date(2011, 3, 3),
        "pit_end_exclusive": None,
        "evidence_cutoff": date(2018, 8, 7),
    }


def _audit(**overrides) -> dict:
    values = _observation_inputs()
    values.update(overrides)
    return audit_observation_range(**values)


def _valid_certificate() -> dict:
    digests = {
        key: hashlib.sha256(key.encode("utf-8")).hexdigest()
        for key in (
            "w2_manifest_sha256",
            "w2_scope_row_sha256",
            "reference_calendar_sha256",
            "raw_manifest_sha256",
            "raw_blob_sha256",
            "factor_manifest_sha256",
            "factor_blob_sha256",
            "benchmark_file_sha256",
            "benchmark_meta_sha256",
            "corporate_action_file_sha256",
            "corporate_action_meta_sha256",
        )
    }
    return build_limited_scope_certificate(
        audit=_audit(),
        input_versions=digests,
        observed_listing_date=date(2011, 3, 3),
        pit_effective_start=date(2011, 3, 3),
        pit_effective_end_exclusive=None,
        evidence_cutoff=date(2018, 8, 7),
    )


def test_audit_accepts_exact_observation_and_maturity_sets():
    result = _audit()

    assert result["security_id"] == SECURITY_ID
    assert result["symbol"] == SYMBOL
    assert result["research_observation_count"] == 1513
    assert result["outcome_maturity_end_date"] == "2018-08-07"
    assert result["reference_calendar_is_official"] is False
    assert result["corporate_action_reconciliation"]["action_count"] == 0


def test_audit_rejects_missing_raw_observation():
    values = _observation_inputs()
    values["raw_dates"] = np.delete(values["raw_dates"], 100)
    values["raw_values"] = np.delete(values["raw_values"], 100, axis=0)

    with pytest.raises(ValueError, match="raw 日期"):
        audit_observation_range(**values)


def test_audit_rejects_missing_benchmark_date_inside_maturity_window():
    values = _observation_inputs()
    values["benchmark_dates"] = np.delete(values["benchmark_dates"], -2)
    values["benchmark_closes"] = np.delete(values["benchmark_closes"], -2)

    with pytest.raises(ValueError, match="benchmark 缺口"):
        audit_observation_range(**values)


def test_audit_rejects_unexplained_adjustment_factor_change():
    values = _observation_inputs()
    values["factor_values"][100] = 1.1

    with pytest.raises(ValueError, match="没有对应现金分红"):
        audit_observation_range(**values)


def test_certificate_digest_and_scope_are_verified():
    certificate = _valid_certificate()
    verify_limited_scope_certificate(certificate)

    altered = dict(certificate)
    altered["research_eligible"] = False
    with pytest.raises(ValueError, match="资格状态"):
        verify_limited_scope_certificate(altered)


def test_certificate_rejects_rehashed_calendar_scope_escalation():
    certificate = _valid_certificate()
    altered = json.loads(json.dumps(certificate))
    altered["audit"]["reference_calendar_is_official"] = True
    payload = {key: value for key, value in altered.items() if key != "certificate_sha256"}
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    )
    altered["certificate_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(ValueError, match="审计日期、日历来源"):
        verify_limited_scope_certificate(altered)
