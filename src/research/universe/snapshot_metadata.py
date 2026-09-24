"""Universe 证据截止日（evidence as-of）解析器。

为什么需要它
------------
「目标日期是否已超出我们知道的范围」必须有一个**可追溯**的答案。
曾用过的 `max(list_date)` 是错的：**最后一只 IPO 的上市日期 ≠ 数据快照抓取日期**。
若 universe 于 2026-09-20 抓取、最近 IPO 是 09-01，则 09-02~09-20 会被误判成
"未来"，并按 09-01 冻结成员集 —— 连带把 09-01~09-20 之间的退市也抹掉。

正式来源（按优先级）
--------------------
1. 全部行的 ``universe_memberships.source_snapshot`` 都能解析成同一个 ISO 日期 → 直取；
2. 该 universe 的**正式报告文件**（见 :data:`UNIVERSE_REPORT_FILES`）里的
   ``generated_at``，并要求 ``universe_version`` 与 ``vendor_data_version``
   与库内实际写入的快照标签**互相印证**；
3. 以上都不成立 → ``available=False``。调用方必须 **fail closed**，
   禁止退回任何"猜一个日期"的兜底。

两道完整性闸门（v2 新增，两道都必须过）
--------------------------------------
* **provenance 完整性**：只要存在任意一行 ``source_snapshot`` 为空/NULL 就 fail closed。
  v1 先 ``if v`` 把空值过滤掉再判唯一，于是"3 行里 1 行没有 provenance"的 universe
  会被宣布为已知 —— 那是把数据缺口当成证据。
* **事件一致性**：候选截止日必须与库内上市/退市事件自洽。
  存在 ``list_date > 候选日`` 的行，或某行 ``status="delisted"`` 而其
  ``delist_date > 候选日``（数据库把它当既成退市事实，却声称证据只到该截止日），
  都是库内容与 cutoff 互相矛盾 → fail closed。
  仅"已预告、尚未发生"的未来退市（status 非 delisted）不算矛盾，但写进 detail 留痕。

``max(list_date)`` 在本模块**只用于对账**（与候选日比较），从不被反过来当成候选日本身
—— 否则就又退化成 R1 修掉的那个错误。

设计约束
--------
* 不在业务代码里散落硬编码日期；日期只来自数据工件本身。
* 报告文件路径与 universe_version 的对应关系集中在此并带版本号，便于测试与后续替换。
* 不通过删除/忽略 membership 行来"修复"数据缺口。
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

#: 本解析口径的版本。
#: v1→v2：新增 provenance 完整性闸与事件一致性闸 ——
#: 原先能过 v1 的库（存在空 source_snapshot 或事件矛盾）在 v2 下会 fail closed。
UNIVERSE_EVIDENCE_METADATA_VERSION = "universe-evidence-asof-v2"

#: universe_version → 正式证据报告文件名（相对 ``settings.data_dir``）。
#: 这些 JSON 由 scripts/ 下的离线构建脚本产出并随仓库入库。
UNIVERSE_REPORT_FILES: dict[str, str] = {
    "v4-full": "phase4_universe_report.json",
}

_SOURCE = "universe_membership_source_snapshot"
_SOURCE_REPORT = "universe_report_generated_at"
_SOURCE_UNAVAILABLE = "unavailable"

#: 只有这一类状态意味着"数据库宣称该退市日已是既成事实"
_STATUS_DELISTED = "delisted"


@dataclass(frozen=True)
class UniverseEvidenceAsOf:
    """一个 universe 版本的证据截止日及其出处。

    无论成功还是拒答，三个计数都会被填上 —— 拒答时必须能说出缺在哪一类。
    """

    universe_version: str
    as_of: date | None
    source: str = _SOURCE_UNAVAILABLE
    detail: str = ""
    metadata_version: str = UNIVERSE_EVIDENCE_METADATA_VERSION
    membership_total: int = 0
    snapshot_present: int = 0
    snapshot_missing: int = 0

    @property
    def available(self) -> bool:
        return self.as_of is not None


@dataclass(frozen=True)
class MembershipFacts:
    """一行 membership 中与"这批数据是哪天抓的"有关的事实。"""

    stock_code: str
    source_snapshot: str
    list_date: date | None
    delist_date: date | None
    status: str


@dataclass(frozen=True)
class MembershipCensus:
    """全量 membership 普查结果 —— 空值不被静默丢弃是它存在的理由。"""

    total: int = 0
    present: int = 0
    missing: int = 0
    distinct_snapshots: tuple[str, ...] = ()
    max_list_date: date | None = None
    facts: tuple[MembershipFacts, ...] = ()

    @property
    def provenance_counts_text(self) -> str:
        return (
            f"membership_total={self.total}, "
            f"snapshot_present={self.present}, "
            f"snapshot_missing={self.missing}"
        )


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


def _census_membership(db: Session, universe_version: str) -> MembershipCensus:
    """普查该 universe 下**全部** membership 行。

    刻意不过滤空 ``source_snapshot``：丢空值正是被审查掉的缺陷。
    """
    from src.db.models import UniverseMembershipRow

    rows = db.execute(
        select(
            UniverseMembershipRow.stock_code,
            UniverseMembershipRow.source_snapshot,
            UniverseMembershipRow.list_date,
            UniverseMembershipRow.delist_date,
            UniverseMembershipRow.status,
        ).where(UniverseMembershipRow.universe_version == universe_version)
    ).all()
    facts = tuple(
        MembershipFacts(
            stock_code=str(code),
            source_snapshot=str(snapshot or "").strip(),
            list_date=list_date,
            delist_date=delist_date,
            status=str(status or "").strip(),
        )
        for code, snapshot, list_date, delist_date, status in rows
    )
    listed = [fact.list_date for fact in facts if fact.list_date]
    return MembershipCensus(
        total=len(facts),
        present=sum(1 for fact in facts if fact.source_snapshot),
        missing=sum(1 for fact in facts if not fact.source_snapshot),
        distinct_snapshots=tuple(sorted({fact.source_snapshot for fact in facts if fact.source_snapshot})),
        max_list_date=max(listed) if listed else None,
        facts=facts,
    )


def _reject(universe_version: str, census: MembershipCensus, detail: str) -> UniverseEvidenceAsOf:
    return UniverseEvidenceAsOf(
        universe_version=universe_version, as_of=None, detail=detail,
        membership_total=census.total, snapshot_present=census.present,
        snapshot_missing=census.missing,
    )


def _event_conflict(census: MembershipCensus, candidate: date) -> str | None:
    """候选截止日与库内事件对账。返回 None 表示自洽，否则返回拒答原因。"""
    future_listings = sorted(
        fact.stock_code for fact in census.facts
        if fact.list_date is not None and fact.list_date > candidate
    )
    if future_listings:
        latest = max(
            fact.list_date for fact in census.facts
            if fact.list_date is not None and fact.list_date > candidate
        )
        return (
            f"存在 {len(future_listings)} 行的 list_date 晚于候选证据截止日 {candidate}"
            f"（最晚 {latest}，如 {future_listings[:3]}），库内容与该 cutoff 自相矛盾，拒绝采信。"
            "注：对账用的 max(list_date) 不会被反过来当成快照日期。"
        )
    contradictory_delists = sorted(
        fact.stock_code for fact in census.facts
        if fact.delist_date is not None
        and fact.delist_date > candidate
        and fact.status == _STATUS_DELISTED
    )
    if contradictory_delists:
        return (
            f"存在 {len(contradictory_delists)} 行 status=delisted 而 delist_date 晚于候选证据"
            f"截止日 {candidate}（如 {contradictory_delists[:3]}）：数据库把它当成既成退市事实，"
            "却声称证据只到该截止日，二者矛盾，拒绝采信。"
        )
    return None


def _announced_future_delists(census: MembershipCensus, candidate: date) -> int:
    """已预告但尚未发生（status 非 delisted）的未来退市行数 —— 只留痕，不算矛盾。"""
    return sum(
        1 for fact in census.facts
        if fact.delist_date is not None and fact.delist_date > candidate
    )


def _candidate_from_source_snapshots(
    census: MembershipCensus,
) -> tuple[date | None, str, str, str]:
    """来源 1。返回（候选日, 出处, detail, 拒答原因）；(None, "", "", "") 表示不适用。"""
    snapshots = census.distinct_snapshots
    if not snapshots:
        return None, _SOURCE_UNAVAILABLE, "", ""
    parsed = [_parse_date(snap) for snap in snapshots]
    if any(when is None for when in parsed):
        return None, _SOURCE_UNAVAILABLE, "", ""
    unique = {when for when in parsed if when is not None}
    if len(unique) > 1:
        return None, _SOURCE_UNAVAILABLE, "", (
            f"存在多个互不相同的快照日期 {list(snapshots)}，无法确定唯一的证据截止日；"
            "拒绝挑一个来用。"
        )
    candidate = next(iter(unique))
    return candidate, _SOURCE, f"source_snapshot={snapshots[0]} 直接给出证据截止日。", ""


def _candidate_from_report(
    universe_version: str,
    census: MembershipCensus,
    data_dir: Path | None,
    registry: Mapping[str, str],
) -> tuple[date | None, str, str]:
    """来源 2：正式报告文件，并与库内快照标签互相印证。"""
    filename = registry.get(universe_version)
    if filename is None:
        return None, _SOURCE_UNAVAILABLE, (
            f"source_snapshot={list(census.distinct_snapshots)} 不全是日期，且 "
            f"universe_version={universe_version} 未登记正式证据报告。"
        )
    path = (data_dir or settings.data_dir) / filename
    if not path.is_file():
        return None, _SOURCE_UNAVAILABLE, f"正式证据报告不存在：{path}"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, _SOURCE_UNAVAILABLE, (
            f"正式证据报告无法解析：{path}（{type(exc).__name__}: {exc}）"
        )

    reported_version = str(report.get("universe_version") or "")
    if reported_version != universe_version:
        return None, _SOURCE_UNAVAILABLE, (
            f"{path.name} 的 universe_version={reported_version!r} 与请求不一致。"
        )
    candidate = _parse_date(report.get("generated_at"))
    if candidate is None:
        return None, _SOURCE_UNAVAILABLE, f"{path.name} 缺少可解析的 generated_at。"
    vendor = str(report.get("vendor_data_version") or "")
    unmatched = [snap for snap in census.distinct_snapshots if snap != vendor]
    if unmatched:
        return None, _SOURCE_UNAVAILABLE, (
            f"{path.name} 声明 vendor_data_version={vendor!r}，"
            f"但库内 source_snapshot 为 {unmatched}，两者无法互相印证；不使用该报告的 generated_at。"
        )
    return candidate, _SOURCE_REPORT, (
        f"{path.name} generated_at={report.get('generated_at')}，"
        f"且 universe_version 与 vendor_data_version={vendor} 均与库内一致。"
    )


def resolve_universe_evidence_as_of(
    db: Session,
    universe_version: str,
    *,
    data_dir: Path | None = None,
    report_files: Mapping[str, str] | None = None,
) -> UniverseEvidenceAsOf:
    """解析 ``universe_version`` 的证据截止日。任一闸门不过即返回 ``available=False``。

    ``report_files`` 允许调用方（含测试）提供另一份登记表；
    缺省用 :data:`UNIVERSE_REPORT_FILES`。
    """
    registry = UNIVERSE_REPORT_FILES if report_files is None else report_files
    census = _census_membership(db, universe_version)

    if census.total == 0:
        return UniverseEvidenceAsOf(
            universe_version=universe_version, as_of=None,
            detail=f"universe_version={universe_version} 下没有任何 membership 行，无法确定证据截止日。",
        )

    # 闸门 1：provenance 完整性 —— 空标签是数据缺口，不是"可以忽略的一行"
    if census.missing:
        return _reject(
            universe_version, census,
            (
                f"有 {census.missing} 行 membership 的 source_snapshot 为空/NULL，"
                "该 universe 的 provenance 不完整；拒绝在忽略这些行的前提下宣布证据截止日。"
                f"（{census.provenance_counts_text}）"
            ),
        )

    candidate, source, detail, conflict_text = _candidate_from_source_snapshots(census)
    if candidate is None and conflict_text:
        return _reject(universe_version, census, f"{conflict_text}（{census.provenance_counts_text}）")
    if candidate is None:
        candidate, source, detail = _candidate_from_report(universe_version, census, data_dir, registry)
    if candidate is None:
        reason = detail or "无法确定证据截止日。"
        return _reject(universe_version, census, f"{reason}（{census.provenance_counts_text}）")

    # 闸门 2：事件一致性 —— 过了才对外宣布 available
    conflict = _event_conflict(census, candidate)
    if conflict is not None:
        return _reject(universe_version, census, f"{conflict}（{census.provenance_counts_text}）")

    announced = _announced_future_delists(census, candidate)
    note = "" if announced == 0 else (
        f" 另有 {announced} 行 delist_date 晚于该截止日且 status 非 delisted，"
        "按「已预告、未发生」处理，不当作截止日之前的已知信息。"
    )
    return UniverseEvidenceAsOf(
        universe_version=universe_version, as_of=candidate, source=source,
        detail=f"{detail}{note}（{census.provenance_counts_text}）",
        membership_total=census.total, snapshot_present=census.present,
        snapshot_missing=census.missing,
    )


__all__ = [
    "UNIVERSE_EVIDENCE_METADATA_VERSION",
    "UNIVERSE_REPORT_FILES",
    "MembershipCensus",
    "MembershipFacts",
    "UniverseEvidenceAsOf",
    "resolve_universe_evidence_as_of",
]
