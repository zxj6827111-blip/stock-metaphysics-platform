"""黄历日课分类的历史表现（研究层，描述性统计）。

它回答什么、不回答什么
----------------------
**回答**：把交易日按**版本化的传统日课分类**（吉 / 凶，见
``huangli_day_class``）分组后，各类别之后 H 个交易日的收益分布如何。

**不回答**：这是**描述性统计**，不是策略回测。没有组合规则、没有仓位、
没有交易成本、没有可执行性检验，因此本模块**刻意不产出**
「策略累计收益」或「净值曲线」——那需要一个可复现的组合定义，
当前系统里并不存在。

三条纪律（其余照抄项目既有研究约定）
------------------------------------
1. **不使用未来信息**：样本只取标签在分析基准日之前**已可观测**的那些
   （标签结束日 ≤ as_of）。特征侧同此。
2. **持有期按股票自己的 bar 推进**，复用 ``compute_forward_returns``
   —— 与 Phase 3D 的标签口径完全同源（停牌造成的实际跨度更长是真实风险，不平滑）。
3. **重叠样本必须披露**：日频样本的 H 日持有期彼此重叠 ``(H-1)/H``，
   因此额外给出**互不重叠子样本**的有效样本量，绝不用朴素显著性
   或重复计数制造"有效"结论。
"""

from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import select

from src.core.orchestration.huangli_day_class import (
    HUANGLI_DAY_CLASS_VERSION,
    class_rule_descriptor,
)
from src.db.base import get_session_factory
from src.db.models import MarketBarDailyRow
from src.engines.huangli.huangli_engine import HuangliEngine
from src.research.labels.horizon_returns import (
    DEFAULT_BENCHMARK_CODE,
    BenchmarkSeries,
    compute_forward_returns,
)
from src.research.labels.panel import adj_factor_index, load_adj_factors

#: 研究口径版本：改动窗口定义 / 聚合方式 / 序列定义必须提升它
HUANGLI_PERFORMANCE_VERSION = "huangli-perf-v1"

#: 窗口预设（年）
WINDOW_YEARS: dict[str, int] = {"1y": 1, "3y": 3, "5y": 5}

#: 允许的持有期（交易日）
SUPPORTED_HORIZONS: tuple[int, ...] = (1, 5, 20)

#: 基准：沪深300（与 Phase 1/2/3 一致）
BENCHMARK_CODE = "IDX000300"

#: hfq 行情来源（已含复权，无需外部分红因子）
_HFQ_SOURCE = "tencent_hfq_import"
#: 原始价（不复权）来源：收益必须用 adj_factor 复权后再算
_RAW_SOURCE = "astockdata_composite_none"

#: 样本量下限：低于它不给"平均收益"，只报样本数（避免用 2 个点造结论）
MIN_SAMPLES_FOR_STATS = 5


def _class_of_date(iso_date: str, engine: HuangliEngine) -> tuple[str | None, str | None, str]:
    """取某一天的（分类码, 中文标签, 依据）。

    纯函数式缓存：分类只由日期与通书口径决定，与行情无关，因此进程内缓存安全。
    """
    cached = _DAY_CLASS_CACHE.get(iso_date)
    if cached is not None:
        return cached
    day = engine.day_for(date.fromisoformat(iso_date))
    from src.core.orchestration.huangli_day_class import classify_day

    info = classify_day(day)
    out = (info["class_code"], info["class_label_cn"], info["class_basis_cn"])
    if len(_DAY_CLASS_CACHE) < _DAY_CLASS_CACHE_MAX:
        _DAY_CLASS_CACHE[iso_date] = out
    return out


_DAY_CLASS_CACHE: dict[str, tuple[str | None, str | None, str]] = {}
_DAY_CLASS_CACHE_MAX = 20000


