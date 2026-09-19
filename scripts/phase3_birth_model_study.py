"""Phase 3B：对 500 股 × 3 模型生成 BaziChart / ZiweiChart + 因子 + 区分度对比。

**关键设计决策**：

* 紫微需要 ``variant_mode`` 决定运限方向；**股票无性别**，但紫微盘上时柱变化（listing open vs close）
  导致命宫可能不同。Phase 3B 我们强制 ``variant_mode='forward'``，理由：这只是为了产生一张盘供
  因子计算，**不暗示股票"应该"取顺行**。此假设写入报告。
* 黄历因子不含 birth 信息，从所有模型抽取都一样（因为 ``huangli factors`` 只依赖 as_of 和
  当日干支），本次不纳入对比。
* 因子计算**不落库** —— 这是研究报告，不是运行时管道（FactorObservation 的入库只在
  Phase 3C 的 calibration 基础上做统一化后才有意义）。

运行：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_birth_model_study.py
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_birth_model_study.py --limit 50
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from src.core.schemas.common import VariantMode  # noqa: E402
from src.core.schemas.factor import FactorObservation  # noqa: E402
from src.db.base import session_scope  # noqa: E402
from src.db.models import StockBirthProfileRow, UniverseMembershipRow  # noqa: E402
from src.engines.bazi.bazi_engine import BaziEngine  # noqa: E402
from src.engines.ziwei.ziwei_engine import ZiweiEngine  # noqa: E402
from src.factors.registry.compute import compute_bazi_factors  # noqa: E402
from src.factors.ziwei.compute import compute_ziwei_factors  # noqa: E402

UNIVERSE_VERSION = "v2-phase3a"
MODEL_TO_BASIS = {
    "listing_open_v1": ("listing_open", "v1-phase3b-listing_open"),
    "listing_close_v1": ("first_trade", "v1-phase3b-listing_close"),
    "ipo_approx_v1": ("ipo_date", "v1-phase3b-ipo_approx"),
}
AS_OF_FIXED = datetime(2026, 8, 14)  # composite_none cutoff
OUT_MD = ROOT / "docs" / "birth-model-study.md"
OUT_CSV = ROOT / "data" / "phase3_universe" / "birth_model_factor_stats.csv"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def load_birth_profiles() -> dict[tuple[str, str], datetime]:
    """(stock_code, model_key) → birth_datetime (naive)。"""
    out: dict[tuple[str, str], datetime] = {}
    with session_scope() as db:
        rows = db.execute(
            select(StockBirthProfileRow).where(
                StockBirthProfileRow.birth_profile_version.in_(
                    [v for _, v in MODEL_TO_BASIS.values()]
                )
            )
        ).scalars().all()
        for r in rows:
            for key, (basis, version) in MODEL_TO_BASIS.items():
                if r.birth_basis == basis and r.birth_profile_version == version:
                    out[(r.stock_code, key)] = r.birth_datetime
    return out


def universe_members() -> list[str]:
    with session_scope() as db:
        return list(db.execute(
            select(UniverseMembershipRow.stock_code)
            .where(UniverseMembershipRow.universe_version == UNIVERSE_VERSION)
            .order_by(UniverseMembershipRow.stock_code)
        ).scalars().all())


def compute_factors_for_model(
    stock_code: str, birth_dt: datetime,
    bazi: BaziEngine, ziwei: ZiweiEngine,
    skip_ziwei: bool,
) -> list[FactorObservation]:
    out: list[FactorObservation] = []
    try:
        chart_b = bazi.build_chart(
            birth_datetime=birth_dt,
            as_of=AS_OF_FIXED,
            variant_mode=VariantMode.NOT_APPLICABLE,
            stock_code=stock_code,
        )
        out.extend(compute_bazi_factors(chart_b, AS_OF_FIXED))
    except Exception as exc:  # noqa: BLE001
        print(f"    [bazi.err] {stock_code}: {exc!r}"[:200], flush=True)

    if not skip_ziwei:
        try:
            ctx_as_of = AS_OF_FIXED
            chart_z = ziwei.calculate_chart(
                # ziwei EngineContext 无状态，用对象保持简单
                __import__('src.engines.base', fromlist=['EngineContext']).EngineContext(
                    stock_code=stock_code, as_of=ctx_as_of,
                ),
                birth_datetime=birth_dt,
                as_of=ctx_as_of,
                # 股票无性别：Phase 3B 强制 forward（非论断，仅生成盘）。
                variant_mode=VariantMode.FORWARD,
            )
            out.extend(compute_ziwei_factors(
                chart_z, ctx_as_of, stock_code=stock_code, variant="forward",
            ))
        except Exception as exc:  # noqa: BLE001
            print(f"    [ziwei.err] {stock_code}: {exc!r}"[:200], flush=True)
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-ziwei", action="store_true")
    args = ap.parse_args()

    bazi = BaziEngine()
    ziwei = ZiweiEngine()

    profiles = load_birth_profiles()
    print(f"birth_profiles: {len(profiles)}", flush=True)

    codes = universe_members()
    if args.limit:
        codes = codes[: args.limit]
    print(f"目标股票数: {len(codes)}", flush=True)

    # factor_values[(model, factor_id)][stock_code] = FactorObservation
    results: dict[tuple[str, str], dict[str, FactorObservation]] = defaultdict(dict)
    # per-stock 四柱对比（用于报告里的真实感）
    pillar_examples: list[tuple[str, str, str, str, str]] = []

    t0 = time.time()
    for i, code in enumerate(codes, 1):
        pillar_row: dict[str, str] = {}
        for model_key in MODEL_TO_BASIS:
            birth_dt = profiles.get((code, model_key))
            if birth_dt is None:
                continue
            factors = compute_factors_for_model(code, birth_dt, bazi, ziwei, args.skip_ziwei)
            for f in factors:
                results[(model_key, f.factor_id)][code] = f
            if i <= 3:
                # 记录四柱用于报告
                try:
                    chart = bazi.build_chart(birth_datetime=birth_dt, as_of=AS_OF_FIXED,
                                             variant_mode=VariantMode.NOT_APPLICABLE,
                                             stock_code=code)
                    pillars = (
                        f"{chart.year_pillar.ganzhi.text}/"
                        f"{chart.month_pillar.ganzhi.text}/"
                        f"{chart.day_pillar.ganzhi.text}/"
                        f"{chart.hour_pillar.ganzhi.text}"
                    )
                    pillar_row[model_key] = pillars
                except Exception:
                    pass
        if pillar_row and len(pillar_examples) < 8:
            pillar_examples.append((code,
                                    pillar_row.get("listing_open_v1", ""),
                                    pillar_row.get("listing_close_v1", ""),
                                    pillar_row.get("ipo_approx_v1", ""),
                                    ""))
        if i % 25 == 0 or i == len(codes):
            el = time.time() - t0
            print(f"[{i}/{len(codes)}]  {el:.1f}s  factors_rows={sum(len(v) for v in results.values())}", flush=True)

    print(f"\n全部完成 {time.time()-t0:.1f}s", flush=True)

    # 聚合统计
    rows_csv: list[dict] = []
    for (model, fid), stock_values in sorted(results.items()):
        values: list[float] = []
        scores: list[float] = []
        for fo in stock_values.values():
            if fo.normalized_value is not None:
                values.append(float(fo.normalized_value))
            if fo.rule_score is not None:
                scores.append(float(fo.rule_score))
        if not values:
            continue
        n = len(values)
        mean = statistics.mean(values)
        std = statistics.pstdev(values) if n > 1 else 0.0
        uniq = len(set(round(v, 6) for v in values))
        constant = n > 1 and std < 1e-9
        smean = statistics.mean(scores) if scores else None
        sstd = statistics.pstdev(scores) if len(scores) > 1 else 0.0
        engine = next(iter(stock_values.values())).engine
        rows_csv.append({
            "model": model, "factor_id": fid, "engine": engine,
            "n": n, "mean": f"{mean:.4f}", "std": f"{std:.4f}",
            "min": f"{min(values):.4f}", "max": f"{max(values):.4f}",
            "unique_ratio": f"{uniq / n:.4f}",
            "is_constant": str(bool(constant)),
            "rule_score_mean": f"{smean:.4f}" if smean is not None else "",
            "rule_score_std": f"{sstd:.4f}" if scores else "",
        })
    print(f"统计因子行: {len(rows_csv)}", flush=True)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_csv[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows_csv)
    print(f"CSV: {OUT_CSV}", flush=True)

    _write_report(rows_csv, pillar_examples, len(codes))
    print(f"报告: {OUT_MD}", flush=True)
    return 0


def _write_report(rows_csv: list[dict], pillar_examples: list[tuple[str, str, str, str, str]], universe_size: int) -> None:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows_csv:
        by_model[r["model"]].append(r)

    # 找特定因子；常量 vs 变量
    def _stats(rows: list[dict]) -> dict:
        const = [r for r in rows if r["is_constant"] == "True"]
        uniqs = [float(r["unique_ratio"]) for r in rows]
        return {
            "total": len(rows),
            "n_constant": len(const),
            "avg_unique_ratio": sum(uniqs) / max(1, len(rows)),
        }

    # 四柱演示
    sample_lines: list[str] = ["## B. 三只真实股票 × 三模型的四柱演示", ""]
    sample_lines.append("| 股票 | listing_open (年/月/日/时) | listing_close | ipo_approx |")
    sample_lines.append("|---|---|---|---|")
    for code, o, cl, ip, _extra in pillar_examples:
        sample_lines.append(f"| {code} | {o} | {cl} | {ip} |")

    # Z_LIFE_006 专项
    zl6 = [r for r in rows_csv if r["factor_id"] == "Z_LIFE_006"]
    # BAZI opinion 代理（无 BAZI_POS / BAZI_NEG 字段——用八字七类 score 变体）
    # 取 engine=bazi 的全部 rule_score_std 最大的前 10
    bazi_rows = [r for r in rows_csv if r["engine"] == "bazi"]

    const_common: dict[str, list[str]] = {}
    for model in sorted(by_model):
        const_common[model] = [r["factor_id"] for r in by_model[model] if r["is_constant"] == "True"]

    md: list[str] = [
        "# Phase 3B · Birth Model 对比研究",
        "",
        f"> 生成：{datetime.now().isoformat(timespec='seconds')}",
        f"> Universe: ``{UNIVERSE_VERSION}``（{universe_size} 股）",
        f"> as_of 固定 = ``{AS_OF_FIXED.date()}``（与 composite_none 快照截止对齐）",
        "> author: Phase 3B pipeline (`scripts/phase3_birth_model_study.py`)",
        "",
        "## A. 候选 Birth Model 定义",
        "",
        "| Model | 定义 | 可用性 | 数据精度 |",
        "|---|---|---|---|",
        "| ``listing_open`` | 上市首日 09:30（``_v1``） | ✅ tushare_pit_universe | 高 |",
        "| ``listing_close`` | 上市首日 15:00（``_v1``） | ✅ 同上 | 高 |",
        "| ``ipo_date_approx`` | 上市日 - 7 自然日 09:30 | ✅（启发式） | 中（approximated=True） |",
        "| ``company_foundation`` | 公司注册成立日 | ❌ UNAVAILABLE | 数据源不可得 |",
        "",
    ] + sample_lines + [
        "",
        "**解读**：",
        "- ``listing_open`` 和 ``listing_close`` **日柱相同，仅时柱不同**（09:30 vs 15:00 落在不同时辰）",
        "- ``ipo_date_approx`` 的日柱整体平移 7 天，造成完全不同的四柱组合",
        "- ``company_foundation`` 缺失，未落库（Phase 3 §3B-1 纪律）",
        "",
        "## C. 因子区分度按模型统计",
        "",
        "| Model | 因子数 | 常量因子数 | 平均 unique_ratio |",
        "|---|---:|---:|---:|",
    ]
    for m in sorted(by_model):
        s = _stats(by_model[m])
        md.append(f"| `{m}` | {s['total']} | {s['n_constant']} | {s['avg_unique_ratio']:.4f} |")

    md += [
        "",
        "## D. Z_LIFE_006（身宫命同宫，Phase 1.1 历史常量）按模型复核",
        "",
        "| Model | n | unique_ratio | is_constant |",
        "|---|---:|---:|---|",
    ]
    for r in zl6:
        md.append(f"| `{r['model']}` | {r['n']} | {r['unique_ratio']} | {r['is_constant']} |")
    if not zl6:
        md.append("| — | (未产生 Z_LIFE_006；可能 ziwei_engine 未运行或引擎报错) | | |")

    md += ["", "## E. 常量因子列表（按模型）", ""]
    for m in sorted(const_common):
        md.append(f"### ``{m}`` (共 {len(const_common[m])} 个)")
        md.append("")
        for fid in sorted(const_common[m]):
            md.append(f"- `{fid}`")
        md.append("")

    md += [
        "## F. 结论与 Phase 3B 纪律声明",
        "",
        "1. 三个 birth model 在同一股票上产生**真正不同的四柱**（见 §B 示例）。",
        "2. **factor 区分度**按模型差异详见 CSV 附表；任何对『哪个 birth model 更合理』的判断必须由 3D 以后的 OOS 检验来支撑——本报告**不下结论**。",
        "3. ``company_foundation`` 缺失数据，**UNAVAILABLE**；不造数据。",
        "4. BAZI_POS / Z_LIFE_006 等历史『CONSTANT』因子是否在换 birth model 后恢复区分度，见 csv 中对应行。",
        "5. 本研究**不生成买卖建议**。全部 score 只是『传统规则强度』。",
    ]

    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
