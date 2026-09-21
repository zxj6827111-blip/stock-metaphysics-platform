"""``/api/v1/system`` 路由：健康检查、引擎状态、数据质量、版本。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.deps import db_session, get_knowledge, get_market
from src.core.config import settings
from src.core.schemas.common import Availability
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.engines.huangli.huangli_engine import HuangliEngine
from src.engines.ziwei.ziwei_engine import ZiweiEngine
from src.factors.registry.definitions import ALL_DEFINITIONS

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health", summary="健康检查")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "phase": settings.phase,
        "time": datetime.now().isoformat(),
    }


@router.get("/engines", summary="引擎状态")
def engines(market=Depends(get_market)) -> dict:
    """列出所有术数引擎的可用性与版本。

    Phase 2 起紫微已实现；其 ``available`` 反映**紫微排盘服务的真实可达性**
    （HTTP 常驻服务或本机 node 子进程）。服务不可用时如实返回 ``false`` 并给出原因，
    **不允许用 0 分或空盘面冒充可用**。
    """
    calendar = CalendarEngine()
    huangli = HuangliEngine()
    bazi = BaziEngine()
    ziwei = ZiweiEngine()

    def _entry(engine, available: bool, reason: str = "") -> dict:
        meta = engine.metadata
        return {
            "engine_id": meta.engine_id,
            "display_name": meta.display_name,
            "available": available,
            "engine_version": meta.engine_version,
            "config_version": meta.config_version,
            "third_party": meta.third_party,
            "third_party_commit": meta.third_party_commit,
            "notes": meta.notes,
            "unavailable_reason": reason,
        }

    return {
        "phase": settings.phase,
        "engines": [
            _entry(calendar, True),
            _entry(huangli, True),
            _entry(bazi, True),
            _entry(
                ziwei,
                ziwei.availability == Availability.OK,
                "" if ziwei.availability == Availability.OK else (
                    f"{ziwei.unavailable_reason()}。紫微相关字段返回 unavailable，"
                    "其余引擎不受影响，也不会以 0 分参与任何聚合。"
                ),
            ),
            {
                "engine_id": "liuyao", "display_name": "六爻引擎", "available": False,
                "engine_version": "", "config_version": "", "third_party": "",
                "third_party_commit": "", "notes": "", "unavailable_reason": "仅预留接口",
            },
            {
                "engine_id": "qimen", "display_name": "奇门遁甲引擎", "available": False,
                "engine_version": "", "config_version": "", "third_party": "",
                "third_party_commit": "", "notes": "", "unavailable_reason": "仅预留接口",
            },
        ],
        "market_provider": market.provider_id,
        "facts": {
            "factor_definitions": len(ALL_DEFINITIONS),
            "birth_profile_version": settings.birth_profile_version,
            "factor_rule_version": settings.factor_rule_version,
            "knowledge_version": settings.knowledge_version,
            "config_version": settings.config_version,
        },
    }


@router.get("/data-quality", summary="数据质量报告")
def data_quality(db: Session = Depends(db_session), market=Depends(get_market),
                 knowledge=Depends(get_knowledge)) -> dict:
    from src.db.models import (
        ClassicalEntryRow,
        FactorObservationRow,
        MarketBarDailyRow,
        StockBirthProfileRow,
        StockMasterRow,
    )

    def _count(model) -> int:  # type: ignore[no-untyped-def]
        return int(db.execute(select(func.count()).select_from(model)).scalar() or 0)

    stocks = _count(StockMasterRow)
    profiles = _count(StockBirthProfileRow)
    bars = _count(MarketBarDailyRow)
    factors = _count(FactorObservationRow)
    entries = _count(ClassicalEntryRow)

    items = [
        {
            "key": "stock_master", "label": "股票基础资料", "count": stocks,
            "grade": "A" if stocks > 0 else "D",
            "note": "来自 MarketDataProvider（AKShare）；离线模式使用内置清单",
        },
        {
            "key": "birth_profile", "label": "出生档案", "count": profiles,
            "grade": "A" if profiles > 0 else "C",
            "note": "listing_open 基准；开盘时刻来自 exchange_session_calendar",
        },
        {
            "key": "market_bar_daily", "label": "日行情", "count": bars,
            "grade": "A" if bars > 1000 else ("B" if bars > 0 else "D"),
            "note": f"行情提供者：{market.provider_id}",
        },
        {
            "key": "factor_observation", "label": "因子观测", "count": factors,
            "grade": "A" if factors > 0 else "C",
            "note": f"因子定义 {len(ALL_DEFINITIONS)} 个，rule_version={settings.factor_rule_version}",
        },
        {
            "key": "classical_entry", "label": "古籍条目", "count": entries,
            "grade": "B" if entries > 0 else "D",
            "note": "公版原文种子语料；Phase 1 未逐字校勘",
        },
    ]

    scores = {"A": 1.0, "B": 0.8, "C": 0.55, "D": 0.25}
    overall = sum(scores[i["grade"]] for i in items) / len(items)
    grade = "A" if overall >= 0.9 else "B" if overall >= 0.75 else "C" if overall >= 0.5 else "D"

    return {
        "overall_grade": grade,
        "overall_score": round(overall, 3),
        "items": items,
        "notes": [
            "Phase 1 尚未接入独立交易日历表，交易日按周末规则 + 行情数据校验。",
            "古籍语料为公版种子数据，正式发布前需完成校勘。",
            "行情数据在第三方不可用时会降级；降级状态会在响应中显式标注。",
        ],
    }


@router.get("/trading-calendar", summary="交易日历覆盖（实测层 / 官方公布层）")
def trading_calendar(exchange: str = "SSE") -> dict:
    """交易日历的三层覆盖状态（只读）。

    刻意把三层分开返回，因为它们回答的是不同的问题：

    * ``observed`` —— 指数**真实成交过**的日期（观测事实，只能到过去）；
    * ``published`` —— 交易所**已公告**的未来开市/休市安排；
    * ``published.boundary_cn`` —— 官方公布到哪一天为止（超出即回答"未知"）。

    "没有未来行情"与"无法确定未来交易日"是两件事：前者是快照边界，
    后者才是数据缺口。这个端点让二者可区分。
    """
    from src.core.stock.trading_calendar import get_trading_calendar_provider

    cal = get_trading_calendar_provider().for_exchange(exchange)
    return {
        **cal.coverage_descriptor(),
        "generator": "scripts/update_trading_calendar.py",
        "third_layer_note_cn": (
            "行情快照末日（data/import/bars）与交易日历是两回事："
            "行情只有已发生的，日历包含交易所已公布的计划。"
        ),
    }


@router.get("/versions", summary="版本信息")
def versions() -> dict:
    """结果可追溯性所需的全部版本号（architecture §72）。"""
    return {
        "app_version": settings.app_version,
        "phase": settings.phase,
        "birth_profile_version": settings.birth_profile_version,
        "calendar_engine_version": settings.calendar_engine_version,
        "huangli_engine_version": settings.huangli_engine_version,
        "bazi_engine_version": settings.bazi_engine_version,
        "factor_rule_version": settings.factor_rule_version,
        "config_version": settings.config_version,
        "knowledge_version": settings.knowledge_version,
        "market_data_version": settings.market_data_version,
        "narrator_prompt_version": "n/a (Phase 2)",
        "fusion_version": "n/a (Phase 2)",
    }


@router.get("/phase1-status", summary="Phase 1 完成度自述")
def phase1_status() -> dict:
    """诚实列出 Phase 1 已实现与未实现项。"""
    return {
        "completed": [
            "CalendarEngine（lunar-python adapter）", "HuangliEngine（raw_huangli 落库）",
            "BaziEngine（自研确定性规则内核）", "StockBirthProfile（exchange_session_calendar 驱动）",
            f"FactorRegistry（{len(ALL_DEFINITIONS)} 个因子）", "MarketDataProvider（AKShare adapter + 缓存 + 降级）",
            "Labels（1/5/10/20/60D + 回撤 + 超额）", "Event Study", "四类负对照",
            "KnowledgeProvider（BM25 + 支持/反证）", "14+ 张表的 SQLite schema + Alembic migration",
            "FastAPI（9+ 端点 + OpenAPI + 结构化错误）", "研究终端 UI（首页 / 综合研判 / 八字详情）",
        ],
        "not_implemented_phase2": [
            "紫微斗数引擎（iztro）", "六爻", "奇门遁甲",
            "正式 ConsensusEngine（当前仅展示层聚合）", "正式 ConflictDetector（当前仅展示层）",
            "AI Narrator（LLM 解释层）", "月度 / 周度时间窗口预测",
            "导出（Markdown / HTML）", "个股级历史验证（当前为因子级事件研究）",
        ],
        "disclaimers": [
            "本系统是研究实验平台，不是荐股系统，也不构成任何投资建议。",
            "传统术数与股票未来收益之间不存在经现代金融科学确认的稳定因果关系。",
            "因子分数是传统规则强度，不是预期收益率。",
        ],
    }