def load_stock_bars(stock_code: str) -> tuple[pd.DataFrame, dict]:
    """读取该股票的日线，并说明**实际用的是哪一份**行情。

    优先 ``hfq``（后复权，价差本身即含分红的复权结果，不需要外部分红因子）；
    否则退回 ``astockdata_composite_none`` 原始价 + TuShare ``adj_factor``
    （与 Phase 3D 标签口径同源）。

    Returns:
        ``(bars, provenance)``；``bars`` 含 ``trade_date`` / ``close``；
        ``provenance`` 含 ``adjust`` / ``source`` / ``adj_factor_*``
        与 ``unavailable_reason``（无数据时为非空字符串）。
    """
    factory = get_session_factory()
    with factory() as db:
        hfq_rows = db.execute(
            select(MarketBarDailyRow.trade_date, MarketBarDailyRow.close)
            .where(
                MarketBarDailyRow.stock_code == stock_code,
                MarketBarDailyRow.adjust == "hfq",
            )
            .order_by(MarketBarDailyRow.trade_date)
        ).all()
        if hfq_rows:
            frame = pd.DataFrame(hfq_rows, columns=["trade_date", "close"])
            return frame, {
                "adjust": "hfq",
                "source": _HFQ_SOURCE,
                "return_basis_cn": "后复权收盘价之比（复权已由行情本身完成）",
                "adj_factor_snapshot": None,
                "adj_factor_uncovered_rows": 0,
                "unavailable_reason": "",
            }

        raw_rows = db.execute(
            select(MarketBarDailyRow.trade_date, MarketBarDailyRow.close)
            .where(
                MarketBarDailyRow.stock_code == stock_code,
                MarketBarDailyRow.source == _RAW_SOURCE,
            )
            .order_by(MarketBarDailyRow.trade_date)
        ).all()

    if not raw_rows:
        return pd.DataFrame(columns=["trade_date", "close"]), {
            "adjust": None,
            "source": None,
            "return_basis_cn": "",
            "adj_factor_snapshot": None,
            "adj_factor_uncovered_rows": 0,
            "unavailable_reason": (
                f"本地行情库中没有 {stock_code} 的日线（既无 hfq，也无 {_RAW_SOURCE}）。"
            ),
        }

    frame = pd.DataFrame(raw_rows, columns=["trade_date", "close"])
    index = adj_factor_index()
    factors = load_adj_factors(stock_code, index, {})
    provenance = {
        "adjust": "raw+adj_factor",
        "source": _RAW_SOURCE,
        "return_basis_cn": "原始收盘价 × 除权因子（TuShare adj_factor 快照）",
        "adj_factor_snapshot": "提供" if factors is not None else "缺失（按 1.0 处理，已披露）",
        "adj_factor_uncovered_rows": 0,
        "unavailable_reason": "",
    }
    frame.attrs["adj_factors"] = factors
    return frame, provenance


def _load_benchmark(code: str = BENCHMARK_CODE) -> tuple[BenchmarkSeries | None, str]:
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(MarketBarDailyRow.trade_date, MarketBarDailyRow.close)
            .where(MarketBarDailyRow.stock_code == code)
            .order_by(MarketBarDailyRow.trade_date)
        ).all()
    if not rows:
        return None, f"本地行情库中没有基准 {code}，本次不展示超额收益。"
    frame = pd.DataFrame(rows, columns=["trade_date", "close"])
    return BenchmarkSeries.from_frame(frame, code=DEFAULT_BENCHMARK_CODE), ""


def _resolve_range(
    as_of: datetime, window: str, start: str | None, end: str | None
) -> tuple[date, date, dict]:
    """把窗口预设 / 自定义区间解析成 ``[start, end]``（闭区间）。"""
    as_of_date = as_of.date()
    if window == "custom":
        if not start:
            raise ValueError("window=custom 时 start 必填")
        s = date.fromisoformat(start)
        e = date.fromisoformat(end) if end else as_of_date
        if e > as_of_date:
            e = as_of_date
        if s > e:
            raise ValueError("自定义区间的开始日晚于结束日")
        return s, e, {"id": "custom", "years": None}
    years = WINDOW_YEARS.get(window)
    if years is None:
        raise ValueError(f"未知的窗口: {window!r}（可用：{sorted(WINDOW_YEARS)} / custom）")
    try:
        s = as_of_date.replace(year=as_of_date.year - years)
    except ValueError:  # 2 月 29 日
        s = as_of_date.replace(year=as_of_date.year - years, day=28)
    return s, as_of_date, {"id": window, "years": years}


