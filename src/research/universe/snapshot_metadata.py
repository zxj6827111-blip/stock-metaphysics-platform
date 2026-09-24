"""Universe 证据截止日（evidence as-of）解析器。

为什么需要它
------------
「目标日期是否已超出我们知道的范围」必须有一个**可追溯**的答案。
曾用过的 `max(list_date)` 是错的：**最后一只 IPO 的上市日期 ≠ 数据快照抓取日期**。
若 universe 于 2026-09-20 抓取、最近 IPO 是 09-01，则 09-02~09-20 会被误判成
"未来"，并按 09-01 冻结成员集 —— 连带把 09-01~09-20 之间的退市也抹掉。

正式来源（按优先级）
--------------------
1. ``universe_memberships.source_snapshot`` 本身能解析成 ISO 日期 → 直接采用；
2. 该 universe 的**正式报告文件**（见 :data:`UNIVERSE_REPORT_FILES`）里的
   ``generated_at``，并要求 ``universe_version`` 与 ``vendor_data_version``
   与库内实际写入的快照标签**互相印证**；
3. 以上都不成立 → ``available=False``。调用方必须 **fail closed**，
   禁止退回任何"猜一个日期"的兜底。

设计约束
--------
* 不在业务代码里散落硬编码日期；日期只来自数据工件本身。
* 报告文件路径与 universe_version 的对应关系集中在此并带版本号，便于测试与后续替换。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: 本解析口径的版本。语义变化（来源优先级、校验规则）必须提升它。
UNIVERSE_EVIDENCE_METADATA_VERSION = "universe-evidence-asof-v1"

#: universe_version → 正式证据报告文件名（相对 ``settings.data_dir``）。
#: 这些 JSON 由 scripts/ 下的离线构建脚本产出并随仓库入库。
UNIVERSE_REPORT_FILES: dict[str, str] = {
    "v4-full": "phase4_universe_report.json",
}

_SOURCE = "universe_membership_source_snapshot"
_SOURCE_REPORT = "universe_report_generated_at"
_SOURCE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class UniverseEvidenceAsOf:
    """一个 universe 版本的证据截止日及其出处。"""

    universe_version: str
    as_of: date | None
    source: str = _SOURCE_UNAVAILABLE
    detail: str = ""
    metadata_version: str = UNIVERSE_EVIDENCE_METADATA_VERSION

    @property
    def available(self) -> bool:
        return self.as_of is not None


def _parse_date(value: object) -> date | None:
    """把标签/ISO 日期/ISO datetime 统一解析成日期；解析不了就返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _distinct_source_snapshots(db: Session, universe_version: str) -> tuple[str, ...]:
    from src.db.models import UniverseMembershipRow

    values = db.execute(
        select(UniverseMembershipRow.source_snapshot).where(
            UniverseMembershipRow.universe_version == universe_version
        ).distinct()
    ).scalars().all()
    return tuple(sorted({str(v) for v in values if v}))


def resolve_universe_evidence_as_of(
    db: Session,
    universe_version: str,
    *,
    data_dir: Path | None = None,
    report_files: Mapping[str, str] | None = None,
) -> UniverseEvidenceAsOf:
    """解析 ``universe_version`` 的证据截止日。解析不出时返回 ``available=False``。

    ``report_files`` 允许调用方（含测试）提供另一份登记表；
    缺省用 :data:`UNIVERSE_REPORT_FILES`。
    """
    registry = UNIVERSE_REPORT_FILES if report_files is None else report_files
    snapshots = _distinct_source_snapshots(db, universe_version)
    if not snapshots:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=f"universe_version={universe_version} 下没有任何 membership 行，无法确定证据截止日。",
        )

    # 来源 1：库内快照标签本身就是日期
    parsed = {snap: _parse_date(snap) for snap in snapshots}
    if snapshots and all(parsed[snap] for snap in snapshots):
        if len({parsed[snap] for snap in snapshots}) > 1:
            return UniverseEvidenceAsOf(
                universe_version=universe_version, as_of=None,
                detail=(
                    f"存在多个互不相同的快照日期 {sorted(snapshots)}，"
                    "无法确定唯一的证据截止日；拒绝挑一个来用。"
                ),
            )
        as_of = parsed[snapshots[0]]
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=as_of, source=_SOURCE,
            detail=f"source_snapshot={snapshots[0]} 直接给出证据截止日。",
        )

    # 来源 2：正式报告文件，并与库内快照标签互相印证
    filename = registry.get(universe_version)
    if filename is None:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=(
                f"source_snapshot={list(snapshots)} 不是日期，且 "
                f"universe_version={universe_version} 未登记正式证据报告。"
            ),
        )
    path = (data_dir or settings.data_dir) / filename
    if not path.is_file():
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=f"正式证据报告不存在：{path}",
        )
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=f"正式证据报告无法解析：{path}（{type(exc).__name__}: {exc}）",
        )

    reported_version = str(report.get("universe_version") or "")
    if reported_version != universe_version:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=f"{path.name} 的 universe_version={reported_version!r} 与请求不一致。",
        )
    as_of = _parse_date(report.get("generated_at"))
    if as_of is None:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=f"{path.name} 缺少可解析的 generated_at。",
        )
    vendor = str(report.get("vendor_data_version") or "")
    unknown = [snap for snap in snapshots if snap != vendor]
    if unknown:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=(
                f"{path.name} 声明 vendor_data_version={vendor!r}，"
                f"但库内 source_snapshot 为 {unknown}，两者无法互相印证；"
                "不使用该报告的 generated_at。"
            ),
        )
    return UniverseEvidenceAsOf(
        universe_version=universe_version, as_of=as_of, source=_SOURCE_REPORT,
        detail=(
            f"{path.name} generated_at={report.get('generated_at')}，"
            f"且 universe_version 与 vendor_data_version={vendor} 均与库内一致。"
        ),
    )


__all__ = [
    "UNIVERSE_EVIDENCE_METADATA_VERSION",
    "UNIVERSE_REPORT_FILES",
    "UniverseEvidenceAsOf",
    "resolve_universe_evidence_as_of",
]
