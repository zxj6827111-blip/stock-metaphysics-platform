"""择日关系扫描口径证据脚本（v2 基线 / v3 终态）。

用法::

    PYTHONUTF8=1 python scripts/relation_scan_evidence.py --mode v2
    PYTHONUTF8=1 python scripts/relation_scan_evidence.py --mode v3

v2 路径必须在**改动前**的 ``4c334e7``（口径整改前）运行；v3 路径在整改后运行。
两路径共用同一份股票池（PIT v4-full）、同一批 12 个采样日期与同一个
平安银行 000001 的 2026 全年逐日扫描，差异只来自口径本身。

.. note::

   v3 内核已把矩阵目标列收窄为年/月/日，``--mode v2`` 无法在当前 HEAD 复现
   （会被新的 3×3 断言挡住）。v2 基线已冻结在 ``docs/relation-v3-evidence/``
   下的 ``baseline-v2.json`` 与 ``pingan-000001-2026-v2.csv``。

指标定义
--------
* 命中数：该日期命中某关系类型的**股票数**（不是事件总数）。
* S/V/U：协同/扰动/混合关系事件计数（v2=3×4 全行聚合；v3=3×3 仅流日行）。
* Jaccard：同一关系类型在不同日期的命中股票集合的交并比（12 日期两两均值）。

输出
----
* ``docs/relation-v3-evidence/baseline-v2.json`` / ``final-v3.json``
* ``docs/relation-v3-evidence/pingan-000001-2026-{mode}.csv``
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.orchestration.date_relation_scan import (  # noqa: E402
    _load_static_natal_cache,
    _natal_ganzhi,
)
from src.core.relations import date_relation as rel  # noqa: E402
from src.core.relations.date_relation import classify_relation_group  # noqa: E402
from src.core.schemas.relation import RELATION_TYPES  # noqa: E402
from src.db.base import get_db  # noqa: E402
from src.engines.calendar.calendar_engine import CalendarEngine  # noqa: E402
from src.research.universe.point_in_time import PointInTimeUniverse  # noqa: E402

#: 12 个固定采样日：2025-10 ～ 2026-09 每月 1 日（结构对比不依赖是否交易日）。
SAMPLE_DATES = [date(2025, 10, 1)] + [date(2025, m, 1) for m in (11, 12)] + [
    date(2026, m, 1) for m in range(1, 10)
]

PINGAN = "000001"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "relation-v3-evidence"

# 与 v2 ``_build_one``/quick 统计完全一致的关系集合定义（来源：date_relation_scan.py）。
# v3 起三个集合统一由 date_relation 模块导出；v2 时代 COMPOUND 集合只在编排层内联，
# 因此这里用 ``getattr`` 向后兼容（v2 运行时取本地常量）。
_COMPOUND_RELATIONS = getattr(rel, "COMPOUND_RELATIONS", None) or {"伏吟", "反吟", "天合地合", "天克地冲"}


def _percentile(sorted_values: list[int], p: float) -> float:
    if not sorted_values:
        return float("nan")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * p
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    frac = rank - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


def _dist(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": float(ordered[0]) if ordered else float("nan"),
        "p25": _percentile(ordered, 0.25),
        "p50": _percentile(ordered, 0.50),
        "p75": _percentile(ordered, 0.75),
        "p90": _percentile(ordered, 0.90),
        "p95": _percentile(ordered, 0.95),
        "max": float(ordered[-1]) if ordered else float("nan"),
    }


def _jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _matrix_for(code: str, natal_cache: dict, snapshot, mode: str):
    natal = natal_cache.get(code)
    if natal is None:
        return None, None
    external = {"year": snapshot.year_ganzhi, "month": snapshot.month_ganzhi, "day": snapshot.day_ganzhi}
    matrix = rel.build_relation_matrix(external, _natal_ganzhi(natal), day_master=natal.day_master)
    if mode == "v2":
        events = rel.flatten_events(matrix)
    else:  # v3：只聚合流日行（external_day_row）
        events = rel.events_for_source_pillar(matrix, "day")
    return matrix, events


def _scan_one_date(day: date, codes: list[str], natal_cache: dict, mode: str) -> dict[str, Any]:
    snapshot = CalendarEngine().snapshot(datetime.combine(day, datetime.min.time()).replace(hour=12))
    relation_sets: dict[str, set[str]] = {relation: set() for relation in RELATION_TYPES}
    s_values: list[int] = []
    v_values: list[int] = []
    u_values: list[int] = []
    groups: dict[str, int] = {}

    for code in codes:
        _matrix, events = _matrix_for(code, natal_cache, snapshot, mode)
        if events is None:
            continue
        types = {event.relation_type for event in events}
        for relation in types:
            if relation in relation_sets:
                relation_sets[relation].add(code)
        s = sum(1 for event in events if event.relation_type in rel.SUPPORTIVE_RELATIONS)
        v = sum(1 for event in events if event.relation_type in rel.DISTURBING_RELATIONS)
        u = sum(1 for event in events if event.relation_type in _COMPOUND_RELATIONS)
        s_values.append(s)
        v_values.append(v)
        u_values.append(u)
        group = classify_relation_group(s, v, u)
        groups[group] = groups.get(group, 0) + 1

    return {
        "day_ganzhi": snapshot.day_ganzhi.text,
        "relation_stock_counts": {k: len(v) for k, v in relation_sets.items()},
        "_relation_sets": relation_sets,
        "s": s_values,
        "v": v_values,
        "u": u_values,
        "groups": groups,
    }


def run_market(mode: str) -> dict[str, Any]:
    db = next(get_db())
    natal_cache = _load_static_natal_cache()
    all_dates_result: dict[str, Any] = {}
    pooled_s: list[int] = []
    pooled_v: list[int] = []
    pooled_u: list[int] = []
    group_pool: dict[str, int] = {}
    universe_size = 0

    for day in SAMPLE_DATES:
        membership = PointInTimeUniverse.load(db, "v4-full", snapshot_at=day).at(day)
        codes = list(membership.member_codes)
        universe_size = max(universe_size, len(codes))
        result = _scan_one_date(day, codes, natal_cache, mode)
        all_dates_result[day.isoformat()] = result
        pooled_s.extend(result["s"])
        pooled_v.extend(result["v"])
        pooled_u.extend(result["u"])
        for group, count in result["groups"].items():
            group_pool[group] = group_pool.get(group, 0) + count
        print(f"[{mode}] {day} stocks={len(codes)} scanned={len(result['s'])}", flush=True)

    jaccard: dict[str, dict[str, float]] = {}
    dates = list(all_dates_result)
    for relation in RELATION_TYPES:
        pairs: list[float] = []
        for i, left in enumerate(dates):
            for right in dates[i + 1:]:
                pairs.append(_jaccard(
                    all_dates_result[left]["_relation_sets"][relation],
                    all_dates_result[right]["_relation_sets"][relation],
                ))
        jaccard[relation] = {
            "mean": sum(pairs) / len(pairs) if pairs else 1.0,
            "min": min(pairs) if pairs else 1.0,
            "max": max(pairs) if pairs else 1.0,
        }

    return {
        "mode": mode,
        "dates": [day.isoformat() for day in SAMPLE_DATES],
        "universe_size": universe_size,
        "aggregate_scope": "all_rows_3x4" if mode == "v2" else "external_day_row_3x3",
        "per_date": {
            day: {
                "day_ganzhi": payload["day_ganzhi"],
                "relation_stock_counts": payload["relation_stock_counts"],
                "groups": payload["groups"],
            }
            for day, payload in all_dates_result.items()
        },
        "jaccard_by_relation": jaccard,
        "svu_distribution_pooled": {
            "S": _dist(pooled_s),
            "V": _dist(pooled_v),
            "U": _dist(pooled_u),
        },
        "group_counts_pooled": group_pool,
    }


def run_pingan(mode: str) -> list[dict[str, Any]]:
    natal_cache = _load_static_natal_cache()
    natal = natal_cache.get(PINGAN)
    if natal is None:
        raise SystemExit("natal cache 缺少 000001，无法生成平安银行证据")

    rows: list[dict[str, Any]] = []
    day = date(2026, 1, 1)
    while day <= date(2026, 12, 31):
        snapshot = CalendarEngine().snapshot(datetime.combine(day, datetime.min.time()).replace(hour=12))
        matrix, events = _matrix_for(PINGAN, natal_cache, snapshot, mode)
        assert matrix is not None and events is not None
        types = list(dict.fromkeys(event.relation_type for event in events))
        s = sum(1 for event in events if event.relation_type in rel.SUPPORTIVE_RELATIONS)
        v = sum(1 for event in events if event.relation_type in rel.DISTURBING_RELATIONS)
        u = sum(1 for event in events if event.relation_type in _COMPOUND_RELATIONS)
        row: dict[str, Any] = {
            "date": day.isoformat(),
            "day_ganzhi": snapshot.day_ganzhi.text,
            "day_stem": snapshot.day_ganzhi.stem,
            "relation_types": "/".join(types),
            "S": s,
            "V": v,
            "U": u,
            "group": classify_relation_group(s, v, u),
        }
        if mode == "v2":
            # v2 旧口径的「十神」= 全部 12 格事件上 ten_god 的去重集合（锁死问题的出处）。
            row["ten_gods"] = "/".join(dict.fromkeys(e.ten_god for e in events if e.ten_god))
        else:
            from src.core.relations.date_relation import build_day_stem_verdict

            verdict = build_day_stem_verdict(
                day_master=natal.day_master,
                day_stem=snapshot.day_ganzhi.stem,
                yong_shen=natal.yong_shen,
                xi_shen=natal.xi_shen,
                ji_shen=natal.ji_shen,
                chou_shen=natal.chou_shen,
                xian_shen=natal.xian_shen,
            )
            row.update({
                "day_stem_wuxing": verdict.day_stem_wuxing,
                "ten_god": verdict.ten_god,
                "ten_god_group": verdict.ten_god_group,
                "wuxing_role": verdict.wuxing_role,
                "verdict": verdict.verdict,
                "is_yong_or_xi": verdict.is_yong_or_xi,
            })
        rows.append(row)
        day += timedelta(days=1)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["v2", "v3"], required=True)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    market = run_market(args.mode)
    (OUTPUT_DIR / f"{'baseline-v2' if args.mode == 'v2' else 'final-v3'}.json").write_text(
        json.dumps(market, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    pingan = run_pingan(args.mode)
    csv_path = OUTPUT_DIR / f"pingan-000001-2026-{args.mode}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pingan[0].keys()))
        writer.writeheader()
        writer.writerows(pingan)
    print(f"written: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
