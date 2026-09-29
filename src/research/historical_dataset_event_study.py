"""W5 v2 研究 API 的只读、manifest 驱动数据查询。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from src.core.schemas.research_v2 import (
    DescriptiveStatistics,
    HistoricalDatasetV2Response,
    HistoricalDatasetVersions,
    HistoricalEventStudyV2Request,
    HistoricalEventStudyV2Response,
    HistoricalEventV2,
    MetricSummary,
)
from src.research.certified_scopes import CertifiedDatasetPin, certified_scope_state
from src.research.historical_dataset import (
    SUPPORTED_W4_SCHEMA_VERSIONS,
    W4_SCHEMA_VERSION,
    _canonical_json,
    _sha256_bytes,
    _sha256_file,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
MAX_EVENT_STUDY_CANDIDATES = 250_000
_MANIFEST_DIGEST_FIELDS = (
    "shard_key", "status", "input_digest", "source_digest", "row_count",
    "features_sha256", "outcomes_sha256", "error_code", "error_type",
)


def _safe_id(value: str, label: str) -> str:
    if not _SAFE_ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{label} 含不安全路径字符")
    return value


def _read_manifest(root: Path, dataset_id: str) -> tuple[dict[str, Any], list[Path], list[Path]]:
    dataset_id = _safe_id(dataset_id, "dataset_id")
    base = Path(root).resolve()
    dataset_root = (base / dataset_id).resolve()
    if not dataset_root.is_relative_to(base):
        raise ValueError("dataset_id 越出配置的数据集目录")
    manifest_path = dataset_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"研究数据集不存在：{dataset_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("dataset_id") != dataset_id
        or manifest.get("schema_version") not in SUPPORTED_W4_SCHEMA_VERSIONS
        or manifest.get("status") not in {"COMPLETE", "PARTIAL"}
    ):
        raise ValueError("数据集 manifest 身份、schema 或状态无效")

    entries = manifest.get("shards")
    if not isinstance(entries, list):
        raise ValueError("数据集 manifest 缺少 shards 数组")
    digest_rows = [
        {key: item.get(key) for key in _MANIFEST_DIGEST_FIELDS}
        for item in sorted(entries, key=lambda item: str(item.get("shard_key", "")))
    ]
    calculated_digest = _sha256_bytes(_canonical_json({
        "schema_version": manifest["schema_version"],
        "dataset_id": dataset_id,
        "metadata": manifest.get("metadata", {}),
        "shards": digest_rows,
        "missing_shards": manifest.get("missing_shards", []),
    }).encode("utf-8"))
    if manifest.get("dataset_digest") != calculated_digest:
        raise ValueError("数据集 manifest digest 不一致")

    features: list[Path] = []
    outcomes: list[Path] = []
    for item in entries:
        if item.get("status") != "COMPLETE":
            continue
        for path_key, hash_key, target in (
            ("features_path", "features_sha256", features),
            ("outcomes_path", "outcomes_sha256", outcomes),
        ):
            relative = Path(str(item.get(path_key) or ""))
            path = (dataset_root / relative).resolve()
            if not path.is_relative_to(dataset_root):
                raise ValueError("manifest 分片路径越出数据集目录")
            if not path.is_file() or _sha256_file(path) != item.get(hash_key):
                raise ValueError(f"manifest 分片缺失或 digest 不一致：{item.get(path_key)}")
            target.append(path)
    return manifest, features, outcomes


def _sql_paths(paths: list[Path]) -> str:
    if not paths:
        raise ValueError("数据集没有已完成分片")
    escaped = [path.as_posix().replace("'", "''") for path in paths]
    return "[" + ",".join(f"'{path}'" for path in escaped) + "]"


def _version_catalog(
    features: list[Path], outcomes: list[Path],
) -> list[HistoricalDatasetVersions]:
    if not features or not outcomes:
        return []
    query = f"""
        SELECT DISTINCT
            f.feature_version, f.pit_version, f.birth_profile_version,
            f.birth_profile_source_version, f.calendar_version,
            f.engine_versions_json, f.rule_versions_json, f.config_version,
            o.label_version, o.bar_version, o.factor_version, o.price_basis
        FROM read_parquet({_sql_paths(features)}) f
        INNER JOIN read_parquet({_sql_paths(outcomes)}) o
          ON f.dataset_id=o.dataset_id
         AND f.security_id=o.security_id
         AND f.research_date=o.research_date
         AND f.feature_version=o.feature_version
         AND f.pit_version=o.pit_version
         AND f.birth_profile_version=o.birth_profile_version
         AND f.birth_profile_source_version=o.birth_profile_source_version
         AND f.calendar_version=o.calendar_version
         AND f.engine_versions_json=o.engine_versions_json
         AND f.rule_versions_json=o.rule_versions_json
         AND f.config_version=o.config_version
        ORDER BY f.feature_version, f.pit_version, f.birth_profile_version,
                 f.birth_profile_source_version, f.calendar_version, f.config_version,
                 o.label_version, o.bar_version, o.factor_version, o.price_basis
    """
    rows = duckdb.connect(database=":memory:").execute(query).fetchall()
    result_by_key: dict[tuple[str, ...], HistoricalDatasetVersions] = {}
    for row in rows:
        version = HistoricalDatasetVersions(
            feature_version=row[0], pit_version=row[1],
            birth_profile_version=row[2], birth_profile_source_version=row[3],
            calendar_version=row[4], engine_versions=json.loads(row[5]),
            rule_versions=json.loads(row[6]), config_version=row[7],
            label_version=row[8], bar_version=row[9], factor_version=row[10],
            price_basis=row[11],
        )
        result_by_key[_version_key(version)] = version
    return list(result_by_key.values())


def _stored_version_json_pairs(
    features: list[Path],
    outcomes: list[Path],
    versions: HistoricalDatasetVersions,
) -> list[tuple[str, str]]:
    """Find raw JSON encodings equal to the requested version objects.

    W4 validates JSON structure but permits insignificant whitespace/key-order
    differences, so SQL string equality against our canonical JSON is too strict.
    """
    query = f"""
        SELECT DISTINCT f.engine_versions_json, f.rule_versions_json
        FROM read_parquet({_sql_paths(features)}) f
        INNER JOIN read_parquet({_sql_paths(outcomes)}) o
          ON f.dataset_id=o.dataset_id
         AND f.security_id=o.security_id
         AND f.research_date=o.research_date
         AND f.feature_version=o.feature_version
         AND f.pit_version=o.pit_version
         AND f.birth_profile_version=o.birth_profile_version
         AND f.birth_profile_source_version=o.birth_profile_source_version
         AND f.calendar_version=o.calendar_version
         AND f.engine_versions_json=o.engine_versions_json
         AND f.rule_versions_json=o.rule_versions_json
         AND f.config_version=o.config_version
        WHERE f.feature_version=? AND f.pit_version=?
          AND f.birth_profile_version=? AND f.birth_profile_source_version=?
          AND f.calendar_version=? AND f.config_version=?
          AND o.label_version=? AND o.bar_version=? AND o.factor_version=?
          AND o.price_basis=?
    """
    parameters = [
        versions.feature_version, versions.pit_version,
        versions.birth_profile_version, versions.birth_profile_source_version,
        versions.calendar_version, versions.config_version,
        versions.label_version, versions.bar_version, versions.factor_version,
        versions.price_basis,
    ]
    rows = duckdb.connect(database=":memory:").execute(query, parameters).fetchall()
    requested_engine = versions.engine_versions
    requested_rules = versions.rule_versions
    pairs = [
        (str(engine_json), str(rule_json))
        for engine_json, rule_json in rows
        if json.loads(engine_json) == requested_engine and json.loads(rule_json) == requested_rules
    ]
    if not pairs:
        raise ValueError("请求版本在当前 dataset 范围内没有对应分片")
    return pairs


def get_historical_dataset_v2(root: Path, dataset_id: str) -> HistoricalDatasetV2Response:
    manifest, feature_paths, outcome_paths = _read_manifest(root, dataset_id)
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("dataset metadata 必须是 JSON 对象")
    certification_status, certification_reason, pin = certified_scope_state(manifest)
    return HistoricalDatasetV2Response(
        dataset_id=manifest["dataset_id"],
        dataset_digest=manifest["dataset_digest"],
        schema_version=manifest["schema_version"],
        status=manifest["status"],
        row_count=int(manifest.get("row_count", 0)),
        expected_shard_count=int(manifest.get("expected_shard_count", 0)),
        complete_shard_count=int(manifest.get("complete_shard_count", 0)),
        failed_shards=list(manifest.get("failed_shards", [])),
        missing_shards=list(manifest.get("missing_shards", [])),
        metadata=metadata,
        available_versions=_version_catalog(feature_paths, outcome_paths),
        research_eligible=bool(metadata.get("research_eligible", False)),
        confirmatory_research_eligible=bool(metadata.get("confirmatory_research_eligible", False)),
        certification_status=certification_status,
        certification_reason=certification_reason,
        certified_stock_code=pin.stock_code if pin else None,
        certified_security_id=pin.security_id if pin else None,
        certified_date_from=pin.date_from if pin else None,
        certified_date_to=pin.date_to if pin else None,
        scope_certificate_id=pin.scope_certificate_id if pin else None,
        scope_certificate_sha256=pin.scope_certificate_sha256 if pin else None,
    )


def _version_key(versions: HistoricalDatasetVersions) -> tuple[str, ...]:
    value = versions.model_dump(mode="json")
    return tuple(
        _canonical_json(value[key]) if isinstance(value[key], dict) else str(value[key])
        for key in (
            "feature_version", "pit_version", "birth_profile_version",
            "birth_profile_source_version", "calendar_version", "engine_versions",
            "rule_versions", "config_version", "label_version", "bar_version",
            "factor_version", "price_basis",
        )
    )


def _stats(
    *, count: int, missing: int, mean: float | None, median: float | None, positive: int,
    mean_positive: float | None = None,
    mean_negative: float | None = None,
    payoff_ratio: float | None = None,
    max_return: float | None = None,
    max_loss: float | None = None,
    metric_summaries: dict[str, MetricSummary] | None = None,
) -> DescriptiveStatistics:
    return DescriptiveStatistics(
        sample_count=count,
        missing_count=missing,
        mean_return=mean,
        median_return=median,
        win_rate=(positive / count) if count else None,
        mean_positive_return=mean_positive,
        mean_negative_return=mean_negative,
        payoff_ratio=payoff_ratio,
        max_return=max_return,
        max_loss=max_loss,
        metric_summaries=metric_summaries or {},
    )


def _empty_statistics() -> DescriptiveStatistics:
    return _stats(count=0, missing=0, mean=None, median=None, positive=0)


def _empty_scope_response(
    manifest: dict[str, Any],
    request: HistoricalEventStudyV2Request,
    *,
    status: str,
    reason: str,
    pin: CertifiedDatasetPin | None,
) -> HistoricalEventStudyV2Response:
    return HistoricalEventStudyV2Response(
        dataset_id=request.dataset_id,
        dataset_digest=str(manifest.get("dataset_digest", "")),
        scope_mode=request.scope_mode,
        date_from=request.date_from,
        date_to=request.date_to,
        target_date=request.target_date,
        factor_ids=request.factor_ids,
        activation=request.activation,
        ten_god_category=request.ten_god_category,
        ten_god_layer=request.ten_god_layer,
        ten_god_position=request.ten_god_position,
        relation_type=request.relation_type,
        relation_source_context=request.relation_source_context,
        relation_source_pillar=request.relation_source_pillar,
        relation_target_context=request.relation_target_context,
        relation_target_pillar=request.relation_target_pillar,
        relation_source_component=request.relation_source_component,
        relation_target_component=request.relation_target_component,
        certified_stock_code=pin.stock_code if pin else None,
        certified_date_from=pin.date_from if pin else None,
        certified_date_to=pin.date_to if pin else None,
        horizon=request.horizon,
        versions=request.versions,
        research_status=status,
        research_status_reasons=[reason],
        candidate_observation_count=0,
        matched_observation_count=0,
        candidate_security_date_count=0,
        matched_security_date_count=0,
        matched_date_count=0,
        missing_observation_count=0,
        missing_by_reason={},
        matched=_empty_statistics(),
        complement=_empty_statistics(),
        overall=_empty_statistics(),
        matched_date_equal_weighted=_empty_statistics(),
        returned_count=0,
        limit=request.limit,
        offset=request.offset,
        events=[],
        warnings=[reason, "未执行统计；没有对请求范围进行裁剪。"],
    )


def _finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _optional_int(value: Any) -> int | None:
    parsed = _finite_float(value)
    return int(parsed) if parsed is not None else None


def run_historical_event_study_v2(
    root: Path,
    request: HistoricalEventStudyV2Request,
    *,
    minimum_sample: int = 8,
) -> HistoricalEventStudyV2Response:
    manifest, feature_paths, outcome_paths = _read_manifest(root, request.dataset_id)
    certification_status, certification_reason, pin = certified_scope_state(manifest)
    if certification_status != "CERTIFIED_LIMITED_SCOPE":
        status = certification_status if certification_status != "DATA_MISSING" else "DATA_MISSING"
        return _empty_scope_response(
            manifest, request, status=status, reason=certification_reason, pin=pin,
        )
    assert pin is not None

    if request.scope_mode == "stock" and request.stock_code != pin.stock_code:
        return _empty_scope_response(
            manifest, request, status="SECURITY_NOT_CERTIFIED",
            reason=f"本数据集仅认证证券 {pin.stock_code}（{pin.security_id}）；{request.stock_code} 未获认证。",
            pin=pin,
        )
    if request.date_from < pin.date_from or request.date_to > pin.date_to:
        return _empty_scope_response(
            manifest, request, status="OUTSIDE_CERTIFIED_SCOPE",
            reason=(
                f"请求范围 {request.date_from} 至 {request.date_to} 超出证书范围 "
                f"{pin.date_from} 至 {pin.date_to}；未裁剪请求或计算子集统计。"
            ),
            pin=pin,
        )
    catalog = _version_catalog(feature_paths, outcome_paths)
    if (
        not feature_paths or not outcome_paths
        or request.versions.pit_version != pin.pit_version
        or request.versions.birth_profile_source_version != pin.birth_profile_source_version
        or request.versions.label_version != pin.label_version
        or _version_key(request.versions) not in {_version_key(item) for item in catalog}
    ):
        return _empty_scope_response(
            manifest, request, status="VERSION_MISMATCH",
            reason="请求版本与证书绑定的数据集版本目录不一致。",
            pin=pin,
        )

    versions = request.versions
    scope_dates = manifest["metadata"]["scope"]["research_dates"]
    expected_dates = [
        date.fromisoformat(value) for value in scope_dates
        if request.date_from <= date.fromisoformat(value) <= request.date_to
    ]
    if not expected_dates:
        return _empty_scope_response(
            manifest, request, status="DATA_MISSING",
            reason="所选日期范围内没有认证观察日期；没有将空覆盖解释为无事件。",
            pin=pin,
        )
    version_json_pairs = _stored_version_json_pairs(feature_paths, outcome_paths, versions)
    json_version_filter = " OR ".join(
        "(f.engine_versions_json = ? AND f.rule_versions_json = ?)"
        for _ in version_json_pairs
    )
    horizon = request.horizon
    label_column = f"ret_{horizon}d"
    available_column = f"horizon_available_{horizon}d"
    path_metric_columns = []
    for metric in ("max_favorable_move", "max_adverse_move", "max_drawdown"):
        column = f"{metric}_{horizon}d"
        if manifest["schema_version"] == W4_SCHEMA_VERSION or horizon == 20:
            path_metric_columns.append(f"o.{column} AS {column}")
        else:
            # W4 v1只存了20日路径统计；历史数据保持可读，但不可用周期不补值。
            path_metric_columns.append(f"NULL AS {column}")

    parameters: list[Any] = [
        *request.factor_ids,
        request.date_from,
        request.date_to,
        versions.feature_version,
        versions.pit_version,
        versions.birth_profile_version,
        versions.birth_profile_source_version,
        versions.calendar_version,
        *(value for pair in version_json_pairs for value in pair),
        versions.config_version,
        versions.label_version,
        versions.bar_version,
        versions.factor_version,
        versions.price_basis,
    ]
    if request.scope_mode == "stock":
        parameters.append(request.stock_code)

    relation_required = request.relation_type is not None
    if relation_required:
        parameters.extend([
            request.relation_type,
            request.relation_source_context,
            request.relation_source_pillar,
            request.relation_target_context,
            request.relation_target_pillar,
            request.relation_source_component,
            request.relation_target_component,
        ])
        relation_json = """(
            SELECT j.value
            FROM json_each(s.features_json, '$.fortune_snapshot.relation_context.events') j
            WHERE json_extract_string(j.value, '$.relation_type') = ?
              AND json_extract_string(j.value, '$.source.context') = ?
              AND json_extract_string(j.value, '$.source.pillar') = ?
              AND json_extract_string(j.value, '$.target.context') = ?
              AND json_extract_string(j.value, '$.target.pillar') = ?
              AND json_extract_string(j.value, '$.source.component') = ?
              AND json_extract_string(j.value, '$.target.component') = ?
            LIMIT 1
        )"""
        relation_match = "relation_json IS NOT NULL"
    else:
        relation_json = "NULL::JSON"
        relation_match = "TRUE"
    if request.direction_filter is not None:
        parameters.append(request.direction_filter)
    if request.min_rule_score is not None:
        parameters.append(request.min_rule_score)
    if request.ten_god_category is not None:
        parameters.append(request.ten_god_category)

    activation_filter = {
        "any": "TRUE",
        "nonzero": "normalized_value IS NOT NULL AND normalized_value <> 0",
        "positive": "normalized_value IS NOT NULL AND normalized_value > 0",
        "negative": "normalized_value IS NOT NULL AND normalized_value < 0",
    }[request.activation]
    ten_god_filter = ""
    if request.ten_god_category is not None:
        ten_god_filter = "AND raw_value = ?"
    relation_missing = "OR NOT relation_data_present" if relation_required else ""
    category_missing = "OR raw_value IS NULL" if request.ten_god_category is not None else ""
    query = f"""
        WITH requested_factors AS (
            SELECT * FROM (VALUES {','.join('( ? )' for _ in request.factor_ids)}) AS v(factor_id)
        ),
        scoped AS (
            SELECT f.dataset_id, f.security_id, f.stock_code,
                   CAST(f.research_date AS DATE) AS research_date,
                   f.features_json,
                   o.{label_column} AS return_value,
                   o.bench_ret_{horizon}d AS benchmark_return,
                   o.excess_return_{horizon}d AS excess_return,
                   {', '.join(path_metric_columns)},
                   COALESCE(o.{available_column}, FALSE) AS horizon_available,
                   COALESCE(o.is_degraded, TRUE) AS is_degraded
            FROM read_parquet({_sql_paths(feature_paths)}) f
            INNER JOIN read_parquet({_sql_paths(outcome_paths)}) o
              ON f.dataset_id=o.dataset_id
             AND f.security_id=o.security_id
             AND f.research_date=o.research_date
             AND f.feature_version=o.feature_version
             AND f.pit_version=o.pit_version
             AND f.birth_profile_version=o.birth_profile_version
             AND f.birth_profile_source_version=o.birth_profile_source_version
             AND f.calendar_version=o.calendar_version
             AND f.engine_versions_json=o.engine_versions_json
             AND f.rule_versions_json=o.rule_versions_json
             AND f.config_version=o.config_version
            WHERE CAST(f.research_date AS DATE) BETWEEN ? AND ?
              AND f.feature_version = ? AND f.pit_version = ?
              AND f.birth_profile_version = ? AND f.birth_profile_source_version = ?
              AND f.calendar_version = ?
              AND ({json_version_filter})
              AND f.config_version = ?
              AND o.label_version = ? AND o.bar_version = ? AND o.factor_version = ?
              AND o.price_basis = ?
              {('AND f.stock_code = ?' if request.scope_mode == 'stock' else '')}
        ),
        selected AS (
            SELECT s.*, rf.factor_id,
                   feature.value AS feature_json,
                   json_extract_string(feature.value, '$.availability') AS feature_availability,
                   TRY_CAST(json_extract_string(feature.value, '$.direction') AS INTEGER) AS direction,
                   TRY_CAST(json_extract_string(feature.value, '$.rule_score') AS DOUBLE) AS rule_score,
                   TRY_CAST(json_extract_string(feature.value, '$.normalized_value') AS DOUBLE) AS normalized_value,
                   json_extract_string(feature.value, '$.raw_value') AS raw_value,
                   json_type(s.features_json, '$.fortune_snapshot.relation_context.events') = 'ARRAY'
                       AS relation_data_present,
                   {relation_json} AS relation_json
            FROM scoped s
            CROSS JOIN requested_factors rf
            LEFT JOIN LATERAL (
                SELECT j.value
                FROM json_each(s.features_json, '$.factor_set.observations') j
                WHERE json_extract_string(j.value, '$.factor_id') = rf.factor_id
            ) feature ON TRUE
        ),
        classified AS (
            SELECT *,
                COALESCE(feature_availability = 'ok', FALSE) AS feature_valid,
                COALESCE(feature_availability = 'ok', FALSE)
                  AND ({activation_filter})
                  {('AND direction = ?' if request.direction_filter is not None else '')}
                  {('AND rule_score >= ?' if request.min_rule_score is not None else '')}
                  AND ({relation_match})
                  {ten_god_filter}
                  AS matched,
                CASE
                    WHEN feature_json IS NULL THEN 'factor_missing'
                    WHEN COALESCE(feature_availability, '') <> 'ok' THEN 'feature_unavailable'
                    WHEN is_degraded THEN 'degraded_data'
                    WHEN ({'TRUE' if relation_required or request.ten_god_category is not None else 'FALSE'})
                         AND (FALSE {relation_missing} {category_missing})
                         THEN 'condition_data_missing'
                    WHEN NOT horizon_available OR return_value IS NULL THEN 'horizon_unavailable'
                    ELSE NULL
                END AS missing_reason
            FROM selected
        )
        SELECT security_id, stock_code, research_date, factor_id, direction, rule_score,
               normalized_value, raw_value, relation_json, return_value, benchmark_return,
               excess_return, max_favorable_move_{horizon}d, max_adverse_move_{horizon}d,
               max_drawdown_{horizon}d, horizon_available, is_degraded, feature_valid,
               matched, missing_reason
        FROM classified
        ORDER BY stock_code, research_date, factor_id
    """
    connection = duckdb.connect(database=":memory:")
    try:
        candidate_count = connection.execute(
            f"SELECT COUNT(*) FROM ({query}) AS candidate_rows", parameters,
        ).fetchone()[0]
        if candidate_count > MAX_EVENT_STUDY_CANDIDATES:
            raise ValueError(
                "本次历史事件候选观察超过单次查询上限；请缩小日期、证券或因子范围 "
                f"({candidate_count} > {MAX_EVENT_STUDY_CANDIDATES})"
            )
        frame = connection.execute(query, parameters).df()
    finally:
        connection.close()

    rows = frame.to_dict(orient="records")
    if len(rows) != candidate_count:
        raise ValueError("历史事件查询行数在计数与读取之间发生变化")
    unique_security_dates = {
        (str(row["security_id"]), row["research_date"]) for row in rows
    }
    if candidate_count != len(unique_security_dates) * len(request.factor_ids):
        raise ValueError("W4 分片中证券/日期/因子存在重复或缺少预期观察")

    missing_by_reason = Counter(
        str(row["missing_reason"]) for row in rows if row["missing_reason"] is not None
    )
    matched_rows = [row for row in rows if bool(row["matched"])]
    valid_rows = [row for row in rows if bool(row["feature_valid"])]
    complement_rows = [row for row in valid_rows if not bool(row["matched"])]
    overall_rows = valid_rows

    def returns_for(items: list[dict[str, Any]]) -> list[float]:
        return [
            value
            for item in items
            if (value := _finite_float(item["return_value"])) is not None
            and not bool(item["is_degraded"])
            and bool(item["horizon_available"])
        ]

    metric_definitions = {
        "benchmark_return": "同一持有期起止日期的沪深300不复权收盘收益。",
        "excess_return": "同一持有期个股收益减同区间基准收益；任一端点缺失则不可用。",
        "max_favorable_move": "事件日收盘后至第N根个股日线最高价相对事件日调整收盘价的最大变动。",
        "max_adverse_move": "事件日收盘后至第N根个股日线最低价相对事件日调整收盘价的最大变动。",
        "max_drawdown": "事件日调整收盘价及其后N根调整收盘价路径中，峰值至后续谷值的最大非负跌幅。",
    }

    def group_stats(items: list[dict[str, Any]]) -> DescriptiveStatistics:
        values = returns_for(items)
        values_sorted = sorted(values)
        count = len(values_sorted)
        if count:
            mid = count // 2
            median = values_sorted[mid] if count % 2 else (values_sorted[mid - 1] + values_sorted[mid]) / 2
            mean = sum(values_sorted) / count
            positive_values = [value for value in values_sorted if value > 0]
            negative_values = [value for value in values_sorted if value < 0]
            positive_count = len(positive_values)
            mean_positive = sum(positive_values) / positive_count if positive_count else None
            mean_negative = sum(negative_values) / len(negative_values) if negative_values else None
            payoff = mean_positive / abs(mean_negative) if mean_positive is not None and mean_negative else None
            maximum_return = max(values_sorted)
            maximum_loss = min(negative_values) if negative_values else None
        else:
            median = mean = mean_positive = mean_negative = payoff = maximum_return = maximum_loss = None
            positive_count = 0
        eligible = sum(bool(item["feature_valid"]) for item in items)

        metric_summaries: dict[str, MetricSummary] = {}
        for field, definition in metric_definitions.items():
            data_field = (
                f"{field}_{horizon}d"
                if field in {"max_favorable_move", "max_adverse_move", "max_drawdown"}
                else field
            )
            metric_values = [
                value for item in items
                if not bool(item["is_degraded"])
                and bool(item["horizon_available"])
                and (value := _finite_float(item.get(data_field))) is not None
            ]
            metric_summaries[field] = MetricSummary(
                sample_count=len(metric_values),
                missing_count=max(0, eligible - len(metric_values)),
                mean=sum(metric_values) / len(metric_values) if metric_values else None,
                minimum=min(metric_values) if metric_values else None,
                maximum=max(metric_values) if metric_values else None,
                definition=definition,
            )
        return _stats(
            count=count,
            missing=max(0, eligible - count),
            mean=mean,
            median=median,
            positive=positive_count,
            mean_positive=mean_positive,
            mean_negative=mean_negative,
            payoff_ratio=payoff,
            max_return=maximum_return,
            max_loss=maximum_loss,
            metric_summaries=metric_summaries,
        )

    date_returns: dict[date, list[float]] = defaultdict(list)
    for row in matched_rows:
        values = returns_for([row])
        if values:
            date_returns[row["research_date"]].extend(values)
    date_means = sorted(sum(values) / len(values) for values in date_returns.values())
    date_count = len(date_means)
    if date_count:
        mid = date_count // 2
        date_median = date_means[mid] if date_count % 2 else (date_means[mid - 1] + date_means[mid]) / 2
        date_mean = sum(date_means) / date_count
        date_positive = sum(value > 0 for value in date_means)
    else:
        date_median = date_mean = None
        date_positive = 0
    matched_dates = {row["research_date"] for row in matched_rows}
    date_weighted = _stats(
        count=date_count,
        missing=max(0, len(matched_dates) - date_count),
        mean=date_mean,
        median=date_median,
        positive=date_positive,
    )

    page = matched_rows[request.offset:request.offset + request.limit]
    events: list[HistoricalEventV2] = []
    for row in page:
        reason = row["missing_reason"]
        if reason is None and not bool(row["horizon_available"]):
            reason = "horizon_unavailable"
        if bool(row["is_degraded"]):
            reason = "degraded_data"
        relation_evidence = row.get("relation_json")
        if isinstance(relation_evidence, str):
            relation_evidence = json.loads(relation_evidence)
        raw_value = row.get("raw_value")
        events.append(HistoricalEventV2(
            security_id=str(row["security_id"]),
            stock_code=str(row["stock_code"]),
            research_date=row["research_date"],
            factor_id=str(row["factor_id"]),
            direction=_optional_int(row["direction"]),
            rule_score=_finite_float(row["rule_score"]),
            normalized_value=_finite_float(row["normalized_value"]),
            ten_god_category=(str(raw_value) if str(row["factor_id"]) == "B_DAY_005" and raw_value is not None else None),
            relation_evidence=relation_evidence,
            horizon=horizon,
            return_value=(
                None if bool(row["is_degraded"]) or not bool(row["horizon_available"])
                else _finite_float(row["return_value"])
            ),
            benchmark_return=(
                None if bool(row["is_degraded"]) or not bool(row["horizon_available"])
                else _finite_float(row["benchmark_return"])
            ),
            excess_return=(
                None if bool(row["is_degraded"]) or not bool(row["horizon_available"])
                else _finite_float(row["excess_return"])
            ),
            max_favorable_move=_finite_float(row.get("max_favorable_move_" + str(horizon) + "d")),
            max_adverse_move=_finite_float(row.get("max_adverse_move_" + str(horizon) + "d")),
            max_drawdown=_finite_float(row.get("max_drawdown_" + str(horizon) + "d")),
            label_available=bool(row["horizon_available"]) and not bool(row["is_degraded"]),
            missing_reason=reason,
        ))

    degraded_rows = any(bool(row["is_degraded"]) for row in rows)
    expected_candidate_count = len(expected_dates) * len(request.factor_ids)
    coverage_missing = candidate_count != expected_candidate_count or len(unique_security_dates) != len(expected_dates)
    data_missing_reasons = {
        "factor_missing", "feature_unavailable", "condition_data_missing", "horizon_unavailable",
    }
    has_missing_data = coverage_missing or any(missing_by_reason[key] for key in data_missing_reasons)
    matched_returns = returns_for(matched_rows)
    if degraded_rows:
        status = "NO_REAL_DATA"
        reasons = ["所选范围包含 synthetic/degraded 行情；不输出其收益统计。"]
    elif has_missing_data:
        status = "DATA_MISSING"
        reasons = [
            f"认证范围预期 {expected_candidate_count} 条证券-日期-因子观察，实际读取 {candidate_count} 条；"
            "缺失标签或条件输入保留为不可用。"
        ]
    elif not matched_rows:
        status = "NO_MATCHING_EVENTS"
        reasons = ["认证范围内没有符合所选因子、激活条件和结构条件的事件。"]
    elif not matched_returns:
        status = "DATA_MISSING"
        reasons = ["命中事件存在，但所选周期没有可用收益标签；收益保持 null。"]
    elif len(matched_returns) < minimum_sample:
        status = "INSUFFICIENT_SAMPLE"
        reasons = [f"可用匹配标签少于最低描述样本数 {minimum_sample}。"]
    else:
        status = "EXPLORATORY_NOT_GATED"
        reasons = ["此接口仅计算描述统计；确认性检验与负对照由预注册实验工作包执行。"]
        limitations = manifest.get("metadata", {}).get("known_limitations", [])
        if isinstance(limitations, list):
            reasons.extend(
                f"数据集限制：{limitation}"
                for limitation in limitations
                if isinstance(limitation, str) and limitation.strip()
            )

    candidate_security_dates = unique_security_dates
    matched_security_dates = {
        (str(row["security_id"]), row["research_date"]) for row in matched_rows
    }
    return HistoricalEventStudyV2Response(
        dataset_id=request.dataset_id,
        dataset_digest=manifest["dataset_digest"],
        scope_mode=request.scope_mode,
        date_from=request.date_from,
        date_to=request.date_to,
        target_date=request.target_date,
        factor_ids=request.factor_ids,
        activation=request.activation,
        ten_god_category=request.ten_god_category,
        ten_god_layer=request.ten_god_layer,
        ten_god_position=request.ten_god_position,
        relation_type=request.relation_type,
        relation_source_context=request.relation_source_context,
        relation_source_pillar=request.relation_source_pillar,
        relation_target_context=request.relation_target_context,
        relation_target_pillar=request.relation_target_pillar,
        relation_source_component=request.relation_source_component,
        relation_target_component=request.relation_target_component,
        condition_logic="AND",
        factor_selection_semantics="per_factor_observation",
        certified_stock_code=pin.stock_code,
        certified_date_from=pin.date_from,
        certified_date_to=pin.date_to,
        horizon=horizon,
        versions=versions,
        research_status=status,
        research_status_reasons=reasons,
        candidate_observation_count=candidate_count,
        matched_observation_count=len(matched_rows),
        candidate_security_date_count=len(candidate_security_dates),
        matched_security_date_count=len(matched_security_dates),
        matched_date_count=len(matched_dates),
        missing_observation_count=sum(missing_by_reason.values()),
        missing_by_reason=dict(sorted(missing_by_reason.items())),
        matched=group_stats(matched_rows),
        complement=group_stats(complement_rows),
        overall=group_stats(overall_rows),
        matched_date_equal_weighted=date_weighted,
        returned_count=len(events),
        limit=request.limit,
        offset=request.offset,
        events=events,
        warnings=[
            "统计单位为证券-日期-因子观察；候选股票日期数与因子观察数分别报告。",
            "研究条件之间使用 AND；不同 factor_id 按独立因子观察统计，不合并为日期去重数。",
            "收益按比例存储，例如 0.05 表示 5%；样本收益极值、路径变动和回撤分别统计。",
            "描述统计不代表预期收益率、上涨概率或交易建议。",
        ],
    )

def read_experiment_report(root: Path, experiment_id: str) -> tuple[dict[str, Any], str]:
    experiment_id = _safe_id(experiment_id, "experiment_id")
    base = (Path(root).resolve() / "research_experiments").resolve()
    path = (base / f"{experiment_id}.json").resolve()
    if not path.is_relative_to(base):
        raise ValueError("experiment_id 越出实验报告目录")
    if not path.is_file():
        raise FileNotFoundError(f"版本化实验报告不存在：{experiment_id}")
    payload = path.read_bytes()
    report = json.loads(payload.decode("utf-8"))
    report_identity = report.get("report_id", report.get("experiment_id")) if isinstance(report, dict) else None
    if not isinstance(report, dict) or report_identity != experiment_id:
        raise ValueError("实验报告身份与请求 ID 不一致")
    if report.get("schema_version") != "w6-research-experiment-v1":
        raise ValueError("实验报告 schema_version 无效")
    return report, hashlib.sha256(payload).hexdigest()


__all__ = [
    "get_historical_dataset_v2",
    "read_experiment_report",
    "run_historical_event_study_v2",
]
