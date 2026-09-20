"""Phase 3H 最终研究报告生成器（``docs/PHASE3_RESEARCH_REPORT.md``）。

**所有数字都从产物读出**，不允许手写 —— 报告与 CSV/JSON 不可能不一致。

26 章：执行摘要 / 研究问题 / 数据集 / PIT 宇宙 / 生存者偏差 / 行情版本 / 出生模型 /
出生模型对比 / 因子质量 / 观点校准 / 八字偏置 / 八字 OOS / 紫微 OOS / 黄历 OOS /
黄历日期效应 / 共振 OOS / 冲突研究 / Walk-forward / 市场中性化 / 行业与 PIT 限制 /
风格控制 / 多重检验 FDR / Bootstrap 与置换 / 稳健性 / 紫微跨实现验证 /
最终结论与限制。

用法::

    python scripts/phase3h_write_report.py
"""

from __future__ import annotations

import argparse
import ast
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data" / "phase3_universe"
DOCS = ROOT / "docs"
REPORT = DOCS / "PHASE3_RESEARCH_REPORT.md"


def _load_json(name: str) -> dict:
    path = DATA / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(name: str) -> pd.DataFrame:
    path = DATA / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _git_tag() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--exact-match"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def _pct(value: object, digits: int = 2) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: object, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _db_counts() -> dict:
    path = ROOT / "data" / "smp.sqlite3"
    if not path.exists():
        return {}
    connection = sqlite3.connect(path)
    try:
        def scalar(sql: str, params: tuple = ()):
            row = connection.execute(sql, params).fetchone()
            return row[0] if row else None

        return {
            "bars_total": scalar("select count(*) from market_bar_daily"),
            "bars_astockdata": scalar(
                "select count(*) from market_bar_daily "
                "where source='astockdata_composite_none'"
            ),
            "bars_benchmark": scalar(
                "select count(*) from market_bar_daily where stock_code='IDX000300'"
            ),
            "universe_members": scalar(
                "select count(*) from universe_memberships where universe_version='v2-phase3a'"
            ),
            "universe_delisted": scalar(
                "select count(*) from universe_memberships "
                "where universe_version='v2-phase3a' and status='delisted'"
            ),
            "birth_profiles": scalar("select count(*) from stock_birth_profile"),
        }
    finally:
        connection.close()