def _expanding_means(
    rows: list[dict], classes: Iterable[str]
) -> tuple[list[str], dict[str, list[float | None]], dict[str, list[int]]]:
    """各类别"截至该日期的平均持有期收益"（扩展均值）与样本计数。

    注意口径：这是**在样本内逐步扩大窗口后的平均持有期收益**，
    **不是**净值、不是累计投资收益 —— 没有组合规则就不该有累计曲线。
    """
    rows = sorted(rows, key=lambda r: r["trade_date"])
    dates: list[str] = []
    means: dict[str, list[float | None]] = {c: [] for c in classes}
    counts: dict[str, list[int]] = {c: [] for c in classes}
    running: dict[str, list[float]] = {c: [] for c in classes}
    for r in rows:
        dates.append(r["trade_date"])
        for c in classes:
            if r["class_code"] == c:
                running[c].append(r["ret"])
            bucket = running[c]
            means[c].append(round(statistics.fmean(bucket), 6) if bucket else None)
            counts[c].append(len(bucket))
    return dates, means, counts


def _group_stats(values: list[float], excess: list[float]) -> dict[str, Any]:
    n = len(values)
    out: dict[str, Any] = {
        "n": n,
        "mean": None,
        "median": None,
        "up_share": None,
        "mean_excess": None,
        "n_excess": len(excess),
        "stats_available": n >= MIN_SAMPLES_FOR_STATS,
    }
    if n >= MIN_SAMPLES_FOR_STATS:
        out["mean"] = round(statistics.fmean(values), 6)
        out["median"] = round(statistics.median(values), 6)
        out["up_share"] = round(sum(1 for v in values if v > 0) / n, 6)
    if len(excess) >= MIN_SAMPLES_FOR_STATS:
        out["mean_excess"] = round(statistics.fmean(excess), 6)
    return out


def _count_independent(rows: list[dict], horizon: int) -> int:
    """互不重叠子样本数：按时间顺序贪心取相隔 ≥ horizon 个交易日的样本。"""
    independent = 0
    last_index: int | None = None
    for r in sorted(rows, key=lambda x: x["trade_index"]):
        if last_index is None or r["trade_index"] - last_index >= horizon:
            independent += 1
            last_index = r["trade_index"]
    return independent


