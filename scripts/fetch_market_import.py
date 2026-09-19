"""真实历史行情抓取 → 标准离线导入文件（data/import/）。

背景与纪律
----------
当前环境 AKShare 上游（东方财富）被代理拦截不可用。经实测，
腾讯行情端点 ``web.ifzq.gtimg.cn`` 在本环境可达，因此用它抓取**真实**历史行情：

* 个股：**后复权（hfq）日线**。为什么不用 qfq —— 腾讯前复权对高股息老股
  在深历史区间会产生负价格（如 600519 在 2016 年以前为负）并在零点附近震荡，
  使持有期收益率比值的符号翻转，属于数学性损坏而非市场事实；
  hfq 价格恒为正且与累计总回报一致。任何快照请整体重抓，不混用。
* 指数：不复权日线（指数无除权问题）。
* 返回行的字段顺序是腾讯已知的怪癖：[date, open, close, high, low, volume, ...]，
  已在 ``_parse_kline_row`` 中显式处理，并有 OHLC 一致性校验。

产物（全部可被 OfflineMarketDataProvider 直接消费）：
    data/import/bars/{CODE}.csv      个股日线
    data/import/bars/IDX{code}.csv   基准指数日线
    data/import/stocks.csv           股票基础资料（上市日期取自首个 K 线交易日，非人工填写）
    data/import/calendar/SSE.csv     上交所交易日历（由上证指数实测交易日推导）
    data/import/calendar/SZSE.csv    深交所交易日历（由深证成指实测交易日推导）
    data/import/_meta.json           来源、抓取时间、快照说明（合规与可追溯）

本脚本是一次性导入工具，运行期链路不依赖腾讯；
任何时刻换成 AKShare 真实数据源，只需重新运行本脚本或用别的方式生成同构文件。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/fetch_market_import.py
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/fetch_market_import.py --start 2016-01-01
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
IMPORT_DIR = ROOT / "data" / "import"

KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
QUOTE_URL = "https://qt.gtimg.cn/q={symbol}"

#: 20 只验收股票池（覆盖 上交所主板/深交所主板/创业板/科创板/近年上市）。
#: 名称仅作 alias 参考 —— 最终以腾讯行情接口返回的名称为准。
UNIVERSE: list[dict] = [
    {"code": "600519", "alias": "贵州茅台", "industry": "白酒"},
    {"code": "000001", "alias": "平安银行", "industry": "银行"},
    {"code": "300750", "alias": "宁德时代", "industry": "电池"},
    {"code": "688981", "alias": "中芯国际", "industry": "半导体"},
    {"code": "600036", "alias": "招商银行", "industry": "银行"},
    {"code": "000858", "alias": "五粮液", "industry": "白酒"},
    {"code": "601318", "alias": "中国平安", "industry": "保险"},
    {"code": "002594", "alias": "比亚迪", "industry": "汽车整车"},
    {"code": "600000", "alias": "浦发银行", "industry": "银行"},
    {"code": "601899", "alias": "紫金矿业", "industry": "小金属"},
    {"code": "300059", "alias": "东方财富", "industry": "证券"},
    {"code": "600030", "alias": "中信证券", "industry": "证券"},
    {"code": "601012", "alias": "隆基绿能", "industry": "光伏设备"},
    {"code": "000333", "alias": "美的集团", "industry": "白色家电"},
    {"code": "600276", "alias": "恒瑞医药", "industry": "化学制药"},
    {"code": "601888", "alias": "中国中免", "industry": "旅游零售"},
    {"code": "002415", "alias": "海康威视", "industry": "安防设备"},
    {"code": "600887", "alias": "伊利股份", "industry": "乳品"},
    {"code": "601166", "alias": "兴业银行", "industry": "银行"},
    {"code": "000651", "alias": "格力电器", "industry": "白色家电"},
]

BENCHMARKS: list[dict] = [
    {"symbol": "sh000300", "code": "000300", "name": "沪深300"},
]

#: 交易日历推导源（指数自身实测交易日即为历法真值）
CALENDAR_SOURCES: list[dict] = [
    {"symbol": "sh000001", "exchange": "SSE", "name": "上证指数"},
    {"symbol": "sz399001", "exchange": "SZSE", "name": "深证成指"},
]

BAR_FIELDS = ["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_change", "adjust"]


def _market_symbol(code: str) -> str:
    if code.startswith(("600", "601", "688", "900", "11", "5")):
        return f"sh{code}"
    if code.startswith(("000", "001", "002", "003", "300", "301", "2")):
        return f"sz{code}"
    raise ValueError(f"无法推断市场前缀: {code}")


def _http_get(url: str, *, params: dict | None = None, retries: int = 3) -> requests.Response:
    sess = requests.Session()
    sess.trust_env = False  # 本环境代理会拦截部分站点；直连腾讯端点
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(
                url, params=params, timeout=20,
                headers={"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * attempt)
    raise RuntimeError(f"请求失败 {url}: {last}")


def fetch_kline(symbol: str, start: date, end: date, *, adjust: str = "") -> list[list[str]]:
    """按自然年分块抓取（单次上限 ~800 条，按年分块必然完整）。

    腾讯偶发返回 501（瞬时故障），对每个分块做二次退避重试；
    最终失败会抛出并中断整个导入 —— 宁可失败也不留半截数据。

    ``adjust``: ""=不复权 / "qfq"=前复权 / "hfq"=后复权。
    """
    rows: dict[str, list[str]] = {}
    year = start.year
    while year <= end.year:
        chunk_start = date(year, 1, 1)
        chunk_end = min(date(year, 12, 31), end)
        adj = adjust
        last_err: Exception | None = None
        for pause in (0, 3.0, 8.0):
            if pause:
                time.sleep(pause)
            try:
                resp = _http_get(KLINE_URL, params={
                    "param": f"{symbol},day,{chunk_start.isoformat()},{chunk_end.isoformat()},800,{adj}",
                })
                payload = resp.json()
                node = (payload.get("data") or {}).get(symbol) or {}
                series = node.get("hfqday") or node.get("qfqday") or node.get("day") or []
                for raw in series:
                    rows[raw[0]] = raw
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        if last_err is not None:
            raise RuntimeError(
                f"分块 {symbol} {chunk_start}~{chunk_end} 多次重试仍失败: {last_err}"
            ) from last_err
        year += 1
        time.sleep(0.6)  # 礼貌限速：过快会被服务端 WAF 临时封禁
    return [rows[k] for k in sorted(rows)]


def _parse_kline_row(raw: list[str]) -> dict:
    """腾讯 K 线行格式: [date, open, close, high, low, volume, ...]。

    注意顺序怪癖：**open 在前、close 在第 3 位**（不是 OCHL 常规顺序）。
    """
    d, o, c, h, lo = raw[0], float(raw[1]), float(raw[2]), float(raw[3]), float(raw[4])
    vol = float(raw[5]) if len(raw) > 5 and raw[5] not in ("", None) else None
    return {"trade_date": d, "open": o, "high": h, "low": lo, "close": c, "volume": vol}


def _validate_bars(code: str, bars: list[dict]) -> list[str]:
    """基础质量校验：OHLC 关系、正数价格、日期单调。"""
    problems: list[str] = []
    prev = None
    for b in bars:
        if b["close"] is None or b["close"] <= 0:
            problems.append(f"{code} {b['trade_date']} 收盘价非法: {b['close']}")
            continue
        if b["high"] is not None and b["low"] is not None and b["high"] < b["low"]:
            problems.append(f"{code} {b['trade_date']} high < low")
        if b["high"] is not None and (b["high"] < b["close"] or b["high"] < (b["open"] or b["close"])):
            problems.append(f"{code} {b['trade_date']} high 与开收不一致")
        if prev is not None and b["trade_date"] <= prev:
            problems.append(f"{code} {b['trade_date']} 日期非单调递增")
        prev = b["trade_date"]
    return problems


def _write_bars_csv(path: Path, bars: list[dict], *, adjust: str) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(BAR_FIELDS)
    prev_close: float | None = None
    for b in bars:
        pct = None
        if prev_close and b["close"] is not None and b["close"] > 0:
            pct = round((b["close"] / prev_close - 1.0) * 100.0, 4)
        w.writerow([
            b["trade_date"],
            _fmt(b["open"]), _fmt(b["high"]), _fmt(b["low"]), _fmt(b["close"]),
            _fmt(b.get("volume"), 0), "", "", _fmt(pct, 4), adjust or "none",
        ])
        prev_close = b["close"]
    path.write_text(buf.getvalue(), encoding="utf-8")


def _fmt(v: float | None, digits: int = 3) -> str:
    return "" if v is None else f"{v:.{digits}f}"


def fetch_name(symbol: str) -> str:
    try:
        resp = _http_get(QUOTE_URL.format(symbol=symbol))
        payload = resp.text.split("~")
        return payload[1] if len(payload) > 1 else ""
    except Exception:  # noqa: BLE001
        return ""


def cmd_fetch(args: argparse.Namespace) -> int:
    # 全历史抓取：上市日期 = 行情首个交易日，由数据推导而非人工填写
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    bars_dir = IMPORT_DIR / "bars"
    cal_dir = IMPORT_DIR / "calendar"
    bars_dir.mkdir(parents=True, exist_ok=True)
    cal_dir.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    stocks_rows: list[dict] = []

    for meta in UNIVERSE:
        code, symbol = meta["code"], _market_symbol(meta["code"])
        target = bars_dir / f"{code}.csv"
        if target.exists() and args.resume:
            # 断点续传：已完成股票跳过（导入文件是同一快照的一部分，不重抓）
            print(f"[skip] {code} {meta['alias']}（文件已存在）", flush=True)
            lines = target.read_text(encoding="utf-8").splitlines()
            dates = [ln.split(",")[0] for ln in lines[1:] if ln.strip()]
            stocks_rows.append({
                "stock_code": code, "name": meta["alias"],
                "exchange": "SSE" if symbol.startswith("sh") else "SZSE",
                "board": ("科创板" if code.startswith("688") else
                          "创业板" if code.startswith(("300", "301")) else "主板"),
                "industry": meta["industry"],
                "listing_date": dates[0], "first_bar": dates[0],
                "last_bar": dates[-1], "rows": len(dates),
            })
            continue
        print(f"[fetch] {code} {meta['alias']} {start}→{end} ...", flush=True)
        # 个股用 hfq（后复权）：qfq 对高股息老股会在深历史区间出现负价格，
        # 跨零点后收益率符号翻转（如 000001 2009 年反复跨零），会产生荒谬结论。
        raw = fetch_kline(symbol, start, end, adjust="hfq")
        bars = [_parse_kline_row(r) for r in raw]
        problems.extend(_validate_bars(code, bars))
        if not bars:
            problems.append(f"{code} 无数据")
            continue
        _write_bars_csv(bars_dir / f"{code}.csv", bars, adjust="hfq")
        name = fetch_name(symbol) or meta["alias"]
        if name and meta["alias"] not in name and name not in meta["alias"]:
            print(f"  [warn] 名称不一致：alias={meta['alias']} / tencent={name}", flush=True)
        stocks_rows.append({
            "stock_code": code,
            "name": name,
            "exchange": "SSE" if symbol.startswith("sh") else "SZSE",
            "board": ("科创板" if code.startswith("688") else
                      "创业板" if code.startswith(("300", "301")) else "主板"),
            "industry": meta["industry"],
            # 上市日期以行情首个交易日为准（数据推导，非人工填写）
            "listing_date": bars[0]["trade_date"],
            "first_bar": bars[0]["trade_date"],
            "last_bar": bars[-1]["trade_date"],
            "rows": len(bars),
        })
        print(f"  -> {len(bars)} 行，首日 {bars[0]['trade_date']}", flush=True)

    for bench in BENCHMARKS:
        print(f"[fetch] 基准 {bench['code']} {bench['name']} ...", flush=True)
        raw = fetch_kline(bench["symbol"], start, end, adjust="")
        bars = [_parse_kline_row(r) for r in raw]
        problems.extend(_validate_bars(bench["code"], bars))
        _write_bars_csv(bars_dir / f"IDX{bench['code']}.csv", bars, adjust="")
        print(f"  -> {len(bars)} 行", flush=True)

    for cal in CALENDAR_SOURCES:
        print(f"[fetch] 交易日历 {cal['exchange']}（由 {cal['name']} 实测交易日推导）...", flush=True)
        raw = fetch_kline(cal["symbol"], date(1990, 1, 1), end, adjust="")
        days = sorted({r[0] for r in raw})
        (cal_dir / f"{cal['exchange']}.csv").write_text(
            "trade_date\n" + "\n".join(days) + "\n", encoding="utf-8"
        )
        print(f"  -> {len(days)} 个交易日（{days[0]} ~ {days[-1]}）", flush=True)

    with open(IMPORT_DIR / "stocks.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "stock_code", "name", "exchange", "board", "industry",
            "listing_date", "first_bar", "last_bar", "rows",
        ], lineterminator="\n")
        w.writeheader()
        w.writerows(stocks_rows)

    meta = {
        "provider": "tencent_ifzq_gtimg",
        "source_url": KLINE_URL,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "adjust": "hfq",
        "adjust_note": (
            "个股采用后复权（hfq）：腾讯前复权（qfq）对高股息老股在深历史区间"
            "会产生负价格并跨零点震荡，使收益率比值符号翻转（如 000001 2008-2009）。"
            "hfq 价格恒为正且与累计总回报一致，是该快照下的正确选择。"
            "基准指数无复权概念，使用不复权日线。"
        ),
        "snapshot_note": (
            "本目录内全部文件属于同一抓取快照，内部自洽；不同日期抓取的快照"
            "不可混用（复权锚点不同）。研究结论引用时请以 `fetched_at` "
            "作为 market_data_version 快照标识。"
        ),
        "universe": [m["code"] for m in UNIVERSE],
        "benchmarks": [b["code"] for b in BENCHMARKS],
        "calendars": [c["exchange"] for c in CALENDAR_SOURCES],
        "request_window": {"start": start.isoformat(), "end": end.isoformat()},
        "quality_problems": problems,
    }
    (IMPORT_DIR / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    if problems:
        print(f"完成，但有 {len(problems)} 个质量问题（已写入 _meta.json）：")
        for p in problems[:20]:
            print(f"  - {p}")
        return 2
    print("完成：全部数据通过质量校验。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抓取真实历史行情到 data/import/")
    parser.add_argument("--start", default="1990-01-01",
                        help="抓取起始日；默认 1990-01-01（全历史，用于推导真实上市日期）")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="跳过已有完整 CSV 的股票（默认开启）")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("run", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    return cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
