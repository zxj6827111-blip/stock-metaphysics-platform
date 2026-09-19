"""Phase 3B · 多 Birth Model 定义与构造。

背景（GOAL §3B）
================

股票无真实医学意义的"出生"，但术数研究里需要为每只股票选一个"启示时刻"以排八字/紫微盘。
不同选择会给出**不同的四柱、不同的宫位**——这是 Phase 3B 要系统回答的问题。

本项目 Phase 1 接受 ``listing_open`` 作为"研究基准"，
但从未证明它优于其他选择。Phase 3B 实现 4 个候选，**全部**登记为 ``BirthBasis`` 的一员：

| model_id                  | 定义                                       | 可用性          | 术数差异点 |
|---|---|---|---|
| ``listing_open_v1``       | list_date + 正式开盘时刻（通常 09:30） | ✅ 100%         | 基准 |
| ``listing_close_v1``      | list_date + 正式收盘时刻（通常 15:00） | ✅ 100%         | **时柱不同**（上午 vs 下午） |
| ``ipo_date_approx_v1``    | list_date - 7 自然日（申购日近似）      | ⚠️ 启发式近似  | **日柱可能不同** |
| ``company_foundation_v1`` | 公司成立日                                | ❌ 数据源不可得 | UNAVAILABLE |

不可用的模型**不造数据**——``build`` 返回 ``BirthModelBuild(
  profile=None, status="UNAVAILABLE", reason=...)``，调用方必须显式处理。

版本号协议
==========

每个``BirthModel`` 自带 ``model_version``。落库时写入
``stock_birth_profile.birth_profile_version``，
并通过唯一索引 ``(stock_code, birth_basis, birth_profile_version)`` 区分：
同一股票的 4 个版本并存不冲突。

使用前请阅读 ``AGENTS.md`` 第 5 节"关于股票无性别"——
这些模型都不涉及性别，因此也不会触发运限逻辑变体（``variant_mode=not_applicable``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Shanghai"
_SHANGHAI = ZoneInfo(DEFAULT_TZ)


class BirthModelId(str, Enum):
    """Phase 3B 支持的 4 个 Birth Model（与 ``BirthBasis`` 对齐）。"""

    LISTING_OPEN = "listing_open"
    LISTING_CLOSE = "listing_close"           # Phase 3B 新增：首日收盘
    IPO_DATE_APPROX = "ipo_date"              # 真实 IPO 不可得 → 启发式近似
    COMPANY_FOUNDATION = "company_foundation" # 不可得，UNAVAILABLE


@dataclass(frozen=True)
class BirthModelBuild:
    """``BirthModel.build(...)`` 的统一返回。``profile=None`` 表示不可用。"""

    model_id: BirthModelId
    birth_datetime: datetime | None
    reason: str = ""
    assumptions: tuple[str, ...] = ()
    approximated: bool = False
    data_quality_grade: str = "A"
    data_quality_score: float = 1.0


@dataclass(frozen=True)
class BirthModel:
    """一个 Birth Model 的静态描述。"""

    model_id: BirthModelId
    version: str                 # birth_profile_version 落库后缀
    description: str
    deterministic_from_listing: bool


# ---------------------------------------------------------------------------
# 4 个模型实现
# ---------------------------------------------------------------------------


_BIRTH_MODELS: dict[BirthModelId, BirthModel] = {
    BirthModelId.LISTING_OPEN: BirthModel(
        model_id=BirthModelId.LISTING_OPEN,
        version="v1-phase3b",
        description="上市首日 + 交易所正式开盘时刻（Phase 1 的研究基准）",
        deterministic_from_listing=True,
    ),
    BirthModelId.LISTING_CLOSE: BirthModel(
        model_id=BirthModelId.LISTING_CLOSE,
        version="v1-phase3b",
        description="上市首日 + 交易所正式收盘时刻（时柱与 listing_open 不同）",
        deterministic_from_listing=True,
    ),
    BirthModelId.IPO_DATE_APPROX: BirthModel(
        model_id=BirthModelId.IPO_DATE_APPROX,
        version="v1-phase3b",
        description="IPO 发行日的启发式近似：list_date - 7 自然日（A股新股平均网上申购前置期）",
        deterministic_from_listing=True,
    ),
    BirthModelId.COMPANY_FOUNDATION: BirthModel(
        model_id=BirthModelId.COMPANY_FOUNDATION,
        version="v1-phase3b",
        description="公司成立日期（本项目数据源不可得，标记 UNAVAILABLE）",
        deterministic_from_listing=False,
    ),
}


def list_birth_models() -> list[BirthModel]:
    return list(_BIRTH_MODELS.values())


def get_birth_model(model_id: BirthModelId | str) -> BirthModel:
    mid = model_id if isinstance(model_id, BirthModelId) else BirthModelId(model_id)
    return _BIRTH_MODELS[mid]


def build_birth(
    model_id: BirthModelId,
    *,
    list_date: date | None,
    session_open_time: str | None = None,
    session_close_time: str | None = None,
    tz: ZoneInfo = _SHANGHAI,
) -> BirthModelBuild:
    """对一只股票在一个 model 下构造 birth_datetime。

    Args:
        model_id: 要选哪个模型
        list_date: 上市首日（``pit_universe`` 或 ``stock_master.listing_date``）
        session_open_time / session_close_time: 交易所时段；``None`` 时由
            ``exchange_session_calendar`` 当前生效配置解析（禁止硬编码）
    """
    if session_open_time is None or session_close_time is None:
        from src.core.stock.exchange_sessions import resolve_session
        from src.core.schemas.common import Exchange
        # 用交易所日历的"今日开市/闭市"配置；Phase 3B 多数是 A 股主板/创业/科创
        # 统一 09:30 开 15:00 收。走 resolve_session 保证唯一来源。
        session, _ = resolve_session(Exchange.SSE, "主板", list_date or date.today())
        # ExchangeSession.open_time / close_time 是 ``datetime.time`` 对象
        def _t2s(t) -> str:
            return t.strftime("%H:%M:%S") if hasattr(t, "strftime") else str(t)
        session_open_time = _t2s(session.open_time)
        session_close_time = _t2s(session.close_time)
    if list_date is None:
        return BirthModelBuild(
            model_id=model_id,
            birth_datetime=None,
            reason="stock.master.listing_date 缺失，所有 birth model 均无法构造",
            data_quality_grade="D",
            data_quality_score=0.0,
        )

    mid = model_id
    if mid == BirthModelId.LISTING_OPEN:
        hh, mm, ss = (int(x) for x in session_open_time.split(":"))
        return BirthModelBuild(
            model_id=mid,
            birth_datetime=datetime(
                list_date.year, list_date.month, list_date.day,
                hh, mm, ss, tzinfo=tz,
            ),
            reason="上市首日 + 该交易所开盘时刻",
        )
    if mid == BirthModelId.LISTING_CLOSE:
        hh, mm, ss = (int(x) for x in session_close_time.split(":"))
        return BirthModelBuild(
            model_id=mid,
            birth_datetime=datetime(
                list_date.year, list_date.month, list_date.day,
                hh, mm, ss, tzinfo=tz,
            ),
            reason="上市首日 + 该交易所收盘时刻（与 listing_open 时柱不同）",
            assumptions=("A股新股首日开盘即交易，收盘为当日最后交易时刻",),
        )
    if mid == BirthModelId.IPO_DATE_APPROX:
        approx = list_date - timedelta(days=7)
        return BirthModelBuild(
            model_id=mid,
            birth_datetime=datetime(approx.year, approx.month, approx.day,
                                     9, 30, 0, tzinfo=tz),
            reason=(
                "Phase 3 数据源不含独立 IPO 发行日（TuShare stock_company 需 API、"
                "AKShare 被代理拦截）；采用 list_date - 7 自然日近似（A股新股网上申购期）"
            ),
            assumptions=("IPO 发行日 ≈ 上市日 - 7 自然日（估计）",),
            approximated=True,
            data_quality_grade="C",
            data_quality_score=0.55,
        )
    if mid == BirthModelId.COMPANY_FOUNDATION:
        return BirthModelBuild(
            model_id=mid,
            birth_datetime=None,
            reason=(
                "公司成立日需要工商注册 / TuShare stock_company 接口数据；"
                "当前网络环境 AKShare/TuShare API 不可达，AStockData 未包含该字段。"
                "按 Phase 3 §3B-1 标记 UNAVAILABLE，不伪造。"
            ),
            data_quality_grade="D",
            data_quality_score=0.0,
        )
    raise ValueError(f"未知 birth model: {mid}")  # pragma: no cover


__all__ = [
    "BirthModel",
    "BirthModelBuild",
    "BirthModelId",
    "build_birth",
    "get_birth_model",
    "list_birth_models",
]
