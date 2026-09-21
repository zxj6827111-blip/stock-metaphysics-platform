"""时间窗口 Schema（Phase 2D）。

两条不可妥协的规则
------------------
1. **禁止发明"流周"。** 传统术数没有"周"这一运限层。
   周度窗口必须由**交易日的流日结果聚合**得到，聚合方法必须版本化
   （``aggregation_version``），且同时给出 mean / median / min / max /
   positive_day_ratio / weighted_mean —— 只用平均值会掩盖分布。

2. **一切基于实际交易日。** 周 / 5D / 10D / 20D / 60D 窗口必须落在
   `TradingCalendarProvider` 给出的真实交易日上，**不得退化回自然日**。

月度窗口不是"一个综合数字"：每个月都必须独立携带
`bazi / ziwei / huangli / consensus / conflict / research_status / data_quality`。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from src.core.schemas.analysis import ConflictSnapshot, ConsensusSnapshot, MetaphysicsOpinion
from src.core.schemas.common import SMBaseModel, Warning_

#: 聚合方法版本。**改动聚合口径必须提升它**，否则"同一个月的分数为什么变了"无法追溯。
AGGREGATION_VERSION = "agg-v1"

#: 逐日窗口序列化口径版本（字段增删 / 含义变化必须提升）
DAILY_WINDOW_VERSION = "daily-v1"

#: 大限/流年等窗口类型
WINDOW_KINDS = ("month", "week")


class MonthWindow(SMBaseModel):
    """未来第 N 个月的时间窗口。

    每个月的三模型观点与共识**独立保存**，不是一个综合数字。
    """

    month: str = Field(description="YYYY-MM")
    month_index: int = Field(ge=1, description="未来第几个月（1 = 下一个月）")
    start_date: date | None = None
    end_date: date | None = None

    bazi: MetaphysicsOpinion | None = None
    ziwei: MetaphysicsOpinion | None = None
    huangli: MetaphysicsOpinion | None = None
    consensus: ConsensusSnapshot | None = None
    conflict: ConflictSnapshot | None = None

    research_status: str = "NOT_RUN"
    data_quality: dict = Field(default_factory=dict)

    #: 该月的交易日数量与用于打分的采样日（**必须来自交易日历**）
    trading_days: int = 0
    sample_dates: list[str] = Field(default_factory=list)

    warnings: list[Warning_] = Field(default_factory=list)


class DayResult(SMBaseModel):
    """周内某个交易日的结果（周度聚合的原子输入）。"""

    trade_date: date
    is_trading_day: bool = True
    bazi_direction: int = 0
    ziwei_direction: int = 0
    huangli_direction: int = 0
    combined_direction: int = 0
    bazi_score: float | None = None
    ziwei_score: float | None = None
    huangli_score: float | None = None


class WeekWindow(SMBaseModel):
    """未来第 N 周的时间窗口。

    **周是聚合的结果，不是独立的术数概念**：它由该周内**交易日**的流日结果
    聚合而来。字段 ``aggregation_method`` / ``aggregation_version`` 必须保留，
    以便未来更换口径时能够解释"为什么同一个周的分数变了"。
    """

    week_index: int = Field(ge=1, description="未来第几周（1 = 下一周）")
    week_start: date
    week_end: date

    trading_days: int = 0
    daily_results: list[DayResult] = Field(default_factory=list)

    aggregation_method: str = Field(default="", description="使用的聚合口径说明")
    aggregation_version: str = AGGREGATION_VERSION

    # --- 聚合指标（不允许只给一个平均数） ---
    mean: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None
    positive_day_ratio: float | None = None
    weighted_mean: float | None = None

    consensus: ConsensusSnapshot | None = None
    research_status: str = "NOT_RUN"
    warnings: list[Warning_] = Field(default_factory=list)


class TimeWindowRequest(SMBaseModel):
    """时间窗口请求。"""

    months: int = Field(default=12, ge=1, le=24)
    weeks: int = Field(default=12, ge=1, le=52)
    as_of: str | None = None
    variant_mode: str = "forward"

class TimeWindowResponse(SMBaseModel):
    """``GET /api/v1/analysis/{id}/timeline/{months,weeks}`` 的响应。"""

    stock_code: str
    as_of: datetime
    analysis_id: str = ""
    variant_mode: str = ""
    aggregation_version: str = AGGREGATION_VERSION
    months: list[MonthWindow] = Field(default_factory=list)
    weeks: list[WeekWindow] = Field(default_factory=list)
    research_status: str = "NOT_RUN"
    research_status_reasons: list[str] = Field(default_factory=list)
    methodology: str = ""
    warnings: list[Warning_] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=datetime.now)


class DailyWindowResponse(SMBaseModel):
    """``GET /api/v1/analysis/{id}/timeline/days`` 的响应（逐日粒度）。

    **逐日 ≠ 把月度分数插值到每一天。** 这里的每一天都是独立的流日结果：
    以该交易日的日柱 + 当日黄历 + 当日紫微流日为输入重新求值，
    因此缺哪一个模型就显式缺那一个（``*_score`` 为 ``None``），不填 0。
    """

    stock_code: str
    as_of: datetime
    analysis_id: str = ""
    variant_mode: str = ""
    daily_version: str = DAILY_WINDOW_VERSION
    requested_days: int = 0
    returned_days: int = 0
    days: list[DayResult] = Field(default_factory=list)
    research_status: str = "NOT_RUN"
    research_status_reasons: list[str] = Field(default_factory=list)
    methodology: str = ""
    warnings: list[Warning_] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=datetime.now)


__all__ = [
    "MonthWindow", "WeekWindow", "DayResult", "TimeWindowRequest",
    "TimeWindowResponse", "DailyWindowResponse",
    "AGGREGATION_VERSION", "DAILY_WINDOW_VERSION",
]
