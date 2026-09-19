# HANDOFF_PHASE1 · 股票玄学多模型研究平台

> **Phase 1.1 已合并（2026-09-19）**：本文档主体保持 Phase 1 交付原貌，
> 但以下内容已被 Phase 1.1 更新取代，**详阅 [`docs/PHASE1_ACCEPTANCE_REPORT.md`](PHASE1_ACCEPTANCE_REPORT.md) 再做判断**：
>
> | Phase 1 原文 | Phase 1.1 现状 |
> |---|---|
> | §12.2「节假日上市会错误对齐」（无交易日历表） | **已修**：`src/core/stock/trading_calendar.py` + 实测日历（由指数真实 K 线推导） |
> | §12.2「/analysis/{id}/backtest 每次重算全库标签」 | **已修**：`forward_label` 表落库 + 幂等 upsert |
> | §13「需 fork bazi-pro」 | **已裁决**：不接入（ADR-0008，许可证不可核实）；自研内核为 Canonical |
> | 合成数据语义仅日志警告 | **已加固**：`research_status` 状态机 + UI 显著横幅 |



> **给第二个 AI 会话（Phase 2）的完整交接文档。**
>
> Phase 2 的任务是「Multi-Engine Productization」：
> 紫微斗数、多模型共识与分歧、正式完整 UI、AI 解释、月/周时间窗口、导出。
>
> **在写任何代码之前，请先读完本文档 + `README.md` + `ARCHITECTURE.md` + `AGENTS.md` + `THIRD_PARTY.md`。**
>
> Phase 1 建立了稳定底座；Phase 2 **不得推翻**本文档「§10 不得破坏的契约」中列出的接口与语义。

---

## 目录

