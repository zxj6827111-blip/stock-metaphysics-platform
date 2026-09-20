"""Phase 4D · 全市场观测面板采集（v4-full，6,104 只 × 68 as_of × 3 出生模型）。

与 Phase 3D 的关系
------------------
复用 ``scripts/phase3d_collect_panel.py`` 的 ``PanelCollector``（**同一份排盘实现**），
只把 universe 换成 ``v4-full``、输出目录换成 ``data/phase4_cache/``：

    Phase 3D: v2-phase3a,  500 只, 175,734 行面板（一次性的基线）
    Phase 4D: v4-full,   6,104 只, 约 746,724 次排盘（全市场）

**不修改 Phase 3D 的任何产物**。

并行
----
按股票分片，12 个子进程并行（本机 16 逻辑核）。分片之间股票集合不重叠，
合并是纯拼接 —— 因此可以用 ``--merge`` 把分片合起来做完整性校验。

**实测过的坑**：常驻紫微 HTTP 服务（``node dist/server.js`` + ``SMP_ZIWEI_SERVICE_URL``）
比"每批一个 node 子进程"**更慢**（3.9/s vs 6.4/s），因此本脚本强制走子进程通道
（显式清掉 ``SMP_ZIWEI_SERVICE_URL``）。

用法::

    python scripts/phase4_collect_panel.py --parallel 12          # 全量并行采集
    python scripts/phase4_collect_panel.py --merge                # 合并校验
    python scripts/phase4_collect_panel.py --limit 60 --parallel 1  # 冒烟
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db.base import get_session_factory  # noqa: E402
from src.db.models import UniverseMembershipRow  # noqa: E402

CACHE_DIR = ROOT / "data" / "phase4_cache"
UNIVERSE_VERSION = "v4-full"
#: 默认 as_of 网格（与 Phase 3D 完全一致，保证可对照）
DATE_FROM = "2010-01-01"
DATE_TO = "2026-08-14"
STEP_MONTHS = 3


def load_panel_collector():  # type: ignore[no-untyped-def]
    """复用 Phase 3D 采集器的 ``PanelCollector`` / ``MODEL_VERSIONS``（同一实现）。"""
    spec = importlib.util.spec_from_file_location(
        "phase3d_collect_panel", ROOT / "scripts" / "phase3d_collect_panel.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_universe(
    version: str, limit: int = 0, only_codes: set[str] | None = None,
) -> tuple[list[str], dict[str, tuple[object, object]]]:
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == version,
            ).order_by(UniverseMembershipRow.stock_code)
        ).scalars().all()
    if only_codes is not None:
        rows = [row for row in rows if row.stock_code in only_codes]
    if limit:
        rows = rows[:limit]
    return (
        [row.stock_code for row in rows],
        {row.stock_code: (row.list_date, row.delist_date) for row in rows},
    )


def read_codes_file(path: str) -> set[str] | None:
    """读取"只算这些股票"的清单（每行一个代码，# 开头为注释）。

    用于**局部重算**：出生档案修正后，只重算受影响的股票，不必全量重跑。
    """
    if not path:
        return None
    codes = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            codes.add(text.split(",")[0].strip().zfill(6))
    return codes or None


def run_shard(args: argparse.Namespace) -> int:
    module = load_panel_collector()
    from datetime import date

    started = time.time()
    dates = module.sample_dates(
        date.fromisoformat(args.date_from), date.fromisoformat(args.date_to), args.step_months,
    )
    codes, eligibility = load_universe(
        args.universe_version, args.limit, only_codes=read_codes_file(args.codes_file),
    )
    if args.shard_count > 1:
        codes = codes[args.shard_index::args.shard_count]
    if not codes:
        raise RuntimeError("分片没有股票")
    eligibility = {code: eligibility[code] for code in codes if code in eligibility}
    profiles = module.load_profiles(codes)
    missing = [
        (code, model) for code in codes for model in module.MODEL_VERSIONS
        if (code, model) not in profiles
    ]
    collector = module.PanelCollector(
        codes, profiles, eligibility=eligibility, skip_ziwei=args.skip_ziwei,
    )
    rows: list[dict] = []
    for as_of in dates:
        chunk = collector.compute_date(as_of)
        rows.extend(chunk)
        print(
            f"[shard {args.shard_index}/{args.shard_count}] {as_of} "
            f"rows={len(chunk)} elapsed={time.time() - started:.0f}s",
            flush=True,
        )
    payload = {
        "universe_version": args.universe_version,
        "codes": codes,
        "dates": [value.isoformat() for value in dates],
        "rows": rows,
        "birth_shift_days": 0,
        "step_months": args.step_months,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "skip_ziwei": bool(args.skip_ziwei),
        "failures": dict(collector.failures),
        "skipped_pit": dict(collector.skipped_pit),
        "ziwei_unavailable_reason": collector.ziwei_unavailable_reason,
        "missing_profiles": len(missing),
        "engine_versions": {
            "bazi": collector.bazi.engine_version,
            "huangli": collector.huangli.engine_version,
            "ziwei": None if collector.ziwei is None else collector.ziwei.engine_version,
        },
        "elapsed_seconds": round(time.time() - started, 1),
        "collector": "scripts/phase4_collect_panel.py",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(
        f"wrote {out} rows={len(rows)} codes={len(codes)} "
        f"elapsed={time.time() - started:.0f}s failures={dict(collector.failures)} "
        f"missing_profiles={len(missing)}",
        flush=True,
    )
    return 0


def launch_parallel(args: argparse.Namespace) -> int:
    """按分片拉起子进程（每个分片一个进程）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_dir = CACHE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    processes: list[tuple[int, subprocess.Popen, object]] = []
    for index in range(args.parallel):
        out = CACHE_DIR / f"main_shard{index:02d}.pkl"
        if args.reuse_cache and out.exists():
            print(f"[shard {index}] 复用已存在的分片，跳过", flush=True)
            continue
        log_path = log_dir / f"main_shard{index:02d}.log"
        handle = log_path.open("w", encoding="utf-8")
        command = [
            sys.executable, str(ROOT / "scripts" / "phase4_collect_panel.py"),
            "--shard-index", str(index), "--shard-count", str(args.parallel),
            "--date-from", args.date_from, "--date-to", args.date_to,
            "--step-months", str(args.step_months),
            "--universe-version", args.universe_version,
            "--out", str(out),
        ]
        if args.limit:
            command += ["--limit", str(args.limit)]
        if args.codes_file:
            command += ["--codes-file", args.codes_file]
        if args.cache_dir:
            command += ["--cache-dir", args.cache_dir]
        if args.skip_ziwei:
            command.append("--skip-ziwei")
        environment = dict(os.environ)
        environment["PYTHONUTF8"] = "1"
        # 实测：常驻 HTTP 服务比子进程慢 → 强制走子进程通道
        environment.pop("SMP_ZIWEI_SERVICE_URL", None)
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, env=environment)
        processes.append((index, process, handle))
        print(f"[shard {index}] pid={process.pid} → {log_path.name}", flush=True)

    failed: list[int] = []
    while processes:
        remaining: list[tuple[int, subprocess.Popen, object]] = []
        for index, process, handle in processes:
            code = process.poll()
            if code is None:
                remaining.append((index, process, handle))
                continue
            handle.close()  # type: ignore[attr-defined]
            if code != 0:
                failed.append(index)
                print(f"[shard {index}] 退出码 {code}", flush=True)
            else:
                print(f"[shard {index}] 完成", flush=True)
        processes = remaining
        if processes:
            time.sleep(20)
            print(
                f"… 仍在运行 {[item[0] for item in processes]}"
                f"（已用 {time.time() - started:.0f}s）",
                flush=True,
            )
    print(f"全部结束，用时 {time.time() - started:.0f}s；失败分片={failed}", flush=True)
    return 1 if failed else 0


