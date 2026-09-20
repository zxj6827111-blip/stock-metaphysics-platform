"""Phase 3D：假设预注册 + 实验登记（GOAL §20/§21/§22）。

两条纪律
--------
1. **假设必须在看到 OOS 收益之前写死**。``hypothesis_registry.yaml`` 里
   每个假设的命中定义、方向、持有期、对照类型都是预注册内容；读取 OOS 结果
   之后不允许修改。要改 → 新建假设 ID，旧假设保留原样。
2. **每个正式实验必须可追溯**：git sha / dataset / universe / birth model /
   factor rule / calibration / split 版本 + 区间 + 参数 + 随机种子 +
   结果状态，一条记录不少。OOS 一旦被真实读取，``oos_used=True`` 写进参数，
   之后任何改动都必须新建 experiment version 并加 ``RESEARCH_REUSE_WARNING``。

存储策略（GOAL §20："优先复用 backtest_experiment"）
---------------------------------------------------
* ``backtest_experiment`` / ``backtest_result`` 已有表结构**不需要迁移**即可容纳
  本阶段记录：``kind="oos"``、``name=hypothesis_id``、版本信息全部放进
  ``params_json``、结果明细放进 ``extra_json``。因此复用，不新建表、不写 ADR。
* 同时落 CSV/JSON 产物（``data/phase3_universe/phase3d_experiment_registry.csv``），
  使研究记录不依赖数据库是否被重建。
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

#: 假设注册表版本号
HYPOTHESIS_REGISTRY_VERSION = "phase3d-hypotheses-v1"
#: 实验登记表版本号
EXPERIMENT_REGISTRY_VERSION = "phase3d-experiments-v1"
#: OOS 被复用后的告警文案（必须出现在任何二次使用 OOS 的结果里）
RESEARCH_REUSE_WARNING = (
    "RESEARCH_REUSE_WARNING：本实验使用的 OOS 区间此前已被读取过。"
    "再次读取会削弱该区间作为 untouched holdout 的意义，"
    "任何基于此的结果都不得表述为『首次样本外验证』。"
)

#: 允许的方向来源
DIRECTION_SOURCES = ("raw", "calibrated")
#: 允许的组合逻辑
COMBO_LOGICS = ("single", "all_positive", "conflict")
#: 允许的预注册方向：positive = 单向 gate；exploratory = 只用双侧描述统计
EXPECTED_DIRECTIONS = ("positive", "exploratory")


@dataclass(frozen=True)
class HypothesisSpec:
    """一条预注册假设。"""

    hypothesis_id: str
    title: str
    object_id: str
    engines: tuple[str, ...]
    direction_source: str
    logic: str
    expected_direction: str = "positive"
    primary_horizon: int = 20
    horizons: tuple[int, ...] = (5, 10, 20, 60)
    birth_models: tuple[str, ...] = ()
    control_kinds: tuple[str, ...] = ()
    conflict: dict | None = None
    rationales: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.direction_source not in DIRECTION_SOURCES:
            raise ValueError(
                f"{self.hypothesis_id}: direction_source 必须是 {DIRECTION_SOURCES}"
            )
        if self.logic not in COMBO_LOGICS:
            raise ValueError(f"{self.hypothesis_id}: logic 必须是 {COMBO_LOGICS}")
        if self.expected_direction not in EXPECTED_DIRECTIONS:
            raise ValueError(
                f"{self.hypothesis_id}: expected_direction 必须是 {EXPECTED_DIRECTIONS}"
            )
        if self.logic == "conflict" and not self.conflict:
            raise ValueError(f"{self.hypothesis_id}: conflict 组合必须给出 conflict 定义")
        if self.primary_horizon not in self.horizons:
            raise ValueError(f"{self.hypothesis_id}: primary_horizon 必须在 horizons 内")
        if not self.engines:
            raise ValueError(f"{self.hypothesis_id}: 至少要有一个引擎")

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["engines"] = list(self.engines)
        payload["horizons"] = list(self.horizons)
        payload["birth_models"] = list(self.birth_models)
        payload["control_kinds"] = list(self.control_kinds)
        return payload


@dataclass(frozen=True)
class HypothesisRegistry:
    version: str
    frozen_at: str
    oos_labels_seen_at_registration: bool
    hypotheses: tuple[HypothesisSpec, ...]
    notes: tuple[str, ...] = ()

    def by_id(self, hypothesis_id: str) -> HypothesisSpec:
        for spec in self.hypotheses:
            if spec.hypothesis_id == hypothesis_id:
                return spec
        raise KeyError(f"未注册的假设：{hypothesis_id}")

    def ids(self) -> list[str]:
        return [spec.hypothesis_id for spec in self.hypotheses]

    def to_dict(self) -> dict:
        return {
            "registry_version": self.version,
            "frozen_at": self.frozen_at,
            "oos_labels_seen_at_registration": self.oos_labels_seen_at_registration,
            "hypothesis_count": len(self.hypotheses),
            "hypotheses": [spec.to_dict() for spec in self.hypotheses],
            "notes": list(self.notes),
        }


def load_hypothesis_registry(path: str | Path) -> HypothesisRegistry:
    """读取 YAML 假设注册表（只依赖 PyYAML，不引入新依赖）。"""
    import yaml

    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"假设注册表格式异常：{path}")
    specs: list[HypothesisSpec] = []
    for raw in payload.get("hypotheses", []):
        specs.append(HypothesisSpec(
            hypothesis_id=str(raw["hypothesis_id"]),
            title=str(raw.get("title", "")),
            object_id=str(raw.get("object_id", raw["hypothesis_id"])),
            engines=tuple(raw.get("engines", ())),
            direction_source=str(raw.get("direction_source", "raw")),
            logic=str(raw.get("logic", "single")),
            expected_direction=str(raw.get("expected_direction", "positive")),
            primary_horizon=int(raw.get("primary_horizon", 20)),
            horizons=tuple(int(h) for h in raw.get("horizons", (5, 10, 20, 60))),
            birth_models=tuple(raw.get("birth_models", ())),
            control_kinds=tuple(raw.get("control_kinds", ())),
            conflict=raw.get("conflict"),
            rationales=str(raw.get("rationale", "")),
            notes=str(raw.get("notes", "")),
        ))
    return HypothesisRegistry(
        version=str(payload.get("registry_version", HYPOTHESIS_REGISTRY_VERSION)),
        frozen_at=str(payload.get("frozen_at", "")),
        oos_labels_seen_at_registration=bool(
            payload.get("oos_labels_seen_at_registration", False)
        ),
        hypotheses=tuple(specs),
        notes=tuple(payload.get("notes", ())),
    )


# ---------------------------------------------------------------------------
# 实验登记
# ---------------------------------------------------------------------------


@dataclass
class ExperimentRecord:
    """一条正式实验记录（字段与 GOAL §20 对齐）。"""

    experiment_id: str
    hypothesis_id: str
    git_sha: str
    dataset_version: str
    universe_version: str
    birth_model_version: str
    factor_version: str
    calibration_version: str
    split_version: str
    train_period: str
    validation_period: str
    oos_period: str
    horizon: int
    parameters: dict = field(default_factory=dict)
    random_seed: int | None = None
    created_at: str = ""
    result_status: str = "NOT_RUN"
    result_reasons: tuple[str, ...] = ()
    metrics: dict = field(default_factory=dict)
    oos_used: bool = False
    research_reuse_warning: str = ""
    registry_version: str = EXPERIMENT_REGISTRY_VERSION

    def to_row(self) -> dict:
        """扁平化 CSV 行（复杂结构 JSON 序列化）。"""
        return {
            "experiment_id": self.experiment_id,
            "hypothesis_id": self.hypothesis_id,
            "git_sha": self.git_sha,
            "dataset_version": self.dataset_version,
            "universe_version": self.universe_version,
            "birth_model_version": self.birth_model_version,
            "factor_version": self.factor_version,
            "calibration_version": self.calibration_version,
            "split_version": self.split_version,
            "train_period": self.train_period,
            "validation_period": self.validation_period,
            "oos_period": self.oos_period,
            "horizon": self.horizon,
            "random_seed": self.random_seed,
            "created_at": self.created_at,
            "result_status": self.result_status,
            "oos_used": self.oos_used,
            "parameters": json.dumps(self.parameters, ensure_ascii=False, sort_keys=True),
            "result_reasons": json.dumps(list(self.result_reasons), ensure_ascii=False),
            "metrics": json.dumps(self.metrics, ensure_ascii=False, sort_keys=True),
            "research_reuse_warning": self.research_reuse_warning,
            "registry_version": self.registry_version,
        }


def new_experiment_id(hypothesis_id: str, birth_model: str = "", suffix: str = "") -> str:
    parts = ["OOS3D", hypothesis_id]
    if birth_model:
        parts.append(birth_model)
    if suffix:
        parts.append(suffix)
    return "--".join(parts)


def write_experiment_registry_csv(records: list[ExperimentRecord], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        if not records:
            handle.write("")
            return target
        writer = csv.DictWriter(handle, fieldnames=list(records[0].to_row()), lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_row())
    return target


def write_registry_json(payload: dict, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return target


def persist_experiments(records: list[ExperimentRecord]) -> int:
    """把实验记录写进已有的 ``backtest_experiment`` / ``backtest_result`` 表。

    复用现有表结构：``kind="oos"``、``name=hypothesis_id``、版本元数据进
    ``params_json``。**不新建表、不写迁移**。
    """
    from sqlalchemy import delete

    from src.db.base import get_session_factory
    from src.db.models import BacktestExperimentRow, BacktestResultRow

    factory = get_session_factory()
    written = 0
    with factory() as db:
        for record in records:
            experiment_id = record.experiment_id
            db.execute(delete(BacktestResultRow).where(
                BacktestResultRow.experiment_id == experiment_id
            ))
            existing = db.get(BacktestExperimentRow, experiment_id)
            params = {
                "hypothesis_id": record.hypothesis_id,
                "git_sha": record.git_sha,
                "dataset_version": record.dataset_version,
                "universe_version": record.universe_version,
                "birth_model_version": record.birth_model_version,
                "factor_version": record.factor_version,
                "calibration_version": record.calibration_version,
                "split_version": record.split_version,
                "train_period": record.train_period,
                "validation_period": record.validation_period,
                "oos_period": record.oos_period,
                "random_seed": record.random_seed,
                "oos_used": record.oos_used,
                "registry_version": record.registry_version,
                "result_reasons": list(record.result_reasons),
                "research_reuse_warning": record.research_reuse_warning,
                **{k: v for k, v in record.parameters.items()},
            }
            if existing is None:
                db.add(BacktestExperimentRow(
                    experiment_id=experiment_id,
                    kind="oos",
                    name=record.hypothesis_id,
                    factor_ids_json=[record.hypothesis_id],
                    logic=str(record.parameters.get("logic", "any")),
                    universe_json=record.parameters.get("birth_models"),
                    horizons_json=list(record.parameters.get("horizons", ())),
                    date_from=_parse_date(record.oos_period.split("..")[0]),
                    date_to=_parse_date(record.oos_period.split("..")[-1]),
                    benchmark_code=str(record.parameters.get("benchmark_code", "000300")),
                    params_json=params,
                    methodology=str(record.parameters.get("methodology", "")),
                    seed=record.random_seed,
                    status=record.result_status,
                ))
            else:
                existing.params_json = params
                existing.status = record.result_status
            db.add(BacktestResultRow(
                experiment_id=experiment_id,
                variant="oos_gate",
                horizon=int(record.horizon),
                sample_count=int(record.metrics.get("sample_count") or 0),
                up_rate=record.metrics.get("up_rate"),
                excess_up_rate=record.metrics.get("excess_up_rate"),
                mean_return=record.metrics.get("mean_return"),
                median_return=record.metrics.get("median_return"),
                std_return=record.metrics.get("std_return"),
                mean_excess_return=record.metrics.get("mean_excess_return"),
                max_drawdown=record.metrics.get("max_drawdown"),
                mean_max_return=record.metrics.get("mean_max_return"),
                extra_json={
                    "event_count": record.metrics.get("event_count"),
                    "cohen_d": record.metrics.get("cohen_d"),
                    "welch_p": record.metrics.get("welch_p"),
                    "permutation_p": record.metrics.get("permutation_p"),
                    "pending_fdr": record.metrics.get("pending_fdr"),
                    "gate_version": record.metrics.get("gate_version"),
                },
            ))
            written += 1
        db.commit()
    return written


def _parse_date(text: str):
    from datetime import date

    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


def utc_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


__all__ = [
    "COMBO_LOGICS",
    "DIRECTION_SOURCES",
    "EXPERIMENT_REGISTRY_VERSION",
    "EXPECTED_DIRECTIONS",
    "HYPOTHESIS_REGISTRY_VERSION",
    "RESEARCH_REUSE_WARNING",
    "ExperimentRecord",
    "HypothesisRegistry",
    "HypothesisSpec",
    "load_hypothesis_registry",
    "new_experiment_id",
    "persist_experiments",
    "utc_timestamp",
    "write_experiment_registry_csv",
    "write_registry_json",
]