1. [当前 commit SHA 与代码规模](#1-当前-commit-sha-与代码规模)
2. [当前目录结构](#2-当前目录结构)
3. [已完成模块](#3-已完成模块)
4. [未完成模块](#4-未完成模块)
5. [数据库](#5-数据库)
6. [API](#6-api)
7. [第三方依赖版本](#7-第三方依赖版本)
8. [bazi-pro commit 状态](#8-bazi-pro-commit-状态)
9. [测试结果](#9-测试结果)
10. [Golden Cases](#10-golden-cases)
11. [UI 完成页面与尚未完成页面](#11-ui-完成页面与尚未完成页面)
12. [已知 Bugs](#12-已知-bugs)
13. [已知技术债](#13-已知技术债)
14. [关键 assumptions](#14-关键-assumptions)
15. [关键 ADR](#15-关键-adr)
16. [不得破坏的契约](#16-不得破坏的契约)
17. [Phase 2 建议实施顺序](#17-phase-2-建议实施顺序)
18. [启动与验收命令速查](#18-启动与验收命令速查)

---

## 1. 当前 commit SHA 与代码规模

| 项 | 值 |
|---|---|
| **当前 commit SHA** | `7d4067f10b5c66a71aea28157d12e2338c3773a8` |
| commit message | `Phase 1: foundation & bazi research loop` |
| 分支 | `master` |
| 文件总数（git tracked） | 293 |
| Python 文件 | ~75 |
| TypeScript/TSX 文件 | ~35 |
| 文档（Markdown） | ~20 |

> Python 代码规模：`src/` + `apps/api/` 约 9800 行；
> 前端 `apps/web/`（不含 node_modules）约 5200 行；
> 测试 `tests/` 约 3400 行。

---

## 2. 当前目录结构

```
stock-metaphysics-platform/
├── README.md                      ← 项目总览（必读）
├── ARCHITECTURE.md                ← 技术架构（必读）
├── AGENTS.md                      ← AI 强制规则（必读）
├── THIRD_PARTY.md                 ← 依赖与许可证
├── Makefile                       ← 统一命令入口
├── docker-compose.yml
├── pyproject.toml                 ← Python 依赖（已锁版本）
├── alembic.ini                    ← ⚠️ 必须保持纯 ASCII（GBK 解码问题）
│
├── doc/                           ← 用户提供的原始设计资料（只读）
│   ├── architecture/
│   │   ├── architecture_v1.md
│   │   ├── two_session_plan_v1.md
│   │   └── uiux_spec_v1.md
│   ├── ui-reference/*.png         ← 11 张 1672×941 视觉真值
│   └── stock_metaphysics_ui_reference_pack_v1_1/
│
├── docs/                          ← 本项目产出的文档
│   ├── IMPLEMENTATION_PLAN_PHASE1.md
│   ├── HANDOFF_PHASE1.md          ← 本文档
│   ├── database.md
│   ├── api.md
│   ├── factor_dictionary.md       ← 65 个因子完整定义（1437 行）
│   ├── methodology.md
│   ├── ui-implementation.md
│   └── ADR/
│       ├── README.md
│       ├── ADR-0001-adapter-isolation.md
│       ├── ADR-0002-bazi-engine-backend.md
│       ├── ADR-0003-no-gender-variant-mode.md
│       ├── ADR-0004-as-of-time-isolation.md
│       ├── ADR-0005-sqlite-duckdb-storage.md
│       ├── ADR-0006-ui-fixture-mode.md
│       └── ADR-0007-red-up-green-down.md
│
├── apps/
│   ├── api/                       ← FastAPI
│   │   ├── main.py                （应用入口 + OpenAPI 描述）
│   │   ├── deps.py                （依赖注入 + as_of 解析）
│   │   ├── errors.py              （统一结构化错误）
│   │   ├── routers/
│   │   │   ├── stocks.py          （4 端点）
│   │   │   ├── analysis.py        （10 端点）
│   │   │   ├── research.py        （6 端点）
│   │   │   ├── knowledge.py       （5 端点）
│   │   │   └── system.py          （5 端点）
│   │   └── Dockerfile
│   └── web/                       ← Next.js 15
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── globals.css        （Design Tokens）
│       │   ├── page.tsx           （首页 01_home）
│       │   ├── stock/[code]/
│       │   │   ├── overview/page.tsx   （综合研判 02）
│       │   │   ├── bazi/page.tsx       （八字详情 03）
│       │   │   └── {huangli,ziwei,timeline,backtest,evidence,conflicts}/page.tsx  （占位）
│       │   └── {research,factors,settings}/page.tsx （占位）
│       ├── components/
│       │   ├── shell/    （AppShell / TopBar / Sidebar / Icons / Phase2Placeholder）
│       │   ├── cards/    （Card 基元 + EngineScoreCard / ConsensusCard / ConflictCard /
│       │   │              DataQualityBadge / BacktestMetricCard / EvidenceRow）
│       │   ├── stock/    （StockSearch / StockContextBar）
│       │   ├── bazi/     （BaziChart / WuxingDistribution / FateSummary / TimeStructure）
│       │   ├── huangli/  （HuangliPanel）
│       │   ├── factor/   （FactorBadge / FactorList / FactorTable / FactorDisclaimer）
│       │   ├── charts/   （TimeWindowChart / DistributionChart / MiniTrend）
│       │   └── evidence/ （EvidenceDrawer）
│       ├── lib/          （api.ts / dataSource.ts / types.ts / fixture.ts）
│       ├── e2e/          （core-flow.spec.ts / layout.spec.ts）
│       ├── scripts/      （capture-screenshots.mjs）
│       └── artifacts/ui-review/   （截图对比产物）
│
├── src/
│   ├── core/
│   │   ├── constants.py           ← 干支/五行/十神/藏干/刑冲合害静态表（自持）
│   │   ├── config.py              ← Settings（SMP_* 环境变量）
│   │   ├── cli.py                 ← seed / research / analyze / doctor
│   │   ├── schemas/               ← Pydantic 领域模型（common/calendar/bazi/stock/
│   │   │                            factor/market/knowledge/analysis）
│   │   ├── stock/                 ← codes.py / exchange_sessions.py / birth_profile.py
│   │   └── orchestration/         ← analysis_service.py（唯一业务入口）
│   ├── engines/
│   │   ├── base.py                ← MetaphysicsEngine 抽象基类 + EngineMetadata
│   │   ├── calendar/              ← CalendarEngine（lunar-python adapter）
│   │   ├── huangli/               ← HuangliEngine
│   │   ├── bazi/                  ← BaziEngine + rules.py（规则内核）
│   │   └── ziwei|liuyao|qimen/    ← 空目录占位（Phase 2）
│   ├── factors/
│   │   └── registry/              ← definitions.py（65 因子）+ compute.py
│   ├── market/
│   │   ├── providers/             ← base / akshare_provider / synthetic
│   │   └── normalization/         ← frames.py / errors.py
│   ├── research/
│   │   ├── labels/                ← forward_returns.py
│   │   ├── event_study/           ← engine.py
│   │   ├── validation/            ← negative_controls.py
│   │   ├── backtest/              ← provider.py
│   │   └── pipeline.py            ← 端到端研究流水线
│   ├── knowledge/
│   │   ├── ingest/                ← loader.py
│   │   └── retrieval/             ← provider.py（BM25 + 反证）
│   ├── db/                        ← base.py（引擎/会话）+ models.py（16 表）
│   └── narrator/                  ← 空目录占位（Phase 2）
│
├── services/ziwei-service/        ← 空目录占位（Phase 2，iztro adapter）
├── knowledge/bazi/classical_seed.json   ← 古籍语料（7 本 43 条，公版）
├── config/exchange_session_calendar.json ← 交易所交易时段（开盘时刻唯一来源）
├── migrations/                    ← Alembic（1 个 initial migration）
├── tests/                         ← 368 项测试
│   ├── conftest.py
│   ├── engines/    （calendar / huangli / bazi）
│   ├── factors/    （factor_calculation）
│   ├── research/   （labels / event_study / negative_controls）
│   ├── market/     （normalization）
│   ├── knowledge/  （retrieval）
│   ├── golden/     （golden_cases）
│   ├── integration/（api）
│   ├── test_birth_profile.py
│   ├── test_no_future_data_access.py   ← P0
│   └── test_third_party_isolation.py   ← 架构约束机器校验
└── data/                          ← SQLite / Parquet（gitignore）
```

---

## 3. 已完成模块

### 3.1 引擎层

| 模块 | 状态 | 说明 |
|---|---|---|
| `MetaphysicsEngine` 抽象基类 | ✅ | `calculate_chart` / `extract_factors` / `explain_rules` / `build_evidence_query` / `score` |
| `CalendarEngine` | ✅ | lunar-python 1.4.8 adapter；输出 `CalendarSnapshot` |
| `HuangliEngine` | ✅ | 依赖 CalendarEngine；含多日扫描（上限 400 天） |
| `BaziEngine` | ✅ | 自研内核 `smx-bazi-native-1.0.0` + `rules.py` 纯函数规则 |
| `ZiweiEngine` | ❌ | 空目录占位 |
| `LiuyaoEngine` / `QimenEngine` | ❌ | 空目录占位 |

### 3.2 八字输出字段（全部已实现）

年柱 / 月柱 / 日柱 / 时柱 / 藏干（含本气中气余气与权重）/ 十神（天干+藏干）/
纳音 / 五行力量（估算）/ 日主 / 旺衰（得令得地得势 + 帮扶占比 + 等级 + 置信度）/
格局（月令本气/透干取格 + 候选列表 + 置信度）/ 喜神 / 用神 / 忌神 / 仇神 / 闲神 /
调候说明 / 刑冲合害（六合/三合/三会/半合/六冲/相刑/相害/天干五合/天干相冲）/
流年 / 流月 / 流日（含十神、十二长生、与原局互动、喜忌归类）/
胎元 / 命宫 / 身宫 / 胎息 / `variant_mode` / `da_yun`（默认空）/ assumptions / warnings

### 3.3 因子体系

**65 个因子**（远超要求的 30–50）：

| 前缀 | 数量 | 内容 |
|---|---|---|
| `B_NATAL_` | 18 | 原局结构 |
| `B_YEAR_` | 10 | 流年 |
| `B_MONTH_` | 12 | 流月 |
| `B_DAY_` | 8 | 流日 |
| `H_DAY_` | 12 | 黄历 × 原局 |
| `H_MONTH_` | 5 | 黄历月度聚合 |

### 3.4 行情与研究层

| 模块 | 状态 |
|---|---|
| `MarketDataProvider` 抽象 | ✅ |
| `AkshareMarketProvider` | ✅ 含 retry×3 + 指数退避 + SQLite 缓存 + 降级链 |
| `SyntheticMarketProvider` | ✅ 确定性合成（seed=hash(code)），显式标注降级 |
| 列归一化 / 异常检测 / `clip_to_as_of` | ✅ |
| 结构化错误（5 类） | ✅ |
| 未来收益标签（1/5/10/20/60D + 回撤 + 超额 + 四种上涨定义） | ✅ |
| Event Study（activation 语义 + 多持有期 + 过滤条件） | ✅ |
| 四类负对照（随机出生日 / ±7 天 / 随机因子） | ✅ |
| `ResearchPipeline`（面板构建 + 事件研究 + 负对照） | ✅ |
| `BacktestProvider` 抽象 + 本地实现 | ✅ |

### 3.5 古籍知识中心

| 模块 | 状态 |
|---|---|
| 语料（7 本 43 条，全部公版） | ✅ |
| `KnowledgeProvider`（BM25 + 主题匹配 + 权威权重 + 域过滤） | ✅ |
| **支持证据 + 反证的强制分类** | ✅ |
| `classical_book` / `classical_entry` / `evidence_link` 落库 | ✅ |

### 3.6 其他

| 模块 | 状态 |
|---|---|
| `StockBirthProfile`（listing_open + exchange_session_calendar） | ✅ |
| `variant_mode`（股票无性别） | ✅ |
| 16 张表 + Alembic migration | ✅ |
| FastAPI 30 端点 + OpenAPI + 结构化错误 | ✅ |
| CLI（seed / research / analyze / doctor） | ✅ |
| Docker Compose + Dockerfile ×2 + Makefile | ✅ |
| 测试 368 项（pytest）+ 40 项（Playwright） | ✅ |
| UI 三页 1:1 复刻 + 截图对比 notes | ✅ |

---

## 4. 未完成模块

| 模块 | 状态 | 阻塞/依赖 |
|---|---|---|
| **紫微斗数引擎** | ❌ 完全未实现 | 需要 iztro + TS service |
| **六爻** | ❌ 仅目录占位 | Phase 2/3 |
| **奇门遁甲** | ❌ 仅目录占位 | Phase 2/3 |
| **正式 ConsensusEngine** | ❌ 仅展示层聚合（`display_only: true`） | 依赖紫微接入 |
| **正式 ConflictDetector** | ❌ 仅展示层快照 | 依赖紫微接入 |
| **AI Narrator（LLM 解释）** | ❌ `src/narrator/` 空目录 | 应最后做 |
| **月度 / 周度时间窗口预测** | ❌ 仅展示层示意曲线 | 需流日因子聚合 + 版本化 |
| **导出（Markdown / HTML）** | ❌ 按钮置灰 | — |
| **因子字典页 / 研究实验室页 / 设置页** | ❌ 占位页 | 后端已就绪 |
| **黄历详情页 / 历史验证页 / 古籍证据页 / 模型分歧页** | ❌ 占位页 | 后端已就绪 |
| **真实收益分布图** | ⚠️ 正态近似（图注已标"示意"） | 需后端返回分箱数据 |
| **交易日历表** | ❌ 未建 | 交易日仅按周末规则 + 行情校验 |
| **标签落库** | ❌ 每次请求重算 | 性能问题 |
| **样本外验证 / IC / 行业中性化** | ❌ 未实现 | 研究方法层 |
| **退市股票处理（生存者偏差）** | ❌ 未处理 | — |
| **多用户 / 权限 / 会员 / 支付** | ❌ 不需要（研究系统） | — |

---

## 5. 数据库

主库：**SQLite**（`data/smp.sqlite3`，已启用 `foreign_keys=ON` + `WAL`）
Migration：**Alembic**（`migrations/versions/a2b7e06fb0ad_phase1_initial_schema.py`）

**16 张业务表 + `alembic_version`**：

| 分组 | 表 |
|---|---|
| 股票 | `stock_master`、`stock_birth_profile`、`exchange_session_calendar` |
| 行情 | `market_bar_daily`、`market_fetch_log` |
| 引擎 | `engine_version`、`engine_run`、`chart_artifact` |
| 因子 | `factor_definition`、`factor_observation` |
| 古籍 | `classical_book`、`classical_entry`、`evidence_link` |
| 研究 | `backtest_experiment`、`backtest_result` |
| 编排 | `analysis_run` |

**关键唯一约束**：

* `stock_birth_profile`：`(stock_code, birth_basis, birth_profile_version)` —— 切基准生成新行，不覆盖历史
* `exchange_session_calendar`：`(exchange, board, session_name, effective_from)`
* `market_bar_daily`：`(stock_code, trade_date, adjust)`
* `factor_observation`：`(stock_code, as_of, factor_id, rule_version)`
* `factor_definition`：`(factor_id, rule_version)`
* `engine_version`：`(engine_id, engine_version)`

字段详情见 [`docs/database.md`](database.md)。

---

## 6. API

**30 个端点**，完整定义见 [`docs/api.md`](api.md) 或 `/docs`。

### 6.1 two_session_plan §16 要求的 9 个端点（全部可用）

| 方法 | 路径 |
|---|---|
| GET | `/api/v1/stocks/search` |
| GET | `/api/v1/stocks/{code}` |
| POST | `/api/v1/stocks/{code}/birth-profile` |
| POST | `/api/v1/stocks/{code}/analysis/bazi` |
| GET | `/api/v1/analysis/{id}/charts/bazi` |
| GET | `/api/v1/analysis/{id}/huangli` |
| GET | `/api/v1/analysis/{id}/factors` |
| GET | `/api/v1/analysis/{id}/backtest` |
| GET | `/api/v1/analysis/{id}/evidence` |

### 6.2 Phase 1 额外提供的端点

```
GET  /api/v1/analysis/{analysis_id}                    分析运行上下文
GET  /api/v1/analysis/{analysis_id}/consensus          展示层共识快照
GET  /api/v1/analysis/{analysis_id}/conflicts          展示层分歧快照
GET  /api/v1/analysis/{analysis_id}/guide              引擎可用性说明
GET  /api/v1/stocks/{code}/birth-profile/compare       出生基准对比
GET  /api/v1/factor-dictionary                         因子字典

POST /api/v1/research/run                              端到端研究流水线
GET  /api/v1/research/labels/{code}                    个股未来收益标签
GET  /api/v1/research/experiments                      实验列表
GET  /api/v1/research/experiments/{experiment_id}      实验详情
GET  /api/v1/research/factor-definitions               因子定义（研究向）

GET  /api/v1/knowledge/books                           古籍书目
GET  /api/v1/knowledge/entries                         古籍条目
POST /api/v1/knowledge/search                          证据检索（含反证）
GET  /api/v1/knowledge/by-factors                      按因子检索证据
GET  /api/v1/knowledge/stats                           知识库统计

GET  /api/v1/system/health                             健康检查
GET  /api/v1/system/engines                            引擎状态
GET  /api/v1/system/data-quality                       数据质量报告
GET  /api/v1/system/versions                           版本信息
GET  /api/v1/system/phase1-status                      Phase 1 完成度自述
```

### 6.3 错误码

```
VALIDATION_ERROR             422   参数校验失败
INVALID_REQUEST              422   业务参数非法
BIRTH_PROFILE_ERROR          422   出生档案无法构造
STOCK_NOT_FOUND              404
NOT_FOUND                    404
MARKET_INSUFFICIENT_DATA     422
MARKET_PROVIDER_UNAVAILABLE  503   含 detail，retryable=true
FUTURE_DATA_ACCESS           500   P0，不可重试
INTERNAL_ERROR               500
```

---

## 7. 第三方依赖版本

### 7.1 核心（术数与数据）

| 依赖 | 版本 | 位置 | 许可证 |
|---|---|---|---|
| **lunar-python** | **1.4.8** | `src/engines/calendar/`、`src/engines/bazi/` | MIT |
| **AKShare** | **1.18.96** | `src/market/providers/akshare_provider.py` | MIT |
| **bazi-pro** | **未接入** | — | **未核实** |

### 7.2 Python

```
fastapi 0.141.1        uvicorn 0.53.0        pydantic 2.13.5
pydantic-settings 2.15.0                     python-multipart 0.0.32
sqlalchemy 2.0.54      alembic 1.20.0
numpy 2.5.3            pandas >=2.3,<3.0     pyarrow 25.0.1   duckdb 1.5.5
jieba 0.42.1           rank-bm25 0.2.2
tenacity 9.1.4         httpx 0.28.1          orjson 3.12.0
pytest 9.1.1           pytest-asyncio 1.4.0  pytest-cov 7.1.0
```

> ⚠️ **pandas 锁定在 2.x**：3.0 存在大量 breaking change，Phase 1 不冒险升级。

### 7.3 Node.js

```
next 15.5.25           react 19.3.0          react-dom 19.3.0
echarts 6.1.0          echarts-for-react 3.0.6
zustand 5.0.x          tailwindcss 4.3.3     @tailwindcss/postcss 4.3.3
typescript 5.9.x       @playwright/test 1.63.0
```

> **未引入第三方图标库**（`components/shell/Icons.tsx` 为内联 SVG）。

完整清单与许可证见 [`THIRD_PARTY.md`](../THIRD_PARTY.md)。

---

## 8. bazi-pro commit 状态

| 项 | 值 |
|---|---|
| **是否已 fork** | ❌ **否** |
| **是否锁定 commit SHA** | ❌ **否** |
| 当前使用的八字引擎 | **自研 `smx-bazi-native-1.0.0`** |
| 决策文档 | [`docs/ADR/ADR-0002`](ADR/ADR-0002-bazi-engine-backend.md) |

**原因**：

1. 启动 Phase 1 时仓库中没有 bazi-pro 的 fork；
2. `new1234cq/bazi-pro` 的 README/版权/提交历史大量指向原作者 `Minervaowl7/bazi-pro`，
   无法确认账号关系；
3. **许可证未核实**（商用前必须核实）；
4. 无法在不联网核实的情况下"锁定一个明确 commit"。

**Phase 2 必须完成**：

```
1. fork bazi-pro 到自有组织 → 核实许可证 → 锁定 commit SHA
2. 实现 BaziProAdapter（只经 BaziEngine 接口调用，不复制源码）
3. 与 smx-bazi-native 并行计算同一批 Golden Case
4. 差异逐条写入 docs/calculation-differences.md
5. 若 bazi-pro 更可靠则替换，并提升 bazi_engine_version
6. 保留自研内核作为 fallback
```

---

## 9. 测试结果

### 9.1 后端（pytest）

```
$ PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q
368 passed, 1 warning in 37.08s
```

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `tests/engines/test_calendar_engine.py` | 18 | 干支/节令边界/农历/黄历字段/鲁棒性 |
| `tests/engines/test_huangli_engine.py` | 12 | 黄历字段/raw_huangli/多日窗口 |
| `tests/engines/test_bazi_engine.py` | 51 | 四柱/藏干/十神/纳音/五行/旺衰/格局/喜用忌/刑冲合害/时间流/无性别契约 |
| `tests/test_birth_profile.py` | 38 | 代码规范化/时段解析/出生档案/无性别/其他基准/落库结构 |
| `tests/factors/test_factor_calculation.py` | 24 | 注册表完整性/因子计算/不可用契约/方向语义/可复现性 |
| `tests/market/test_normalization.py` | 25 | 列归一化/异常检测/裁剪/合成行情诚实性/结构化错误/降级链 |
| `tests/research/test_labels.py` | 22 | 各持有期/路径指标/超额收益/四种上涨定义/数据不足 |
| `tests/research/test_event_study.py` | 25 | 统计量/过滤/activation/多因子逻辑/辅助分析 |
| `tests/research/test_negative_controls.py` | 20 | 四类对照/判定诚实性/汇总/birth transforms |
| `tests/knowledge/test_retrieval.py` | 27 | 语料完整性/版权/分词/检索/反证/域过滤/权威权重 |
| `tests/golden/test_golden_cases.py` | 36 | 8 组干支/5 组节气/结构性不变量/四柱/十神/黄历/时间流/复现性/出生档案 |
| `tests/integration/test_api.py` | 42 | 30 个端点 + 错误结构 + 落库可追溯 + 紫微不伪造 |
| `tests/test_no_future_data_access.py` | 16 | **P0** 哨兵污染 + 反向对照 + 结构隔离 |
| `tests/test_third_party_isolation.py` | 17 | **架构约束机器校验** |

### 9.2 前端（Playwright）

```
$ cd apps/web && npx playwright test
40 passed (31.3s)
```

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `e2e/core-flow.spec.ts` | 31 | 三页渲染/搜索交互/四柱盘 DOM/五行条/因子 ID/免责声明/证据抽屉/无控制台错误/9 个占位页/紫微不伪造 |
| `e2e/layout.spec.ts` | 9 | 1672×941 与 1440×900 无横向溢出/侧栏尺寸/设计令牌生效 |

### 9.3 复现测试命令

```bash
make test          # 后端 368 项
make test-ui       # 前端 40 项（需 web 已启动）
make test-leak     # 仅 P0 防泄漏测试
make test-golden   # 仅 Golden Cases
make check         # typecheck + lint
```

> ⚠️ **Playwright 前置条件**：需先 `npx next build && npx next start -p 3000`。
> 只跑 `npm run dev` 也可以，但生产构建更接近截图验收环境。

---

## 10. Golden Cases

`tests/golden/test_golden_cases.py`，**36 个用例**，锁定 lunar-python 1.4.8 的行为。

### 10.1 干支（8 组）

| 日期时刻 | 年柱 | 月柱 | 日柱 | 时柱 | 备注 |
|---|---|---|---|---|---|
| 2001-08-27 09:30 | 辛巳 | 丙申 | 壬戌 | 乙巳 | 贵州茅台上市时刻（**手工验证**） |
| 1991-04-03 09:30 | 辛未 | 辛卯 | 癸卯 | 丁巳 | 平安银行上市时刻 |
| 2018-06-11 09:30 | 戊戌 | 戊午 | 甲戌 | 己巳 | 宁德时代上市时刻 |
| 2000-01-01 00:00 | 己卯 | 丙子 | 戊午 | 壬子 | 千禧年零点（**锚点日**） |
| 1984-02-02 12:00 | 癸亥 | 乙丑 | 丙寅 | 甲午 | 甲子年起点前 |
| 2024-02-04 20:00 | 甲辰 | 丙寅 | 戊戌 | 壬戌 | 2024 立春后 |
| 2024-02-04 10:00 | 癸卯 | 乙丑 | 戊戌 | 丁巳 | 2024 立春前 |
| 1999-12-31 23:30 | 己卯 | 丙子 | 戊午 | 壬子 | 跨年夜子时（晚子时归次日） |

**锚点手工验证**：以 2000-01-01 = 戊午日为锚，闰年 366 + 238 = 604 天，604 mod 60 = 4，
戊+4 = 壬、午+4 = 戌 → 壬戌日，与期望一致。时柱用五鼠遁独立验证（丁壬起庚子，壬日巳时 = 乙巳）。

### 10.2 节气边界（5 组 + 立春专项）

惊蛰 / 清明 / 立秋 / 立冬 / 大雪 当日必须换月；立春当日必须换年（癸卯→甲辰）且月柱同时变（乙丑→丙寅）。

### 10.3 结构性不变量（4 项，比逐点期望值更强）

| 测试 | 检验 |
|---|---|
| `test_day_pillar_advances_through_60_jiazi` | 连续 120 天日柱严格 +1 天干 +1 地支 |
| `test_year_pillar_changes_exactly_once_per_year` | 2024 年年柱只变 1 次，且在 2 月 |
| `test_month_pillar_changes_exactly_12_times` | 2024 年月柱变 12 次 |
| `test_hour_pillar_uses_five_rats_rule` | 五鼠遁时干映射正确 |

> **这四项能捕获"整体错位一天"这类系统性错误，不要删除。**

### 10.4 其他 Golden Case

四柱完整装配（含胎元/命宫）、十神、黄历字段、流年/流月/流日、
复现性（同输入 3 次调用结果一致）、版本号锁定、5 只代表股票的出生档案。

### 10.5 Golden Case 失败时怎么办

**不要直接改期望值。** 见 [`AGENTS.md`](../AGENTS.md) §12：

```
1. 判断：库升级导致的口径变化，还是代码 bug？
2. bug → 修代码
3. 口径变化 → 写 docs/calculation-differences.md → 提升 engine_version → 重新生成期望值 → 全量回归
```

---

## 11. UI 完成页面与尚未完成页面

### 11.1 已完成（1:1 复刻，1672×941）

| 页面 | 路由 | 参考图 | 实现 | 截图 |
|---|---|---|---|---|
| 首页 | `/` | `01_home.png` | `app/page.tsx` | `apps/web/artifacts/ui-review/01-home/` |
| 综合研判 | `/stock/[code]/overview` | `02_integrated_analysis.png` | `app/stock/[code]/overview/page.tsx` | `.../02-overview/` |
| 八字详情 | `/stock/[code]/bazi` | `03_bazi_detail.png` | `app/stock/[code]/bazi/page.tsx` | `.../03-bazi/` |

每个目录含 `reference.png` / `current.png` / `notes.md`（已匹配 / 仍有差异 / 下一轮调整）。

### 11.2 占位页（明确说明未实现，非 404）

```
/stock/[code]/huangli      后端已就绪，UI 属第二轮
/stock/[code]/ziwei        引擎未实现
/stock/[code]/timeline     Phase 2
/stock/[code]/backtest     Phase 2
/stock/[code]/evidence      Phase 2
/stock/[code]/conflicts    Phase 2
/research                  后端已就绪
/factors                   后端已就绪
/settings                  Phase 2
```

### 11.3 尚未实现（参考图编号）

`04_ziwei_detail` / `05_backtest_validation` / `06_factor_dictionary` /
`07_model_conflict_center` / `08_huangli_detail` / `09_classics_evidence_search` /
`10_time_window`

### 11.4 UI 已知视觉差异

见各页 `notes.md`。摘要：

| 页面 | 主要差异 |
|---|---|
| 01 首页 | 右侧罗盘纹样用同心圆近似；走势缩略图为平滑曲线；字体跨平台差异 |
| 02 综合研判 | **紫微卡在生产模式显示"未启用"（有意为之）**；时间窗口曲线为展示层外推；收益分布为正态近似；标题区右侧缺竖排装饰 |
| 03 八字详情 | 参考图的因子 ID 命名（`B_STRUCT_002` 等）与实际因子体系（`B_NATAL_*`）不同；四柱表多一行"长生"；古籍证据为列表行而非书脊卡片 |

### 11.5 复刻验收流程

```bash
make web-build && npx next start -p 3000
make shots          # fixture 模式，输出 current.png + capture-report.json
make shots-live     # 真实 API 模式
```

---

## 12. 已知 Bugs

### 12.1 已修复（保留记录，避免重蹈）

| # | 问题 | 位置 | 修复 |
|---|---|---|---|
| 1 | **负对照全部输出 tie**：对照组传入了空观测，导致对照永远 0 样本 | `src/research/validation/negative_controls.py` | 改为传入"用平移/随机出生时间重算的因子观测"二元组 |
| 2 | **负对照仍全部 tie**：事件定义是"因子被计算过"，真实组与对照组事件集合完全相同 | `src/research/event_study/engine.py` | 引入 `activation` 语义（默认 `nonzero`：`normalized_value != 0` 才算结构成立） |
| 3 | **超额收益/回撤在所有持有期重复出现**（指标口径错配） | `src/research/event_study/engine.py` | 只在 20D 输出，其余返回 `None` 并在 `note` 说明 |
| 4 | **事件与标签无法对齐**：as_of 可能落在非交易日 | `src/research/pipeline.py` | 新增 `_align_observation_trade_dates` |
| 5 | **`AnalysisRun` 校验失败导致 consensus 丢失**：`extra` 字段污染严格模型 | `src/core/orchestration/analysis_service.py` | 附加信息移入 `_extras` 键；`load_analysis` 只保留已声明字段 |
| 6 | **索引名冲突**：`classical_entry.domain` 的 `index=True` 与显式复合索引同名 | `src/db/models.py` | 复合索引改名 `ix_classical_entry_domain_school` |
| 7 | **Alembic 读取 `alembic.ini` 报 GBK 解码错误** | `alembic.ini` | 文件保持纯 ASCII（中文 Windows locale 编码问题） |
| 8 | **`variant_mode`/`exchange` 等枚举字段 `.value` 抛 AttributeError** | 多处 | Pydantic `use_enum_values=True` 使字段变字符串；统一用 `ex_value()` 辅助函数 |
| 9 | **周末上市未被顺延**：`_ensure_trading_day` 从未把 `shifted` 置为 `True` | `src/core/stock/birth_profile.py` | 移动游标时设置 `shifted = True` |
| 10 | **`BalanceDate` 别名导致 Schema 复杂化** | `src/core/schemas/calendar.py` | 改为 `timestamp` 字段 |
| 11 | **Playwright strict mode 误报**：Next.js 水合期间同一元素短暂出现两次 | `apps/web/e2e/*.spec.ts` | 对可能重复的 `data-testid` 统一使用 `.first()` |
| 12 | **Next.js 收到 404 预取请求**：侧栏链接指向不存在的页面 | `apps/web/app/**` | 为 9 个未实现模块创建占位页 |

### 12.2 未修复（已知问题）

| # | 问题 | 影响 | 优先级 |
|---|---|---|---|
| 1 | **节假日上市会被错误对齐**（无独立交易日历表） | 出生时刻可能差 1 天，数据质量已降级为 B/C | P1 |
| 2 | **`/analysis/{id}/backtest` 每次请求重算全库标签** | 响应 1–3 秒 | P1 |
| 3 | **收益分布用正态近似** | UI 图注已标"示意分布"，非真实直方图 | P2 |
| 4 | **时间窗口曲线为展示层外推** | UI 卡片内有文字说明，非真实预测 | P2 |
| 5 | **首屏短暂"加载中…"**（Suspense + useSearchParams） | 视觉闪烁，已被测试兼容 | P3 |
| 6 | **综合研判页 First Load JS 510 kB**（含 ECharts） | 可 `next/dynamic` 懒加载优化 | P3 |
| 7 | **中文字形跨平台差异**（Windows YaHei vs 参考图 PingFang SC） | 字形宽度系统性差异，非结构问题 | P3 |

---

## 13. 已知技术债

| # | 位置 | 问题 | Phase 2 建议 |
|---|---|---|---|
| 1 | `src/core/stock/birth_profile.py` | 无交易日历表 | 新增 `trading_calendar` 表 + `TradingCalendar` 服务 |
| 2 | `apps/api/routers/analysis.py::_load_label_rows` | 标签不落库，每次重算 | 建 `forward_label` 表 + 增量更新 |
| 3 | `src/research/event_study/engine.py` | 返回汇总统计而非全量样本 | 增 `include_histogram=true` 返回分箱 |
| 4 | `src/knowledge/` | 无 Embedding / FAISS，仅 BM25 | 接入 `sentence-transformers` + FAISS（注意离线可用性） |
| 5 | `src/factors/registry/compute.py` | 五行力量权重为工程近似 | 用 Golden Case + 回测校准，提升 `rule_version` |
| 6 | `apps/api/routers/research.py` | 研究流水线同步执行 | 引入任务队列（RQ / Celery） |
| 7 | `src/engines/bazi/rules.py` | 格局/喜用神流派覆盖不足 | bazi-pro adapter 双引擎对比（ADR-0002） |
| 8 | 全局 | 无样本外验证 / IC / 行业中性化 / 生存者偏差处理 | 研究层增强 |
| 9 | 全局 | `duckdb` 依赖已装但未使用 | 数据规模上来后启用（ADR-0005） |
| 10 | `apps/web` | 未做移动端适配 | Phase 2 若需要再补 |
| 11 | 全局 | 无日志聚合 / 无监控 | 单用户研究系统暂不需要 |

---

## 14. 关键 assumptions

| # | 假设 | 值 | 位置 | 影响 |
|---|---|---|---|---|
| 1 | **股票出生时间** | 上市首个正式交易日 + 交易所 session 正式开盘 + `Asia/Shanghai` | `birth_profile.py` | 这是**研究假设**，不是定论；必须回测检验 |
| 2 | **开盘时刻来源** | `exchange_session_calendar` 配置（当前 A 股统一 09:30） | `config/exchange_session_calendar.json` | 禁止硬编码（AST 测试强制） |
| 3 | **股票无性别** | `variant_mode = not_applicable`，不输出大运 | `BaziEngine` | 大运不进入 Phase 1 因子 |
| 4 | **年柱换柱** | 立春（非农历正月初一） | `CalendarEngine` | 1–2 月样本的年柱口径 |
| 5 | **月柱换柱** | 节气中的"节" | `CalendarEngine` | 交节当日的月柱边界 |
| 6 | **时柱口径** | 23:00 后归次日子时（晚子时） | lunar-python 内置 | 跨日子时样本 |
| 7 | **五行力量权重** | 天干 1.0（日干 0.8）/ 月支 ×1.5 / 日支 ×1.2 / 藏干 0.6-0.3-0.1 | `rules.py` | **工程近似**，非传统定论 |
| 8 | **旺衰阈值** | ≥0.62 身强 / ≥0.55 偏强 / >0.45 中和 / >0.38 偏弱 / 其余身弱 | `rules.py` | 临界区间自动降置信度 |
| 9 | **格局取法** | 月令本气/中气/余气透干优先，不透则以本气取格 | `rules.py` | 子平通行法；盲派/新派可能有不同结论 |
| 10 | **喜用神取法** | 扶抑法为主 + 调候法为辅 | `rules.py` | 中和时用神取食伤 |
| 11 | **黄历流派** | lunar-python 内置通书口径 | `CalendarEngine` | 宜忌在不同通书间存在差异 |
| 12 | **神煞类字段低置信度** | 建除/黄黑道/十二神/星宿 `confidence ≤ 0.55` | `compute.py` | 依据《命理约言》对神煞的批评（语料 `MLYY-0001`） |
| 13 | **因子分数语义** | 传统规则强度（0–10），**不是收益预测** | 所有因子 | 写入每个因子的 `rule_score_meaning` |
| 14 | **数量型因子方向中性** | `direction = 0` | 所有 `*_COUNT` 类因子 | 数量多寡由回测回答 |
| 15 | **成本假设** | 收益计算忽略交易成本、滑点、税费 | `labels/forward_returns.py` | 结论偏乐观 |
| 16 | **复权方式** | 统一前复权（qfq） | `market/providers` | 未对比其他复权方式 |
| 17 | **生存者偏差** | 未处理退市股票 | 研究层 | 结论偏乐观 |
| 18 | **古籍语料未校勘** | Phase 1 未逐字对照权威刊本 | `knowledge/bazi/classical_seed.json` `_meta` | 正式发布前必须校勘 |
| 19 | **合成行情边界** | `synthetic_demo` 仅用于联调与演示，**不可用于任何判断** | `market/providers/synthetic.py` | 响应带 `is_degraded=true` + error 级 warning |

---

## 15. 关键 ADR

| # | 标题 | 状态 | 核心决策 |
|---|---|---|---|
| [0001](ADR/ADR-0001-adapter-isolation.md) | 第三方引擎必须经 Adapter 隔离 | 已接受 | 六个核心接口 + 白名单 + AST 强制 |
| [0002](ADR/ADR-0002-bazi-engine-backend.md) | Phase 1 八字计算使用自研确定性内核 | 已接受；**Phase 2 需重评** | `smx-bazi-native-1.0.0`，bazi-pro 作为 Phase 2 可插拔后端 |
| [0003](ADR/ADR-0003-no-gender-variant-mode.md) | 股票无性别 → `variant_mode` | 已接受 | 默认 `not_applicable`，不输出大运 |
| [0004](ADR/ADR-0004-as-of-time-isolation.md) | `as_of` 单向隔离与防泄漏 | 已接受 | 唯一裁剪入口 + 哨兵污染验证 + 反向对照 |
| [0005](ADR/ADR-0005-sqlite-duckdb-storage.md) | SQLite 主库 + DuckDB/Parquet 研究层 | 已接受 | Phase 1 仅用 SQLite，DuckDB 留给 Phase 2 |
| [0006](ADR/ADR-0006-ui-fixture-mode.md) | UI fixture 模式与生产 runtime 分离 | 已接受 | `?fixture=ui-reference` + 常驻浮标 |
| [0007](ADR/ADR-0007-red-up-green-down.md) | 涨跌配色采用 A 股惯例 | 已接受 | **覆盖 UI 规范文档**；三重编码补偿 |

---

## 16. 不得破坏的契约

> **这一节是本文档最重要的部分。** Phase 2 若确实需要修改，必须：
> 1. 先创建 ADR（说明问题、原因、兼容方案、风险）；
> 2. 只做最小兼容修改；
> 3. 保留 v1 API 或新增 `/api/v2/`。

### 16.1 接口契约

| 契约 | 具体内容 |
|---|---|
| `MetaphysicsEngine` 抽象 | 方法签名 `calculate_chart` / `extract_factors` / `explain_rules` / `build_evidence_query` / `score` |
| `CalendarEngine.calculate_chart(context, when=...)` | 返回 `CalendarSnapshot` |
| `HuangliEngine.calculate_chart(context, when=..., days=...)` | 返回 `HuangliSnapshot` |
| `BaziEngine.calculate_chart(context, birth_datetime=..., as_of=..., variant_mode=..., stock_code=...)` | 返回 `BaziChart` |
| `MarketDataProvider` | `search` / `get_stock` / `get_daily_bars` / `get_benchmark_bars` |
| `KnowledgeProvider.search(EvidenceQuery)` | 返回 `EvidenceBundle`，**必须含 `counter_evidence`** |
| `BacktestProvider` | `evaluate_factor` / `evaluate_signal` / `evaluate_negative_controls` |
| `EngineMetadata` | `engine_id` / `display_name` / `engine_version` / `config_version` / `third_party` / `third_party_commit` / `notes` |

### 16.2 数据契约

| 类型 | 必须保留的字段 |
|---|---|
| `StockBirthProfile` | `stock_code` / `exchange` / `birth_basis` / `birth_datetime` / `timezone` / `source` / `birth_profile_version` / `assumptions` / `data_quality` / `variant_mode` |
| `Pillar` | `position` / `ganzhi` / `stem_ten_god` / `hidden_stems` / `nayin` / `di_shi` |
| `BaziChart` | 四柱 / `day_master` / `wuxing` / `day_master_analysis` / `pattern` / `yong_shen` / `relations` / `current_{year,month,day}_pillar` / `variant_mode` / `engine_version` / `assumptions` / `warnings` |
| `FactorObservation` | `factor_id` / `name` / `engine` / `category` / `raw_value` / `normalized_value` / `direction` / `rule_score` / `confidence` / `rule_version` / `evidence` / `explanation` |
| `FactorSet` | `stock_code` / `as_of` / `rule_version` / `config_version` / `observations` |
| `MetaphysicsOpinion` | `engine` / `availability` / `direction` / `score` / `confidence` / `top_positive_reasons` / `top_negative_reasons` / `factor_ids` / `historical_validity` |
| `EventStudyResult` | `experiment_id` / `factor_ids` / `logic` / `event_count` / `universe_size` / `horizons[]` / `methodology` |
| `NegativeControlReport` | `experiment_id` / `results[]`（含 `kind` / `verdict` / `verdict_note`）/ `conclusion` |
| `EvidenceBundle` | `supporting_evidence` / `counter_evidence` / `neutral_evidence` / `retrieval_method` |

### 16.3 语义契约

| # | 契约 |
|---|---|
| 1 | **不可用必须是 `null` / `"unavailable"`，绝不用 `0` 冒充** |
| 2 | 因子 `direction` / `rule_score` 是**传统规则强度**，不是收益率、不是上涨概率 |
| 3 | `activation` 默认 `nonzero`（事件必须"结构成立"才算命中） |
| 4 | 超额收益 / 回撤 / 最大上涨**只在 20D 持有期输出** |
| 5 | 标签数据不足时返回 `None` + `horizon_available=false`，**不用 0 填充** |
| 6 | 负对照必须**真的重排盘重算因子**，不得拿真实因子比随机标签 |
| 7 | 负对照结论必须如实输出（含 `underperform` 与"未显示正向信息量"） |
| 8 | 古籍检索必须同时返回支持与反证 |
| 9 | 模型分歧不得被平均分掩盖 |
| 10 | `variant_mode` 默认 `not_applicable`，不输出大运 |
| 11 | 出生档案切换基准生成**新版本**，不覆盖历史 |
| 12 | 业务层不得 import `lunar_python` / `akshare` |
| 13 | 每个结果必须记录 `engine_version` / `config_version` / `birth_profile_version` |
| 14 | `chart_artifact.raw_chart` 必须落库 |

### 16.4 API 契约

* `/api/v1/**` 的路径、请求体字段名、响应字段名**不得在不加版本号的情况下修改**；
* `display_only: true` 在 Phase 1 恒为 `true`；Phase 2 实现正式 Consensus 后改为 `false`，
  但**字段本身必须保留**；
* `/api/v1/analysis/{id}/guide` 中的 `engines[].available` / `unavailable_reason` 必须保留。

### 16.5 数据库契约

* 16 张表的表名与关键列名不变；
* **唯一约束语义不变**（尤其 `stock_birth_profile` 的版本化约束）；
* 新增列必须可空或带默认值；
* 不允许删除已有列（先废弃再在下个大版本移除）。

---

## 17. Phase 2 建议实施顺序

> 原则：**先解决 Phase 1 留下的正确性问题，再扩展模型，最后做产品和 AI。**

### 阶段 A：先修正确性（1–3 天）

| # | 任务 | 产出 |
|---|---|---|
| A1 | fork bazi-pro，核实许可证，锁定 commit SHA | `THIRD_PARTY.md` 更新 |
| A2 | 实现 `BaziProAdapter`，与自研内核做双引擎 Golden Case 对比 | `docs/calculation-differences.md` |
| A3 | 引入 `trading_calendar` 表 + 服务，替换周末规则 | 出生档案质量提升 |
| A4 | 标签落库（`forward_label` 表）+ 增量更新 | `/backtest` 响应 < 300ms |
| A5 | 事件研究返回真实分箱数据 | UI 可画真实直方图 |

### 阶段 B：紫微接入（3–5 天）

| # | 任务 | 产出 |
|---|---|---|
| B1 | `services/ziwei-service`（Node/TypeScript + iztro），`POST /internal/ziwei/chart` | 独立服务 |
| B2 | `ZiweiEngine` adapter（实现 `MetaphysicsEngine`） | `src/engines/ziwei/` |
| B3 | 紫微 `raw_chart` 落库 + `variant_mode`（顺逆两个 variant） | `chart_artifact` |
| B4 | 30–50 个紫微因子（`Z_FIN_*` / `Z_CAREER_*` / `Z_LIFE_*` / `Z_YEAR_*` / `Z_MONTH_*` / `Z_DAY_*`） | `factors/ziwei/` |
| B5 | 紫微 Golden Cases（十二宫 / 四化 / 流年） | `tests/golden/` |
| B6 | 引擎故障隔离：紫微失败时其他引擎继续，紫微显示 unavailable | 测试覆盖 |

### 阶段 C：多模型融合（2–4 天）

| # | 任务 | 产出 |
|---|---|---|
| C1 | 正式 `ConsensusEngine`（6 种共识分类，禁止简单平均） | `src/core/orchestration/consensus.py` |
| C2 | 正式 `ConflictDetector`（`conflicting_engines` / `directions` / `reasons` / `conflicting_factor_ids` / `historical_conflict_stats`） | 同上 |
| C3 | 共振历史统计：单模型 / 两两同向 / 三模型同向 / 三模型冲突 | `research/` |
| C4 | `display_only` 改为 `false`，但保留字段 | API |
| C5 | UI 分歧矩阵页（参考图 `07`） | `app/stock/[code]/conflicts/` |

### 阶段 D：时间窗口与历史验证（2–3 天）

| # | 任务 | 产出 |
|---|---|---|
| D1 | 月度预测（未来 12 个月，每月保留三模型 opinion + consensus + conflict） | `research/` |
| D2 | 周度聚合（**交易日流日因子聚合，禁止发明"流周"**；方法版本化） | `research/` |
| D3 | 时间窗口页（参考图 `10`） | `app/stock/[code]/timeline/` |
| D4 | 历史验证页（参考图 `05`）：分布 / 年度稳定性 / 牛熊分组 / 样本内外 | `app/stock/[code]/backtest/` |
| D5 | 黄历详情页（参考图 `08`）、古籍证据页（参考图 `09`）、因子字典页（参考图 `06`） | 三个页面 |

### 阶段 E：AI Narrator（2–3 天）

| # | 任务 | 产出 |
|---|---|---|
| E1 | `EvidenceBundle` → LLM 输入契约（**只允许解释，禁止计算**） | `src/narrator/` |
| E2 | System Prompt 固化 10 条禁令（见 `architecture_v1.md` §36） | 同上 |
| E3 | 输出校验：LLM 不得修改干支/宫位/四化/分数；古籍必须来自 evidence | 测试 |
| E4 | 在 UI 上标注"AI 解释"与"确定性结果"的边界 | UI |

### 阶段 F：产品化（2–3 天）

| # | 任务 |
|---|---|
| F1 | 导出 Markdown / HTML（含版本信息与方法限制） |
| F2 | 设置页（出生模型切换生成新版本） |
| F3 | 研究实验室图形化 |
| F4 | 移动端适配（若需要） |

### 每阶段的必做事项

```
1. 新增/修改引擎或规则 → 提升对应 engine_version / rule_version
2. 新增因子 → 更新 docs/factor_dictionary.md 与 HANDOFF
3. 修改 UI → 更新 apps/web/artifacts/ui-review/*/notes.md
4. 每个阶段结束 → make test + make test-ui 全绿
5. 涉及契约改动 → 先写 ADR
```

---

## 18. 启动与验收命令速查

### 18.1 首次启动

```bash
# 依赖
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"
cd apps/web && npm install && cd ../..

# 数据库
PYTHONUTF8=1 .venv/Scripts/python.exe -m alembic upgrade head
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli seed

# 自检
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli doctor

# 启动
PYTHONUTF8=1 .venv/Scripts/python.exe -m uvicorn apps.api.main:app --port 8000 --reload
cd apps/web && npm run dev
```

### 18.2 一条命令

```bash
make bootstrap && make migrate && make seed && make api   # 后端
make web                                                  # 前端（另开终端）
```

### 18.3 Docker

```bash
docker compose up --build     # api:8000 + web:3000
docker compose down
docker compose run --rm api python -m pytest -q
```

### 18.4 测试

```bash
make test           # 后端 368 项
make test-leak      # P0 防未来数据泄漏（16 项）
make test-golden    # Golden Cases（36 项）
make test-ui        # Playwright（40 项，需 web 已启动）
make test-all       # 后端 + UI
make typecheck      # 前端类型检查
make check          # typecheck + lint
```

### 18.5 UI 复刻验收

```bash
cd apps/web
npx next build && npx next start -p 3000
make shots          # → apps/web/artifacts/ui-review/<page>/current.png
make shots-live     # 真实 API 数据
```

### 18.6 常用分析命令

```bash
# 单股分析
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli analyze 600519 --as-of 2024-11-15T14:32:00

# 研究流水线（事件研究 + 四类负对照）
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli research --universe 600519 000001 300750
```

### 18.7 离线模式（无网络时）

```bash
export SMP_MARKET_PROVIDER=synthetic
```

> 合成行情仅用于联调与演示，**不可用于任何投资判断**。

---

## 19. 给 Phase 2 的第一句话

> **Phase 1 的价值不在于"算得多准"，而在于把三件事做对了：**
>
> 1. **确定性**：所有排盘可复现、可审计、可回归；
> 2. **可证伪**：因子、标签、事件研究、四类负对照都真实可跑，且**如实输出**；
> 3. **可交接**：六个核心接口、65 个因子、16 张表、368 项测试全部有契约保护。
>
> **请在这三件事的基础上扩展，而不是重做它们。**
>
> 如果你发现某个契约确实阻碍了 Phase 2 的正确性 —— 先写 ADR，再做最小兼容修改。
>
> 最重要的一条：**不要为了让结果好看而修改计算。**
