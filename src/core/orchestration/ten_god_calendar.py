"""股票 → 未来十神时历（TG-2，`ten-god-v1`）。

三条时间轴的边界定义（合同 §12）
--------------------------------
* **流年**：不是 1 月 1 日。区间 ``[本年立春交节时刻, 下一年立春交节时刻)``，
  以 ``CalendarEngine.year_ganzhi`` 的实际翻柱点为准。
* **流月**：不是公历 1 号。只在十二「节」换月柱，
  区间 ``[本次换月节气时刻, 下一换月节气时刻)``。
* **流日**：日级产品，固定 ``12:00:00 Asia/Shanghai`` 取日柱，
  与 Date Scan 的 ``evaluation_time`` 同源（合同 §12.4）。

为什么不能直接取 ``jieqi.next_at`` 当月边界
------------------------------------------
lunar-python 1.4.8 的 ``getPrevJieQi/getNextJieQi`` 形参是 ``whole_day``，
**没有**「只取节」的开关，返回的是全部 24 节气（交节后先看到的是「雨水」「春分」
这类中气）。因此这里用项目自有的十二节白名单做跳步定位。

另外 ``jieqi.current_name`` 在交节**之前**就报出该节气
（2024-02-04 12:00 已报「立春」而月柱仍是乙丑），所以边界计算禁止使用它。

分层约束
--------
本模块只调用 ``CalendarEngine.snapshot()``，不 import ``lunar_python``
（由 ``tests/test_third_party_isolation.py`` 强制）。十神一律走
``src.core.constants.ten_god``；流日判定直接复用 Date Scan 的
``build_day_stem_verdict``，保证两个入口对同一股票同一天给出完全一致的结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.constants import (
    STEM_WUXING,
    TEN_GOD_GROUP,
    TEN_GODS,
    nayin_of,
    twelve_stage,
)
from src.core.relations.date_relation import build_day_stem_verdict
from src.core.relations.ten_god import (
    DAY_MASTER_LABEL,
    count_ten_gods,
    hidden_stems_with_gods,
    role_and_verdict,
    ten_god_ref,
)
from src.core.schemas.bazi import YongShenAnalysis
from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import Warning_
from src.core.schemas.relation import VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN, WUXING_ROLES
from src.core.schemas.stock import StockBirthProfile
from src.core.schemas.ten_god import (
    DEFAULT_DAYS,
    DEFAULT_MONTHS,
    DEFAULT_YEARS,
    OBSERVATION_TIMEZONE,
    TEN_GOD_GROUPS,
    TenGodCalendarVersions,
    TenGodDayRow,
    TenGodNatalPillar,
    TenGodNatalProfile,
    TenGodNatalStem,
    TenGodStockCalendarResponse,
    TenGodStockSummary,
    TenGodTemporalSegment,
    TenGodTradingCalendarStatus,
    TenGodYongShen,
)
from src.core.stock.birth_profile import from_row
from src.core.stock.codes import normalize_code
from src.core.stock.exchange_sessions import ex_value
from src.core.stock.trading_calendar import KNOWN_SOURCES, TradingCalendar, get_trading_calendar_provider
from src.db.models import StockBirthProfileRow, StockMasterRow
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine

SHANGHAI = ZoneInfo(OBSERVATION_TIMEZONE)

#: 换月柱的十二「节」（不含中气）。月柱只在这些点翻柱。
MONTH_BOUNDARY_JIEQI: frozenset[str] = frozenset({
    "立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
})
#: 换年柱的唯一节气。
YEAR_BOUNDARY_JIEQI: str = "立春"

#: 日级标准采样时刻，与 Date Scan 的 evaluation_time 同义。
OBSERVATION_HOUR = 12

#: 一次跳步最多经过多少个节气（24 节气中节/气交替，2 跳必命中；留足冗余并防死循环）。
_MAX_JIEQI_HOPS = 24

_NATAL_POSITIONS: tuple[str, ...] = ("year", "month", "day", "hour")

_CALENDAR = CalendarEngine()


class TenGodCalendarError(ValueError):
    """十神时历构建失败（股票档案缺失、筛选枚举非法、节气边界无法定位）。"""


# ---------------------------------------------------------------------------
# 历法基础设施（进程级缓存：同一天/同一时刻只排一次，与具体股票无关）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PillarReading:
    """某时刻的三柱 + 前后节气。刻意只留小字段，不缓存整个 CalendarSnapshot。"""

    year: str
    month: str
    day: str
    prev_jieqi: str
    prev_at: datetime | None
    next_jieqi: str
    next_at: datetime | None


@lru_cache(maxsize=20000)
def _read(when: datetime) -> PillarReading:
    snapshot = _CALENDAR.snapshot(when)
    return PillarReading(
        year=snapshot.year_ganzhi.text,
        month=snapshot.month_ganzhi.text,
        day=snapshot.day_ganzhi.text,
        prev_jieqi=snapshot.jieqi.prev_name,
        prev_at=snapshot.jieqi.prev_at,
        next_jieqi=snapshot.jieqi.next_name,
        next_at=snapshot.jieqi.next_at,
    )


def _at_noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, OBSERVATION_HOUR)


def _next_allowed_jieqi(after: datetime, allowed: frozenset[str]) -> tuple[str, datetime]:
    """``after`` 之后第一个属于 ``allowed`` 的节气，返回（节气名, 精确时刻）。"""
    cursor = after
    for _ in range(_MAX_JIEQI_HOPS):
        reading = _read(cursor)
        if reading.next_at is None:
            raise TenGodCalendarError(f"{cursor} 之后取不到下一个节气")
        if reading.next_jieqi in allowed:
            return reading.next_jieqi, reading.next_at
        cursor = reading.next_at + timedelta(seconds=1)
    raise TenGodCalendarError(f"{after} 之后 {_MAX_JIEQI_HOPS} 跳内未命中允许的节气")


def _prev_allowed_jieqi(before: datetime, allowed: frozenset[str]) -> tuple[str, datetime]:
    cursor = before
    for _ in range(_MAX_JIEQI_HOPS):
        reading = _read(cursor)
        if reading.prev_at is None:
            raise TenGodCalendarError(f"{cursor} 之前取不到上一个节气")
        if reading.prev_jieqi in allowed:
            return reading.prev_jieqi, reading.prev_at
        cursor = reading.prev_at - timedelta(seconds=1)
    raise TenGodCalendarError(f"{before} 之前 {_MAX_JIEQI_HOPS} 跳内未命中允许的节气")


@dataclass(frozen=True)
class BoundarySegment:
    """一个流月/流年段：半开区间 ``[start_at, end_at)`` 与其干支。"""

    ganzhi_text: str
    boundary_jieqi: str
    start_at: datetime
    end_at: datetime
    next_boundary_jieqi: str


def segment_boundaries(window_start: datetime, count: int, *, kind: str) -> list[BoundarySegment]:
    """从 ``window_start`` **所在的那一段**开始，向后生成 ``count`` 个连续段。

    第一段是当前仍在生效的段（``start_at`` 可能早于 window_start），
    否则「未来 10 年 / 24 个月」会把用户此刻所处的流年/流月丢掉。
    """
    if kind == "year":
        allowed = frozenset({YEAR_BOUNDARY_JIEQI})
    elif kind == "month":
        allowed = MONTH_BOUNDARY_JIEQI
    else:
        raise TenGodCalendarError(f"未知段类型: {kind}")
    if count <= 0:
        return []

    first_name, first_start = _prev_allowed_jieqi(window_start, allowed)
    marks: list[tuple[str, datetime]] = [(first_name, first_start)]
    cursor = first_start
    for _ in range(count):
        name, at = _next_allowed_jieqi(cursor + timedelta(seconds=1), allowed)
        marks.append((name, at))
        cursor = at

    segments: list[BoundarySegment] = []
    for idx in range(count):
        name, start_at = marks[idx]
        next_name, end_at = marks[idx + 1]
        # 段内干支取「翻柱后 1 秒」，避开半开区间端点歧义
        reading = _read(start_at + timedelta(seconds=1))
        segments.append(BoundarySegment(
            ganzhi_text=reading.year if kind == "year" else reading.month,
            boundary_jieqi=name,
            start_at=start_at,
            end_at=end_at,
            next_boundary_jieqi=next_name,
        ))
    return segments


# ---------------------------------------------------------------------------
# 原局十神
# ---------------------------------------------------------------------------
def _ganzhi(text: str) -> GanZhi:
    return GanZhi.from_text(text, nayin=nayin_of(text))


def build_natal_profile(pillars: dict[str, str], day_master: str) -> TenGodNatalProfile:
    """四柱 → 原局天干十神 + 各地支藏干十神。

    日柱天干 ``display_label`` 是「日主」，其规范关系（比肩）仍保留在
    ``ten_god`` 字段中 —— 显示语义与算法语义不合并（合同 §4）。
    """
    result_pillars: list[TenGodNatalPillar] = []
    stem_refs: list[TenGodNatalStem] = []
    hidden_refs = []
    for position in _NATAL_POSITIONS:
        gz = _ganzhi(pillars[position])
        is_day_master = position == "day"
        ref = ten_god_ref(day_master, gz.stem)
        stem = TenGodNatalStem(
            position=position,
            stem=gz.stem,
            wuxing=ref.wuxing,
            ten_god=ref.ten_god,
            ten_god_group=ref.ten_god_group,
            display_label=DAY_MASTER_LABEL if is_day_master else ref.ten_god,
            is_day_master=is_day_master,
        )
        hidden = hidden_stems_with_gods(day_master, gz.branch)
        hidden_refs.extend(hidden)
        stem_refs.append(stem)
        result_pillars.append(TenGodNatalPillar(
            position=position,
            ganzhi=gz,
            stem=stem,
            branch=gz.branch,
            branch_wuxing=gz.branch_wuxing,
            hidden_stems=hidden,
            nayin=gz.nayin,
        ))

    # 日主不计入可见天干统计（与 BaziEngine._ten_god_stats 同口径）；藏干计入。
    visible = [stem for stem in stem_refs if not stem.is_day_master]
    counts, group_counts = count_ten_gods([*visible, *hidden_refs])
    return TenGodNatalProfile(
        day_master=day_master,
        day_master_wuxing=STEM_WUXING.get(day_master, ""),
        pillars=result_pillars,
        visible_stem_ten_gods=[stem.ten_god for stem in visible if stem.ten_god],
        ten_god_counts=counts,
        ten_god_group_counts=group_counts,
    )


# ---------------------------------------------------------------------------
# 流年 / 流月 / 流日行
# ---------------------------------------------------------------------------
def _segment_row(
    kind: str,
    segment: BoundarySegment,
    *,
    day_master: str,
    wish: dict[str, tuple[str, ...]],
) -> TenGodTemporalSegment:
    gz = _ganzhi(segment.ganzhi_text)
    ref = ten_god_ref(day_master, gz.stem)
    role, verdict, _ = role_and_verdict(ref.wuxing, **wish)
    label = "流年" if kind == "year" else "流月"
    return TenGodTemporalSegment(
        kind=kind,
        ganzhi=gz,
        boundary_jieqi=segment.boundary_jieqi,
        next_boundary_jieqi=segment.next_boundary_jieqi,
        stem=gz.stem,
        stem_wuxing=ref.wuxing,
        stem_ten_god=ref.ten_god,
        stem_ten_god_group=ref.ten_god_group,
        branch=gz.branch,
        branch_wuxing=gz.branch_wuxing,
        branch_hidden_stems=hidden_stems_with_gods(day_master, gz.branch),
        di_shi=twelve_stage(day_master, gz.branch),
        start_at=segment.start_at.replace(tzinfo=SHANGHAI),
        end_at=segment.end_at.replace(tzinfo=SHANGHAI),
        stem_wuxing_role=role,
        verdict=verdict,
        reason=(
            f"{label}干{gz.stem}属{ref.wuxing}；相对{day_master}日主的十神为「{ref.ten_god}」"
            f"（分组「{ref.ten_god_group}」）。五行角色「{role}」、喜用匹配「{verdict}」"
            f"是另一套独立维度。{label}段起于{segment.boundary_jieqi}"
            f"，止于{segment.next_boundary_jieqi}（半开区间，不含端点）。"
        ),
    )


def _day_row(
    target: date,
    *,
    day_master: str,
    wish: dict[str, tuple[str, ...]],
    calendar: TradingCalendar,
) -> TenGodDayRow:
    reading = _read(_at_noon(target))
    gz = _ganzhi(reading.day)
    # 流日判定直接调用 Date Scan 的同一个函数：两个入口必须给出同一结果。
    verdict = build_day_stem_verdict(day_master=day_master, day_stem=gz.stem, **wish)
    query = calendar.is_trading_day(target)
    return TenGodDayRow(
        date=target,
        ganzhi=gz,
        stem=gz.stem,
        stem_wuxing=STEM_WUXING.get(gz.stem, ""),
        stem_ten_god=verdict.ten_god,
        ten_god_group=verdict.ten_god_group or TEN_GOD_GROUP.get(verdict.ten_god, ""),
        branch=gz.branch,
        branch_wuxing=gz.branch_wuxing,
        branch_hidden_stems=hidden_stems_with_gods(day_master, gz.branch),
        year_ganzhi=reading.year,
        month_ganzhi=reading.month,
        di_shi=twelve_stage(day_master, gz.branch),
        wuxing_role=verdict.wuxing_role,
        verdict=verdict.verdict,
        is_yong_or_xi=verdict.is_yong_or_xi,
        reason=verdict.reason,
        is_trading_day=query.value,
        trading_calendar_source=query.source,
        trading_calendar_authoritative=query.source in KNOWN_SOURCES,
        trading_calendar_degraded_reason=query.degraded_reason,
    )


# ---------------------------------------------------------------------------
# 股票档案与交易日状态
# ---------------------------------------------------------------------------
def load_birth_profile(
    db: Session,
    code: str,
    birth_basis: str,
    birth_profile_version: str,
) -> tuple[StockBirthProfile, str]:
    """取出生档案 + 股票名称。档案不存在时抛错，不回退到别的版本。"""
    normalized = normalize_code(code)
    row = db.execute(
        select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code == normalized,
            StockBirthProfileRow.birth_basis == birth_basis,
            StockBirthProfileRow.birth_profile_version == birth_profile_version,
        )
    ).scalars().first()
    if row is None:
        raise TenGodCalendarError(
            f"股票 {normalized} 没有 birth_basis={birth_basis} / "
            f"birth_profile_version={birth_profile_version} 的出生档案"
        )
    name = db.execute(
        select(StockMasterRow.name).where(StockMasterRow.stock_code == normalized)
    ).scalars().first() or ""
    return from_row(row), name


def _natal_chart(profile: StockBirthProfile, window_start: date) -> tuple[dict[str, str], str, YongShenAnalysis]:
    """排一次原局盘。原局与 ``as_of`` 无关，但仍需显式参考时点，
    沿用 Date Scan 的 12:00 标准时点口径。
    """
    chart = BaziEngine().build_chart(
        birth_datetime=profile.birth_datetime.replace(tzinfo=None),
        as_of=_at_noon(window_start),
        variant_mode=profile.variant_mode,
        stock_code=profile.stock_code,
    )
    pillars = {
        position: chart.pillar_by_position(position).ganzhi.text
        for position in _NATAL_POSITIONS
    }
    return pillars, chart.day_master, chart.yong_shen


def _wish_map(yong: YongShenAnalysis) -> dict[str, tuple[str, ...]]:
    """喜用忌仇闲五组五行。刻意用**关键字**形式传递，
    因为 ``build_day_stem_verdict`` 的参数全是 keyword-only。
    """
    return {
        "yong_shen": tuple(yong.yong_shen),
        "xi_shen": tuple(yong.xi_shen),
        "ji_shen": tuple(yong.ji_shen),
        "chou_shen": tuple(yong.chou_shen),
        "xian_shen": tuple(yong.xian_shen),
    }


def _trading_calendar_status(calendar: TradingCalendar, rows: list[TenGodDayRow]) -> TenGodTradingCalendarStatus:
    observed = calendar.coverage
    published = calendar.published_coverage
    return TenGodTradingCalendarStatus(
        exchange=calendar.exchange,
        observed_start=observed[0] if observed else None,
        observed_end=observed[1] if observed else None,
        published_start=published[0] if published else None,
        published_end=published[1] if published else None,
        loaded=calendar.loaded,
        published_loaded=calendar.published_loaded,
        load_error=calendar.load_error or None,
        published_error=calendar.published_error or None,
        version_token=calendar.version_token,
        out_of_coverage_days=sum(1 for row in rows if row.trading_calendar_source == "out_of_coverage"),
        degraded_days=sum(1 for row in rows if row.trading_calendar_source == "weekend_rule_fallback"),
        note=(
            "交易日优先级：实测成交记录 > 交易所已公布日历 > 周末规则（降级）。"
            "is_trading_day=null 表示日历未覆盖，不等于休市。"
        ),
    )


_FILTER_ENUMS: dict[str, set[str]] = {
    "ten_god": set(TEN_GODS),
    "ten_god_group": set(TEN_GOD_GROUPS),
    "wuxing_role": set(WUXING_ROLES),
    "verdict": {VERDICT_MATCH, VERDICT_MISMATCH, VERDICT_UNKNOWN},
}


def _validate_filters(filters: dict[str, str]) -> None:
    for key, value in filters.items():
        if value and value not in _FILTER_ENUMS[key]:
            raise TenGodCalendarError(
                f"未知 {key}={value!r}；合法值见 /api/v1/research/ten-gods/catalog"
            )


def _apply_day_filters(rows: list[TenGodDayRow], filters: dict[str, str]) -> list[TenGodDayRow]:
    """四个条件是 AND。过滤只影响显示，不改变任何一行的十神结果。"""
    if not any(filters.values()):
        return rows
    return [
        row for row in rows
        if (not filters["ten_god"] or row.stem_ten_god == filters["ten_god"])
        and (not filters["ten_god_group"] or row.ten_god_group == filters["ten_god_group"])
        and (not filters["wuxing_role"] or row.wuxing_role == filters["wuxing_role"])
        and (not filters["verdict"] or row.verdict == filters["verdict"])
    ]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def build_stock_ten_god_calendar(
    db: Session,
    code: str,
    *,
    start_date: date | None = None,
    years: int = DEFAULT_YEARS,
    months: int = DEFAULT_MONTHS,
    days: int = DEFAULT_DAYS,
    view: str = "all",
    ten_god: str | None = None,
    ten_god_group: str | None = None,
    wuxing_role: str | None = None,
    verdict: str | None = None,
    birth_basis: str = settings.canonical_birth_basis,
    birth_profile_version: str = settings.canonical_birth_profile_version,
) -> TenGodStockCalendarResponse:
    """构造「股票 → 未来十神时历」。

    底层**始终**生成全部自然日；``view="trading"`` 只是显示过滤，
    ``natural_day_count`` 仍报告完整底表行数（合同 §1.1）。
    """
    profile, stock_name = load_birth_profile(db, code, birth_basis, birth_profile_version)
    filters = {
        "ten_god": ten_god or "",
        "ten_god_group": ten_god_group or "",
        "wuxing_role": wuxing_role or "",
        "verdict": verdict or "",
    }
    _validate_filters(filters)

    window_start = start_date or date.today()
    pillars, day_master, yong = _natal_chart(profile, window_start)
    wish = _wish_map(yong)

    exchange = ex_value(profile.exchange)
    calendar = get_trading_calendar_provider().for_exchange(exchange)

    origin = _at_noon(window_start)
    year_segments = [
        _segment_row("year", seg, day_master=day_master, wish=wish)
        for seg in segment_boundaries(origin, years, kind="year")
    ]
    month_segments = [
        _segment_row("month", seg, day_master=day_master, wish=wish)
        for seg in segment_boundaries(origin, months, kind="month")
    ]
    natural_rows = [
        _day_row(window_start + timedelta(step), day_master=day_master, wish=wish, calendar=calendar)
        for step in range(days)
    ]
    trading_status = _trading_calendar_status(calendar, natural_rows)

    displayed = natural_rows
    if view == "trading":
        # 未知（None）不得静默当成休市：保留行并由 UI 显式提示覆盖不足。
        displayed = [row for row in displayed if row.is_trading_day is not False]
    displayed = _apply_day_filters(displayed, filters)

    warnings = [Warning_(
        code="TEN_GOD_STRUCTURAL_ONLY",
        message=(
            "十神与喜用匹配是两个独立维度：十神是传统结构分类，不代表预期收益率、"
            "上涨概率或交易建议。流年按立春、流月按十二节换柱，边界精确到秒。"
        ),
        severity="info",
    )]
    if not any(wish.values()):
        warnings.append(Warning_(
            code="TEN_GOD_YONGSHEN_UNAVAILABLE",
            message="原局喜用忌仇闲集合为空，所有行的五行角色与匹配状态均为「未知」，未冒充「不匹配」。",
            severity="warning",
        ))
    unknown = sum(1 for row in natural_rows if row.is_trading_day is None)
    if unknown:
        warnings.append(Warning_(
            code="TRADING_CALENDAR_OUT_OF_COVERAGE",
            message=(
                f"{unknown} 个自然日超出 {exchange} 的实测与已公布日历覆盖，is_trading_day 返回 null；"
                "「仅交易日」视图保留这些未知行，未当成休市。"
            ),
            severity="warning",
        ))
    if trading_status.degraded_days:
        warnings.append(Warning_(
            code="TRADING_CALENDAR_WEEKEND_FALLBACK",
            message=(
                f"{trading_status.degraded_days} 个自然日仅由周末规则近似（日历文件缺失时的降级路径），"
                "节假日未剔除，必须显式标注为估算。"
            ),
            severity="warning",
        ))
    if view == "trading":
        warnings.append(Warning_(
            code="TEN_GOD_TRADING_VIEW_IS_DISPLAY_ONLY",
            message=(
                f"view=trading 只过滤显示，底层仍完整计算 {len(natural_rows)} 个自然日"
                "（natural_day_count），非交易日的十神结果未丢失。"
            ),
            severity="info",
        ))

    return TenGodStockCalendarResponse(
        stock=TenGodStockSummary(
            stock_code=profile.stock_code,
            name=stock_name,
            exchange=exchange,
            birth_basis=ex_value(profile.birth_basis),
            birth_profile_version=profile.birth_profile_version,
            birth_datetime=profile.birth_datetime,
            timezone=profile.timezone,
            source=profile.source.source,
            data_quality_grade=ex_value(profile.data_quality.grade),
            assumptions=[item.reason for item in profile.assumptions][:8],
            variant_mode=ex_value(profile.variant_mode),
        ),
        versions=TenGodCalendarVersions(
            ten_god_rule_version=settings.ten_god_rule_version,
            calendar_engine_version=settings.calendar_engine_version,
            bazi_engine_version=settings.bazi_engine_version,
            birth_profile_version=profile.birth_profile_version,
            trading_calendar_version_token=trading_status.version_token,
        ),
        natal=build_natal_profile(pillars, day_master),
        yong_shen=TenGodYongShen(
            yong_shen=list(wish["yong_shen"]), xi_shen=list(wish["xi_shen"]),
            ji_shen=list(wish["ji_shen"]), chou_shen=list(wish["chou_shen"]),
            xian_shen=list(wish["xian_shen"]),
            available=any(wish.values()),
        ),
        years=year_segments,
        months=month_segments,
        days=displayed,
        natural_day_count=len(natural_rows),
        displayed_day_count=len(displayed),
        trading_day_count=sum(1 for row in natural_rows if row.is_trading_day is True),
        unknown_trading_day_count=unknown,
        calendar_window_start=window_start,
        calendar_window_end=window_start + timedelta(days=max(days - 1, 0)),
        trading_calendar=trading_status,
        view=view,
        filters_applied={key: value for key, value in filters.items() if value},
        warnings=warnings,
    )


__all__ = [
    "MONTH_BOUNDARY_JIEQI",
    "OBSERVATION_HOUR",
    "YEAR_BOUNDARY_JIEQI",
    "BoundarySegment",
    "PillarReading",
    "TenGodCalendarError",
    "build_natal_profile",
    "build_stock_ten_god_calendar",
    "load_birth_profile",
    "segment_boundaries",
]
