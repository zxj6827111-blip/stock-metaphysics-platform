"""交易所交易时段解析（``exchange_session_calendar``）。

**为什么单独做一个模块**

架构文档反复强调：**禁止把 09:30 写死在业务代码里**。
"股票出生时刻" = 上市首个正式交易日 + 该交易所对应 session 的正式开盘时刻。
未来如果出现：
  * 不同板块不同开盘时间
  * 历史上交易时段变更（如 T+0 试点、延长交易时间）
  * 北交所/港股/美股扩展
只需改配置表，无需改任何业务代码。

配置来源优先级：
    1. SQLite ``exchange_session_calendar`` 表（可由运维覆盖）
    2. 仓库内 ``config/exchange_session_calendar.json``（默认值）
"""

from __future__ import annotations

import json
from datetime import date, time
from functools import lru_cache
from pathlib import Path

from src.core.config import PROJECT_ROOT
from src.core.schemas.common import Exchange
from src.core.schemas.stock import ExchangeSession

CONFIG_PATH = PROJECT_ROOT / "config" / "exchange_session_calendar.json"


def ex_value(exchange: object) -> str:
    """把 Exchange 枚举或字符串统一成字符串值。

    Schema 基类开启了 ``use_enum_values``，因此从 Pydantic 对象拿到的
    exchange 字段可能是 str；这里统一处理，避免调用方到处判断。
    """
    return getattr(exchange, "value", str(exchange))


@lru_cache(maxsize=4)
def _load_config_file(path: str | None = None) -> tuple[dict, ...]:
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        raise FileNotFoundError(f"交易所时段配置缺失: {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    return tuple(payload.get("sessions", []))


def _row_to_session(row: dict) -> ExchangeSession:
    def _parse_time(value: str | None, default: str) -> time:
        raw = (value or default).strip()
        parts = [int(p) for p in raw.split(":")]
        while len(parts) < 3:
            parts.append(0)
        return time(parts[0], parts[1], parts[2])

    def _parse_date(value: str | None) -> date | None:
        return date.fromisoformat(value) if value else None

    return ExchangeSession(
        exchange=Exchange(row.get("exchange", "UNKNOWN")),
        board=row.get("board", "DEFAULT"),
        session_name=row.get("session_name", "continuous_trading"),
        open_time=_parse_time(row.get("open_time"), "09:30:00"),
        close_time=_parse_time(row.get("close_time"), "15:00:00"),
        timezone=row.get("timezone", "Asia/Shanghai"),
        effective_from=_parse_date(row.get("effective_from")),
        effective_to=_parse_date(row.get("effective_to")),
        note=row.get("note", ""),
        source=row.get("source", "config/exchange_session_calendar.json"),
    )


def all_sessions(config_path: str | None = None) -> list[ExchangeSession]:
    """返回配置中的全部交易时段。"""
    return [_row_to_session(r) for r in _load_config_file(config_path)]


def resolve_session(
    exchange: Exchange,
    board: str = "DEFAULT",
    on_date: date | None = None,
    *,
    config_path: str | None = None,
    db_sessions: list[ExchangeSession] | None = None,
) -> tuple[ExchangeSession, str]:
    """按 (交易所, 板块, 日期) 解析出有效交易时段。

    Returns:
        ``(session, matched_key)``，``matched_key`` 形如 ``SSE/科创板``，
        未精确命中板块时会是 ``SSE/DEFAULT``，两者都不命中时为 ``UNKNOWN/DEFAULT``。

    匹配顺序：
        1. 交易所 + 板块（在 effective 区间内）
        2. 交易所 + DEFAULT
        3. UNKNOWN + DEFAULT（兜底）
    """
    sessions = db_sessions if db_sessions is not None else all_sessions(config_path)
    ex = ex_value(exchange)

    def _effective(s: ExchangeSession) -> bool:
        if on_date is None:
            return True
        if s.effective_from and on_date < s.effective_from:
            return False
        return not (s.effective_to and on_date > s.effective_to)

    candidates = [s for s in sessions if _effective(s)]

    for s in candidates:
        if ex_value(s.exchange) == ex and s.board == board:
            return s, f"{ex}/{board}"
    for s in candidates:
        if ex_value(s.exchange) == ex and s.board == "DEFAULT":
            return s, f"{ex}/DEFAULT"
    for s in candidates:
        if ex_value(s.exchange) == "UNKNOWN":
            return s, "UNKNOWN/DEFAULT"

    raise LookupError(f"无法解析交易时段: exchange={ex} board={board} date={on_date}")


def seed_rows() -> list[dict]:
    """把配置文件转成可写入 ``exchange_session_calendar`` 表的数据行。"""
    rows: list[dict] = []
    for s in all_sessions():
        rows.append({
            "exchange": ex_value(s.exchange),
            "board": s.board,
            "session_name": s.session_name,
            "open_time": s.open_time.strftime("%H:%M:%S"),
            "close_time": s.close_time.strftime("%H:%M:%S"),
            "timezone": s.timezone,
            "effective_from": s.effective_from,
            "effective_to": s.effective_to,
            "note": s.note,
            "source": s.source,
        })
    return rows


def sessions_from_db(session_rows: list) -> list[ExchangeSession]:
    """把 ORM 行转换为 Schema 对象。"""
    out: list[ExchangeSession] = []
    for r in session_rows:
        out.append(ExchangeSession(
            exchange=Exchange(r.exchange),
            board=r.board,
            session_name=r.session_name,
            open_time=time.fromisoformat(r.open_time),
            close_time=time.fromisoformat(r.close_time),
            timezone=r.timezone,
            effective_from=r.effective_from,
            effective_to=r.effective_to,
            note=r.note,
            source=r.source,
        ))
    return out
