"""因子系统 Schema。

核心纪律（architecture §28、two_session_plan §9）：

    "财星" ≠ 股票上涨；"食神生财" ≠ 股票一定上涨；"三合" ≠ 股票上涨。

所有传统术数结构只能先变成**研究因子**，之后由历史数据验证。
因此因子 Schema 中的 ``direction`` / ``rule_score`` 表达的是**传统规则的强弱与方向**，
**不是**预期收益率，也**不是**上涨概率。该语义由 ``rule_score_meaning`` 显式声明。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from src.core.schemas.common import Direction, EngineId, SMBaseModel


class FactorCategory(str, Enum):
    """因子层级/类别。"""

    NATAL = "natal"        # 原局结构
    YEAR = "year"          # 流年
    MONTH = "month"        # 流月
    DAY = "day"            # 流日
    CROSS = "cross"        # 跨盘关系（黄历 × 原局）
    FUSION = "fusion"      # 多模型融合（Phase 2）


class FactorDefinition(SMBaseModel):
    """因子定义（写入 ``factor_definition`` 表，构成"因子字典"）。"""

    factor_id: str = Field(description="全局唯一 ID，如 B_NATAL_001")
    name: str
    engine: EngineId
    category: FactorCategory
    definition: str = Field(description="因子含义与业务定义")
    computation: str = Field(default="", description="计算公式/规则描述")
    raw_unit: str = Field(default="", description="原始值单位或取值域")
    normalized_hint: str = Field(default="", description="归一化说明")
    # 因子方向只有研究含义：规则预期的方向，尚待历史检验
    default_direction: Direction = Direction.NEUTRAL
    rule_score_meaning: str = Field(
        default="传统规则强度分（0-10），不代表预期收益率，也不代表上涨概率",
    )
    rule_version: str = "v1"
    enabled: bool = True
    requires: list[str] = Field(default_factory=list, description="依赖的盘面字段")
    tags: list[str] = Field(default_factory=list)


class FactorObservation(SMBaseModel):
    """某只股票在某时刻的因子取值（写入 ``factor_observation`` 表）。"""

    factor_id: str
    stock_code: str
    as_of: datetime = Field(description="观测基准时间：该时刻之后的数据不得作为输入")
    trade_date: date | None = None

    engine: EngineId
    category: FactorCategory
    name: str = ""

    raw_value: Any = Field(
        default=None,
        description="原始值，可为标量 / 列表 / 结构化字典；None 表示不可用",
    )
    normalized_value: float | None = Field(default=None, description="-1.0 ~ 1.0；None 表示不可用")
    direction: Direction = Direction.NEUTRAL
    rule_score: float = Field(default=0.0, description="传统规则强度 0-10（非收益预测）")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    availability: str = "ok"
    rule_version: str = "v1"
    engine_version: str = ""
    config_version: str = ""

    evidence: list[str] = Field(default_factory=list, description="盘面依据（可追溯）")
    explanation: str = ""
    warnings: list[str] = Field(default_factory=list)

    computed_at: datetime = Field(default_factory=datetime.now)


class FactorSet(SMBaseModel):
    """一次计算产出的因子集合。"""

    stock_code: str
    as_of: datetime
    engine_version: str = ""
    rule_version: str = "v1"
    config_version: str = ""
    observations: list[FactorObservation] = Field(default_factory=list)

    def by_id(self, factor_id: str) -> FactorObservation | None:
        for obs in self.observations:
            if obs.factor_id == factor_id:
                return obs
        return None

    def positives(self) -> list[FactorObservation]:
        return [o for o in self.observations if o.direction == Direction.POSITIVE]

    def negatives(self) -> list[FactorObservation]:
        return [o for o in self.observations if o.direction == Direction.NEGATIVE]
