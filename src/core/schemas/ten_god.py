"""十神系统 V1.0 的 Schema 合同（`ten_god_rule_version = ten-god-v1`）。

唯一语义（docs/TEN_GOD_SYSTEM_V1_IMPLEMENTATION_PLAN_20260924.md §2）
---------------------------------------------------------------------
股票自己的**日干**是固定日主；原局其他天干、原局地支藏干、流年天干、流月天干、
流日天干，以及流年/流月/流日地支的藏干，**全部相对该固定日主**由
``src.core.constants.ten_god(day_master, other_stem)`` 计算。

本模块刻意不提供任何"日期×股票三干关系矩阵"字段。矩阵（流年/流月/流日 ×
股票年/月/日）负责冲、合、刑、害、破、生克、伏吟、反吟，是**另一条轴**；
它不是传统十神的权威来源（合同 §5 / §17）。

不可用语义：``is_trading_day`` 与 ``verdict`` 的未知分别用 ``None`` /
``未知`` 表达，绝不用 ``False`` / ``不匹配`` 冒充。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from src.core.config import settings
from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import SMBaseModel, Warning_
from src.core.schemas.relation import (
    VERDICT_MATCH,
    VERDICT_MISMATCH,
    VERDICT_UNKNOWN,
    WUXING_ROLES,
)

#: 日主来源与对象来源的自描述（前端与审计据此判断"以谁为中心"）。
DAY_MASTER_SOURCE = "stock_natal_day_stem"
OTHER_STEM_SOURCE = "temporal_or_natal_stem"

#: 十神组全集（顺序即展示顺序，与 TEN_GOD_GROUP 一致）。
TEN_GOD_GROUPS: tuple[str, ...] = ("比劫", "食伤", "财星", "官杀", "印星")

#: 匹配状态全集（复用关系模块的三态常量，避免第二份定义）。
VERDICTS: tuple[str, ...] = (VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN)

#: 五类十神来源（合同 §3）——同一个 ten_god() 的五种输入，不是五套算法。
TEN_GOD_SCOPES: tuple[str, ...] = (
    "natal_stem", "natal_hidden_stem", "year_stem", "month_stem", "day_stem",
)

#: 日级产品的标准采样时刻（与 Date Scan 一致；合同 §12.4）。
OBSERVATION_TIME = "12:00:00"
OBSERVATION_TIMEZONE = "Asia/Shanghai"

#: 默认时间范围（合同 §1.3）。
DEFAULT_YEARS = 10
DEFAULT_MONTHS = 24
DEFAULT_DAYS = 365

#: 交易日历来源取值（与 TradingCalendar.CalendarQuery.source 对齐）。
TRADING_CALENDAR_SOURCES: tuple[str, ...] = (
    "observed_index_days",
    "published_exchange_calendar",
    "out_of_coverage",
    "weekend_rule_fallback",
)

#: 未来日期股票池语义（合同 §14）。
UNIVERSE_MODE_PIT = "point_in_time"
UNIVERSE_MODE_LATEST_KNOWN = "latest_known_for_future"


class TenGodRef(SMBaseModel):
    """一个天干相对固定日主的十神结果。"""

    stem: str
    wuxing: str = ""
    ten_god: str = ""
    ten_god_group: str = ""


class TenGodHiddenStem(TenGodRef):
    """地支藏干及其十神。``weight`` 是工程近似，不是传统定论。"""

    rank: str = ""
    weight: float | None = None
    weight_is_engineering_approximation: bool = True


class TenGodNatalStem(TenGodRef):
    """原局天干十神。日柱的规范关系是比肩，但盘面显示「日主」。"""

    position: str = Field(description="year | month | day | hour")
    #: 盘面标签：日柱为「日主」，其余为十神本身。
    display_label: str = ""
    is_day_master: bool = False


class TenGodNatalPillar(SMBaseModel):
    position: str
    ganzhi: GanZhi
    stem: TenGodNatalStem
    branch: str = ""
    branch_wuxing: str = ""
    hidden_stems: list[TenGodHiddenStem] = Field(default_factory=list)
    nayin: str = ""


class TenGodNatalProfile(SMBaseModel):
    """原局十神全貌：四柱天干十神 + 各地支藏干十神。"""

    day_master: str
    day_master_wuxing: str = ""
    pillars: list[TenGodNatalPillar] = Field(default_factory=list)
    #: 不含日柱的可见天干十神（沿用 BaziEngine 的 visible 口径）。
    visible_stem_ten_gods: list[str] = Field(default_factory=list)
    ten_god_counts: dict[str, int] = Field(default_factory=dict)
    ten_god_group_counts: dict[str, int] = Field(default_factory=dict)
    #: 藏干权重为工程近似的显式声明（合同 §9.B）。
    hidden_stem_weight_note: str = (
        "藏干权重（本气/中气/余气）是本项目五行力量估算的工程近似，不是传统定论。"
    )


class TenGodYongShen(SMBaseModel):
    """原局喜用忌仇闲五行集合（喜用与十神是两套独立维度）。"""

    yong_shen: list[str] = Field(default_factory=list)
    xi_shen: list[str] = Field(default_factory=list)
    ji_shen: list[str] = Field(default_factory=list)
    chou_shen: list[str] = Field(default_factory=list)
    xian_shen: list[str] = Field(default_factory=list)
    available: bool = False


class TenGodTemporalSegment(SMBaseModel):
    """流年 / 流月的一段有效区间，边界是**精确交节时刻**。

    半开区间 ``[start_at, end_at)``，保证交节瞬间只属于一个段（合同 §11.1）。
    """

    kind: str = Field(description="year | month")
    ganzhi: GanZhi
    #: 触发本次换柱的节气名（年柱恒为立春；月柱为十二"节"之一）。
    boundary_jieqi: str = ""
    next_boundary_jieqi: str = ""
    stem: str = ""
    stem_wuxing: str = ""
    stem_ten_god: str = ""
    stem_ten_god_group: str = ""
    branch: str = ""
    branch_wuxing: str = ""
    branch_hidden_stems: list[TenGodHiddenStem] = Field(default_factory=list)
    #: 该柱十二长生（以股票日主为准）。
    di_shi: str = ""
    start_at: datetime
    end_at: datetime
    timezone: str = OBSERVATION_TIMEZONE
    #: 喜用维度（独立于十神）。
    stem_wuxing_role: str = "未知"
    verdict: str = "未知"
    reason: str = ""


class TenGodDayRow(SMBaseModel):
    """一个**自然日**的流日十神行。非交易日也必须出行。"""

    date: date
    ganzhi: GanZhi
    stem: str = ""
    stem_wuxing: str = ""
    stem_ten_god: str = ""
    ten_god_group: str = ""
    branch: str = ""
    branch_wuxing: str = ""
    branch_hidden_stems: list[TenGodHiddenStem] = Field(default_factory=list)
    #: 流日所属的流年/流月柱（便于 UI 折叠展示，不重复计算）。
    year_ganzhi: str = ""
    month_ganzhi: str = ""
    di_shi: str = ""
    #: 喜用维度：与十神独立，未知不写成不匹配。
    wuxing_role: str = "未知"
    verdict: str = "未知"
    is_yong_or_xi: bool | None = None
    reason: str = ""
    #: 交易日状态。None = 日历覆盖不足，**不等于**休市。
    is_trading_day: bool | None = None
    trading_calendar_source: str = ""
    trading_calendar_authoritative: bool = False
    trading_calendar_degraded_reason: str = ""
    observation_time: str = OBSERVATION_TIME
    timezone: str = OBSERVATION_TIMEZONE


class TenGodStockSummary(SMBaseModel):
    stock_code: str
    name: str = ""
    exchange: str = ""
    birth_basis: str = ""
    birth_profile_version: str = ""
    birth_datetime: datetime | None = None
    timezone: str = OBSERVATION_TIMEZONE
    source: str = ""
    data_quality_grade: str = ""
    assumptions: list[str] = Field(default_factory=list)
    variant_mode: str = ""


class TenGodCalendarVersions(SMBaseModel):
    ten_god_rule_version: str = settings.ten_god_rule_version
    calendar_engine_version: str = ""
    bazi_engine_version: str = ""
    birth_profile_version: str = ""
    universe_version: str = ""
    trading_calendar_version_token: str = ""
    config_version: str = settings.config_version


class TenGodTradingCalendarStatus(SMBaseModel):
    """交易日历覆盖自述：默认「仅交易日」视图必须据此给出告警。"""

    exchange: str = ""
    observed_start: date | None = None
    observed_end: date | None = None
    published_start: date | None = None
    published_end: date | None = None
    loaded: bool = False
    published_loaded: bool = False
    load_error: str | None = None
    published_error: str | None = None
    version_token: str = ""
    #: 请求窗口内超出全部可用覆盖的日期数（None = 无法判定）。
    out_of_coverage_days: int | None = None
    #: 请求窗口内只由周末规则近似得到的日期数。
    degraded_days: int = 0
    note: str = ""


class TenGodCatalogItem(SMBaseModel):
    name: str
    group: str


class TenGodGroupItem(SMBaseModel):
    name: str
    members: list[str] = Field(default_factory=list)


class TenGodCatalogResponse(SMBaseModel):
    """前端十神/十神组/五行角色/匹配状态的**唯一**枚举来源。"""

    ten_god_rule_version: str = settings.ten_god_rule_version
    ten_gods: list[TenGodCatalogItem] = Field(default_factory=list)
    ten_god_groups: list[TenGodGroupItem] = Field(default_factory=list)
    wuxing_roles: list[str] = Field(default_factory=list)
    verdicts: list[str] = Field(default_factory=list)
    #: 算法方向自描述：谁向日主取十神。
    day_master_source: str = DAY_MASTER_SOURCE
    other_stem_source: str = OTHER_STEM_SOURCE
    #: 五类十神来源（合同 §3）。
    ten_god_scopes: list[str] = Field(default_factory=lambda: list(TEN_GOD_SCOPES))
    #: 与关系矩阵的边界声明（防止前端把 3×3 矩阵当十神展示）。
    relation_matrix_is_not_ten_god: bool = True
    relation_matrix_note: str = (
        "流年/流月/流日 × 股票年/月/日的 3×3 矩阵负责冲合刑害破生克伏吟反吟，"
        "不是传统十神的权威来源；权威流日十神只有 ten_god(股票日主, 流日干)。"
    )
    hidden_stems_by_branch: dict[str, list[str]] = Field(default_factory=dict)
    day_master_display_note: str = (
        "日柱天干相对自身是比肩关系，盘面显示为「日主」；两者语义不同，不合并。"
    )
    observation_time: str = OBSERVATION_TIME
    timezone: str = OBSERVATION_TIMEZONE
    calendar_engine_version: str = ""
    disclaimer: str = (
        "十神是传统术数的结构性分类，不代表预期收益率、上涨概率或交易建议；"
        "「喜用匹配」只是传统规则内的结构匹配，其市场有效性必须由独立历史研究、"
        "负对照与样本外验证确认。"
    )


class TenGodStockCalendarRequest(SMBaseModel):
    """股票 → 未来十神时历的查询参数。

    ``view`` 只做**显示过滤**：计算层始终构造全部自然日（合同 §1.1）。
    """

    start_date: date | None = None
    years: int = Field(default=DEFAULT_YEARS, ge=0, le=30)
    months: int = Field(default=DEFAULT_MONTHS, ge=0, le=60)
    days: int = Field(default=DEFAULT_DAYS, ge=0, le=730)
    view: str = Field(default="all", pattern="^(all|trading)$")
    ten_god: str | None = None
    ten_god_group: str | None = None
    wuxing_role: str | None = None
    verdict: str | None = None
    birth_basis: str = settings.canonical_birth_basis
    birth_profile_version: str = settings.canonical_birth_profile_version


class TenGodStockCalendarResponse(SMBaseModel):
    stock: TenGodStockSummary
    versions: TenGodCalendarVersions
    #: 十神口径自描述（与 catalog 同源，避免前端各自解释）。
    day_master_source: str = DAY_MASTER_SOURCE
    other_stem_source: str = OTHER_STEM_SOURCE
    natal: TenGodNatalProfile
    yong_shen: TenGodYongShen = Field(default_factory=TenGodYongShen)
    years: list[TenGodTemporalSegment] = Field(default_factory=list)
    months: list[TenGodTemporalSegment] = Field(default_factory=list)
    days: list[TenGodDayRow] = Field(default_factory=list)
    #: 自然日底表行数（``view=trading`` 时 days 会被显示过滤，本字段不变）。
    natural_day_count: int = 0
    displayed_day_count: int = 0
    trading_day_count: int | None = None
    unknown_trading_day_count: int = 0
    calendar_window_start: date | None = None
    calendar_window_end: date | None = None
    trading_calendar: TenGodTradingCalendarStatus = Field(default_factory=TenGodTradingCalendarStatus)
    view: str = "all"
    filters_applied: dict[str, str] = Field(default_factory=dict)
    warnings: list[Warning_] = Field(default_factory=list)
    disclaimer: str = (
        "十神时历是确定性术数结构的展示，不构成收益预测或交易建议；"
        "十神与喜用匹配是两个独立维度。"
    )


class TenGodDateScanRequest(SMBaseModel):
    """日期 → 全市场十神扫描请求（新端点，不改旧 DateScanRequest 契约）。"""

    date: date
    universe: str = settings.canonical_universe_version
    birth_basis: str = settings.canonical_birth_basis
    birth_profile_version: str = settings.canonical_birth_profile_version
    ten_god_rule_version: str = Field(
        default_factory=lambda: settings.ten_god_rule_version,
        description="只接受 settings.ten_god_rule_version；其他取值返回 422。",
    )
    relation_rule_version: str = Field(
        default_factory=lambda: settings.relation_rule_version,
        description="复合 relation_type 过滤时的矩阵口径，必须与 settings 一致。",
    )
    ten_god: str | None = None
    ten_god_group: str | None = None
    wuxing_role: str | None = None
    verdict: str | None = None
    relation_type: str | None = Field(
        default=None,
        description="与十神条件是 AND 关系；只统计流日行（external_day_row）命中。",
    )
    sort: str = Field(default="stock_code", pattern="^(stock_code|ten_god|s|v|u)$")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)


class TenGodDateScanRow(SMBaseModel):
    stock_code: str
    name: str = ""
    exchange: str = ""
    day_master: str = ""
    #: 权威流日十神：ten_god(股票日主, 目标日干)。
    day_stem: str = ""
    ten_god: str = ""
    ten_god_group: str = ""
    day_stem_wuxing: str = ""
    wuxing_role: str = "未知"
    verdict: str = "未知"
    is_yong_or_xi: bool | None = None
    reason: str = ""
    #: 复合 relation_type 过滤所需的流日行关系类型（去重稳定序）。
    relation_types: list[str] = Field(default_factory=list)
    s_raw: int | None = None
    v_raw: int | None = None
    u_raw: int | None = None
    relation_group: str = "不可用"
    availability: str = "ok"
    unavailable: list[str] = Field(default_factory=list)


class TenGodDateScanVersions(SMBaseModel):
    ten_god_rule_version: str = settings.ten_god_rule_version
    calendar_engine_version: str = ""
    bazi_engine_version: str = ""
    relation_rule_version: str = ""
    relation_matrix_schema_version: str = ""
    birth_basis: str = ""
    birth_profile_version: str = ""
    universe_version: str = ""
    universe_digest: str = ""


class TenGodDateScanResponse(SMBaseModel):
    scan_id: str
    target_date: date
    versions: TenGodDateScanVersions
    #: 股票池语义（未来日期不得假装知道未来上市/退市）。
    universe_mode: str = UNIVERSE_MODE_PIT
    universe_as_of: date | None = None
    future_universe_assumption: str = ""
    observation_time: str = OBSERVATION_TIME
    timezone: str = OBSERVATION_TIMEZONE
    day_master_source: str = DAY_MASTER_SOURCE
    #: 权威流日十神来源声明（不得由 3×3 矩阵格子聚合）。
    ten_god_source: str = "ten_god(stock_day_master, target_day_stem)"
    stock_total: int = 0
    valid_scan_count: int = 0
    #: 过滤后、分页前的集合大小。
    filtered_count: int = 0
    returned_count: int = 0
    offset: int = 0
    limit: int = 100
    #: 以下计数基于"可计算行"全集，与过滤条件无关（合同 §15/§16）。
    ten_god_counts: dict[str, int] = Field(default_factory=dict)
    ten_god_group_counts: dict[str, int] = Field(default_factory=dict)
    verdict_counts: dict[str, int] = Field(default_factory=dict)
    wuxing_role_counts: dict[str, int] = Field(default_factory=dict)
    filtered_ten_god_counts: dict[str, int] = Field(default_factory=dict)
    rows: list[TenGodDateScanRow] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    cache: dict[str, object] = Field(default_factory=dict)
    disclaimer: str = (
        "流日十神由股票日主与目标日日干确定性计算，是结构分类而非收益预测；"
        "十神与喜用匹配相互独立，「正财」不等于「适合」，「七杀」不等于「不适合」。"
    )


__all__ = [
    "DAY_MASTER_SOURCE",
    "DEFAULT_DAYS",
    "DEFAULT_MONTHS",
    "DEFAULT_YEARS",
    "OBSERVATION_TIME",
    "OBSERVATION_TIMEZONE",
    "TEN_GOD_GROUPS",
    "TEN_GOD_SCOPES",
    "TRADING_CALENDAR_SOURCES",
    "UNIVERSE_MODE_LATEST_KNOWN",
    "UNIVERSE_MODE_PIT",
    "VERDICTS",
    "WUXING_ROLES",
    "TenGodCalendarVersions",
    "TenGodCatalogItem",
    "TenGodCatalogResponse",
    "TenGodDateScanRequest",
    "TenGodDateScanResponse",
    "TenGodDateScanRow",
    "TenGodDateScanVersions",
    "TenGodDayRow",
    "TenGodGroupItem",
    "TenGodHiddenStem",
    "TenGodNatalPillar",
    "TenGodNatalProfile",
    "TenGodNatalStem",
    "TenGodRef",
    "TenGodStockCalendarRequest",
    "TenGodStockCalendarResponse",
    "TenGodStockSummary",
    "TenGodTemporalSegment",
    "TenGodTradingCalendarStatus",
    "TenGodYongShen",
]
