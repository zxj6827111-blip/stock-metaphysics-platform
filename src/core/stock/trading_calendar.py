"""交易日历（TradingCalendarProvider）。

解决什么问题
------------
Phase 1 之前**没有独立交易日历**：

* 上市日落在中秋/春节等节假日时，周末规则无法识别，出生时刻会被错误对齐；
* "未来 5 个交易日"的收益标签必须按**交易日**推进，不能按自然日；
* 停牌日没有行情 bar（自然被跳过），但节假日连 bar 都不存在，需要日历显式判定。

三层覆盖必须分开（把"没有未来行情"和"无法确定未来交易日"分开）
------------------------------------------------------------------
1. **实测层**：``data/import/calendar/{EXCHANGE}.csv`` —— 由指数（上证指数 /
   深证成指）**实测交易日**推导，即真实发生过的交易日，覆盖 1990 年至今。
   这是观测事实，不是规则推算。它**天然只到过去**：没有未来行情，
   不代表无法确定未来交易日。
2. **公布层**：``data/import/calendar/published/{EXCHANGE}.csv`` ——
   交易所**已公告**的未来开市/休市安排（深交所官网逐日标志；上交所休市安排
   公告）。由 ``scripts/update_trading_calendar.py`` 生成，只覆盖已公布范围。
   实测层优先于公布层：已发生的成交事实胜过计划安排。
3. **降级**：两层都不可用（文件缺失）或日期超出两层覆盖时，退化为"周末规则"
   （周一至周五视为交易日），并在 ``CalendarQuery.degraded_reason``
   中明确说明。**绝不静默把周末规则当成正式日历。**

``CalendarQuery.source`` 的取值因此是：
``observed_index_days`` / ``published_exchange_calendar`` /
``out_of_coverage`` / ``weekend_rule_fallback``。

接口：``is_trading_day`` / ``next_trading_day`` / ``prev_trading_day`` /
``add_trading_days`` / ``trading_days_between`` / ``coverage_descriptor``。
"""

from __future__ import annotations

import csv
import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from src.core.config import PROJECT_ROOT

CALENDAR_DIR = PROJECT_ROOT / "data" / "import" / "calendar"

#: 官方已公布日历目录（由 scripts/update_trading_calendar.py 生成）
PUBLISHED_DIR = CALENDAR_DIR / "published"

#: 超出实测覆盖时，向后查找交易日的上限（自然日）
MAX_LOOKAHEAD_DAYS = 40

#: 各交易所的日历文件名（BSE 暂未接入实测数据，恒走降级路径并显式标注）
_EXCHANGE_FILES = {"SSE": "SSE.csv", "SZSE": "SZSE.csv"}

#: 可以当作"已知事实"使用的结果来源。``weekend_rule_fallback`` 不在此列 ——
#: 它是"数据缺失时的近似"，调用方（黄历未来卡、时间窗口）必须自行决定是否接受。
KNOWN_SOURCES = frozenset({"observed_index_days", "published_exchange_calendar"})


@dataclass
class CalendarQuery:
    """一次日历查询的应答，附带数据来源与降级说明。"""

    value: date | bool | int | None
    source: str
    degraded_reason: str = ""


