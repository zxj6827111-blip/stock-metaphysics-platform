"""未来交易日黄历（"黄历 / 日课详情"页的「未来 N 个交易日黄历」分区）。

这一层解决什么问题
------------------
页面需要的是"**基准日当日或之后的前 N 个有效交易日**"的黄历，
而 ``HuangliEngine`` 只会算"从某时刻起连续 N 个**自然日**"。

两者**不能互相冒充**：
* 自然日窗口里周末与长假是空壳，把它们当日期卡会凭空多出"非交易日"；
* 前端的「排除周末」近似识别不了长假（春节 / 国庆连休），
  会把休市日当成交易日。

因此本模块用 ``TradingCalendarProvider``（实测交易日历，来自指数真实成交日）
枚举交易日，再逐日取 ``HuangliEngine`` 的确定性结果。

数据边界（诚实性约束）
----------------------
* 基准日**不是**交易日时，从其后首个交易日开始，并在响应中标注该规则；
* 交易日历覆盖不足时**不猜测**：返回实际能覆盖的天数 +
  ``coverage.explanation_cn``，绝不补零、绝不假装肯定（AGENTS.md §2.4）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from src.core.orchestration.huangli_day_class import (
    HUANGLI_DAY_CLASS_VERSION,
    class_rule_descriptor,
    day_payload,
)
from src.core.stock.trading_calendar import get_trading_calendar_provider
from src.engines.calendar.calendar_engine import WEEKDAY_CN
from src.engines.huangli.huangli_engine import HuangliEngine

#: 序列化口径版本（响应字段增删需提升）
HUANGLI_OUTLOOK_VERSION = "huangli-outlook-v1"

#: 默认"近 N 个交易日"
DEFAULT_TRADING_DAYS = 20
#: 上限：黄历单日约 4–5ms，90 天仍是亚秒级；超过就没有 UI 意义了
MAX_TRADING_DAYS = 90
#: "近 3 个月"模式上限
MAX_MONTHS = 3

#: 自然日扫描上限（交易日一定少于自然日；留足长假余量）
_MAX_CALENDAR_DAYS = 5 * 366

MODE_TODAY = "today"
MODE_TRADING_DAYS = "trading_days"
MODE_MONTHS = "months"


def _is_trading_day(calendar, d: date) -> bool | None:
    """``True`` / ``False`` / ``None``（超出实测覆盖 → 未知，不猜）。"""
    try:
        q = calendar.is_trading_day(d)
    except Exception:  # noqa: BLE001 - 日历不可用时如实降级为"未知"
        return None
    # 只接受**实测**指数成交日。文件缺失时 TradingCalendar 会退化为"周末规则"
    # 并标注 source=weekend_rule_fallback —— 那条路径识别不了长假，
    # 用它产出未来日期卡等于把春节连休当成交易日，因此归为"未知"。
    if q.source != "observed_index_days":
        return None
    if q.value is None:
        return None
    return bool(q.value)


def _month_end(year: int, month: int) -> date:
    import calendar as _cal

    return date(year, month, _cal.monthrange(year, month)[1])


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    m = month + delta
    return year + (m - 1) // 12, (m - 1) % 12 + 1


def _enumerate_trading_days(
    calendar,
    *,
    start: date,
    limit: int,
    hard_end: date | None = None,
) -> tuple[list[date], int, date | None]:
    """从 ``start`` 起枚举交易日。

    Returns:
        ``(交易日, 因日历越界而未知的自然日数, 首个未知日期)``。
        遇到"未知"日期时**立即停止**，因为越过日历边界后无法再判断任何一天，
        继续扫描只会把未知当成非交易日（那是伪装成「休市」的猜测）。
    """
    out: list[date] = []
    cursor = start
    unknown = 0
    first_unknown: date | None = None
    for _ in range(_MAX_CALENDAR_DAYS):
        if hard_end is not None and cursor > hard_end:
            break
        flag = _is_trading_day(calendar, cursor)
        if flag is None:
            unknown += 1
            first_unknown = cursor
            break
        if flag:
            out.append(cursor)
            if len(out) >= limit:
                break
        cursor += timedelta(days=1)
    return out, unknown, first_unknown


def build_huangli_outlook(
    *,
    as_of: datetime,
    exchange: str = "SSE",
    mode: str = MODE_TRADING_DAYS,
    days: int = DEFAULT_TRADING_DAYS,
    months: int = MAX_MONTHS,
    engine: HuangliEngine | None = None,
) -> dict:
    """构建"未来交易日黄历"视图。

    Args:
        as_of: 分析基准日（页面上的"分析基准"）。
        exchange: 交易所（决定用哪份实测日历）。
        mode: ``today`` / ``trading_days`` / ``months``。
        days: ``trading_days`` 模式的交易日数量。
        months: ``months`` 模式的自然月数量（含基准日所在月）。
    """
    huangli = engine or HuangliEngine()
    calendar = get_trading_calendar_provider().for_exchange(exchange)
    coverage = calendar.coverage
    anchor = as_of.date()

    if mode not in (MODE_TODAY, MODE_TRADING_DAYS, MODE_MONTHS):
        raise ValueError(f"未知的 outlook mode: {mode}")

    warnings: list[dict] = []
    unknown_days = 0
    first_unknown: date | None = None
    anchor_is_trading_day: bool | None = _is_trading_day(calendar, anchor)

    if mode == MODE_TODAY:
        # "今日"只问基准日当天，不要求它是交易日（基准日可能就是休市日）
        target_dates = [anchor]
        rule_cn = "展示分析基准日当日的黄历；基准日是否为交易日单独标注。"
    elif mode == MODE_MONTHS:
        months = max(1, min(int(months), MAX_MONTHS))
        y, m = _add_months(anchor.year, anchor.month, months - 1)
        hard_end = _month_end(y, m)
        target_dates, unknown_days, first_unknown = _enumerate_trading_days(
            calendar, start=anchor, limit=MAX_TRADING_DAYS, hard_end=hard_end
        )
        rule_cn = (
            f"自分析基准日（{anchor.isoformat()}）起，到第 {months} 个月末"
            f"（{hard_end.isoformat()}）为止的**全部交易日**。"
        )
    else:
        days = max(1, min(int(days), MAX_TRADING_DAYS))
        target_dates, unknown_days, first_unknown = _enumerate_trading_days(
            calendar, start=anchor, limit=days
        )
        rule_cn = (
            f"自分析基准日（{anchor.isoformat()}）当日或之后的首个有效交易日起，"
            f"连续 {days} 个交易日。"
        )

    if mode != MODE_TODAY and anchor_is_trading_day is False:
        rule_cn += "基准日不是交易日，已从其后首个交易日开始。"

    payload_days = [
        {
            **day_payload(huangli.day_for(d), weekday_cn=WEEKDAY_CN[d.weekday()]),
            "is_trading_day": True,
            "offset_trading_days": i + 1,
        }
        for i, d in enumerate(target_dates)
    ]

    # 按自然月分组（长区间用月历/分组展示，避免 90 张卡片无限撑高页面）
    month_groups: list[dict] = []
    for item in payload_days:
        key = item["date"][:7]
        if not month_groups or month_groups[-1]["month"] != key:
            month_groups.append({"month": key, "dates": []})
        month_groups[-1]["dates"].append(item["date"])

    # --- 覆盖说明：把"为什么只有这么多天"讲清楚 ---
    requested = days if mode == MODE_TRADING_DAYS else None
    if mode == MODE_TODAY:
        coverage_status = "complete"
    elif not target_dates:
        coverage_status = "unavailable"
    elif unknown_days:
        coverage_status = "partial"
    elif requested is not None and len(target_dates) < requested:
        coverage_status = "partial"
    else:
        coverage_status = "complete"

    explanation = _coverage_explanation(
        status=coverage_status,
        exchange=exchange,
        calendar_loaded=calendar.loaded,
        calendar_error=calendar.load_error,
        coverage=coverage,
        anchor=anchor,
        returned=len(target_dates),
        requested=requested,
        mode=mode,
        first_unknown=first_unknown,
        unknown_days=unknown_days,
    )
    if coverage_status == "partial":
        warnings.append({
            "code": "HUANGLI_OUTLOOK_CALENDAR_PARTIAL",
            "severity": "warning",
            "message": explanation,
        })
    elif coverage_status == "unavailable":
        warnings.append({
            "code": "HUANGLI_OUTLOOK_CALENDAR_UNAVAILABLE",
            "severity": "warning",
            "message": explanation,
        })

    return {
        "outlook_version": HUANGLI_OUTLOOK_VERSION,
        "class_rule_version": HUANGLI_DAY_CLASS_VERSION,
        "engine_version": huangli.engine_version,
        "exchange": exchange,
        "as_of": as_of.isoformat(),
        "anchor_date": anchor.isoformat(),
        "anchor_is_trading_day": anchor_is_trading_day,
        "mode": mode,
        "requested_days": requested,
        "requested_months": months if mode == MODE_MONTHS else None,
        "returned_days": len(payload_days),
        "rule_cn": rule_cn,
        "coverage": {
            "status": coverage_status,
            "explanation_cn": explanation,
            "calendar_loaded": bool(calendar.loaded),
            "calendar_source": "observed_index_days" if calendar.loaded else "unavailable",
            "calendar_coverage": (
                {"start": coverage[0].isoformat(), "end": coverage[1].isoformat()}
                if coverage
                else None
            ),
            "unknown_days": unknown_days,
            "first_unknown_date": first_unknown.isoformat() if first_unknown else None,
        },
        "class_rule": class_rule_descriptor(),
        "month_groups": month_groups,
        "days": payload_days,
        "warnings": warnings,
        "methodology_cn": (
            "交易日来自 TradingCalendarProvider 的**实测**指数成交日序列"
            "（data/import/calendar/<EXCHANGE>.csv），不是「排除周末」的近似；"
            "黄历字段来自 HuangliEngine（lunar-python 通书口径），前端不重算历法。"
        ),
    }


def _coverage_explanation(
    *,
    status: str,
    exchange: str,
    calendar_loaded: bool,
    calendar_error: str,
    coverage: tuple[date, date] | None,
    anchor: date,
    returned: int,
    requested: int | None,
    mode: str,
    first_unknown: date | None,
    unknown_days: int,
) -> str:
    if not calendar_loaded:
        return (
            f"{exchange} 没有可用的实测交易日历（{calendar_error or '文件缺失'}），"
            "无法判定交易日，因此**不产出**任何未来日期卡"
            "（不以「排除周末」近似冒充交易日历）。"
        )
    span = f"{coverage[0].isoformat()} ~ {coverage[1].isoformat()}" if coverage else "未知"
    if status == "unavailable":
        return (
            f"分析基准日 {anchor.isoformat()} 起没有可用的实测交易日："
            f"{exchange} 日历覆盖 {span}，该区间落在覆盖范围之外。"
            "页面保留完整结构但不补造日期；请等待日历数据更新，"
            "或把分析基准日设为覆盖范围内的日期。"
        )
    if status == "partial":
        if unknown_days:
            return (
                f"实测日历覆盖到 {coverage[1].isoformat() if coverage else '未知'}"
                f"（{exchange}，{span}）。请求的未来日期已越过该边界"
                f"（首个越界日 {first_unknown.isoformat() if first_unknown else '未知'}），"
                f"因此只返回边界前的 {returned} 个交易日，"
                "其余日期**未知**而非「休市」——不猜测、不补零。"
            )
        return (
            f"只为 {exchange} 找到 {returned} 个交易日，"
            f"少于请求的 {requested if requested is not None else '（月区间）'}："
            "区间内的交易日数量本身不足（例如区间正好落在长假上）。"
        )
    unit = "个交易日" if mode != MODE_TODAY else "日"
    return f"已返回 {returned} {unit}，全部落在实测交易日历覆盖区间（{span}）之内。"


__all__ = [
    "HUANGLI_OUTLOOK_VERSION",
    "DEFAULT_TRADING_DAYS",
    "MAX_TRADING_DAYS",
    "MAX_MONTHS",
    "MODE_TODAY",
    "MODE_TRADING_DAYS",
    "MODE_MONTHS",
    "build_huangli_outlook",
]
