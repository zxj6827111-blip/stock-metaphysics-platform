# Phase 1 实施计划（IMPLEMENTATION_PLAN_PHASE1）

> 本文件由第一会话（Session 1）在读完以下资料后生成：
>
> - `doc/architecture/architecture_v1.md`（总体架构 V1.0）
> - `doc/architecture/two_session_plan_v1.md`（两次会话实施计划 V1.0）
> - `doc/architecture/uiux_spec_v1.md`（UI/UX 完整设计规范 V1.0）
> - `doc/stock_metaphysics_ui_reference_pack_v1_1/.../prompts/ui_round1_prompt.md`
> - `doc/ui-reference/*.png`（11 张 1672×941 视觉真值图，已逐张读取）

---

## 1. 我理解的系统架构

### 1.1 一句话定位

> 第三方库负责"算盘"，自研 Factor Engine 负责"把盘变成可研究变量"，Research 层负责"验证这些变量有没有历史信息量"，
> Knowledge Center 负责"说明古籍依据"，Consensus Engine（Phase 2）负责"判断多模型是否共振或冲突"，
> LLM Narrator（Phase 2）只负责把确定性结果解释成人能读懂的报告。

**本项目不是"算命网站"，是"术数多模型量化研究工作台"。**

### 1.2 分层

```
┌────────────────────────────────────────────────────────────┐
│  apps/web  Next.js 研究终端（Phase1 只做首页/综合研判/八字）  │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTP / OpenAPI
┌───────────────────────────▼────────────────────────────────┐
│  apps/api  FastAPI  Orchestrator（唯一对外出口）             │
└───────────────────────────┬────────────────────────────────┘
                            │
        ┌───────────────────┼────────────────────┬──────────────────┐
        ▼                   ▼                    ▼                  ▼
  core/stock          engines/*             factors/*          research/*
  StockMaster         CalendarEngine        FactorRegistry     labels
  StockBirthProfile   HuangliEngine         bazi factors       event_study
  exchange_session    BaziEngine            huangli factors    validation
                      ZiweiEngine(预留)     (fusion Phase2)    backtest
        │                   │                    │                  │
        └───────────────────┴────────┬───────────┴──────────────────┘
                                     ▼
                          market/*   knowledge/*   db/* (SQLAlchemy+SQLite)
                          AKShare    BM25+古籍     Alembic migrations
```

### 1.3 硬性架构约束（写入 AGENTS.md，Phase 2 不得破坏）

1. 所有术数排盘必须由**确定性代码**产生，禁止 LLM 计算。
2. 第三方库（lunar-python / AKShare / bazi-pro）**只能经 Adapter** 进入系统；
   业务层不得持有第三方对象。
3. 六个核心接口：
   `CalendarEngine`、`HuangliEngine`、`BaziEngine`、`MarketDataProvider`、
   `KnowledgeProvider`、`BacktestProvider`、`MetaphysicsEngine`（抽象基类）。
4. 原始盘面是一等数据：`chart_artifact.raw_chart` 必须落库，可审计。
5. 每个结果记录 `engine_version` / `rule_version` / `birth_profile_version` /
   `config_version`。
6. `as_of` 严格隔离：`as_of` 之后的任何数据不得作为输入特征，
   未来收益只能作为 label。
7. 术数结构只能是**研究因子**；财星 ≠ 股票上涨；三合 ≠ 股票上涨。
8. 模型分歧不得被平均分掩盖（Phase 2 生效，Phase 1 先预留 opinion 契约）。

---

## 2. Phase 1 范围

### 2.1 必须打通的主链路

```
股票代码
 → 股票基础资料（AKShare via MarketDataProvider）
 → 上市日期 / 交易所
 → StockBirthProfile（listing_open + exchange_session_calendar）
 → CalendarEngine（lunar-python adapter）
 → HuangliEngine（raw_huangli）
 → BaziEngine（四柱 + 十神 + 藏干 + 五行 + 旺衰 + 格局 + 喜用忌 + 刑冲合害 + 流年流月）
 → chart_artifact.raw_chart 落库
 → FactorRegistry（B_* / H_* 因子）
 → market_bar_daily（日行情 + 复权 + 沪深300 benchmark）
 → forward return labels（1/5/10/20/60D + max_return/max_drawdown/excess）
 → Event Study
 → 负对照（随机出生日期 / ±7 天 / 随机因子）
 → KnowledgeProvider（古籍条目 + BM25 + 支持证据 / 反证）
 → FastAPI（9 个端点 + OpenAPI）
 → 第一批正式 UI（首页 / 综合研判 / 八字详情，1672×941 1:1 复刻）
 → pytest 全绿 + Playwright UI 测试
 → docs/HANDOFF_PHASE1.md
```

### 2.2 明确不做（Phase 2 范围）

