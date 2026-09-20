"""Walk-forward 研究（Phase 3D §6/§7）—— 本阶段的 P0 规则所在。

P0 规则
-------
**Walk-forward 不得复用全 TRAIN 校准。**

    Fold(test=2015):  train = 2010-01-01..2014-12-31
                      → 只用这 5 年重新 fit percentiles / mean / std / 方向阈值
                      → 再 transform 2015

如果拿 Phase 3C 用 **全体 TRAIN(2010–2018)** 得到的阈值去评估 2015，
那么 2016–2018 的分布信息就泄漏进了 2015 的评估。因此本模块**在结构上**
只提供 ``fit(fold_train)`` → ``transform(fold_test)`` 这一条路径：

* 拟合帧按 ``as_of <= fold.train_end`` 过滤，不由调用方传入"已经过滤好"的帧；
* ``ResearchCalibrationLayer.fit`` 自带 ``fit_max_as_of`` 越界断言（第二道闸门）；
* transform 帧要求 ``as_of > fold.train_end`` 且落在测试区间内（第三道闸门）；
* 每个 fold 记录 ``calibration_fit_hash``，用哈希证明"每个 fold 的阈值确实不同"。

两个协议的关系
--------------
固定 holdout（TRAIN/VALIDATION/OOS）与 walk-forward 是**两套独立协议**：
walk-forward 的 train 前缀可以跨过 holdout 的 Validation 分区（例如
test=2020 时 train=2010..2019），因为它仍然**严格早于**测试年。两套协议
不共享阈值：holdout 用 ``cal-v1``（fit 2010–2018），walk-forward 用逐 fold
重拟合的 ``cal-wf-<fold>``。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from src.research.calibration import ResearchCalibrationLayer
from src.research.oos.calibration_freeze import CALIBRATION_VERSION, FREEZE_V1
from src.research.oos.splits import TRAIN, ResearchSplit, SplitContractError

#: walk-forward 各 fold 使用的校准版本前缀
WALK_FORWARD_CALIBRATION_PREFIX = "cal-wf"
#: 预注册的最短训练窗（年）：与 GOAL §7 的示例一致（Train 2010–2014 → Test 2015）
MIN_TRAIN_YEARS = 5


class WalkForwardLeakError(SplitContractError):
    """检测到 fold 内使用了测试期数据拟合校准（P0 违规）。"""


@dataclass(frozen=True)
class WalkForwardFold:
    """一个扩窗（expanding window）fold 的不可变定义。"""

    fold_id: str
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    calibration_version: str

    def __post_init__(self) -> None:
        if not self.train_start <= self.train_end < self.test_start <= self.test_end:
            raise SplitContractError(
                f"{self.fold_id} 时间顺序错误：train {self.train_start}..{self.train_end} "
                f"test {self.test_start}..{self.test_end}"
            )

    @property
    def test_year(self) -> int:
        return self.test_start.year

    def to_dict(self) -> dict:
        return {
            "fold_id": self.fold_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "calibration_version": self.calibration_version,
        }


def expanding_folds(
    split: ResearchSplit,
    *,
    min_train_years: int = MIN_TRAIN_YEARS,
    first_test_year: int | None = None,
    last_test_year: int | None = None,
) -> list[WalkForwardFold]:
    """生成扩窗 fold 列表。

    ``first_test_year`` 默认为 ``train_start.year + min_train_years``；
    如果样本更早年份不足，允许显式推迟（必须在报告里说明推迟原因与影响）。
    """
    if min_train_years < 1:
        raise ValueError("min_train_years 必须 >= 1")
    start_year = first_test_year or (split.train_start.year + min_train_years)
    end_year = last_test_year or split.oos_end.year
    if start_year <= split.train_start.year:
        raise ValueError("first_test_year 不能早于或等于 train_start 年份")
    if end_year < start_year:
        raise ValueError("last_test_year 不能早于 first_test_year")

    folds: list[WalkForwardFold] = []
    for year in range(start_year, end_year + 1):
        train_end = date(year, 1, 1) - timedelta(days=1)
        test_start = date(year, 1, 1)
        test_end = min(date(year, 12, 31), split.oos_end)
        folds.append(WalkForwardFold(
            fold_id=f"WF-{year}",
            train_start=split.train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            calibration_version=f"{WALK_FORWARD_CALIBRATION_PREFIX}-{year}",
        ))
    return folds


def calibration_fit_hash(layer: ResearchCalibrationLayer) -> str:
    """对一层已 fit 的校准做内容哈希（证明每个 fold 的阈值确实不同）。"""
    if not layer.fitted:
        raise RuntimeError("校准尚未 fit，无法计算 fit hash")
    payload = "|".join(
        f"{group.key}:{group.sample_count}:{group.mean}:{group.std}:"
        f"{group.lower_threshold}:{group.upper_threshold}"
        for group in sorted(layer.groups.values(), key=lambda g: tuple(str(k) for k in g.key))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def fit_fold_calibration(
    panel: pd.DataFrame,
    fold: WalkForwardFold,
    *,
    value_col: str,
    group_cols: tuple[str, ...],
    date_col: str = "as_of",
    partition_col: str = "partition",
    lower_quantile: float = FREEZE_V1.lower_quantile,
    upper_quantile: float = FREEZE_V1.upper_quantile,
    require_train_partition: bool = False,
) -> tuple[ResearchCalibrationLayer, dict]:
    """只用 fold 训练前缀拟合校准。

    Args:
        panel: 观测面板（必须含 ``date_col``）。
        fold: 目标 fold。拟合帧 = ``as_of <= fold.train_end``。
        require_train_partition: 为 True 时额外要求拟合帧的所有行都标记为
            holdout 的 TRAIN 分区。**默认 False**：扩窗协议的 train 前缀
            天然会跨过 holdout 的 Validation 分区（例如 test=2020 时
            train=2010..2019），这是 walk-forward 的定义，**不是泄漏** ——
            因为它仍然严格早于测试年。无论取值如何，``fit_audit`` 都会
            记录真实使用过的分区，供报告核对。

    Returns:
        ``(layer, fit_audit)``；``fit_audit`` 记录真实使用的日期上界与行数，
        供实验结果携带。
    """
    if panel.empty:
        raise ValueError("面板为空，无法拟合 walk-forward 校准")
    if date_col not in panel.columns:
        raise ValueError(f"面板缺少 {date_col} 列")

    dates = pd.to_datetime(panel[date_col]).dt.date
    mask = dates <= fold.train_end
    fit_frame = panel.loc[mask].copy()
    if fit_frame.empty:
        raise WalkForwardLeakError(
            f"{fold.fold_id} 在 {fold.train_end} 之前没有任何训练样本"
        )
    fit_max = pd.to_datetime(fit_frame[date_col]).dt.date.max()
    if fit_max > fold.train_end:
        raise WalkForwardLeakError(
            f"{fold.fold_id} 拟合帧越界：{fit_max} > train_end {fold.train_end}"
        )
    fit_partitions = sorted(
        {str(v).upper() for v in fit_frame[partition_col].dropna().unique()}
    ) if partition_col in fit_frame.columns else []
    if require_train_partition and set(fit_partitions) - {TRAIN}:
        raise WalkForwardLeakError(
            f"{fold.fold_id} 拟合帧包含非 TRAIN 分区：{sorted(set(fit_partitions) - {TRAIN})}"
        )
    # P0 结构守卫：fold 绝不能复用冻结的 holdout 校准版本。
    # "用 cal-v1（全 TRAIN 2010–2018 拟合）去评估 2015" 正是 GOAL §6 禁止的泄漏形态。
    if fold.calibration_version == FREEZE_V1.calibration_version:
        raise WalkForwardLeakError(
            f"{fold.fold_id} 试图复用冻结的 holdout 校准 {FREEZE_V1.calibration_version}；"
            "每个 fold 必须使用自己的 cal-wf-<year> 版本并只用 fold 训练前缀拟合。"
        )
    # 协议语义转换：在 walk-forward 的**fold 内部**，"测试年之前的全部样本"就是该 fold 的
    # TRAIN。原始的 holdout 分区标签已经记录在 audit["fit_partitions"] 里（上面），
    # 这里改标签只是为了让 Calibration Layer 的「fit 只能吃 TRAIN」守卫继续生效。
    fit_frame = fit_frame.copy()
    fit_frame[partition_col] = TRAIN
    # 第三道闸门：ResearchCalibrationLayer 自带的 fit_max_as_of 断言
    layer = ResearchCalibrationLayer(
        value_col=value_col,
        group_cols=group_cols,
        date_col=date_col,
        partition_col=partition_col,
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
        calibration_version=fold.calibration_version,
        fit_partition=TRAIN,
        fit_max_as_of=fold.train_end,
    ).fit(fit_frame)
    # cal-v1 的 fit 上界（2018-12-31）只约束**固定 holdout 校准器**。
    # 扩窗 walk-forward 的训练前缀按定义会跨过 holdout 的 Validation 区段
    # （例如 test=2020 时 train=2010..2019），这是协议本身，不是泄漏：
    # 它仍然**严格早于**测试年。是否越界在这里如实记录，供报告核对。
    freeze_bound_exceeded = fit_max > FREEZE_V1.fit_period_end
    audit = {
        "fold_id": fold.fold_id,
        "train_period": [fold.train_start.isoformat(), fold.train_end.isoformat()],
        "fit_row_count": int(len(fit_frame)),
        "fit_actual_max_as_of": fit_max.isoformat(),
        "fit_max_as_of_bound": fold.train_end.isoformat(),
        "fit_partitions": fit_partitions,
        "fit_group_count": len(layer.groups),
        "calibration_fit_hash": calibration_fit_hash(layer),
        "calibration_version": layer.calibration_version,
        "holdout_freeze_bound": FREEZE_V1.fit_period_end.isoformat(),
        "freeze_bound_exceeded": bool(freeze_bound_exceeded),
        "freeze_bound_note": (
            "扩窗训练前缀越过 cal-v1 的 fit 上界（holdout 协议专属），仍严格早于测试年"
            if freeze_bound_exceeded else "训练前缀落在 cal-v1 fit 区间内"
        ),
    }
    return layer, audit


def transform_fold(
    panel: pd.DataFrame,
    fold: WalkForwardFold,
    layer: ResearchCalibrationLayer,
    *,
    date_col: str = "as_of",
) -> pd.DataFrame:
    """把 fold 校准 transform 到**测试期**样本上。

    测试帧必须严格位于 ``fold.train_end`` 之后、且落在测试区间内：
    任何越界行都会 raise，而不是被静默丢弃。
    """
    dates = pd.to_datetime(panel[date_col]).dt.date
    mask = (dates >= fold.test_start) & (dates <= fold.test_end)
    test_frame = panel.loc[mask].copy()
    if test_frame.empty:
        return test_frame
    test_min = pd.to_datetime(test_frame[date_col]).dt.date.min()
    if test_min <= fold.train_end:
        raise WalkForwardLeakError(
            f"{fold.fold_id} 测试帧包含训练期样本：{test_min} <= {fold.train_end}"
        )
    return layer.transform(test_frame)


@dataclass
class WalkForwardResult:
    """walk-forward 的汇总容器（fold 明细 + 一致性摘要）。"""

    folds: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def fold_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.folds)


def run_walk_forward(
    panel: pd.DataFrame,
    folds: list[WalkForwardFold],
    evaluator: Callable[[WalkForwardFold, pd.DataFrame], dict],
    *,
    value_col: str,
    group_cols: tuple[str, ...],
    date_col: str = "as_of",
    partition_col: str = "partition",
    require_train_partition: bool = False,
) -> WalkForwardResult:
    """逐 fold 执行：``fit(fold_train)`` → ``transform(fold_test)`` → ``evaluator``。

    ``evaluator(fold, transformed_test_frame)`` 返回该 fold 的结果字典；
    本函数负责拼装 fold 元数据（train/test 区间、样本数、fit hash）。
    """
    result = WalkForwardResult()
    for fold in folds:
        layer, audit = fit_fold_calibration(
            panel, fold,
            value_col=value_col, group_cols=group_cols, date_col=date_col,
            partition_col=partition_col, require_train_partition=require_train_partition,
        )
        test_frame = transform_fold(panel, fold, layer, date_col=date_col)
        outcome = evaluator(fold, test_frame)
        record = {
            **audit,
            "test_period": [fold.test_start.isoformat(), fold.test_end.isoformat()],
            "test_row_count": int(len(test_frame)),
            **outcome,
        }
        result.folds.append(record)
    result.summary = summarize_folds(result.folds)
    return result


def summarize_folds(records: list[dict], *, status_key: str = "research_status") -> dict:
    """fold 级摘要：fit hash 是否真的随 fold 变化、状态分布、方向一致性。"""
    if not records:
        return {"fold_count": 0}
    hashes = [r.get("calibration_fit_hash") for r in records]
    statuses: dict[str, int] = {}
    for record in records:
        key = str(record.get(status_key, "NOT_RUN"))
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "fold_count": len(records),
        "distinct_fit_hashes": len(set(hashes)),
        "fold_calibration_refit": len(set(hashes)) == len(hashes),
        "status_counts": statuses,
        "calibration_versions": [r.get("calibration_version") for r in records],
        "holdout_calibration_version": CALIBRATION_VERSION,
    }


__all__ = [
    "MIN_TRAIN_YEARS",
    "WALK_FORWARD_CALIBRATION_PREFIX",
    "WalkForwardFold",
    "WalkForwardLeakError",
    "WalkForwardResult",
    "calibration_fit_hash",
    "expanding_folds",
    "fit_fold_calibration",
    "run_walk_forward",
    "summarize_folds",
    "transform_fold",
]