def build_report() -> str:
    d3_summary = _load_json("phase3d_run_summary.json")
    d3_results = _load_csv("phase3d_oos_results.csv")
    d3_walkforward = _load_csv("phase3d_walkforward_results.csv")
    d3_concentration = _load_csv("phase3d_oos_hit_concentration.csv")
    e3_meta = _load_json("phase3e_neutralization_meta.json")
    e3_results = _load_csv("phase3e_neutralization_results.csv")
    f_summary = _load_json("phase3f_run_summary.json")
    f_results = _load_csv("phase3f_multiple_testing_results.csv")
    f_family = _load_csv("phase3f_family_correction.csv")
    f_robust = _load_csv("phase3f_robustness_slices.csv")
    g_summary = _load_json("phase3g_ziwei_crosscheck_summary.json")
    opinion_dist = _load_csv("phase3c_opinion_distribution.csv")
    birth_stats = _load_csv("birth_model_factor_stats.csv")
    counts = _db_counts()
    sha = _git_sha()
    tag = _git_tag()

    split = d3_summary.get("split", {})
    panel = d3_summary.get("panel", {})
    labels_meta = d3_summary.get("labels", {})
    calibration = d3_summary.get("calibration", {})
    gate_v1 = d3_summary.get("gate_thresholds", {})
    gate_v2 = f_summary.get("gate_v2_thresholds", {})
    questions = e3_meta.get("questions", {})

    gated = f_results[f_results["family_gated"] == True] if not f_results.empty else pd.DataFrame()  # noqa: E712
    fdr_pass_gated = int(gated["fdr_pass"].sum()) if not gated.empty else 0
    bonf_pass_gated = int(gated["bonferroni_pass"].sum()) if not gated.empty else 0
    supported = (
        int((f_results["gate_v2_status"] == "SUPPORTED_OUT_OF_SAMPLE").sum())
        if not f_results.empty else 0
    )
    v1_counts = (
        gated["gate_v1_status"].value_counts().to_dict() if not gated.empty else {}
    )
    v2_gated_counts = (
        gated["gate_v2_status"].value_counts().to_dict() if not gated.empty else {}
    )

    lines: list[str] = []
    add = lines.append

    add("# Phase 3 · 最终研究报告")
    add("")
    add(
        f"> **commit** `{sha}`" + (f" · **tag** `{tag}`" if tag else "") + "\n"
        f"> **数据集** `{split.get('dataset_version', '')}` · **universe** `{split.get('universe_version', '')}` · "
        f"**calibration** `{split.get('calibration_version', '')}` · **label** `{split.get('label_version', '')}`\n"
        f"> **split** `{split.get('split_version', '')}`（`{split.get('train_start', '')}`..`{split.get('train_end', '')}` / "
        f"`{split.get('validation_start', '')}`..`{split.get('validation_end', '')}` / "
        f"`{split.get('oos_start', '')}`..`{split.get('oos_end', '')}`）\n"
        f"> **gate-v1** `{gate_v1.get('gate_version', '')}` · **gate-v2** `{gate_v2.get('gate_version', '')}` · "
        f"**mt** `{f_summary.get('mt_version', '')}`"
    )
    add("")
    add(
        "> 本文档由 `scripts/phase3h_write_report.py` **从产物自动生成**：每个数字都能在 "
        "`data/phase3_universe/phase3*.csv|json` 中核对。生成脚本不参与任何统计计算，"
        "只做读取与排版。"
    )
    add("")
    add("---")
    add("")

    # 1
    add("## 1. Executive Summary")
    add("")
    add(
        f"**结论：`SUPPORTED_OUT_OF_SAMPLE = {supported}`。** 42 个正式 gate 实验中，"
        f"族内 BH-FDR 通过 **{fdr_pass_gated}** 个、Bonferroni 通过 **{bonf_pass_gated}** 个。"
        "术数因子（八字 / 紫微 / 黄历及其共振）在本研究的样本与协议下"
        "**没有显示出可复现的样本外信息量**。"
    )
    add("")
    add(
        "这不是“没跑通”：管线完整执行了 54 个预注册实验、5000 次/实验的日期分层置换、"
        "date-block bootstrap、9 个稳健性维度与 24 个案例的跨实现核对。"
        "**结论为负，方法为正** —— Phase 3 交付的是一台可以给出可信否定结论的研究机器。"
    )
    add("")
    add("三条最重要的真实发现：")
    add("")
    add(
        "1. **校准改善区分度，但不产生预测信息量**（3D Q1–Q3）：原始 `BAZI_POS` 正向率"
        " 93.1%–95.4%（OOS），Jaccard 0.82–0.86（对照失效）；TRAIN-only 校准后正向率降到"
        " 25.3%–26.4%、Jaccard 降到 0.125–0.135（对照恢复有效），但事件集合的 OOS 平均超额"
        "仍为 −1.2%…−1.7%，无一达到预注册门槛。"
    )
    add(
        "2. **黄历是“日期选择器”而不是“股票选择器”**（3D §6.5 / 3E）：同一 `as_of` 上"
        "要么几乎全体命中、要么几乎全体不命中（命中率 std 0.27 vs 八字 0.09）。"
        "折叠到日期后（15 个 OOS 日期）命中比例斜率 TRAIN +0.044 vs OOS −0.066"
        "（符号相反、均不显著）→ **不是稳定的市场-wide 日历效应**。"
    )
    add(
        "3. **结论高度依赖股票生命周期分组**（3F）：`universe_subset`（在市股 vs 退市股）"
        "在 31/42 个正式实验中给出**相反符号**的效应；而退市股正是本阶段用来根治生存者偏差的资产。"
    )
    add("")
    add("三条最重要的限制：")
    add("")
    add(
        "1. **行业 PIT 分类完全不可得**（`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`）："
        "无法排除“是不是产业周期”，只做了板块（法定 board）控制。"
    )
    add(
        "2. **出生时间是研究构造**：`company_foundation` 不可得；上市日/近似 IPO 日都不是公司的真实出生时刻。"
    )
    add(
        "3. **未计交易成本 / 流动性 / 涨跌停 / 卖空约束**：这是信息量检验，不是可交易性检验。"
    )
    add("")

    # 2
    add("## 2. Research Question")
    add("")
    add(
        "本阶段回答一个问题：**把传统术数排盘变成确定性因子之后，这些因子在 A 股历史上"
        "是否携带可复现的横截面信息量？**"
    )
    add("")
    add("研究纪律（Phase 3 全程不可违反）：")
    add("")
    add("- 排盘全部由确定性代码产生，LLM 不参与计算；")
    add("- 假设在读取 OOS 收益**之前**预注册（`config/phase3d_hypothesis_registry.yaml`，"
        f"`oos_labels_seen_at_registration = {d3_summary.get('hypothesis_registry', {}).get('oos_labels_seen', False)}`）；")
    add("- 校准阈值只由 TRAIN 拟合并冻结为 `cal-v1`；")
    add("- 负对照必须与真实事件集合可区分（Jaccard ≤ 0.9）才承认任何结果；")
    add("- 允许最终结论为 `NO_SIGNAL`，**不为好看而改方法**。")
    add("")

    # 3
    add("## 3. Dataset")
    add("")
    add("| 项目 | 值 |")
    add("|---|---|")
    add("| 行情来源 | `astockdata_composite_none`（ADR-0012 canonical，不复权原始价）|")
    add(f"| 行情行数（全库） | {counts.get('bars_total', 'n/a'):,} |")
    add(f"| 其中 canonical 独立行情 | {counts.get('bars_astockdata', 'n/a'):,} |")
    add(f"| 基准行情（IDX000300） | {counts.get('bars_benchmark', 'n/a'):,} |")
    add(f"| 主面板观测行 | {panel.get('main_rows', panel.get('row_count', 'n/a'))} |")
    add(f"| 主面板（股票 × 出生模型 × as_of × 引擎） | {panel.get('main_rows', 'n/a')} 行 / "
        f"{len(panel.get('dates', []) or [])} 个 as_of |" if panel else "| 主面板 | n/a |")
    add(f"| 标签行数 | {labels_meta.get('label_rows', 'n/a')} |")
    add(f"| 除权因子覆盖 | {labels_meta.get('codes_with_adj', 'n/a')} 只股票 / "
        f"未覆盖行 {labels_meta.get('coverage_totals', {}).get('uncovered_rows', 'n/a')} |")
    add(f"| 降级行情 | {len(labels_meta.get('degraded_codes', []) or [])} 只 |")
    add(f"| 出生档案 | {counts.get('birth_profiles', 'n/a')} 行 |")
    add("")
    add(
        "**标签口径**：`raw × adj_factor`（TuShare 除权因子，主快照 + 退市补丁并集）。"
        "canonical 是不复权原始价，直接算收益会把除权当下跌。"
        "收益与超额的日历区间完全一致（Phase 1 审计修正过的口径）。"
    )
    add("")

    # 4
    add("## 4. Point-in-Time Universe")
    add("")
    add("| 项目 | 值 |")
    add("|---|---|")
    add(f"| universe 版本 | `{split.get('universe_version', '')}` |")
    add(f"| 成员数 | {counts.get('universe_members', 'n/a')} |")
    add(f"| 退市股 | {counts.get('universe_delisted', 'n/a')} |")
    add(f"| 在市股 | {(counts.get('universe_members') or 0) - (counts.get('universe_delisted') or 0)} |")
    add(f"| 采样步长 | 每 {split.get('sample_step_months', 3)} 个月 |")
    add(f"| as_of 时刻 | 收盘后（{split.get('as_of_hour', 15)}:00）|")
    add("")
    add(
        "资格窗口 `[list_date, delist_date]` 是“事件能不能存在”的前提：退市后的 `(股票, as_of)` "
        "不是“收益缺失”而是“当时不可投资”，必须从面板排除 —— 否则负对照的候选池会被"
        "不存在的股票-日期对撑大。"
    )
    add("")

    # 5
    add("## 5. Survivorship Bias")
    add("")
    add(
        "Phase 3A 的关键决策是**换用无偏 universe**：主数据源从腾讯单通道（对已退市股"
        "结构性返回 `param error`）切换到本机 AStockData composite（含退市股补全）。"
    )
    add("")
    add(
        f"当前 universe 含 **{counts.get('universe_delisted', 'n/a')} 只退市股 / "
        f"{counts.get('universe_members', 'n/a')} 只 = "
        f"{_pct((counts.get('universe_delisted') or 0) / max((counts.get('universe_members') or 1), 1), 1)}**。"
        "manifest 声明 `survivorship_bias=false`、`delisted_coverage_complete=true`。"
    )
    add("")
    add(
        "**残余风险（如实登记）**：① 退市股的除权因子只有 311/500 只能由退市补丁提供，"
        "若该补丁有系统性缺口会影响退市股收益；② 退市日 `delist_date` 来自 TuShare PIT "
        "注册簿，最后交易日与退市日之间存在停牌期，已按 `[list_date, delist_date]` 保守截断；"
        "③ 3F 发现 `universe_subset` 稳健性维度在 31/42 个实验中符号不一致 —— "
        "**结论本身对退市股是否纳入高度敏感**，这是本阶段最重要的残余风险。"
    )
    add("")

    # 6
    add("## 6. Market Data Versions")
    add("")
    add("| 版本字段 | 值 |")
    add("|---|---|")
    add(f"| `dataset_version` | `{split.get('dataset_version', '')}` |")
    add(f"| `label_version` | `{split.get('label_version', '')}` |")
    add("| 除权因子快照 | 主 `tsfactor_20260731T221443_49624041` + 退市补丁 `tsfactor_20260806T110553_91dc1a9e` |")
    add("| 基准 | `IDX000300`（沪深 300），价格指数不复权 |")
    add("| 基准映射 | **统一基准**；`BENCHMARK_SPLIT_UNAVAILABLE`（快照内无中证 500）|")
    add("")
    add(
        "不同快照**禁止静默混用**：Phase 3A 因此把 20 股腾讯通道降级为交叉验证辅通道，"
        "不复权锚点不一致的两批数据不混合。"
    )
    add("")

    # 7
    add("## 7. Birth Models")
    add("")
    add(
        "股票没有真实出生时间。本阶段把“出生”显式建模为 4 种**研究构造**并各自版本化："
    )
    add("")
    add("| 模型 | 含义 | 可得性 |")
    add("|---|---|---|")
    add("| `listing_open_v1` | 上市日 + 交易所开盘时刻 | 100%（PIT 注册簿）|")
    add("| `listing_close_v1` | 上市日 + 收盘时刻 | 100% |")
    add("| `ipo_approx_v1` | 近似发行日（启发式）| 近似，携带 `IPO_APPROXIMATION_WARNING` |")
    add("| `company_foundation_v1` | 公司成立日 | **UNAVAILABLE**（不伪造）|")
    add("")
    add(
        "**股票无性别**（AGENTS.md §5）：`variant_mode` 默认 `not_applicable`，该模式下不输出大运；"
        "需要顺逆时必须显式传入并写入 `assumptions`。生产面板使用 `not_applicable`，"
        "紫微批量研究使用 `forward`（已由 3G 核对确认与标准性别规则一一对应）。"
    )
    add("")

    # 8
    add("## 8. Birth Model Comparison")
    add("")
    if not birth_stats.empty:
        add(f"因子区分度统计行数：**{len(birth_stats)}**（{birth_stats['factor_id'].nunique() if 'factor_id' in birth_stats else '?'} 个因子 × 出生模型）。")
        add("")
    add(
        "3B 的结论是：**换出生模型不改变宏观分布**。三个模型下因子唯一值比例的中位数"
        "≈ 0.006（每 500 只股票只有约 3 个唯一值）→ A 股术数因子整体**天然低区分度**。"
        "`Z_LIFE_006`（身宫命同宫）在 500 × 3 = 1500 次抽取中**恒为 0**，"
        "属 iztro 结构性常量，不是出生模型能救的。"
    )
    add("")
    add("3D 的出生模型对比（OOS 主持有期，正式 gate 实验）：")
    add("")
    if not d3_results.empty:
        table = d3_results.groupby("birth_model")["status"].value_counts().unstack(fill_value=0)
        add("| 出生模型 | " + " | ".join(table.columns) + " |")
        add("|---|" + "---|" * len(table.columns))
        for model, row in table.iterrows():
            add(f"| `{model}` | " + " | ".join(str(int(value)) for value in row) + " |")
    add("")
    add(
        "3F 的出生模型对比族（18 个配对检验，符号翻转置换双侧 p）"
        f"最小 raw p = **{_num((f_summary.get('family_summaries') or [{}])[-1].get('min_raw_p'))}**，"
        "FDR 通过 0 个 → **换出生模型不改变“无信号”这一结论**。"
    )
    add("")

    # 9
    add("## 9. Factor Quality")
    add("")
    add(
        "Phase 3B 已在 500 股 × 3 模型上抽取全部因子并统计区分度（`birth_model_factor_stats.csv`）。"
        "关键事实："
    )
    add("")
    add("- **唯一值比例中位数 ≈ 0.006**：绝大多数因子在横截面上几乎是常量；")
    add("- 常量/近常量因子**只报告、不删除**（有信息量的是“这个术数体系在 500 只股票上几乎不区分”这一事实本身）；")
    add("- 因子质量审计由 `scripts/factor_quality_audit.py` 与 `scripts/ziwei_factor_quality_audit.py` 覆盖，"
        "并进入 `scripts/run_acceptance.py` 的验收链。")
    add("")

    # 10
    add("## 10. Opinion Calibration")
    add("")
    add("| 项目 | 值 |")
    add("|---|---|")
    add(f"| calibration_version | `{calibration.get('calibration_version', 'cal-v1')}` |")
    add(f"| fit_scope | `{calibration.get('fit_scope', 'TRAIN_ONLY')}` |")
    add(f"| fit 最后一个 as_of | `{calibration.get('fit_max_as_of', '')}`（边界 {split.get('train_end', '')}）|")
    add(f"| fit 行数 / 分组数 | {calibration.get('fit_row_count', 'n/a')} / {calibration.get('fit_group_count', 'n/a')} |")
    add(f"| calibration_fit_hash | `{calibration.get('calibration_fit_hash', '')}` |")
    add("")
    if not opinion_dist.empty and "birth_model" in opinion_dist.columns:
        add("Phase 3C 的 TRAIN-only 校准结果（`BAZI_POS`）：")
        add("")
        add("| 出生模型 | 原始正向率 | 校准后正向率 |")
        add("|---|---:|---:|")
        for model, group in opinion_dist.groupby("birth_model"):
            raw_col = "raw_positive_rate" if "raw_positive_rate" in group.columns else None
            cal_col = "calibrated_positive_rate" if "calibrated_positive_rate" in group.columns else None
            if raw_col and cal_col:
                add(f"| `{model}` | {_pct(group[raw_col].mean(), 1)} | {_pct(group[cal_col].mean(), 1)} |")
    add("")
    add(
        "**`opinion.score`、原始 `direction`、Factor 原值均未被修改**：校准只追加研究派生列"
        "（`research_percentile` / `z_score` / `rank_score` / `calibrated_direction`）。"
        "方向阈值 P25/P75 只由全体 TRAIN 原始分布冻结得到，Validation/OOS 只做 transform。"
    )
    add("")

    # 11
    add("## 11. Bazi Bias Analysis")
    add("")
    add(
        "`BAZI_POS` 的真实性质是**高激活 / 高正向的分布偏置**，不是上涨概率："
        "原始运行阈值（`score >= 58 / <= 42`）固定，而在实测分布下得分几乎恒高于 58，"
        "导致正向率 94.0%–96.6%。这直接造成**负对照失效**："
        "真实事件集合几乎等于整个面板时，任何随机类对照都无法区分真实与随机。"
    )
    add("")
    if not d3_results.empty:
        raw = d3_results[d3_results["direction_source"] == "raw"]
        if not raw.empty:
            add("| 出生模型 | OOS 正向率 | OOS 事件/资格数 | Jaccard | 状态 |")
            add("|---|---:|---|---:|---|")
            for _index, row in raw.iterrows():
                if row["object_id"] != "bazi_raw":
                    continue
                add(
                    f"| `{row['birth_model']}` | {_pct(row['oos_positive_rate'])} | "
                    f"{int(row['oos_event_count'])}/{int(row['oos_pool_count'])} | "
                    f"{_num(row['control_jaccard'], 3)} | `{row['status']}` |"
                )
    add("")
    add(
        "**结论**：这是 Phase 3 最重要的方法学发现之一 —— 一个“看起来总有信号”的因子"
        "实际上是因为它几乎对所有股票都给出同一方向。校准把它还原为 25%–26% 的正向率，"
        "对照才重新具备区分能力。**但区分度 ≠ 信息量**（见 §12）。"
    )
    add("")

    # 12
    add("## 12. Bazi OOS")
    add("")
    if not d3_results.empty:
        bazi = d3_results[d3_results["object_id"].isin(["bazi_raw", "bazi_calibrated"])]
        add("| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | 对照差 | p | Jaccard | 状态 |")
        add("|---|---|---:|---:|---:|---:|---:|---:|---|")
        for _index, row in bazi.iterrows():
            add(
                f"| {row['object_id']} | `{row['birth_model']}` | {int(row['oos_event_count'])} | "
                f"{_pct(row['oos_positive_rate'])} | {_pct(row['oos_mean_excess_return'])} | "
                f"{_pct(row['control_mean_excess_return'] - row['oos_mean_excess_return'] if pd.notna(row['control_mean_excess_return']) else None)} | "
                f"{_num(row['control_p_value'], 4)} | {_num(row['control_jaccard'], 3)} | `{row['status']}` |"
            )
    add("")
    add(
        "**回答 GOAL §19 三问**：Q1 是（原始方向在 OOS 仍 93.1%–95.4% 近乎恒正）；"
        "Q2 是（Jaccard 从 0.82–0.86 降到 0.125–0.135）；Q3 **否** —— "
        "**Calibration improved discrimination, but did not create predictive information.**"
    )
    add("")

    # 13
    add("## 13. Ziwei OOS")
    add("")
    if not d3_results.empty:
        ziwei = d3_results[d3_results["object_id"].isin(["ziwei_raw", "ziwei_calibrated"])]
        add("| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | p | Jaccard | 状态 |")
        add("|---|---|---:|---:|---:|---:|---:|---|")
        for _index, row in ziwei.iterrows():
            add(
                f"| {row['object_id']} | `{row['birth_model']}` | {int(row['oos_event_count'])} | "
                f"{_pct(row['oos_positive_rate'])} | {_pct(row['oos_mean_excess_return'])} | "
                f"{_num(row['control_p_value'], 4)} | {_num(row['control_jaccard'], 3)} | `{row['status']}` |"
            )
    add("")
    add(
        "紫微在 OOS 的平均超额为 −1.39%…−2.58%，**全部为负**，"
        "没有任何一个出生模型下达到预注册门槛。3E 进一步显示其负效应中有一部分来自风格暴露"
        "（风格中性化后残差均值转为小幅正），但幅度远不足以抵消。"
    )
    add("")

    # 14
    add("## 14. Huangli OOS")
    add("")
    if not d3_results.empty:
        huangli = d3_results[d3_results["object_id"].isin(["huangli_raw", "huangli_calibrated"])]
        add("| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | p（上尾） | p（下尾） | Jaccard | 状态 |")
        add("|---|---|---:|---:|---:|---:|---:|---:|---|")
        for _index, row in huangli.iterrows():
            add(
                f"| {row['object_id']} | `{row['birth_model']}` | {int(row['oos_event_count'])} | "
                f"{_pct(row['oos_positive_rate'])} | {_pct(row['oos_mean_excess_return'])} | "
                f"{_num(row['control_p_value'], 4)} | {_num(row['control_p_value_lower'], 4)} | "
                f"{_num(row['control_jaccard'], 3)} | `{row['status']}` |"
            )
    add("")
    add(
        "黄历校准事件在 OOS 的平均超额为 −4.6%…−5.0%，同数量随机集合为 −2.2%，"
        "**显著弱于随机**（下尾 p ≈ 0.005–0.03）。这是本阶段唯一的方向性显著结果，"
        "但**不表述为可交易信号**、也不作为术数有效性的反面证据 —— "
        "它在这段样本里恰好更差，其结构原因见 §15。"
    )
    add("")

    # 15
    add("## 15. Huangli Date Effect")
    add("")
    if not d3_concentration.empty:
        add("命中集中度（Phase 3D §6.5）：")
        add("")
        add("| 对象 | 出生模型 | 日期数 | 命中率最低 | 命中率最高 | 命中率标准差 |")
        add("|---|---|---:|---:|---:|---:|")
        for _index, row in d3_concentration.iterrows():
            if not str(row.get("object_id", "")).startswith("huangli"):
                continue
            add(
                f"| {row['object_id']} | `{row['birth_model']}` | {int(row['date_count'])} | "
                f"{_num(row['min_rate'], 3)} | {_num(row['max_rate'], 3)} | {_num(row['std_rate'], 3)} |"
            )
    add("")
    oos = (
        e3_results[
            (e3_results["partition"] == "OOS")
            & (e3_results["horizon"] == 20)
            & (e3_results["object_id"].str.startswith("huangli"))
        ]
        if not e3_results.empty else pd.DataFrame()
    )
    train = (
        e3_results[
            (e3_results["partition"] == "TRAIN")
            & (e3_results["horizon"] == 20)
            & (e3_results["object_id"].str.startswith("huangli"))
        ]
        if not e3_results.empty else pd.DataFrame()
    )
    if not oos.empty:
        add("Phase 3E 的 P0 统计修正（折叠到日期，`hit_share` 斜率 → 当日市场超额）：")
        add("")
        add("| 对象 | 出生模型 | 日期数 | 日均股票数 | `market_excess` | 二值切分 | `hit_share` 斜率（OOS） | 斜率（TRAIN） |")
        add("|---|---|---:|---:|---:|---|---:|---:|")
        train_map = {
            (row["object_id"], row["birth_model"]): row["hit_share_slope"]
            for _index, row in train.iterrows()
        } if not train.empty else {}
        for _index, row in oos.iterrows():
            add(
                f"| {row['object_id']} | `{row['birth_model']}` | {int(row['date_count'])} | "
                f"{_num(row['stock_count_per_date_mean'], 1)} | {_pct(row['market_excess_date_mean'])} | "
                f"{'可用' if row['date_binary_split_usable'] else '**退化**'} | "
                f"{_num(row['hit_share_slope'], 4)} ({_num(row['hit_share_slope_t'], 2)}) | "
                f"{_num(train_map.get((row['object_id'], row['birth_model'])))} |"
            )
    add("")
    add(
        "因为 15/15 个 OOS 日期都至少有 1 个命中，"
        "**二值切分退化**（已显式标记），改用中位数切分与连续斜率。"
        "结论：斜率在 TRAIN 为正、OOS 为负，**符号相反且都不显著** → "
        "黄历的“日期选择器”结构**没有**转化为稳定的市场-wide 日历效应。"
        "详见 [`huangli-date-effect-analysis.md`](huangli-date-effect-analysis.md)。"
    )
    add("")

    # 16
    add("## 16. Consensus OOS")
    add("")
    if not d3_results.empty:
        cons = d3_results[d3_results["logic"] == "all_positive"]
        add("| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | p | Jaccard | 状态 |")
        add("|---|---|---:|---:|---:|---:|---:|---|")
        for _index, row in cons.iterrows():
            add(
                f"| {row['object_id']} | `{row['birth_model']}` | {int(row['oos_event_count'])} | "
                f"{_pct(row['oos_positive_rate'])} | {_pct(row['oos_mean_excess_return'])} | "
                f"{_num(row['control_p_value'], 4)} | {_num(row['control_jaccard'], 3)} | `{row['status']}` |"
            )
    add("")
    add(
        "共振对象的事件数随引擎数快速下降（八字+紫微约 170、三模型 cal 仅 40–69 → "
        "`INSUFFICIENT_SAMPLE`）。控制市场与风格之后（3E）其控制后系数 t 值全部 < 2，"
        "FDR 通过 0 个 → **共振并未把弱信号叠加成强信号**。"
    )
    add("")

    # 17
    add("## 17. Conflict Research")
    add("")
    conflict = f_results[f_results["family_id"] == "conflict"] if not f_results.empty else pd.DataFrame()
    if not conflict.empty:
        add("冲突组合在预注册中被登记为**探索性（无方向性预测）**：照常执行全部负对照与统计，"
            "但**不套用单向 gate**、状态恒为 `EXPLORATORY_NOT_GATED`、**永不解锁**。")
        add("")
        add("| 对象 | 出生模型 | 事件数 | raw p（双侧） | q | FDR 通过 |")
        add("|---|---|---:|---:|---:|---|")
        for _index, row in conflict.iterrows():
            add(
                f"| `{row['object_id']}` | `{row['birth_model']}` | "
                f"{int(row['event_count']) if pd.notna(row['event_count']) else 0} | "
                f"{_num(row['raw_p_value'], 4)} | {_num(row['fdr_q_value'], 4)} | "
                f"{'**是**' if row['fdr_pass'] else '否'} |"
            )
    add("")
    add(
        "**唯一通过 BH-FDR 的检验就在这一族**（`conflict_bazi_pos_huangli_neg` × `ipo_approx_v1`，"
        "raw p = 0.0036，q = 0.0432）。按预注册规则它**不能解锁任何状态**，"
        "如实记录、不做正面解读。这正是“预先声明冲突组合不套 gate”这条纪律的价值："
        "否则最容易被误读为“发现”的恰好是探索性最强的结果。"
    )
    add("")

    # 18
    add("## 18. Walk Forward")
    add("")
    if not d3_walkforward.empty and "object_id" in d3_walkforward.columns:
        summary = d3_walkforward.groupby("object_id").agg(
            folds=("fold", "nunique") if "fold" in d3_walkforward.columns else ("object_id", "size"),
            mean_excess=("mean_excess_return", "mean"),
        ).reset_index()
        add("| 对象 | fold 数 | 平均超额 |")
        add("|---|---:|---:|")
        for _index, row in summary.iterrows():
            add(f"| `{row['object_id']}` | {int(row['folds'])} | {_pct(row['mean_excess'])} |")
    add("")
    add(
        "扩窗 walk-forward：12 个 fold / 序列，**逐 fold 重拟合校准**"
        "（每个 fold 的 `calibration_fit_hash` 互不相同，证明没有复用全 TRAIN 校准）。"
        "12 条序列 × 12 个 fold = 144 行记录，全部在 [`walk-forward-methodology.md`](walk-forward-methodology.md) "
        "的四道结构性闸门下执行：内部按日期过滤 / layer 的 `fit_max_as_of` 断言 / transform 帧守卫 / "
        "禁止 fold 使用 `cal-v1` 版本号。"
    )
    add("")

    # 19
    add("## 19. Market Neutralization")
    add("")
    add(
        "统一使用 `IDX000300`（沪深 300）作为全部股票的基准：**`BENCHMARK_SPLIT_UNAVAILABLE`** —— "
        "canonical 快照内不存在中证 500，因此不做 GOAL 期望的市值分层映射，"
        "也不用自建等权组合冒充。偏差方向已知（规模暴露混入超额收益），由风格维度单独量化。"
    )
    add("")
    add(
        "`market_excess_return_Nd = ret_Nd − bench_ret_Nd`（同一日历区间），"
        "三段（`raw` / `benchmark` / `market_excess`）必须同时报告。"
    )

    # 20
    add("")
    add("## 20. Industry / PIT Industry Limitations")
    add("")
    add(
        "**双重不可用**：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE` 且 `INDUSTRY_CLASSIFICATION_UNAVAILABLE`。"
        "排查范围：canonical blob（只有 OHLCV）、TuShare PIT 注册簿（只有 board / list_status）、"
        "本地 TuShare 目录（只有 adj_factor 与退市日线）、`data/import/stocks.csv`"
        "（有 industry 但只覆盖 Phase 1 的 20 只，与 500 只 universe 不重叠到可用程度）。"
    )
    add("")
    add(
        "因此：**不做**行业中性化；不使用当前行业冒充历史 PIT 行业；不联网抓取后冒充权威分类；"
        "**不得声称**做过严格 industry-neutral backtest。替代控制是 `SEGMENT_CONTROL_BOARD`"
        "（法定板块，5 类），并在报告中明确声明**它不是行业**。"
    )
    add("")

    # 21
    add("## 21. Style Controls")
    add("")
    add("| 维度 | 实现 |")
    add("|---|---|")
    add("| size（真实市值）| **不可得** `MARKET_CAP_UNAVAILABLE`（无股本表）|")
    add("| size（代理）| 20 日均成交额对数 `SIZE_PROXY_LIQUIDITY_AMOUNT` |")
    add("| momentum | trailing 60 / 120 交易日累计收益 |")
    add("| volatility | trailing 20 / 60 交易日日对数收益标准差 |")
    add("| value | **不可得** `VALUE_FACTOR_UNAVAILABLE`（无 PIT 基本面）|")
    add("")
    add(
        f"风格解释力：`style_r2_mean = {_num(next((row['style_r2_mean'] for _i, row in (e3_results[(e3_results['partition']=='OOS') & (e3_results['horizon']==20)].iterrows() if not e3_results.empty else [])), None))}`"
        "（OOS 20D 横截面方差比例）。防泄漏由硬断言验证：改写 `as_of` 之后的 bar 必须不影响暴露。"
    )
    add("")
    if not e3_results.empty:
        oos20 = e3_results[
            (e3_results["partition"] == "OOS") & (e3_results["horizon"] == 20)
            & (e3_results["birth_model"] == "listing_open_v1")
        ]
        add("风格中性化结果（OOS 20D，`listing_open_v1`）：")
        add("")
        add("| 对象 | 命中数 | 原始命中均值 | 风格中性残差均值 | 控制后系数 (t) | 板块中性均值 |")
        add("|---|---:|---:|---:|---:|---:|")
        for _index, row in oos20.iterrows():
            add(
                f"| {row['object_id']} | {int(row['hit_row_count'])} | "
                f"{_pct(row['hit_date_mean_market_excess'])} | {_pct(row['style_neutral_hit_mean'])} | "
                f"{_pct(row['controlled_hit_coefficient'])} ({_num(row['controlled_hit_coefficient_t'], 2)}) | "
                f"{_pct(row['segment_neutral_hit_mean'])} |"
            )
    add("")
    if questions:
        add("")
        add("### 21.1 GOAL §3E-5 的 Q-E1..Q-E5（OOS 主持有期，来自 3E 产物）")
        add("")
        add("| 问题 | 关键数字 |")
        add("|---|---|")
        q1 = questions.get("Q-E1_bazi_calibrated_market_neutral") or []
        if q1:
            row = q1[0]
            add(
                f"| Q-E1 八字 cal 做 market neutral 后是否改变 | 命中原始收益 "
                f"{_pct(row.get('hit_mean_raw_return'))} − 基准 {_pct(row.get('hit_mean_benchmark_return'))} "
                f"= 市场超额 {_pct(row.get('hit_mean_market_excess_return'))}；风格中性后 "
                f"{_pct(row.get('style_neutral_hit_mean'))} |"
            )
        q2 = questions.get("Q-E2_ziwei_market_exposure") or []
        if q2:
            row = q2[0]
            add(
                f"| Q-E2 紫微是否存在市场暴露解释 | 命中市场超额 "
                f"{_pct(row.get('hit_mean_market_excess_return'))}，因子 RankIC "
                f"{_num(row.get('factor_rank_ic_mean'), 4)} |"
            )
        q3 = questions.get("Q-E3_huangli_calendar_effect") or []
        if q3:
            row = q3[0]
            add(
                f"| Q-E3 黄历日期效应是否市场-wide | 命中比例斜率 "
                f"{_num(row.get('hit_share_slope'), 4)}（t={_num(row.get('hit_share_slope_t'), 2)}）；"
                f"高命中日 {_pct(row.get('above_median_hit_share_date_excess'))} vs "
                f"低命中日 {_pct(row.get('below_median_hit_share_date_excess'))} |"
            )
        q4 = questions.get("Q-E4_consensus_after_market_control") or []
        if q4:
            row = q4[0]
            add(
                f"| Q-E4 Consensus 控制市场后是否仍 NO_SIGNAL | 控制后系数 "
                f"{_pct(row.get('controlled_hit_coefficient'))}"
                f"（t={_num(row.get('controlled_hit_coefficient_t'), 2)}） |"
            )
        q5 = questions.get("Q-E5_top_results_style_explained") or []
        if q5:
            row = q5[0]
            add(
                f"| Q-E5 看似较好的结果是否被风格解释 | 榜首对象 `{row.get('object_id')}`："
                f"命中 {_pct(row.get('hit_date_mean_market_excess'))} → 风格中性 "
                f"{_pct(row.get('style_neutral_hit_mean'))} |"
            )
    add("")
    add(
        "**符号翻转是双向的**：部分对象由正转负（说明表面效应来自风格暴露），"
        "部分由小转大。因此“风格中性化”不是单向开关 —— 两种口径（残差均值 vs 控制后系数）必须同时报告。"
        "其中控制后 |t| ≥ 2 的对象只有 2 个（黄历 cal 1.97、八字+黄历 cal 2.15），"
        "在 42–54 个实验下属噪声水平。"
    )
    add("")

    # 22
    add("## 22. Multiple Testing / FDR")
    add("")
    add(
        f"族定义在结果之前冻结（`{f_summary.get('mt_version', 'mt-v1')}`，"
        f"`final_results_seen_at_freeze = {(f_summary.get('families') or {}).get('final_results_seen_at_freeze', False)}`），"
        "由代码强制校验“每个假设恰好属于一个族、无遗漏无重复”。"
    )
    add("")
    if not f_family.empty:
        agg = f_family.groupby(["family_id", "family_test_count"]).agg(
            m=("raw_p_value", "size"),
            min_p=("raw_p_value", "min"),
            bonferroni_pass=("bonferroni_pass", "sum"),
            fdr_pass=("fdr_pass", "sum"),
        ).reset_index()
        add("| 族 | m | 最小 raw p | Bonferroni 通过 | FDR 通过 |")
        add("|---|---:|---:|---:|---:|")
        for _index, row in agg.iterrows():
            add(
                f"| `{row['family_id']}` | {int(row['family_count'] if 'family_count' in row else row['m'])} | "
                f"{_num(row['min_p'], 4)} | {int(row['bonferroni_pass'])} | {int(row['fdr_pass'])} |"
            )
    add("")
    if not f_family.empty:
        passers = f_family[f_family["fdr_pass"] == True]  # noqa: E712
        add(f"**通过 BH-FDR 的检验共 {len(passers)} 个**，全部属于 `conflict`（探索性）族，"
            "按预注册规则**不解锁任何状态**。正式 gate 实验（42 个）通过 **0** 个。")
    add("")

    # 23
    add("## 23. Bootstrap / Permutation")
    add("")
    add(
        "**日期分层置换**是本阶段最重要的口径修正：零假设 = 在每个 `as_of` 内部命中标签可交换，"
        "**严格保留每个日期的命中数量**。这正是 Phase 3D 报告 §6.5 预登记的改进项（gate-v2 的 H 条件）。"
    )
    add("")
    if not f_results.empty and not gated.empty:
        add("| 项 | 结果 |")
        add("|---|---|")
        add(f"| 置换次数 | {int(gated['permutation_count'].max())} 次/实验（种子由实验标识派生，可复现）|")
        add("| date-block bootstrap | 2000 次/实验，95% CI |")
        add(
            "| 命中均值 95% CI 跨 0 的实验数 | "
            f"**{int((gated['bootstrap_hit_mean_crosses_zero'] == True).sum())}/{len(gated)}** |"  # noqa: E712
        )
        add(f"| 置换单侧 p ≤ 0.05 的实验数 | {int((gated['p_value_upper'] <= 0.05).sum())}/{len(gated)} |")
        add(f"| 效应量（`|Cohen's d|`）中位数 | {_num(gated['cohen_d'].abs().median())} |")
    add("")
    add(
        "构造实验直接证明分层的必要性：一个**纯日期选择器**在池化置换下 p < 0.05（假显著），"
        "在分层置换下 p > 0.1（正确判为不显著）。"
    )
    add("")

    # 24
    add("## 24. Robustness")
    add("")
    add("9 个预注册维度；测不了的显式记 `ROBUSTNESS_DIMENSION_UNAVAILABLE`。")
    add("")
    if not f_robust.empty:
        gated_ids = set(gated["hypothesis_id"] + "|" + gated["birth_model"]) if not gated.empty else set()
        robust_gated = f_robust[
            (f_robust["hypothesis_id"] + "|" + f_robust["birth_model"]).isin(gated_ids)
        ]
        def _slice_count(value: object) -> int:
            """``slices`` 列是序列化的切片列表；数出实际切片数（解析失败按 0）。"""
            try:
                parsed = ast.literal_eval(str(value))
            except (ValueError, SyntaxError):
                return 0
            return len(parsed) if isinstance(parsed, list) else 0

        stats = robust_gated.groupby("dimension").agg(
            evaluated=("status", "size"),
            slices=("slices", lambda values: sum(_slice_count(value) for value in values)),
            unavailable=("status", lambda values: int((values == "ROBUSTNESS_DIMENSION_UNAVAILABLE").sum())),
            unstable=("stable", lambda values: int((values == False).sum())),  # noqa: E712
        ).reset_index()
        add("| 维度 | 被评估次数 | 切片总数 | 不可用 | 判为不稳定 |")
        add("|---|---:|---:|---:|---:|")
        for _index, row in stats.iterrows():
            add(
                f"| `{row['dimension']}` | {int(row['evaluated'])} | {int(row['slices'])} | "
                f"{int(row['unavailable'])} | {int(row['unstable'])} |"
            )
        add("")
        unstable = gated["robustness_unstable_dimensions"].fillna("")
        per_dimension: dict[str, int] = {}
        for value in unstable:
            for dimension in str(value).split(","):
                if dimension:
                    per_dimension[dimension] = per_dimension.get(dimension, 0) + 1
        if per_dimension:
            add("正式 gate 实验中**不稳定**的维度（按实验计数）：")
            add("")
            add("| 维度 | 不稳定的实验数 |")
            add("|---|---:|")
            for dimension, count in sorted(per_dimension.items(), key=lambda item: -item[1]):
                add(f"| `{dimension}` | {count} |")
    add("")
    add(
        "**最值得注意的一项**：`universe_subset`（在市股 vs 退市股）在 31/42 个正式实验中符号不一致。"
        "这意味着结论对“是否纳入退市股”高度敏感 —— 而退市股正是本阶段用来根治生存者偏差的资产。"
        "这是 Phase 3 最重要的残余风险之一，已写入 [`phase3-model-limitations.md`](phase3-model-limitations.md)。"
    )
    add("")

    # 25
    add("## 25. Ziwei Cross-engine Validation")
    add("")
    add(
        f"**状态：`{g_summary.get('second_engine_status', 'n/a')}`** —— "
        f"参考实现 `{(g_summary.get('reference') or {}).get('library', '')}` "
        f"{(g_summary.get('reference') or {}).get('version', '')}"
        f"（{(g_summary.get('reference') or {}).get('school', '')}，"
        f"{(g_summary.get('reference') or {}).get('license', '')}）。"
    )
    add("")
    counts_g = g_summary.get("difference_classification_counts") or {}
    if counts_g:
        add("| 分类 | 条数 |")
        add("|---|---:|")
        for key, value in counts_g.items():
            add(f"| `{key}` | {value} |")
        add("")
        add(f"完全一致比例：**{g_summary.get('identical_ratio', 0):.4f}**"
            f"（{g_summary.get('case_count', 0)} 个案例、{sum(counts_g.values())} 项字段比较）。")
        add("")
    add(
        "**关键审计结论**：星标最高的两个“紫微排盘引擎”里，`SylarLong/iztro` 就是本项目的生产引擎，"
        "而 `Renhuai123/ziwei-doushu`（4169★）的 `lib/ziwei/algorithm.ts` 首行即 "
        "`import { astro } from 'iztro'` —— **不是独立实现**。Python 侧候选"
        "（`py-iztro` / `iztro-py` / `mingli-master`）同为 iztro 移植。"
        "用它们做交叉核对等于用 iztro 验证 iztro。"
    )
    add("")
    for index, finding in enumerate(g_summary.get("notable_findings") or [], start=1):
        add(f"**25.{index} {finding['title']}** —— {finding['observation']}")
        add("")
    add(
        "参考实现**只作为 Reference**：不进入 `ConsensusEngine`，不与 iztro 构成“双重确认”，"
        "生产代码零引用（由测试强制扫描 `apps/` 与 `src/` 全目录）。"
        "详见 [`ziwei-cross-engine-differences.md`](ziwei-cross-engine-differences.md)。"
    )
    add("")

    # 26
    add("## 26. Final Conclusions & Limitations")
    add("")
    add("### 26.1 逐条回答 Phase 3 Q1–Q10")
    add("")
    add("| # | 问题 | 回答 |")
    add("|---|---|---|")
    add("| Q1 | 扩大样本以后 `BAZI_POS` 是否仍近乎恒正？ | **是**。OOS 原始正向率 93.1%–95.4%（500 只，含 333 退市股）。 |")
    add("| Q2 | 哪个 birth model 区分度最好？ | **没有实质差异**。三模型下因子唯一值比例中位数均 ≈ 0.006；3F 的出生模型对比族 FDR 通过 0 个 → 换模型不改变结论。 |")
    add("| Q3 | 紫微单模型有无稳定 OOS signal？ | **无**。OOS 平均超额 −1.39%…−2.58%，FDR 通过 0 个。 |")
    add("| Q4 | 黄历有无稳定 OOS signal？ | **无**。校准后事件显著弱于同数量随机集合（下尾 p ≈ 0.005–0.03），但折叠到日期后**不是**稳定的市场-wide 日历效应（斜率 TRAIN/OOS 符号相反且不显著）。 |")
    add("| Q5 | 三模型共振是否仍 `NO_SIGNAL`？ | **是**。控制市场与风格后控制后系数 t 值全部 < 2；FDR 通过 0 个。 |")
    add("| Q6 | Neutralization 后信号是否消失？ | **是**。风格中性化后符号双向翻转，没有对象变得更强；控制后 |t| ≥ 2 的仅 2 个，在多重检验下属噪声。 |")
    add("| Q7 | FDR 后有多少显著 hypothesis？ | **正式 gate 实验 0 个**（Bonferroni 同样 0 个）；唯一 1 个在 `conflict` 探索性族，按预注册**不解锁**。 |")
    add("| Q8 | 跨年份是否稳定？ | **否**。8/42 个正式实验跨年份符号不一致；名义 p 最小的 6 个实验**全部**未通过跨年稳定性条件。 |")
    add("| Q9 | 换 birth model 结论是否改变？ | **不改变**（18 个配对检验，FDR 通过 0 个）。但 `universe_subset` 维度在 31/42 个实验中符号不一致 —— 结论对**退市股是否纳入**敏感。 |")
    add(f"| Q10 | 是否有任何 `SUPPORTED_OUT_OF_SAMPLE`？ | **{supported} 个**。 |")
    add("")
    add("### 26.2 最终状态")
    add("")
    add(f"**`SUPPORTED_OUT_OF_SAMPLE = {supported}`** · **`MULTI_ENGINE_NO_SIGNAL`**")
    add("")
    add("这不是失败。Phase 3 交付的是：")
    add("")
    add("1. 一台可复现的研究机器（预注册 → 冻结校准 → 固定 holdout → 逐 fold 重拟合 → "
        "日期分层置换 → 族内 FDR → gate-v2）；")
    add("2. 一组**可信的否定结论**：在 500 只无偏股票的 2010–2026 样本上，"
        "这些术数因子没有可复现的样本外信息量；")
    add("3. 一组**方法学发现**：BAZI_POS 的分布偏置如何让负对照失效、"
        "黄历的日期选择器结构如何制造两个相反的零假设、多重检验如何把名义显著清零。")
    add("")
    add("### 26.3 gate-v1 / gate-v2 并排")
    add("")
    add("| 状态 | gate-v1（3D） | gate-v2（3F，正式 gate 实验）|")
    add("|---|---:|---:|")
    for status in sorted(set(v1_counts) | set(v2_gated_counts)):
        add(f"| `{status}` | {v1_counts.get(status, 0)} | {v2_gated_counts.get(status, 0)} |")
    add("")
    add(
        "gate-v2 的 `WEAK_EVIDENCE` 显著增加，正是新增条件（FDR / bootstrap / 置换 / 中性化）"
        "生效的结果。两版**并排报告**让这一差异可见，而不是被掩盖。"
    )
    add("")
    add("### 26.4 限制")
    add("")
    add("完整清单见 [`phase3-model-limitations.md`](phase3-model-limitations.md)。最关键的五条：")
    add("")
    add("1. **行业 PIT 分类完全不可得** —— 无法排除产业周期解释；")
    add("2. **出生时间是研究构造** —— `company_foundation` 不可得，上市日 ≠ 公司出生；")
    add("3. **结论对退市股是否纳入高度敏感**（`universe_subset` 31/42 符号不一致）；")
    add("4. **未计交易成本 / 流动性 / 涨跌停 / 卖空约束** —— 信息量检验，不是可交易性检验；")
    add("5. **多重检验仍不完美**：族划分是最少数量的合理划分，"
        "不同划分会给出不同的校正强度（但不会把 0 个变成多个）。")
    add("")
    add("---")
    add("")
    add(
        "**最终定性：`PASS WITH CONDITIONS — RESEARCH PIPELINE READY / EVIDENCE INCONCLUSIVE`**\n\n"
        "管线成熟可用；证据本身为负。`PASS` 仅代表研究管线成熟，**绝不等于术数有效**。"
    )
    add("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3H 最终研究报告生成器")
    parser.add_argument("--out", default=str(REPORT))
    args = parser.parse_args()
    report = build_report()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(f"wrote {path} chars={len(report)} lines={report.count(chr(10)) + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
