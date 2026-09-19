"""独立的 Research Calibration Layer。

本模块只处理研究变量的分布重表达，不参与运行时排盘、Opinion 聚合或标签计算。
所有拟合统计量都必须来自显式标记为 ``TRAIN`` 的行；Validation/OOS 只能调用
``transform``，不能改变已冻结的参考分布。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite, sqrt

import numpy as np
import pandas as pd

CALIBRATION_VERSION = "research-calibration-v1"
DEFAULT_LOWER_QUANTILE = 0.25
DEFAULT_UPPER_QUANTILE = 0.75

# Calibration fit 明确拒绝标签/未来字段。这里采用字段名守卫，而不是依赖调用方自觉。
_FORBIDDEN_FIT_TOKENS = (
    "ret_",
    "return",
    "label",
    "future",
    "forward",
    "target",
    "bench_",
    "drawdown",
    "max_return",
)


def _finite(value: object) -> bool:
    try:
        return value is not None and isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _clean(values: Sequence[object]) -> list[float]:
    return [float(value) for value in values if _finite(value)]


def research_percentile(value: float | None, reference: Sequence[object]) -> float | None:
    """返回相对于 ``reference`` 的经验分位数（并列值取平均秩）。

    采用 ``(小于值的数量 + 0.5 * 等于值的数量) / n``，因此结果位于
    ``(0, 1)``；缺失值、非有限值或空参考分布统一返回 ``None``。
    """
    if not _finite(value):
        return None
    ref = _clean(reference)
    if not ref:
        return None
    numeric = float(value)
    less = sum(1 for item in ref if item < numeric)
    equal = sum(1 for item in ref if item == numeric)
    return round((less + 0.5 * equal) / len(ref), 12)


def cross_sectional_percentile(values: Sequence[object]) -> list[float | None]:
    """在一个当前横截面内计算逐项经验分位数，保持输入顺序。"""
    ref = _clean(values)
    return [research_percentile(float(value), ref) if _finite(value) else None for value in values]


def historical_percentile(value: float | None, train_reference: Sequence[object]) -> float | None:
    """相对于冻结 TRAIN 分布的历史分位数。"""
    return research_percentile(value, train_reference)


def z_score(value: float | None, reference: Sequence[object]) -> float | None:
    """使用参考分布的总体均值/标准差计算 z-score。

    参考分布为常量时返回 ``None``，避免把不可辨识的标准化结果伪装成 0。
    """
    if not _finite(value):
        return None
    ref = _clean(reference)
    if len(ref) < 2:
        return None
    mean = sum(ref) / len(ref)
    variance = sum((item - mean) ** 2 for item in ref) / len(ref)
    std = sqrt(variance)
    if std == 0.0:
        return None
    return round((float(value) - mean) / std, 12)


def rank_score(percentile: float | None) -> float | None:
    """把研究分位数映射为独立的 0-100 rank score。"""
    if percentile is None or not _finite(percentile):
        return None
    return round(max(0.0, min(1.0, float(percentile))) * 100.0, 6)


@dataclass(frozen=True)
class CalibrationGroup:
    """一个 TRAIN 分组的冻结统计量。"""

    key: tuple[object, ...]
    sample_count: int
    mean: float | None
    std: float | None
    lower_threshold: float | None
    upper_threshold: float | None
    reference: tuple[float, ...] = field(repr=False)

    @property
    def usable(self) -> bool:
        return (
            bool(self.reference)
            and self.std is not None
            and self.std > 0.0
            and self.lower_threshold is not None
            and self.upper_threshold is not None
        )


@dataclass
class ResearchCalibrationLayer:
    """按研究变量分组冻结 TRAIN 统计量，再对任意分区做非破坏性变换。

    ``group_cols`` 必须包含能区分研究变量语义的键，例如
    ``("engine", "birth_model")`` 或 ``("engine", "birth_model", "factor_id")``。
    """

    value_col: str
    group_cols: tuple[str, ...]
    date_col: str = "as_of"
    partition_col: str = "partition"
    lower_quantile: float = DEFAULT_LOWER_QUANTILE
    upper_quantile: float = DEFAULT_UPPER_QUANTILE
    calibration_version: str = CALIBRATION_VERSION
    fit_partition: str = "TRAIN"
    fit_max_as_of: date | datetime | None = None
    groups: dict[tuple[object, ...], CalibrationGroup] = field(default_factory=dict)
    fitted: bool = False

    def __post_init__(self) -> None:
        if not self.value_col:
            raise ValueError("value_col 不能为空")
        if not self.group_cols:
            raise ValueError("group_cols 不能为空，Calibration 必须显式分组")
        if not 0.0 <= self.lower_quantile < self.upper_quantile <= 1.0:
            raise ValueError("分位点必须满足 0 <= lower < upper <= 1")

    def fit(self, frame: pd.DataFrame) -> ResearchCalibrationLayer:
        """只用 TRAIN 行拟合并冻结统计量。"""
        self._validate_common_columns(frame)
        self._reject_future_columns(frame)
        if self.partition_col not in frame.columns:
            raise ValueError(f"Calibration fit 必须包含 {self.partition_col} 列并显式标记 TRAIN")
        partitions = {str(value).upper() for value in frame[self.partition_col].dropna().unique()}
        if partitions != {self.fit_partition.upper()}:
            raise ValueError(
                f"Calibration fit 只能使用 {self.fit_partition}，实际分区为 {sorted(partitions)}"
            )

        dates = pd.to_datetime(frame[self.date_col], errors="coerce")
        if dates.isna().any():
            raise ValueError(f"{self.date_col} 含无法解析的日期")
        max_date = dates.max().to_pydatetime()
        max_allowed = self._as_datetime(self.fit_max_as_of) if self.fit_max_as_of is not None else None
        if max_allowed is not None and max_date > max_allowed:
            raise ValueError(
                f"Calibration fit 使用了超过 fit_max_as_of={max_allowed.date()} 的样本：{max_date.date()}"
            )
        self.fit_max_as_of = max_allowed.date() if max_allowed is not None else max_date.date()

        self.groups = {}
        for key, sub in frame.groupby(list(self.group_cols), dropna=False, sort=True):
            normalized_key = key if isinstance(key, tuple) else (key,)
            values = tuple(_clean(sub[self.value_col].tolist()))
            if not values:
                self.groups[normalized_key] = CalibrationGroup(
                    key=normalized_key, sample_count=0, mean=None, std=None,
                    lower_threshold=None, upper_threshold=None, reference=(),
                )
                continue
            mean = sum(values) / len(values)
            variance = sum((item - mean) ** 2 for item in values) / len(values)
            sorted_values = sorted(values)
            self.groups[normalized_key] = CalibrationGroup(
                key=normalized_key,
                sample_count=len(values),
                mean=round(mean, 12),
                std=round(sqrt(variance), 12),
                lower_threshold=round(self._quantile(sorted_values, self.lower_quantile), 12),
                upper_threshold=round(self._quantile(sorted_values, self.upper_quantile), 12),
                reference=values,
            )
        self.fitted = True
        return self

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """追加研究派生列，绝不覆盖输入 DataFrame 或原始字段。"""
        if not self.fitted:
            raise RuntimeError("Calibration Layer 尚未 fit")
        self._validate_common_columns(frame)
        self._reject_future_columns(frame)
        out = frame.copy(deep=True)
        out["research_percentile"] = np.nan
        out["cross_sectional_percentile"] = np.nan
        out["historical_percentile"] = np.nan
        out["z_score"] = np.nan
        out["rank_score"] = np.nan
        out["calibrated_direction"] = np.nan
        out["calibration_status"] = "unavailable"

        numeric = pd.to_numeric(out[self.value_col], errors="coerce")
        valid = numeric.notna()
        if not valid.any():
            return out

        # 当前横截面分位：只在 transform 批次内计算，不参与 fit。
        cross_keys = [*self.group_cols, self.date_col]
        cross_frame = out.loc[valid, cross_keys].copy()
        cross_frame["__value"] = numeric.loc[valid].to_numpy(dtype=float)
        cross_frame["__row"] = cross_frame.index
        cross_percentiles = np.full(len(out), np.nan, dtype=float)
        for _key, group in cross_frame.groupby(cross_keys, sort=False, dropna=False):
            values = group["__value"].to_numpy(dtype=float)
            order = np.argsort(values, kind="mergesort")
            sorted_values = values[order]
            less = np.searchsorted(sorted_values, values, side="left")
            right = np.searchsorted(sorted_values, values, side="right")
            percentiles = (less + 0.5 * (right - less)) / len(values)
            cross_percentiles[group["__row"].to_numpy(dtype=int)] = percentiles
        out["cross_sectional_percentile"] = cross_percentiles

        # TRAIN 统计量按 group key 映射到整批数据；避免对每行调用 Python 函数。
        group_keys = list(zip(*(out[column].tolist() for column in self.group_cols), strict=True))
        references = [self.groups.get(key) for key in group_keys]
        usable = np.asarray([
            group is not None and bool(group.reference) for group in references
        ], dtype=bool) & valid.to_numpy()
        if not usable.any():
            return out

        values = numeric.to_numpy(dtype=float)
        hist = np.full(len(out), np.nan, dtype=float)
        zscores = np.full(len(out), np.nan, dtype=float)
        lower = np.full(len(out), np.nan, dtype=float)
        upper = np.full(len(out), np.nan, dtype=float)
        usable_group = np.zeros(len(out), dtype=bool)
        for key, indices in out.groupby(list(self.group_cols), sort=False, dropna=False).groups.items():
            normalized_key = key if isinstance(key, tuple) else (key,)
            group = self.groups.get(normalized_key)
            if group is None or not group.reference:
                continue
            idx = np.asarray(list(indices), dtype=int)
            idx = idx[valid.iloc[idx].to_numpy()]
            if not len(idx):
                continue
            reference = np.asarray(group.reference, dtype=float)
            vals = values[idx]
            less = (reference[None, :] < vals[:, None]).sum(axis=1)
            equal = (reference[None, :] == vals[:, None]).sum(axis=1)
            hist[idx] = (less + 0.5 * equal) / len(reference)
            if group.std is not None and group.std > 0:
                zscores[idx] = (vals - float(group.mean)) / float(group.std)
                lower[idx] = float(group.lower_threshold)
                upper[idx] = float(group.upper_threshold)
                usable_group[idx] = True

        out["research_percentile"] = hist
        out["historical_percentile"] = hist
        out["z_score"] = zscores
        out["rank_score"] = np.where(np.isnan(hist), np.nan, np.clip(hist, 0.0, 1.0) * 100.0)
        out.loc[valid, "calibration_status"] = "unavailable_constant_train"
        out.loc[usable_group, "calibration_status"] = "ok"
        direction = np.where(values < lower, -1.0, np.where(values > upper, 1.0, 0.0))
        out.loc[usable_group, "calibrated_direction"] = direction[usable_group]
        return out

    def metadata(self) -> dict:
        """返回可写入研究报告的版本与 fit 摘要。"""
        return {
            "calibration_version": self.calibration_version,
            "fit_partition": self.fit_partition,
            "fit_max_as_of": self.fit_max_as_of.isoformat() if self.fit_max_as_of else None,
            "value_col": self.value_col,
            "group_cols": list(self.group_cols),
            "lower_quantile": self.lower_quantile,
            "upper_quantile": self.upper_quantile,
            "group_count": len(self.groups),
            "groups": [
                {
                    "key": list(group.key),
                    "sample_count": group.sample_count,
                    "mean": group.mean,
                    "std": group.std,
                    "lower_threshold": group.lower_threshold,
                    "upper_threshold": group.upper_threshold,
                }
                for group in self.groups.values()
            ],
        }

    def _validate_common_columns(self, frame: pd.DataFrame) -> None:
        required = {self.value_col, self.date_col, *self.group_cols}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"Calibration 缺少字段: {missing}")

    @staticmethod
    def _reject_future_columns(frame: pd.DataFrame) -> None:
        forbidden = [
            column for column in frame.columns
            if any(token in str(column).lower() for token in _FORBIDDEN_FIT_TOKENS)
        ]
        # partition/as_of 是研究元数据，不是未来标签；其它字段命中即拒绝。
        forbidden = [column for column in forbidden if str(column).lower() not in {"as_of", "partition"}]
        if forbidden:
            raise ValueError(
                "Calibration 输入不得包含未来标签/收益字段：" + ", ".join(map(str, forbidden))
            )

    @staticmethod
    def _as_datetime(value: date | datetime | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime(value.year, value.month, value.day, 23, 59, 59, 999999)

    @staticmethod
    def _quantile(sorted_values: list[float], q: float) -> float:
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = (len(sorted_values) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)
        fraction = position - lower
        return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


__all__ = [
    "CALIBRATION_VERSION",
    "DEFAULT_LOWER_QUANTILE",
    "DEFAULT_UPPER_QUANTILE",
    "CalibrationGroup",
    "ResearchCalibrationLayer",
    "cross_sectional_percentile",
    "historical_percentile",
    "rank_score",
    "research_percentile",
    "z_score",
]
