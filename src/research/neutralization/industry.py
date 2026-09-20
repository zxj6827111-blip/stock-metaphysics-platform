"""Phase 3E · 行业分类可得性与板块（segment）控制。

为什么不能"顺手用当前行业"
--------------------------
GOAL §3E-2 明确：把**当前**行业分类当成历史行业，等于把未来信息写进历史横截面
（一家 2015 年是钢铁、2024 年重组为半导体的公司，会被按 2024 年的行业分组）。
因此本项目规定：

* 没有 PIT 行业分类时，唯一合法的状态是 ``POINT_IN_TIME_INDUSTRY_UNAVAILABLE``；
* 如果只有当前行业，可以用于 ``CURRENT_INDUSTRY_SENSITIVITY_ANALYSIS``，
  但必须携带该 warning，且**不得**称为"严格 industry-neutral backtest"；
* 找不到就不编造，不联网抓取后冒充权威分类。

本项目实测结论（2026-09-20）
----------------------------
* canonical AStockData 快照不含任何行业字段（blob 只有 OHLCV；PIT universe JSON
  只有 ``board`` / ``list_status``）；
* TuShare 本地目录下**没有** ``stock_basic`` / ``daily_basic`` 一类的带行业表；
* 唯一带 ``industry`` 的文件是 ``data/import/stocks.csv``，覆盖的是 Phase 1
  的 20 只腾讯快照，与 Phase 3 的 500 只 universe **不重叠到可用程度**，
  且是"当前行业"而非历史行业。

因此本阶段行业中性化状态为 **双重不可用**：
``POINT_IN_TIME_INDUSTRY_UNAVAILABLE`` 与 ``INDUSTRY_CLASSIFICATION_UNAVAILABLE``。

替代方案（真实可得，且不是行业）
--------------------------------
``board``（交易所板块：``sse_main`` / ``szse_main`` / ``szse_sme_legacy`` /
``chinext`` / ``star``）来自 Phase 3A 的 PIT universe 注册簿，是**法定板块归属**，
不是行业。本模块把它作为 ``SEGMENT_CONTROL_BOARD`` 提供，用于部分回答
"是不是某个板块整体在涨"，并在报告中明确它不能替代行业中性化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import pandas as pd
from sqlalchemy import select

from src.db.base import get_session_factory
from src.db.models import UniverseMembershipRow

#: 行业分类口径版本
INDUSTRY_VERSION = "phase3e-industry-v1"
#: 状态常量
POINT_IN_TIME_INDUSTRY_UNAVAILABLE = "POINT_IN_TIME_INDUSTRY_UNAVAILABLE"
INDUSTRY_CLASSIFICATION_UNAVAILABLE = "INDUSTRY_CLASSIFICATION_UNAVAILABLE"
CURRENT_INDUSTRY_SENSITIVITY_ANALYSIS = "CURRENT_INDUSTRY_SENSITIVITY_ANALYSIS"
#: 板块控制口径
SEGMENT_CONTROL_BOARD = "SEGMENT_CONTROL_BOARD"

#: 板块取值 → 中文释义（写入报告，避免读者把 board 误当行业）
BOARD_LABELS: dict[str, str] = {
    "sse_main": "上交所主板",
    "szse_main": "深交所主板",
    "szse_sme_legacy": "深交所中小板（已并入主板）",
    "chinext": "创业板",
    "star": "科创板",
}


@dataclass(frozen=True)
class IndustryStatus:
    """行业分类可得性状态（写入产物与报告）。"""

    industry_version: str
    status: str
    point_in_time_available: bool
    current_classification_available: bool
    detail: str
    segment_control: str = SEGMENT_CONTROL_BOARD
    segment_labels: dict[str, str] = field(default_factory=lambda: dict(BOARD_LABELS))

    def to_dict(self) -> dict:
        return {
            "industry_version": self.industry_version,
            "status": self.status,
            "point_in_time_available": self.point_in_time_available,
            "current_classification_available": self.current_classification_available,
            "detail": self.detail,
            "segment_control": self.segment_control,
            "segment_labels": dict(self.segment_labels),
            "neutralization_available": self.point_in_time_available,
            "strict_industry_neutral_backtest_allowed": self.point_in_time_available,
        }


@runtime_checkable
class IndustryClassificationProvider(Protocol):
    """行业分类提供者契约（为将来真正拿到 PIT 分类时预留）。"""

    def status(self) -> IndustryStatus: ...

    def classify(self, as_of) -> dict[str, str]:  # type: ignore[no-untyped-def]
        """返回 ``{stock_code: industry}``，必须已经是该 ``as_of`` 的历史口径。"""
        ...


class UnavailableIndustryProvider:
    """当前阶段唯一诚实的实现：显式不可用，``classify`` 直接拒绝。"""

    def status(self) -> IndustryStatus:
        return IndustryStatus(
            industry_version=INDUSTRY_VERSION,
            status=INDUSTRY_CLASSIFICATION_UNAVAILABLE,
            point_in_time_available=False,
            current_classification_available=False,
            detail=(
                f"{POINT_IN_TIME_INDUSTRY_UNAVAILABLE} 且 {INDUSTRY_CLASSIFICATION_UNAVAILABLE}："
                "canonical 快照与本地 TuShare 目录均无行业字段，"
                "Phase 1 的 20 只腾讯快照带 industry 但与 500 只 universe 不重叠到可用程度。"
                "本阶段不做行业中性化，也不用板块冒充行业。"
            ),
        )

    def classify(self, as_of) -> dict[str, str]:  # type: ignore[no-untyped-def]
        raise NotImplementedError(
            "行业分类不可用（POINT_IN_TIME_INDUSTRY_UNAVAILABLE）；"
            "在研究代码里不得用当前行业替代历史 PIT 行业。"
        )


def load_board_map(
    universe_version: str, *, limit_codes: list[str] | None = None,
) -> dict[str, str]:
    """读取 PIT universe 注册簿里的 ``stock_code -> board``（法定板块，非行业）。"""
    factory = get_session_factory()
    with factory() as db:
        stmt = select(
            UniverseMembershipRow.stock_code, UniverseMembershipRow.board,
        ).where(UniverseMembershipRow.universe_version == universe_version)
        if limit_codes:
            stmt = stmt.where(UniverseMembershipRow.stock_code.in_(limit_codes))
        rows = db.execute(stmt).all()
    return {str(code): str(board) for code, board in rows}


def attach_segment(frame: pd.DataFrame, board_map: dict[str, str]) -> pd.DataFrame:
    """追加 ``segment`` 列（板块）。缺失板块返回 ``"unknown"``，不猜测。"""
    out = frame.copy()
    out["segment"] = [
        board_map.get(str(code), "unknown") for code in out["stock_code"].tolist()
    ]
    return out


def segment_neutralize(
    frame: pd.DataFrame,
    value_col: str,
    *,
    date_col: str = "as_of",
    segment_col: str = "segment",
    min_members: int = 3,
) -> pd.DataFrame:
    """按 ``(as_of, segment)`` 做**去均值**，追加 ``segment_neutral_value`` 列。

    仅用于回答"是不是某个板块整体在动"：组内成员少于 ``min_members`` 时该组
    不参与（返回 NaN），因为 2 只股票的平均值没有横截面意义。
    这是板块控制，**不是**行业中性化。
    """
    out = frame.copy()
    grouped = out.groupby([date_col, segment_col], dropna=False)[value_col]
    mean = grouped.transform("mean")
    size = grouped.transform("size")
    neutral = pd.to_numeric(out[value_col], errors="coerce") - mean
    out["segment_neutral_value"] = neutral.where(size >= min_members)
    out["segment_size"] = size
    return out


__all__ = [
    "BOARD_LABELS",
    "CURRENT_INDUSTRY_SENSITIVITY_ANALYSIS",
    "INDUSTRY_CLASSIFICATION_UNAVAILABLE",
    "INDUSTRY_VERSION",
    "POINT_IN_TIME_INDUSTRY_UNAVAILABLE",
    "SEGMENT_CONTROL_BOARD",
    "IndustryClassificationProvider",
    "IndustryStatus",
    "UnavailableIndustryProvider",
    "attach_segment",
    "load_board_map",
    "segment_neutralize",
]
