"""``/api/v1/system`` 路由：健康检查、引擎状态、数据质量、版本。"""

from __future__ import annotations

from datetime import datetime

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from apps.api.deps import db_session, get_market
from src.core.config import PROJECT_ROOT, settings
from src.core.schemas.common import Availability
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.engines.huangli.huangli_engine import HuangliEngine
from src.engines.ziwei.ziwei_engine import ZiweiEngine
from src.factors.registry.definitions import ALL_DEFINITIONS
from src.market.status import describe_market_data

router = APIRouter(prefix="/api/v1/system", tags=["system"])
readiness_router = APIRouter(prefix="/api/v2/system", tags=["system"])


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
def data_quality(db: Session = Depends(db_session)) -> dict:
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

    # 状态报告必须能描述 Provider 初始化失败；不要让依赖注入在进入端点前先变成 500。
    market_status = describe_market_data()
    stored_cutoff = db.execute(select(func.max(MarketBarDailyRow.trade_date))).scalar()

    source_rows = db.execute(
        select(StockMasterRow.source, func.count()).group_by(StockMasterRow.source)
    ).all()
    stock_sources = {str(source or "unknown"): int(count) for source, count in source_rows}
    stock_grade = "D" if stocks == 0 or any(
        source in {"synthetic", "synthetic_demo"} for source in stock_sources
    ) else "C"

    profile_rows = db.execute(select(StockBirthProfileRow)).scalars().all()
    complete_profile_metadata = all(
        row.source and row.birth_profile_version and row.data_quality_json
        for row in profile_rows
    )
    profile_grade = "D" if profiles == 0 else "C" if not complete_profile_metadata else "B"

    missing_factor_provenance = int(db.execute(
        select(func.count()).select_from(FactorObservationRow).where(
            or_(FactorObservationRow.engine_version == "", FactorObservationRow.rule_version == "")
        )
    ).scalar() or 0)
    unavailable_factors = int(db.execute(
        select(func.count()).select_from(FactorObservationRow).where(
            FactorObservationRow.availability != "ok"
        )
    ).scalar() or 0)
    factor_grade = (
        "D" if factors == 0 else "C" if missing_factor_provenance or unavailable_factors else "B"
    )

    missing_entry_provenance = int(db.execute(
        select(func.count()).select_from(ClassicalEntryRow).where(
            or_(
                ClassicalEntryRow.source == "",
                ClassicalEntryRow.edition == "",
                ClassicalEntryRow.provenance == "",
                ClassicalEntryRow.license_status != "public_domain",
                ClassicalEntryRow.original_text == "",
            )
        )
    ).scalar() or 0)
    entry_grade = "D" if entries == 0 else "C" if missing_entry_provenance else "B"

    market_grade = market_status.get("data_quality_grade", "unavailable")
    if market_grade not in {"A", "B", "C", "D"}:
        market_grade = "D"
    bar_grade = "D" if bars == 0 and market_status.get("status") == "unavailable" else market_grade

    items = [
        {
            "key": "stock_master", "label": "股票基础资料", "count": stocks,
            "grade": stock_grade,
            "source_distribution": stock_sources,
            "note": "等级取决于来源可追溯状态；记录条数本身不构成质量证明。",
        },
        {
            "key": "birth_profile", "label": "出生档案", "count": profiles,
            "grade": profile_grade,
            "note": "检查来源、版本与质量元数据；未完成逐档案认证前最高为 B。",
        },
        {
            "key": "market_bar_daily", "label": "日行情", "count": bars,
            "grade": bar_grade,
            "source": market_status.get("provider_id"),
            "version": market_status.get("data_version"),
            "cutoff_date": market_status.get("cutoff_date"),
            "stored_cutoff_date": stored_cutoff.isoformat() if stored_cutoff else None,
            "is_degraded": market_status.get("is_degraded"),
            "research_eligible": market_status.get("research_eligible", False),
            "note": "数据等级来自 Provider 来源与认证状态；行数不用于推断质量。",
        },
        {
            "key": "factor_observation", "label": "因子观测", "count": factors,
            "grade": factor_grade,
            "missing_provenance_count": missing_factor_provenance,
            "unavailable_count": unavailable_factors,
            "note": f"因子定义 {len(ALL_DEFINITIONS)} 个，rule_version={settings.factor_rule_version}；按版本与可用性评估。",
        },
        {
            "key": "classical_entry", "label": "古籍条目", "count": entries,
            "grade": entry_grade,
            "missing_provenance_count": missing_entry_provenance,
            "note": "按来源、版本、出处、许可状态检查；文本校勘状态另行披露。",
        },
    ]

    scores = {"A": 1.0, "B": 0.8, "C": 0.55, "D": 0.25}
    overall = min(scores[i["grade"]] for i in items)
    grade = min(items, key=lambda item: scores[item["grade"]])["grade"]

    return {
        "overall_grade": grade,
        "overall_score": round(overall, 3),
        "items": items,
        "market_data": {
            **market_status,
            "stored_cutoff_date": stored_cutoff.isoformat() if stored_cutoff else None,
        },
        "notes": [
            "总等级采用最弱数据项，避免高数量或其他高等级项目掩盖未认证数据。",
            "古籍语料为公版种子数据，正式发布前需完成校勘。",
            "行情快照截止日与数据库已存行情截止日分开展示；未知值保持 null。",
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
    market_status = describe_market_data()
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
        "market_data_version": market_status.get("data_version") or "",
        "market_data_source": market_status.get("provider_id"),
        "market_data_cutoff_date": market_status.get("cutoff_date"),
        "market_data_snapshot_at": market_status.get("snapshot_at"),
        "narrator_prompt_version": "n/a (Phase 2)",
        "fusion_version": "n/a (Phase 2)",
    }


def _migration_status(db: Session) -> dict:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    current = MigrationContext.configure(db.connection()).get_current_revision()
    one_current_head = len(heads) == 1 and current == heads[0]
    return {
        "status": "ready" if one_current_head else "not_ready",
        "required": True,
        "current_revision": current,
        "heads": heads,
        "reason": "" if one_current_head else "数据库迁移版本未到唯一 Alembic head。",
    }


@readiness_router.get("/readiness", summary="实例就绪状态（v2）")
def readiness(response: Response, db: Session = Depends(db_session)) -> dict:
    """分别检查核心数据库/迁移和可降级的紫微/研究数据组件。

    `/api/v1/system/health` 保持为存活探针；本端点才判断当前实例能否接收依赖数据库的请求。
    紫微与研究数据状态独立报告，不会把可降级能力混同为数据库故障。
    """
    try:
        db.execute(text("SELECT 1"))
        database = {"status": "ready", "required": True, "reason": ""}
    except Exception as exc:  # noqa: BLE001 - 返回明确的非就绪组件状态
        database = {
            "status": "not_ready", "required": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    if database["status"] == "ready":
        try:
            migrations = _migration_status(db)
        except Exception as exc:  # noqa: BLE001 - 缺表/多 head/配置错误都必须 fail closed
            migrations = {
                "status": "not_ready", "required": True,
                "current_revision": None, "heads": [],
                "reason": f"{type(exc).__name__}: {exc}",
            }
    else:
        migrations = {
            "status": "blocked", "required": True,
            "current_revision": None, "heads": [],
            "reason": "数据库连接失败，无法核验迁移版本。",
        }

    try:
        ziwei = ZiweiEngine()
        ziwei_available = ziwei.availability == Availability.OK
        ziwei_component = {
            "status": "ready" if ziwei_available else "degraded",
            "required": False,
            "available": ziwei_available,
            "transport": ziwei.transport_name,
            "reason": "" if ziwei_available else ziwei.unavailable_reason(),
        }
    except Exception as exc:  # noqa: BLE001
        ziwei_component = {
            "status": "unavailable", "required": False, "available": False,
            "transport": None, "reason": f"{type(exc).__name__}: {exc}",
        }

    market_status = describe_market_data()
    research_ready = bool(market_status.get("research_eligible"))
    research_component = {
        **market_status,
        "status": "ready" if research_ready else (
            "unavailable" if market_status.get("status") == "unavailable" else "not_certified"
        ),
        "required": False,
        "reason": "" if research_ready else "当前行情来源尚未具备已认证研究范围。",
    }

    core_ready = database["status"] == "ready" and migrations["status"] == "ready"
    optional_ready = ziwei_component["status"] == "ready" and research_component["status"] == "ready"
    overall_status = "not_ready" if not core_ready else "ready" if optional_ready else "degraded"
    response.status_code = 200 if core_ready else 503
    return {
        "status": overall_status,
        "ready": core_ready,
        "checked_at": datetime.now().isoformat(),
        "components": {
            "database": database,
            "migrations": migrations,
            "ziwei_service": ziwei_component,
            "research_data": research_component,
        },
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
