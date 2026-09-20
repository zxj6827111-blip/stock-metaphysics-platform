"""Phase 3F · 假设族冻结与读取（GOAL §4.2）。

为什么族必须先冻结
------------------
多重检验校正的强度直接取决于"族里有多少个检验"。如果允许在看过 q-value 之后
把族拆细（把 42 个检验说成"其实它们是 6 个独立的族"），校正就会变得毫无约束 ——
这是研究里最常见、也最难被外部发现的作弊方式。

因此本项目把族定义放在 ``config/phase3f_multiple_testing_families.yaml``：
在读取最终校正结果之前写入并冻结，且带 ``mt_version``。改动族定义必须
新建 ``mt-v2``，旧文件原样保留。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

#: 多重检验协议版本（改动族定义/检验口径必须提升）
MT_VERSION = "mt-v1"
#: 默认显著性水平（预注册）
DEFAULT_ALPHA = 0.05


class FamilyContractError(ValueError):
    """假设族契约被破坏（重复归属、未知假设、缺少族等）。"""


@dataclass(frozen=True)
class FamilySpec:
    """一个假设族。"""

    family_id: str
    description: str
    gated: bool
    tails: str
    hypothesis_ids: tuple[str, ...] = ()
    comparison_objects: tuple[str, ...] = ()
    birth_model_pairs: tuple[tuple[str, str], ...] = ()
    primary_horizon_only: bool = False

    def to_dict(self) -> dict:
        return {
            "family_id": self.family_id,
            "description": self.description,
            "gated": self.gated,
            "tails": self.tails,
            "hypothesis_ids": list(self.hypothesis_ids),
            "comparison_objects": list(self.comparison_objects),
            "birth_model_pairs": [list(pair) for pair in self.birth_model_pairs],
            "primary_horizon_only": self.primary_horizon_only,
        }


@dataclass(frozen=True)
class FamilyRegistry:
    """全部族的不可变集合。"""

    mt_version: str
    frozen_at: str
    final_results_seen_at_freeze: bool
    alpha: float
    families: tuple[FamilySpec, ...]
    notes: tuple[str, ...] = field(default=())

    def by_id(self, family_id: str) -> FamilySpec:
        for family in self.families:
            if family.family_id == family_id:
                return family
        raise KeyError(f"未注册的族：{family_id}")

    def family_of(self, hypothesis_id: str) -> str:
        """假设 → 族。每个 formal hypothesis 必须**恰好**属于一个族。"""
        matches = [
            family.family_id for family in self.families
            if hypothesis_id in family.hypothesis_ids
        ]
        if len(matches) != 1:
            raise FamilyContractError(
                f"假设 {hypothesis_id} 归属族数量为 {len(matches)}（必须恰好 1）：{matches}"
            )
        return matches[0]

    def gated_families(self) -> tuple[FamilySpec, ...]:
        return tuple(family for family in self.families if family.gated)

    def validate_against(self, hypothesis_ids: tuple[str, ...]) -> None:
        """校验族划分覆盖了**全部**假设（不能有假设被静默漏掉）。"""
        registered = {
            hypothesis_id for family in self.families for hypothesis_id in family.hypothesis_ids
        }
        known = set(hypothesis_ids)
        unknown = sorted(registered - known)
        if unknown:
            raise FamilyContractError(f"族引用了未注册的假设：{unknown}")
        missing = sorted(known - registered)
        if missing:
            raise FamilyContractError(
                f"以下假设没有归属任何族（多重检验会漏掉它们）：{missing}"
            )
        duplicates = [
            hypothesis_id for hypothesis_id in known
            if sum(
                hypothesis_id in family.hypothesis_ids for family in self.families
            ) > 1
        ]
        if duplicates:
            raise FamilyContractError(f"假设重复归属多个族：{sorted(duplicates)}")

    def to_dict(self) -> dict:
        return {
            "mt_version": self.mt_version,
            "frozen_at": self.frozen_at,
            "final_results_seen_at_freeze": self.final_results_seen_at_freeze,
            "alpha": self.alpha,
            "families": [family.to_dict() for family in self.families],
            "notes": list(self.notes),
        }


def load_family_registry(path: str | Path) -> FamilyRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FamilyContractError(f"族定义文件格式异常：{path}")
    families: list[FamilySpec] = []
    for raw in payload.get("families", []):
        pairs = tuple(
            (str(pair[0]), str(pair[1])) for pair in raw.get("birth_model_pairs", []) or []
        )
        families.append(FamilySpec(
            family_id=str(raw["family_id"]),
            description=str(raw.get("description", "")),
            gated=bool(raw.get("gated", True)),
            tails=str(raw.get("tails", "one_sided")),
            hypothesis_ids=tuple(str(value) for value in raw.get("hypothesis_ids", []) or []),
            comparison_objects=tuple(
                str(value) for value in raw.get("comparison_objects", []) or []
            ),
            birth_model_pairs=pairs,
            primary_horizon_only=bool(raw.get("primary_horizon_only", False)),
        ))
    if not families:
        raise FamilyContractError(f"族定义文件没有 families：{path}")
    for family in families:
        if family.tails not in {"one_sided", "two_sided"}:
            raise FamilyContractError(f"{family.family_id}: tails 必须是 one_sided / two_sided")
    return FamilyRegistry(
        mt_version=str(payload.get("mt_version", MT_VERSION)),
        frozen_at=str(payload.get("frozen_at", "")),
        final_results_seen_at_freeze=bool(payload.get("final_results_seen_at_freeze", False)),
        alpha=float(payload.get("alpha", DEFAULT_ALPHA)),
        families=tuple(families),
        notes=tuple(str(value) for value in payload.get("notes", []) or []),
    )


__all__ = [
    "DEFAULT_ALPHA",
    "MT_VERSION",
    "FamilyContractError",
    "FamilyRegistry",
    "FamilySpec",
    "load_family_registry",
]
