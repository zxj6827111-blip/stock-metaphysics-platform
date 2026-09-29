"""F5 W6：冻结并可重放的首批研究实验。"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import yaml

from src.core.schemas.market import EventStudyRequest, HorizonStats
from src.research.historical_dataset_event_study import _read_manifest
from src.research.multipletesting.fdr import benjamini_hochberg
from src.research.multipletesting.resample import (
    moving_date_block_bootstrap,
    permutation_test,
)
from src.research.validation.negative_controls import random_factor_control

PROTOCOL_PATH = Path(__file__).resolve().parents[2] / "config" / "f5_preregistered_experiments.yaml"
MAX_DATASET_ROWS = 250_000
_SAFE_EXPERIMENT_ID = re.compile(r"^F5-EXP-00[1-3]$")
_SAFE_REPORT_ID = re.compile(r"^F5-EXP-00[1-3](?:-[A-Z0-9]+(?:-[A-Z0-9]+)*)?$")
_VERSION_JOIN_FIELDS = (
    "feature_version", "pit_version", "birth_profile_version",
    "birth_profile_source_version", "calendar_version", "engine_versions_json",
    "rule_versions_json", "config_version",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _seed_for(base_seed: int, *parts: object) -> int:
    payload = "|".join([str(base_seed), *(str(part) for part in parts)]).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:8], 16)


def load_f5_protocol(path: Path = PROTOCOL_PATH) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    protocol = yaml.safe_load(raw.decode("utf-8"))
    supported = {"f5-preregistered-v1", "f5-preregistered-limited-v1"}
    if not isinstance(protocol, dict) or protocol.get("protocol_version") not in supported:
        raise ValueError("F5 预注册协议版本无效")
    if protocol.get("confirmatory_eligible") is not False:
        raise ValueError("W6 协议不得声明确认性研究资格")
    if protocol.get("pilot_labels_previously_seen") is not True:
        raise ValueError("预注册必须披露此前已查看的 W4 工程样本标签摘要")
    experiments = protocol.get("experiments")
    if not isinstance(experiments, list) or [item.get("experiment_id") for item in experiments] != [
        "F5-EXP-001", "F5-EXP-002",
    ]:
        raise ValueError("只允许按冻结顺序注册 F5-EXP-001/002")
    not_configured = protocol.get("not_configured", [])
    if [item.get("experiment_id") for item in not_configured] != ["F5-EXP-003"]:
        raise ValueError("F5-EXP-003 必须显式保持未配置")
    partitions = protocol.get("split", {}).get("partitions", [])
    if [item.get("id") for item in partitions] != ["TRAIN", "VALIDATION", "OOS"]:
        raise ValueError("研究时间分区与冻结 split 不一致")

    expected_sizes = {"F5-EXP-001": 60, "F5-EXP-002": 18}
    horizons = protocol.get("analysis", {}).get("horizons")
    if horizons != [5, 20]:
        raise ValueError("W6 只允许冻结的 5 日与 20 日周期")
    for experiment in experiments:
        experiment_id = experiment["experiment_id"]
        if not _SAFE_EXPERIMENT_ID.fullmatch(experiment_id):
            raise ValueError("实验 ID 不安全")
        if experiment.get("expected_direction") != "none" or experiment.get("tails") != "two_sided":
            raise ValueError(f"{experiment_id} 不允许事后指定有利方向")
        if experiment.get("registered_family_size") != expected_sizes[experiment_id]:
            raise ValueError(f"{experiment_id} 检验族大小与冻结检验族不一致")
        if not _SAFE_REPORT_ID.fullmatch(str(experiment.get("report_id", experiment_id))):
            raise ValueError(f"{experiment_id} report_id 不安全")
    for item in not_configured:
        if not _SAFE_REPORT_ID.fullmatch(str(item.get("report_id", item["experiment_id"]))):
            raise ValueError("未配置实验 report_id 不安全")

    if protocol["protocol_version"] == "f5-preregistered-v1":
        if protocol.get("dataset", {}).get("use") != "engineering_replay_only":
            raise ValueError("冻结 W6 v1 必须继续绑定原工程回放数据集")
    else:
        dataset = protocol.get("dataset", {})
        if dataset.get("use") != "limited_scope_exploratory_only":
            raise ValueError("限域 W6 协议必须明确为 limited_scope_exploratory_only")
        if dataset.get("confirmatory_research_eligible") is not False:
            raise ValueError("限域 W6 协议不得声明确认性研究资格")
        if not dataset.get("scope_certificate_sha256"):
            raise ValueError("限域 W6 协议必须绑定 scope certificate SHA-256")
    return protocol, _sha256(raw)

def _sql_paths(paths: list[Path]) -> str:
    if not paths:
        raise ValueError("W4 manifest 没有完整分片")
    escaped = [path.as_posix().replace("'", "''") for path in paths]
    return "[" + ",".join(f"'{path}'" for path in escaped) + "]"


def _load_w4_panel(
    root: Path,
    protocol: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], set[str]]:
    dataset = protocol["dataset"]
    manifest, feature_paths, outcome_paths = _read_manifest(root, dataset["dataset_id"])
    if manifest.get("dataset_digest") != dataset["dataset_digest"]:
        raise ValueError("W4 数据集 digest 与冻结预注册版本不一致")
    if manifest.get("status") != "COMPLETE":
        raise ValueError("W6 不读取 PARTIAL 数据集")
    if protocol.get("protocol_version") == "f5-preregistered-limited-v1":
        metadata = manifest.get("metadata", {})
        certificate = metadata.get("scope_certificate", {})
        if metadata.get("research_eligible") is not True:
            raise ValueError("限域 W6 输入数据集没有声明限域 research eligibility")
        if metadata.get("confirmatory_research_eligible") is not False:
            raise ValueError("限域 W6 输入数据集确认性资格必须保持 false")
        if metadata.get("full_pit_universe_status") != "COVERAGE_INCOMPLETE":
            raise ValueError("限域 W6 不得把局部认证覆盖到完整 W2 PIT 状态")
        if certificate.get("certificate_sha256") != dataset.get("scope_certificate_sha256"):
            raise ValueError("W6 协议与 W4 scope certificate digest 不一致")
    if len(feature_paths) != len(outcome_paths):
        raise ValueError("W4 features/outcomes 分片数量不一致")

    con = duckdb.connect(database=":memory:")
    try:
        outcome_columns = {
            str(row[0]) for row in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet({_sql_paths(outcome_paths)})"
            ).fetchall()
        }
        end_dates = {
            horizon: (
                f"CAST(o.label_end_date_{horizon}d AS DATE) AS label_end_date_{horizon}d"
                if f"label_end_date_{horizon}d" in outcome_columns
                else f"CAST(NULL AS DATE) AS label_end_date_{horizon}d"
            )
            for horizon in (5, 20)
        }
        query = f"""
            SELECT f.dataset_id, f.security_id, f.stock_code,
                   CAST(f.research_date AS DATE) AS research_date,
                   f.features_json, f.research_eligible, f.research_use_status,
                   o.trade_date, o.trade_index, COALESCE(o.is_degraded, TRUE) AS is_degraded,
                   o.ret_5d, o.ret_20d, o.excess_return_5d, o.excess_return_20d,
                   COALESCE(o.horizon_available_5d, FALSE) AS horizon_available_5d,
                   COALESCE(o.horizon_available_20d, FALSE) AS horizon_available_20d,
                   {end_dates[5]}, {end_dates[20]}
            FROM read_parquet({_sql_paths(feature_paths)}) f
            INNER JOIN read_parquet({_sql_paths(outcome_paths)}) o
              ON f.dataset_id=o.dataset_id
             AND f.security_id=o.security_id
             AND f.research_date=o.research_date
             AND """ + " AND ".join(f"f.{field}=o.{field}" for field in _VERSION_JOIN_FIELDS) + """
            ORDER BY f.stock_code, f.research_date, f.security_id
        """
        count = int(con.execute(f"SELECT COUNT(*) FROM ({query}) AS verified_panel").fetchone()[0])
        if count > MAX_DATASET_ROWS:
            raise ValueError(
                f"W6 单次最多读取 {MAX_DATASET_ROWS} 个证券-日期观察；当前 {count}，请预先构建较小的版本化数据集。"
            )
        result = con.execute(query).fetchall()
    finally:
        con.close()
    if protocol.get("protocol_version") == "f5-preregistered-limited-v1":
        required_end_dates = {"label_end_date_5d", "label_end_date_20d"}
        if not required_end_dates.issubset(outcome_columns):
            raise ValueError("限域 W6 需要 W4 保存精确的 5/20 日 label_end_date")

    columns = [
        "dataset_id", "security_id", "stock_code", "research_date", "features_json",
        "research_eligible", "research_use_status", "trade_date", "trade_index", "is_degraded",
        "ret_5d", "ret_20d", "excess_return_5d", "excess_return_20d",
        "horizon_available_5d", "horizon_available_20d", "label_end_date_5d", "label_end_date_20d",
    ]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, date]] = set()
    for raw in result:
        row = dict(zip(columns, raw, strict=True))
        identity = (str(row["security_id"]), row["research_date"])
        if identity in seen:
            raise ValueError(f"W4 数据集证券/日期键重复：{identity}")
        seen.add(identity)
        feature_payload = json.loads(row.pop("features_json") or "{}")
        observations = feature_payload.get("factor_set", {}).get("observations", [])
        factor_map: dict[str, dict[str, Any]] = {}
        for item in observations:
            factor_id = str(item.get("factor_id") or "")
            if not factor_id:
                continue
            if factor_id in factor_map:
                raise ValueError(f"W4 特征中同一观察的因子重复：{identity}/{factor_id}")
            factor_map[factor_id] = item
        row["factors"] = factor_map
        row["stock_code"] = str(row["stock_code"])
        row["research_date"] = row["research_date"]
        row["trade_date"] = row["trade_date"]
        row["is_degraded"] = bool(row["is_degraded"])
        rows.append(row)
    return rows, manifest, outcome_columns


def _partition_for(day: date, partitions: list[dict[str, str]]) -> str | None:
    for partition in partitions:
        if date.fromisoformat(partition["start"]) <= day <= date.fromisoformat(partition["end"]):
            return str(partition["id"])
    return None


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _condition_specs(experiment: dict[str, Any]) -> list[dict[str, Any]]:
    if experiment["experiment_id"] == "F5-EXP-001":
        return [
            {
                "condition_id": f"ten_god_{index:02d}",
                "title": category,
                "factor_id": experiment["factor_id"],
                "raw_value_category": category,
                "registered_categories": list(experiment["raw_value_categories"]),
            }
            for index, category in enumerate(experiment["raw_value_categories"], start=1)
        ]
    return [dict(item) for item in experiment["conditions"]]


def _factor_observation(row: dict[str, Any], factor_id: str) -> dict[str, Any] | None:
    observation = row.get("factors", {}).get(factor_id)
    return observation if isinstance(observation, dict) else None


def _is_hit(row: dict[str, Any], experiment_id: str, condition: dict[str, Any]) -> bool:
    observation = _factor_observation(row, str(condition["factor_id"]))
    if not observation or observation.get("availability") != "ok":
        return False
    raw = observation.get("raw_value")
    if experiment_id == "F5-EXP-001":
        if raw not in condition["registered_categories"]:
            raise ValueError(f"B_DAY_005 出现未预注册十神类别：{raw!r}")
        return raw == condition["raw_value_category"]
    count = _finite(raw)
    if count is None or count < 0 or not count.is_integer():
        raise ValueError(f"{condition['factor_id']} 原始关系计数无效：{raw!r}")
    return count > 0


def _metrics(rows: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    return_fields = {
        "adjusted_absolute_return": f"ret_{horizon}d",
        "benchmark_excess_return": f"excess_return_{horizon}d",
    }
    metrics: dict[str, Any] = {
        "candidate_observation_count": len(rows),
        "degraded_observation_count": sum(bool(row["is_degraded"]) for row in rows),
        "horizon_unavailable_count": sum(
            not bool(row.get(f"horizon_available_{horizon}d")) for row in rows
        ),
        "adjusted_return_missing_count": sum(
            bool(row.get(f"horizon_available_{horizon}d"))
            and _finite(row.get(f"ret_{horizon}d")) is None
            for row in rows
        ),
        "benchmark_excess_missing_count": sum(
            bool(row.get(f"horizon_available_{horizon}d"))
            and _finite(row.get(f"excess_return_{horizon}d")) is None
            for row in rows
        ),
    }
    for metric, column in return_fields.items():
        values = [
            value for row in rows
            if not row["is_degraded"]
            and bool(row.get(f"horizon_available_{horizon}d"))
            and (value := _finite(row.get(column))) is not None
        ]
        metrics[metric] = {
            "sample_count": len(values),
            "missing_count": max(0, len(rows) - len(values)),
            "mean": round(float(np.mean(values)), 8) if values else None,
            "median": round(float(np.median(values)), 8) if values else None,
            "win_rate": round(float(np.mean(np.asarray(values) > 0)), 8) if values else None,
        }
    return metrics


def _daily_permutable_dates(rows: list[dict[str, Any]], factor_id: str, experiment_id: str,
                            condition: dict[str, Any], horizon: int) -> int:
    by_date: dict[date, list[bool]] = {}
    for row in rows:
        if row["is_degraded"] or not row.get(f"horizon_available_{horizon}d"):
            continue
        if _finite(row.get(f"excess_return_{horizon}d")) is None:
            continue
        observation = _factor_observation(row, factor_id)
        if not observation or observation.get("availability") != "ok":
            continue
        by_date.setdefault(row["research_date"], []).append(_is_hit(row, experiment_id, condition))
    return sum(any(flags) and not all(flags) for flags in by_date.values())


def _legacy_random_factor_control(
    rows: list[dict[str, Any]],
    hit_rows: list[dict[str, Any]],
    factor_id: str,
    *,
    seed: int,
) -> dict[str, Any]:
    labels = pd.DataFrame([
        {
            "stock_code": row["stock_code"],
            "trade_date": row["trade_date"],
            "ret_5d": row.get("ret_5d"),
            "ret_20d": row.get("ret_20d"),
            "excess_return_20d": row.get("excess_return_20d"),
        }
        for row in rows
    ])
    observations = pd.DataFrame([
        {
            "stock_code": row["stock_code"],
            "trade_date": row["trade_date"],
            "factor_id": factor_id,
            "direction": (_factor_observation(row, factor_id) or {}).get("direction"),
            "rule_score": (_factor_observation(row, factor_id) or {}).get("rule_score"),
            "normalized_value": (_factor_observation(row, factor_id) or {}).get("normalized_value"),
        }
        for row in hit_rows
    ])
    hit_20 = [
        value for row in hit_rows
        if not row["is_degraded"]
        and row.get("horizon_available_20d")
        and (value := _finite(row.get("ret_20d"))) is not None
    ]
    hit_20_excess = [
        value for row in hit_rows
        if not row["is_degraded"]
        and row.get("horizon_available_20d")
        and (value := _finite(row.get("excess_return_20d"))) is not None
    ]
    real_stats = HorizonStats(
        horizon=20,
        sample_count=len(hit_20),
        mean_return=round(float(np.mean(hit_20)), 8) if hit_20 else None,
        up_rate=round(float(np.mean(np.asarray(hit_20) > 0)), 8) if hit_20 else None,
        mean_excess_return=round(float(np.mean(hit_20_excess)), 8) if hit_20_excess else None,
    )
    request = EventStudyRequest(
        factor_ids=[factor_id],
        horizons=[5, 20],
        activation="any",
    )
    control = random_factor_control(
        observations,
        labels,
        request,
        real_stats=real_stats,
        seed=seed,
    )
    return control.model_dump(mode="json", exclude={"computed_at"})


def _correct_registered_family(
    tests: list[dict[str, Any]],
    *,
    experiment: dict[str, Any],
    alpha: float,
) -> dict[str, Any]:
    family_size = int(experiment["registered_family_size"])
    if len(tests) != family_size:
        raise ValueError(
            f"{experiment['experiment_id']} 实际注册检验数 {len(tests)} != 冻结族大小 {family_size}"
        )
    p_values = [
        float(item["raw_p_value"]) if item.get("raw_p_value") is not None else 1.0
        for item in tests
    ]
    q_values = benjamini_hochberg(p_values, alpha)
    threshold = alpha / family_size
    for item, q_value in zip(tests, q_values, strict=True):
        if item.get("raw_p_value") is None:
            item["fdr_q_value"] = None
            item["fdr_pass"] = False
            item["bonferroni_pass"] = False
        else:
            item["fdr_q_value"] = round(float(q_value), 10) if q_value is not None else None
            item["fdr_pass"] = bool(q_value is not None and q_value <= alpha)
            item["bonferroni_pass"] = float(item["raw_p_value"]) <= threshold
        item["family_id"] = experiment["family_id"]
        item["registered_family_size"] = family_size
        item["family_alpha"] = alpha
        item["bonferroni_threshold"] = round(threshold, 10)
        item["unavailable_tests_padded_with_one"] = sum(
            test.get("raw_p_value") is None for test in tests
        )
    return {
        "family_id": experiment["family_id"],
        "registered_test_count": family_size,
        "evaluable_p_value_count": sum(item.get("raw_p_value") is not None for item in tests),
        "unavailable_p_value_count": sum(item.get("raw_p_value") is None for item in tests),
        "alpha": alpha,
        "bonferroni_threshold": round(threshold, 10),
        "fdr_pass_count": sum(bool(item.get("fdr_pass")) for item in tests),
        "bonferroni_pass_count": sum(bool(item.get("bonferroni_pass")) for item in tests),
        "missing_p_values_conservatively_padded_with": 1.0,
    }


def analyze_f5_panel(
    panel: list[dict[str, Any]],
    manifest: dict[str, Any],
    outcome_columns: set[str],
    protocol: dict[str, Any],
    *,
    protocol_digest: str,
    implementation_digest: str,
) -> list[dict[str, Any]]:
    analysis = protocol["analysis"]
    partitions = protocol["split"]["partitions"]
    alpha = float(analysis["alpha"])
    base_seed = int(analysis["permutation"]["seed"])
    per_family_tests: dict[str, list[dict[str, Any]]] = {}
    reports: list[dict[str, Any]] = []
    scope_counts = {partition["id"]: 0 for partition in partitions}
    out_of_scope_count = 0
    partition_rows: dict[str, list[dict[str, Any]]] = {key: [] for key in scope_counts}
    for row in panel:
        partition_id = _partition_for(row["research_date"], partitions)
        if partition_id is None:
            out_of_scope_count += 1
            continue
        scope_counts[partition_id] += 1
        partition_rows[partition_id].append(row)

    for experiment in protocol["experiments"]:
        experiment_id = experiment["experiment_id"]
        tests: list[dict[str, Any]] = []
        for partition in partitions:
            partition_id = partition["id"]
            rows = partition_rows[partition_id]
            start = date.fromisoformat(partition["start"])
            end = date.fromisoformat(partition["end"])
            for condition in _condition_specs(experiment):
                factor_id = str(condition["factor_id"])
                feature_rows = [
                    row for row in rows
                    if (obs := _factor_observation(row, factor_id)) is not None
                    and obs.get("availability") == "ok"
                ]
                for horizon in analysis["horizons"]:
                    h = int(horizon)
                    end_field = f"label_end_date_{h}d"
                    valid_label_rows = [
                        row for row in feature_rows
                        if not row["is_degraded"]
                        and row.get(f"horizon_available_{h}d")
                        and (
                            _finite(row.get(f"ret_{h}d")) is not None
                            or _finite(row.get(f"excess_return_{h}d")) is not None
                        )
                    ]
                    end_date_known = (
                        end_field in outcome_columns
                        and all(isinstance(row.get(end_field), date) for row in valid_label_rows)
                    )
                    boundary_crossing_count = 0
                    if end_date_known:
                        if any(row[end_field] < row["research_date"] for row in valid_label_rows):
                            raise ValueError(f"{end_field} 早于对应研究日")
                        boundary_crossing_count = sum(
                            row[end_field] > end for row in valid_label_rows
                        )
                        valid_label_ids = {id(row) for row in valid_label_rows}
                        isolated_rows = [
                            row for row in rows
                            if row["research_date"] <= end
                            and (
                                id(row) not in valid_label_ids
                                or row[end_field] <= end
                            )
                        ]
                    else:
                        isolated_rows = rows
                    isolated_feature_rows = [
                        row for row in isolated_rows
                        if (obs := _factor_observation(row, factor_id)) is not None
                        and obs.get("availability") == "ok"
                    ]
                    isolated_hits = [
                        row for row in isolated_feature_rows
                        if _is_hit(row, experiment_id, condition)
                    ]
                    isolated_complement = [
                        row for row in isolated_feature_rows if not _is_hit(row, experiment_id, condition)
                    ]
                    matched_metrics = _metrics(isolated_hits, h)
                    complement_metrics = _metrics(isolated_complement, h)
                    overall_metrics = _metrics(isolated_feature_rows, h)

                    inference_rows = [
                        row for row in isolated_feature_rows
                        if not row["is_degraded"]
                        and row.get(f"horizon_available_{h}d")
                        and _finite(row.get(f"excess_return_{h}d")) is not None
                        and end_date_known
                    ]
                    inferential_hit_count = sum(
                        _is_hit(row, experiment_id, condition) for row in inference_rows
                    )
                    inferential_complement_count = len(inference_rows) - inferential_hit_count
                    permutable_dates = _daily_permutable_dates(
                        inference_rows, factor_id, experiment_id, condition, h,
                    )
                    window_status = (
                        "VERIFIED"
                        if end_date_known
                        else "UNVERIFIABLE_LABEL_END_DATE"
                    )
                    reasons: list[str] = []
                    if not end_date_known:
                        reasons.append("W4 分片未保存全部标签终点日期，不能验证分区隔离窗口。")
                    if inferential_hit_count < analysis["min_hit_and_complement_samples"]:
                        reasons.append("超额收益命中组低于预注册最低样本数。")
                    if inferential_complement_count < analysis["min_hit_and_complement_samples"]:
                        reasons.append("超额收益补集低于预注册最低样本数。")
                    if not any(
                        _finite(row.get(f"excess_return_{h}d")) is not None
                        for row in isolated_feature_rows
                        if not row["is_degraded"] and row.get(f"horizon_available_{h}d")
                    ):
                        reasons.append("本周期没有可用的 benchmark excess return。")
                    if permutable_dates == 0:
                        reasons.append("没有同时含命中与补集证券的日期分层，置换零假设不可识别。")

                    permutation_payload: dict[str, Any] = {
                        "method": analysis["permutation"]["method"],
                        "tail": analysis["permutation"]["tail"],
                        "requested_count": int(analysis["permutation"]["count"]),
                        "permutation_count": 0,
                        "seed": _seed_for(base_seed, experiment_id, condition["condition_id"], partition_id, h, "perm"),
                        "permutable_date_count": permutable_dates,
                        "p_value": None,
                        "status": "NOT_RUN",
                    }
                    bootstrap_payload: dict[str, Any] = {
                        "method": analysis["bootstrap"]["method"],
                        "requested_count": int(analysis["bootstrap"]["count"]),
                        "bootstrap_count": 0,
                        "seed": _seed_for(
                            int(analysis["bootstrap"]["seed"]),
                            experiment_id, condition["condition_id"], partition_id, h,
                        ),
                        "block_length_trading_dates": int(analysis["bootstrap"]["block_length_trading_dates"]),
                        "status": "NOT_RUN",
                    }
                    if (
                        end_date_known
                        and inferential_hit_count >= analysis["min_hit_and_complement_samples"]
                        and inferential_complement_count >= analysis["min_hit_and_complement_samples"]
                        and permutable_dates > 0
                    ):
                        inferential_frame = pd.DataFrame([
                            {
                                "as_of": row["research_date"],
                                "hit": _is_hit(row, experiment_id, condition),
                                "excess_return": float(row[f"excess_return_{h}d"]),
                            }
                            for row in inference_rows
                        ])
                        permutation = permutation_test(
                            inferential_frame,
                            "hit",
                            "excess_return",
                            date_col="as_of",
                            permutation_count=int(analysis["permutation"]["count"]),
                            seed=permutation_payload["seed"],
                        )
                        permutation_payload.update({
                            "permutation_count": permutation.permutation_count,
                            "p_value": permutation.p_value_two_sided,
                            "statistic": permutation.statistic,
                            "status": "COMPLETED" if permutation.p_value_two_sided is not None else "UNAVAILABLE",
                        })
                        bootstrap = moving_date_block_bootstrap(
                            inferential_frame,
                            "excess_return",
                            date_col="as_of",
                            hit_col="hit",
                            block_length=bootstrap_payload["block_length_trading_dates"],
                            bootstrap_count=int(analysis["bootstrap"]["count"]),
                            confidence=float(analysis["bootstrap"]["confidence"]),
                            seed=bootstrap_payload["seed"],
                        )
                        bootstrap_payload.update(bootstrap.to_dict())
                        bootstrap_payload["status"] = (
                            "COMPLETED" if bootstrap.ci_lower is not None else "INSUFFICIENT_BLOCKS"
                        )
                    else:
                        if not end_date_known:
                            permutation_payload["reason"] = "标签终点日期缺失，分区隔离推断被阻止。"
                            bootstrap_payload["reason"] = "标签终点日期缺失，分区隔离推断被阻止。"
                        elif inferential_hit_count < analysis["min_hit_and_complement_samples"] or (
                            inferential_complement_count < analysis["min_hit_and_complement_samples"]
                        ):
                            permutation_payload["reason"] = "命中组或补集未达到最低可解释样本数。"
                            bootstrap_payload["reason"] = "命中组或补集未达到最低可解释样本数。"
                        else:
                            permutation_payload["reason"] = "单日横截面无可置换变异。"
                            bootstrap_payload["reason"] = "命中组或补集未达到最低可解释样本数。"

                    negative_rows = [
                        row for row in isolated_feature_rows
                        if not row["is_degraded"]
                    ]
                    negative_hits = [
                        row for row in negative_rows
                        if _is_hit(row, experiment_id, condition)
                    ]
                    negative_control = _legacy_random_factor_control(
                        negative_rows,
                        negative_hits,
                        factor_id,
                        seed=_seed_for(
                            int(analysis["negative_control"]["seed"]),
                            experiment_id, condition["condition_id"], partition_id, "random-factor",
                        ),
                    )
                    sample_status = (
                        "INSUFFICIENT_SAMPLE"
                        if reasons else "RESAMPLING_COMPLETE_EXPLORATORY"
                    )
                    item = {
                        "hypothesis_id": f"{experiment_id}:{condition['condition_id']}:{partition_id}:H{h}",
                        "condition_id": condition["condition_id"],
                        "condition_title": condition["title"],
                        "factor_id": factor_id,
                        "partition": partition_id,
                        "horizon": h,
                        "start_date": start.isoformat(),
                        "end_date": end.isoformat(),
                        "candidate_observation_count": len(rows),
                        "feature_available_count": len(isolated_feature_rows),
                        "feature_unavailable_count": max(0, len(isolated_rows) - len(isolated_feature_rows)),
                        "boundary_crossing_window_excluded_count": boundary_crossing_count,
                        "partition_window_status": window_status,
                        "matched_observation_count": len(isolated_hits),
                        "complement_observation_count": len(isolated_complement),
                        "matched": matched_metrics,
                        "complement": complement_metrics,
                        "overall": overall_metrics,
                        "inferential_excess_return_sample": {
                            "matched_count": inferential_hit_count,
                            "complement_count": inferential_complement_count,
                            "permutable_date_count": permutable_dates,
                        },
                        "permutation": permutation_payload,
                        "moving_block_bootstrap": bootstrap_payload,
                        "negative_control": {
                            "method": analysis["negative_control"]["method"],
                            "metric_scope": "legacy absolute adjusted returns; diagnostic only",
                            **negative_control,
                        },
                        "sample_status": sample_status,
                        "sample_status_reasons": reasons,
                        "research_status": "EXPLORATORY_NOT_GATED",
                    }
                    item["raw_p_value"] = permutation_payload["p_value"]
                    tests.append(item)

        correction = _correct_registered_family(
            tests, experiment=experiment, alpha=alpha,
        )
        per_family_tests[experiment_id] = tests
        research_eligible = bool(manifest.get("metadata", {}).get("research_eligible", False))
        report = {
            "schema_version": "w6-research-experiment-v1",
            "experiment_id": experiment_id,
            "title": experiment["title"],
            "protocol_version": protocol["protocol_version"],
            "protocol_sha256": protocol_digest,
            "implementation_sha256": implementation_digest,
            "registration": {
                "registered_at": protocol["registered_at"],
                "pilot_labels_previously_seen": protocol["pilot_labels_previously_seen"],
                "category_level_results_seen_at_registration": protocol[
                    "category_level_results_seen_at_registration"
                ],
                "confirmatory_eligible": False,
            },
            "dataset": {
                "dataset_id": manifest["dataset_id"],
                "dataset_digest": manifest["dataset_digest"],
                "schema_version": manifest["schema_version"],
                "manifest_status": manifest["status"],
                "metadata": manifest.get("metadata", {}),
                "research_eligible": research_eligible,
                "confirmatory_research_eligible": bool(
                    manifest.get("metadata", {}).get("confirmatory_research_eligible", False)
                ),
            },
            "scope": {
                "observation_count": len(panel),
                "partition_observation_counts": scope_counts,
                "out_of_scope_observation_count": out_of_scope_count,
                "date_from": (
                    min((row["research_date"] for row in panel), default=None).isoformat()
                    if panel else None
                ),
                "date_to": (
                    max((row["research_date"] for row in panel), default=None).isoformat()
                    if panel else None
                ),
                "security_count": len({str(row["security_id"]) for row in panel}),
                "label_end_date_columns_available": sorted(
                    column for column in outcome_columns if column in {
                        "label_end_date_5d", "label_end_date_20d",
                    }
                ),
            },
            "frozen_conditions": experiment,
            "analysis_protocol": analysis,
            "time_split_protocol": protocol["split"],
            "family_correction": correction,
            "registered_tests": tests,
            "research_status": "EXPLORATORY_NOT_GATED",
            "research_status_reasons": protocol.get("research_status_reasons", [
                "此协议固定于 W4 工程样本；该样本及完整 W2 物理范围均未认证。",
                "研究状态不升级为显著、有效、可预测或交易建议。",
            ]),
        }
        if experiment.get("report_id"):
            report["report_id"] = str(experiment["report_id"])
        reports.append(report)

    for item in protocol["not_configured"]:
        report = {
            "schema_version": "w6-research-experiment-v1",
            "experiment_id": item["experiment_id"],
            "title": "未配置实验",
            "protocol_version": protocol["protocol_version"],
            "protocol_sha256": protocol_digest,
            "implementation_sha256": implementation_digest,
            "status": "NOT_CONFIGURED",
            "research_status": "NOT_RUN",
            "reason": item["reason"],
            "search_performed": False,
            "dataset": {
                "dataset_id": manifest["dataset_id"],
                "dataset_digest": manifest["dataset_digest"],
            },
        }
        if item.get("report_id"):
            report["report_id"] = str(item["report_id"])
        reports.append(report)
    return reports


def run_f5_preregistered_experiments(
    data_dir: Path,
    *,
    protocol_path: Path = PROTOCOL_PATH,
) -> list[dict[str, Any]]:
    protocol, protocol_digest = load_f5_protocol(protocol_path)
    panel, manifest, outcome_columns = _load_w4_panel(
        Path(data_dir) / "research_datasets", protocol,
    )
    implementation_paths = [
        Path(__file__),
        Path(__file__).with_name("multipletesting") / "resample.py",
        protocol_path,
    ]
    implementation_digest = _sha256(_canonical_json({
        path.name: _sha256(path.read_bytes()) for path in implementation_paths
    }))
    reports = analyze_f5_panel(
        panel,
        manifest,
        outcome_columns,
        protocol,
        protocol_digest=protocol_digest,
        implementation_digest=implementation_digest,
    )
    for report in reports:
        report["result_digest"] = _sha256(_canonical_json(report))
    write_f5_experiment_reports(Path(data_dir) / "research_experiments", reports)
    return reports


def write_f5_experiment_reports(root: Path, reports: list[dict[str, Any]]) -> dict[str, str]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for report in reports:
        experiment_id = str(report.get("experiment_id") or "")
        if not _SAFE_EXPERIMENT_ID.fullmatch(experiment_id):
            raise ValueError("W6 输出包含不安全 experiment_id")
        report_id = str(report.get("report_id", experiment_id))
        if not _SAFE_REPORT_ID.fullmatch(report_id):
            raise ValueError("W6 输出包含不安全 report_id")
        payload = {key: value for key, value in report.items() if key != "result_digest"}
        payload["result_digest"] = _sha256(_canonical_json(payload))
        encoded = _canonical_json(payload) + b"\n"
        target = root / f"{report_id}.json"
        digest = _sha256(encoded)
        if target.exists():
            existing = target.read_bytes()
            if existing != encoded:
                raise FileExistsError(
                    f"现有 W6 报告与本次重放不一致，拒绝覆盖：{target.name}；请提升协议版本创建新 ID。"
                )
            digests[report_id] = digest
            continue
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        digests[report_id] = digest
    return digests


__all__ = [
    "MAX_DATASET_ROWS",
    "PROTOCOL_PATH",
    "analyze_f5_panel",
    "load_f5_protocol",
    "run_f5_preregistered_experiments",
    "write_f5_experiment_reports",
]