def merge_shards() -> int:
    """合并分片并做完整性校验（股票集合不重叠、与 universe 一致）。"""
    paths = sorted(CACHE_DIR.glob("main_shard[0-9][0-9].pkl"))
    if not paths:
        print("没有分片可合并")
        return 1
    all_rows: list[dict] = []
    codes: list[str] = []
    dates: list[str] = []
    failures: dict[str, int] = {}
    missing_profiles = 0
    elapsed = 0.0
    expected_version = ""
    for path in paths:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        all_rows.extend(payload["rows"])
        codes.extend(payload["codes"])
        dates.extend(payload["dates"])
        for key, value in (payload.get("failures") or {}).items():
            failures[key] = failures.get(key, 0) + int(value)
        missing_profiles += int(payload.get("missing_profiles", 0) or 0)
        elapsed += float(payload.get("elapsed_seconds", 0) or 0)
        expected_version = str(payload.get("universe_version", ""))

    expected_codes, _ = load_universe(expected_version)
    overlap = len(codes) - len(set(codes))
    report = {
        "shards": len(paths),
        "universe_version": expected_version,
        "codes_in_shards": len(set(codes)),
        "codes_in_universe": len(expected_codes),
        "missing_codes": sorted(set(expected_codes) - set(codes))[:20],
        "overlapping_codes": overlap,
        "row_count": len(all_rows),
        "dates": len(set(dates)),
        "failures": failures,
        "missing_profiles": missing_profiles,
        "summed_shard_seconds": round(elapsed, 1),
    }
    out = CACHE_DIR / "merged_panel.pkl"
    with out.open("wb") as handle:
        pickle.dump({
            "universe_version": expected_version,
            "codes": sorted(set(codes)),
            "dates": sorted(set(dates)),
            "rows": all_rows,
            "failures": failures,
            "merge_report": report,
        }, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"合并完成 → {out}")
    for key, value in report.items():
        print(f"  {key}: {value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 4D 全市场面板采集")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--parallel", type=int, default=0, help=">0 表示启动 N 个并行分片")
    parser.add_argument("--merge", action="store_true", help="只合并校验")
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-ziwei", action="store_true")
    parser.add_argument("--universe-version", default=UNIVERSE_VERSION)
    parser.add_argument("--date-from", default=DATE_FROM)
    parser.add_argument("--date-to", default=DATE_TO)
    parser.add_argument("--step-months", type=int, default=STEP_MONTHS)
    parser.add_argument("--out", default="")
    parser.add_argument(
        "--codes-file", default="",
        help="只计算该文件内的股票代码（每行一个）；用于出生档案修正后的局部重算",
    )
    parser.add_argument(
        "--cache-dir", default="",
        help="分片输出目录（默认 data/phase4_cache）；局部重算时指向独立目录，避免覆盖全量分片",
    )
    return parser


def main() -> int:
    global CACHE_DIR
    args = build_parser().parse_args()
    if args.cache_dir:
        CACHE_DIR = Path(args.cache_dir)
    if args.merge:
        return merge_shards()
    if args.parallel > 0:
        return launch_parallel(args)
    if not args.out:
        args.out = str(CACHE_DIR / f"main_shard{args.shard_index:02d}.pkl")
    return run_shard(args)


if __name__ == "__main__":
    raise SystemExit(main())