@dataclass
class TradingCalendar:
    """单一交易所的交易日历（实测层 + 官方公布层）。"""

    exchange: str
    _days: frozenset[date] = field(default_factory=frozenset)
    #: 官方公布层：窗口内**每一个自然日**的开市标志（True 开市 / False 休市），
    #: 因此公布窗口内不存在"未知"——每个日期都有官方依据。
    _published: dict[date, bool] = field(default_factory=dict)
    _published_evidence: dict[date, str] = field(default_factory=dict)
    published_meta: dict = field(default_factory=dict)
    published_loaded: bool = False
    published_error: str = ""
    loaded: bool = False
    load_error: str = ""
    #: 内容指纹（加载时算一次）。**不是**区间+行数：
    #: "覆盖区间与行数不变、但某些天的开市标志被修正"同样会改变结果，
    #: 只有对内容本身取哈希才能识别这种更新。
    observed_fingerprint: str = ""
    published_fingerprint: str = ""

    # ------------------------------------------------------------------
    @property
    def coverage(self) -> tuple[date, date] | None:
        """**实测层**覆盖区间（已发生成交的日期范围）。"""
        if not self._days:
            return None
        ordered = sorted(self._days)
        return ordered[0], ordered[-1]

    @property
    def published_coverage(self) -> tuple[date, date] | None:
        """**官方公布层**覆盖区间（交易所已公告的范围）。"""
        if not self._published:
            return None
        ordered = sorted(self._published)
        return ordered[0], ordered[-1]

    @property
    def effective_coverage(self) -> tuple[date, date] | None:
        """两层合并后的可用范围（``None`` 表示两层都不可用）。"""
        ranges = [r for r in (self.coverage, self.published_coverage) if r]
        if not ranges:
            return None
        return min(r[0] for r in ranges), max(r[1] for r in ranges)

    def covers(self, d: date) -> bool:
        """实测层是否覆盖 ``d``。"""
        rng = self.coverage
        return rng is not None and rng[0] <= d <= rng[1]

    def covers_effective(self, d: date) -> bool:
        """实测层或公布层是否覆盖 ``d``。"""
        rng = self.effective_coverage
        return rng is not None and rng[0] <= d <= rng[1]

    def published_flag(self, d: date) -> bool | None:
        """公布层对 ``d`` 的开市标志；不在公布窗口内返回 ``None``。"""
        return self._published.get(d)

    @property
    def version_token(self) -> str:
        """日历内容指纹（进缓存键）。

        日历更新后，"未来 N 个交易日"的答案会变。缓存键里没有这个指纹，
        就可能把更新前的窗口当成更新后的返回 —— 与漏掉一个引擎版本号同类。

        **为什么必须是对内容取哈希**：早期版本用「区间 + 行数 + 生成时间」，
        无法识别"覆盖区间与行数都不变、但某几天的开市标志被修正"的更新
        （例如某日由休市改为开市、或公布层补充了证据）—— 那正是会给出
        错误交易日集合的一类变化。行数相同不代表内容相同。
        """
        return "|".join([
            self.exchange,
            f"o:{self.observed_fingerprint}" if self._days else "o:none",
            f"p:{self.published_fingerprint}" if self._published else "p:none",
            str(self.published_meta.get("generated_at") or ""),
        ])

    def coverage_descriptor(self) -> dict:
        """给上层（API / UI）用的覆盖元数据。

        刻意把三层分开报告 —— 混在一起就无法解释
        "为什么今天之后的日期查不到"到底是哪一层的问题。
        """
        obs = self.coverage
        pub = self.published_coverage
        return {
            "exchange": self.exchange,
            "observed": {
                "loaded": bool(self.loaded),
                "error": self.load_error or None,
                "start": obs[0].isoformat() if obs else None,
                "end": obs[1].isoformat() if obs else None,
                "days": len(self._days),
                "source": "observed_index_days",
            },
            "published": {
                "loaded": bool(self.published_loaded),
                "error": self.published_error or None,
                "start": pub[0].isoformat() if pub else None,
                "end": pub[1].isoformat() if pub else None,
                "days": len(self._published),
                "source": "published_exchange_calendar",
                "generated_at": self.published_meta.get("generated_at"),
                "verified": (self.published_meta.get("cross_validation") or {}).get("verified"),
                "sources": self.published_meta.get("sources"),
                "boundary_cn": self.published_meta.get("boundary_cn"),
            },
        }

    # ------------------------------------------------------------------
    # 核心判定
    # ------------------------------------------------------------------
    def is_trading_day(self, d: date) -> CalendarQuery:
        """是否交易日。

        优先级：**实测层**（已发生的事实）> **官方公布层**（已公告的安排）>
        周末规则（明确标注降级）。超出两层覆盖范围的日期返回 ``None`` 语义
        （未知），不猜测。
        """
        if self.loaded and self.covers(d):
            return CalendarQuery(d in self._days, "observed_index_days")
        flag = self._published.get(d)
        if flag is not None:
            return CalendarQuery(
                flag,
                "published_exchange_calendar",
                f"{self.exchange} 该日不在实测成交记录内，取官方已公布日历"
                f"（证据：{self._published_evidence.get(d, 'unknown')}；"
                f"生成于 {self.published_meta.get('generated_at', '未知')}）。",
            )
        if self.loaded and not self.covers(d):
            # 已加载但越界：明确说"未知"，禁止用周末规则 silently 顶替
            rng = self.coverage
            eff = self.effective_coverage
            return CalendarQuery(
                None,
                "out_of_coverage",
                f"{self.exchange} 实测日历覆盖 {rng[0]}~{rng[1]}"
                + (f"，官方公布日历覆盖 {eff[0]}~{eff[1]}" if self.published_coverage else "，无官方公布日历")
                + f"；{d} 超出全部可用范围。"
                "请先跑 scripts/update_trading_calendar.py 更新日历。",
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
        """``[start, end]`` 闭区间内的交易日数量。

        实测层与公布层按天合并（实测优先）；两层都没覆盖到的日期算"未知"，
        在 ``degraded_reason`` 里报出未知天数 —— 不静默当成休市。
        """
        if not self.loaded and not self.published_loaded:
            # 两层都不可用：退化为周末规则近似并标注
            days = [d for d in _date_range(start, end) if d.weekday() < 5]
            return CalendarQuery(
                len(days), "weekend_rule_fallback",  # type: ignore[arg-type]
                "日历降级：交易日按周末规则近似，节假日未剔除。",
            )

        merged = {d for d in self._days if start <= d <= end}
        if self.published_loaded:
            merged |= {d for d, flag in self._published.items() if flag and start <= d <= end}
        unknown = sum(
            1 for d in _date_range(start, end)
            if not self.covers(d) and d not in self._published
        )
        sources = ["observed_index_days"] if self.loaded else []
        if self.published_loaded:
            sources.append("published_exchange_calendar")
        reason = ""
        if unknown:
            reason = (
                f"{start}~{end} 中有 {unknown} 天既不在实测日历也不在官方公布日历内，"
                "这些日期未计入交易日（不使用周末规则假装肯定）。"
            )
        return CalendarQuery(len(merged), "+".join(sources), reason)  # type: ignore[arg-type]

    # ------------------------------------------------------------------


def _date_range(start: date, end: date):
    """``[start, end]`` 的自然日迭代器。"""
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _fingerprint(text: str) -> str:
    """内容指纹（取前 16 位即可：缓存键去重用途，不是安全用途）。"""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def observed_days_fingerprint(days) -> str:
    """实测层内容指纹：对全部成交日**排序后**取哈希（与迭代顺序无关）。"""
    if not days:
        return ""
    joined = ",".join(d.isoformat() for d in sorted(days))
    return _fingerprint(f"obs:{len(days)}:{joined}")


def published_flags_fingerprint(flags: dict[date, bool]) -> str:
    """公布层内容指纹：对「日期:开市标志」**排序后**取哈希。

    开市标志变了（True↔False）哈希就变 —— 这是行数无法区分的更新类型。
    """
    if not flags:
        return ""
    joined = ",".join(
        f"{d.isoformat()}:{'1' if flag else '0'}" for d, flag in sorted(flags.items())
    )
    return _fingerprint(f"pub:{len(flags)}:{joined}")


class TradingCalendarProvider:
    """按交易所提供交易日历（进程内缓存单例）。

    **缓存会跟着文件变化失效**：只按 exchange 缓存是错的 ——
    `scripts/update_trading_calendar.py` 更新 CSV 后，已经跑着的 API 进程
    会一直返回更新前的日历（以及更新前的 `version_token`，于是连"缓存键变了"
    这条兜底也失效）。这里用文件 mtime 判定是否需要重新加载。
    """

    def __init__(self, calendar_dir: Path | None = None,
                 published_dir: Path | None = None) -> None:
        self._dir = calendar_dir or CALENDAR_DIR
        self._published_dir = published_dir or (self._dir / "published")
        self._cache: dict[str, TradingCalendar] = {}
        self._mtimes: dict[str, tuple] = {}

    def _source_mtimes(self, exchange: str) -> tuple:
        """该交易所全部来源文件的 mtime 签名（缺文件用 None 占位）。"""
        fname = _EXCHANGE_FILES.get(exchange)
        paths = [
            self._dir / fname if fname else None,
            self._published_dir / f"{exchange}.csv",
            self._published_dir / "_meta.json",
        ]
        out = []
        for p in paths:
            if p is None:
                out.append(None)
                continue
            try:
                st = p.stat()
                out.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                out.append((str(p), None, None))
        return tuple(out)

    def for_exchange(self, exchange: str) -> TradingCalendar:
        ex = (exchange or "UNKNOWN").upper()
        signature = self._source_mtimes(ex)
        cached = self._cache.get(ex)
        if cached is not None and self._mtimes.get(ex) == signature:
            return cached
        cal = self._load(ex)
        self._load_published(cal)
        self._cache[ex] = cal
        self._mtimes[ex] = signature
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
            return TradingCalendar(
                exchange=exchange, _days=days, loaded=True,
                observed_fingerprint=observed_days_fingerprint(days),
            )
        except Exception as exc:  # noqa: BLE001
            return TradingCalendar(exchange=exchange, loaded=False,
                                   load_error=f"{type(exc).__name__}: {exc}")

    def _load_published(self, cal: TradingCalendar) -> None:
        """加载官方公布层。

        **交叉校验不通过就不加载**：``_meta.json`` 里 ``verified=false``
        说明 SSE 推导与官方逐日口径不一致，此时宁可用不了，也不给错答案。
        """
        ex = cal.exchange
        if ex not in _EXCHANGE_FILES:
            cal.published_error = f"无 {ex} 的官方公布日历映射（未接入官方来源）"
            return
        path = self._published_dir / f"{ex}.csv"
        if not path.exists():
            cal.published_error = f"官方公布日历不存在: {path}"
            return
        meta: dict = {}
        meta_path = self._published_dir / "_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                meta = {}
        verified = (meta.get("cross_validation") or {}).get("verified")
        if verified is False:
            cal.published_error = (
                "官方公布日历未通过交叉校验（cross_validation.verified=false），"
                "已拒绝加载；请重新运行 scripts/update_trading_calendar.py"
            )
            return
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                flags: dict[date, bool] = {}
                evidence: dict[date, str] = {}
                for row in csv.DictReader(fh):
                    raw = (row.get("trade_date") or "").strip()
                    if not raw:
                        continue
                    d = date.fromisoformat(raw)
                    flags[d] = (row.get("is_open") or "0").strip() == "1"
                    evidence[d] = (row.get("evidence") or "").strip()
            cal._published = flags
            cal._published_evidence = evidence
            cal.published_meta = meta
            cal.published_loaded = bool(flags)
            cal.published_fingerprint = published_flags_fingerprint(flags)
            if not flags:
                cal.published_error = f"官方公布日历为空: {path}"
        except Exception as exc:  # noqa: BLE001
            cal.published_error = f"{type(exc).__name__}: {exc}"


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
    "CALENDAR_DIR", "PUBLISHED_DIR", "KNOWN_SOURCES",
]
