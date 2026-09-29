"""Build a small, provenance-pinned W4 engineering panel from the W2 artifacts.

This command intentionally does not certify a research-ready range. It consumes
one stock's W2 physical scope, keeps chart features separate from future labels,
and writes resumable Parquet shards under data/research_datasets/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time as wall_time
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_W2_ROOT = ROOT / "artifacts" / "w2-data-certification-20260927-full-06"
DEFAULT_MARKET_ROOT = Path("E:/AStockData/datasets/market_data")
DEFAULT_DATABASE = ROOT / "data" / "smp.sqlite3"
DEFAULT_DATASET_ROOT = ROOT / "data" / "research_datasets"
DEFAULT_DATASET_ID = "w4-engineering-002561-20120223-asof-v2"
RAW_MANIFEST_NAME = (
    "overlay_v1_l2_composite_r3_tushare_none_1d_20260814_"
    "f8d20d528543_wm20260924_seq00000005.json"
)
FACTOR_MANIFEST_NAME = (
    "overlay_v1_factor_r3_tushare_adjfactor_1d_20260814_"
    "a4a1109b4c91_wm20260924_seq00000006.json"
)
FEATURE_VERSION = "w4-f1-f4-factor-panel-v1"
RESEARCH_TIME = time(15, 0)
RESEARCH_TIMEZONE = "Asia/Shanghai"
HORIZONS = (1, 5, 10, 20, 60)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _strip_volatile(value: Any) -> Any:
    """Drop wall-clock fields so same inputs produce the same feature digest."""
    if isinstance(value, dict):
        return {
            key: _strip_volatile(item)
            for key, item in value.items()
            if key not in {"calculated_at", "computed_at", "generated_at"}
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"输入必须是 JSON object：{path.name}")
    return value


def _read_jsonl_match(path: Path, key: str, expected: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        for _line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if str(row.get(key)) == expected:
                return row
    raise KeyError(f"{path.name} 中找不到 {key}={expected}")


def _load_w2_inputs(w2_root: Path, market_root: Path, stock_code: str) -> dict[str, Any]:
    w2_manifest_path = w2_root / "w2_data_certification_manifest.json"
    calendar_path = w2_root / "w2_exchange_reference_dates.json"
    scope_path = w2_root / "w2_physical_scope_rows.jsonl"
    raw_audit_path = w2_root / "w2_raw_physical_audit.jsonl"
    factor_audit_path = w2_root / "w2_factor_physical_audit.jsonl"
    for path in (w2_manifest_path, calendar_path, scope_path, raw_audit_path, factor_audit_path):
        if not path.is_file():
            raise FileNotFoundError(f"缺少 W2 输入：{path}")

    w2_manifest = _read_json(w2_manifest_path)
    if w2_manifest.get("full_pit_universe_status") != "COVERAGE_INCOMPLETE":
        raise ValueError("W4 工程样本要求读取当前已知的 full PIT COVERAGE_INCOMPLETE 基线")
    if w2_manifest.get("confirmatory_research_eligibility") not in {
        False, "NOT_GRANTED_BY_DATA_PHYSICAL_AUDIT",
    }:
        raise ValueError("W2 确认性研究资格状态不是未授予；需重新审阅认证边界")
    raw_info = w2_manifest["raw_overlay"]
    factor_info = w2_manifest["factor_overlay"]
    raw_manifest_path = market_root / "manifests" / str(raw_info["manifest_file"])
    factor_manifest_path = market_root / "manifests" / str(factor_info["manifest_file"])
    if raw_manifest_path.name != RAW_MANIFEST_NAME or factor_manifest_path.name != FACTOR_MANIFEST_NAME:
        raise ValueError("W2 manifest 指向的 raw/factor 数据版本与预期冻结输入不一致")
    raw_manifest_sha = _sha256_file(raw_manifest_path)
    factor_manifest_sha = _sha256_file(factor_manifest_path)
    if raw_manifest_sha != raw_info["manifest_sha256"]:
        raise ValueError("raw manifest SHA-256 与 W2 清单不一致")
    if factor_manifest_sha != factor_info["manifest_sha256"]:
        raise ValueError("factor manifest SHA-256 与 W2 清单不一致")
    raw_manifest = _read_json(raw_manifest_path)
    factor_manifest = _read_json(factor_manifest_path)
    if raw_manifest.get("dataset_id") != raw_info.get("dataset_id"):
        raise ValueError("raw manifest dataset_id 与 W2 manifest 不一致")
    if factor_manifest.get("dataset_id") != factor_info.get("dataset_id"):
        raise ValueError("factor manifest dataset_id 与 W2 manifest 不一致")
    symbol_matches = [
        str(row["symbol"])
        for row in raw_manifest["symbols"]
        if str(row.get("symbol", "")).endswith(f".STK.{stock_code}")
    ]
    if len(symbol_matches) != 1:
        raise ValueError(f"证券代码必须唯一映射到 pinned raw overlay symbol：{stock_code}")
    symbol = symbol_matches[0]
    raw_entry = next((row for row in raw_manifest["symbols"] if row.get("symbol") == symbol), None)
    factor_entry = next((row for row in factor_manifest["symbols"] if row.get("symbol") == symbol), None)
    if raw_entry is None or factor_entry is None:
        raise KeyError(f"raw/factor manifest 中缺少 {symbol}")

    scope = _read_jsonl_match(scope_path, "symbol", symbol)
    raw_audit = _read_jsonl_match(raw_audit_path, "symbol", symbol)
    factor_audit = _read_jsonl_match(factor_audit_path, "symbol", symbol)
    if scope.get("raw_status") != "PASS" or scope.get("factor_status") != "PASS":
        raise ValueError("指定证券没有通过 W2 raw/factor 物理状态检查")
    if not scope.get("has_verified_common_dates"):
        raise ValueError("指定证券没有可用的 W2 raw/factor 日期交集")
    if raw_audit.get("status") != "PASS" or factor_audit.get("status") != "PASS":
        raise ValueError("指定证券 W2 物理审计状态不是 PASS")
    if raw_entry.get("blob_sha256") != raw_audit.get("blob_sha256"):
        raise ValueError("raw manifest 与 W2 raw 物理审计 blob SHA 不一致")
    if factor_entry.get("blob_sha256") != factor_audit.get("blob_sha256"):
        raise ValueError("factor manifest 与 W2 factor 物理审计 blob SHA 不一致")

    calendar = _read_json(calendar_path)
    calendar_digest = _sha256_file(calendar_path)
    if calendar_digest != w2_manifest["reference_calendar"]["file_sha256"]:
        raise ValueError("W2 reference calendar 文件 digest 与 manifest 不一致")
    if scope.get("reference_calendar_digest") != calendar.get("reference_calendar_digest"):
        raise ValueError("物理范围行与 W2 reference calendar digest 不一致")
    exchange = str(scope["exchange"]).upper()
    exchange_dates_value = calendar["exchanges"][exchange]
    exchange_dates = (
        exchange_dates_value.get("reference_dates", [])
        if isinstance(exchange_dates_value, dict)
        else exchange_dates_value
    )
    reference_dates = [int(value) for value in exchange_dates]
    if reference_dates != sorted(set(reference_dates)):
        raise ValueError("W2 reference dates 必须严格升序且无重复")

    raw_blob = market_root / "blobs" / f"{raw_entry['blob_sha256']}.npz"
    factor_blob = market_root / "blobs" / f"{factor_entry['blob_sha256']}.npz"
    if not raw_blob.is_file() or not factor_blob.is_file():
        raise FileNotFoundError("W2 pinned raw/factor content-addressed blob 缺失")
    if _sha256_file(raw_blob) != raw_entry["blob_sha256"]:
        raise ValueError("raw blob 文件 SHA-256 不匹配")
    if _sha256_file(factor_blob) != factor_entry["blob_sha256"]:
        raise ValueError("factor blob 文件 SHA-256 不匹配")
    with np.load(raw_blob, allow_pickle=False) as archive:
        required = {"trade_date", "open", "high", "low", "close", "volume", "amount"}
        if not required.issubset(archive.files):
            raise ValueError("raw blob schema 不完整")
        raw_dates = np.asarray(archive["trade_date"], dtype=np.int64)
        raw_values = {
            name: np.asarray(archive[name], dtype=np.float64)
            for name in ("open", "high", "low", "close", "volume", "amount")
        }
    with np.load(factor_blob, allow_pickle=False) as archive:
        if not {"trade_date", "adj_factor"}.issubset(archive.files):
            raise ValueError("factor blob schema 不完整")
        factor_dates = np.asarray(archive["trade_date"], dtype=np.int64)
        factor_values = np.asarray(archive["adj_factor"], dtype=np.float64)
    if len(raw_dates) != len(set(raw_dates.tolist())) or np.any(np.diff(raw_dates) <= 0):
        raise ValueError("raw blob trade dates duplicated or unsorted")
    if len(factor_dates) != len(set(factor_dates.tolist())) or np.any(np.diff(factor_dates) <= 0):
        raise ValueError("factor blob trade dates duplicated or unsorted")
    if any(len(values) != len(raw_dates) for values in raw_values.values()):
        raise ValueError("raw blob date/value length mismatch")
    if len(factor_dates) != len(factor_values):
        raise ValueError("factor blob date/value length mismatch")

    date_text = raw_dates.astype(str)
    bars = pd.DataFrame(raw_values)
    bars["trade_date"] = pd.to_datetime(date_text, format="%Y%m%d")
    cutoff = date.fromisoformat(str(w2_manifest["pit_universe"]["evidence_cutoff"]))
    bars = bars[bars["trade_date"].dt.date <= cutoff].reset_index(drop=True)
    factor_frame = pd.DataFrame({
        "trade_date": pd.to_datetime(factor_dates.astype(str), format="%Y%m%d"),
        "factor": factor_values,
    })
    factor_frame = factor_frame[factor_frame["trade_date"].dt.date <= cutoff].reset_index(drop=True)

    return {
        "w2_root": w2_root,
        "w2_manifest_path": w2_manifest_path,
        "w2_manifest": w2_manifest,
        "w2_manifest_sha256": _sha256_file(w2_manifest_path),
        "calendar_path": calendar_path,
        "calendar_sha256": calendar_digest,
        "calendar": calendar,
        "exchange": exchange,
        "reference_dates": reference_dates,
        "scope": scope,
        "raw_audit": raw_audit,
        "factor_audit": factor_audit,
        "raw_manifest": raw_manifest,
        "factor_manifest": factor_manifest,
        "raw_manifest_sha256": raw_manifest_sha,
        "factor_manifest_sha256": factor_manifest_sha,
        "raw_blob_sha256": raw_entry["blob_sha256"],
        "factor_blob_sha256": factor_entry["blob_sha256"],
        "bars": bars,
        "factors": factor_frame,
        "symbol": symbol,
        "stock_code": stock_code,
        "evidence_cutoff": cutoff,
    }


def _select_sample_dates(inputs: dict[str, Any], start_date: date, count: int) -> list[date]:
    scope = inputs["scope"]
    pit_start = date.fromisoformat(str(scope["pit_effective_start"]))
    pit_end = (
        date.fromisoformat(str(scope["pit_effective_end_exclusive"]))
        if scope.get("pit_effective_end_exclusive")
        else None
    )
    cutoff = inputs["evidence_cutoff"]
    bars = inputs["bars"]
    factors = inputs["factors"]
    raw_date_set = set(bars["trade_date"].dt.strftime("%Y%m%d").astype(int))
    factor_date_set = set(factors["trade_date"].dt.strftime("%Y%m%d").astype(int))
    date_to_index = {value: index for index, value in enumerate(inputs["reference_dates"])}
    ranges = [tuple(int(part) for part in item) for item in scope["reference_date_gap_audit"][
        "reference_calendar_index_ranges"
    ]]

    def _is_usable_reference_date(value: int) -> bool:
        index = date_to_index.get(value)
        if index is None:
            return False
        return any(start <= index < end and code == 0 for start, end, code in ranges)

    dates: list[date] = []
    for value in inputs["reference_dates"]:
        day = date(value // 10000, value // 100 % 100, value % 100)
        if day < start_date or day > cutoff:
            continue
        if day < pit_start or (pit_end is not None and day >= pit_end):
            continue
        if value not in raw_date_set or value not in factor_date_set:
            continue
        if not _is_usable_reference_date(value):
            continue
        dates.append(day)
        if len(dates) >= count:
            break
    if not dates or dates[0] != start_date:
        raise ValueError(f"起始研究日 {start_date} 未通过 PIT/calendar/raw/factor 联合重验")
    if len(dates) != count:
        raise ValueError(f"范围内可用工程样本不足：请求 {count}，实际 {len(dates)}")
    return dates


class _RecordingArtifactWriter:
    """保留 F4 artifact writer 的确定性 ID，并计算可复核 payload digest。"""

    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.records: dict[str, dict[str, Any]] = {}

    def persist_chart_artifact(self, **kwargs: Any) -> str:
        artifact_id = self.delegate.persist_chart_artifact(**kwargs)
        record = {"chart_id": artifact_id, **kwargs}
        self.records[artifact_id] = record
        return artifact_id


def _build_feature_payload(
    *,
    writer: _RecordingArtifactWriter,
    stock_code: str,
    stock_name: str,
    exchange: str,
    listing_date: date,
    first_observed_bar_date: date,
    source_birth_profile_version: str,
    as_of: datetime,
    birth_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """只接收出生档案、研究日和确定性引擎，不接收行情或未来标签。"""
    from src.core.config import settings
    from src.core.fortune.birth import resolve_market_first_trade_profile
    from src.core.orchestration.stock_fortune import StockFortuneEngine
    from src.core.schemas.bazi import BaziChart
    from src.core.schemas.common import Exchange, SourceRef
    from src.core.schemas.fortune import (
        FirstTradeObservation,
        FirstTradeObservationResolution,
        FirstTradeObservationStatus,
        FortuneTemporalInput,
        FortuneTemporalInputKind,
        StockFortuneEvaluationRequest,
        StockFortuneIdentity,
    )
    from src.engines.huangli.huangli_engine import HuangliEngine
    from src.factors.registry.compute import compute_factor_set

    exchange_enum = Exchange(exchange)
    raw_source_extra = {
        "observation_basis": "earliest_observed_daily_bar_date",
        "source_type": "composite_raw_daily_bar",
        "canonical_birth_profile_version": source_birth_profile_version,
        "historical_publication_status": "NOT_PROVEN",
    }
    if birth_evidence is not None:
        raw_source_extra.update({
            "historical_publication_status": "PUBLIC_LISTING_DATE_NOTICE_PRECEDES_RESEARCH_RANGE",
            "official_listing_notice": birth_evidence,
            "time_precision": "listing date corroborated; exact first trade time not observed",
        })
    raw_source = SourceRef(source="w2_pinned_raw_overlay", extra=raw_source_extra)
    observation = FirstTradeObservation(
        status=FirstTradeObservationStatus.OBSERVED_TRADING_DATE,
        first_trade_date=first_observed_bar_date,
        resolution=FirstTradeObservationResolution.DAILY_BAR,
        source=raw_source,
        source_version="w2-observed-daily-bar-date-v1",
        timezone=RESEARCH_TIMEZONE,
        reason=(
            "冻结 raw overlay 最早可观测日线日期；官方上市公告交叉支持上市日期。"
            "该日线不是首笔成交时刻；09:30 仍是 listing_open 假设。"
            if birth_evidence is not None
            else "冻结 raw overlay 最早可观测日线日期；它不是首笔成交时刻，且不能证明该证据在历史研究日已公开。"
        ),
    )
    profile = resolve_market_first_trade_profile(
        symbol=stock_code,
        exchange=exchange_enum,
        observation=observation,
        listing_date=listing_date,
        config_version=settings.config_version,
        market_session_version="a-share-session-v1",
    )
    request = StockFortuneEvaluationRequest(
        stock_identity=StockFortuneIdentity(
            symbol=stock_code,
            exchange=exchange_enum,
            name=stock_name,
            source=raw_source,
            source_version="w2-observed-daily-bar-date-v1",
        ),
        birth_profile=profile,
        evaluation_context=FortuneTemporalInput(
            kind=FortuneTemporalInputKind.EXACT_DATETIME,
            target_datetime=as_of,
        ),
        evaluation_source=SourceRef(source="w4-historical-dataset-engineering-replay"),
        evaluation_source_version="w4-history-dataset-v1",
        config_version=settings.config_version,
    )
    artifact_ids_before = set(writer.records)
    fortune = StockFortuneEngine(writer).evaluate(request)
    if fortune.temporal_resolution.context is None or "bazi" not in fortune.raw_chart:
        raise RuntimeError("F4 未能生成研究时点或 Bazi 原始盘面")

    local_as_of = as_of.astimezone(ZoneInfo(RESEARCH_TIMEZONE)).replace(tzinfo=None)
    huangli = HuangliEngine().snapshot(local_as_of, days=31)
    huangli_raw = _strip_volatile(
        huangli.model_dump(mode="json", exclude={"calculated_at"})
    )
    huangli_id = writer.persist_chart_artifact(
        engine_id=huangli.engine_id,
        engine_version=huangli.engine_version,
        symbol=stock_code,
        as_of=as_of,
        input_payload={
            "stock_code": stock_code,
            "as_of": as_of.isoformat(),
            "days": 31,
            "source_birth_profile_version": source_birth_profile_version,
        },
        raw_chart=huangli_raw,
        assumptions=[{"text": item} for item in huangli.assumptions],
        warnings=[item.model_dump(mode="json") for item in huangli.warnings],
        birth_profile_version=profile.birth_profile_version,
        config_version=huangli.config_version or settings.config_version,
    )
    chart = BaziChart.model_validate(fortune.raw_chart["bazi"])
    factor_set = compute_factor_set(chart, huangli, local_as_of, stock_code=stock_code)
    factor_set_payload = {
        "stock_code": factor_set.stock_code,
        "as_of": factor_set.as_of.isoformat(),
        "engine_version": factor_set.engine_version,
        "rule_version": factor_set.rule_version,
        "config_version": factor_set.config_version,
        "observations": [
            item.model_dump(mode="json", exclude={"computed_at"})
            for item in factor_set.observations
        ],
    }
    artifact_ids = [*fortune.chart_artifact_ids, huangli_id]
    new_artifact_ids = set(writer.records) - artifact_ids_before
    if set(artifact_ids) != new_artifact_ids:
        raise RuntimeError("F4/Huangli artifact 引用与本次 writer 输出不一致")
    artifact_digests = {
        artifact_id: _sha256_bytes(_canonical_json(writer.records[artifact_id]).encode("utf-8"))
        for artifact_id in artifact_ids
    }
    engine_versions = {
        "calendar": settings.calendar_engine_version,
        "bazi": settings.bazi_engine_version,
        "huangli": settings.huangli_engine_version,
        "fortune": fortune.engine_version,
        "ziwei": {
            "version": settings.ziwei_engine_version,
            "availability": "unavailable:not_applicable_variant",
        },
    }
    rule_versions = {
        "factor": settings.factor_rule_version,
        "fortune": fortune.rule_versions.model_dump(mode="json"),
        "factor_set": {
            "engine_version": factor_set.engine_version,
            "rule_version": factor_set.rule_version,
            "config_version": factor_set.config_version,
        },
    }
    return {
        "profile": profile,
        "artifact_ids": artifact_ids,
        "artifact_digests": artifact_digests,
        "engine_versions": engine_versions,
        "rule_versions": rule_versions,
        "feature_payload": {
            "fortune_snapshot": _strip_volatile(
                fortune.model_dump(mode="json", exclude={"raw_chart"})
            ),
            "factor_set": factor_set_payload,
            "chart_artifact_ids": artifact_ids,
            "chart_artifact_digests": artifact_digests,
        },
    }


def _db_birth_inputs(database_path: Path, stock_code: str, profile_version: str) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        master = connection.execute(
            "SELECT stock_code, name, exchange, listing_date FROM stock_master WHERE stock_code=?",
            (stock_code,),
        ).fetchone()
        profile = connection.execute(
            "SELECT stock_code, exchange, birth_basis, birth_datetime, timezone, source, "
            "birth_profile_version, evidence_json, assumptions_json, data_quality_json, "
            "variant_mode, variant_note, created_at, updated_at "
            "FROM stock_birth_profile WHERE stock_code=? AND birth_profile_version=?",
            (stock_code, profile_version),
        ).fetchone()
    finally:
        connection.close()
    if master is None or profile is None:
        raise KeyError(f"本机数据库缺少股票或出生档案：{stock_code} / {profile_version}")
    master_row = dict(master)
    profile_row = dict(profile)
    if master_row["listing_date"] is None:
        raise ValueError("stock_master.listing_date 不可用")
    listing_date = date.fromisoformat(str(master_row["listing_date"]))
    birth_datetime = datetime.fromisoformat(str(profile_row["birth_datetime"]))
    if birth_datetime.date() != listing_date or profile_row["birth_basis"] != "listing_open":
        raise ValueError("本地 canonical birth profile 不符合 listing_open 工程样本条件")
    if profile_row["variant_mode"] != "not_applicable":
        raise ValueError("W4 工程样本要求 variant_mode=not_applicable")
    if master_row["exchange"] != profile_row["exchange"]:
        raise ValueError("stock_master 与 birth profile 的交易所冲突")
    return {
        "master": master_row,
        "profile": profile_row,
        "listing_date": listing_date,
        "profile_version": str(profile_row["birth_profile_version"]),
        "profile_recorded_at": str(profile_row["created_at"]),
    }


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if pd.isna(value):
        return None
    return value


def _outcome_row(
    *,
    label: dict[str, Any],
    feature: dict[str, Any],
    bars: pd.DataFrame,
    bar_manifest_sha256: str,
    factor_manifest_sha256: str,
) -> dict[str, Any]:
    day = label["as_of"]
    outcome = {
        key: feature[key]
        for key in (
            "dataset_id", "security_id", "stock_code", "research_date", "research_time",
            "research_timezone", "feature_version", "pit_version", "birth_profile_version",
            "birth_profile_source_version", "calendar_version", "engine_versions_json",
            "rule_versions_json", "config_version",
        )
    }
    outcome.update({
        "label_version": label["label_version"],
        "bar_version": label["bar_version"],
        "factor_version": label["factor_version"],
        "price_basis": label["price_basis"],
        "bar_manifest_sha256": bar_manifest_sha256,
        "factor_manifest_sha256": factor_manifest_sha256,
        "trade_date": _json_scalar(label["trade_date"]),
        "trade_index": int(label["trade_index"]),
        "benchmark_code": label.get("benchmark_code"),
        "is_degraded": bool(label.get("is_degraded", False)),
        "max_favorable_move_20d": _json_scalar(label.get("max_favorable_move_20d")),
        "max_adverse_move_20d": _json_scalar(label.get("max_adverse_move_20d")),
        "max_drawdown_20d": _json_scalar(label.get("max_drawdown_20d")),
    })
    for horizon in HORIZONS:
        for metric in ("max_favorable_move", "max_adverse_move", "max_drawdown"):
            outcome[f"{metric}_{horizon}d"] = _json_scalar(label.get(f"{metric}_{horizon}d"))
        outcome[f"ret_{horizon}d"] = _json_scalar(label.get(f"ret_{horizon}d"))
        outcome[f"bench_ret_{horizon}d"] = _json_scalar(label.get(f"bench_ret_{horizon}d"))
        outcome[f"excess_return_{horizon}d"] = _json_scalar(label.get(f"excess_return_{horizon}d"))
        outcome[f"horizon_available_{horizon}d"] = bool(
            label.get("horizon_available", {}).get(f"{horizon}d", False)
        )
        outcome[f"horizon_requested_{horizon}d"] = True
        outcome[f"label_end_date_{horizon}d"] = _label_end_date(
            bars, label, horizon,
        )
    if _json_scalar(day) != feature["research_date"]:
        raise ValueError("label as_of 与 research_date 不一致")
    return outcome


def _label_end_date(
    bars: pd.DataFrame,
    label: dict[str, Any],
    horizon: int,
) -> date | None:
    """Persist the exact T+h bar date used to prevent time-split leakage."""
    if not label.get("horizon_available", {}).get(f"{horizon}d", False):
        return None
    trade_index = int(label["trade_index"])
    end_index = trade_index + int(horizon)
    if trade_index < 0 or end_index >= len(bars):
        raise ValueError("label kernel 声明周期可用，但对应行情终点越界")
    end_date = bars.iloc[end_index]["trade_date"]
    return pd.Timestamp(end_date).date()


def build_engineering_dataset(
    *,
    dataset_id: str,
    stock_code: str,
    start_date: date,
    max_observations: int | None,
    w2_root: Path,
    market_root: Path,
    database_path: Path,
    dataset_root: Path,
    scope_certificate_path: Path | None = None,
) -> dict[str, Any]:
    start = wall_time.perf_counter()
    from src.core.config import settings
    from src.core.orchestration.stock_fortune import DatabaseFortuneChartArtifactWriter
    from src.db.base import session_scope
    from src.research.historical_dataset import (
        HistoricalResearchDatasetStore,
        query_historical_dataset,
    )
    from src.research.labels.horizon_returns import LABEL_VERSION, compute_forward_returns

    w2_root = w2_root.resolve(strict=True)
    market_root = market_root.resolve(strict=True)
    database_path = database_path.resolve(strict=True)
    dataset_root = dataset_root.resolve()
    expected_root = (ROOT / "data" / "research_datasets").resolve()
    if dataset_root != expected_root:
        raise ValueError(f"dataset-root 必须严格为生成数据目录：{expected_root}")
    inputs = _load_w2_inputs(w2_root, market_root, stock_code)
    scope_certificate = None
    scope_material = None
    if scope_certificate_path is not None:
        from scripts.w2_limited_scope_evidence import verify_certificate_against_current_inputs
        from src.research.scoped_data_certificate import (
            BIRTH_EVIDENCE,
            SECURITY_ID,
            START_DATE,
            verify_limited_scope_certificate,
        )

        scope_certificate_path = scope_certificate_path.resolve(strict=True)
        scope_certificate = _read_json(scope_certificate_path)
        verify_limited_scope_certificate(scope_certificate)
        if stock_code != "002561" or inputs["scope"]["security_id"] != SECURITY_ID:
            raise ValueError("有限范围证书只适用于 SZSE.STK.002561")
        if start_date != START_DATE:
            raise ValueError("有限范围证书要求使用冻结的研究起始日期")
        if dataset_id == DEFAULT_DATASET_ID:
            raise ValueError("有限范围证书必须写入新的独立 dataset_id")
        if max_observations not in (None, scope_certificate["scope"]["observation_count"]):
            raise ValueError("有限范围证书的样本数固定为证书登记的 1,513 日")
        scope_material = verify_certificate_against_current_inputs(
            scope_certificate,
            w2_root=w2_root,
            market_root=market_root,
        )
        if scope_certificate["birth_evidence"] != BIRTH_EVIDENCE:
            raise ValueError("有限范围证书上市公告来源与代码内冻结来源不一致")
        dates = [
            date(int(value[:4]), int(value[4:6]), int(value[6:8]))
            for value in scope_certificate["audit"]["research_dates"]
        ]
    else:
        if max_observations is None:
            max_observations = 20
        if max_observations < 1 or max_observations > 1000:
            raise ValueError("工程样本 max_observations 必须在 1..1000 之间")
        dates = _select_sample_dates(inputs, start_date, max_observations)
    birth = _db_birth_inputs(database_path, stock_code, "v2-phase4b-listing_open")
    if birth["master"]["exchange"] != inputs["exchange"]:
        raise ValueError("本地 stock master 与 W2 identity exchange 不一致")
    if birth["listing_date"].isoformat() != inputs["scope"]["listing_date"]:
        raise ValueError("本地 stock master listing date 与 W2 SecurityMaster 不一致")
    if scope_certificate is not None:
        birth_profile_sha256 = hashlib.sha256(
            _canonical_json(birth["profile"]).encode("utf-8")
        ).hexdigest()
        expected_birth_inputs = {
            "birth_profile_version": birth["profile_version"],
            "birth_profile_recorded_at": birth["profile_recorded_at"],
            "birth_profile_row_sha256": birth_profile_sha256,
        }
        if any(
            scope_certificate["input_versions"].get(key) != value
            for key, value in expected_birth_inputs.items()
        ):
            raise ValueError("有限范围证书绑定的本机出生档案副本与当前数据库不一致")
    first_observed_bar_date = inputs["bars"].iloc[0]["trade_date"].date()
    if first_observed_bar_date != birth["listing_date"]:
        raise ValueError("raw overlay 最早 bar 与 listing date 不同；此差异需先解释")

    pit_version = str(inputs["w2_manifest"]["pit_universe"]["dataset_version"])
    pit_manifest_sha256 = inputs["w2_manifest_sha256"]
    pit_calendar_digest = str(inputs["calendar"]["reference_calendar_digest"])
    raw_dataset_id = str(inputs["raw_manifest"]["dataset_id"])
    factor_dataset_id = str(inputs["factor_manifest"]["dataset_id"])
    limited_scope = scope_certificate is not None
    benchmark = None
    if limited_scope:
        from src.research.labels.horizon_returns import BenchmarkSeries

        benchmark = BenchmarkSeries.from_frame(scope_material["benchmark_frame"])
    research_eligible = limited_scope
    research_use_status = (
        "EXPLORATORY_LIMITED_SCOPE" if limited_scope else "ENGINEERING_ONLY"
    )
    limitations = (
        list(scope_certificate["limitations"])
        if limited_scope
        else [
            "W2 remains COVERAGE_INCOMPLETE; this sample does not certify a research range.",
            "Birth-profile source publication time is not proven at historical T; all rows remain ineligible.",
            "W2 reference dates are observed-index/reference dates, not official exchange calendars.",
            "Suspension/ST explanations are not present for remaining market gaps.",
            "Benchmark identity/data are not in the pinned W2 overlay; benchmark and excess returns stay null.",
        ]
    )
    metadata = {
        "schema_version": "w4-historical-panel-v1",
        "status": "CERTIFIED_LIMITED_SCOPE_EXPLORATORY" if limited_scope else "ENGINEERING_ONLY",
        "research_eligible": research_eligible,
        "confirmatory_research_eligible": False,
        "full_pit_universe_status": inputs["w2_manifest"]["full_pit_universe_status"],
        "scope": {
            "security_id": inputs["scope"]["security_id"],
            "stock_code": stock_code,
            "exchange": inputs["exchange"],
            "research_dates": [day.isoformat() for day in dates],
            "research_time": RESEARCH_TIME.isoformat(),
            "research_timezone": RESEARCH_TIMEZONE,
            "sample_kind": (
                "single-security limited historical exploratory range"
                if limited_scope
                else "single-security deterministic engineering replay"
            ),
        },
        "input_versions": {
            "w2_manifest_sha256": pit_manifest_sha256,
            "pit_dataset_version": pit_version,
            "reference_calendar_digest": pit_calendar_digest,
            "raw_dataset_id": raw_dataset_id,
            "raw_manifest_sha256": inputs["raw_manifest_sha256"],
            "raw_blob_sha256": inputs["raw_blob_sha256"],
            "factor_dataset_id": factor_dataset_id,
            "factor_manifest_sha256": inputs["factor_manifest_sha256"],
            "factor_blob_sha256": inputs["factor_blob_sha256"],
            "source_birth_profile_version": birth["profile_version"],
            "source_birth_profile_recorded_at": birth["profile_recorded_at"],
            "label_end_date_method": "exact_stock_bar_at_trade_index_plus_horizon",
            **({
                "scope_certificate_id": scope_certificate["certificate_id"],
                "scope_certificate_sha256": scope_certificate["certificate_sha256"],
                "scope_certificate_input_versions": scope_certificate["input_versions"],
                "benchmark_file_sha256": scope_certificate["input_versions"]["benchmark_file_sha256"],
                "benchmark_provider": scope_certificate["input_versions"]["benchmark_provider"],
                "benchmark_snapshot_at": scope_certificate["input_versions"]["benchmark_snapshot_at"],
                "corporate_action_file_sha256": scope_certificate["input_versions"]["corporate_action_file_sha256"],
                "full_pit_universe_status": "COVERAGE_INCOMPLETE",
            } if limited_scope else {}),
        },
        "scope_certificate": ({
            "certificate_id": scope_certificate["certificate_id"],
            "certificate_sha256": scope_certificate["certificate_sha256"],
            "status": scope_certificate["status"],
            "birth_evidence": scope_certificate["birth_evidence"],
            "audit": scope_certificate["audit"],
            "limitations": scope_certificate["limitations"],
        } if limited_scope else None),
        "benchmark": ({
            "code": "000300",
            "storage_code": "IDX000300",
            "provider": scope_material["benchmark_meta"]["provider"],
            "snapshot_at": scope_material["benchmark_meta"]["fetched_at"],
            "adjustment": "none",
            "file_sha256": scope_certificate["input_versions"]["benchmark_file_sha256"],
        } if limited_scope else None),
        "known_limitations": limitations,
    }
    store = HistoricalResearchDatasetStore(
        dataset_root,
        dataset_id=dataset_id,
        metadata=metadata,
    )

    coverage_rows: dict[str, Any] = {}
    label_rows = compute_forward_returns(
        inputs["bars"],
        dates,
        stock_code=stock_code,
        horizons=HORIZONS,
        adj_factors=inputs["factors"],
        benchmark=benchmark,
        is_degraded=False,
        bar_version=raw_dataset_id,
        factor_version=factor_dataset_id,
        price_basis="raw_times_factor",
        coverage_out=coverage_rows,
    )
    labels_by_date = {row["as_of"].isoformat(): row for row in label_rows}
    if set(labels_by_date) != {day.isoformat() for day in dates}:
        raise RuntimeError("label kernel 没有为每个研究样本返回一行（缺失保持不可用，不能静默丢行）")

    from src.db.models import ChartArtifactRow

    features_by_year: dict[int, list[dict[str, Any]]] = {}
    outcomes_by_year: dict[int, list[dict[str, Any]]] = {}
    artifact_counts: dict[str, int] = {}
    resumed_shard_count = 0
    source_profile = birth["profile"]
    session_url = f"sqlite:///{database_path.as_posix()}"
    with session_scope(session_url) as session:
        writer = _RecordingArtifactWriter(DatabaseFortuneChartArtifactWriter(session))
        for day in dates:
            as_of = datetime.combine(day, RESEARCH_TIME, tzinfo=ZoneInfo(RESEARCH_TIMEZONE))
            computed = _build_feature_payload(
                writer=writer,
                stock_code=stock_code,
                stock_name=str(birth["master"]["name"] or ""),
                exchange=inputs["exchange"],
                listing_date=birth["listing_date"],
                first_observed_bar_date=first_observed_bar_date,
                source_birth_profile_version=birth["profile_version"],
                as_of=as_of,
                birth_evidence=(
                    scope_certificate["birth_evidence"] if limited_scope else None
                ),
            )
            profile_recorded_at = datetime.fromisoformat(str(source_profile["created_at"]))
            evidence_status = (
                "PUBLIC_LISTING_DATE_NOTICE_PRECEDES_T_LISTING_OPEN_TIME_ASSUMED"
                if limited_scope
                else (
                    "RECORDED_BEFORE_T_BUT_SOURCE_PUBLICATION_UNPROVEN"
                    if profile_recorded_at.date() <= day
                    else "NOT_PROVEN"
                )
            )
            feature = {
                "dataset_id": dataset_id,
                "security_id": inputs["scope"]["security_id"],
                "stock_code": stock_code,
                "research_date": day.isoformat(),
                "research_time": RESEARCH_TIME.isoformat(),
                "research_timezone": RESEARCH_TIMEZONE,
                "feature_version": FEATURE_VERSION,
                "pit_version": pit_version,
                "birth_profile_version": computed["profile"].birth_profile_version,
                "birth_profile_source_version": birth["profile_version"],
                "calendar_version": settings.calendar_engine_version,
                "engine_versions_json": _canonical_json(computed["engine_versions"]),
                "rule_versions_json": _canonical_json(computed["rule_versions"]),
                "config_version": settings.config_version,
                "pit_manifest_sha256": pit_manifest_sha256,
                "pit_calendar_digest": pit_calendar_digest,
                "birth_profile_source": str(source_profile["source"]),
                "birth_profile_recorded_at": profile_recorded_at.isoformat(),
                "birth_evidence_asof_status": evidence_status,
                "chart_artifact_ids_json": _canonical_json(computed["artifact_ids"]),
                "chart_artifact_digests_json": _canonical_json(computed["artifact_digests"]),
                "features_json": _canonical_json(computed["feature_payload"]),
                "research_use_status": research_use_status,
                "research_eligible": research_eligible,
            }
            outcome = _outcome_row(
                label=labels_by_date[day.isoformat()],
                feature=feature,
                bars=inputs["bars"],
                bar_manifest_sha256=inputs["raw_manifest_sha256"],
                factor_manifest_sha256=inputs["factor_manifest_sha256"],
            )
            features_by_year.setdefault(day.year, []).append(feature)
            outcomes_by_year.setdefault(day.year, []).append(outcome)
        persisted_ids = session.scalars(
            select(ChartArtifactRow.chart_id).where(
                ChartArtifactRow.chart_id.in_(list(writer.records))
            )
        ).all()
        if set(persisted_ids) != set(writer.records):
            raise RuntimeError("chart_artifact 存储确认未覆盖本次所有 artifact 引用")
        artifact_counts = {
            "artifact_references": len(writer.records),
            "verified_database_rows": len(persisted_ids),
        }

    source_common = {
        "w2_manifest_sha256": pit_manifest_sha256,
        "calendar_file_sha256": inputs["calendar_sha256"],
        "raw_manifest_sha256": inputs["raw_manifest_sha256"],
        "factor_manifest_sha256": inputs["factor_manifest_sha256"],
        "raw_blob_sha256": inputs["raw_blob_sha256"],
        "factor_blob_sha256": inputs["factor_blob_sha256"],
        **({
            "scope_certificate_sha256": scope_certificate["certificate_sha256"],
            "benchmark_file_sha256": scope_certificate["input_versions"]["benchmark_file_sha256"],
            "corporate_action_file_sha256": scope_certificate["input_versions"]["corporate_action_file_sha256"],
        } if limited_scope else {}),
        "birth_profile_row": source_profile,
        "feature_version": FEATURE_VERSION,
        "label_versions": {
            "label_version": LABEL_VERSION,
            "price_basis": "raw_times_factor",
            "horizons": list(HORIZONS),
            "end_date_method": "exact_stock_bar_at_trade_index_plus_horizon",
        },
    }
    expected_shards: list[str] = []
    for year in sorted(features_by_year):
        shard_key = f"{inputs['scope']['security_id']}/{year}"
        expected_shards.append(shard_key)
        source_digest = _sha256_bytes(_canonical_json({
            **source_common,
            "security_id": inputs["scope"]["security_id"],
            "year": year,
            "research_dates": [row["research_date"] for row in features_by_year[year]],
        }).encode("utf-8"))
        shard_result = store.write_shard(
            features_by_year[year],
            outcomes_by_year[year],
            source_digest=source_digest,
        )
        resumed_shard_count += int(bool(shard_result.get("resumed")))
    manifest = store.finalize(expected_shards=expected_shards)
    output = query_historical_dataset(dataset_root, dataset_id)
    expected_rows = len(dates)
    if len(output) != expected_rows or output[["security_id", "research_date"]].duplicated().any():
        raise RuntimeError("Parquet/DuckDB 回读的样本数或身份键不一致")
    elapsed = wall_time.perf_counter() - start
    parquet_bytes = sum(path.stat().st_size for path in store.root.rglob("*.parquet"))
    unavailable = {
        f"{horizon}d": int((~output[f"horizon_available_{horizon}d"].astype(bool)).sum())
        for horizon in HORIZONS
    }
    benchmark_unavailable = int(output["bench_ret_1d"].isna().sum())
    if limited_scope:
        horizon_unavailable_total = sum(unavailable.values())
        if horizon_unavailable_total or benchmark_unavailable:
            raise RuntimeError(
                "有限范围证书要求所有 1/5/10/20/60 日及 benchmark 标签完整；"
                f"horizon_unavailable={unavailable}, benchmark_unavailable={benchmark_unavailable}"
            )
    return {
        "dataset_root": str(store.root),
        "dataset_status": manifest["status"],
        "dataset_digest": manifest["dataset_digest"],
        "row_count": manifest["row_count"],
        "expected_shards": expected_shards,
        "resumed_shards": resumed_shard_count,
        "artifact_count": artifact_counts["artifact_references"],
        "artifact_rows_verified": artifact_counts["verified_database_rows"],
        "parquet_bytes": parquet_bytes,
        "parquet_bytes_per_row": round(parquet_bytes / manifest["row_count"], 2)
        if manifest["row_count"]
        else None,
        "elapsed_seconds": round(elapsed, 3),
        "observations_per_second": round(expected_rows / elapsed, 4) if elapsed else None,
        "horizon_unavailable_counts": unavailable,
        "benchmark_unavailable_count": benchmark_unavailable,
        "research_eligible": research_eligible,
        "research_use_status": research_use_status,
        "w2_status": inputs["w2_manifest"]["certification_status"],
        "w2_full_pit_status": inputs["w2_manifest"]["full_pit_universe_status"],
        "birth_evidence_status": (
            "PUBLIC_LISTING_DATE_NOTICE_PRECEDES_T_LISTING_OPEN_TIME_ASSUMED"
            if limited_scope else "NOT_PROVEN_AT_HISTORICAL_T"
        ),
        "bar_factor_coverage": coverage_rows,
        "sample_date_range": [dates[0].isoformat(), dates[-1].isoformat()],
        "limitations": metadata["known_limitations"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--stock-code", default="002561")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2012, 2, 23))
    parser.add_argument("--max-observations", type=int)
    parser.add_argument("--w2-root", type=Path, default=DEFAULT_W2_ROOT)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--scope-certificate", type=Path)
    args = parser.parse_args()
    try:
        result = build_engineering_dataset(
            dataset_id=args.dataset_id,
            stock_code=args.stock_code,
            start_date=args.start_date,
            max_observations=args.max_observations,
            w2_root=args.w2_root,
            market_root=args.market_root,
            database_path=args.database,
            dataset_root=args.dataset_root,
            scope_certificate_path=args.scope_certificate,
        )
    except (KeyError, FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        parser.exit(2, f"W4 historical dataset 未完成：{type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