紫微计算引擎、六爻、奇门、AI Narrator、最终 Consensus Engine、最终
ConflictDetector、自动交易、券商接口、会员、支付、多租户、复杂权限、移动端 App。

> **例外说明（重要）**：UI 参考图 `02_integrated_analysis.png` 上存在紫微卡片与共识卡。
> 按用户指令第二十二/二十三条：
> - 生产 runtime：紫微显示 `未启用 / unavailable`，**绝不伪造紫微结果**；
> - `?fixture=ui-reference` 模式下允许使用固定 Mock 紫微数据做**视觉复刻**；
> - Mock **只存在于前端 fixture 模块**，不写入分析数据库。
>
> UI 上出现的 Consensus 评分同理：Phase 1 只做**展示层**的共识/分歧可视化，
> 其数据来源在 fixture 模式为 Mock、在真实模式为后端 `opinion` 契约的只读聚合
> （仅用于 UI 呈现，不构成正式 Consensus Engine）。

### 2.3 交付物清单

| 类别 | 交付物 |
|---|---|
| 代码 | `src/`（core/engines/factors/market/research/knowledge）、`apps/api`、`apps/web`、`services/ziwei-service`（占位） |
| 数据库 | SQLite（14 张表）+ Alembic migration |
| API | 9 个 `/api/v1` 端点 + OpenAPI |
| 因子 | ≥ 40 个真实可计算因子（B_NATAL/B_YEAR/B_MONTH/B_DAY/H_DAY/H_MONTH） |
| 测试 | pytest 套件（含 `test_no_future_data_access`、Golden Cases）+ Playwright UI 流程 |
| UI | 首页 / 综合研判 / 八字详情（1672×941 截图 + reference 对比 notes） |
| 文档 | README / ARCHITECTURE / AGENTS / THIRD_PARTY / docs/{database,api,factor_dictionary,methodology,ui-implementation}.md / HANDOFF_PHASE1.md |
| 部署 | docker-compose.yml、Dockerfile×2、Makefile、统一测试脚本 |

---

## 3. 实施顺序（实际执行顺序）

| # | 步骤 | 产出 |
|---|---|---|
| 1 | 骨架 + git + 依赖锁定 | pyproject/uv.lock、package.json、THIRD_PARTY.md |
| 2 | core schemas | Pydantic v2 领域模型（含 StockBirthProfile / FactorObservation / ChartArtifact） |
| 3 | db | SQLAlchemy 模型 + Alembic migration + 14 张表 |
| 4 | CalendarEngine | lunar-python adapter + Golden Cases |
| 5 | StockBirthProfile | exchange_session_calendar 驱动，禁止硬编码 09:30 |
| 6 | HuangliEngine | raw_huangli + 结构化 schema |
| 7 | BaziEngine | 四柱/十神/藏干/五行/旺衰/格局/喜用忌/刑冲合害/流年流月 |
| 8 | FactorRegistry | 因子定义 + 计算引擎 + 落库 |
| 9 | MarketDataProvider | AKShare adapter + 缓存 + 重试 + 失败降级 |
| 10 | Labels/EventStudy/负对照 | research 层 |
| 11 | KnowledgeProvider | 古籍条目 ingest + BM25 + supporting/counter evidence |
| 12 | FastAPI | 9 端点 + OpenAPI + 结构化错误 |
| 13 | UI 骨架 | tokens + AppShell/Sidebar/TopBar/StockContextBar |
| 14 | 首页 | 1:1 复刻 + Playwright 截图 |
| 15 | 综合研判 | 1:1 复刻 + Playwright 截图 |
| 16 | 八字详情 | 1:1 复刻 + Playwright 截图 |
| 17 | 测试 | pytest 全量 + Playwright UI flow |
| 18 | 文档与交接 | HANDOFF_PHASE1.md |

---

## 4. 技术栈（锁定）

### Backend
- Python 3.12（uv 管理；`pyproject.toml` 要求 `>=3.11`）
- FastAPI + Uvicorn + Pydantic v2
- SQLAlchemy 2.x + Alembic（SQLite 为主库）
- DuckDB + Pandas + NumPy + PyArrow（研究查询）
- lunar-python（历法）
- AKShare（行情，经 adapter）
- jieba + rank-bm25（古籍检索，Phase 1 不引入 FAISS/embedding 以避免
  不可控下载体积；接口已按 `KnowledgeProvider` 抽象，Phase 2 可替换）

### Frontend
- Next.js 15（App Router）+ React 19 + TypeScript
- Tailwind CSS v4
- ECharts（echarts-for-react）
- Zustand

### Testing
- pytest + pytest-asyncio + httpx
- Playwright（UI 1:1 截图 + 核心流程）

### DevOps
- Docker Compose（api / web）
- Makefile

---

