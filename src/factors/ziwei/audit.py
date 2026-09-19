"""紫微因子质量审计（Phase 2B）。

为什么需要一个**专门**的审计口径
--------------------------------
Phase 1 的因子审计用 ``activation_rate``（``normalized_value != 0`` 的占比）
判断区分度，并把 ``>95%`` / ``<0.5%`` 标记为 ``LOW_DISCRIMINATION_FACTOR``。

那个口径是为**事件型（离散）因子**设计的 —— "结构成立/不成立"。
直接套到紫微会出错：像 ``Z_LIFE_001``（命宫主星庙旺和）这类**连续型**因子的
取值几乎永远不为 0，于是 activation_rate ≈ 100%，会被误判为"低区分度"，
而它实际上区分度良好。

第二个陷阱：``count`` 型因子
--------------------------
``Z_TRINE_005``（财官迁三宫主星总数）这类计数**天然有下限**（三宫主星合计永远 ≥ 1），
因此它的 activation_rate 恒为 100%，但它在样本上有 5 个不同取值、区分度良好。
把 activation_rate 用在它身上同样会误判。

因此本模块的最终口径：

    binary         0/1 事件型：activation_rate > 95% 或 < 0.5% → LOW_DISCRIMINATION
    count / cont.  有量纲：unique <= 1 → CONSTANT（同时标 LOW_DISCRIMINATION）
                            主值占比 ≥ 99.5% → NEAR_CONSTANT
                            unique <= 2 且主值占比 ≥ 95% → LOW_DISCRIMINATION

**审计只报告，不删除因子。** 低区分度是事实，不是缺陷；隐瞒才是缺陷。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.factors.ziwei.definitions import ZIWEI_DEFINITION_INDEX

#: 阈值（与 Phase 1 审计保持一致，便于横向比较）
LOW_DISCRIMINATION_HIGH = 0.95
LOW_DISCRIMINATION_LOW = 0.005
DUPLICATE_CORR = 0.98
NEAR_CONSTANT_SHARE = 0.995

#: raw_unit → 因子类型
_BINARY_UNITS = {"bool"}
_COUNT_UNITS = {"count", "count_diff", "days", "tier"}


def factor_kind(factor_id: str) -> str:
    """把因子分为 ``binary`` / ``count`` / ``continuous``。"""
    definition = ZIWEI_DEFINITION_INDEX.get(factor_id)
    unit = (definition.raw_unit if definition else "") or ""
    if unit in _BINARY_UNITS:
        return "binary"
    if unit in _COUNT_UNITS:
        return "count"
    return "continuous"


@dataclass
class ZiweiFactorQuality:
    factor_id: str
    kind: str
    sample_count: int = 0
    null_rate: float = 0.0
    activation_rate: float = 0.0
    unique_value_count: int = 0
    direction_distribution: dict[str, int] = field(default_factory=dict)
    mean: float | None = None
    std: float | None = None
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "factor_id": self.factor_id,
            "kind": self.kind,
            "sample_count": self.sample_count,
            "null_rate": self.null_rate,
            "activation_rate": self.activation_rate,
            "unique_value_count": self.unique_value_count,
            "direction_distribution": self.direction_distribution,
            "mean": self.mean,
            "std": self.std,
            "flags": self.flags,
        }


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def audit_factor(
    factor_id: str,
    normalized: list[float | None],
    directions: list[int],
    availability: list[str],
) -> ZiweiFactorQuality:
    """对单个因子的观测序列做质量审计。"""
    kind = factor_kind(factor_id)
    n = len(normalized)
    present = [v for v in normalized if v is not None]
    usable = [
        v for v, a in zip(normalized, availability, strict=True)
        if a == "ok" and v is not None
    ]
    non_zero = [v for v in usable if v != 0.0]

    q = ZiweiFactorQuality(factor_id=factor_id, kind=kind, sample_count=n)
    if n == 0:
        q.flags.append("NO_SAMPLE")
        return q

    q.null_rate = round(1.0 - len(present) / n, 4)
    q.activation_rate = round(len(non_zero) / max(len(usable), 1), 4)
    q.unique_value_count = len(set(present))
    q.direction_distribution = {
        "+1": sum(1 for d in directions if d > 0),
        "0": sum(1 for d in directions if d == 0),
        "-1": sum(1 for d in directions if d < 0),
    }
    if present:
        q.mean = round(sum(present) / len(present), 6)
        q.std = round(_std(present), 6)

    # --- 标记 ---
    if not present:
        q.flags.append("ALL_NULL_FACTOR")
        return q

    share = _dominant_share(present)
    if q.unique_value_count == 1:
        q.flags.append("CONSTANT_FACTOR")
    elif share >= NEAR_CONSTANT_SHARE:
        q.flags.append("NEAR_CONSTANT_FACTOR")

    if kind == "binary":
        # 0/1 事件型：激活率就是区分度本身
        if q.activation_rate > LOW_DISCRIMINATION_HIGH or q.activation_rate < LOW_DISCRIMINATION_LOW:
            q.flags.append("LOW_DISCRIMINATION_FACTOR")
    else:
        # 计数/连续型：取值天然有下限时 activation 恒为 100%，不能用它判区分度。
        # 改用"是否几乎只有一个取值"。
        if q.unique_value_count <= 1:
            q.flags.append("LOW_DISCRIMINATION_FACTOR")
        elif q.unique_value_count <= 2 and share >= 0.95:
            q.flags.append("LOW_DISCRIMINATION_FACTOR")

    if q.null_rate >= 1.0 and "ALL_NULL_FACTOR" not in q.flags:
        q.flags.append("ALL_NULL_FACTOR")
    return q


def _dominant_share(values: list[float]) -> float:
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.values()) / len(values)


def audit_many(rows: list[dict]) -> list[ZiweiFactorQuality]:
    """``rows`` 每项形如 ``{factor_id, normalized_value, direction, availability}``。"""
    by_factor: dict[str, dict[str, list]] = {}
    for r in rows:
        bucket = by_factor.setdefault(
            str(r["factor_id"]), {"n": [], "d": [], "a": []},
        )
        bucket["n"].append(r.get("normalized_value"))
        bucket["d"].append(int(r.get("direction") or 0))
        bucket["a"].append(str(r.get("availability") or "ok"))

    return [
        audit_factor(fid, b["n"], b["d"], b["a"])
        for fid, b in sorted(by_factor.items())
    ]


def pairwise_correlations(
    series: dict[str, list[float | None]], *, threshold: float = DUPLICATE_CORR,
) -> list[dict]:
    """两两 Pearson 相关；返回超过阈值的疑似重复因子对。

    只使用**两个因子都非空**的样本对，避免用 0 填充制造假相关。
    """
    ids = sorted(series)
    out: list[dict] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            va, vb = series[a], series[b]
            pairs = [
                (x, y) for x, y in zip(va, vb, strict=False)
                if x is not None and y is not None
            ]
            if len(pairs) < 8:
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            r = _pearson(xs, ys)
            if r is not None and abs(r) > threshold:
                out.append({"a": a, "b": b, "pearson": round(r, 4), "n": len(pairs)})
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


__all__ = [
    "ZiweiFactorQuality", "audit_factor", "audit_many", "factor_kind",
    "pairwise_correlations", "LOW_DISCRIMINATION_HIGH", "LOW_DISCRIMINATION_LOW",
    "DUPLICATE_CORR",
]
