"""Phase 3A：从 E:\\AStockData 落库 canon universe + universe_memberships。

工作流
======

1. **加载 PIT universe**：``pit_universe_1d_20260717_bdd82bb209bd.json``（5,868 只）
2. **加载 manifest**：``internal_composite_none_1d_20260814_a8dd1b07beee.json``（5,541 只 bars）
3. **抽样**：``sample_phase3a_universe()`` 按 GOAL 500 只目标构建：
     - 全部 SSE/SZSE 退市股（≈333 只）：强制纳入（消除退市股挑选偏差）
     - 每个 era×board 桶：配额式抽满剩余 167 只
     - 确定性 seed=42，``_meta.json`` 写抽样配置
4. **落库**：
     - ``stock_master``：补齐基本字段
     - ``universe_memberships`` 版本 ``v2-phase3a``：``list_date / delist_date`` 均为真值
     - ``market_bar_daily`` ``source="astockdata_composite_none"`` 全军入库
     - （可选）``--max-stocks N`` / ``--include-delisted`` 控制

幂等：可重复运行；同 code 的 bars 先 delete 再 insert；membership 按
``(universe_version, stock_code)`` 先 delete 再 insert。删干净现有
``v1-phase3a``（因为那是腾讯通道的半成品）。

运行：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_import_astockdata.py
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_import_astockdata.py --max-stocks 500 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select  # noqa: E402

from src.db.base import init_db, session_scope  # noqa: E402
from src.db.models import (  # noqa: E402
    MarketBarDailyRow,
    StockMasterRow,
    UniverseMembershipRow,
)
from src.market.providers.astockdata_store import AStockDataBlobStore  # noqa: E402

ASTOCK_ROOT = Path(r"E:\AStockData")
# 直接使用 dict：避免 import pit_universe JSON 时产生依赖循环
PIT_UNIVERSE_PATH = (
    ASTOCK_ROOT / "datasets/market_data/universes/pit_universe_1d_20260717_bdd82bb209bd.json"
)
UNIVERSE_VERSION = "v2-phase3a"
BAR_SOURCE = "astockdata_composite_none"
SNAPSHOT_LABEL = "astockdata_composite_none_20260814"


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------


def load_pit_universe() -> dict[str, dict]:
    """读取 pit_universe JSON，返回 ``{stock_code: entry_dict}``。"""
    payload = json.loads(PIT_UNIVERSE_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for e in payload["entries"]:
        code = e["ts_code"].split(".")[0]
        out[code] = {
            "ts_code": e["ts_code"],
            "exchange": e["exchange"],
            "board": e["board"],
            "name": e["name"],
            "list_status": e["list_status"],
            "list_date": _int_to_date(e["list_date"]),
            "delist_date": _int_to_date(e["delist_date"]) if e.get("delist_date") else None,
            "last_trade_date": _int_to_date(e["last_trade_date"]) if e.get("last_trade_date") else None,
        }
    return out


def _int_to_date(v: int | str | None) -> date | None:
    if v is None or v == "":
        return None
    s = str(v).strip()
    if not s or s == "None":
        return None
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


# ---------------------------------------------------------------------------
# 抽样
# ---------------------------------------------------------------------------


@dataclass
class UniversePick:
    stock_code: str
    reason: str        # "delisted" | "active"
    stratum: str       # e.g. "sse_main:2000s"


def sample_phase3a_universe(
    pit: dict[str, dict],
    *,
    max_total: int = 500,
    seed: int = 42,
) -> tuple[list[UniversePick], dict]:
    """分层抽样：

    * 必选：全部 SSE/SZSE 已退市股（``list_status == 'D'``），约 333 只。
    * 剩余配额 ``max_total - len(delisted)``：从 L 中按 ``listing_era × board`` 分层抽取。
    """
    delisted = sorted([
        (c, e) for c, e in pit.items()
        if e["list_status"] == "D" and e["exchange"] in ("SSE", "SZSE")
    ], key=lambda kv: kv[0])

    rng = random.Random(seed)
    picks: list[UniversePick] = []

    for code, e in delisted:
        era = _era_label(e["list_date"])
        picks.append(UniversePick(stock_code=code, reason="delisted",
                                  stratum=f"{e['exchange'].lower()}_{e['board']}:{era}"))

    quota = max_total - len(picks)
    # 在册（L）票源
    actives = [
        (c, e) for c, e in pit.items()
        if e["list_status"] == "L" and e["exchange"] in ("SSE", "SZSE")
    ]
    # 分桶：board_group x listing_era
    buckets: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for c, e in actives:
        era = _era_label(e["list_date"])
        key = f"{e['exchange'].lower()}_{e['board']}:{era}"
        buckets[key].append((c, e))

    # 按桶大小比例分配配额；桶内确定性抽（rng.choice on sorted bucket）
    bucket_keys = sorted(buckets.keys())
    total_active = len(actives)
    per_bucket_quota: dict[str, int] = {}
    allocated = 0
    for k in bucket_keys:
        # 至少 1
        q = max(1, round(len(buckets[k]) / total_active * quota))
        per_bucket_quota[k] = q
        allocated += q
    # 从最大的桶开始回吐多余配额
    ordering = sorted(bucket_keys, key=lambda k: -len(buckets[k]))
    while allocated > quota and ordering:
        for k in ordering:
            if allocated <= quota:
                break
            if per_bucket_quota[k] > 1:
                per_bucket_quota[k] -= 1
                allocated -= 1
    while allocated < quota:
        for k in ordering:
            if allocated >= quota:
                break
            per_bucket_quota[k] += 1
            allocated += 1

    for k in bucket_keys:
        bucket = sorted(buckets[k], key=lambda kv: kv[0])
        take = rng.sample(bucket, min(per_bucket_quota[k], len(bucket)))
        for c, e in take:
            picks.append(UniversePick(stock_code=c, reason="active", stratum=k))

    picks.sort(key=lambda p: p.stock_code)
    stats = {
        "total": len(picks),
        "delisted": sum(1 for p in picks if p.reason == "delisted"),
        "active": sum(1 for p in picks if p.reason == "active"),
        "seed": seed,
        "strata": len(buckets),
        "era_distribution": _era_distribution(picks, pit),
    }
    return picks, stats


def _era_label(d: date | None) -> str:
    if d is None:
        return "unknown"
    if d < date(2000, 1, 1):   return "pre2000"
    if d < date(2010, 1, 1):   return "2000s"
    if d < date(2015, 1, 1):   return "early2010s"
    if d < date(2020, 1, 1):   return "late2010s"
    return "post2020"


def _era_distribution(picks: list[UniversePick], pit: dict[str, dict]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for p in picks:
        e = pit[p.stock_code]
        out[_era_label(e["list_date"])] += 1
    return dict(out)


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------


def clear_prior_version(universe_version: str) -> int:
    with session_scope() as db:
        res = db.execute(delete(UniverseMembershipRow).where(
            UniverseMembershipRow.universe_version == universe_version
        ))
        return res.rowcount or 0


def persist_universe(picks: list[UniversePick], pit: dict[str, dict]) -> dict:
    """把 picks 写 universe_memberships（v2-phase3a）与 stock_master（幂等）。"""
    stats = {"memberships_written": 0, "stock_master_upserted": 0}
    with session_scope() as db:
        for p in picks:
            e = pit[p.stock_code]
            # universe_memberships
            db.add(UniverseMembershipRow(
                universe_version=UNIVERSE_VERSION,
                stock_code=p.stock_code,
                exchange=e["exchange"],
                board=e["board"],
                list_date=e["list_date"],
                delist_date=e["delist_date"],
                status="delisted" if e["list_status"] == "D" else "active",
                source="tushare_pit_universe",
                source_snapshot=SNAPSHOT_LABEL,
                # 关键约定：delist_source 永不为空。
                # - 退市股：tushare_pit_universe 直接给了 delist_date
                # - 在市股：tushare_pit_universe 的名单 catch-up 即"截至 2026-07-17 尚未退市"
                # NULL + 非空 delist_source 的语义 = "已知仍在市"。
                delist_source="tushare_pit_universe",
                notes=f"reason={p.reason};stratum={p.stratum}",
            ))
            stats["memberships_written"] += 1

            # stock_master
            row = db.execute(select(StockMasterRow).where(
                StockMasterRow.stock_code == p.stock_code
            )).scalars().first()
            if row is None:
                row = StockMasterRow(
                    stock_code=p.stock_code,
                    wind_code=e["ts_code"],
                    name=e["name"].replace("(退)", ""),
                    exchange=e["exchange"],
                    board=e["board"],
                    industry="",  # 留给 Phase 3E 独立 curated 表
                    listing_date=e["list_date"],
                    source="astockdata_pit_universe",
                )
                db.add(row)
            else:
                row.wind_code = e["ts_code"]
                row.name = e["name"].replace("(退)", "")
                row.exchange = e["exchange"]
                row.board = e["board"]
                row.listing_date = e["list_date"]
                row.source = "astockdata_pit_universe"
            stats["stock_master_upserted"] += 1
        db.flush()
    return stats


def persist_bars(
    picks: list[UniversePick],
    store: AStockDataBlobStore,
    *,
    skip_existing: bool = False,
) -> dict:
    """把 universe 中每只股票的 bars 写入 ``market_bar_daily``。"""
    stats = {"written_rows": 0, "skipped": 0, "failed": [], "series": 0}
    # symbol 格式：SSE.STK.600519
    with session_scope() as db:
        for p in picks:
            code = p.stock_code
            # 在 manifest 里找到 entry
            # pit_universe entry gives us exchange; store has full symbol
            sym = None
            for cand in (f"SSE.STK.{code}", f"SZSE.STK.{code}"):
                if cand in store.manifest.symbols:
                    sym = cand
                    break
            if sym is None:
                stats["failed"].append((code, "no blob in composite manifest"))
                continue
            if skip_existing:
                cnt = db.execute(
                    select(func.count(MarketBarDailyRow.id)).where(
                        MarketBarDailyRow.stock_code == code,
                        MarketBarDailyRow.source == BAR_SOURCE,
                    )
                ).scalar_one()
                if cnt:
                    stats["skipped"] += 1
                    continue
            try:
                df = store.load_bars(sym)
            except Exception as exc:  # noqa: BLE001
                stats["failed"].append((code, f"load_bars: {exc!r}"[:200]))
                continue
            if df.empty:
                stats["failed"].append((code, "empty bars"))
                continue
            # 幂等：先删
            db.execute(delete(MarketBarDailyRow).where(
                MarketBarDailyRow.stock_code == code,
                MarketBarDailyRow.source == BAR_SOURCE,
            ))
            db.flush()
            # 插入
            prev_close: float | None = None
            for r in df.itertuples(index=False):
                close = float(r.close)
                pct = None
                if prev_close and prev_close > 0:
                    pct = round((close / prev_close - 1.0) * 100.0, 6)
                db.add(MarketBarDailyRow(
                    stock_code=code,
                    trade_date=r.trade_date.date(),
                    open=float(r.open), high=float(r.high),
                    low=float(r.low), close=close,
                    volume=float(r.volume), amount=float(r.amount),
                    turnover=None, pct_change=pct,
                    adjust="none",   # raw / composite_none
                    is_benchmark=False,
                    source=BAR_SOURCE,
                    is_degraded=False,
                ))
                prev_close = close
            stats["written_rows"] += len(df)
            stats["series"] += 1
        db.flush()
    return stats


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-stocks", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-bars", action="store_true", help="只落 universe/stock_master，不导行情")
    ap.add_argument("--skip-existing-bars", action="store_true",
                    help="幂等：market_bar_daily 里已有同源同 code 的行则跳过")
    args = ap.parse_args()

    print(f"PIT universe src: {PIT_UNIVERSE_PATH}", flush=True)
    pit = load_pit_universe()
    print(f"PIT universe entries: {len(pit)}", flush=True)

    store = AStockDataBlobStore.latest_composite_none()
    print(f"composite_none manifest: {store.manifest.dataset_id}, "
          f"symbols={len(store.manifest.symbols)}, cutoff={store.manifest.cutoff_date}", flush=True)

    picks, stats = sample_phase3a_universe(pit, max_total=args.max_stocks)
    print(f"抽样规模: total={stats['total']}  delisted={stats['delisted']}  active={stats['active']}", flush=True)
    print(f"era 分布: {stats['era_distribution']}", flush=True)

    if args.dry_run:
        print("dry-run 完成，未落库")
        out = ROOT / "data" / "phase3_universe" / f"phase3a_astock_sample_{args.max_stocks}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "universe_version": UNIVERSE_VERSION,
            "seed": stats["seed"], "stats": stats,
            "picks": [{"code": p.stock_code, "reason": p.reason, "stratum": p.stratum} for p in picks],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"写入样本清单: {out}", flush=True)
        return 0

    init_db()

    # 清理旧 v1-phase3a（半成品）+ 新版重写
    prior_v1 = clear_prior_version("v1-phase3a")
    prior_v2 = clear_prior_version(UNIVERSE_VERSION)
    print(f"已清理旧版本: v1-phase3a={prior_v1}  {UNIVERSE_VERSION}={prior_v2}", flush=True)

    t0 = time.time()
    ps = persist_universe(picks, pit)
    print(f"universe_memberships[{UNIVERSE_VERSION}] 写入 {ps['memberships_written']} 行; "
          f"stock_master upsert {ps['stock_master_upserted']} 行  "
          f"({time.time()-t0:.1f}s)", flush=True)

    if args.skip_bars:
        print("跳过 bars 落库（--skip-bars）", flush=True)
        return 0

    t1 = time.time()
    bs = persist_bars(picks, store, skip_existing=args.skip_existing_bars)
    print(f"market_bar_daily: written_rows={bs['written_rows']}  series={bs['series']}  "
          f"skipped={bs['skipped']}  failed={len(bs['failed'])}  ({time.time()-t1:.1f}s)", flush=True)
    if bs["failed"]:
        print("失败样例:", bs["failed"][:8], flush=True)

    # 落盘后 summary
    with session_scope() as db:
        n_sm = db.execute(select(func.count(StockMasterRow.id))).scalar_one()
        n_bars = db.execute(select(func.count(MarketBarDailyRow.id)).where(
            MarketBarDailyRow.source == BAR_SOURCE)).scalar_one()
        n_um = db.execute(select(func.count(UniverseMembershipRow.id)).where(
            UniverseMembershipRow.universe_version == UNIVERSE_VERSION)).scalar_one()
    print(f"DB 状态: stock_master={n_sm}  market_bar_daily[{BAR_SOURCE}]={n_bars}  "
          f"universe_memberships[{UNIVERSE_VERSION}]={n_um}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
