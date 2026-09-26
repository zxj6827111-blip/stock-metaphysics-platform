"""FastAPI 应用入口。

    股票代码 → 出生档案 → 历法 → 黄历 → 八字 → 因子 → 行情标签 → 事件研究
    → 负对照 → 古籍证据 → API

Phase 1 未实现紫微 / 六爻 / 奇门 / LLM Narrator / 正式 Consensus。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.errors import install_exception_handlers
from apps.api.routers import analysis, knowledge, research, stock_fortune, stocks, system, ten_gods
from src.core.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("smp.api")

DESCRIPTION = """
## 股票玄学多模型研究平台 · Phase 1 API

**这不是荐股系统**，而是一套「传统术数多模型 × 古籍知识库 × 股票历史行情 × 统计回测验证」
的研究平台。

### 已实现（Phase 1）
- 历法引擎（lunar-python adapter）：公历/农历/干支/节气/纳音
- 黄历引擎：建除十二值 / 十二神 / 黄黑道 / 冲煞 / 彭祖百忌
- 八字引擎：四柱 / 藏干 / 十神 / 五行 / 旺衰 / 格局 / 喜用忌 / 刑冲合害 / 流年流月流日
- 股票出生档案（`listing_open`，开盘时刻来自 `exchange_session_calendar`，**不硬编码 09:30**）
- 因子注册表（60+ 个真实可计算因子）
- 行情（AKShare adapter + 缓存 + 重试 + 显式降级）
- 未来收益标签（1/5/10/20/60D + 最大回撤 + 超额收益）
- 事件研究 + 四类负对照（随机出生日 / ±7 天 / 随机因子）
- 古籍知识中心（BM25 + 权威权重 + **支持证据与反证**）

### 明确未实现（Phase 2）
紫微斗数 / 六爻 / 奇门 / AI Narrator / 正式 ConsensusEngine / 冲突检测引擎 / 月周预测 / 导出

### 核心纪律
1. 所有排盘由确定性代码产生，**禁止 LLM 计算**。
2. 第三方库只能经 Adapter 进入，业务层不得直接依赖。
3. 原始盘面（`chart_artifact.raw_chart`）是一等数据，必须落库、可审计。
4. `as_of` 之后的数据**不得**作为输入特征；未来收益只能作为 label。
5. 因子分数是**传统规则强度**，不是预期收益率。财星 ≠ 股票上涨。
6. 不可用字段返回 `unavailable`，**禁止猜测或用 0 冒充**。
"""


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    logger.info("启动 %s %s (phase=%s)", settings.app_name, settings.app_version, settings.phase)
    try:
        from src.db.base import init_db

        init_db()
        logger.info("数据库 schema 已就绪: %s", settings.resolved_database_url)
    except Exception:  # noqa: BLE001
        logger.exception("数据库初始化失败（服务继续启动，相关接口会返回结构化错误）")
    yield
    logger.info("服务停止")


app = FastAPI(
    title=f"{settings.app_name} API",
    description=DESCRIPTION,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_exception_handlers(app)

app.include_router(stocks.router)
app.include_router(analysis.router)
app.include_router(research.router)
app.include_router(ten_gods.router)
app.include_router(stock_fortune.router)
app.include_router(knowledge.router)
app.include_router(system.router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "phase": settings.phase,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "disclaimer": "研究实验平台，不构成任何投资建议。",
    }


def main() -> None:  # pragma: no cover - 运行入口
    import uvicorn

    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=settings.debug)


if __name__ == "__main__":  # pragma: no cover
    main()
