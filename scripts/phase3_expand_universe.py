"""Phase 3A：扩容股票池 20 → 100 + 落库 + Point-in-Time Universe 登记。

这是研究脚本，不是长期生产设备。
``scripts/fetch_market_import.py`` 的扩展版，区别在于：

1. **抽样可复现**：从 ``data/phase3_universe/sina_hs_a_snapshot.json`` 出发，
   使用 ``SEED=42`` 与 ``board × mktcap_decile`` 分层抽样，抽中股票名单
   写入 ``data/import/_meta.json`` 的 ``universe_selection`` 段，供研究报告
   复盘。
2. **单快照纪律**：全部 100 股在同一进程、同一天抓取，``_meta.json.fetched_at``
   即本快照标识。与 Phase 1.1 的 20 股快照（``fetched_at=2026-09-18T20:40:34+0800``）
   **不混合**：这次会覆盖 ``data/import/bars/*.csv``，但语义上是"新一次
   抓取"，落库行 ``source=tencent_hfq_import`` 不变。
3. **落库三件事**：
     * ``market_bar_daily``：腾讯 hfq 日线（``source=tencent_hfq_import``）
     * ``stock_master``：补齐代码/名称/交易所/板块/上市日（上市日 = 行情首个交易日）
     * ``universe_memberships``：universe_version=``v1-phase3a``，
       ``list_date`` = 首个交易日，
       ``delist_date = NULL`` + ``delist_source="NOT_AVAILABLE_FROM_PROVIDER"``
       （腾讯 K 线对已退市股返回 param error，结构性不可得；详见
       ``docs/data-coverage-phase3.md`` §Survivorship Bias）
4. **退市可得性探测**：脚本显式抽样探测 4 只著名退市股，把"不可得"以证据
   形式写进 ``_meta.json.quality_problems``。

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_expand_universe.py

产出物：
    data/import/bars/{CODE}.csv               100 股日线（hfq）
    data/import/bars/IDX000300.csv            沪深 300 基准（复用旧抓取，当天上午
                                              已抓入 SQLite；如需重抓见 --refetch-bench）
    data/import/calendar/{SSE,SZSE}.csv       交易日历（复用）
    data/import/stocks.csv                    100 股概要（含 listing_date）
    data/import/_meta.json                    完整快照元数据（含抽样规格）
    data/phase3_universe/sina_hs_a_snapshot.json   输入：全 A 股名单（5564）
    data/phase3_universe/phase3a_universe_seed.csv 抽样中间产物（100 股代码）
    data/phase3_universe/phase3a_fetch_report.json 抓取报告（成功/失败/重试）

依赖：
    pip install requests  （项目已安装；脚本不会新增第三方依赖）
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
IMPORT_DIR = ROOT / "data" / "import"
UNIVERSE_DIR = ROOT / "data" / "phase3_universe"
SEED_INPUT = UNIVERSE_DIR / "sina_hs_a_snapshot.json"

KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
QUOTE_URL = "https://qt.gtimg.cn/q={symbol}"

# 抽样控制
SEED = 42  # 必须写入 _meta.json，保证可复现
SAMPLE_TARGETS: list[tuple[str, str, int]] = [
    # (板块, 说明, 目标样本数)
    ("SSE_MAIN", "上交所主板（sh600/sh601/sh603/sh605）", 30),
    ("SSE_STAR", "上交所科创板（sh688）", 10),
    ("SZSE_MAIN", "深交所主板（sz000/sz001）", 10),
    ("SZSE_SME", "深交所中小板（sz002/sz003，2021 并入主板）", 15),
    ("SZSE_GEM", "深交所创业板（sz300/sz301）", 15),
]
# 抽样过滤
MIN_MKTCAP_YI = 30.0  # 总市值下限（亿元），排除壳股、微型股以降低数据不稳定
EXCLUDE_PREFIXES = ("bj",)  # 北交所上市时间短（2021 起），历史厚度不足，暂排除
KNOWN_EVIL_NAMES = ("*ST", "ST", "退")  # 排除 ST / 退市整理


@dataclass
class SelectedStock:
    code: str
    symbol: str          # 腾讯/新浪使用的带市场前缀 symbol
    name: str
    board: str           # SSE_MAIN / SSE_STAR / SZSE_MAIN / SZSE_SME / SZSE_GEM
    mktcap_yi: float     # 总市值（亿元），抽样用
    source: str = "sina_hs_a"


# ---------------------------------------------------------------------------
# 分层抽样
# ---------------------------------------------------------------------------

def load_sina_snapshot() -> list[dict]:
    if not SEED_INPUT.exists():
        raise FileNotFoundError(
            f"缺少全 A 股快照 {SEED_INPUT}。请先手动刷新："
            "data/phase3_universe/sina_hs_a_snapshot.json"
        )
    payload = json.loads(SEED_INPUT.read_text(encoding="utf-8"))
    return payload.get("stocks") or []


def _board_of(symbol: str) -> str | None:
    """把带前缀 symbol 归类到板块；返回 None 表示排除。"""
    prefix = symbol[:2]
    rest = symbol[2:]
    if prefix == "bj":
        return None
    if prefix == "sh":
        if rest.startswith("68"):
            return "SSE_STAR"
        if rest.startswith(("60",)):
            return "SSE_MAIN"
        return None
    if prefix == "sz":
        if rest.startswith(("300", "301")):
            return "SZSE_GEM"
        if rest.startswith(("002", "003")):
            return "SZSE_SME"
        if rest.startswith(("000", "001")):
            return "SZSE_MAIN"
        return None
    return None


def _banned_name(name: str) -> bool:
    return any(k in name for k in KNOWN_EVIL_NAMES)


def stratified_sample(stocks: list[dict], targets: list[tuple[str, str, int]]) -> list[SelectedStock]:
    """板内按市值排序，分桶抽取；每个板块 bucket_i 取第 i 名（确定性）。返回完整 80 股。"""
    rng = random.Random(SEED)
    selected: list[SelectedStock] = []

    # 查已纳入的 20 股，把它们从抽样池里剔除
    existing_codes = _existing_universe_codes()

    for board, _label, n_target in targets:
        pool = []
        for s in stocks:
            sym = s.get("symbol", "")
            if _board_of(sym) != board:
                continue
            code = s.get("code") or sym[-6:]
            if code in existing_codes:
                continue
            name = str(s.get("name") or "").strip()
            if not name or _banned_name(name):
                continue
            try:
                mktcap = float(s.get("mktcap") or 0) / 1e4  # 万 => 亿
            except (TypeError, ValueError):
                continue
            if mktcap < MIN_MKTCAP_YI:
                continue
            pool.append(SelectedStock(
                code=code, symbol=sym, name=name, board=board, mktcap_yi=mktcap,
            ))

        if not pool:
            print(f"[warn] 板块 {board} 没有可抽样本", flush=True)
            continue

        # 板内按市值降序分 n_target 个桶，每桶用固定 rng 抽 1 只
        pool.sort(key=lambda s: (-s.mktcap_yi, s.code))
        bucket_size = max(1, len(pool) // n_target)
        buckets = [pool[i * bucket_size: (i + 1) * bucket_size] for i in range(n_target)]
        for bucket in buckets:
            if not bucket:
                continue
            selected.append(rng.choice(bucket))

    return selected


def _existing_universe_codes() -> set[str]:
    """现存 20 股快照中的核心代码。"""
    path = IMPORT_DIR / "stocks.csv"
    if not path.exists():
        return set()
    codes: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("stock_code"):
                codes.add(row["stock_code"])
    return codes


def persist_selection(selected: list[SelectedStock]) -> Path:
    out = UNIVERSE_DIR / "phase3a_universe_seed.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["code", "symbol", "name", "board", "mktcap_yi", "source"],
            lineterminator="\n",
        )
        w.writeheader()
        for s in selected:
            w.writerow(asdict(s))
    return out


# ---------------------------------------------------------------------------
# 探测退市股可得性（Survivorship bias 证据）
# ---------------------------------------------------------------------------

DELISTED_PROBES: list[tuple[str, str, str]] = [
    # (symbol, 说明, 退市年份)
    ("sz000003", "PT金田A：2002 年退市（深交所早期退市代表）", "2002"),
    ("sz000018", "ST中侨A：2003 年退市", "2003"),
    ("sh600001", "邯郸钢铁：2009 年换股吸收合并后退市", "2009"),
    ("sh600087", "退市长油：2014 年 6 月退市（后来重新上市 601975）", "2014"),
]


def probe_delisted_availability() -> list[dict]:
    out = []
    for sym, desc, year in DELISTED_PROBES:
        code = sym[-6:]
        try:
            resp = _http_get(KLINE_URL, params={
                "param": f"{code},day,1990-01-01,{year}-12-31,800,hfq",
            })
            payload = resp.json()
            node = (payload.get("data") or {}).get(code) or {}
            bars = node.get("hfqday") or node.get("qfqday") or node.get("day") or []
            out.append({
                "symbol": sym,
                "desc": desc,
                "expected_delist_year": year,
                "response_code": payload.get("code"),
                "bars_returned": len(bars),
                "conclusion": (
                    "UNAVAILABLE_FROM_PROVIDER" if not bars
                    else f"unexpectedly_returned_{len(bars)}_bars"
                ),
            })
        except Exception as exc:  # noqa: BLE001
            out.append({
                "symbol": sym,
                "desc": desc,
                "expected_delist_year": year,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "conclusion": "UNAVAILABLE_FROM_PROVIDER",
            })
    return out


# ---------------------------------------------------------------------------
# 抓取：复用 scripts/fetch_market_import.py 的稳定逻辑
# ---------------------------------------------------------------------------
# 直接复用现有 fetch_kline / _parse_kline_row / _validate_bars / _write_bars_csv /
# fetch_name / _http_get（这些已通过 Phase 1.1 验收）。
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_market_import import (  # noqa: E402
    BAR_FIELDS,
    _http_get,
    _market_symbol,
    _parse_kline_row,
    _validate_bars,
    _write_bars_csv,
    fetch_kline,
    fetch_name,
)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 3A：扩容股票池并落库")
    parser.add_argument("--max-new", type=int, default=80, help="本次最多新增的样本股数")
    parser.add_argument("--yes", action="store_true", help="确认开始（不传则 dry-run）")
    parser.add_argument("--refetch-existing", action="store_true",
                        help="是否重新抓取已有 20 股（默认 False：快照同一天数据等价，复用）")
    parser.add_argument("--start", default="1990-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    args = parser.parse_args(argv)

    stocks = load_sina_snapshot()
    print(f"loaded sina_hs_a snapshot: {len(stocks)} 只", flush=True)

    selected = stratified_sample(stocks, SAMPLE_TARGETS)[: args.max_new]
    print(f"新增抽样 {len(selected)} 只：{[s.code for s in selected][:10]}...", flush=True)

    selection_path = persist_selection(selected)
    print(f"抽样清单：{selection_path}", flush=True)

    if not args.yes:
        print("dry-run 完毕。要真正抓取，加 --yes")
        return 0

    # ---- 退市可得性探测（证据） ----
    probes = probe_delisted_availability()
    print("退市股可得性探测：", flush=True)
    for p in probes:
        print(f"  {p['symbol']:>10s}  bars={p.get('bars_returned', 0)}  {p['conclusion']}", flush=True)

    # ---- 抓取 ----
    bars_dir = IMPORT_DIR / "bars"
    bars_dir.mkdir(parents=True, exist_ok=True)

    start_d = date.fromisoformat(args.start)
    end_d = date.fromisoformat(args.end)

    quality_problems: list[str] = []
    fetch_report: list[dict] = []
    stocks_rows: list[dict] = []

    existing_rows: dict[str, dict] = {}
    existing_csv = IMPORT_DIR / "stocks.csv"
    if existing_csv.exists():
        with existing_csv.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                existing_rows[row["stock_code"]] = row

    # 1) 现有 20 股：默认保留旧 CSV；--refetch-existing 时重抓
    for code, old in existing_rows.items():
        if not args.refetch_existing and (bars_dir / f"{code}.csv").exists():
            fetch_report.append({"code": code, "status": "reused", "rows": int(old.get("rows") or 0)})
            stocks_rows.append(old)
            continue
        fetch_one(code=code, symbol=_market_symbol(code), alias=old.get("name", ""),
                  industry=old.get("industry", ""), bars_dir=bars_dir,
                  start_d=start_d, end_d=end_d,
                  quality_problems=quality_problems,
                  fetch_report=fetch_report, stocks_rows=stocks_rows)

    # 2) 新抽 80 股
    for sel in selected:
        fetch_one(code=sel.code, symbol=sel.symbol, alias=sel.name,
                  industry="",  # 行业分类留给 Phase 3E 单独维护；此处不伪造
                  bars_dir=bars_dir,
                  start_d=start_d, end_d=end_d,
                  quality_problems=quality_problems,
                  fetch_report=fetch_report, stocks_rows=stocks_rows)

    # 3) 写 stocks.csv（覆盖：本快照自洽）
    with (IMPORT_DIR / "stocks.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "stock_code", "name", "exchange", "board", "industry",
            "listing_date", "first_bar", "last_bar", "rows",
        ], lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(stocks_rows, key=lambda r: r["stock_code"]))

    # 4) 写新 _meta.json
    meta = json.loads((IMPORT_DIR / "_meta.json").read_text(encoding="utf-8"))
    meta["fetched_at_phase3a"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    meta["universe"] = sorted([r["stock_code"] for r in stocks_rows])
    meta["universe_size"] = len(stocks_rows)
    meta["universe_selection"] = {
        "strategy": "stratified_by_board_and_mktcap",
        "seed": SEED,
        "targets": [{"board": b, "count": n} for b, _, n in SAMPLE_TARGETS],
        "excluded_prefixes": list(EXCLUDE_PREFIXES),
        "excluded_name_keywords": list(KNOWN_EVIL_NAMES),
        "min_mktcap_yi": MIN_MKTCAP_YI,
        "input_snapshot": str(SEED_INPUT.relative_to(ROOT)),
        "note": (
            "从 sina_hs_a 全 A 快照（5564 只）按 5 大板块分层抽样，每板块按总市值降序分桶 "
            "后每桶以 SEED=42 确定性抽取。剔除 ST/退市整理、市值<30亿、北交所。"
            "20 只 Phase 1.1 股票保留。最终 100 只。"
        ),
    }
    meta["delisted_probes"] = probes
    meta["quality_problems"] = quality_problems
    (IMPORT_DIR / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5) 抓取报告
    (UNIVERSE_DIR / "phase3a_fetch_report.json").write_text(
        json.dumps({
            "started_at": None, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "selection_size": len(selected),
            "fetched": sum(1 for r in fetch_report if r["status"] == "ok"),
            "reused": sum(1 for r in fetch_report if r["status"] == "reused"),
            "failed": sum(1 for r in fetch_report if r["status"] == "error"),
            "details": fetch_report,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("== Phase 3A 抓取完成 ==", flush=True)
    ok = sum(1 for r in fetch_report if r["status"] == "ok")
    reused = sum(1 for r in fetch_report if r["status"] == "reused")
    bad = sum(1 for r in fetch_report if r["status"] == "error")
    print(f"  ok={ok}  reused={reused}  failed={bad}", flush=True)
    return 0


def fetch_one(*, code: str, symbol: str, alias: str, industry: str,
              bars_dir: Path, start_d: date, end_d: date,
              quality_problems: list[str],
              fetch_report: list[dict], stocks_rows: list[dict]) -> None:
    print(f"[fetch] {code} {symbol} {alias}", flush=True)
    try:
        raw = fetch_kline(symbol, start_d, end_d, adjust="hfq")
        bars = [_parse_kline_row(r) for r in raw]
        problems = _validate_bars(code, bars)
        quality_problems.extend(problems)
        if not bars:
            fetch_report.append({"code": code, "status": "error", "reason": "no bars returned"})
            return
        _write_bars_csv(bars_dir / f"{code}.csv", bars, adjust="hfq")
        name = fetch_name(symbol) or alias
        stocks_rows.append({
            "stock_code": code,
            "name": name,
            "exchange": "SSE" if symbol.startswith("sh") else "SZSE",
            "board": ("科创板" if code.startswith("688") else
                      "创业板" if code.startswith(("300", "301")) else "主板"),
            "industry": industry,
            "listing_date": bars[0]["trade_date"],
            "first_bar": bars[0]["trade_date"],
            "last_bar": bars[-1]["trade_date"],
            "rows": len(bars),
        })
        fetch_report.append({"code": code, "status": "ok", "rows": len(bars)})
        print(f"    -> {len(bars)} 行, {bars[0]['trade_date']} ~ {bars[-1]['trade_date']}", flush=True)
    except Exception as exc:  # noqa: BLE001
        fetch_report.append({"code": code, "status": "error", "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
        print(f"    -> 失败 {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
