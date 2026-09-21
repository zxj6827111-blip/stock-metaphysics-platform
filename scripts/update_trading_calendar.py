"""交易日历更新（可重复执行、来源可追溯、只增不删）。

为什么需要这个脚本
------------------
"没有未来行情"和"无法确定未来交易日"是两件事，以前被混为一谈：

1. **行情末日** —— ``data/import/bars`` 快照末日，由 ``fetch_market_import.py``
   决定。行情只有已发生的，**天然没有未来**。
2. **实测交易日历末日** —— ``data/import/calendar/{SSE,SZSE}.csv``：
   指数**真实成交过**的日期，是观测事实，同样只能覆盖到过去。
3. **官方已公布日历范围** —— 交易所**公告**的未来交易日安排，
   落在 ``data/import/calendar/published/{SSE,SZSE}.csv``。

只做第 2 层时，"未来 20 个交易日"必然在覆盖之外 —— 那是数据边界，
不是功能缺陷；但也不该就此停止：交易所**已经公布**了未来的休市安排，
把它导入即可支持当前日期之后的交易日查询。本脚本就是做这件事。

来源（每条都记录 URL 与获取时间）
----------------------------------
* **实测层**：腾讯指数日线（``sh000001`` / ``sz399001``），与
  ``fetch_market_import.py`` 同源同口径 —— 只追加新日期，绝不改写历史。
* **SZSE 公布层**：深交所官网「月度交易日」接口，逐日给出开市标志
  （``jybz``：1 开市 / 0 休市），是官方原始口径，无需推断。
* **SSE 公布层**：上交所「休市安排」公告正文里的休市区间。
  公布范围内的交易日 = 工作日 − 已公告休市日。这条推导用的是**交易所自己的规则**
  （周末一律休市，工作日除公告休市外均为交易日），不是"照搬上一年节假日"。
  它必须通过与 SZSE 官方逐日口径的**交叉校验**才会被运行时加载。

诚实性约束
----------
* **不推断未公布年份**：官方尚未公布 2027 年安排，公布窗口就停在 2026-12-31，
  不做"照搬上一年"的延伸。
* **交叉校验不过就不加载**：SSE 公布层与 SZSE 官方口径不一致时，
  标记 ``verified=false``，运行时不使用（宁可用不了，也不给错答案）。
* **BSE 保持显式降级**：北交所没有同等可靠的官方日历导入链路，
  不借用沪深日历冒充。
* **只增不删**：实测层覆盖收缩需要 ``--allow-shrink`` 显式确认，
  避免一次网络故障就把历史日历截断。

用法
----
    python scripts/update_trading_calendar.py            # 更新（实测增量 + 公布全量）
    python scripts/update_trading_calendar.py --check    # 只校验，不写文件
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CALENDAR_DIR = PROJECT_ROOT / "data" / "import" / "calendar"
PUBLISHED_DIR = CALENDAR_DIR / "published"

#: 实测层来源（与 fetch_market_import.py 完全同源）
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
OBSERVED_SOURCES: list[dict] = [
    {"symbol": "sh000001", "exchange": "SSE", "name": "上证指数"},
    {"symbol": "sz399001", "exchange": "SZSE", "name": "深证成指"},
]

#: 公布层来源
SZSE_MONTH_API = "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"
SSE_CLOSED_PAGE = "https://www.sse.com.cn/disclosure/dealinstruc/closed/"

#: 公布层逐日证据类型（写进 CSV，便于逐行核对）
EV_SZSE_API = "szse_official_month_api"          # 官方逐日开市标志
EV_SSE_CLOSURE = "sse_announced_holiday_closure"  # 公告明示休市
EV_SSE_WEEKDAY = "sse_weekday_rule_with_announced_closures"  # 工作日且不在休市清单
EV_WEEKEND = "weekend_closed"

#: SSE 公告里的休市区间："9月25日（星期五）至9月27日（星期日）休市" / "5月6日（星期三）休市"
_CLOSURE_RANGE = re.compile(
    r"(\d{1,2})月(\d{1,2})日（星期[一二三四五六日]）"
    r"(?:至(\d{1,2})月(\d{1,2})日（星期[一二三四五六日]）)?"
    r"休市"
)
_ANNO_NO = re.compile(r"上证公告〔(\d{4})〕(\d+)号")


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def _session() -> requests.Session:
    """与 fetch_market_import.py 同策略：绕过本环境代理，直连数据源。"""
    sess = requests.Session()
    sess.trust_env = False
    return sess


def _get(sess: requests.Session, url: str, *, params: dict | None = None,
         referer: str = "", retries: int = 3) -> requests.Response:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(
                url, params=params, timeout=20,
                headers={"User-Agent": "Mozilla/5.0", "Referer": referer or url},
            )
            resp.raise_for_status()
            # 沪深官网的 HTML 响应头不带 charset，requests 会退回 ISO-8859-1，
            # 中文全部变成乱码（公告正文就再也匹配不到休市区间）。
            if "charset" not in (resp.headers.get("Content-Type") or "").lower():
                resp.encoding = "utf-8"
            return resp
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.2 * attempt)
    raise RuntimeError(f"请求失败 {url}: {last}")


def load_observed_csv(path: Path) -> list[date]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return sorted(
            date.fromisoformat(row["trade_date"])
            for row in csv.DictReader(fh) if row.get("trade_date")
        )


@dataclass
class MergeResult:
    """实测层合并结果。"""

    days: list[date]
    added: list[date]
    dropped: list[date]
    source_truncated: bool


def merge_observed(exchange: str, old: list[date], fresh: list[date],
                   *, allow_shrink: bool) -> MergeResult:
    """实测层合并规则：只增不删。

    历史成交日不会变化。"数据源回得比已有覆盖还短"只可能是抓取被截断或
    数据源异常 —— 那种情况下**宁可中断**（本次不写文件）也不要让历史日历
    被悄悄截断，所以默认直接失败。确认是数据源口径变化时用
    ``--allow-shrink`` 显式放行，此时以数据源为准并记录被丢弃的日期。
    """
    old_set, fresh_set = set(old), set(fresh)
    if not allow_shrink and old and fresh and max(fresh) < max(old):
        raise RuntimeError(
            f"{exchange} 数据源本次只返回到 {max(fresh)}，"
            f"而本地已有覆盖到 {max(old)}：疑似抓取被截断。"
            "已放弃本次更新（未写文件）；确认无误后加 --allow-shrink 重跑。"
        )
    if allow_shrink:
        days = sorted(fresh_set)
        dropped = sorted(old_set - fresh_set)
    else:
        days = sorted(old_set | fresh_set)
        dropped = []
    return MergeResult(
        days=days,
        added=sorted(fresh_set - old_set),
        dropped=dropped,
        source_truncated=bool(old and fresh and max(fresh) < max(old)),
    )


def expand_closure_ranges(text: str, *, publish_date: date | None) -> list[date]:
    """从公告正文里抽出休市日（含区间展开）。

    只认**明示**的休市表述："X月X日（星期X）至X月X日（星期X）休市"
    或单日 "X月X日（星期X）休市"。不推断、不补全未写出的日子。
    """
    out: list[date] = []
    for m in _CLOSURE_RANGE.finditer(text):
        y = publish_date.year if publish_date else date.today().year
        m1, d1 = int(m.group(1)), int(m.group(2))
        # 12 月公告写次年 1 月休市 → 年份跨年
        if publish_date and m1 < publish_date.month - 6:
            y += 1
        start_d = date(y, m1, d1)
        if m.group(3):
            m2, d2 = int(m.group(3)), int(m.group(4))
            end_d = date(y, m2, d2)
        else:
            end_d = start_d
        cur = start_d
        while cur <= end_d:
            out.append(cur)
            cur += timedelta(days=1)
    return out


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8", ) as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


# ----------------------------------------------------------------------
# 第一层：实测交易日历（指数真实成交日）
# ----------------------------------------------------------------------
def fetch_index_trade_days(sess: requests.Session, symbol: str,
                           start: date, end: date) -> list[date]:
    """抓取指数日线并提取成交日。按自然年分块，避免单次条数上限截断。"""
    out: list[date] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(date(chunk_start.year, 12, 31), end)
        resp = _get(sess, KLINE_URL, params={
            "param": f"{symbol},day,{chunk_start.isoformat()},{chunk_end.isoformat()},800,",
        }, referer="https://gu.qq.com/")
        payload = resp.json()
        node = (payload.get("data") or {}).get(symbol) or {}
        # 腾讯统一用 "day" 键（偶发 "qfqday"/"hfqday"，这里无复权 → day）
        rows = node.get("day") or node.get("qfqday") or []
        out.extend(date.fromisoformat(r[0]) for r in rows if r and r[0])
        chunk_start = date(chunk_start.year + 1, 1, 1)
    return sorted(set(out))


def update_observed(sess: requests.Session, *, dry_run: bool,
                    allow_shrink: bool) -> dict:
    """实测层：只追加新成交日，不改历史、不删行。"""
    today = date.today()
    report: dict = {"source_url": KLINE_URL, "exchanges": {}}

    for src in OBSERVED_SOURCES:
        ex = src["exchange"]
        path = CALENDAR_DIR / f"{ex}.csv"
        old = load_observed_csv(path)
        # 回溯 10 个自然日：覆盖"快照当天盘后才有 bar"的情况；
        # 再往前就没必要——历史成交日不会变化，重复抓取只是浪费请求。
        fetch_start = (old[-1] - timedelta(days=10)) if old else date(1990, 1, 1)
        fresh = fetch_index_trade_days(sess, src["symbol"], fetch_start, today)
        merged = merge_observed(ex, old, fresh, allow_shrink=allow_shrink)

        info = {
            "index_symbol": src["symbol"],
            "index_name": src["name"],
            "rows_before": len(old),
            "rows_after": len(merged.days),
            "added": len(merged.added),
            "added_first": merged.added[0].isoformat() if merged.added else None,
            "added_last": merged.added[-1].isoformat() if merged.added else None,
            "dropped": [d.isoformat() for d in merged.dropped],
            "source_truncated": merged.source_truncated,
            "coverage_start": merged.days[0].isoformat() if merged.days else None,
            "coverage_end": merged.days[-1].isoformat() if merged.days else None,
        }
        report["exchanges"][ex] = info
        if not dry_run and merged.days != old:
            _write_csv(path, ["trade_date"], [[d.isoformat()] for d in merged.days])
        print(f"[observed] {ex}: {len(old)} → {len(merged.days)} 行（新增 {len(merged.added)}，"
              f"末日 {info['coverage_end']}）{'[dry-run]' if dry_run else ''}", flush=True)

    return report


# ----------------------------------------------------------------------
# 第二层：官方已公布日历
# ----------------------------------------------------------------------
def fetch_szse_month(sess: requests.Session, month: str) -> list[tuple[date, bool]]:
    """深交所官方月度交易日接口：逐日给出开市标志。"""
    resp = _get(sess, SZSE_MONTH_API, params={"month": month},
                referer="https://www.szse.cn/marketServices/tradingservice/calendar/")
    rows = (resp.json() or {}).get("data") or []
    out: list[tuple[date, bool]] = []
    for row in rows:
        d = row.get("jyrq")
        flag = str(row.get("jybz", ""))
        if not d or flag not in ("0", "1"):
            continue
        out.append((date.fromisoformat(d), flag == "1"))
    return sorted(out)


def fetch_szse_published(sess: requests.Session, start: date, end: date) -> dict[date, bool]:
    """按自然月拉取 SZSE 官方日历，直到某个月完全无数据（= 官方尚未公布）。"""
    out: dict[date, bool] = {}
    cursor = date(start.year, start.month, 1)
    empty_streak = 0
    while cursor <= end:
        month = f"{cursor.year:04d}-{cursor.month:02d}"
        rows = fetch_szse_month(sess, month)
        if not rows:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0
            for d, is_open in rows:
                if start <= d <= end:
                    out[d] = is_open
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def fetch_sse_closures(sess: requests.Session) -> tuple[dict[date, dict], list[dict]]:
    """上交所「休市安排」公告 → 休市日期集合（含每条公告的可追溯信息）。"""
    page = _get(sess, SSE_CLOSED_PAGE, referer="https://www.sse.com.cn/")
    html = page.text
    links: list[tuple[str, str]] = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href, txt = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "休市" in txt and "公告" in txt:
            links.append((href, txt))

    closures: dict[date, dict] = {}
    announcements: list[dict] = []
    for href, title in links:
        url = href if href.startswith("http") else f"https://www.sse.com.cn{href}"
        body = _get(sess, url, referer=SSE_CLOSED_PAGE).text
        text = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;|\s+", " ", text)

        # 公告落款日（正文标题下方第一个 YYYY-MM-DD）
        pub = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        pub_date = date(int(pub.group(1)), int(pub.group(2)), int(pub.group(3))) if pub else None
        anno = _ANNO_NO.search(text)
        anno_no = f"上证公告〔{anno.group(1)}〕{anno.group(2)}号" if anno else None

        found: list[str] = []
        for d in expand_closure_ranges(text, publish_date=pub_date):
            closures[d] = {"announcement": anno_no, "title": title, "url": url}
            found.append(d.isoformat())

        announcements.append({
            "title": title, "url": url,
            "published": pub_date.isoformat() if pub_date else None,
            "announcement_no": anno_no,
            "closure_days": len(found),
            "closure_first": found[0] if found else None,
            "closure_last": found[-1] if found else None,
        })
        print(f"[published] SSE 公告「{title}」→ {len(found)} 个休市日", flush=True)

    return closures, announcements


def build_published(sess: requests.Session, *, window_start: date, year_end: date,
                    dry_run: bool) -> dict:
    """构造公布层：SZSE 用官方逐日标志；SSE 用公告休市清单推导 + 交叉校验。"""
    szse = fetch_szse_published(sess, window_start, year_end)
    if not szse:
        raise RuntimeError("SZSE 官方日历接口无数据，无法构造公布层")
    published_end = max(szse)

    closures, announcements = fetch_sse_closures(sess)

    # SSE 推导：工作日 − 已公告休市（交易所自己的规则：周末一律休市）
    sse: dict[date, tuple[bool, str]] = {}
    cur = window_start
    while cur <= published_end:
        if cur.weekday() >= 5:
            sse[cur] = (False, EV_WEEKEND)
        elif cur in closures:
            sse[cur] = (False, EV_SSE_CLOSURE)
        else:
            sse[cur] = (True, EV_SSE_WEEKDAY)
        cur += timedelta(days=1)

    # 交叉校验：公布窗口内 SSE 推导 vs SZSE 官方逐日口径
    mismatches = [
        {"date": d.isoformat(), "sse": sse[d][0], "szse": szse[d],
         "evidence": sse[d][1]}
        for d in sorted(set(sse) & set(szse)) if sse[d][0] != szse[d]
    ]
    verified = not mismatches

    meta = {
        "generator": "scripts/update_trading_calendar.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "window": {"start": window_start.isoformat(), "end": published_end.isoformat()},
        "sources": [
            {"layer": "SZSE 公布层", "url": SZSE_MONTH_API,
             "note": "深交所官网月度交易日接口，逐日开市标志（官方原始口径）"},
            {"layer": "SSE 公布层", "url": SSE_CLOSED_PAGE,
             "note": "上交所「休市安排」公告；交易日 = 工作日 − 公告休市日"},
        ],
        "sse_announcements": announcements,
        "cross_validation": {
            "rule": "公布窗口内 SSE 推导结果必须与 SZSE 官方逐日口径完全一致",
            "compared_days": len(set(sse) & set(szse)),
            "mismatches": mismatches,
            "verified": verified,
        },
        "assumption_cn": (
            "SSE 公布层的交易日由「工作日 − 已公告休市日」推导，"
            "依据是交易所自身的休市规则（周末一律休市）。"
            "该推导必须通过 SZSE 官方逐日口径的交叉校验；"
            "校验不通过时 verified=false，运行时不加载这一层。"
        ),
        "boundary_cn": (
            "公布层只覆盖交易所**已经公告**的范围；"
            f"当前官方公布到 {published_end.isoformat()}，"
            "超出该日期一律回答「未知」，不照搬上一年安排。"
        ),
        "bse_note_cn": (
            "北交所（BSE）没有同等可靠的官方日历导入链路，"
            "保持显式降级为「无法判定交易日」，不借用沪深日历冒充。"
        ),
    }

    for ex, rows in (("SZSE", {d: (v, EV_SZSE_API) for d, v in szse.items()}), ("SSE", sse)):
        payload = [
            [d.isoformat(), "1" if flag else "0", ev]
            for d, (flag, ev) in sorted(rows.items())
        ]
        if not dry_run:
            _write_csv(PUBLISHED_DIR / f"{ex}.csv",
                       ["trade_date", "is_open", "evidence"], payload)
        print(f"[published] {ex}: {len(payload)} 天（{payload[0][0]} ~ {payload[-1][0]}，"
              f"开市 {sum(1 for r in payload if r[1] == '1')} 天）"
              f"{'' if verified else ' ★交叉校验失败'}"
              f"{'[dry-run]' if dry_run else ''}", flush=True)

    if not dry_run:
        (PUBLISHED_DIR / "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return meta


# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="交易日历更新（实测增量 + 官方公布层）")
    parser.add_argument("--check", action="store_true",
                        help="只抓取与校验，不写文件")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="允许实测层覆盖收缩（仅在确认数据源口径变化时使用）")
    parser.add_argument("--observed-only", action="store_true",
                        help="只更新实测层（不访问交易所公告）")
    args = parser.parse_args(argv)

    dry = args.check
    sess = _session()

    observed = update_observed(sess, dry_run=dry, allow_shrink=args.allow_shrink)

    published: dict | None = None
    if not args.observed_only:
        # 公布窗口从实测末日之后开始：已发生的成交事实优先于计划安排
        obs_end = max(
            date.fromisoformat(v["coverage_end"])
            for v in observed["exchanges"].values() if v["coverage_end"]
        )
        window_start = obs_end + timedelta(days=1)
        # 官方公布到哪一年就拉到哪一年；不跨年外推
        year_end = date(window_start.year, 12, 31)
        published = build_published(sess, window_start=window_start,
                                    year_end=year_end, dry_run=dry)

    summary = {
        "observed": observed,
        "published_window": (published or {}).get("window"),
        "cross_validation": (published or {}).get("cross_validation"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if published and not published["cross_validation"]["verified"]:
        print("★ SSE 公布层交叉校验未通过：运行时不会加载该层。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
