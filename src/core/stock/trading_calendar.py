"""交易日历（TradingCalendarProvider）。

解决什么问题
------------
Phase 1 之前**没有独立交易日历**：

* 上市日落在中秋/春节等节假日时，周末规则无法识别，出生时刻会被错误对齐；
* "未来 5 个交易日"的收益标签必须按**交易日**推进，不能按自然日；
* 停牌日没有行情 bar（自然被跳过），但节假日连 bar 都不存在，需要日历显式判定。

数据来源与降级策略（诚实性约束）
--------------------------------
1. **首选**：``data/import/calendar/{EXCHANGE}.csv`` —— 由指数（上证指数 /
   深证成指）**实测交易日**推导，即真实发生过的交易日，覆盖 1990 年至今。
   这是观测事实，不是规则推算。
2. **降级**：导入文件缺失或日期超出覆盖范围时，退化为"周末规则"
   （周一至周五视为交易日），并在 ``CalendarQuery.degraded_reason``
   中明确说明。**绝不静默把周末规则当成正式日历。**

接口：``is_trading_day`` / ``next_trading_day`` / ``prev_trading_day`` /
``add_trading_days`` / ``trading_days_between``。
"""

from __future__ import annotations

import csv
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from src.core.config import PROJECT_ROOT

CALENDAR_DIR = PROJECT_ROOT / "data" / "import" / "calendar"

#: 超出实测覆盖时，向后查找交易日的上限（自然日）
MAX_LOOKAHEAD_DAYS = 40

#: 各交易所的日历文件名（BSE 暂未接入实测数据，恒走降级路径并显式标注）
_EXCHANGE_FILES = {"SSE": "SSE.csv", "SZSE": "SZSE.csv"}


@dataclass
class CalendarQuery:
    """一次日历查询的应答，附带数据来源与降级说明。"""

    value: date | bool | int | None
    source: str                       # observed_index_days / weekend_rule_fallback / out_of_coverage
    degraded_reason: str = ""


@dataclass
class TradingCalendar:
    """单一交易所的交易日历。"""

    exchange: str
    _days: frozenset[date] = field(default_factory=frozenset)
    loaded: bool = False
    load_error: str = ""

    # ------------------------------------------------------------------
    @property
    def coverage(self) -> tuple[date, date] | None:
        if not self._days:
            return None
        ordered = sorted(self._days)
        return ordered[0], ordered[-1]

    def covers(self, d: date) -> bool:
        rng = self.coverage
        return rng is not None and rng[0] <= d <= rng[1]

    # ------------------------------------------------------------------
    # 核心判定
    # ------------------------------------------------------------------
    def is_trading_day(self, d: date) -> CalendarQuery:
        """是否交易日。

        优先级：实测交易日 > 周末规则（明确标注降级）。
        超出覆盖范围的日期返回 ``None`` 语义（未知），不猜测。
        """
        if self.loaded and self.covers(d):
            return CalendarQuery(d in self._days, "observed_index_days")
        if self.loaded and not self.covers(d):
            # 已加载但越界：明确说"未知"，禁止用周末规则 silently 顶替
            rng = self.coverage
            return CalendarQuery(
                None,
                "out_of_coverage",
                f"{self.exchange} 实测日历覆盖 {rng[0]}~{rng[1]}，{d} 超出范围；"
                "请更新 data/import/calendar/ 或显式接受降级。",
            )
        # 文件缺失：退化为周末规则，显式降级
        return CalendarQuery(
            d.weekday() < 5,
            "weekend_rule_fallback",
            f"{self.exchange} 无实测交易日历（{self.load_error or '文件缺失'}），"
            "按周末规则近似；节假日无法识别。",
        )

    def next_trading_day(self, d: date, *, max_lookahead: int = MAX_LOOKAHEAD_DAYS) -> CalendarQuery:
        """``d`` 当日或之后的首个交易日（含 ``d`` 自身）。"""
        cursor = d
        for _ in range(max_lookahead):
            q = self.is_trading_day(cursor)
            if q.value is True:
                return CalendarQuery(cursor, q.source, q.degraded_reason)
            if q.value is None:
                # 越界：不猜测，直接返回失败
                return CalendarQuery(None, q.source, q.degraded_reason)
            cursor += timedelta(days=1)
        return CalendarQuery(
            None, "exhausted",
            f"自 {d} 起 {max_lookahead} 个自然日内未找到交易日（数据源 {self.exchange}）",
        )

    def prev_trading_day(self, d: date, *, max_lookback: int = MAX_LOOKAHEAD_DAYS) -> CalendarQuery:
        cursor = d
        for _ in range(max_lookback):
            q = self.is_trading_day(cursor)
            if q.value is True:
                return CalendarQuery(cursor, q.source, q.degraded_reason)
            if q.value is None:
                return CalendarQuery(None, q.source, q.degraded_reason)
            cursor -= timedelta(days=1)
        return CalendarQuery(
            None, "exhausted",
            f"自 {d} 向前 {max_lookback} 个自然日内未找到交易日",
        )

    def add_trading_days(self, d: date, n: int) -> CalendarQuery:
        """从 ``d`` 起加 ``n`` 个交易日（``n=0`` 返回 ``d`` 自身的交易日对齐）。"""
        if n < 0:
            return CalendarQuery(None, "unsupported", "暂不支持负向推移")
        step = self.next_trading_day(d)
        if step.value is None:
            return step
        cursor: date = step.value  # type: ignore[assignment]
        for _ in range(n):
            q = self.next_trading_day(cursor + timedelta(days=1))
            if q.value is None:
                return q
            cursor = q.value  # type: ignore[assignment]
        return CalendarQuery(cursor, step.source, step.degraded_reason)

    def trading_days_between(self, start: date, end: date) -> CalendarQuery:
        """``[start, end]`` 闭区间内的交易日列表。"""
        if self.loaded and self.covers(start) and self.covers(end):
            days = sorted(d for d in self._days if start <= d <= end)
            return CalendarQuery(len(days), "observed_index_days")  # type: ignore[arg-type]
        # 降级时按周末规则近似并标注
        days = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor += timedelta(days=1)
        return CalendarQuery(
            len(days), "weekend_rule_fallback",  # type: ignore[arg-type]
            "日历降级：交易日按周末规则近似，节假日未剔除。",
        )

    # ------------------------------------------------------------------


