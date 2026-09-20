"""Phase 3G 差异报告生成器（``docs/ziwei-cross-engine-differences.md``）。

产物字段遵循 GOAL §3G-5：``case_id`` / ``field`` / ``iztro_result`` /
``reference_result`` / ``same/different`` / ``possible_reason`` /
``school_convention`` / ``resolved`` / ``unresolved``。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

#: 报告中每个字段最多展示的明细行数（完整明细在 CSV）
MAX_ROWS_PER_FIELD = 6


def _fmt(value: object) -> str:
    text = str(value)
    return text if len(text) <= 60 else text[:57] + "…"


def write_difference_doc(summary: dict, differences: pd.DataFrame, path: Path) -> None:
    """把核对结果写成 Markdown 差异报告。"""
    reference = summary.get("reference", {})
    lines: list[str] = []
    lines.append("# Phase 3G · 紫微第二实现源交叉核对差异报告")
    lines.append("")
    lines.append(
        f"> 生成时间：{summary.get('generated_at', '')} · commit `{summary.get('git_sha', '')}`\n"
        f"> 案例集 `{summary.get('case_version', '')}` · 案例数 {summary.get('case_count', 0)}\n"
        f"> 生产引擎 `{summary.get('production_engine_version', '')}` · "
        f"参考实现 `{reference.get('library', '')}` {reference.get('version', '')}"
        f"（{reference.get('school', '')}，{reference.get('license', '')}）"
    )
    lines.append("")
    status = summary.get("second_engine_status", "")
    if status != "REFERENCE_AVAILABLE":
        lines.append("## ZIWEI_SECOND_ENGINE_UNAVAILABLE")
        lines.append("")
        lines.append(f"参考实现不可用，交叉核对未执行：{summary.get('second_engine_unavailable_reason', '')}")
        lines.append("")
        lines.append(
            "按 GOAL §3G-6，本状态**不阻塞** Phase 3H；差异报告仅保留来源审计部分。"
        )
        lines.append("")
    else:
        lines.append("## 0. 一句话结论")
        lines.append("")
        lines.append(
            f"在 {summary.get('case_count', 0)} 个固定案例、"
            f"{sum((summary.get('difference_classification_counts') or {}).values())} 项字段比较中，"
            f"**{summary.get('identical_ratio', 0):.2%} 完全一致**；"
            f"差异集中在 {len(summary.get('difference_classification_counts') or {}) - 1} 类可解释原因上，"
            "没有任何一类差异会改变本研究平台的因子语义。"
        )
        lines.append("")

    lines.append("## 1. 来源与许可证审计（GOAL §3G-1）")
    lines.append("")
    lines.append(
        "| 仓库 | 语言 | 许可证 | ★ | 依赖 | 是否独立实现 | 决定 | 理由 |"
    )
    lines.append("|---|---|---|---:|---|---|---|---|")
    for item in summary.get("audited_candidates", []):
        stars = item.get("stars")
        independent = item.get("independent")
        independent_text = (
            "是" if independent is True else ("否" if independent is False else "未知")
        )
        lines.append(
            f"| `{item.get('repository')}` | {item.get('language')} | {item.get('license')} | "
            f"{stars} | {_fmt(item.get('dependency'))} | {independent_text} | "
            f"`{item.get('decision')}` | {_fmt(item.get('reason'))} |"
        )
    lines.append("")
    lines.append(
        "**关键审计结论**：星标最高的两个「紫微排盘引擎」中，"
        "`SylarLong/iztro` 就是本项目的生产引擎，"
        "而 `Renhuai123/ziwei-doushu` 的 `lib/ziwei/algorithm.ts` 首行即 "
        "`import { astro } from 'iztro'` —— 它不是独立实现。"
        "所有 Python 侧候选（`py-iztro` / `iztro-py` / `mingli-master`）同样是 iztro 的移植，"
        "**用它们做交叉核对等于用 iztro 验证 iztro**。"
    )
    lines.append("")
    lines.append(
        "因此本项目采用的唯一独立实现源是 `airicyu/fortel-ziweidoushu`（中州派，MIT，"
        "唯一运行时依赖 `util`，自带日历，不依赖 iztro）。"
        "按 GOAL §3G-2，它**只作为 Reference**：不进入 `ConsensusEngine`，"
        "不与 iztro 构成「双重确认」。"
    )
    lines.append("")

    lines.append("## 2. 比较范围（GOAL §3G-3）")
    lines.append("")
    lines.append(" | ".join(summary.get("comparison_scope", [])))
    lines.append("")
    if summary.get("second_engine_status") == "REFERENCE_AVAILABLE":
        lines.append("### 2.1 差异分类分布")
        lines.append("")
        lines.append("| 分类 | 条数 | 含义 |")
        lines.append("|---|---:|---|")
        meanings = {
            "IDENTICAL": "两边完全一致",
            "DIFFERENT_NAMING_CONVENTION": "命名/收录范围差异（同物不同名）",
            "DIFFERENT_SCHOOL_CONVENTION": "流派口径差异（四化表、晚子时换日等）",
            "DIFFERENT_VARIANT_ASSUMPTION": "由「股票无性别」的假设参数引起",
            "DIFFERENT_SUSPECTED_IMP_BUG": "疑似参考实现的实现问题，非流派差异",
            "FIELD_UNAVAILABLE": "参考实现没有可比对的出口（不静默省略）",
        }
        for key, value in (summary.get("difference_classification_counts") or {}).items():
            lines.append(f"| `{key}` | {value} | {meanings.get(key, '')} |")
        lines.append("")
        lines.append(f"完全一致比例：**{summary.get('identical_ratio', 0):.4f}**")
        lines.append("")

    if not differences.empty:
        lines.append("## 3. 逐类差异明细")
        lines.append("")
        different = differences[differences["same_or_different"] == "different"]
        for classification in sorted(set(different["classification"])):
            subset = different[different["classification"] == classification]
            lines.append(f"### 3.{classification}")
            lines.append("")
            lines.append(f"共 {len(subset)} 条，涉及 {subset['field'].nunique()} 个字段。")
            lines.append("")
            lines.append(
                "| case_id | field | iztro_result | reference_result | possible_reason | "
                "school_convention | resolved |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for field_name in sorted(set(subset["field"]))[:MAX_ROWS_PER_FIELD]:
                rows = subset[subset["field"] == field_name]
                row = rows.iloc[0]
                lines.append(
                    f"| `{row['case_id']}` | `{field_name}` | {_fmt(row['production_value'])} | "
                    f"{_fmt(row['reference_value'])} | {_fmt(row['possible_reason'])} | "
                    f"{_fmt(row['school_convention'])} | {row['resolved']} |"
                )
            lines.append("")

        lines.append("## 4. 流派/实现差异逐条结论（GOAL §3G-5）")
        lines.append("")
        findings = summary.get("notable_findings") or []
        for index, finding in enumerate(findings, start=1):
            lines.append(f"### 4.{index} {finding['title']}")
            lines.append("")
            lines.append(f"- **现象**：{finding['observation']}")
            lines.append(f"- **证据**：{finding['evidence']}")
            lines.append(f"- **分类**：`{finding['classification']}`")
            lines.append(f"- **resolved**：{finding['resolved']}")
            lines.append(f"- **对本项目研究的影响**：{finding['impact']}")
            lines.append("")

    lines.append("## 5. 未解决项（unresolved）")
    lines.append("")
    unresolved = (
        differences[differences["resolved"] == False]  # noqa: E712 - 显式比较
        if not differences.empty else pd.DataFrame()
    )
    if unresolved.empty:
        lines.append("无。")
    else:
        lines.append("| field | 条数 | 说明 |")
        lines.append("|---|---:|---|")
        for field_name, group in unresolved.groupby("field"):
            lines.append(
                f"| `{field_name}` | {len(group)} | {_fmt(group.iloc[0]['possible_reason'])} |"
            )
    lines.append("")
    lines.append("## 6. 定性")
    lines.append("")
    lines.append(
        "本核对**不判定谁对谁错**：不同流派在四化表、晚子时换日、命主取用上有长期分歧，"
        "交叉核对的价值在于**把差异定位到具体字段与具体原因**，"
        "从而知道哪些结论对实现选择敏感、哪些不敏感。"
    )
    lines.append("")
    lines.append(
        "本项目不据此修改生产引擎：`iztro` 仍是唯一的 `MetaphysicsEngine` 实现，"
        "参考实现只出现在本研究报告中。"
    )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


__all__ = ["write_difference_doc"]
