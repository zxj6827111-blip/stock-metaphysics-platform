"""Phase 3D：ResearchSplit 契约（固定 holdout 切分 + 版本冻结）。

为什么需要这个模块
------------------
研究里最容易犯的错误不是算错公式，而是**把不同阶段的结果混在一起**：
用 Validation 调过阈值、又在 OOS 上报告同一阈值的结果；或者反过来，把
Walk-forward 的测试年当作"从未看过"。本模块把切分**写成不可变契约**，
让每个实验都能声明自己属于哪个分区、用的是哪一版快照/宇宙/校准。

硬性纪律
--------
* 时间顺序**不得反转**：``train_end < validation_start <= validation_end < oos_start``。
  没有随机切分，也没有"打乱日期后抽样"。
* 分区由**日历**决定，与行情、收益、标签无关 —— 因此切分本身不会泄漏未来信息。
* 每条结果都必须携带 ``split_version``；改动切分必须新建版本号，
  旧版本号下的实验不得被静默重解释。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

from src.research.labels.horizon_returns import (
    HORIZONS,
    LABEL_VERSION,
    PRIMARY_HORIZON,
)

#: 本阶段固定的切分版本号（GOAL §5）
SPLIT_VERSION = "phase3-oos-v1"
#: 主数据快照（ADR-0012 canonical）
DATASET_VERSION = "phase3a_astockdata_cutoff_20260814"
#: Point-in-Time Universe（Phase 3A）
UNIVERSE_VERSION = "v2-phase3a"
#: 主面板采样步长（月）。3 = 季度：对 20D/60D 窗口天然非重叠。
SAMPLE_STEP_MONTHS = 3
#: as_of 采用的时刻（收盘后），与 Phase 3C 保持一致
AS_OF_HOUR = 15

TRAIN = "TRAIN"
VALIDATION = "VALIDATION"
OOS = "OOS"
OUT_OF_SCOPE = "OUT_OF_SCOPE"

#: 允许出现在研究输入里的分区名（OUT_OF_SCOPE 不得进入任何统计）
RESEARCH_PARTITIONS: tuple[str, ...] = (TRAIN, VALIDATION, OOS)


class SplitContractError(ValueError):
    """切分契约被破坏（时间反转、分区重叠、越界读取）。"""


@dataclass(frozen=True)
class ResearchSplit:
    """Train / Validation / OOS 的固定切分契约。

    ``oos_end`` 是本快照的数据截止日；OOS 区间是**描述性**的，
    不代表"OOS 期间没有任何决策"—— 决策记录在 ``oos_labels_seen`` /
    ``oos_used`` 上，见 ``calibration_freeze`` 与实验登记。
    """

    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    oos_start: date
    oos_end: date
    dataset_version: str = DATASET_VERSION
    universe_version: str = UNIVERSE_VERSION
    calibration_version: str = ""
    label_version: str = LABEL_VERSION
    split_version: str = SPLIT_VERSION
    primary_horizon: int = PRIMARY_HORIZON
    horizons: tuple[int, ...] = HORIZONS
    sample_step_months: int = SAMPLE_STEP_MONTHS
    as_of_hour: int = AS_OF_HOUR
    #: 该切分是否已被真实读取过 OOS 标签（写入实验元数据，只增不减）
    oos_labels_seen: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.train_start <= self.train_end:
            raise SplitContractError("train_start 必须早于或等于 train_end")
        if not self.train_end < self.validation_start:
            raise SplitContractError(
                "train_end 必须严格早于 validation_start（禁止时间方向反转）"
            )
        if not self.validation_start <= self.validation_end:
            raise SplitContractError("validation_start 必须早于或等于 validation_end")
        if not self.validation_end < self.oos_start:
            raise SplitContractError(
                "validation_end 必须严格早于 oos_start（禁止 Validation 与 OOS 重叠）"
            )
        if not self.oos_start <= self.oos_end:
            raise SplitContractError("oos_start 必须早于或等于 oos_end")
        if self.primary_horizon not in self.horizons:
            raise SplitContractError("primary_horizon 必须包含在 horizons 中")

    # ------------------------------------------------------------------
    def partition_of(self, value: date) -> str:
        """把任意日期映射到分区。区间外的日期是 ``OUT_OF_SCOPE``，不参与研究。"""
        if self.train_start <= value <= self.train_end:
            return TRAIN
        if self.validation_start <= value <= self.validation_end:
            return VALIDATION
        if self.oos_start <= value <= self.oos_end:
            return OOS
        return OUT_OF_SCOPE

    def bounds(self, partition: str) -> tuple[date, date]:
        name = partition.upper()
        if name == TRAIN:
            return self.train_start, self.train_end
        if name == VALIDATION:
            return self.validation_start, self.validation_end
        if name == OOS:
            return self.oos_start, self.oos_end
        raise SplitContractError(f"未知分区：{partition}")

    def contains(self, partition: str, value: date) -> bool:
        start, end = self.bounds(partition)
        return start <= value <= end

    def assert_partition(self, partition: str, values: list[date]) -> None:
        """断言一组日期全部落在指定分区内。越界即 raise（绝不静默丢弃）。"""
        start, end = self.bounds(partition)
        offenders = [v for v in values if not start <= v <= end]
        if offenders:
            raise SplitContractError(
                f"{partition} 分区越界读取：{min(offenders)}..{max(offenders)} "
                f"（允许范围 {start}..{end}）"
            )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """稳定序列化（用于元数据、指纹与报告）。"""
        return {
            "split_version": self.split_version,
            "dataset_version": self.dataset_version,
            "universe_version": self.universe_version,
            "calibration_version": self.calibration_version,
            "label_version": self.label_version,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "oos_start": self.oos_start.isoformat(),
            "oos_end": self.oos_end.isoformat(),
            "primary_horizon": self.primary_horizon,
            "horizons": list(self.horizons),
            "sample_step_months": self.sample_step_months,
            "as_of_hour": self.as_of_hour,
            "oos_labels_seen": self.oos_labels_seen,
            "notes": list(self.notes),
        }

    def fingerprint(self) -> str:
        """切分指纹：任何版本字段或区间改动都会改变它。"""
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def with_oos_used(self, *, notes: str = "") -> ResearchSplit:
        """标记"OOS 标签已被读取"，返回新实例（原实例不可变）。"""
        extra = tuple(self.notes) + ((notes,) if notes else ())
        return ResearchSplit(
            train_start=self.train_start, train_end=self.train_end,
            validation_start=self.validation_start, validation_end=self.validation_end,
            oos_start=self.oos_start, oos_end=self.oos_end,
            dataset_version=self.dataset_version, universe_version=self.universe_version,
            calibration_version=self.calibration_version, label_version=self.label_version,
            split_version=self.split_version, primary_horizon=self.primary_horizon,
            horizons=self.horizons, sample_step_months=self.sample_step_months,
            as_of_hour=self.as_of_hour, oos_labels_seen=True, notes=extra,
        )


def default_split(*, calibration_version: str) -> ResearchSplit:
    """Phase 3D 的默认切分（GOAL §3）。"""
    return ResearchSplit(
        train_start=date(2010, 1, 1),
        train_end=date(2018, 12, 31),
        validation_start=date(2019, 1, 1),
        validation_end=date(2022, 12, 31),
        oos_start=date(2023, 1, 1),
        oos_end=date(2026, 8, 14),
        calibration_version=calibration_version,
        notes=(
            "OOS 上界 = AStockData 快照截止日（2026-08-14），并非「研究结束」；"
            "任何早于该日的标签都存在，必须按预注册协议一次性读取。",
        ),
    )


__all__ = [
    "AS_OF_HOUR",
    "DATASET_VERSION",
    "HORIZONS",
    "LABEL_VERSION",
    "OOS",
    "OUT_OF_SCOPE",
    "PRIMARY_HORIZON",
    "RESEARCH_PARTITIONS",
    "SAMPLE_STEP_MONTHS",
    "SPLIT_VERSION",
    "TRAIN",
    "UNIVERSE_VERSION",
    "VALIDATION",
    "ResearchSplit",
    "SplitContractError",
    "default_split",
]