class TradingCalendarProvider:
    """按交易所提供交易日历（进程内缓存单例）。"""

    def __init__(self, calendar_dir: Path | None = None) -> None:
        self._dir = calendar_dir or CALENDAR_DIR
        self._cache: dict[str, TradingCalendar] = {}

    def for_exchange(self, exchange: str) -> TradingCalendar:
        ex = (exchange or "UNKNOWN").upper()
        if ex in self._cache:
            return self._cache[ex]
        cal = self._load(ex)
        self._cache[ex] = cal
        return cal

    def _load(self, exchange: str) -> TradingCalendar:
        fname = _EXCHANGE_FILES.get(exchange)
        if fname is None:
            return TradingCalendar(
                exchange=exchange, loaded=False,
                load_error=f"无 {exchange} 的实测日历映射（当前仅支持 SSE/SZSE）",
            )
        path = self._dir / fname
        if not path.exists():
            return TradingCalendar(
                exchange=exchange, loaded=False,
                load_error=f"日历文件不存在: {path}",
            )
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                days = frozenset(
                    date.fromisoformat(row["trade_date"])
                    for row in csv.DictReader(fh)
                    if row.get("trade_date")
                )
            return TradingCalendar(exchange=exchange, _days=days, loaded=True)
        except Exception as exc:  # noqa: BLE001
            return TradingCalendar(exchange=exchange, loaded=False,
                                   load_error=f"{type(exc).__name__}: {exc}")


_lock = threading.Lock()
_default_provider: TradingCalendarProvider | None = None


def get_trading_calendar_provider() -> TradingCalendarProvider:
    """进程级默认 provider（日历文件在导入数据更新时不会变，按需重建即可）。"""
    global _default_provider
    with _lock:
        if _default_provider is None:
            _default_provider = TradingCalendarProvider()
    return _default_provider


def reset_trading_calendar_provider() -> None:
    """测试用：清空缓存，强制重新加载日历文件。"""
    global _default_provider
    with _lock:
        _default_provider = None


__all__ = [
    "TradingCalendar", "TradingCalendarProvider", "CalendarQuery",
    "get_trading_calendar_provider", "reset_trading_calendar_provider",
    "CALENDAR_DIR",
]
