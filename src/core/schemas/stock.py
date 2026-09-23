"""股票领域 Schema：StockMaster、ExchangeSession、StockBirthProfile。"""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import Field, field_validator

from src.core.schemas.common import (
    Assumption,
    BirthBasis,
    DataQuality,
    DataQualityGrade,
    Exchange,
    SMBaseModel,
    SourceRef,
    VariantBasis,
    VariantMode,
)


class StockMaster(SMBaseModel):
    """股票基础资料。"""

    stock_code: str = Field(description="6 位标准代码，如 600519")
    wind_code: str = Field(default="", description="带后缀代码，如 600519.SH")
    name: str = ""
    exchange: Exchange = Exchange.UNKNOWN
    board: str = Field(default="", description="主板 / 创业板 / 科创板 / 北交所")
    industry: str = ""
    listing_date: date | None = None
    #: 上市首日涨跌幅与「阴阳」标识（阳=首日收涨 / 阴=首日收跌），来自权威表。
    #: **不是股票的性别**：只在 ``variant_basis=first_day_yinyang`` 时作为显式假设
    #: 参与运限顺逆推导（ADR-0014 / AGENTS.md §5），缺数据一律 None，禁止默认填充。
    first_day_pct_chg: float | None = None
    first_day_yinyang: str | None = Field(default=None, description="阳 / 阴 / None（无数据）")
    total_market_cap: float | None = None
    circulating_market_cap: float | None = None
    is_active: bool = True
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="akshare"))
    data_quality: DataQuality = Field(default_factory=DataQuality)
    updated_at: datetime = Field(default_factory=datetime.now)

    @field_validator("stock_code")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip()


class ExchangeSession(SMBaseModel):
    """交易所交易时段配置（``exchange_session_calendar`` 表）。

    这是"股票出生时间"里"正式开盘时刻"的**唯一来源**。
    严禁在业务代码中硬编码 09:30。
    """

    exchange: Exchange
    board: str = Field(default="DEFAULT", description="板块；DEFAULT 为兜底配置")
    session_name: str = Field(default="continuous_trading", description="时段名")
    open_time: time = Field(description="正式开盘时刻（本地时间）")
    close_time: time = Field(description="收盘时刻")
    timezone: str = Field(default="Asia/Shanghai")
    effective_from: date | None = None
    effective_to: date | None = None
    note: str = ""
    source: str = "config/exchange_session_calendar.yaml"


class BirthProfileEvidence(SMBaseModel):
    """出生档案的证据链（为什么是这一刻）。"""

    listing_date: date | None = None
    first_trading_day: date | None = None
    session_name: str = ""
    session_open_time: str = ""
    timezone: str = ""
    derivation: str = Field(default="", description="人类可读的推导过程")
    lookup_key: str = Field(default="", description="exchange_session_calendar 命中键")


class StockBirthProfile(SMBaseModel):
    """股票"出生研究档案"——本项目第一重要的研究变量。

    默认模型 ``listing_open``：

        上市首个正式交易日 + 该交易所对应 session 的正式开盘时刻 + Asia/Shanghai

    Phase 1 只把该时刻用于**排盘**；不同出生基准的优劣必须由历史回测决定。
    """

    stock_code: str
    exchange: Exchange
    birth_basis: BirthBasis = BirthBasis.LISTING_OPEN
    birth_datetime: datetime
    timezone: str = "Asia/Shanghai"

    source: SourceRef = Field(default_factory=lambda: SourceRef(source="derived"))
    birth_profile_version: str = "v1"

    # 可追溯性
    evidence: BirthProfileEvidence = Field(default_factory=BirthProfileEvidence)
    assumptions: list[Assumption] = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    # 运限顺逆假设（股票无性别）
    variant_mode: VariantMode = VariantMode.NOT_APPLICABLE
    variant_note: str = ""

    # 预留候选基准（Phase 2 回测比较用）
    ipo_date: date | None = None
    company_foundation: date | None = None
    first_trade: datetime | None = None
    custom_datetime: datetime | None = None

    created_at: datetime = Field(default_factory=datetime.now)

    def quality_grade(self) -> DataQualityGrade:
        return self.data_quality.grade


class BirthProfileCreateRequest(SMBaseModel):
    """创建出生档案的请求体。"""

    birth_basis: BirthBasis = BirthBasis.LISTING_OPEN
    variant_mode: VariantMode = VariantMode.NOT_APPLICABLE
    variant_basis: VariantBasis = Field(
        default=VariantBasis.EXPLICIT,
        description=(
            "运限变体的来源口径。`explicit`（默认）直接用 variant_mode；"
            "`first_day_yinyang` 由上市首日涨跌标识推导（阳→forward / 阴→reverse），"
            "此时 variant_mode 必须保持 not_applicable，否则视为冲突（ADR-0014）。"
        ),
    )
    override_datetime: datetime | None = Field(
        default=None, description="仅当 birth_basis=custom 时使用"
    )
    exchange_override: Exchange | None = None
