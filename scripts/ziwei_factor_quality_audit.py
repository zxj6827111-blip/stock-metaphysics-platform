"""紫微因子质量审计 + 因子字典生成（Phase 2B）。

做什么
------
1. 在**真实导入快照**的股票池上，为每只股票构造出生档案；
2. 对每个 (股票 × as_of 采样点 × variant) 排紫微盘并计算 49 个 ``Z_*`` 因子；
3. 按 ``src/factors/ziwei/audit.py`` 的口径做质量审计
   （横截面 + 时间截面双重采样，否则区分度结论不可信）；
4. 输出：
     artifacts/acceptance/ziwei_factor_quality.json
     docs/ziwei-factor-dictionary.md     （由定义自动生成，避免手抄出错）

**只报告，不删除因子。** 低区分度是事实，不是缺陷；隐瞒才是缺陷。

用法
----
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/ziwei_factor_quality_audit.py
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/ziwei_factor_quality_audit.py --offline-universe
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONUTF8", "1")

from src.core.schemas.common import Availability, VariantMode  # noqa: E402
from src.core.stock.exchange_sessions import ex_value  # noqa: E402

#: 与 scripts/run_real_research.py 保持一致的真实股票池
DEFAULT_UNIVERSE = [
    "600519", "000001", "300750", "688981", "600036",
    "000858", "601318", "002594", "600000", "601899",
    "300059", "600030", "601012", "000333", "600276",
    "601888", "002415", "600887", "601166", "000651",
]

#: as_of 采样点（覆盖不同年份/月份，避免"同一天的流年流月流日"造成的假恒定）
SAMPLE_AS_OF = [
    datetime(2024, 11, 15, 14, 32),
    datetime(2025, 3, 20, 14, 32),
    datetime(2023, 7, 7, 14, 32),
    datetime(2022, 1, 10, 14, 32),
    datetime(2026, 5, 18, 14, 32),
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def collect_observations(offline_universe: bool) -> tuple[list[dict], list[str]]:
    """在真实快照上采集紫微因子观测；返回 ``(rows, problems)``。"""
    from src.core.schemas.stock import BirthProfileCreateRequest
    from src.core.stock.birth_profile import build_birth_profile
    from src.engines.base import EngineContext
    from src.engines.ziwei.ziwei_engine import ZiweiEngine, ZiweiUnavailableError
    from src.factors.ziwei.compute import compute_ziwei_factors
    from src.market.providers.offline import OfflineMarketDataProvider

    problems: list[str] = []
    rows: list[dict] = []

    market = OfflineMarketDataProvider()
    engine = ZiweiEngine()
    if engine.availability != Availability.OK:
        raise SystemExit(f"紫微服务不可用，无法审计：{engine.unavailable_reason()}")

    universe = DEFAULT_UNIVERSE[:6] if offline_universe else DEFAULT_UNIVERSE
    _log(f"股票池 {len(universe)} 只 × as_of {len(SAMPLE_AS_OF)} 个 × 2 variant")

    for code in universe:
        try:
            stock = market.get_stock(code)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{code}: 无法获取基础资料 {type(exc).__name__}: {exc}")
            continue
        if stock.listing_date is None:
            problems.append(f"{code}: 缺少上市日期，无法构造出生档案")
            continue

        for variant in (VariantMode.FORWARD, VariantMode.REVERSE):
            try:
                profile = build_birth_profile(
                    stock,
                    BirthProfileCreateRequest(variant_mode=variant),
                )
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{code}: 出生档案构造失败 {type(exc).__name__}: {exc}")
                continue

            for as_of in SAMPLE_AS_OF:
                if as_of.date() < stock.listing_date:
                    continue
                try:
                    chart = engine.calculate_chart(
                        EngineContext(stock_code=code, as_of=as_of),
                        birth_datetime=profile.birth_datetime.replace(tzinfo=None),
                        as_of=as_of,
                        variant_mode=variant,
                        stock_code=code,
                    )
                except ZiweiUnavailableError as exc:
                    problems.append(f"{code}@{as_of.date()}[{variant}]: {exc}")
                    continue
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{code}@{as_of.date()}[{variant}]: "
                                    f"{type(exc).__name__}: {exc}")
                    continue

                for o in compute_ziwei_factors(
                    chart, as_of, stock_code=code, variant=ex_value(variant),
                ):
                    rows.append({
                        "factor_id": o.factor_id,
                        "stock_code": code,
                        "as_of": as_of.isoformat(),
                        "variant": ex_value(variant),
                        "normalized_value": o.normalized_value,
                        "direction": int(o.direction),
                        "rule_score": o.rule_score,
                        "confidence": o.confidence,
                        "availability": o.availability,
                    })
    return rows, problems


def build_report(rows: list[dict]) -> dict:
    from src.factors.ziwei.audit import audit_many, pairwise_correlations

    qualities = audit_many(rows)
    series: dict[str, list[float | None]] = {}
    for r in rows:
        series.setdefault(r["factor_id"], []).append(r["normalized_value"])
    duplicates = pairwise_correlations(series)

    flagged = {
        "CONSTANT_FACTOR": [q.factor_id for q in qualities if "CONSTANT_FACTOR" in q.flags],
        "NEAR_CONSTANT_FACTOR": [q.factor_id for q in qualities if "NEAR_CONSTANT_FACTOR" in q.flags],
        "LOW_DISCRIMINATION_FACTOR":
            [q.factor_id for q in qualities if "LOW_DISCRIMINATION_FACTOR" in q.flags],
        "ALL_NULL_FACTOR": [q.factor_id for q in qualities if "ALL_NULL_FACTOR" in q.flags],
    }
    return {
        "generated_at": datetime.now().isoformat(),
        "sample_rows": len(rows),
        "factor_count": len(qualities),
        "flags": flagged,
        "duplicates": duplicates,
        "factors": [q.as_dict() for q in qualities],
    }


def write_dictionary(report: dict) -> Path:
    """由定义自动生成紫微因子字典（避免手抄与实际实现不一致）。"""
    from src.core.config import settings
    from src.factors.ziwei.definitions import (
        ALL_ZIWEI_DEFINITIONS,
        KEY_PALACES,
        VARIANT_SENSITIVE_FACTOR_IDS,
    )

    quality = {f["factor_id"]: f for f in report["factors"]}
    groups: dict[str, list] = {}
    for d in ALL_ZIWEI_DEFINITIONS:
        ns = d.factor_id.rsplit("_", 1)[0]
        groups.setdefault(ns, []).append(d)

    ns_cn = {
        "Z_LIFE": "命宫", "Z_FIN": "财帛宫（研究映射：资金/价格结构）",
        "Z_CAREER": "官禄宫（研究映射：公司经营）", "Z_MOVE": "迁移宫（研究映射：外部市场）",
        "Z_MUTAGEN": "生年四化", "Z_TRINE": "三方四正",
        "Z_YEAR": "流年", "Z_MONTH": "流月", "Z_DAY": "流日（周度聚合输入）",
        "Z_DECADE": "大限（随 variant 变化）", "Z_AGE": "小限（随 variant 变化）",
    }

    lines: list[str] = [
        "# 紫微因子字典（Phase 2B）",
        "",
        "> 本文件由 `scripts/ziwei_factor_quality_audit.py` **自动生成**，请勿手工编辑。",
        f"> 规则版本：定义 `{settings.ziwei_factor_rule_version}`，"
        f"观测按 variant 后缀区分为 `{settings.ziwei_factor_rule_version}.fwd` / "
        f"`{settings.ziwei_factor_rule_version}.rev`。",
        f"> 引擎版本：`{settings.ziwei_engine_version}`。",
        "",
        "---",
        "",
        "## 0. 先读这一段",
        "",
        "### 0.1 宫位→金融含义的映射不是传统定论",
        "",
        "「财帛宫 = 资金/价格」「官禄宫 = 公司经营」「迁移宫 = 外部市场」"
        "**不是传统紫微斗数的规定**，而是本项目的**研究假设**，"
        f"版本号 `{settings.ziwei_stock_mapping_version}`，必须先经历史回测检验。",
        "禁止在 UI / 文档 / 报告中表述为「传统紫微规定财帛宫就是股价」。",
        "",
        "### 0.2 方向不是收益率",
        "",
        "每个因子的 `direction` / `rule_score` 表达的是**传统规则认为的方向与强度**：",
        "",
        "* 吉曜 / 庙旺 / 化禄权科 → 传统视为偏吉（`POSITIVE`）",
        "* 煞曜 / 化忌 → 传统视为偏凶（`NEGATIVE`）",
        "* 宫位位阶 / 主星数量 / 五行局 → 结构性变量（`NEUTRAL`）",
        "",
        "它们**都不是预期收益率，也不是上涨概率**。",
        "",
        "### 0.3 关键宫（研究映射的位阶体系）",
        "",
        f"核心宫（位阶 2）：{'、'.join(KEY_PALACES)}；次核心宫（位阶 1）：福德、田宅；其余位阶 0。",
        "",
        "### 0.4 随 variant 变化的因子",
        "",
        "只有以下因子会随顺行/逆行 variant 变化"
        f"（{len(VARIANT_SENSITIVE_FACTOR_IDS)} 个）："
        f"{'、'.join(f'`{i}`' for i in VARIANT_SENSITIVE_FACTOR_IDS)}。",
        "",
        "其余因子在两个 variant 之间**完全一致** —— 因为 variant 只影响大限/小限顺逆"
        "与长生十二神顺逆（见 `docs/calculation-differences-phase2-ziwei.md` D4）。",
        "**两个 variant 不是两条独立证据。**",
        "",
        "---",
        "",
        f"## 1. 因子总览（{len(ALL_ZIWEI_DEFINITIONS)} 个）",
        "",
        "| 命名空间 | 数量 | 含义 |",
        "|---|---|---|",
    ]
    for ns in sorted(groups):
        lines.append(f"| `{ns}_*` | {len(groups[ns])} | {ns_cn.get(ns, '')} |")

    lines += [
        "",
        "---",
        "",
        "## 2. 逐因子定义",
        "",
    ]
    for ns in sorted(groups):
        lines += [f"### {ns}_* · {ns_cn.get(ns, '')}", ""]
        for d in groups[ns]:
            q = quality.get(d.factor_id, {})
            flags = "、".join(f"`{f}`" for f in q.get("flags", [])) or "—"
            direction_cn = {"1": "正向", "0": "中性", "-1": "负向"}.get(
                str(int(d.default_direction)), "中性")
            lines += [
                f"#### `{d.factor_id}` · {d.name}",
                "",
                f"* **方向（传统规则）**：{direction_cn}",
                f"* **原始值单位**：`{d.raw_unit}`",
                f"* **归一化**：{d.normalized_hint}",
                f"* **依赖盘面字段**：{', '.join(f'`{r}`' for r in d.requires)}",
                f"* **标签**：{', '.join(d.tags) or '—'}",
                f"* **观测 rule_version**：`{settings.ziwei_factor_rule_version}.fwd` / "
                f"`{settings.ziwei_factor_rule_version}.rev`",
                "",
                "**定义**",
                "",
                d.definition,
                "",
                "**计算**",
                "",
                f"```\n{d.computation}\n```",
                "",
                f"**规则分语义**：{d.rule_score_meaning}",
                "",
                "**质量审计（真实快照）**",
                "",
                "| 样本数 | 空值率 | 激活率 | 不同取值数 | 均值 | 标准差 | 标记 |",
                "|---|---|---|---|---|---|---|",
                (f"| {q.get('sample_count', '—')} | {q.get('null_rate', '—')} | "
                 f"{q.get('activation_rate', '—')} | {q.get('unique_value_count', '—')} | "
                 f"{q.get('mean', '—')} | {q.get('std', '—')} | {flags} |"),
                "",
            ]

    flagged_names = report["flags"]
    lines += [
        "---",
        "",
        "## 3. 质量标记汇总（**只报告，不删除**）",
        "",
        "| 标记 | 数量 | 因子 |",
        "|---|---|---|",
        f"| `CONSTANT_FACTOR` | {len(flagged_names['CONSTANT_FACTOR'])} | "
        f"{'、'.join(f'`{i}`' for i in flagged_names['CONSTANT_FACTOR']) or '—'} |",
        f"| `NEAR_CONSTANT_FACTOR` | {len(flagged_names['NEAR_CONSTANT_FACTOR'])} | "
        f"{'、'.join(f'`{i}`' for i in flagged_names['NEAR_CONSTANT_FACTOR']) or '—'} |",
        f"| `LOW_DISCRIMINATION_FACTOR` | {len(flagged_names['LOW_DISCRIMINATION_FACTOR'])} | "
        f"{'、'.join(f'`{i}`' for i in flagged_names['LOW_DISCRIMINATION_FACTOR']) or '—'} |",
        f"| `ALL_NULL_FACTOR` | {len(flagged_names['ALL_NULL_FACTOR'])} | "
        f"{'、'.join(f'`{i}`' for i in flagged_names['ALL_NULL_FACTOR']) or '—'} |",
        "",
        "**疑似重复（|Pearson| > 0.98）**",
        "",
    ]
    if report["duplicates"]:
        lines += ["| A | B | Pearson | 样本 |", "|---|---|---|---|"]
        for p in report["duplicates"]:
            lines.append(f"| `{p['a']}` | `{p['b']}` | {p['pearson']} | {p['n']} |")
    else:
        lines.append("无。")
    lines += [
        "",
        "> 审计口径说明：连续型因子（如庙旺和）**不使用** `activation_rate` 判低区分度 —— "
        "它们的取值几乎永远不为 0，用激活率会误判。判定规则见 "
        "`src/factors/ziwei/audit.py` 模块文档。",
        "",
        "---",
        "",
        "## 4. 参考",
        "",
        "* [`docs/ziwei-engine.md`](ziwei-engine.md)",
        "* [`docs/calculation-differences-phase2-ziwei.md`](calculation-differences-phase2-ziwei.md)",
        "* [`docs/factor_quality_report.md`](factor_quality_report.md)（Phase 1 因子审计）",
        "",
    ]

    out = ROOT / "docs" / "ziwei-factor-dictionary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-universe", action="store_true",
                        help="只用前 6 只股票（快速跑通）")
    parser.add_argument("--skip-dictionary", action="store_true")
    args = parser.parse_args()

    rows, problems = collect_observations(args.offline_universe)
    if not rows:
        _log("没有采集到任何观测，审计无法进行。")
        for p in problems[:10]:
            _log(f"  - {p}")
        return 1

    report = build_report(rows)
    report["problems"] = problems

    out_dir = ROOT / "artifacts" / "acceptance"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ziwei_factor_quality.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    _log(f"观测行数：{report['sample_rows']}  因子数：{report['factor_count']}")
    for key, val in report["flags"].items():
        _log(f"  {key}: {len(val)}" + (f" -> {', '.join(val)}" if val else ""))
    _log(f"疑似重复对：{len(report['duplicates'])}")
    if problems:
        _log(f"采集问题 {len(problems)} 条（前 3）：")
        for p in problems[:3]:
            _log(f"  - {p}")

    if not args.skip_dictionary:
        path = write_dictionary(report)
        _log(f"因子字典已写入：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
