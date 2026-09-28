"""Finite, replayable certification for the first released observation scope.

This module deliberately certifies one bounded exploratory dataset. It never
overrides the full W2 PIT-universe status and does not grant confirmatory
research eligibility.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import numpy as np
from src.research.scoped_data_certificate_evidence import BIRTH_EVIDENCE, LIMITATIONS

CERTIFICATE_ID = "w2-szse-002561-20120223-20180514-v1"
CERTIFICATE_STATUS = "CERTIFIED_LIMITED_OBSERVATION_RANGE"
CERTIFICATE_SCHEMA = "w2-limited-observation-range-v1"
SECURITY_ID = "dba06cf4-8e33-594d-a077-595dbcb029bd"
SYMBOL = "SZSE.STK.002561"
STOCK_CODE = "002561"
EXCHANGE = "SZSE"
START_DATE = date(2012, 2, 23)
END_DATE = date(2018, 5, 14)
MAX_HORIZON = 60
DIVIDEND_ROUNDING_TOLERANCE = 0.01

def _int_dates(values: Any, label: str) -> np.ndarray:
    parsed = np.asarray(values, dtype=np.int64)
    if parsed.ndim != 1:
        raise ValueError(f"{label} 必须是一维日期序列")
    if len(parsed) > 1 and np.any(np.diff(parsed) <= 0):
        raise ValueError(f"{label} 日期重复或未严格递增")
    return parsed


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def audit_observation_range(
    *,
    reference_dates: Any,
    raw_dates: Any,
    raw_values: Any,
    factor_dates: Any,
    factor_values: Any,
    benchmark_dates: Any,
    benchmark_closes: Any,
    corporate_actions: list[dict[str, Any]],
    pit_start: date,
    pit_end_exclusive: date | None,
    evidence_cutoff: date,
    start_date: date = START_DATE,
    end_date: date = END_DATE,
    max_horizon: int = MAX_HORIZON,
) -> dict[str, Any]:
    """Prove exact date coverage and action reconciliation for the fixed scope.

    The result is valid only for the explicitly named observed-index date set.
    Missing or extra dates, incomplete forward horizons, invalid bars, or an
    unexplained adjustment-factor change fail closed.
    """
    if (start_date, end_date, max_horizon) != (START_DATE, END_DATE, MAX_HORIZON):
        raise ValueError("此版本证书只允许预先固定的 002561 日期范围和 60 日最长窗口")
    if pit_start > start_date or (pit_end_exclusive and end_date >= pit_end_exclusive):
        raise ValueError("认证日期越出 PIT 身份成员区间")
    if end_date > evidence_cutoff:
        raise ValueError("认证日期越出 PIT evidence cutoff")

    reference = _int_dates(reference_dates, "reference_dates")
    raw = _int_dates(raw_dates, "raw_dates")
    factors = _int_dates(factor_dates, "factor_dates")
    benchmark = _int_dates(benchmark_dates, "benchmark_dates")
    bars = np.asarray(raw_values, dtype=np.float64)
    factor = np.asarray(factor_values, dtype=np.float64)
    bench_close = np.asarray(benchmark_closes, dtype=np.float64)
    if bars.shape != (len(raw), 6):
        raise ValueError("raw 值必须是与日期逐行对应的 OHLCV/amount 六列")
    if factor.shape != (len(factors),) or bench_close.shape != (len(benchmark),):
        raise ValueError("factor/benchmark 日期与值长度不一致")
    if max_horizon < 1:
        raise ValueError("max_horizon 必须为正数")

    start_int = int(start_date.strftime("%Y%m%d"))
    end_int = int(end_date.strftime("%Y%m%d"))
    selected_reference = reference[(reference >= start_int) & (reference <= end_int)]
    if not len(selected_reference):
        raise ValueError("认证范围内没有参考观察日")

    def _window(values: np.ndarray, upper: int) -> np.ndarray:
        return values[(values >= start_int) & (values <= upper)]

    raw_scope = _window(raw, end_int)
    factor_scope = _window(factors, end_int)
    if not np.array_equal(raw_scope, selected_reference):
        raise ValueError("研究日期内 raw 日期与冻结参考日集合不完全相同")
    if not np.array_equal(factor_scope, selected_reference):
        raise ValueError("研究日期内 factor 日期与冻结参考日集合不完全相同")

    raw_index = {int(value): index for index, value in enumerate(raw)}
    end_position = raw_index.get(end_int)
    if end_position is None:
        raise ValueError("研究结束日没有 raw bar")
    maturity_position = end_position + max_horizon
    if maturity_position >= len(raw):
        raise ValueError("认证范围最后一个研究日没有完整的最长收益窗口")
    maturity_int = int(raw[maturity_position])
    maturity_date = date(maturity_int // 10000, maturity_int // 100 % 100, maturity_int % 100)
    if maturity_date > evidence_cutoff:
        raise ValueError("最长收益窗口越出 PIT evidence cutoff")

    outcome_reference = reference[
        (reference >= start_int) & (reference <= maturity_int)
    ]
    if not np.array_equal(_window(raw, maturity_int), outcome_reference):
        raise ValueError("研究日期到最长标签成熟日之间存在 raw 缺口或额外日期")
    if not np.array_equal(_window(factors, maturity_int), outcome_reference):
        raise ValueError("研究日期到最长标签成熟日之间存在 factor 缺口或额外日期")
    if not np.array_equal(_window(benchmark, maturity_int), outcome_reference):
        raise ValueError("研究日期到最长标签成熟日之间存在 benchmark 缺口或额外日期")

    outcome_mask = np.isin(raw, outcome_reference, assume_unique=True)
    outcome_raw_values = bars[outcome_mask]
    if not np.isfinite(outcome_raw_values).all():
        raise ValueError("研究与标签窗口内 raw 含非有限值")
    open_, high, low, close, volume, amount = outcome_raw_values.T
    if np.any(np.column_stack((open_, high, low, close)) <= 0):
        raise ValueError("研究与标签窗口内 OHLC 存在非正值")
    if np.any(high < np.maximum.reduce((open_, low, close))):
        raise ValueError("研究与标签窗口内存在 OHLC high 边界异常")
    if np.any(low > np.minimum.reduce((open_, high, close))):
        raise ValueError("研究与标签窗口内存在 OHLC low 边界异常")
    if np.any(volume <= 0) or np.any(amount <= 0):
        raise ValueError("研究与标签窗口内存在零/负成交量额，不能证明该观察为有效成交日")
    factor_slice = factor[np.isin(factors, outcome_reference, assume_unique=True)]
    if not np.isfinite(factor_slice).all() or np.any(factor_slice <= 0):
        raise ValueError("研究与标签窗口内 factor 含非正或非有限值")
    selected_benchmark = bench_close[
        np.isin(benchmark, outcome_reference, assume_unique=True)
    ]
    if not np.isfinite(selected_benchmark).all() or np.any(selected_benchmark <= 0):
        raise ValueError("研究与标签窗口内 benchmark close 含非正或非有限值")

    actions_by_date: dict[int, dict[str, Any]] = {}
    for action in corporate_actions:
        try:
            action_date = int(action["date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("公司行动记录缺少有效 date") from exc
        if action_date in actions_by_date:
            raise ValueError("公司行动记录有重复日期")
        actions_by_date[action_date] = action

    changes: list[dict[str, Any]] = []
    first_factor_position = int(np.searchsorted(factors, start_int, side="left"))
    start_change_position = max(1, first_factor_position)
    for position in range(start_change_position, len(factors)):
        action_date = int(factors[position])
        if action_date > maturity_int:
            break
        if action_date < start_int or factor[position] == factor[position - 1]:
            continue
        action = actions_by_date.get(action_date)
        if action is None or action.get("event_type") != "cash_dividend":
            raise ValueError(f"复权因子在 {action_date} 变化但没有对应现金分红行动记录")
        multiplier = float(action.get("share_multiplier", 1.0))
        gross_cash = action.get("meta", {}).get("cash_div_tax")
        if multiplier != 1.0 or gross_cash is None:
            raise ValueError(f"{action_date} 公司行动含未认证的送转或缺少税前现金额")
        previous_raw_index = int(np.searchsorted(raw, action_date, side="left")) - 1
        if previous_raw_index < 0:
            raise ValueError(f"{action_date} 缺少行动日前 raw 收盘价")
        previous_close = float(bars[previous_raw_index, 3])
        factor_ratio = float(factor[position] / factor[position - 1])
        implied_cash = previous_close * (1.0 - 1.0 / factor_ratio)
        delta = abs(implied_cash - float(gross_cash))
        if delta > DIVIDEND_ROUNDING_TOLERANCE:
            raise ValueError(
                f"{action_date} factor 隐含现金额与行动记录偏差超出 0.01：{delta:.6f}"
            )
        changes.append({
            "ex_date": str(action_date),
            "factor_ratio": round(factor_ratio, 10),
            "previous_close": round(previous_close, 6),
            "ledger_gross_cash_per_share": float(gross_cash),
            "factor_implied_cash_per_share": round(implied_cash, 6),
            "absolute_difference": round(delta, 6),
            "rounding_tolerance": DIVIDEND_ROUNDING_TOLERANCE,
            "ledger_source": action.get("source"),
        })

    scoped_action_dates = sorted(
        action_date
        for action_date, action in actions_by_date.items()
        if start_int <= action_date <= maturity_int
        and action.get("event_type") == "cash_dividend"
    )
    if scoped_action_dates != [int(item["ex_date"]) for item in changes]:
        raise ValueError("研究与最长标签窗口内的分红记录与 factor 变更日期不一一对应")

    return {
        "security_id": SECURITY_ID,
        "symbol": SYMBOL,
        "stock_code": STOCK_CODE,
        "exchange": EXCHANGE,
        "research_start_date": start_date.isoformat(),
        "research_end_date": end_date.isoformat(),
        "research_observation_count": int(len(selected_reference)),
        "research_dates": [str(int(value)) for value in selected_reference],
        "reference_source_type": "observed_index_days",
        "reference_calendar_is_official": False,
        "raw_reference_dates_equal": True,
        "factor_reference_dates_equal": True,
        "benchmark_reference_dates_equal_through_maturity": True,
        "longest_horizon_days": max_horizon,
        "outcome_maturity_end_date": maturity_date.isoformat(),
        "outcome_session_count_from_research_start": int(len(outcome_reference)),
        "raw_bar_value_checks": {
            "all_finite": True,
            "ohlc_positive_and_ordered": True,
            "volume_and_amount_positive": True,
            "zero_volume_rows": 0,
            "zero_amount_rows": 0,
        },
        "factor_value_checks": {"all_finite_and_positive": True},
        "benchmark_value_checks": {"all_finite_and_positive": True},
        "corporate_action_reconciliation": {
            "action_count": len(changes),
            "factor_change_count": len(changes),
            "all_factor_changes_matched": True,
            "all_cash_amount_differences_within_tolerance": True,
            "changes": changes,
        },
    }


def build_limited_scope_certificate(
    *,
    audit: dict[str, Any],
    input_versions: dict[str, Any],
    observed_listing_date: date,
    pit_effective_start: date,
    pit_effective_end_exclusive: date | None,
    evidence_cutoff: date,
) -> dict[str, Any]:
    """Bind the exact-series audit to pinned W2, market, benchmark and birth evidence."""
    if audit.get("security_id") != SECURITY_ID or audit.get("symbol") != SYMBOL:
        raise ValueError("有限范围证书仅允许预先指定的 SZSE.STK.002561 身份")
    if audit.get("research_start_date") != START_DATE.isoformat() or audit.get("research_end_date") != END_DATE.isoformat():
        raise ValueError("有限范围证书日期不符合冻结范围")
    if observed_listing_date != date(2011, 3, 3):
        raise ValueError("002561 listing date 与官方上市公告不一致")
    if pit_effective_start > START_DATE or (pit_effective_end_exclusive and END_DATE >= pit_effective_end_exclusive):
        raise ValueError("PIT membership 不覆盖冻结研究区间")
    if END_DATE > evidence_cutoff:
        raise ValueError("研究区间越出 PIT evidence cutoff")
    if BIRTH_EVIDENCE["published_at"] >= START_DATE.isoformat():
        raise ValueError("上市公告未能证明在首个研究日之前公开")
    if audit.get("research_observation_count") != 1513 or not audit.get("corporate_action_reconciliation", {}).get("all_factor_changes_matched"):
        raise ValueError("有限范围物理审计未通过")
    required_versions = {
        "w2_manifest_sha256", "w2_scope_row_sha256", "reference_calendar_sha256",
        "raw_manifest_sha256", "raw_blob_sha256", "factor_manifest_sha256",
        "factor_blob_sha256", "benchmark_file_sha256", "benchmark_meta_sha256",
        "corporate_action_file_sha256", "corporate_action_meta_sha256",
    }
    missing = required_versions - set(input_versions)
    if missing:
        raise ValueError(f"有限范围证书缺少输入版本：{sorted(missing)}")
    for key in required_versions:
        value = str(input_versions[key])
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"有限范围证书输入 digest 无效：{key}")

    payload = {
        "schema_version": CERTIFICATE_SCHEMA,
        "certificate_id": CERTIFICATE_ID,
        "status": CERTIFICATE_STATUS,
        "research_eligible": True,
        "confirmatory_research_eligible": False,
        "scope": {
            "security_id": SECURITY_ID,
            "symbol": SYMBOL,
            "stock_code": STOCK_CODE,
            "exchange": EXCHANGE,
            "research_start_date": START_DATE.isoformat(),
            "research_end_date": END_DATE.isoformat(),
            "research_time": "15:00:00",
            "research_timezone": "Asia/Shanghai",
            "observation_count": audit["research_observation_count"],
            "sample_kind": "single-security limited historical exploratory range",
        },
        "pit_membership": {
            "effective_start": pit_effective_start.isoformat(),
            "effective_end_exclusive": pit_effective_end_exclusive.isoformat() if pit_effective_end_exclusive else None,
            "evidence_cutoff": evidence_cutoff.isoformat(),
            "verified_listing_date": observed_listing_date.isoformat(),
        },
        "birth_evidence": BIRTH_EVIDENCE,
        "input_versions": input_versions,
        "audit": audit,
        "limitations": LIMITATIONS,
    }
    return {**payload, "certificate_sha256": _sha256_text(_canonical_json(payload))}


def verify_limited_scope_certificate(certificate: dict[str, Any]) -> None:
    """Reject altered, differently scoped, or eligibility-escalated certificates."""
    if certificate.get("schema_version") != CERTIFICATE_SCHEMA:
        raise ValueError("有限范围证书 schema 不匹配")
    if certificate.get("certificate_id") != CERTIFICATE_ID or certificate.get("status") != CERTIFICATE_STATUS:
        raise ValueError("有限范围证书身份或状态无效")
    if certificate.get("research_eligible") is not True or certificate.get("confirmatory_research_eligible") is not False:
        raise ValueError("有限范围证书资格状态无效")
    if certificate.get("scope", {}).get("security_id") != SECURITY_ID:
        raise ValueError("有限范围证书证券身份无效")
    scope = certificate.get("scope", {})
    if (
        scope.get("stock_code") != STOCK_CODE
        or scope.get("exchange") != EXCHANGE
        or scope.get("research_start_date") != START_DATE.isoformat()
        or scope.get("research_end_date") != END_DATE.isoformat()
        or scope.get("research_time") != "15:00:00"
        or scope.get("research_timezone") != "Asia/Shanghai"
        or scope.get("observation_count") != 1513
    ):
        raise ValueError("有限范围证书日期范围无效")
    if certificate.get("birth_evidence") != BIRTH_EVIDENCE:
        raise ValueError("有限范围证书出生日期来源或时间假设被修改")
    if certificate.get("limitations") != LIMITATIONS:
        raise ValueError("有限范围证书限制声明被修改")
    audit = certificate.get("audit", {})
    research_dates = audit.get("research_dates", [])
    if (
        audit.get("research_observation_count") != 1513
        or len(research_dates) != 1513
        or audit.get("research_start_date") != START_DATE.isoformat()
        or audit.get("research_end_date") != END_DATE.isoformat()
        or audit.get("reference_source_type") != "observed_index_days"
        or audit.get("reference_calendar_is_official") is not False
        or audit.get("longest_horizon_days") != MAX_HORIZON
        or audit.get("outcome_maturity_end_date") != "2018-08-07"
    ):
        raise ValueError("有限范围证书审计日期、日历来源或成熟窗口无效")
    if research_dates != sorted(set(research_dates)):
        raise ValueError("有限范围证书 research_dates 重复或未排序")
    versions = certificate.get("input_versions", {})
    digest_keys = [key for key in versions if key.endswith("_sha256")]
    if not digest_keys:
        raise ValueError("有限范围证书缺少输入 digest")
    for key in digest_keys:
        value = str(versions[key])
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError(f"有限范围证书输入 digest 无效：{key}")
    digest = certificate.get("certificate_sha256")
    payload = {key: value for key, value in certificate.items() if key != "certificate_sha256"}
    if digest != _sha256_text(_canonical_json(payload)):
        raise ValueError("有限范围证书 digest 不一致")


__all__ = [
    "BIRTH_EVIDENCE",
    "CERTIFICATE_ID",
    "CERTIFICATE_SCHEMA",
    "CERTIFICATE_STATUS",
    "DIVIDEND_ROUNDING_TOLERANCE",
    "END_DATE",
    "LIMITATIONS",
    "MAX_HORIZON",
    "SECURITY_ID",
    "START_DATE",
    "STOCK_CODE",
    "SYMBOL",
    "audit_observation_range",
    "build_limited_scope_certificate",
    "verify_limited_scope_certificate",
]
