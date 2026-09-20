"""Calibration V1 冻结声明（Phase 3D 第一节）。

背景
----
Phase 3C 已经"看过" TRAIN / Validation / OOS 的**特征分布**，但没有读取任何
未来收益标签，也没有用 Validation / OOS 的分布调整过阈值。Phase 3D 从第一次
读取 OOS 收益开始，必须把当时的校准状态**冻结**下来：

    冻结前：阈值只由 TRAIN 分布决定（已经如此）
    冻结后：任何对 P25/P75、z-score baseline、rank mapping、方向阈值的改动，
            都必须新建 ``cal-v2`` 并重新定义 OOS 协议；不得静默覆盖 ``cal-v1``。

本模块只做两件事：**声明冻结内容** + **提供断言**（防止某次运行不小心用
Validation/OOS 重新拟合）。它不参与任何计算。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.research.calibration import (
    CALIBRATION_VERSION as LAYER_VERSION,
)
from src.research.calibration import (
    DEFAULT_LOWER_QUANTILE,
    DEFAULT_UPPER_QUANTILE,
)

#: Phase 3D 研究口径下的校准版本号（等价于仓库既有的 ``research-calibration-v1``）
CALIBRATION_VERSION = "cal-v1"
#: 冻结记录自身的版本号
FREEZE_VERSION = "calibration-freeze-v1"
#: 允许 fit 的最大 as_of 之外的分区名（唯一合法 fit 分区）
FIT_SCOPE = "TRAIN_ONLY"


class CalibrationFreezeError(RuntimeError):
    """校准冻结被破坏：检测到用非 TRAIN 数据拟合，或用超期数据拟合。"""


@dataclass(frozen=True)
class CalibrationFreeze:
    """一份不可变的校准冻结记录。"""

    calibration_version: str
    layer_version: str
    fit_period_start: date
    fit_period_end: date
    fit_scope: str
    lower_quantile: float
    upper_quantile: float
    oos_labels_seen: bool
    frozen_at: str
    freeze_version: str = FREEZE_VERSION
    notes: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    def assert_fit_within_train(self, *, fit_max_as_of: date) -> None:
        """「fit 只允许使用 TRAIN 及其子区间」的硬断言。

        Walk-forward 每个 fold 用的是 TRAIN 的**前缀**（更早的终点），
        因此这里只禁止"越过 TRAIN 终点"，不要求等于终点。
        """
        if fit_max_as_of > self.fit_period_end:
            raise CalibrationFreezeError(
                f"{self.calibration_version} 只允许在 {self.fit_period_start}..{self.fit_period_end} "
                f"内拟合；实际 fit 用到 {fit_max_as_of}。"
                "如需改变口径，必须新建 cal-v2 并重定义 OOS 协议。"
            )
        if fit_max_as_of < self.fit_period_start:
            raise CalibrationFreezeError(
                f"fit_max_as_of={fit_max_as_of} 早于 fit 起点 {self.fit_period_start}，契约异常"
            )

    def assert_partition(self, partition: str) -> None:
        if str(partition).upper() != self.fit_scope:
            raise CalibrationFreezeError(
                f"{self.calibration_version} 只允许在 {self.fit_scope} 上拟合，"
                f"实际分区为 {partition}"
            )

    def assert_holdout_fit(self, *, fit_max_as_of: date, target_partition: str) -> None:
        """固定 holdout 运行时的额外断言。

        注意：采样是**离散网格**（例如季度采样），因此 fit 实际用到的最后一个
        ``as_of`` 允许早于 ``fit_period_end``（2018-12-31 落在网格之外是正常的），
        但**绝不允许越界**。实际滞后天数会写入审计记录，供报告披露。
        """
        self.assert_partition(self.fit_scope)
        self.assert_fit_within_train(fit_max_as_of=fit_max_as_of)
        if str(target_partition).upper() not in {"VALIDATION", "OOS"}:
            raise CalibrationFreezeError(
                f"holdout 目标分区只能是 VALIDATION / OOS，实际为 {target_partition}"
            )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "freeze_version": self.freeze_version,
            "calibration_version": self.calibration_version,
            "layer_version": self.layer_version,
            "fit_period": [self.fit_period_start.isoformat(), self.fit_period_end.isoformat()],
            "fit_scope": self.fit_scope,
            "lower_quantile": self.lower_quantile,
            "upper_quantile": self.upper_quantile,
            "oos_labels_seen": self.oos_labels_seen,
            "frozen_at": self.frozen_at,
            "notes": list(self.notes),
        }


#: Phase 3D 使用的冻结实例。``oos_labels_seen=False`` 表示：冻结声明写入时，
#: 本项目的任何研究流程都还没有读取过 OOS 收益标签。
FREEZE_V1 = CalibrationFreeze(
    calibration_version=CALIBRATION_VERSION,
    layer_version=LAYER_VERSION,
    fit_period_start=date(2010, 1, 1),
    fit_period_end=date(2018, 12, 31),
    fit_scope=FIT_SCOPE,
    lower_quantile=DEFAULT_LOWER_QUANTILE,
    upper_quantile=DEFAULT_UPPER_QUANTILE,
    oos_labels_seen=False,
    frozen_at="2026-09-20",
    notes=(
        "Phase 3C 只审计了特征/Opinion 分布，未读取未来收益标签。",
        "冻结内容：P25/P75 方向阈值、z-score 的均值/标准差、经验分位参考分布。",
        "任何修改必须新建 cal-v2 并重定义 OOS 协议；不得静默覆盖 cal-v1。",
    ),
)

#: 便于外部按版本号取用
FREEZES: dict[str, CalibrationFreeze] = {FREEZE_V1.calibration_version: FREEZE_V1}


def freeze_for(calibration_version: str) -> CalibrationFreeze:
    try:
        return FREEZES[calibration_version]
    except KeyError as exc:  # pragma: no cover - 版本号写错时立刻失败
        raise CalibrationFreezeError(
            f"未知校准版本 {calibration_version!r}；已知：{sorted(FREEZES)}"
        ) from exc


__all__ = [
    "CALIBRATION_VERSION",
    "FIT_SCOPE",
    "FREEZES",
    "FREEZE_V1",
    "FREEZE_VERSION",
    "CalibrationFreeze",
    "CalibrationFreezeError",
    "freeze_for",
]
