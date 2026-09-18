"""ORM 模型 —— Phase 1 的 14 张核心表。

表清单（对应 architecture §47 / two_session_plan §15）：

    stock_master                 股票基础资料
    stock_birth_profile          股票出生研究档案（版本化）
    exchange_session_calendar    交易所交易时段配置（"开盘时刻"的唯一来源）
    market_bar_daily             日行情（含 benchmark）

    engine_version               引擎版本登记
    engine_run                   引擎运行记录
    chart_artifact               原始术数盘面（一等数据，可审计）

    factor_definition            因子定义（因子字典）
    factor_observation           因子观测值

    classical_book               古籍书目
    classical_entry              古籍条目
    evidence_link                证据关联（因子/规则 ↔ 古籍条目）

    backtest_experiment          研究实验
    backtest_result              研究结果
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# 1. 股票主数据
# ---------------------------------------------------------------------------


class StockMasterRow(TimestampMixin, Base):
    __tablename__ = "stock_master"

    stock_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    wind_code: Mapped[str] = mapped_column(String(24), default="")
    name: Mapped[str] = mapped_column(String(64), default="")
    exchange: Mapped[str] = mapped_column(String(16), default="UNKNOWN", index=True)
    board: Mapped[str] = mapped_column(String(32), default="")
    industry: Mapped[str] = mapped_column(String(64), default="")
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    total_market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    circulating_market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(32), default="akshare")
    data_quality_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    birth_profiles: Mapped[list[StockBirthProfileRow]] = relationship(
        back_populates="stock", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# 2. 交易所交易时段（开盘时刻唯一来源）
# ---------------------------------------------------------------------------


class ExchangeSessionRow(TimestampMixin, Base):
    __tablename__ = "exchange_session_calendar"
    __table_args__ = (
        UniqueConstraint("exchange", "board", "session_name", "effective_from", name="uq_exchange_session"),
        Index("ix_exchange_session_lookup", "exchange", "board"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(16), index=True)
    board: Mapped[str] = mapped_column(String(32), default="DEFAULT")
    session_name: Mapped[str] = mapped_column(String(32), default="continuous_trading")
    open_time: Mapped[str] = mapped_column(String(8), default="09:30:00")
    close_time: Mapped[str] = mapped_column(String(8), default="15:00:00")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(64), default="config/exchange_session_calendar.yaml")


# ---------------------------------------------------------------------------
# 3. 股票出生档案（版本化，不覆盖历史）
# ---------------------------------------------------------------------------


class StockBirthProfileRow(TimestampMixin, Base):
    __tablename__ = "stock_birth_profile"
    __table_args__ = (
        UniqueConstraint(
            "stock_code", "birth_basis", "birth_profile_version", name="uq_birth_profile_version"
        ),
        Index("ix_birth_profile_stock", "stock_code", "birth_basis"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(ForeignKey("stock_master.stock_code"), index=True)
    exchange: Mapped[str] = mapped_column(String(16))
    birth_basis: Mapped[str] = mapped_column(String(32), default="listing_open")
    birth_datetime: Mapped[datetime] = mapped_column(DateTime, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")

    source: Mapped[str] = mapped_column(String(64), default="derived")
    birth_profile_version: Mapped[str] = mapped_column(String(16), default="v1")

    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    data_quality_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    variant_mode: Mapped[str] = mapped_column(String(24), default="not_applicable")
    variant_note: Mapped[str] = mapped_column(Text, default="")

    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    company_foundation: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_trade: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    custom_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    stock: Mapped[StockMasterRow] = relationship(back_populates="birth_profiles")


# ---------------------------------------------------------------------------
# 4. 日行情
# ---------------------------------------------------------------------------


class MarketBarDailyRow(Base):
    __tablename__ = "market_bar_daily"
    __table_args__ = (
        UniqueConstraint("stock_code", "trade_date", "adjust", name="uq_bar_daily"),
        Index("ix_bar_daily_code_date", "stock_code", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjust: Mapped[str] = mapped_column(String(8), default="qfq")
    is_benchmark: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="akshare")
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class MarketFetchLogRow(Base):
    """行情抓取日志：用于缓存 TTL 与故障诊断。"""

    __tablename__ = "market_fetch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # ok / cached / degraded / error
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# 5. 引擎版本 / 运行 / 原始盘面
# ---------------------------------------------------------------------------


class EngineVersionRow(Base):
    __tablename__ = "engine_version"
    __table_args__ = (UniqueConstraint("engine_id", "engine_version", name="uq_engine_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine_id: Mapped[str] = mapped_column(String(32), index=True)
    engine_version: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    config_version: Mapped[str] = mapped_column(String(32), default="")
    third_party: Mapped[str] = mapped_column(String(128), default="")
    third_party_commit: Mapped[str] = mapped_column(String(64), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class EngineRunRow(Base):
    __tablename__ = "engine_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    engine_id: Mapped[str] = mapped_column(String(32), index=True)
    engine_version: Mapped[str] = mapped_column(String(64), default="")
    config_version: Mapped[str] = mapped_column(String(32), default="")
    stock_code: Mapped[str] = mapped_column(String(16), default="", index=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok / error / partial
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ChartArtifactRow(Base):
    """原始术数盘面（一等数据）。未来引擎升级后必须可重新审计。"""

    __tablename__ = "chart_artifact"
    __table_args__ = (
        Index("ix_chart_artifact_lookup", "stock_code", "engine", "as_of"),
    )

    chart_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    engine: Mapped[str] = mapped_column(String(32), index=True)
    engine_version: Mapped[str] = mapped_column(String(64), default="")
    config_version: Mapped[str] = mapped_column(String(32), default="")
    birth_profile_version: Mapped[str] = mapped_column(String(16), default="")
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_chart: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# 6. 因子
# ---------------------------------------------------------------------------


class FactorDefinitionRow(TimestampMixin, Base):
    __tablename__ = "factor_definition"
    __table_args__ = (
        UniqueConstraint("factor_id", "rule_version", name="uq_factor_def_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    factor_id: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(128))
    engine: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    definition: Mapped[str] = mapped_column(Text)
    computation: Mapped[str] = mapped_column(Text, default="")
    raw_unit: Mapped[str] = mapped_column(String(64), default="")
    normalized_hint: Mapped[str] = mapped_column(Text, default="")
    default_direction: Mapped[int] = mapped_column(Integer, default=0)
    rule_score_meaning: Mapped[str] = mapped_column(Text, default="")
    rule_version: Mapped[str] = mapped_column(String(16), default="v1")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tags_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class FactorObservationRow(Base):
    __tablename__ = "factor_observation"
    __table_args__ = (
        UniqueConstraint("stock_code", "as_of", "factor_id", "rule_version", name="uq_factor_obs"),
        Index("ix_factor_obs_lookup", "factor_id", "as_of"),
        Index("ix_factor_obs_code", "stock_code", "as_of"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    factor_id: Mapped[str] = mapped_column(String(48), index=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    engine: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(128), default="")

    raw_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction: Mapped[int] = mapped_column(Integer, default=0)
    rule_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    availability: Mapped[str] = mapped_column(String(16), default="ok")

    rule_version: Mapped[str] = mapped_column(String(16), default="v1")
    engine_version: Mapped[str] = mapped_column(String(64), default="")
    config_version: Mapped[str] = mapped_column(String(32), default="")
    evidence_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# 7. 古籍知识
# ---------------------------------------------------------------------------


class ClassicalBookRow(Base):
    __tablename__ = "classical_book"

    book_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    author: Mapped[str] = mapped_column(String(64), default="")
    dynasty: Mapped[str] = mapped_column(String(32), default="")
    domain: Mapped[str] = mapped_column(String(24), index=True, default="bazi")
    school: Mapped[str] = mapped_column(String(32), default="")
    edition: Mapped[str] = mapped_column(String(128), default="")
    provenance: Mapped[str] = mapped_column(Text, default="")
    license_status: Mapped[str] = mapped_column(String(24), default="public_domain")
    authority_weight: Mapped[float] = mapped_column(Float, default=1.0)
    note: Mapped[str] = mapped_column(Text, default="")

    entries: Mapped[list[ClassicalEntryRow]] = relationship(
        back_populates="book_ref", cascade="all, delete-orphan"
    )


class ClassicalEntryRow(Base):
    __tablename__ = "classical_entry"
    __table_args__ = (Index("ix_classical_entry_domain_school", "domain", "school"),)

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("classical_book.book_id"), index=True)
    book: Mapped[str] = mapped_column(String(128), default="")
    domain: Mapped[str] = mapped_column(String(24), index=True, default="bazi")
    school: Mapped[str] = mapped_column(String(32), default="")
    chapter: Mapped[str] = mapped_column(String(128), default="")
    section: Mapped[str] = mapped_column(String(128), default="")
    topic_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    original_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    modern_note: Mapped[str] = mapped_column(Text, default="")
    commentary: Mapped[str] = mapped_column(Text, default="")
    authority_weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(256), default="")
    edition: Mapped[str] = mapped_column(String(128), default="")
    provenance: Mapped[str] = mapped_column(Text, default="")
    license_status: Mapped[str] = mapped_column(String(24), default="public_domain")
    stance_hint: Mapped[str] = mapped_column(String(16), default="neutral")
    applies_to_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    book_ref: Mapped[ClassicalBookRow] = relationship(back_populates="entries")


class EvidenceLinkRow(Base):
    """证据关联：把因子/规则/分析结果与古籍条目连起来。"""

    __tablename__ = "evidence_link"
    __table_args__ = (
        Index("ix_evidence_link_target", "target_type", "target_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)  # factor / rule / analysis
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("classical_entry.entry_id"), index=True)
    stance: Mapped[str] = mapped_column(String(16), default="neutral")
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ---------------------------------------------------------------------------
# 8. 研究实验
# ---------------------------------------------------------------------------


class BacktestExperimentRow(Base):
    __tablename__ = "backtest_experiment"

    experiment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # event_study / negative_control / label
    name: Mapped[str] = mapped_column(String(256), default="")
    factor_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    logic: Mapped[str] = mapped_column(String(16), default="any")
    universe_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    horizons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    benchmark_code: Mapped[str] = mapped_column(String(16), default="000300")
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    methodology: Mapped[str] = mapped_column(Text, default="")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class BacktestResultRow(Base):
    __tablename__ = "backtest_result"
    __table_args__ = (
        Index("ix_backtest_result_exp", "experiment_id", "horizon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("backtest_experiment.experiment_id"), index=True
    )
    variant: Mapped[str] = mapped_column(String(48), default="real", index=True)  # real / random_birth_date / ...
    horizon: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    up_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_up_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_excess_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_max_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AnalysisRunRow(Base):
    """一次分析运行的索引（供 API ``GET /analysis/{id}`` 查询）。"""

    __tablename__ = "analysis_run"

    analysis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, index=True)
    horizon: Mapped[str] = mapped_column(String(16), default="20d")
    engines_requested_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    engines_completed_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    engines_failed_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    versions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


__all__ = [
    "StockMasterRow", "StockBirthProfileRow", "ExchangeSessionRow",
    "MarketBarDailyRow", "MarketFetchLogRow",
    "EngineVersionRow", "EngineRunRow", "ChartArtifactRow",
    "FactorDefinitionRow", "FactorObservationRow",
    "ClassicalBookRow", "ClassicalEntryRow", "EvidenceLinkRow",
    "BacktestExperimentRow", "BacktestResultRow", "AnalysisRunRow",
]
