"""A 股代码规范化与交易所/板块识别。

支持输入形式：
    ``600519`` / ``600519.SH`` / ``sh600519`` / ``SH600519`` / ``600519.XSHG``

输出统一为 ``(stock_code, Exchange, board, wind_code)``。
"""

from __future__ import annotations

import re

from src.core.schemas.common import Exchange

_CODE_RE = re.compile(r"(\d{6})")

# 板块判定规则：按代码前缀（A 股现行规则）
_BOARD_RULES: tuple[tuple[re.Pattern[str], Exchange, str], ...] = (
    (re.compile(r"^(60[0135]|601|603|605|688|689|900)"), Exchange.SSE, "主板"),
    (re.compile(r"^68[89]"), Exchange.SSE, "科创板"),
    (re.compile(r"^(000|001|002|003|200)"), Exchange.SZSE, "主板"),
    (re.compile(r"^(300|301)"), Exchange.SZSE, "创业板"),
    (re.compile(r"^(43|83|87|88|92)"), Exchange.BSE, "北交所"),
)

# 精确前缀表（优先级高于上面的宽松规则）
_PREFIX_BOARD: tuple[tuple[str, Exchange, str], ...] = (
    ("688", Exchange.SSE, "科创板"),
    ("689", Exchange.SSE, "科创板"),
    ("600", Exchange.SSE, "主板"),
    ("601", Exchange.SSE, "主板"),
    ("603", Exchange.SSE, "主板"),
    ("605", Exchange.SSE, "主板"),
    ("900", Exchange.SSE, "主板"),
    ("000", Exchange.SZSE, "主板"),
    ("001", Exchange.SZSE, "主板"),
    ("002", Exchange.SZSE, "主板"),
    ("003", Exchange.SZSE, "主板"),
    ("200", Exchange.SZSE, "主板"),
    ("300", Exchange.SZSE, "创业板"),
    ("301", Exchange.SZSE, "创业板"),
    ("430", Exchange.BSE, "北交所"),
    ("830", Exchange.BSE, "北交所"),
    ("831", Exchange.BSE, "北交所"),
    ("832", Exchange.BSE, "北交所"),
    ("833", Exchange.BSE, "北交所"),
    ("834", Exchange.BSE, "北交所"),
    ("835", Exchange.BSE, "北交所"),
    ("836", Exchange.BSE, "北交所"),
    ("837", Exchange.BSE, "北交所"),
    ("838", Exchange.BSE, "北交所"),
    ("839", Exchange.BSE, "北交所"),
    ("870", Exchange.BSE, "北交所"),
    ("871", Exchange.BSE, "北交所"),
    ("872", Exchange.BSE, "北交所"),
    ("873", Exchange.BSE, "北交所"),
    ("920", Exchange.BSE, "北交所"),
)

EXCHANGE_SUFFIX: dict[Exchange, str] = {
    Exchange.SSE: "SH",
    Exchange.SZSE: "SZ",
    Exchange.BSE: "BJ",
    Exchange.UNKNOWN: "",
}


def normalize_code(raw: str) -> str:
    """提取 6 位股票代码。

    Raises:
        ValueError: 无法解析出 6 位数字代码。
    """
    if not raw or not str(raw).strip():
        raise ValueError("股票代码为空")
    match = _CODE_RE.search(str(raw).strip())
    if not match:
        raise ValueError(f"无法解析股票代码: {raw!r}")
    return match.group(1)


def detect_exchange(code: str) -> Exchange:
    """按代码前缀识别交易所。"""
    for prefix, exchange, _board in _PREFIX_BOARD:
        if code.startswith(prefix):
            return exchange
    for pattern, exchange, _board in _BOARD_RULES:
        if pattern.match(code):
            return exchange
    # 交易所后缀兜底
    return Exchange.UNKNOWN


def detect_board(code: str) -> str:
    """按代码前缀识别板块。"""
    for prefix, _exchange, board in _PREFIX_BOARD:
        if code.startswith(prefix):
            return board
    return "未知"


def to_wind_code(code: str, exchange: Exchange | None = None) -> str:
    """生成带交易所后缀的代码，如 ``600519.SH``。"""
    ex = exchange or detect_exchange(code)
    suffix = EXCHANGE_SUFFIX.get(ex, "")
    return f"{code}.{suffix}" if suffix else code


def parse(raw: str) -> tuple[str, Exchange, str, str]:
    """一站式解析。

    Returns:
        ``(stock_code, exchange, board, wind_code)``
    """
    code = normalize_code(raw)
    exchange = detect_exchange(code)
    board = detect_board(code)
    return code, exchange, board, to_wind_code(code, exchange)


def market_prefix(code: str, exchange: Exchange | None = None) -> str:
    """返回东财 secid 前缀：1 = 上交所，0 = 深交所/北交所。"""
    ex = exchange or detect_exchange(code)
    return "1" if ex == Exchange.SSE else "0"
