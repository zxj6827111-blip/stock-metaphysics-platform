"""Phase 3F · 多重检验校正（Benjamini-Hochberg FDR + Bonferroni）。

为什么必须报告三个数
--------------------
只报告校正后的结论，读者无法判断"是校正把它们全杀了，还是本来就没有信号"。
因此每个检验都同时输出：

    raw_p_value            未校正
    bonferroni_threshold   族内 α/m（最保守）
    fdr_q_value            BH 调整后的 q
    fdr_pass               q <= α

BH 在**族内**做校正。族由 ``families.py`` 冻结定义；把族拆细以降低校正强度
属于禁止行为（GOAL §4.1）。

实现细节
--------
* ``raw_p`` 必须是已经算好的、与检验口径一致的 p 值；
  本模块**不做**任何统计检验，只做校正（避免"校正里藏着第二种检验"）。
* p 值缺失（None / NaN）的检验被排除在校正之外，并单独计数：
  m 只统计**可判定**的检验，但缺失情况必须显式报告。
* BH 的单调化（step-up）必须做：只按排名取阈值会在非单调的 q 上给出
  自相矛盾的结论（q(2) < q(1)）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class MultipleTestingResult:
    """一个族的校正结果。"""

    family_id: str
    alpha: float
    test_count: int
    evaluable_count: int
    missing_count: int
    mt_version: str = ""
    rows: list[dict] = field(default_factory=list)

    @property
    def fdr_pass_count(self) -> int:
        return sum(1 for row in self.rows if row.get("fdr_pass"))

    @property
    def bonferroni_pass_count(self) -> int:
        return sum(
            1 for row in self.rows
            if row.get("raw_p_value") is not None
            and float(row["raw_p_value"]) <= float(row["bonferroni_threshold"])
        )

    @property
    def min_raw_p(self) -> float | None:
        values = [
            float(row["raw_p_value"]) for row in self.rows
            if row.get("raw_p_value") is not None
        ]
        return min(values) if values else None

    def to_dict(self) -> dict:
        return {
            "family_id": self.family_id,
            "alpha": self.alpha,
            "mt_version": self.mt_version,
            "test_count": self.test_count,
            "evaluable_count": self.evaluable_count,
            "missing_count": self.missing_count,
            "fdr_pass_count": self.fdr_pass_count,
            "bonferroni_pass_count": self.bonferroni_pass_count,
            "min_raw_p": self.min_raw_p,
            "bonferroni_threshold": (
                self.rows[0]["bonferroni_threshold"] if self.rows else None
            ),
            "rows": list(self.rows),
        }


def benjamini_hochberg(p_values: list[float | None], alpha: float) -> list[float | None]:
    """BH 调整后的 q 值（保持输入顺序；缺失项返回 None）。

    ``q_(i) = min_{j >= i} ( m * p_(j) / j )``，并对 1.0 截断。
    """
    if alpha <= 0 or alpha >= 1:
        raise ValueError("alpha 必须在 (0, 1) 内")
    indexed = [
        (index, float(value)) for index, value in enumerate(p_values) if value is not None
    ]
    out: list[float | None] = [None] * len(p_values)
    if not indexed:
        return out
    m = len(indexed)
    ordered = sorted(indexed, key=lambda item: item[1])
    adjusted = [min(1.0, m * value / (rank + 1)) for rank, (_index, value) in enumerate(ordered)]
    # step-up 单调化：从最大值往回扫，保证 q 随 p 单调不减
    for rank in range(m - 2, -1, -1):
        adjusted[rank] = min(adjusted[rank], adjusted[rank + 1])
    for rank, (index, _value) in enumerate(ordered):
        out[index] = adjusted[rank]
    return out


def apply_family_correction(
    rows: list[dict],
    *,
    family_id: str,
    alpha: float,
    mt_version: str = "",
    p_field: str = "raw_p_value",
) -> MultipleTestingResult:
    """对一个族的检验行做校正，返回带 q 值的新行（浅拷贝，不改输入）。"""
    evaluable = [
        row for row in rows
        if row.get(p_field) is not None
        and np.isfinite(float(row[p_field]))
    ]
    missing = len(rows) - len(evaluable)
    p_values = [float(row[p_field]) for row in evaluable]
    q_values = benjamini_hochberg(p_values, alpha)
    m = len(evaluable)
    threshold = alpha / m if m else None

    out_rows: list[dict] = []
    for row in rows:
        new_row = dict(row)
        value = row.get(p_field)
        usable = value is not None and np.isfinite(float(value))
        new_row["family_id"] = family_id
        new_row["family_test_count"] = m
        new_row["alpha"] = alpha
        new_row["bonferroni_threshold"] = threshold
        new_row["fdr_q_value"] = None
        new_row["fdr_pass"] = False
        new_row["bonferroni_pass"] = False
        new_row[f"{p_field}_missing"] = not usable
        out_rows.append(new_row)

    position = 0
    for new_row, row in zip(out_rows, rows, strict=True):
        value = row.get(p_field)
        if value is None or not np.isfinite(float(value)):
            continue
        q_value = q_values[position]
        position += 1
        new_row["fdr_q_value"] = None if q_value is None else round(float(q_value), 10)
        new_row["fdr_pass"] = bool(q_value is not None and q_value <= alpha)
        new_row["bonferroni_pass"] = bool(threshold is not None and float(value) <= threshold)

    return MultipleTestingResult(
        family_id=family_id,
        alpha=alpha,
        test_count=len(rows),
        evaluable_count=m,
        missing_count=missing,
        mt_version=mt_version,
        rows=out_rows,
    )


__all__ = [
    "MultipleTestingResult",
    "apply_family_correction",
    "benjamini_hochberg",
]
