"""BacktestProvider 抽象与本地实现（architecture §14）。

V1 不绑定 vectorbt / backtrader；先用 pandas + numpy + duckdb 自研，
满足：因子验证、事件研究、负对照。

Phase 2 若接入外部回测框架，只需实现同一接口，业务层不受影响。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from src.core.schemas.market import EventStudyRequest, EventStudyResult, NegativeControlReport
from src.research.event_study.engine import evaluate_event_study
from src.research.validation.negative_controls import (
    NegativeControlKind,
    random_birth_date_control,
    random_factor_control,
    shift_birth_date_control,
    summarize_controls,
)


class BacktestProvider(ABC):
    """回测 / 验证提供者契约。"""

    provider_id: str = "local"

    @abstractmethod
    def evaluate_factor(
        self,
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> EventStudyResult:
        """评估单个（或一组）因子。"""

    @abstractmethod
    def evaluate_signal(
        self,
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> EventStudyResult:
        """评估一个信号组合（等价于多因子 all 逻辑）。"""

    @abstractmethod
    def evaluate_negative_controls(
        self,
        real_result: EventStudyResult,
        *,
        control_panels: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> NegativeControlReport:
        """执行全部负对照。

        ``control_panels`` 每项为 ``(观测, 标签)``，且观测必须是
        用对应负对照假设（随机出生日 / ±7 天）**重新排盘重算**得到的，
        否则对照无效。
        """


class LocalBacktestProvider(BacktestProvider):
    """本地实现（pandas + numpy）。"""

    provider_id = "local"

    def evaluate_factor(
        self,
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> EventStudyResult:
        return evaluate_event_study(observations, labels, request, variant="real")

    def evaluate_signal(
        self,
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> EventStudyResult:
        req = request.model_copy(update={"logic": "all"})
        return evaluate_event_study(observations, labels, req, variant="real_signal")

    def evaluate_negative_controls(
        self,
        real_result: EventStudyResult,
        *,
        control_panels: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
        observations: pd.DataFrame,
        labels: pd.DataFrame,
        request: EventStudyRequest,
    ) -> NegativeControlReport:
        real_stats = next((h for h in real_result.horizons if h.horizon == 20), None)
        results = []

        random_panel = control_panels.get(str(NegativeControlKind.RANDOM_BIRTH_DATE))
        if random_panel is not None:
            results.append(random_birth_date_control(
                random_panel[0], random_panel[1], request, real_stats=real_stats
            ))

        plus7 = control_panels.get(str(NegativeControlKind.SHIFT_PLUS_7D))
        if plus7 is not None:
            results.append(shift_birth_date_control(
                NegativeControlKind.SHIFT_PLUS_7D, plus7[0], plus7[1], request,
                real_stats=real_stats, days=7,
            ))

        minus7 = control_panels.get(str(NegativeControlKind.SHIFT_MINUS_7D))
        if minus7 is not None:
            results.append(shift_birth_date_control(
                NegativeControlKind.SHIFT_MINUS_7D, minus7[0], minus7[1], request,
                real_stats=real_stats, days=-7,
            ))

        results.append(random_factor_control(
            observations, labels, request, real_stats=real_stats
        ))

        return summarize_controls(real_result.experiment_id, request.factor_ids, results)


def get_backtest_provider() -> BacktestProvider:
    return LocalBacktestProvider()
