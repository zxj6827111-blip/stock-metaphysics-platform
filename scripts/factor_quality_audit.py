"""65 因子质量审计（验收 §六）——"数量超过要求"不等于"质量合格"。

对全部因子在真实导入快照上跑全量面板，输出每个因子的：

    activation_rate      激活率（normalized_value != 0 的占比）
    null_rate            不可用率（normalized_value 为 null / availability!=ok）
    direction_dist       方向分布（+1/0/-1）
    mean_score/std_score 规则强度均值/方差
    unique_values        归一化值不同取值数（恒定因子探测）
    sample_count         观测行数

并给出自动标记（**只报告，不自动删除**）：

    CONSTANT_FACTOR              unique_values == 1
    NEAR_CONSTANT_FACTOR         主值占比 ≥ 99.5% 且 unique_values ≤ 2
    ALL_NULL_FACTOR              null_rate == 100%
    LOW_DISCRIMINATION_FACTOR    activation_rate > 95% 或 < 0.5%
    POTENTIAL_DUPLICATE_FACTOR   两因子 |pearson| > 0.98

输出：
    artifacts/acceptance/factor_quality.json
    docs/factor_quality_report.md

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/factor_quality_audit.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.schemas.common import VariantMode  # noqa: E402
from src.core.stock.birth_profile import build_birth_profile  # noqa: E402
from src.engines.bazi.bazi_engine import BaziEngine  # noqa: E402
from src.engines.huangli.huangli_engine import HuangliEngine  # noqa: E402
from src.factors.registry.compute import compute_factor_set  # noqa: E402
from src.factors.registry.definitions import DEFINITION_INDEX  # noqa: E402
from src.market.providers.offline import OfflineMarketDataProvider  # noqa: E402
from src.research.pipeline import month_starts  # noqa: E402

#: 激活率与判重阈值（验收 §三 / §六）
LOW_DISCRIMINATION_HIGH = 0.95
LOW_DISCRIMINATION_LOW = 0.005
DUPLICATE_CORR = 0.98


def build_panel(market: OfflineMarketDataProvider, sample_dates: list[date]) -> pd.DataFrame:
    """在真实快照上构建全部 65 因子的观测面板。"""
    bazi = BaziEngine()
    huangli = HuangliEngine()
    stocks = list(market._stocks.values())  # noqa: SLF001 审计脚本读取导入清单
    hl_cache: dict[str, object] = {}
    rows: list[dict] = []

    for stock_row in stocks:
        code = stock_row["stock_code"]
        listing = date.fromisoformat(stock_row["listing_date"])
        stock = market.get_stock(code)
        profile = build_birth_profile(stock, None)
        for as_of_date in sample_dates:
            if as_of_date < listing:
                continue
            as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 0, 0)
            key = as_of_date.isoformat()
            hl = hl_cache.get(key)
            if hl is None:
                hl = huangli.snapshot(as_of, days=31)
                hl_cache[key] = hl
            try:
                fset = compute_factor_set(
                    bazi.build_chart(
                        birth_datetime=profile.birth_datetime.replace(tzinfo=None),
                        as_of=as_of,
                        variant_mode=VariantMode(profile.variant_mode),
                        stock_code=code,
                    ),
                    hl, as_of, stock_code=code,
                )
            except Exception as exc:  # noqa: BLE001 - 单点失败不中断审计，但必须记录
                print(f"[warn] {code}@{as_of_date} 因子计算失败: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                continue
            rows.extend({
                "stock_code": code,
                "as_of": as_of_date.isoformat(),
                "factor_id": o.factor_id,
                "normalized_value": o.normalized_value,
                "direction": int(o.direction),
                "rule_score": o.rule_score,
                "availability": o.availability,
            } for o in fset.observations)
    return pd.DataFrame(rows)


def audit(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """逐因子统计 + 重复性检测。"""
    per_factor: list[dict] = []
    for fid in sorted(df["factor_id"].unique()):
        sub = df[df["factor_id"] == fid]
        nv = pd.to_numeric(sub["normalized_value"], errors="coerce")
        total = len(sub)
        null_rate = float(nv.isna().mean())
        valid = nv.dropna()
        act_rate = float((valid != 0.0).mean()) if len(valid) else 0.0
        dir_counts = sub["direction"].value_counts().to_dict()
        uniq = int(valid.nunique())
        flags: list[str] = []
        if null_rate >= 1.0:
            flags.append("ALL_NULL_FACTOR")
        if uniq <= 1 and null_rate < 1.0:
            flags.append("CONSTANT_FACTOR")
        top_share = float(valid.value_counts(normalize=True).iloc[0]) if len(valid) else 0.0
        if uniq == 2 and top_share >= 0.995:
            flags.append("NEAR_CONSTANT_FACTOR")
        if act_rate > LOW_DISCRIMINATION_HIGH:
            flags.append("LOW_DISCRIMINATION_FACTOR(>95%)")
        if 0 < act_rate < LOW_DISCRIMINATION_LOW and total >= 100:
            flags.append("LOW_DISCRIMINATION_FACTOR(<0.5%)")

        per_factor.append({
            "factor_id": fid,
            "name": DEFINITION_INDEX[fid].name if fid in DEFINITION_INDEX else "",
            "sample_count": int(total),
            "null_rate": round(null_rate, 6),
            "activation_rate": round(act_rate, 6),
            "direction_dist": {str(int(k)): int(v) for k, v in dir_counts.items()},
            "mean_score": round(float(pd.to_numeric(sub["rule_score"], errors="coerce").mean()), 4),
            "std_score": round(float(pd.to_numeric(sub["rule_score"], errors="coerce").std(ddof=1)), 4),
            "unique_values": uniq,
            "flags": flags,
        })

    # 相关性（成对齐全观测上的 Pearson）
    pivot = df.pivot_table(
        index=["stock_code", "as_of"], columns="factor_id", values="normalized_value",
        aggfunc="first",
    )
    dup_pairs: list[dict] = []
    cols = list(pivot.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = pivot[cols[i]], pivot[cols[j]]
            both = pd.concat([a, b], axis=1).dropna()
            if len(both) < 30:
                continue
            sa, sb = both.iloc[:, 0], both.iloc[:, 1]
            if sa.std(ddof=0) == 0 or sb.std(ddof=0) == 0:
                continue
            corr = abs(float(np.corrcoef(sa, sb)[0, 1]))
            if corr > DUPLICATE_CORR:
                dup_pairs.append({
                    "factor_a": cols[i], "factor_b": cols[j],
                    "abs_corr": round(corr, 6), "n": int(len(both)),
                    "flag": "POTENTIAL_DUPLICATE_FACTOR",
                })
    return per_factor, dup_pairs


def render_markdown(per_factor: list[dict], dup_pairs: list[dict], meta: dict) -> str:
    flagged = [f for f in per_factor if f["flags"]]
    lines = [
        "# 因子质量审计报告（Phase 1.1 验收 §六）", "",
        f"- 生成时间：{meta['generated_at']}",
        f"- 数据快照：{meta['snapshot']}（{meta['snapshot_note']}）",
        f"- 样本面板：{meta['panel_rows']} 行观测 = {meta['stocks']} 只股票 × "
        f"~{meta['samples']} 个季度采样",
        f"- 判定阈值：activation_rate > {LOW_DISCRIMINATION_HIGH} 或 < {LOW_DISCRIMINATION_LOW}，"
        f"|corr| > {DUPLICATE_CORR}", "",
        "## 总览", "",
        f"- 因子总数：**{len(per_factor)}**",
        f"- 被标记因子：**{len(flagged)}**（"
        + (", ".join(f"`{f['factor_id']}`" for f in flagged) if flagged else "无") + "）",
        f"- 疑似重复因子对：**{len(dup_pairs)}**", "",
        "## 重要说明", "",
        "* `B_NATAL_*` 系列因子的区分度来源是**横截面**（不同股票不同命盘），",
        "  同一股票内随时间不变是设计语义，不应按时间序列激活率判死刑；",
        "  本报告仍标注其激活率，是否采纳由研究者判断并遵守 factor_dictionary 的语义声明。",
        "* `activation_rate` 基于 `normalized_value != 0`（与事件研究默认激活口径一致）。",
        "* 恒定/近恒定/疑似重复因子**只报告，不自动删除**（删除意味着丢失对照能力）。",
        "* 本面板基于真实行情快照（腾讯 hfq 导入），但因子本身不依赖行情，",
        "  因此面板统计对行情源不敏感；行情真实性影响的是收益侧而非因子侧。", "",
        "## 逐因子明细", "",
        "| factor_id | 样本 | null率 | 激活率 | 方向(+1/0/-1) | 均值 | 标准差 | 唯一值 | 标记 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for f in per_factor:
        d = f["direction_dist"]
        lines.append(
            f"| `{f['factor_id']}` | {f['sample_count']} | {f['null_rate']:.1%} | "
            f"{f['activation_rate']:.1%} | {d.get('1', 0)}/{d.get('0', 0)}/{d.get('-1', 0)} | "
            f"{f['mean_score']:.2f} | {f['std_score']:.2f} | {f['unique_values']} | "
            f"{'；'.join(f['flags']) or '—'} |"
        )
    lines += ["", "## 疑似重复因子对（|corr| > 0.98）", ""]
    if dup_pairs:
        lines += ["| 因子 A | 因子 B | |corr| | 样本 |", "|---|---|---|---|"]
        for p in dup_pairs:
            lines.append(f"| `{p['factor_a']}` | `{p['factor_b']}` | {p['abs_corr']:.4f} | {p['n']} |")
        lines.append("")
        lines.append("> 本列表**只报告，不自动删除**。相关≠同源：例如 B_YEAR_005（流年三合）与 "
                     "B_YEAR_010（流年三合局）语义相邻，需研究者按因子字典判断是否保留。")
    else:
        lines.append("无。")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="65 因子质量审计")
    parser.add_argument("--date-from", default="2018-01-01")
    parser.add_argument("--date-to", default=date.today().isoformat())
    parser.add_argument("--step-months", type=int, default=3)
    args = parser.parse_args(argv)

    market = OfflineMarketDataProvider()
    sample_dates = month_starts(
        date.fromisoformat(args.date_from), date.fromisoformat(args.date_to),
        step_months=args.step_months,
    )
    print(f"审计面板：{len(market._stocks)} 只股票 × {len(sample_dates)} 个采样日", flush=True)

    df = build_panel(market, sample_dates)
    print(f"面板观测行数：{len(df)}", flush=True)
    if df.empty:
        print("错误：面板为空", file=sys.stderr)
        return 1

    per_factor, dup_pairs = audit(df)

    out_dir = ROOT / "artifacts" / "acceptance"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "snapshot": f"{market._meta.source_label}@{market._meta.fetched_at}",
        "snapshot_note": "腾讯 hfq 快照（导入时点锚定）",
        "panel_rows": int(len(df)),
        "stocks": int(df["stock_code"].nunique()),
        "samples": len(sample_dates),
        "date_range": [args.date_from, args.date_to],
    }
    payload = {"meta": meta, "factors": per_factor, "duplicate_pairs": dup_pairs}
    (out_dir / "factor_quality.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = render_markdown(per_factor, dup_pairs, meta)
    (ROOT / "docs" / "factor_quality_report.md").write_text(md, encoding="utf-8")

    flagged = [f for f in per_factor if f["flags"]]
    print(f"被标记因子：{len(flagged)}；疑似重复对：{len(dup_pairs)}")
    print("已写出 docs/factor_quality_report.md 与 artifacts/acceptance/factor_quality.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
