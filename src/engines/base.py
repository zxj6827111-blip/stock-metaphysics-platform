"""术数引擎统一抽象（architecture §19）。

所有术数引擎（八字 / 紫微 / 六爻 / 奇门）必须实现同一接口。
Phase 1 实现 Calendar / Huangli / Bazi，其余只保留骨架。

关键约束
--------
- 引擎内部**可以**使用第三方库；引擎外部**不得**看到第三方对象。
- 每个引擎必须声明 ``engine_id`` / ``engine_version`` / ``third_party``，
  信息写入 ``engine_version`` 表，用于结果可追溯。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

from src.core.schemas.common import Assumption, Availability, Warning_

ChartT = TypeVar("ChartT")


@dataclass(frozen=True)
class EngineMetadata:
    """引擎元信息（写入 ``engine_version`` 表）。"""

    engine_id: str
    display_name: str
    engine_version: str
    config_version: str = ""
    third_party: str = ""
    third_party_commit: str = ""
    notes: str = ""


@dataclass
class EngineContext:
    """引擎调用上下文。"""

    stock_code: str = ""
    as_of: datetime | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class MetaphysicsEngine(ABC, Generic[ChartT]):
    """所有术数引擎的抽象基类。"""

    metadata: EngineMetadata

    @property
    def engine_id(self) -> str:
        return self.metadata.engine_id

    @property
    def engine_version(self) -> str:
        return self.metadata.engine_version

    @property
    def availability(self) -> Availability:
        """引擎是否可用。Phase 1 未实现的引擎返回 UNAVAILABLE。"""
        return Availability.OK

    @abstractmethod
    def calculate_chart(self, context: EngineContext, **kwargs: Any) -> ChartT:
        """生成原始盘面。"""

    def extract_factors(self, chart: ChartT, context: EngineContext) -> list[dict]:
        """从盘面抽取因子。默认无因子。"""
        return []

    def explain_rules(self, chart: ChartT, factors: list[dict]) -> list[str]:
        """生成规则解释。默认空。"""
        return []

    def build_evidence_query(self, chart: ChartT, factors: list[dict]) -> list[str]:
        """构造古籍检索查询。默认空。"""
        return []

    def score(self, factors: list[dict]) -> dict:
        """传统规则强度聚合（非收益预测）。"""
        return {"score": None, "direction": 0, "confidence": 0.0}

    def collect_assumptions(self) -> list[Assumption]:
        return []

    def collect_warnings(self) -> list[Warning_]:
        return []
