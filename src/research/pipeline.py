"""研究流水线：把「因子观测」与「未来收益标签」拼成面板，执行事件研究与负对照。

流程
----
    1. 选定股票池与采样日期
    2. 对每个 (股票, as_of) 生成因子观测（只读 as_of 及之前的信息）
    3. 对每个 (股票, as_of) 计算未来收益标签（只用 as_of 之后的数据）
    4. 面板 = 观测 ⨝ 标签
    5. Event Study
    6. 负对照：随机出生日 / ±7 天 / 随机因子

负对照中的「出生日期平移/随机」需要**真的重排盘、重算因子**，
否则对照没有意义。本模块通过 ``birth_datetime_transform`` 回调实现。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from src.core.config import settings
from src.core.schemas.common import Warning_
from src.core.schemas.market import (
    EventStudyRequest,
    NegativeControlKind,
    NegativeControlReport,
)
from src.core.schemas.stock import StockBirthProfile
from src.core.schemas.factor import FactorObservation
from src.research.backtest.provider import BacktestProvider, LocalBacktestProvider

BirthTransform = Callable[[datetime, np.random.Generator], datetime]


def _label_row(labels) -> dict:  # type: ignore[no-untyped-def]
    return {
        "stock_code": labels.stock_code,
        "trade_date": labels.trade_date,
        "as_of": labels.as_of,
        "ret_1d": labels.ret_1d,
        "ret_5d": labels.ret_5d,
        "ret_10d": labels.ret_10d,
        "ret_20d": labels.ret_20d,
        "ret_60d": labels.ret_60d,
        "max_return_20d": labels.max_return_20d,
        "max_drawdown_20d": labels.max_drawdown_20d,
        "excess_return_20d": labels.excess_return_20d,
        "bench_ret_20d": labels.bench_ret_20d,
        "absolute_up_20d": labels.absolute_up_20d,
        "excess_up_20d": labels.excess_up_20d,
        "strong_up_20d": labels.strong_up_20d,
    }


def _observation_rows(observations: list[FactorObservation]) -> list[dict]:
    return [
        {
            "stock_code": o.stock_code,
            "trade_date": o.trade_date,
            "as_of": o.as_of,
            # as_of_date 是因子与标签的对齐键：as_of 可能落在非交易日，
            # 而标签的 trade_date 是 >= as_of 的第一个交易日。
            "as_of_date": o.as_of.date() if isinstance(o.as_of, datetime) else o.as_of,
            "factor_id": o.factor_id,
            "category": o.category,
            "direction": o.direction,
            "rule_score": o.rule_score,
            "normalized_value": o.normalized_value,
            "availability": o.availability,
        }
        for o in observations
    ]


def _align_observation_trade_dates(
    obs_df: pd.DataFrame, label_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把因子观测的 trade_date 对齐到标签的交易日。

    ``as_of`` 可能是月中任意一天（含非交易日），而标签的 ``trade_date``
    是 ``>= as_of`` 的第一个交易日。若不显式对齐，事件研究就无法把
    "因子命中"与"未来收益"按同一交易日连接起来。

    未匹配到标签的观测保留原 trade_date，最终会在 inner join 中被剔除
    （这是正确行为：没有未来数据的样本不能进入事件研究）。
    """
    if obs_df.empty or label_df.empty:
        return obs_df, label_df

    obs_df = obs_df.copy()
    label_df = label_df.copy()
    obs_df["as_of_date"] = pd.to_datetime(obs_df["as_of"]).dt.date
    label_df["as_of_date"] = pd.to_datetime(label_df["as_of"]).dt.date

    mapping = {
        (str(r.stock_code), r.as_of_date): r.trade_date
        for r in label_df.itertuples()
    }
    obs_df["trade_date"] = [
        mapping.get((str(c), a), t)
        for c, a, t in zip(obs_df["stock_code"], obs_df["as_of_date"], obs_df["trade_date"],
                           strict=True)
    ]
    # 没有对应标签的观测直接剔除，避免用 None 参与后续计算
    obs_df = obs_df[obs_df["trade_date"].notna()].reset_index(drop=True)
    return obs_df, label_df


