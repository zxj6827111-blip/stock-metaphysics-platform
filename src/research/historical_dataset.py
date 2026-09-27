"""W4 版本化历史研究数据集：特征/结果分离、严格联结与幂等分片存储。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

W4_SCHEMA_VERSION = "w4-historical-panel-v1"
FEATURE_KEY = ("security_id", "research_date")
FEATURE_VERSION_FIELDS = (
    "feature_version",
    "pit_version",
    "birth_profile_version",
    "birth_profile_source_version",
    "calendar_version",
    "engine_versions_json",
    "rule_versions_json",
    "config_version",
)
LABEL_VERSION_FIELDS = (
    "label_version",
    "bar_version",
    "factor_version",
    "price_basis",
)
FEATURE_REQUIRED = {
    "dataset_id", "security_id", "stock_code", "research_date", "research_time",
    "research_timezone",
    *FEATURE_VERSION_FIELDS, "pit_manifest_sha256", "pit_calendar_digest",
    "birth_profile_source", "birth_profile_recorded_at", "birth_evidence_asof_status",
    "chart_artifact_ids_json", "chart_artifact_digests_json", "features_json",
    "research_use_status", "research_eligible",
}
OUTCOME_REQUIRED = {
    "dataset_id", "security_id", "stock_code", "research_date", "research_time",
    "research_timezone", *FEATURE_VERSION_FIELDS, *LABEL_VERSION_FIELDS,
    "bar_manifest_sha256", "factor_manifest_sha256", "trade_date", "trade_index",
    "benchmark_code", "is_degraded", "max_favorable_move_20d",
    "max_adverse_move_20d", "max_drawdown_20d",
    *{
        f"{prefix}_{horizon}d"
        for prefix in (
            "ret", "bench_ret", "excess_return", "horizon_available",
            "horizon_requested",
        )
        for horizon in (1, 5, 10, 20, 60)
    },
}
_DIGEST_FIELDS = (
    "pit_manifest_sha256", "pit_calendar_digest",
    "bar_manifest_sha256", "factor_manifest_sha256",
)
_FEATURE_NONEMPTY_FIELDS = (
    "dataset_id", "security_id", "stock_code", "research_timezone",
    *FEATURE_VERSION_FIELDS, "birth_profile_source", "birth_profile_recorded_at",
    "birth_evidence_asof_status", "research_use_status",
)
_OUTCOME_NONEMPTY_FIELDS = (
    "dataset_id", "security_id", "stock_code", "research_timezone",
    *FEATURE_VERSION_FIELDS, *LABEL_VERSION_FIELDS,
)
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _safe_component(value: str, label: str) -> str:
    text = str(value).strip()
    if not _SAFE_COMPONENT.fullmatch(text) or text in {".", ".."}:
        raise ValueError(f"{label} 含不安全路径字符")
    return text


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical_json(value))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _as_date_text(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"研究日期不可解析：{value!r}")
    return parsed.date().isoformat()


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} 缺少必需字段：{sorted(missing)}")
    if frame.empty:
        raise ValueError(f"{label} 不得为空")


def _check_unique_key(frame: pd.DataFrame, label: str) -> None:
    if frame["security_id"].astype(str).str.strip().eq("").any():
        raise ValueError(f"{label} 的 security_id 不得为空")
    if frame[list(FEATURE_KEY)].isna().any().any():
        raise ValueError(f"{label} 的 security_id/research_date 不得为空")
    if frame.duplicated(list(FEATURE_KEY), keep=False).any():
        raise ValueError(f"{label} 存在重复 security_id + research_date 键")


def validate_feature_outcome_frames(
    features: pd.DataFrame,
    outcomes: pd.DataFrame,
    *,
    expected_versions: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """按证券身份、研究日与特征版本做一对一联结；任何缺行/重复/跨版本都失败。"""
    _require_columns(features, FEATURE_REQUIRED, "features")
    _require_columns(outcomes, OUTCOME_REQUIRED, "outcomes")
    feature_frame = features.copy()
    outcome_frame = outcomes.copy()
    for frame, nonempty_fields in (
        (feature_frame, _FEATURE_NONEMPTY_FIELDS),
        (outcome_frame, _OUTCOME_NONEMPTY_FIELDS),
    ):
        raw_security_ids = frame["security_id"]
        missing_security_ids = raw_security_ids.isna() | raw_security_ids.astype(str).str.strip().str.lower().isin(
            {"", "none", "nan", "<na>"}
        )
        if missing_security_ids.any():
            raise ValueError("security_id 不得为空")
        frame["security_id"] = frame["security_id"].astype(str).str.strip()
        frame["research_date"] = frame["research_date"].map(_as_date_text)
        frame["research_time"] = frame["research_time"].astype(str)
        for field in nonempty_fields:
            if frame[field].isna().any() or frame[field].astype(str).str.strip().str.lower().isin(
                {"", "none", "nan", "<na>"}
            ).any():
                raise ValueError(f"{field} 不得为空")
    _check_unique_key(feature_frame, "features")
    _check_unique_key(outcome_frame, "outcomes")

    if not feature_frame["research_time"].eq("15:00:00").all():
        raise ValueError("W4 历史日频特征必须使用 15:00:00 Asia/Shanghai")
    if not outcome_frame["research_time"].eq("15:00:00").all():
        raise ValueError("W4 历史日频结果必须使用 15:00:00 Asia/Shanghai")
    if not feature_frame["research_timezone"].eq("Asia/Shanghai").all() or not outcome_frame[
        "research_timezone"
    ].eq("Asia/Shanghai").all():
        raise ValueError("W4 历史日频数据必须标记 Asia/Shanghai")
    for frame, label in ((feature_frame, "features"), (outcome_frame, "outcomes")):
        for field in _DIGEST_FIELDS:
            if field not in frame.columns:
                continue
            if not frame[field].astype(str).str.fullmatch(r"[a-f0-9]{64}").all():
                raise ValueError(f"{label} 的 {field} 必须为 SHA-256")
    for field in (
        "engine_versions_json", "rule_versions_json", "chart_artifact_ids_json",
        "chart_artifact_digests_json", "features_json",
    ):
        try:
            parsed = feature_frame[field].map(json.loads)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"features 的 {field} 必须是有效 JSON") from exc
        if field == "chart_artifact_ids_json" and not parsed.map(
            lambda value: isinstance(value, list) and bool(value) and all(
                isinstance(item, str) and item.strip() for item in value
            )
        ).all():
            raise ValueError("features.chart_artifact_ids_json 必须是非空 artifact ID 数组")
        if field == "chart_artifact_digests_json" and not parsed.map(
            lambda value: isinstance(value, dict) and bool(value) and all(
                isinstance(key, str) and key.strip()
                and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest)
                for key, digest in value.items()
            )
        ).all():
            raise ValueError("features.chart_artifact_digests_json 必须为 artifact ID 到 SHA-256 映射")
        if field in {"engine_versions_json", "rule_versions_json", "features_json"} and not parsed.map(
            lambda value: isinstance(value, dict)
        ).all():
            raise ValueError(f"features 的 {field} 必须为 JSON 对象")
    for artifact_ids, artifact_digests in zip(
        feature_frame["chart_artifact_ids_json"].map(json.loads),
        feature_frame["chart_artifact_digests_json"].map(json.loads),
        strict=True,
    ):
        if set(artifact_ids) != set(artifact_digests):
            raise ValueError("chart artifact 引用与 checksum 清单必须完全对应")
    if not feature_frame["research_eligible"].isin([True, False]).all():
        raise ValueError("research_eligible 必须为布尔值")

    expected = dict(expected_versions or {})
    for field, value in expected.items():
        if field in feature_frame.columns and not feature_frame[field].astype(str).eq(str(value)).all():
            raise ValueError(f"features 的 {field} 与请求版本不一致")
        if field in outcome_frame.columns and not outcome_frame[field].astype(str).eq(str(value)).all():
            raise ValueError(f"outcomes 的 {field} 与请求版本不一致")

    feature_keys = set(map(tuple, feature_frame[list(FEATURE_KEY)].itertuples(index=False, name=None)))
    outcome_keys = set(map(tuple, outcome_frame[list(FEATURE_KEY)].itertuples(index=False, name=None)))
    if feature_keys != outcome_keys:
        missing_outcomes = sorted(feature_keys - outcome_keys)[:3]
        extra_outcomes = sorted(outcome_keys - feature_keys)[:3]
        raise ValueError(
            "features/outcomes 的身份日期范围不完全相同；"
            f"缺结果={missing_outcomes}，缺特征={extra_outcomes}"
        )

    shared_versions = (
        "dataset_id", "stock_code", "research_time", "research_timezone", *FEATURE_VERSION_FIELDS,
    )
    check = feature_frame[[*FEATURE_KEY, *shared_versions]].merge(
        outcome_frame[[*FEATURE_KEY, *shared_versions]],
        on=list(FEATURE_KEY), how="inner", suffixes=("_feature", "_outcome"),
        validate="one_to_one",
    )
    for field in shared_versions:
        if not check[f"{field}_feature"].astype(str).equals(
            check[f"{field}_outcome"].astype(str)
        ):
            raise ValueError(f"features/outcomes 的 {field} 版本或身份不一致")

    for label_field in LABEL_VERSION_FIELDS:
        values = outcome_frame[label_field].astype(str).str.strip()
        if values.eq("").any() or values.eq("None").any():
            raise ValueError(f"outcomes 缺少 {label_field} 版本")
    if not outcome_frame["price_basis"].eq("raw_times_factor").all():
        raise ValueError("W4 新研究结果必须使用 raw_times_factor")
    if not outcome_frame.apply(
        lambda row: _as_date_text(row["trade_date"]) == row["research_date"], axis=1,
    ).all():
        raise ValueError("W4 结果 trade_date 必须与已核验研究日一致")

    merged = feature_frame.merge(
        outcome_frame.drop(columns=[field for field in shared_versions if field not in FEATURE_KEY]),
        on=list(FEATURE_KEY), how="inner", suffixes=("", "_outcome"), validate="one_to_one",
    )
    return merged.sort_values(["security_id", "research_date"], kind="stable").reset_index(drop=True)


class HistoricalResearchDatasetStore:
    """单写者、按 security_id/year 原子发布的 Parquet 分片存储。"""

    def __init__(
        self,
        root: Path,
        *,
        dataset_id: str,
        metadata: Mapping[str, Any],
    ) -> None:
        self.dataset_id = _safe_component(dataset_id, "dataset_id")
        self.root = Path(root).resolve() / self.dataset_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata = json.loads(_canonical_json(dict(metadata)))
        existing_manifest = self.root / "manifest.json"
        if existing_manifest.exists():
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
            if existing.get("dataset_id") != self.dataset_id:
                raise ValueError("输出目录中的 manifest dataset_id 不一致")
            if existing.get("schema_version") != W4_SCHEMA_VERSION:
                raise ValueError("输出目录使用了不同 schema；请新建 dataset_id")
            if existing.get("metadata") != self.metadata:
                raise ValueError("数据集 metadata 已变化；请创建新 dataset_id")
        self.state_path = self.root / "progress.json"
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if self.state.get("dataset_id") != self.dataset_id:
                raise ValueError("续跑账本 dataset_id 不一致")
            if self.state.get("metadata") != self.metadata:
                raise ValueError("续跑账本 metadata 已变化；请创建新 dataset_id")
        else:
            self.state = {
                "dataset_id": self.dataset_id,
                "metadata": self.metadata,
                "shards": {},
            }

    @staticmethod
    def _rows_digest(rows: Sequence[Mapping[str, Any]]) -> str:
        normalized = sorted(
            (dict(row) for row in rows),
            key=lambda row: (str(row.get("security_id")), str(row.get("research_date"))),
        )
        return _sha256_bytes(_canonical_json(normalized).encode("utf-8"))

    def write_shard(
        self,
        features: Sequence[Mapping[str, Any]],
        outcomes: Sequence[Mapping[str, Any]],
        *,
        source_digest: str,
    ) -> dict[str, Any]:
        feature_frame = pd.DataFrame([dict(row) for row in features])
        outcome_frame = pd.DataFrame([dict(row) for row in outcomes])
        expected_versions = {
            field: str(feature_frame[field].iloc[0])
            for field in ("dataset_id", *FEATURE_VERSION_FIELDS)
        }
        validate_feature_outcome_frames(
            feature_frame, outcome_frame, expected_versions=expected_versions,
        )
        if not feature_frame["dataset_id"].astype(str).eq(self.dataset_id).all():
            raise ValueError("分片 dataset_id 与 store 不一致")

        identities = set(feature_frame["security_id"].astype(str))
        years = {int(day[:4]) for day in feature_frame["research_date"].map(_as_date_text)}
        if len(identities) != 1 or len(years) != 1:
            raise ValueError("每个分片必须只包含一个 security_id 和一个自然年")
        security_id = _safe_component(next(iter(identities)), "security_id")
        year = next(iter(years))
        shard_key = f"{security_id}/{year}"
        source_digest = str(source_digest).strip()
        if not re.fullmatch(r"[a-f0-9]{64}", source_digest):
            raise ValueError("source_digest 必须为 SHA-256")
        input_digest = _sha256_bytes(_canonical_json({
            "schema_version": W4_SCHEMA_VERSION,
            "source_digest": source_digest,
            "feature_rows_digest": self._rows_digest(features),
            "outcome_rows_digest": self._rows_digest(outcomes),
        }).encode("utf-8"))

        previous = self.state["shards"].get(shard_key)
        if previous and previous.get("status") == "COMPLETE":
            if previous.get("input_digest") != input_digest:
                raise RuntimeError("已完成分片输入发生变化；请创建新 dataset_id，不覆盖历史产物")
            for field in ("features_path", "outcomes_path"):
                output = self.root / previous[field]
                if not output.is_file() or _sha256_file(output) != previous[field.replace("_path", "_sha256")]:
                    raise RuntimeError(f"已完成分片文件缺失或 digest 不符：{output}")
            return {**previous, "resumed": True}

        shard_tag = input_digest[:20]
        feature_rel = Path("features") / f"security_id={security_id}" / f"year={year}" / f"part-{shard_tag}.parquet"
        outcome_rel = Path("outcomes") / f"security_id={security_id}" / f"year={year}" / f"part-{shard_tag}.parquet"
        feature_path = self.root / feature_rel
        outcome_path = self.root / outcome_rel
        feature_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        feature_frame = feature_frame.sort_values(["security_id", "research_date"], kind="stable")
        outcome_frame = outcome_frame.sort_values(["security_id", "research_date"], kind="stable")
        temp_paths: list[Path] = []
        try:
            for frame, final_path in ((feature_frame, feature_path), (outcome_frame, outcome_path)):
                fd, temp_name = tempfile.mkstemp(
                    prefix=f".{final_path.stem}.", suffix=".tmp.parquet", dir=final_path.parent,
                )
                os.close(fd)
                temporary = Path(temp_name)
                temp_paths.append(temporary)
                frame.to_parquet(temporary, index=False, compression="zstd", version="2.6")
            hashes = [_sha256_file(path) for path in temp_paths]
            for temporary, final_path, expected_hash in zip(
                temp_paths, (feature_path, outcome_path), hashes, strict=True,
            ):
                if final_path.exists():
                    if _sha256_file(final_path) != expected_hash:
                        raise RuntimeError(f"未登记的既有分片内容不同，拒绝覆盖：{final_path}")
                    temporary.unlink()
                else:
                    os.replace(temporary, final_path)
            entry = {
                "shard_key": shard_key,
                "status": "COMPLETE",
                "input_digest": input_digest,
                "source_digest": source_digest,
                "row_count": int(len(feature_frame)),
                "features_path": feature_rel.as_posix(),
                "features_sha256": hashes[0],
                "outcomes_path": outcome_rel.as_posix(),
                "outcomes_sha256": hashes[1],
                "resumed": False,
            }
            self.state["shards"][shard_key] = entry
            _atomic_json(self.state_path, self.state)
            return entry
        finally:
            for temporary in temp_paths:
                if temporary.exists():
                    temporary.unlink()

    def record_failure(
        self,
        *,
        security_id: str,
        year: int,
        source_digest: str,
        error_code: str,
        error_type: str,
    ) -> None:
        security_id = _safe_component(security_id, "security_id")
        if not re.fullmatch(r"[a-f0-9]{64}", source_digest):
            raise ValueError("source_digest 必须为 SHA-256")
        self.state["shards"][f"{security_id}/{int(year)}"] = {
            "shard_key": f"{security_id}/{int(year)}",
            "status": "FAILED",
            "source_digest": source_digest,
            "error_code": _safe_component(error_code, "error_code"),
            "error_type": _safe_component(error_type, "error_type"),
        }
        _atomic_json(self.state_path, self.state)

    def finalize(self, *, expected_shards: Sequence[str] | None = None) -> dict[str, Any]:
        shards = self.state["shards"]
        expected = set(expected_shards or shards)
        missing = sorted(expected - set(shards))
        failed = sorted(
            key for key, item in shards.items()
            if item.get("status") != "COMPLETE"
        )
        complete = not missing and not failed
        ordered = [shards[key] for key in sorted(shards)]
        digest_input = [
            {key: item.get(key) for key in (
                "shard_key", "status", "input_digest", "source_digest", "row_count",
                "features_sha256", "outcomes_sha256", "error_code", "error_type",
            )}
            for item in ordered
        ]
        digest = _sha256_bytes(_canonical_json({
            "schema_version": W4_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "metadata": self.metadata,
            "shards": digest_input,
            "missing_shards": missing,
        }).encode("utf-8"))
        manifest = {
            "schema_version": W4_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "status": "COMPLETE" if complete else "PARTIAL",
            "dataset_digest": digest,
            "row_count": sum(int(item.get("row_count", 0)) for item in ordered),
            "expected_shard_count": len(expected),
            "complete_shard_count": sum(1 for item in ordered if item.get("status") == "COMPLETE"),
            "failed_shards": failed,
            "missing_shards": missing,
            "metadata": self.metadata,
            "shards": ordered,
        }
        _atomic_json(self.root / "manifest.json", manifest)
        return manifest


def query_historical_dataset(
    root: Path,
    dataset_id: str,
    *,
    security_ids: Sequence[str] = (),
    date_from: date | None = None,
    date_to: date | None = None,
) -> pd.DataFrame:
    """使用 DuckDB 只查询 manifest 已登记的成对分片，不扫描目录中的孤儿文件。"""
    dataset_id = _safe_component(dataset_id, "dataset_id")
    dataset_root = (Path(root).resolve() / dataset_id).resolve()
    manifest_path = dataset_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"研究数据集不存在：{dataset_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != dataset_id or manifest.get("schema_version") != W4_SCHEMA_VERSION:
        raise ValueError("数据集 manifest 身份或版本无效")
    complete_shards = [item for item in manifest.get("shards", []) if item.get("status") == "COMPLETE"]
    if not complete_shards:
        return pd.DataFrame()
    feature_paths: list[str] = []
    outcome_paths: list[str] = []
    for shard in complete_shards:
        for key, digest_key, collection in (
            ("features_path", "features_sha256", feature_paths),
            ("outcomes_path", "outcomes_sha256", outcome_paths),
        ):
            path = (dataset_root / shard[key]).resolve()
            if not path.is_relative_to(dataset_root):
                raise ValueError("manifest 分片路径越出数据集目录")
            if not path.is_file() or _sha256_file(path) != shard[digest_key]:
                raise ValueError(f"manifest 分片缺失或 digest 不一致：{shard[key]}")
            collection.append(str(path))

    def _sql_paths(paths: Sequence[str]) -> str:
        return "[" + ",".join(
            "'" + path.replace("\\", "/").replace("'", "''") + "'" for path in paths
        ) + "]"

    clauses: list[str] = []
    parameters: list[Any] = []
    if security_ids:
        clauses.append("f.security_id IN (" + ",".join("?" for _ in security_ids) + ")")
        parameters.extend(str(value) for value in security_ids)
    if date_from is not None:
        clauses.append("CAST(f.research_date AS DATE) >= ?")
        parameters.append(date_from)
    if date_to is not None:
        clauses.append("CAST(f.research_date AS DATE) <= ?")
        parameters.append(date_to)
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from 不能晚于 date_to")
    predicate = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = f"""
        SELECT f.*, o.label_version, o.bar_version, o.factor_version, o.price_basis,
               o.bar_manifest_sha256, o.factor_manifest_sha256,
               o.trade_date, o.trade_index, o.benchmark_code, o.is_degraded,
               o.ret_1d, o.ret_5d, o.ret_10d, o.ret_20d, o.ret_60d,
               o.bench_ret_1d, o.bench_ret_5d, o.bench_ret_10d, o.bench_ret_20d, o.bench_ret_60d,
               o.excess_return_1d, o.excess_return_5d, o.excess_return_10d,
               o.excess_return_20d, o.excess_return_60d,
               o.horizon_available_1d, o.horizon_available_5d, o.horizon_available_10d,
               o.horizon_available_20d, o.horizon_available_60d,
               o.horizon_requested_1d, o.horizon_requested_5d, o.horizon_requested_10d,
               o.horizon_requested_20d, o.horizon_requested_60d,
               o.max_favorable_move_20d, o.max_adverse_move_20d, o.max_drawdown_20d
        FROM read_parquet({_sql_paths(feature_paths)}) f
        INNER JOIN read_parquet({_sql_paths(outcome_paths)}) o
          ON f.dataset_id=o.dataset_id
         AND f.security_id=o.security_id
         AND f.research_date=o.research_date
         AND f.feature_version=o.feature_version
         AND f.pit_version=o.pit_version
         AND f.birth_profile_version=o.birth_profile_version
         AND f.calendar_version=o.calendar_version
         AND f.engine_versions_json=o.engine_versions_json
         AND f.rule_versions_json=o.rule_versions_json
         AND f.config_version=o.config_version
        {predicate}
        ORDER BY f.security_id, f.research_date
    """
    with duckdb.connect(database=":memory:") as connection:
        return connection.execute(query, parameters).df()


__all__ = [
    "FEATURE_KEY",
    "HistoricalResearchDatasetStore",
    "W4_SCHEMA_VERSION",
    "query_historical_dataset",
    "validate_feature_outcome_frames",
]
