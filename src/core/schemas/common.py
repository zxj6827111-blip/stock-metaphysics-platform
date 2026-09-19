"""跨模块通用枚举与基础类型。

这些类型是所有引擎 / 因子 / 研究层共享的契约，Phase 2 不得破坏。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SMBaseModel(BaseModel):
    """项目统一基类：禁止未声明字段，允许由 ORM 构造。"""

    model_config = ConfigDict(extra="forbid", from_attributes=True, use_enum_values=True)


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class Exchange(str, Enum):
    """交易所。"""

    SSE = "SSE"       # 上海证券交易所
    SZSE = "SZSE"     # 深圳证券交易所
    BSE = "BSE"       # 北京证券交易所
    UNKNOWN = "UNKNOWN"


EXCHANGE_CN_NAME: dict[str, str] = {
    "SSE": "上海证券交易所",
    "SZSE": "深圳证券交易所",
    "BSE": "北京证券交易所",
    "UNKNOWN": "未知交易所",
}


class BirthBasis(str, Enum):
    """股票"出生时间"研究基准。

    Phase 1 默认且仅默认启用 ``LISTING_OPEN``；其余为预留候选，
    必须经历史回测比较后才能进入正式模型。
    """

    LISTING_OPEN = "listing_open"              # 上市首个正式交易日 + 交易所正式开盘时刻（默认）
    IPO_DATE = "ipo_date"                      # IPO 发行日期
    COMPANY_FOUNDATION = "company_foundation"  # 公司成立日
    FIRST_TRADE = "first_trade"                # 首笔真实成交时刻
    CUSTOM = "custom"                          # 自定义


class VariantMode(str, Enum):
    """股票无性别 → 运限顺逆的变体模式。

    股票不存在真实"男命/女命"，因此任何依赖性别的顺逆规则**不得**被默认填充。
    """

    FORWARD = "forward"                # 顺排
    REVERSE = "reverse"                # 逆排
    BOTH = "both"                      # 两种都算（用于对比回测）
    NOT_APPLICABLE = "not_applicable"  # 不适用：Phase 1 默认，顺逆不进入因子


class EngineId(str, Enum):
    """术数引擎标识。Phase 1 只启用 CALENDAR / HUANGLI / BAZI。"""

    CALENDAR = "calendar"
    HUANGLI = "huangli"
    BAZI = "bazi"
    ZIWEI = "ziwei"
    LIUYAO = "liuyao"
    QIMEN = "qimen"


class DataQualityGrade(str, Enum):
    """数据质量等级。"""

    A = "A"  # 完整、来源确定
    B = "B"  # 完整但存在假设
    C = "C"  # 部分缺失或来源降级
    D = "D"  # 严重缺失，结论不可靠
    UNAVAILABLE = "unavailable"


class Direction(int, Enum):
    """因子 / 观点方向。"""

    POSITIVE = 1
    NEUTRAL = 0
    NEGATIVE = -1


class MarketDataSource(str, Enum):
    AKSHARE = "akshare"
    CACHE = "cache"
    #: 离线真实数据导入（data/import/，来自真实交易所历史的冻结快照）
    OFFLINE_IMPORT = "offline_import"
    SYNTHETIC_DEMO = "synthetic_demo"
    UNAVAILABLE = "unavailable"


class Availability(str, Enum):
    """字段 / 引擎可用性。禁止用 0 或空值冒充"不可用"。"""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    ERROR = "error"


class ConsensusLabel(str, Enum):
    """共识分类（Phase 1 仅用于展示层聚合，正式 Consensus Engine 属 Phase 2）。"""

    STRONG_POSITIVE_CONSENSUS = "STRONG_POSITIVE_CONSENSUS"
    POSITIVE_CONSENSUS = "POSITIVE_CONSENSUS"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    NEGATIVE_CONSENSUS = "NEGATIVE_CONSENSUS"
    STRONG_NEGATIVE_CONSENSUS = "STRONG_NEGATIVE_CONSENSUS"


CONSENSUS_CN_LABEL: dict[str, str] = {
    "STRONG_POSITIVE_CONSENSUS": "强正向共振",
    "POSITIVE_CONSENSUS": "正向共振",
    "MIXED": "模型分歧",
    "NEUTRAL": "中性",
    "NEGATIVE_CONSENSUS": "负向共振",
    "STRONG_NEGATIVE_CONSENSUS": "强负向共振",
}


# ---------------------------------------------------------------------------
# 基础结构
# ---------------------------------------------------------------------------


class Warning_(SMBaseModel):
    """结构化警告：任何"算不出 / 不确定"都必须显式产出，禁止静默填充。"""

    code: str = Field(description="机器可读代码，如 BAZI_PATTERN_UNAVAILABLE")
    message: str = Field(description="人类可读说明")
    severity: Literal["info", "warning", "error"] = "warning"
    context: dict[str, Any] = Field(default_factory=dict)


class Assumption(SMBaseModel):
    """显式记录的研究假设。"""

    key: str
    value: str
    reason: str
    impact: str = ""


class VersionStamp(SMBaseModel):
    """结果可追溯性版本戳。"""

    engine_version: str = ""
    rule_version: str = ""
    config_version: str = ""
    birth_profile_version: str = ""
    knowledge_version: str = ""
    factor_version: str = ""
    market_data_version: str = ""
    computed_at: datetime = Field(default_factory=datetime.now)


class DataQuality(SMBaseModel):
    """数据质量摘要。"""

    grade: DataQualityGrade = DataQualityGrade.B
    score: float = Field(default=0.8, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class SourceRef(SMBaseModel):
    """数据来源引用。"""

    source: str
    url: str = ""
    retrieved_at: datetime | None = None
    extra: dict[str, Any] = Field(default_factory=dict)