def build_day_class_performance(
    *,
    stock_code: str,
    as_of: datetime,
    window: str = "1y",
    horizon: int = 1,
    start: str | None = None,
    end: str | None = None,
    engine: HuangliEngine | None = None,
) -> dict:
    """按版本化日课分类统计未来的持有期收益。"""
    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(f"不支持的持有期 {horizon}（可用：{list(SUPPORTED_HORIZONS)}）")
    hl_engine = engine or HuangliEngine()
    range_start, range_end, window_meta = _resolve_range(as_of, window, start, end)

    bars, provenance = load_stock_bars(stock_code)
    rule = class_rule_descriptor()
    base = {
        "performance_version": HUANGLI_PERFORMANCE_VERSION,
        "class_rule_version": HUANGLI_DAY_CLASS_VERSION,
        "engine_version": hl_engine.engine_version,
        "stock_code": stock_code,
        "as_of": as_of.isoformat(),
        "window": {
            **window_meta,
            "requested_start": range_start.isoformat(),
            "requested_end": range_end.isoformat(),
            "effective_start": None,
            "effective_end": None,
        },
        "horizon": horizon,
        "class_rule": rule,
        "labels": {
            "label_version": HUANGLI_PERFORMANCE_VERSION,
            "horizon_supported": list(SUPPORTED_HORIZONS),
            "return_basis_cn": provenance["return_basis_cn"],
            "bar_source": provenance["source"],
            "bar_adjust": provenance["adjust"],
            "adj_factor_snapshot": provenance["adj_factor_snapshot"],
            "benchmark_code": BENCHMARK_CODE,
            "benchmark_available": False,
            "benchmark_note_cn": "",
            "data_cutoff": None,
            "label_cutoff": None,
            "n_dropped_incomplete_label": 0,
            "degraded": False,
        },
        "sample_rule_cn": (
            f"样本 = {range_start.isoformat()} ~ {range_end.isoformat()} 之间的交易日，"
            f"且其 {horizon} 日收益标签在分析基准日（{as_of.date().isoformat()}）之前"
            "已可观测（标签结束日 ≤ 分析基准日）。"
        ),
        "groups": [],
        "series": {"dates": [], "by_class": {}, "counts_by_class": {}, "metric_cn": ""},
        "overlap": {
            "horizon": horizon,
            "overlap_ratio": round((horizon - 1) / horizon, 6) if horizon > 1 else 0.0,
            "independent_note_cn": "",
        },
        "key_findings": [],
        "limitations_cn": _limitations(),
        "warnings": [],
        "unavailable_reason": "",
    }

    if bars.empty:
        base["unavailable_reason"] = provenance["unavailable_reason"]
        base["warnings"].append({
            "code": "HUANGLI_PERF_NO_BARS",
            "severity": "warning",
            "message": provenance["unavailable_reason"],
        })
        return base

    bars = bars.sort_values("trade_date").reset_index(drop=True)
    bar_dates = pd.to_datetime(bars["trade_date"]).dt.date.tolist()
    #: 行情**数据源**的截止日（与基准日无关，用于说明"本地数据新到哪一天"）
    base["labels"]["data_cutoff"] = bar_dates[-1].isoformat()

    # --- 只用基准日之前（含）的 bar：这样"标签结束日 ≤ 基准日"是构造性保证的 ---
    visible = [i for i, d in enumerate(bar_dates) if d <= range_end]
    if not visible:
        base["unavailable_reason"] = (
            f"行情数据从 {bar_dates[0].isoformat()} 开始，晚于分析基准日 "
            f"{range_end.isoformat()}，没有可用样本。"
        )
        base["warnings"].append({
            "code": "HUANGLI_PERF_OUT_OF_WINDOW",
            "severity": "warning",
            "message": base["unavailable_reason"],
        })
        return base
    bars = bars.iloc[: visible[-1] + 1].reset_index(drop=True)

    # --- 样本日：窗口内的该股交易日（停牌日没有 bar，自然不构成样本） ---
    sample_dates = [d for d in pd.to_datetime(bars["trade_date"]).dt.date.tolist() if d >= range_start]
    base["window"]["effective_start"] = (sample_dates[0].isoformat() if sample_dates else None)
    base["window"]["effective_end"] = (
        pd.to_datetime(bars["trade_date"]).dt.date.tolist()[-1].isoformat()
    )
    if not sample_dates:
        base["unavailable_reason"] = (
            f"该股在 {range_start.isoformat()} ~ {range_end.isoformat()} 之间没有行情样本"
            "（可能尚未上市或已退市）。"
        )
        base["warnings"].append({
            "code": "HUANGLI_PERF_NO_SAMPLE",
            "severity": "warning",
            "message": base["unavailable_reason"],
        })
        return base

    benchmark, bench_note = _load_benchmark()
    base["labels"]["benchmark_available"] = benchmark is not None
    base["labels"]["benchmark_note_cn"] = bench_note

    adj = bars.attrs.get("adj_factors")
    coverage: dict[str, Any] = {}
    rows = compute_forward_returns(
        bars,
        sample_dates,
        stock_code=stock_code,
        horizons=(horizon,),
        adj_factors=adj,
        benchmark=benchmark,
        coverage_out=coverage,
    )
    base["labels"]["adj_factor_uncovered_rows"] = int(coverage.get("uncovered_rows", 0))
    if provenance["adjust"] == "raw+adj_factor" and coverage.get("uncovered_rows", 0):
        base["labels"]["degraded"] = True
        base["warnings"].append({
            "code": "HUANGLI_PERF_ADJ_PARTIAL",
            "severity": "warning",
            "message": (
                f"{int(coverage.get('uncovered_rows', 0))} 行行情没有匹配到除权因子，"
                "这些行的收益未做复权（已在结论中作为限制披露）。"
            ),
        })

    ret_key = f"ret_{horizon}d"
    exc_key = f"excess_return_{horizon}d"
    usable: list[dict] = []
    dropped_incomplete = 0
    for row in rows:
        if not row.get("horizon_available", {}).get(f"{horizon}d"):
            dropped_incomplete += 1  # 标签不完整 → 不纳入（不填 0）
            continue
        ret = row.get(ret_key)
        if ret is None:
            dropped_incomplete += 1
            continue
        # 标签结束日 ≤ 基准日：由上面的 bars 截断构造性保证，这里再断言一次
        end_idx = row["trade_index"] + horizon
        end_date = pd.to_datetime(bars["trade_date"]).dt.date.tolist()
        end_d = end_date[end_idx] if end_idx < len(end_date) else None
        if end_d is None or end_d > range_end:
            continue
        class_code, class_label, class_basis = _class_of_date(
            row["trade_date"].isoformat(), hl_engine
        )
        usable.append({
            "trade_date": row["trade_date"].isoformat(),
            "label_end_date": end_d.isoformat(),
            "trade_index": int(row["trade_index"]),
            "class_code": class_code,
            "class_label_cn": class_label,
            "class_basis_cn": class_basis,
            "ret": float(ret),
            "excess": None if row.get(exc_key) is None else float(row[exc_key]),
        })

    if not usable:
        base["labels"]["n_dropped_incomplete_label"] = dropped_incomplete
        base["unavailable_reason"] = (
            f"窗口内没有**标签完整**的样本：{horizon} 日持有期需要在此之后仍有 "
            f"{horizon} 个交易日，而可观测数据只到 {range_end.isoformat()}。"
            "请缩短持有期或提前分析基准日。"
        )
        base["warnings"].append({
            "code": "HUANGLI_PERF_NO_COMPLETE_LABEL",
            "severity": "warning",
            "message": base["unavailable_reason"],
        })
        return base

    classes = ["auspicious", "inauspicious"]
    present = [c for c in classes if any(r["class_code"] == c for r in usable)]
    if len(present) < len(classes):
        missing = [c for c in classes if c not in present]
        label_cn = {"auspicious": "吉", "inauspicious": "凶"}
        base["warnings"].append({
            "code": "HUANGLI_PERF_CLASS_MISSING",
            "severity": "warning",
            "message": (
                "窗口内没有出现"
                + "、".join(f"「{label_cn[m]}」" for m in missing)
                + f"日样本，因此该类别没有统计结果（不以 0 填充）。"
            ),
        })

    groups: list[dict] = []
    for code in classes:
        vals = [r["ret"] for r in usable if r["class_code"] == code]
        excs = [r["excess"] for r in usable if r["class_code"] == code and r["excess"] is not None]
        groups.append({
            "class_code": code,
            "class_label_cn": {"auspicious": "吉", "inauspicious": "凶"}[code],
            **(_group_stats(vals, excs)),
            "independent_n": _count_independent([r for r in usable if r["class_code"] == code], horizon),
        })
    unclassified = [r for r in usable if r["class_code"] is None]
    if unclassified:
        vals = [r["ret"] for r in unclassified]
        groups.append({
            "class_code": None,
            "class_label_cn": "未给出分类",
            **(_group_stats(vals, [])),
            "independent_n": _count_independent(unclassified, horizon),
        })

    dates, means, counts = _expanding_means(usable, present or classes)
    base["labels"]["n_dropped_incomplete_label"] = dropped_incomplete
    #: 纳入样本的最后一个**标签结束日**（必须 ≤ 分析基准日，这是防未来信息的证据）
    base["labels"]["label_cutoff"] = max(r["label_end_date"] for r in usable)
    base["groups"] = groups
    base["series"] = {
        "dates": dates,
        "by_class": {c: means[c] for c in (present or classes)},
        "counts_by_class": {c: counts[c] for c in (present or classes)},
        "metric_cn": (
            "纵轴为「截至该日期、该类样本的平均持有期收益」（扩展均值，单位：小数）；"
            "**不是净值、不是累计投资收益、不是策略回测结果**，"
            "也没有扣除交易成本或考虑可执行性。"
        ),
    }
    total = len(usable)
    independent_total = _count_independent(usable, horizon)
    base["overlap"]["total_samples"] = total
    base["overlap"]["independent_samples"] = independent_total
    if horizon <= 1:
        # 1 日持有期不存在重叠：如实说明"不重叠"，不要套用多日口径的免责话术
        base["overlap"]["independent_note_cn"] = (
            f"{horizon} 日持有期的相邻样本不共享任何持有区间，"
            f"因此 {total} 个样本之间不存在持有期重叠；"
            "但它们仍受同一段市场行情驱动，不是彼此独立的实验。"
        )
    else:
        base["overlap"]["independent_note_cn"] = (
            f"{horizon} 日持有期的日频样本彼此重叠：相邻样本共享 {horizon - 1} 个交易日，"
            f"重叠率 {(horizon - 1) / horizon:.0%}。按互不重叠抽样，"
            f"有效样本约 {independent_total} 个（原始 {total} 个），"
            "两者不能当作同一份独立证据。"
        )
    base["key_findings"] = _findings(groups, horizon, total, independent_total)
    return base


