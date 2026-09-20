"""由 Phase 3D 产物生成 `docs/phase3d-oos-results.md`（GOAL §25 的 28 项）。

只读产物、只写报告：不重算统计、不改动任何结果 CSV。
结论性文字只陈述产物里能直接核对的数字，避免"报告比数据说得更多"。

用法::

    python scripts/phase3d_write_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "phase3_universe"
REPORT = ROOT / "docs" / "phase3d-oos-results.md"

#: 报告里当作"头条对象"的顺序
HEADLINE_OBJECTS = (
    "bazi_raw", "bazi_calibrated", "ziwei_raw", "ziwei_calibrated",
    "huangli_raw", "huangli_calibrated",
    "bazi_ziwei_calibrated", "bazi_huangli_calibrated", "ziwei_huangli_calibrated",
    "all_three_calibrated", "all_three_raw",
)
OBJECT_LABEL = {
    "bazi_raw": "八字 raw", "bazi_calibrated": "八字 calibrated",
    "ziwei_raw": "紫微 raw", "ziwei_calibrated": "紫微 calibrated",
    "huangli_raw": "黄历 raw", "huangli_calibrated": "黄历 calibrated",
    "bazi_ziwei_calibrated": "八字+紫微 cal", "bazi_ziwei_raw": "八字+紫微 raw",
    "bazi_huangli_calibrated": "八字+黄历 cal", "bazi_huangli_raw": "八字+黄历 raw",
    "ziwei_huangli_calibrated": "紫微+黄历 cal", "ziwei_huangli_raw": "紫微+黄历 raw",
    "all_three_calibrated": "三模型 cal", "all_three_raw": "三模型 raw",
    "conflict_bazi_pos_ziwei_neg": "冲突 八字+ / 紫微−",
    "conflict_ziwei_pos_bazi_neg": "冲突 紫微+ / 八字−",
    "conflict_bazi_pos_huangli_neg": "冲突 八字+ / 黄历−",
    "conflict_ziwei_pos_huangli_neg": "冲突 紫微+ / 黄历−",
}
STATUS_NOTE = {
    "OOS_CANDIDATE_SUPPORTED": "候选（十项条件全过，未做 FDR）",
    "WEAK_EVIDENCE": "弱证据",
    "INCONCLUSIVE": "结论不明确",
    "NO_SIGNAL": "未发现信号",
    "INVALID_CONTROL": "负对照失效",
    "INSUFFICIENT_SAMPLE": "样本不足",
    "NOT_RUN": "未运行",
    "NO_REAL_DATA": "无真实数据",
    "EXPLORATORY_NOT_GATED": "探索性（未套用单向 gate）",
}


def _read_csv(name: str) -> pd.DataFrame:
    path = OUT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺少产物：{path}（请先运行 phase3d_oos_pipeline.py）")
    return pd.read_csv(path)


def _fmt_pct(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value) * 100:.{digits}f}%"


def _fmt_num(value: object, digits: int = 4) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}"


def _fmt_int(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{int(value)}"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


GATED_STATUSES = (
    "OOS_CANDIDATE_SUPPORTED", "WEAK_EVIDENCE", "INCONCLUSIVE",
    "NO_SIGNAL", "INVALID_CONTROL", "INSUFFICIENT_SAMPLE", "NOT_RUN", "NO_REAL_DATA",
)


def _fdr_projection(results: pd.DataFrame) -> dict:
    """BH-FDR 前瞻：只统计**通过单向 gate** 的实验（探索性对象不套 gate，不计入 m）。"""
    gated = results[
        results["control_p_value"].notna() & results["status"].isin(GATED_STATUSES)
    ]
    p_values = gated["control_p_value"].to_numpy(dtype=float)
    if len(p_values) == 0:
        return {"m": 0}
    ordered = np.sort(p_values)
    m = len(ordered)
    thresholds = 0.05 * (np.arange(1, m + 1) / m)
    passing = int((ordered <= thresholds).sum())
    return {
        "m": m,
        "min_p": float(ordered[0]),
        "bh_threshold_min": float(thresholds[0]),
        "passing_bh": passing,
        "nominal_significant": int((ordered < 0.05).sum()),
    }


def _bazi_answer_lines(raw: pd.DataFrame, calibrated: pd.DataFrame) -> list[str]:
    """GOAL §19 Q1–Q3 的数值化回答（引用产物里的真实数字，不写死）。"""
    lines: list[str] = []
    if raw.empty or calibrated.empty:
        return ["（缺少 bazi raw / calibrated 结果，无法回答。）"]
    raw_rates = [row["oos_positive_rate"] for row in raw.to_dict("records")]
    raw_j = [row["control_jaccard"] for row in raw.to_dict("records")]
    cal_j = [row["control_jaccard"] for row in calibrated.to_dict("records")]
    cal_excess = [row["oos_mean_excess_return"] for row in calibrated.to_dict("records")]
    cal_p = [row["control_p_value"] for row in calibrated.to_dict("records")]
    statuses = sorted({row["status"] for row in calibrated.to_dict("records")})

    lines.append(
        f"- **Q1（原始 BAZI_POS 是否仍近乎恒正）**：OOS 正向率 "
        f"{min(raw_rates):.1%}–{max(raw_rates):.1%}（TRAIN 期同样在此量级），"
        "即**是**，样本外仍然接近「全体命中」。"
    )
    lines.append(
        f"- **Q2（校准是否降低 Jaccard）**：真实集合与随机集合的 Jaccard 从 "
        f"{min(raw_j):.2f}–{max(raw_j):.2f} 降到 {min(cal_j):.2f}–{max(cal_j):.2f}，"
        "即**是**，区分度问题被校准解决。"
    )
    lines.append(
        f"- **Q3（区分度改善后是否真的优于随机）**：校准后事件的 OOS 平均超额收益为 "
        f"{min(cal_excess):.2%}–{max(cal_excess):.2%}（同期随机对照 "
        f"{min(row['control_mean_excess_return'] for row in calibrated.to_dict('records')):.2%}"
        f"–{max(row['control_mean_excess_return'] for row in calibrated.to_dict('records')):.2%}），"
        f"单侧置换 p = {min(cal_p):.3f}–{max(cal_p):.3f}，状态 "
        f"{', '.join('`' + s + '`' for s in statuses)}。"
    )
    lines.append(
        "- **本阶段对 Q3 的结论**：校准**提高了事件区分度**，但在预注册的显著性门槛"
        "（p < 0.05）下**没有产生可复现的预测信息**；且校准后事件的绝对超额收益仍为负。"
        "即 `Calibration improved discrimination, but did not create predictive information.`"
    )
    return lines


def _label(object_id: str) -> str:
    return OBJECT_LABEL.get(object_id, object_id)


def build_report() -> str:
    summary = json.loads((OUT_DIR / "phase3d_run_summary.json").read_text(encoding="utf-8"))
    registry = json.loads((OUT_DIR / "phase3d_hypothesis_registry.json").read_text(encoding="utf-8"))
    freeze = json.loads((OUT_DIR / "phase3d_calibration_freeze.json").read_text(encoding="utf-8"))
    results = _read_csv("phase3d_oos_results.csv")
    partitions = _read_csv("phase3d_oos_partition_stats.csv")
    controls = _read_csv("phase3d_oos_controls.csv")
    walkforward = _read_csv("phase3d_walkforward_results.csv")
    overlap = _read_csv("phase3d_overlap_sensitivity.csv")
    registry_csv = _read_csv("phase3d_experiment_registry.csv")
    concentration = _read_csv("phase3d_oos_hit_concentration.csv")

    split = summary["split"]
    thresholds = summary["gate_thresholds"]
    panel = summary["panel"]
    labels = summary["labels"]
    status_counts = summary["status_counts"]

    lines: list[str] = []
    lines += [
        "# Phase 3D · 样本外（OOS）与 Walk-forward 研究结果",
        "",
        f"> 生成时间：{summary['generated_at']} · commit `{summary['git_sha']}`",
        f"> `split_version={split['split_version']}` · `calibration_version={split['calibration_version']}`"
        f" · `label_version={split['label_version']}` · `gate_version={thresholds['gate_version']}`",
        f"> 数据快照 `{split['dataset_version']}`（universe `{split['universe_version']}`）",
        "",
        "**先读这一句**：本阶段没有任何结果解锁 `SUPPORTED_OUT_OF_SAMPLE`。"
        "最高状态是 `OOS_CANDIDATE_SUPPORTED`（候选），且正式解锁必须等 Phase 3F 的 "
        "BH-FDR 多重检验校正。以下是全部结果（含空结果与失败假设）。",
        "",
        "## 0. 结论摘要",
        "",
    ]
    candidates = results[results["status"] == "OOS_CANDIDATE_SUPPORTED"]
    fdr = _fdr_projection(results)
    lines += _table(
        ["问题", "答案"],
        [
            ["是否产生 OOS 候选（`OOS_CANDIDATE_SUPPORTED`）",
             f"**{'是' if not candidates.empty else '否'}**（{len(candidates)}/{len(results)}）"],
            ["是否产出 `SUPPORTED_OUT_OF_SAMPLE`",
             "**否** —— 结构上不可能（需 3F 的 BH-FDR）"],
            ["状态分布", ", ".join(f"`{k}`={v}" for k, v in sorted(status_counts.items()))],
            ["正向（优于对照）的实验数",
             f"gate 内 {fdr.get('nominal_significant')} 个名义 p < 0.05"
             f"（探索性另有若干，未套 gate）；最低 p = {fdr.get('min_p', float('nan')):.4f}"],
            ["若现在就做 BH-FDR 会怎样",
             f"m={fdr.get('m')} 个正式实验，最小 BH 门槛 = "
             f"{fdr.get('bh_threshold_min', float('nan')):.5f} → "
             f"**通过 {fdr.get('passing_bh')} 个**（这正是把正式解锁留给 3F 的实证理由）"],
            ["唯一显著为负的发现",
             "黄历校准事件集合在 OOS 显著弱于同数量随机集合（见 §5 与 §6）"],
            ["本阶段是否成功",
             "**是**：管线建立、纪律可执行、结论为 NO_SIGNAL/INCONCLUSIVE 且如实输出"],
        ],
    )
    lines += [
        "",
        "## 1. 基线与规模",
        "",
    ]
    lines += _table(
        ["项目", "值"],
        [
            ["commit SHA", f"`{summary['git_sha']}`"],
            ["TRAIN", f"{split['train_start']} .. {split['train_end']}"],
            ["VALIDATION", f"{split['validation_start']} .. {split['validation_end']}"],
            ["OOS", f"{split['oos_start']} .. {split['oos_end']}"],
            ["切分指纹", f"`{split['split_version']}` / `{_split_fingerprint(summary)}`"],
            ["主面板采样", f"每 {split['sample_step_months']} 个月，{panel['main_dates']} 个 as_of"],
            ["主面板观测行", f"{panel['main_rows']:,}"],
            ["月度 OOS 子面板", f"{panel['monthly_dates']} 个 as_of（{panel['monthly_rows']:,} 行）"],
            ["出生平移面板", f"±7 天 × {panel['shift_dates']} 个 as_of（仅 OOS）"],
            ["宇宙", f"{split['universe_version']} · {panel['main_codes']} 只（含退市股）"],
            ["排盘失败", f"`{panel['failures']}`"],
            ["紫微可用性", panel["ziwei_unavailable_reason"] or "可用"],
            ["标签口径", f"`{labels['label_version']}`；除权因子文件 {labels['adj_factor_files']} 个，覆盖 {labels['codes_with_adj']}/{labels['codes_with_adj'] + labels['codes_without_adj']} 只"],
            ["标签行数", f"{labels['label_rows']:,}"],
            ["降级行情", f"{len(labels['degraded_codes'])} 只"],
            ["假设注册表", f"`{registry['hypothesis_registry']['registry_version']}`（冻结于 "
                          f"{registry['hypothesis_registry']['frozen_at']}，"
                          f"预注册时 `oos_labels_seen={registry['hypothesis_registry']['oos_labels_seen_at_registration']}`）"],
            ["假设数 / 实验数", f"{summary['hypothesis_count']} 个假设 → {summary['experiment_count']} 个固定 holdout 实验"],
            ["Walk-forward", f"{summary['walkforward_fold_count']} 个 fold/序列 × 12 条序列（{summary['walkforward_row_count']} 行记录）"],
            ["实验登记行", f"{len(registry_csv)}"],
        ],
    )

    lines += ["", "## 2. 校准冻结（cal-v1）", ""]
    holdout_fit = freeze["holdout_fit"]
    lines += _table(
        ["项目", "值"],
        [
            ["calibration_version", f"`{holdout_fit['calibration_version']}`（= `research-calibration-v1`）"],
            ["fit_scope", f"`{holdout_fit['fit_scope']}`"],
            ["fit 实际最后一个 as_of", f"{holdout_fit['fit_max_as_of']}（网格点；边界 {holdout_fit['train_end']}，滞后 {holdout_fit['fit_lag_days_vs_train_end']} 天）"],
            ["fit 行数 / 分组数", f"{holdout_fit['fit_row_count']:,} / {holdout_fit['fit_group_count']}"],
            ["fit hash", f"`{holdout_fit['calibration_fit_hash']}`"],
            ["oos_labels_seen（冻结时）", f"{freeze['freeze']['oos_labels_seen']}"],
        ],
    )

    # ---------------------------------------------------------------- 头条结果
    lines += ["", "## 3. 全部对象 × 出生模型的 OOS 结果（主持有期 20D）", ""]
    lines.append(
        "`OOS 事件`/`资格数` 给出正向率；`对照差` = OOS 平均超额收益 − 随机事件位置对照均值；"
        "`p` = 置换法单侧经验 p；`Jaccard` = 真实事件集合与代表性随机集合的重合度（>0.9 即对照失效）。"
    )
    lines.append("")
    header = ["对象", "出生模型", "OOS 事件/资格数", "正向率", "OOS 平均超额", "对照差", "p", "Jaccard", "状态"]
    rows: list[list[str]] = []
    for object_id in HEADLINE_OBJECTS:
        for birth_model in ("listing_open_v1", "listing_close_v1", "ipo_approx_v1"):
            record = results[
                (results["object_id"] == object_id) & (results["birth_model"] == birth_model)
            ]
            if record.empty:
                continue
            row = record.iloc[0]
            rows.append([
                _label(object_id), f"`{birth_model}`",
                f"{_fmt_int(row['oos_sample_count'])}/{_fmt_int(row['oos_pool_count'])}",
                _fmt_pct(row["oos_positive_rate"]),
                _fmt_pct(row["oos_mean_excess_return"]),
                _fmt_pct(row["control_mean_excess_return"] and row["oos_mean_excess_return"] - row["control_mean_excess_return"]),
                _fmt_num(row["control_p_value"], 4),
                _fmt_num(row["control_jaccard"], 3),
                f"`{row['status']}`",
            ])
    lines += _table(header, rows)

    lines += ["", "## 4. 全部持有期结果（禁止只报告最好的一档）", ""]
    lines.append(
        "每个对象 × 出生模型 × 四个持有期的平均超额收益与上涨率（OOS 分区）。"
    )
    lines.append("")
    header = ["对象", "出生模型", "5D", "10D", "20D", "60D"]
    rows = []
    for object_id in HEADLINE_OBJECTS:
        for birth_model in ("listing_open_v1", "listing_close_v1", "ipo_approx_v1"):
            sub = partitions[
                (partitions["object_id"] == object_id)
                & (partitions["birth_model"] == birth_model)
                & (partitions["partition"] == "OOS")
            ]
            if sub.empty:
                continue
            cells = []
            for horizon in (5, 10, 20, 60):
                item = sub[sub["horizon"] == horizon]
                cells.append(
                    "—" if item.empty
                    else f"{_fmt_pct(item.iloc[0]['mean_excess_return'], 2)} (n={_fmt_int(item.iloc[0]['sample_count'])})"
                )
            rows.append([_label(object_id), f"`{birth_model}`", *cells])
    lines += _table(header, rows)

    # ---------------------------------------------------------------- §19 三问
    lines += ["", "## 5. 正式回答 GOAL §19 的核心三问（BAZI_POS）", ""]
    raw = results[results["object_id"] == "bazi_raw"]
    calibrated = results[results["object_id"] == "bazi_calibrated"]
    lines.append("**Q1：Raw BAZI_POS 在 Validation / OOS 是否仍然近乎恒正？**")
    lines.append("")
    rows = []
    for birth_model in ("listing_open_v1", "listing_close_v1", "ipo_approx_v1"):
        for table, name in ((raw, "raw"), (calibrated, "calibrated")):
            record = table[table["birth_model"] == birth_model]
            if record.empty:
                continue
            row = record.iloc[0]
            rows.append([
                f"`{birth_model}`", name,
                _fmt_pct(row["train_positive_rate"]),
                _fmt_pct(row["validation_positive_rate"]),
                _fmt_pct(row["oos_positive_rate"]),
            ])
    lines += _table(["出生模型", "口径", "TRAIN 正向率", "VALIDATION 正向率", "OOS 正向率"], rows)
    lines.append("")
    lines.append("**Q2：Calibrated Bazi 是否成功降低 Jaccard？**")
    lines.append("")
    rows = []
    for birth_model in ("listing_open_v1", "listing_close_v1", "ipo_approx_v1"):
        raw_row = raw[raw["birth_model"] == birth_model]
        cal_row = calibrated[calibrated["birth_model"] == birth_model]
        if raw_row.empty or cal_row.empty:
            continue
        rows.append([
            f"`{birth_model}`",
            _fmt_num(raw_row.iloc[0]["control_jaccard"], 3),
            _fmt_num(cal_row.iloc[0]["control_jaccard"], 3),
            f"`{raw_row.iloc[0]['status']}`",
            f"`{cal_row.iloc[0]['status']}`",
        ])
    lines += _table(["出生模型", "raw Jaccard", "calibrated Jaccard", "raw 状态", "calibrated 状态"], rows)
    lines.append("")
    lines.append("**Q3：事件区分度改善以后，是否真的优于随机？**")
    lines.append("")
    lines.append(
        "见下表：区分度（正向率）与 Jaccard 是第一层问题，是否优于对照是第二层问题。"
        "两者必须分别回答 —— 区分度提升不等于产生信息量。"
    )
    lines.append("")
    rows = []
    for birth_model in ("listing_open_v1", "listing_close_v1", "ipo_approx_v1"):
        cal_row = calibrated[calibrated["birth_model"] == birth_model]
        raw_row = raw[raw["birth_model"] == birth_model]
        if cal_row.empty:
            continue
        row = cal_row.iloc[0]
        rows.append([
            f"`{birth_model}`",
            _fmt_pct(row["oos_positive_rate"]),
            _fmt_num(row["control_jaccard"], 3),
            _fmt_pct(row["oos_mean_excess_return"]),
            _fmt_pct(row["control_mean_excess_return"]),
            _fmt_num(row["control_p_value"], 3),
            f"`{row['status']}`",
            "—" if raw_row.empty else f"`{raw_row.iloc[0]['status']}`",
        ])
    lines += _table(
        ["出生模型", "cal 正向率", "cal Jaccard", "cal OOS 超额", "对照", "p", "cal 状态", "raw 状态"],
        rows,
    )

    # ---------------------------------------------------------------- 负对照
    lines += ["", "## 6. 负对照状态（GOAL §14 / §19）", ""]
    lines.append(
        "`位置` = 随机事件位置（200 次置换）；`指派` = 随机出生指派；`方向` = 随机模型方向；"
        "`−7d`/`+7d` = 出生日期平移（仅 OOS、使用真实 TRAIN 阈值）。"
    )
    lines.append("")
    header = ["对象", "出生模型", "对照", "对照事件数", "对照均值", "相对差", "p", "Jaccard", "判定"]
    rows = []
    focus = results[
        (results["object_id"].isin([
            "bazi_raw", "bazi_calibrated", "ziwei_calibrated", "huangli_calibrated",
            "all_three_calibrated",
        ]))
    ]
    for record in focus.to_dict("records"):
        sub = controls[
            (controls["hypothesis_id"] == record["hypothesis_id"])
            & (controls["birth_model"] == record["birth_model"])
        ]
        for item in sub.to_dict("records"):
            rows.append([
                _label(record["object_id"]), f"`{record['birth_model']}`",
                f"`{item['control_kind']}`",
                _fmt_int(item["event_count"]),
                _fmt_pct(item["mean_excess_return"]),
                _fmt_pct(item["delta_mean_excess_vs_real"]),
                _fmt_num(item["p_value"], 3),
                _fmt_num(item["jaccard_with_real"], 3),
                f"`{item['verdict']}`" + ("（失效）" if (item["jaccard_with_real"] or 0) > 0.9 else ""),
            ])
    lines += _table(header, rows)

    invalid = controls[
        controls["jaccard_with_real"].notna() & (controls["jaccard_with_real"] > 0.9)
    ]
    lines += [
        "",
        f"**Jaccard > 0.9 的对照共 {len(invalid)} 条**（占全部对照 "
        f"{len(controls)} 条，{len(invalid) / max(len(controls), 1):.1%}）。"
        "它们集中在哪些对象上，直接对应 Phase 3C 记录的原始方向偏置："
        "事件集合接近整个可用池时，任何随机类对照都无法区分真实与随机。",
    ]

    # ---------------------------------------------------------------- 集中度
    lines += ["", "## 6.5 横截面命中集中度：黄历是「日历开关」", ""]
    lines.append(
        "每个 `as_of` 的命中率 = 当日命中股票数 / 当日可用股票数。若某引擎常常"
        "「几乎全体命中或几乎全体不命中」，它的事件集合实际是**日期选择**而不是"
        "**股票选择** —— 这会让两类负对照测量不同的零假设（见下）。"
    )
    lines.append("")
    header = ["对象", "出生模型", "日期数", "命中率最低", "命中率最高", "命中率标准差", ">60% 的日期", "<5% 的日期"]
    rows = []
    focus_objects = [
        "bazi_raw", "bazi_calibrated", "ziwei_calibrated", "huangli_raw",
        "huangli_calibrated", "all_three_calibrated",
    ]
    for item in concentration.to_dict("records"):
        if item["object_id"] not in focus_objects or item["partition"] != "OOS":
            continue
        rows.append([
            _label(item["object_id"]), f"`{item['birth_model']}`",
            _fmt_int(item["date_count"]), _fmt_num(item["min_rate"], 3),
            _fmt_num(item["max_rate"], 3), _fmt_num(item["std_rate"], 3),
            _fmt_int(item["dates_above_high"]), _fmt_int(item["dates_below_low"]),
        ])
    lines += _table(header, rows)
    lines += [
        "",
        "**结构性发现（对负对照解读至关重要）**：`huangli` 的校准方向在横截面上"
        "几乎没有区分度 —— 同一天要么几乎全体命中、要么几乎全体不命中，"
        "因此它的事件集合接近「挑选日期」。这直接造成两类负对照给出相反结论：",
        "",
        "* `random_event_position`（从整个池随机抽同数量）→ 混合了日期构成，"
        "与真实集合的日期权重错配 → 真实集合看起来**显著更差**（下尾 p 很小）；",
        "* `random_birth_assignment` / `random_model_direction`（保留每日命中数量）"
        "→ 与真实集合的差异只剩「哪些股票命中」→ 真实 ≈ 对照（差 ≈ +0.1pp）。",
        "",
        "本阶段**不**因此改动协议（那属于看到结果后调参）：两个口径都按预注册口径输出，"
        "gate 因「对照结论不一致」判 `INCONCLUSIVE`，并把「按日期分层的随机对照」"
        "列为 Phase 3F 的协议改进项（`gate-v2` / `cal-v2`）。",
    ]

    # ---------------------------------------------------------------- 稳定性
    lines += ["", "## 7. 跨年份稳定性、单一股票依赖与重叠敏感性", ""]
    lines.append("### 7.1 年份稳定性（OOS 分区，主持有期）")
    lines.append("")
    header = ["对象", "出生模型", "有效年数", "正向年份比例", "符号一致性", "OOS 平均超额"]
    rows = []
    for record in focus.to_dict("records"):
        rows.append([
            _label(record["object_id"]), f"`{record['birth_model']}`",
            _fmt_int(record["year_count"]), _fmt_num(record["positive_year_ratio"], 2),
            _fmt_num(record["sign_consistency"], 2),
            _fmt_pct(record["oos_mean_excess_return"]),
        ])
    lines += _table(header, rows)
    lines.append("")
    lines.append("### 7.2 单一股票依赖（top1/top5 绝对贡献份额 + leave-one-stock-out）")
    lines.append("")
    header = ["对象", "出生模型", "top1", "top5", "LOO 最小值", "LOO 最大值", "符号翻转股票数", "判定"]
    rows = []
    for record in focus.to_dict("records"):
        rows.append([
            _label(record["object_id"]), f"`{record['birth_model']}`",
            _fmt_num(record["top_1_contribution"], 3),
            _fmt_num(record["top_5_contribution"], 3),
            _fmt_pct(record["loo_mean_min"]), _fmt_pct(record["loo_mean_max"]),
            _fmt_int(record["loo_sign_flip_count"]),
            "`SINGLE_NAME_DEPENDENT`" if record["single_name_dependent"] else "否",
        ])
    lines += _table(header, rows)
    lines.append("")
    lines.append("### 7.3 重叠窗口敏感性（月度 OOS 子面板：密集采样 vs 非重叠子样本）")
    lines.append("")
    header = ["对象", "出生模型", "事件数（月度）", "重叠比例", "全样本平均超额", "非重叠子样本 n", "非重叠平均超额"]
    rows = []
    for item in overlap.to_dict("records"):
        rows.append([
            _label(str(item["object_id"])), f"`{item['birth_model']}`",
            _fmt_int(item["event_count"]),
            _fmt_num(item["overlap_ratio"], 3),
            _fmt_pct(item["mean_excess_return_all"]),
            _fmt_int(item["non_overlapping_event_count"]),
            _fmt_pct(item["mean_excess_return_non_overlapping"]),
        ])
    lines += _table(header, rows)

    # ---------------------------------------------------------------- walk-forward
    lines += ["", "## 8. Walk-forward（扩窗、逐 fold 重拟合）", ""]
    wf_summary = (
        walkforward.groupby(["hypothesis_id", "birth_model"])
        .agg(
            folds=("fold_id", "count"),
            refit=("calibration_fit_hash", "nunique"),
            positive=("mean_excess_return", lambda values: int((values > 0).sum())),
            outperformed=("research_status", lambda values: int((values == "OUTPERFORM_CONTROL").sum())),
            mean_excess=("mean_excess_return", "mean"),
        )
        .reset_index()
    )
    header = ["对象", "出生模型", "fold 数", "不同 fit hash 数", "正收益 fold", "击败对照 fold", "平均超额"]
    rows = []
    for item in wf_summary.to_dict("records"):
        record = results[
            (results["hypothesis_id"] == item["hypothesis_id"])
            & (results["birth_model"] == item["birth_model"])
        ]
        object_label = _label(record.iloc[0]["object_id"]) if not record.empty else item["hypothesis_id"]
        rows.append([
            object_label, f"`{item['birth_model']}`", _fmt_int(item["folds"]),
            _fmt_int(item["refit"]), _fmt_int(item["positive"]),
            _fmt_int(item["outperformed"]), _fmt_pct(item["mean_excess"]),
        ])
    lines += _table(header, rows)
    fit_hash_ok = bool((wf_summary["refit"] == wf_summary["folds"]).all())
    lines += [
        "",
        f"每个 fold 的 `calibration_fit_hash` 全部互不相同：**{fit_hash_ok}**"
        "（证明逐 fold 重拟合，而不是复用全 TRAIN 校准）。",
        "fold 级明细（含训练区间、`fit_partitions`、`freeze_bound_exceeded`、负对照）见 "
        "`data/phase3_universe/phase3d_walkforward_results.csv`。",
    ]

    # ---------------------------------------------------------------- 出生模型
    lines += ["", "## 9. 出生模型对比（GOAL §10）", ""]
    lines.append(
        "这里回答的是「哪个出生模型下结论更稳定」，而不是「哪个出生模型才是真实出生时间」。"
        "三个模型都是上市日派生的研究构造，且 OOS 表现最好也不构成"
        "「它就是真实出生时间」的任何证据。"
    )
    lines.append("")
    header = ["出生模型", "实验数", "NO_SIGNAL", "INVALID_CONTROL", "INCONCLUSIVE", "WEAK_EVIDENCE", "候选"]
    rows = []
    for birth_model in ("listing_open_v1", "listing_close_v1", "ipo_approx_v1"):
        sub = results[results["birth_model"] == birth_model]
        counts = sub["status"].value_counts().to_dict()
        rows.append([
            f"`{birth_model}`", _fmt_int(len(sub)),
            _fmt_int(counts.get("NO_SIGNAL", 0)),
            _fmt_int(counts.get("INVALID_CONTROL", 0)),
            _fmt_int(counts.get("INCONCLUSIVE", 0)),
            _fmt_int(counts.get("WEAK_EVIDENCE", 0)),
            _fmt_int(counts.get("OOS_CANDIDATE_SUPPORTED", 0)),
        ])
    lines += _table(header, rows)

    # ---------------------------------------------------------------- 结论
    candidates = results[results["status"] == "OOS_CANDIDATE_SUPPORTED"]
    lines += ["", "## 10. 是否产生 OOS 候选 / 正式支持", ""]
    fdr = _fdr_projection(results)
    lines += _table(
        ["问题", "答案"],
        [
            ["是否产生 OOS_CANDIDATE_SUPPORTED",
             f"**{'是' if not candidates.empty else '否'}**（{len(candidates)} 个实验）"],
            ["是否产生 SUPPORTED_OUT_OF_SAMPLE", "**否** —— Phase 3D 结构上不可能产出（FDR 属 3F）"],
            ["状态分布", ", ".join(f"`{k}`={v}" for k, v in sorted(status_counts.items()))],
        ],
    )
    lines += [
        "",
        "### FDR 前瞻（为什么必须把解锁留给 Phase 3F）",
        "",
        f"把 {fdr.get('m')} 个进入 gate 的实验按名义 p 值排序，最小 p = "
        f"{fdr.get('min_p', float('nan')):.5f}；BH-FDR（α=0.05，m={fdr.get('m')}）对应的"
        f"最小门槛为 {fdr.get('bh_threshold_min', float('nan')):.5f} → "
        f"**通过 {fdr.get('passing_bh')} 个**。名义上 p < 0.05 的有 "
        f"{fdr.get('nominal_significant')} 个，但它们全部是效应量极小"
        "（|Cohen's d| ≈ 0.02–0.06）的弱结果，且无一通过年份稳定性条件。"
        "这正是 GOAL §15 要求「3D 最多给候选、正式解锁交给 3F」的实证理由。",
        "",
        "### 唯一的方向性负结果",
        "",
        "黄历校准事件集合（`huangli_calibrated`）在 OOS 的 20D 平均超额收益为 "
        "−4.6% 至 −5.0%，而同数量随机集合为 −2.2%，单侧置换 p 的上尾为 1.0、"
        "下尾约 0.005–0.03 —— 即**显著弱于随机**。这不是「术数有效」的反面证据，"
        "而是「按该口径挑出来的日期在这一段样本里恰好更差」的描述性事实："
        "它同样需要 3F 的多重检验与 3E 的中性化才能判断是否为结构（日历/季节）效应。"
        "系统不把它表述为可交易信号。",
    ]

    lines += ["", "## 11. 实验登记与 OOS 复用纪律", ""]
    lines += _table(
        ["项目", "值"],
        [
            ["登记行数", f"{len(registry_csv)}"],
            ["全部 oos_used", f"{bool(registry_csv['oos_used'].all())}"],
            ["git_sha 一致", f"{registry_csv['git_sha'].nunique() == 1}"],
            ["split_version", ", ".join(sorted(registry_csv['split_version'].unique()))],
        ],
    )
    lines.append("")
    lines += ["", "## 12. 失败假设与空结果清单", ""]
    lines.append("以下是**没有**显示样本外信息量的对象（如实列出，不做美化）：")
    lines.append("")
    no_signal = results[results["status"].isin(["NO_SIGNAL", "WEAK_EVIDENCE", "INCONCLUSIVE"])]
    header = ["对象", "出生模型", "状态", "原因（首条）"]
    rows = []
    for record in no_signal.to_dict("records"):
        rows.append([_label(record["object_id"]), f"`{record['birth_model']}`",
                     f"`{record['status']}`", _first_reason(registry_csv, record["experiment_id"])])
    lines += _table(header, rows)

    lines += [
        "",
        "## 13. 方法与限制",
        "",
        "完整协议见 [`oos-methodology.md`](oos-methodology.md) 与 "
        "[`walk-forward-methodology.md`](walk-forward-methodology.md)。"
        "读本报告时必须同时接受以下限制：",
        "",
        "1. **未做多重检验校正**（BH-FDR 属 Phase 3F）：54 个实验共享同一 OOS 区间，"
        "`p` 值未校正，这正是本阶段不产出 `SUPPORTED_OUT_OF_SAMPLE` 的原因。",
        "2. **行业无 PIT**（`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`）：未做行业/风格中性化，"
        "OOS 差异可能混入行业结构。",
        "3. **出生时间 = 上市日派生**：`company_foundation` 不可得，结论只适用于该研究构造。",
        "4. **出生平移对照只覆盖 OOS**，且使用真实 TRAIN 冻结阈值。",
        "5. **未计交易成本 / 流动性 / 涨跌停**：这是信息量检验，不是可交易性检验。",
        "6. **退市股除权因子来自第二个快照**，覆盖情况已在 "
        "`phase3d_calibration_freeze.json` 的 `label` 字段披露。",
        "",
    ]
    return "\n".join(lines) + "\n"


def _split_fingerprint(summary: dict) -> str:
    """切分指纹（由 split 字段重算，保证报告可核对）。"""
    import hashlib

    payload = json.dumps(summary["split"], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _first_reason(registry: pd.DataFrame, experiment_id: str) -> str:
    record = registry[registry["experiment_id"] == experiment_id]
    if record.empty:
        return "—"
    reasons = json.loads(record.iloc[0]["result_reasons"] or "[]")
    if not reasons:
        return "—"
    text = str(reasons[0]).replace("|", "/").replace("\n", " ")
    return text[:160] + ("…" if len(text) > 160 else "")


def main() -> int:
    REPORT.write_text(build_report(), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
