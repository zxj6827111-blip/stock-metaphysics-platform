"""Point-in-Time Universe（Phase 3A）。

设计要点
========

* **单版本多快照**：``universe_version`` 区分"同一份定义下的不同抓取快照"或
  "不同选择口径"。研究引用时必须指定 ``universe_version``，不得跨版本混用。
* **as_of 语义**：见模块顶层 docstring。任何绕过这里直接查 universe 的代码
  都需要上 ADR。
* **生存者偏差告警**：只要 ``universe_version`` 下存在任意一条 ``delist_date IS NULL``，
  ``PointInTimeUniverse`` 就**必须**在返回时把 ``SurvivorshipBiasWarning`` 附上；
  调用者可以选择忽略，但不得静默丢弃（研究报告中必须出现）。
* **排序稳定**：``at()``/``iter_daily_range()`` 返回的股票代码按 ``stock_code`` 升序，
  保证实验可复现（GOAL §13 / §14）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.db.models import UniverseMembershipRow


@dataclass(frozen=True)
class MembershipRecord:
    stock_code: str
    exchange: str
    board: str
    list_date: date
    delist_date: date | None
    status: str
    source: str
    universe_version: str
    delist_source: str = ""   # tushare_pit_universe / NOT_AVAILABLE_FROM_PROVIDER / 空串
    """数据源声明是否覆盖该股的退市日：
    * ``tushare_pit_universe`` 等真实来源 → ``delist_date=NULL`` 的语义是"截至快照未退市"
    * 空串 / ``NOT_AVAILABLE_FROM_PROVIDER`` → ``NULL`` 的语义是"不可得"
    """


@dataclass(frozen=True)
class SurvivorshipBiasWarning:
    """生存者偏差告知（§3A-2 强制输出）。

    只要本 universe_version 下所有股票的 ``delist_date`` 都是 NULL
    （即我们**不知道**谁已退市），就意味着该宇宙里可能混入了"今天还在上市
    但在历史上表现被当前快照过度代表"的股票。
    """

    kind: str = "SURVIVORSHIP_BIAS_WARNING"
    severity: str = "warning"

    version: str = ""
    reason: str = ""
    member_count_with_delist_known: int = 0
    member_count_total: int = 0

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "version": self.version,
            "reason": self.reason,
            "member_count_with_delist_known": self.member_count_with_delist_known,
            "member_count_total": self.member_count_total,
        }


@dataclass(frozen=True)
class UniverseSnapshot:
    """``at(as_of)`` 的一次查询结果。

    ``digest`` 是对成员列表的稳定哈希，供研究引用 / 回归对账使用。
    """

    universe_version: str
    as_of: date
    member_codes: tuple[str, ...]
    members: tuple[MembershipRecord, ...] = field(repr=False, compare=False)
    warnings: tuple[SurvivorshipBiasWarning, ...] = ()
    digest: str = ""

    def as_dict(self) -> dict:
        return {
            "universe_version": self.universe_version,
            "as_of": self.as_of.isoformat(),
            "size": len(self.member_codes),
            "digest": self.digest,
            "warnings": [w.as_dict() for w in self.warnings],
        }


class PointInTimeUniverse:
    """查询 ``universe_memberships`` 的官方入口。

    使用::

        uni = PointInTimeUniverse.load(db, universe_version="v1")
        snap = uni.at(date(2020, 1, 1))
        assert 600519 在 snap.member_codes 中
    """

    def __init__(
        self,
        records: list[MembershipRecord],
        universe_version: str,
        *,
        snapshot_at: date,
    ) -> None:
        self.universe_version = universe_version
        self.snapshot_at = snapshot_at
        # 先按 stock_code 排序，再按 list_date 排序：保证 at() 返回稳定
        self._records = sorted(records, key=lambda r: (r.stock_code, r.list_date))
        # 预聚合生存者偏差警告（若需要）
        self._survivorship_warnings: tuple[SurvivorshipBiasWarning, ...] = (
            self._build_survivorship_warnings()
        )

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------
    @classmethod
    def load(
        cls,
        db: Session,
        universe_version: str,
        *,
        snapshot_at: date | None = None,
    ) -> PointInTimeUniverse:
        from src.db.models import UniverseMembershipRow

        rows: list[UniverseMembershipRow] = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == universe_version
            ).order_by(UniverseMembershipRow.stock_code)
        ).scalars().all()
        records = [
            MembershipRecord(
                stock_code=r.stock_code,
                exchange=r.exchange,
                board=r.board,
                list_date=r.list_date,
                delist_date=r.delist_date,
                status=r.status,
                source=r.source,
                universe_version=r.universe_version,
                delist_source=str(r.delist_source or ""),
            )
            for r in rows
        ]
        return cls(
            records,
            universe_version=universe_version,
            snapshot_at=snapshot_at or date.today(),
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def at(self, as_of: date) -> UniverseSnapshot:
        """``as_of`` 时刻的 universe 成员。

        严格遵循：
          ``list_date <= as_of`` AND (``delist_date IS NULL`` OR ``as_of <= delist_date``)
        """
        members: list[MembershipRecord] = [
            r for r in self._records
            if r.list_date <= as_of and (r.delist_date is None or as_of <= r.delist_date)
        ]
        codes = tuple(m.stock_code for m in members)
        return UniverseSnapshot(
            universe_version=self.universe_version,
            as_of=as_of,
            member_codes=codes,
            members=tuple(members),
            warnings=self._survivorship_warnings,
            digest=self._digest(codes),
        )

    def iter_daily_range(self, start: date, end: date):
        """按日步进生成 ``(date, UniverseSnapshot)``。"""
        cur = start
        while cur <= end:
            yield cur, self.at(cur)
            cur += timedelta(days=1)

    def is_member(self, stock_code: str, as_of: date) -> bool:
        """便捷判断。"""
        if not stock_code:
            return False
        target = stock_code.strip()
        for r in self._records:
            if r.stock_code == target and r.list_date <= as_of and (
                r.delist_date is None or as_of <= r.delist_date
            ):
                return True
        return False

    def list_all_members(self) -> list[MembershipRecord]:
        """返回所有已登记的 membership（含未来才上市 / 已退市的）。"""
        return list(self._records)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _build_survivorship_warnings(self) -> tuple[SurvivorshipBiasWarning, ...]:
        if not self._records:
            return (SurvivorshipBiasWarning(
                version=self.universe_version,
                reason="universe_version 下没有任何 membership 记录",
                member_count_with_delist_known=0,
                member_count_total=0,
            ),)
        total = len(self._records)
        # 已知"最终归宿"的股数：要么有明确退市日，要么 delist_source 声明了可信来源且为 NULL（="确认在市"）
        known = sum(
            1 for r in self._records
            if r.delist_date is not None
            or (r.delist_source and r.delist_source != "NOT_AVAILABLE_FROM_PROVIDER")
        )
        unknown = total - known
        if unknown == 0:
            return ()
        # 如果"未知"数量 > 0，分两种情形：
        if known == 0:
            return (SurvivorshipBiasWarning(
                version=self.universe_version,
                reason=(
                    "当前数据通道对全部股票均无法判断退市状态（delist_source 缺失或 NOT_AVAILABLE_FROM_PROVIDER），"
                    "无法排除『宇宙内全是幸存者』的情形。研究报告必须显式声明 SURVIVORSHIP_BIAS_WARNING。"
                ),
                member_count_with_delist_known=known,
                member_count_total=total,
            ),)
        return (SurvivorshipBiasWarning(
            version=self.universe_version,
            reason=(
                f"universe 内 {unknown}/{total} 条 membership 的退市状态未知"
                f"（delist_date IS NULL 且 delist_source 缺失）；"
                f"其余 {known} 条已确认。"
            ),
            member_count_with_delist_known=known,
            member_count_total=total,
        ),)

    @staticmethod
    def _digest(codes: tuple[str, ...]) -> str:
        return hashlib.sha256(
            json.dumps(list(codes), ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
