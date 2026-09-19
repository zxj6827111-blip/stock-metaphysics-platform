"""行情与研究层 Schema：Bar、Label、EventStudy、NegativeControl。"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import Field

from src.core.schemas.common import (
    MarketDataSource,
    SMBaseModel,
    SourceRef,
    Warning_,
)


class Bar(SMBaseModel):
    """标准日线 Bar。所有行情源必须归一化到该结构。"""

    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover: float | None = None
    pct_change: float | None = None
    # 复权因子与来源
    adjust: str = Field(default="qfq", description="复权方式：none / qfq / hfq")
    source: str = ""


class BarSeries(SMBaseModel):
    """一段行情序列。"""

    stock_code: str
    bars: list[Bar] = Field(default_factory=list)
    source: MarketDataSource = MarketDataSource.AKSHARE
    source_ref: SourceRef = Field(default_factory=lambda: SourceRef(source="akshare"))
    adjust: str = "qfq"
    start: date | None = None
    end: date | None = None
    warnings: list[Warning_] = Field(default_factory=list)
    is_degraded: bool = Field(default=False, description="True 表示非真实行情（降级/合成）")

    def closes(self) -> list[float]:
        return [b.close for b in self.bars if b.close is not None]


class LabelSet(SMBaseModel):
    """某只股票在某 as_of 的**未来收益标签**。

    这些字段**只能作为预测目标（label）**，绝不能作为 as_of 时刻的输入特征。
    参见 ``tests/test_no_future_data_access.py``。
    """

    stock_code: str
    as_of: date = Field(description="特征基准日（该日收盘后可得信息）")
    trade_date: date = Field(description="实际计算基准交易日（>= as_of 的第一个交易日）")

    ret_1d: float | None = None
    ret_5d: float | None = None
    ret_10d: float | None = None
    ret_20d: float | None = None
    ret_60d: float | None = None

    max_return_20d: float | None = None
    max_drawdown_20d: float | None = None

    bench_ret_20d: float | None = None
    excess_return_20d: float | None = None

    # 多定义"上涨"（architecture §42）
    absolute_up_20d: bool | None = None
    excess_up_20d: bool | None = None
    strong_up_20d: bool | None = None
    drawdown_controlled_up_20d: bool | None = None

    benchmark_code: str = "000300"
    horizon_available: dict[str, bool] = Field(default_factory=dict)
    #: 非标准持有期（不在 1/5/10/20/60 内）的收益，避免动态 setattr 静默丢失
    extra_returns: dict[str, float] = Field(default_factory=dict)
    #: 标签所依据的行情是否为降级/合成（Phase 1.1：合成数据不得产出"研究证据"）
    data_is_degraded: bool = False
    data_source: str = ""
    computed_at: datetime = Field(default_factory=datetime.now)


class EventStudyRequest(SMBaseModel):
    """事件研究请求。"""

    factor_ids: list[str] = Field(default_factory=list, description="目标因子（单因子或多因子组合）")
    logic: str = Field(default="any", description="多因子组合逻辑：any / all")
    horizons: list[int] = Field(default_factory=lambda: [5, 10, 20, 60])
    stock_codes: list[str] = Field(default_factory=list, description="股票池；空表示全库")
    date_from: date | None = None
    date_to: date | None = None
    direction_filter: int | None = Field(default=None, description="只看 direction=+1 / -1 的观测")
    min_rule_score: float | None = None
    activation: str = Field(
        default="nonzero",
        description=(
            "事件激活条件：any=只要算了该因子就算命中；"
            "nonzero=归一化值非 0 才算命中（默认，语义为『该传统结构成立』）；"
            "positive / negative=只看正向 / 负向命中。"
            "负对照要能检出差异，必须使用 nonzero/positive/negative。"
        ),
    )
    benchmark_code: str = "000300"


class HorizonStats(SMBaseModel):
    """单个持有期的统计结果。"""

    horizon: int
    sample_count: int = 0
    up_rate: float | None = None
    excess_up_rate: float | None = None
    mean_return: float | None = None
    median_return: float | None = None
    std_return: float | None = None
    mean_excess_return: float | None = None
    max_drawdown: float | None = None
    mean_max_return: float | None = None
    note: str = ""


class EventStudyResult(SMBaseModel):
    """事件研究输出（architecture §16）。

    Phase 1.1 新增（后向兼容的可选字段）：

    * ``research_status`` / ``research_status_reasons`` —— 研究结论状态机
      （``src/research/status.py``）。合成/降级数据时恒为 ``NO_REAL_DATA``。
    * ``activation_stats`` —— 每个目标因子的激活率统计
      （``activation_rate > 0.95`` 或 ``< 0.005`` 会触发 LOW_DISCRIMINATION_FACTOR 警告）。
    """

    experiment_id: str = ""
    factor_ids: list[str] = Field(default_factory=list)
    logic: str = "any"
    universe_size: int = 0
    event_count: int = 0
    date_from: date | None = None
    date_to: date | None = None
    horizons: list[HorizonStats] = Field(default_factory=list)
    benchmark_code: str = "000300"
    methodology: str = ""
    warnings: list[Warning_] = Field(default_factory=list)
    research_status: str | None = Field(
        default=None,
        description="研究状态机输出：NOT_RUN/NO_REAL_DATA/INSUFFICIENT_SAMPLE/INVALID_CONTROL/"
                    "NO_SIGNAL/INCONCLUSIVE/WEAK_EVIDENCE/SUPPORTED_IN_SAMPLE。",
    )
    research_status_reasons: list[str] = Field(default_factory=list)
    data_source: dict | None = Field(
        default=None,
        description="面板行情来源汇总：{provider, degraded_codes, is_real, snapshot}。",
    )
    activation_stats: dict[str, dict] | None = Field(
        default=None,
        description="每个目标因子的激活统计：total/activated/activation_rate。",
    )
    computed_at: datetime = Field(default_factory=datetime.now)


class NegativeControlKind(str, Enum):
    """负对照类型（architecture §44）。"""

    RANDOM_BIRTH_DATE = "random_birth_date"      # 随机出生日期
    SHIFT_PLUS_7D = "shift_plus_7d"              # 出生日期 +7 天
    SHIFT_MINUS_7D = "shift_minus_7d"            # 出生日期 -7 天
    RANDOM_FACTOR = "random_factor"              # 随机因子


class NegativeControlResult(SMBaseModel):
    """负对照结果。

    目的：检验"真实术数因子是否显著优于随机结果"。
    如果真实因子并不优于随机，必须如实输出，不得隐藏。
    """

    kind: NegativeControlKind
    description: str = ""
    seed: int | None = None
    horizon_stats: list[HorizonStats] = Field(default_factory=list)
    # 与真实结果的对比
    real_mean_return_20d: float | None = None
    control_mean_return_20d: float | None = None
    real_up_rate_20d: float | None = None
    control_up_rate_20d: float | None = None
    real_mean_excess_return_20d: float | None = None
    control_mean_excess_return_20d: float | None = None
    delta_mean_return_20d: float | None = None
    delta_up_rate_20d: float | None = None
    # --- 事件集合独立性诊断（Phase 1.1） ---
    event_count: int | None = Field(default=None, description="对照组事件数（激活后）")
    real_event_count: int | None = Field(default=None, description="真实组事件数（激活后）")
    overlap_with_real: int | None = Field(default=None, description="与真实事件集合的交集大小")
    jaccard_with_real: float | None = Field(
        default=None,
        description="与真实事件集合的 Jaccard 相似度；> 0.9 触发 NEGATIVE_CONTROL_NOT_INDEPENDENT",
    )
    verdict: str = Field(
        default="inconclusive",
        description="outperform / tie / underperform / inconclusive",
    )
    verdict_note: str = ""
    warnings: list[Warning_] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=datetime.now)


class NegativeControlReport(SMBaseModel):
    """完整负对照报告（四类对照）。"""

    experiment_id: str = ""
    factor_ids: list[str] = Field(default_factory=list)
    results: list[NegativeControlResult] = Field(default_factory=list)
    conclusion: str = Field(
        default="",
        description="如实结论：真实因子是否优于随机；无法结论时必须明说",
    )
    computed_at: datetime = Field(default_factory=datetime.now)