def _findings(
    groups: list[dict], horizon: int, total: int, independent_total: int
) -> list[dict]:
    """只从实际数字生成的客观摘要。

    **不预设吉日优于凶日**，也不给任何未来收益承诺：低于样本量下限的组
    直接说明"样本不足，不做比较"。
    """
    out: list[dict] = []
    by_code = {g["class_code"]: g for g in groups}
    aus, inaus = by_code.get("auspicious"), by_code.get("inauspicious")
    out.append({
        "level": "info",
        "text_cn": (
            f"本次共纳入 {total} 个标签完整的交易日样本（{horizon} 日持有期）；"
            f"按互不重叠口径的有效样本约 {independent_total} 个。"
        ),
    })
    if aus and inaus:
        if not (aus["stats_available"] and inaus["stats_available"]):
            out.append({
                "level": "warn",
                "text_cn": (
                    f"样本不足 {MIN_SAMPLES_FOR_STATS} 个的类别不做平均收益比较"
                    f"（吉日 n={aus['n']}，凶日 n={inaus['n']}）。"
                ),
            })
            return out
        diff = aus["mean"] - inaus["mean"]
        out.append({
            "level": "info",
            "text_cn": (
                f"窗口内「吉」日均收益 {aus['mean']:+.2%}（n={aus['n']}），"
                f"「凶」日 {inaus['mean']:+.2%}（n={inaus['n']}），"
                f"差值 {diff:+.2%}"
                f"（**仅为描述性差值，未做显著性检验，也不含交易成本**）。"
            ),
        })
        if aus.get("mean_excess") is not None and inaus.get("mean_excess") is not None:
            out.append({
                "level": "info",
                "text_cn": (
                    f"相对 {BENCHMARK_CODE} 的平均超额：吉日 {aus['mean_excess']:+.2%}、"
                    f"凶日 {inaus['mean_excess']:+.2%}。"
                ),
            })
    out.append({
        "level": "warn",
        "text_cn": (
            "以上差异不能解释为因果关系或可交易收益：样本重叠、" 
            "窗口选择、单一标的与市场整体走势都可能产生同样量级的差值。"
        ),
    })
    return out


def _limitations() -> list[str]:
    return [
        "描述性统计，不是策略回测：没有组合规则、仓位、交易成本与可执行性检验，因此不提供净值或累计收益。",
        "日频样本的持有期彼此重叠，独立样本量远小于原始样本量；本页不提供朴素显著性结论。",
        "结论只针对当前标的与当前窗口；换标的、换窗口、换持有期都可能不同。",
        "传统分类来自通书口径（十二神所属黄黑道的吉凶派生），其历史关联不代表任何因果机制。",
        "收益为后复权/复权后的价格收益，不含分红再投资的税费与滑点。",
    ]


__all__ = [
    "HUANGLI_PERFORMANCE_VERSION",
    "WINDOW_YEARS",
    "SUPPORTED_HORIZONS",
    "BENCHMARK_CODE",
    "MIN_SAMPLES_FOR_STATS",
    "build_day_class_performance",
    "load_stock_bars",
]