class ResearchPipeline:
    """端到端研究流水线。"""

    def __init__(self, backtest: BacktestProvider | None = None) -> None:
        self.backtest = backtest or LocalBacktestProvider()

    # ------------------------------------------------------------------
    def build_panel(
        self,
        *,
        stocks: Iterable[str],
        sample_dates: list[date],
        factor_builder: Callable[[str, date, StockBirthProfile], list[FactorObservation]],
        label_builder: Callable[[str, date], object],
        birth_profile_provider: Callable[[str, str | None], StockBirthProfile],
        birth_transform: BirthTransform | None = None,
        variant: str = "real",
        seed: int | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, list[Warning_]]:
        """构建 (观测面板, 标签面板)。

        Args:
            factor_builder: ``(code, as_of_date, birth_profile) -> [FactorObservation]``
            label_builder: ``(code, as_of_date) -> LabelSet``
            birth_profile_provider: ``(code, variant) -> StockBirthProfile``
            birth_transform: 负对照使用的出生时间变换；None 表示真实基准
        """
        warnings: list[Warning_] = []
        rng = np.random.default_rng(settings.negative_control_seed if seed is None else seed)
        obs_rows: list[dict] = []
        label_rows: list[dict] = []

        for code in stocks:
            try:
                profile = birth_profile_provider(code, variant)
            except Exception as exc:  # noqa: BLE001
                warnings.append(Warning_(
                    code="RESEARCH_BIRTH_PROFILE_FAILED",
                    message=f"{code} 出生档案构造失败：{type(exc).__name__}: {exc}",
                    severity="warning",
                ))
                continue

            if birth_transform is not None:
                shifted = birth_transform(profile.birth_datetime, rng)
                profile = profile.model_copy(update={
                    "birth_datetime": shifted,
                    "source": profile.source.model_copy(update={"source": f"negative_control:{variant}"}),
                })

            for as_of_date in sample_dates:
                try:
                    observations = factor_builder(code, as_of_date, profile)
                    obs_rows.extend(_observation_rows(observations))
                except Exception as exc:  # noqa: BLE001
                    warnings.append(Warning_(
                        code="RESEARCH_FACTOR_FAILED",
                        message=f"{code}@{as_of_date} 因子计算失败：{type(exc).__name__}: {exc}",
                        severity="warning",
                    ))
                    continue

                try:
                    labels = label_builder(code, as_of_date)
                except Exception as exc:  # noqa: BLE001 - 数据不足属预期情况
                    warnings.append(Warning_(
                        code="RESEARCH_LABEL_UNAVAILABLE",
                        message=f"{code}@{as_of_date} 标签不可用：{type(exc).__name__}: {exc}",
                        severity="info",
                    ))
                    continue

                if labels is not None:
                    label_rows.append(_label_row(labels))

        obs_df = pd.DataFrame(obs_rows)
        label_df = pd.DataFrame(label_rows)
        obs_df, label_df = _align_observation_trade_dates(obs_df, label_df)
        if obs_df.empty:
            obs_df = pd.DataFrame(columns=[
                "stock_code", "trade_date", "as_of", "factor_id", "category",
                "direction", "rule_score", "normalized_value", "availability",
            ])
        if label_df.empty:
            label_df = pd.DataFrame(columns=[
                "stock_code", "trade_date", "as_of", "ret_20d",
            ])
        return obs_df, label_df, warnings

    # ------------------------------------------------------------------
    def run_event_study(
        self,
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ):
        return self.backtest.evaluate_factor(observations, labels, request)

    def run_negative_controls(
        self,
        real_result,
        *,
        control_panels: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> NegativeControlReport:
        return self.backtest.evaluate_negative_controls(
            real_result,
            control_panels=control_panels,
            observations=observations,
            labels=labels,
            request=request,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def make_birth_transform(mode: NegativeControlKind, *, rng_offset_days: int = 3650) -> BirthTransform:
        """生成出生时间变换函数。

        * ``RANDOM_BIRTH_DATE``：在上市日前后 ±``rng_offset_days`` 天内均匀随机
        * ``SHIFT_PLUS_7D`` / ``SHIFT_MINUS_7D``：平移 ±7 天
        """
        if mode == NegativeControlKind.SHIFT_PLUS_7D:
            return lambda dt, _rng: dt + timedelta(days=7)
        if mode == NegativeControlKind.SHIFT_MINUS_7D:
            return lambda dt, _rng: dt - timedelta(days=7)
        if mode == NegativeControlKind.RANDOM_BIRTH_DATE:
            def _random(dt: datetime, rng: np.random.Generator) -> datetime:
                delta = int(rng.integers(-rng_offset_days, rng_offset_days + 1))
                return dt + timedelta(days=delta)
            return _random
        raise ValueError(f"不支持的负对照类型: {mode}")


def new_experiment_id(prefix: str = "EXP") -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


def month_starts(date_from: date, date_to: date, step_months: int = 3) -> list[date]:
    """生成采样日期（默认每季度一个 as_of），控制研究规模。"""
    out: list[date] = []
    cur = date(date_from.year, date_from.month, 1)
    while cur <= date_to:
        out.append(cur)
        month = cur.month + step_months
        year = cur.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        cur = date(year, month, 1)
    return out


__all__ = [
    "ResearchPipeline", "new_experiment_id", "month_starts", "BirthTransform",
]