## 5. 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| bazi-pro 未 fork，无法锁定 commit | 高 | 见 ADR-0002：Phase 1 使用自研确定性引擎 `SMX-BAZI-NATIVE`，规则全部版本化；`BaziEngine` 保留 `backend` 字段，Phase 2 可挂 bazi-pro adapter 做双引擎对比 |
| 股票无性别但传统顺逆依赖性别 | 高 | `variant_mode ∈ {forward, reverse, both, not_applicable}`，默认 `not_applicable`；顺逆大运**不参与** Phase 1 因子；assumption 强制记录 |
| AKShare 接口不稳定/限流/被墙 | 高 | Adapter 内 retry + 指数退避 + 本地 Parquet/SQLite 缓存 + 结构化错误；不可用时系统降级而非崩溃 |
| 未来数据泄漏 | 极高 | `as_of` 贯穿 market/labels/event_study；专门写 `test_no_future_data_access` |
| 古籍版权 | 中 | 语料只收**公版原文**（民国前刊本），逐条记 `provenance`/`edition`/`license_status` |
| 因子把"财星"当"上涨" | 极高 | factor schema 强制 `direction` + `rule_score` 为**规则分数**而非收益预测；文档反复声明 |
| UI 1:1 与真实数据冲突 | 中 | `?fixture=ui-reference` 固定 Mock；生产 runtime 强制真实 API |
| lunar-python 精度/流派差异 | 中 | Golden Cases 锁行为；引擎版本落库；升级需跑 golden |

---

## 6. 验收点

### 6.1 P0（数据正确 / 无泄漏 / 可追溯 / 解耦 / 测试）

- [ ] `test_no_future_data_access` 通过：`as_of=2020-01-01` 时特征不读 2020-01-02 及以后
- [ ] 所有 `raw_chart` / `raw_huangli` 落 `chart_artifact`，含 `engine_version` / `config_version`
- [ ] 业务层 grep 不到 `import lunar_python` / `import akshare`（只允许在 adapter 内）
- [ ] Golden Cases 覆盖：公历→干支、节气边界、四柱、十神、黄历、流年、流月
- [ ] ≥ 40 个因子，每个有 `factor_id` / `definition` / `rule_version` / `explanation`
- [ ] 标签：`ret_1d/5d/10d/20d/60d`、`max_return_20d`、`max_drawdown_20d`、`excess_return_20d`
- [ ] Event Study + 4 类负对照全部可运行并输出样本数/上涨率/均值/中位数/超额/回撤

### 6.2 P1（API / UI 架构 / UI 1:1）

- [ ] 9 个 API 全部可调用，OpenAPI 可查看，错误结构化
- [ ] UI 组件复用：AppShell/Sidebar/TopBar/StockSearch/StockContextBar/EngineScoreCard/
      ConsensusCard/ConflictCard/DataQualityBadge/BaziChart/HuangliPanel/FactorBadge/
      FactorTable/BacktestMetricCard/EvidenceDrawer
- [ ] 首页 / 综合研判 / 八字详情 三页 1672×941 截图与 reference 结构高度一致
- [ ] 禁止 `background-image: reference.png` / 整页 `<img>`

### 6.3 交接

- [ ] `docs/HANDOFF_PHASE1.md` 完整（commit SHA / 模块 / DB / API / 版本 / 测试 / 已知问题 / ADR / 不破坏契约 / Phase 2 顺序）

---

## 7. 关键假设（Assumptions）

1. **股票出生时间 = 上市首个正式交易日的交易所正式开盘时刻**（`listing_open`），
   时区 `Asia/Shanghai`。这是**研究假设**，不是定论；版本化为 `v1`。
2. 开盘时刻来自 `exchange_session_calendar` 配置表，**不硬编码**；目前配置：
   SSE/SZSE/BSE 上午 09:30，SZSE 创业板/深市集合竞价 09:30 统一按正式连续竞价开盘计。
3. **股票无性别**：`variant_mode` 默认 `not_applicable`，顺逆大运不进入 Phase 1 因子。
4. 格局/喜用忌由自研确定性规则给出，`confidence` 会如实降低，并输出 `warnings`。
5. 因子 `rule_score` 是**传统规则强度分**（0-10），**不是**预期收益率。
6. Phase 1 的 consensus/conflict 仅用于 UI 呈现，正式 Consensus Engine 属 Phase 2。

---

## 8. ADR 索引

- ADR-0001：第三方引擎必须经 Adapter 隔离
- ADR-0002：Phase 1 八字计算使用自研确定性引擎，bazi-pro 作为 Phase 2 可插拔后端
- ADR-0003：股票无性别 → `variant_mode`，默认 `not_applicable`
- ADR-0004：`as_of` 单向时间隔离与未来数据泄漏防护
- ADR-0005：SQLite 主库 + DuckDB/Parquet 研究层
- ADR-0006：UI fixture 模式与生产 runtime 分离
