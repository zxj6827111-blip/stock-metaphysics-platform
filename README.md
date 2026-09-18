# 股票玄学多模型研究平台

> **Phase 1 · Foundation & BaZi Research Loop**
>
> 一个真实可运行的 **传统术数多模型 × 古籍知识库 × 股票历史行情 × 统计回测验证** 研究系统。

---

## ⚠️ 先说清楚这个项目是什么

**这不是荐股系统，也不是"算命工具"。**

本平台做的事情是：

```
传统术数
  ↓ 确定性代码计算（禁止 LLM 算命）
结构化因子
  ↓ 与真实历史行情对齐（as_of 严格隔离，禁止未来数据泄漏）
统计检验 + 负对照
  ↓ 如实输出结果（哪怕结论是"没有信息量"）
可追溯、可审计、可复现的研究结论
```

**本项目最重要的一条原则：**

> 传统八字、紫微、黄历与股票未来收益之间，**不存在经现代金融科学确认的稳定因果关系**。
> 系统的价值不在于"证明术数很准"，而在于**用可复现的方法回答"哪些传统结构在历史数据上确实有统计关系，哪些没有"**。

因此：

* 因子分数是**传统规则强度**，不是预期收益率，也不是上涨概率；
* **财星 ≠ 股票上涨**，**食神生财 ≠ 股票一定上涨**，**三合 ≠ 股票上涨**；
* 系统内置四类**负对照**（随机出生日 / 出生日 ±7 天 / 随机因子），
  如果真实因子并不优于随机，系统会**如实输出**，不会美化；
* 紫微斗数在 Phase 1 **明确不实现**，接口返回 `unavailable`，**不会用 0 分冒充**。

---

## 目录

- [快速开始](#快速开始)
- [Phase 1 能做什么](#phase-1-能做什么)
- [Phase 1 明确不做什么](#phase-1-明确不做什么)
- [系统架构](#系统架构)
- [核心概念](#核心概念)
- [目录结构](#目录结构)
- [常用命令](#常用命令)
- [API](#api)
- [数据库](#数据库)
- [因子体系](#因子体系)
- [方法论要点](#方法论要点)
- [UI](#ui)
- [Docker](#docker)
- [常见问题](#常见问题)
- [文档索引](#文档索引)

---

## 快速开始

### 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | **3.12**（≥3.11） | AKShare 与 numpy/pandas 在该版本上轮子最全 |
| Node.js | **≥ 20** | 前端 Next.js 15 |
| uv | 最新 | Python 包管理（也可用 pip + venv） |
| Docker | 可选 | `docker compose up` 一键启动 |

> **Windows 用户注意**：本项目所有 Python 命令都建议带 `PYTHONUTF8=1`。
> 中文 Windows 的默认编码是 GBK，会导致 `configparser` 读取含中文的配置文件失败。

### 方式一：本地开发（推荐）

```bash
# 1. 创建虚拟环境并安装依赖
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"

# 2. 初始化数据库
PYTHONUTF8=1 .venv/Scripts/python.exe -m alembic upgrade head

# 3. 写入种子数据（古籍语料 + 交易所交易时段）
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli seed

# 4. 环境自检（可选，但强烈建议）
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli doctor

# 5. 启动后端（http://127.0.0.1:8000，交互文档 /docs）
PYTHONUTF8=1 .venv/Scripts/python.exe -m uvicorn apps.api.main:app --port 8000 --reload

# 6. 启动前端（另开一个终端；http://127.0.0.1:3000）
cd apps/web && npm install && npm run dev
```

Linux / macOS 用户把 `.venv/Scripts/python.exe` 换成 `.venv/bin/python` 即可。

**一键完成 1–3 步：**

```bash
make bootstrap && make migrate && make seed
```

### 方式二：Docker Compose

```bash
docker compose up --build
# 前端 http://localhost:3000
# 后端 http://localhost:8000/docs
```

### 第一次运行

```bash
# 对单只股票跑一次完整分析
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli analyze 600519 --as-of 2024-11-15T14:32:00

# 运行研究流水线（事件研究 + 四类负对照）
PYTHONUTF8=1 .venv/Scripts/python.exe -m src.cli research --universe 600519 000001 300750
```

### 无网络环境

AKShare 依赖外部接口，可能因为网络/代理/限流不可用。此时系统会：

```
AKShare 失败 → 重试 → 本地缓存 → 确定性合成行情（显式标注 synthetic_demo）
```

合成行情**只用于系统联调与 UI 演示**，所有输出都会带 `is_degraded=true` 与 error 级警告。
如需强制离线模式：

```bash
export SMP_MARKET_PROVIDER=synthetic
```

---

## Phase 1 能做什么

输入一个 A 股代码，系统会完成：

| # | 能力 | 状态 |
|---|---|---|
| 1 | 股票基础资料（名称/交易所/板块/上市日期） | ✅ |
| 2 | **股票出生档案**（`listing_open` = 上市首日正式开盘 + `Asia/Shanghai`） | ✅ |
| 3 | 历法（公历/农历/干支/节气/生肖/纳音） | ✅ |
| 4 | **黄历**（建除十二值/十二神/黄黑道/冲煞/彭祖百忌/吉神方位） | ✅ |
| 5 | **八字原盘**（四柱/藏干/十神/纳音/五行/旺衰/格局/喜用忌/刑冲合害/流年流月流日） | ✅ |
| 6 | **原始盘面落库**（`chart_artifact.raw_chart`，可审计、可复算） | ✅ |
| 7 | **65 个真实可计算因子**（B_NATAL / B_YEAR / B_MONTH / B_DAY / H_DAY / H_MONTH） | ✅ |
| 8 | 历史行情（AKShare adapter + 缓存 + 重试 + 显式降级） | ✅ |
| 9 | **未来收益标签**（1/5/10/20/60 日 + 最大回撤 + 超额收益 + 四种"上涨"定义） | ✅ |
| 10 | **Event Study**（样本数/上涨率/平均收益/中位数/超额收益/最大回撤） | ✅ |
| 11 | **四类负对照**（随机出生日 / ±7 天 / 随机因子） | ✅ |
| 12 | **古籍知识中心**（BM25 + 权威权重 + **支持证据与反证**） | ✅ |
| 13 | REST API（30 个端点 + OpenAPI） | ✅ |
| 14 | 研究终端 UI（首页 / 综合研判 / 八字详情，1672×941 1:1 复刻） | ✅ |
| 15 | pytest 测试套件（368 项，含 P0 级防未来数据泄漏测试） | ✅ |
| 16 | Playwright UI 端到端测试（40 项） | ✅ |

---

## Phase 1 明确不做什么

以下内容**在代码层面就不存在**，访问对应接口会返回结构化的 `unavailable`：

| 模块 | Phase 1 行为 | 说明 |
|---|---|---|
| **紫微斗数** | 不实现 | 接口返回 `available: false`，UI 显示"未启用"，**不以 0 分参与任何聚合** |
| 六爻 / 奇门 | 仅预留目录与接口 | 同上 |
| AI Narrator（LLM 解释） | 不实现 | 所有结论由确定性代码产生 |
| 正式 ConsensusEngine | 不实现 | 综合研判页的共识/分歧卡片是**展示层聚合**（`display_only: true`） |
| 正式 ConflictDetector | 不实现 | 同上 |
| 月度 / 周度时间窗口预测 | 不实现 | 时间窗口图仅为**展示层示意**，卡片内有文字说明 |
| 导出（Markdown / HTML） | 不实现 | 按钮置灰 |
| 自动交易 / 券商接口 / 会员 / 支付 / 多租户 | 不实现 | 平台定位是研究系统 |

> UI 的 `?fixture=ui-reference` 模式会显示紫微的**固定演示数据**（用于逐像素比对参考图）。
> 这些数据只存在于前端 `lib/fixture.ts`，**不进入任何分析数据库**，页面上有明确标识。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│  apps/web   Next.js 研究终端                                  │
│  首页 / 综合研判 / 八字详情（1672×941 1:1 复刻参考图）          │
└─────────────────────────┬────────────────────────────────────┘
                          │ HTTP（OpenAPI）
┌─────────────────────────▼────────────────────────────────────┐
│  apps/api   FastAPI（唯一对外出口，30 个端点）                  │
└─────────────────────────┬────────────────────────────────────┘
                          │
   ┌──────────────────────┼───────────────────────┬─────────────────┐
   ▼                      ▼                       ▼                 ▼
 core/stock            engines/*              factors/*        research/*
 StockMaster           CalendarEngine         FactorRegistry    labels
 StockBirthProfile     HuangliEngine          65 个因子          event_study
 exchange_session      BaziEngine             B_* / H_*         validation
   │                      │                       │             backtest
   └──────────────────────┴───────────┬───────────┴─────────────────┘
                                      ▼
                        market/*   knowledge/*   db/*
                        AKShare    BM25 + 古籍   SQLAlchemy + SQLite
                        adapter    + 反证        + Alembic
```

### 六个核心接口（Phase 2 不得破坏的契约）

| 接口 | 位置 | 职责 |
|---|---|---|
| `CalendarEngine` | `src/engines/calendar/` | 历法（lunar-python adapter） |
| `HuangliEngine` | `src/engines/huangli/` | 黄历 / 日课 |
| `BaziEngine` | `src/engines/bazi/` | 八字排盘与结构化分析 |
| `MarketDataProvider` | `src/market/providers/` | 行情（AKShare adapter） |
| `KnowledgeProvider` | `src/knowledge/retrieval/` | 古籍检索（含反证） |
| `BacktestProvider` | `src/research/backtest/` | 回测 / 验证 |
| `MetaphysicsEngine`（基类） | `src/engines/base.py` | 所有术数引擎的抽象契约 |

**硬性约束**（由 `tests/test_third_party_isolation.py` 机器校验）：

1. 业务层**不得** `import lunar_python` / `import akshare`；
2. 第三方对象**不得**出现在任何 Schema 中；
3. 所有排盘由确定性代码产生，**禁止 LLM 计算**。

---

## 核心概念

### StockBirthProfile（股票出生档案）

股票不存在传统意义的"出生时间"。本项目把它当作**一个必须被回测检验的研究假设**，而不是事实。

默认模型：

```
listing_open = 上市首个正式交易日
             + 该交易所 session 的正式开盘时刻（来自 exchange_session_calendar 配置）
             + Asia/Shanghai
```

* 开盘时刻**不硬编码**，配置在 [`config/exchange_session_calendar.json`](config/exchange_session_calendar.json)；
* 每个档案带 `birth_profile_version`，切换基准**生成新版本**而不覆盖历史；
* 预留 `ipo_date` / `company_foundation` / `first_trade` / `custom` 四种候选基准。

### 股票没有性别

传统大运顺逆依赖"性别 + 年干阴阳"。股票没有真实性别，因此：

* **禁止**偷偷填"男命"或"女命"；
* `variant_mode ∈ {forward, reverse, both, not_applicable}`，Phase 1 默认 `not_applicable`；
* 该模式下**不输出大运**，大运不进入任何因子；
* 必须写入 `assumptions`（键名 `bazi.variant_mode`）；
* 如需研究，可显式切换为 `forward`/`reverse` 并分别回测比较。

### as_of 单向时间隔离

```python
as_of = "2020-01-01"

特征（因子）：只能读 <= 2020-01-01 的信息 —— 而因子只依赖盘面，结构上不读行情
标签（收益）：只能读 >  2020-01-01 的信息
```

`src/market/normalization/frames.py::clip_to_as_of` 是唯一的裁剪入口，
`tests/test_no_future_data_access.py` 用**哨兵污染法**验证：
把 as_of 之后的行情替换成 999999，特征结果必须完全不变。

### 原始盘面是一等数据

不要只保存 `score = 83`。`chart_artifact` 表保存：

```json
{
  "chart_id": "bazi-600519-20241115143200-a1b2c3",
  "engine": "bazi",
  "engine_version": "smx-bazi-native-1.0.0",
  "config_version": "cfg-2026.09",
  "birth_profile_version": "v1",
  "input": { "birth_datetime": "...", "variant_mode": "not_applicable" },
  "raw_chart": { "year_pillar": { "ganzhi": { "text": "辛巳" } }, ... },
  "calculated_at": "2024-11-15T14:32:00"
}
```

未来引擎升级后可以重新计算并逐字段比较。

---

## 目录结构

```
stock-metaphysics-platform/
├── apps/
│   ├── api/                     FastAPI（main / routers / errors / deps）
│   └── web/                     Next.js 15（app / components / lib / e2e）
├── src/
│   ├── core/
│   │   ├── constants.py         干支 / 五行 / 十神 / 刑冲合害 静态表
│   │   ├── config.py            全局配置（SMP_* 环境变量）
│   │   ├── cli.py               命令行工具（seed / research / analyze / doctor）
│   │   ├── schemas/             Pydantic 领域模型
│   │   ├── stock/               代码规范化 / 交易所时段 / 出生档案
│   │   └── orchestration/       分析编排（唯一业务入口）
│   ├── engines/
│   │   ├── base.py              MetaphysicsEngine 抽象基类
│   │   ├── calendar/            CalendarEngine（lunar-python adapter）
│   │   ├── huangli/             HuangliEngine
│   │   ├── bazi/                BaziEngine + rules.py（规则内核）
│   │   └── ziwei|liuyao|qimen/  预留（Phase 2）
│   ├── factors/
│   │   └── registry/            因子定义 + 计算引擎
│   ├── market/
│   │   ├── providers/           MarketDataProvider / AKShare / Synthetic
│   │   └── normalization/       列归一化 / 异常检测 / as_of 裁剪 / 结构化错误
│   ├── research/
│   │   ├── labels/              未来收益标签
│   │   ├── event_study/         事件研究
│   │   ├── validation/          负对照（四类）
│   │   ├── backtest/            BacktestProvider
│   │   └── pipeline.py          端到端研究流水线
│   ├── knowledge/
│   │   ├── ingest/              语料加载与落库
│   │   └── retrieval/           KnowledgeProvider（BM25 + 反证）
│   ├── db/                      SQLAlchemy 模型 + 会话
│   └── narrator/                预留（Phase 2）
├── services/ziwei-service/      预留（Phase 2，iztro adapter）
├── knowledge/bazi/              古籍语料（公版原文）
├── config/                      交易所交易时段配置
├── migrations/                  Alembic migration
├── tests/                       368 项测试
├── docs/                        见「文档索引」
├── data/                        SQLite / Parquet（gitignore）
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

---

## 常用命令

```bash
make help              # 列出全部命令
make bootstrap         # 创建虚拟环境 + 安装前后端依赖
make migrate           # 数据库 migration
make seed              # 写入种子数据
make api               # 启动后端（reload）
make web               # 启动前端
make test              # 全部后端测试
make test-golden       # 只跑 Golden Cases
make test-leak         # 只跑防未来数据泄漏测试（P0）
make test-ui           # Playwright UI 测试（需 web 已启动）
make test-all          # 后端 + UI 全部测试
make check             # 类型检查 + lint
make shots             # 生成 1672×941 三页截图并与参考图对比
make research          # 运行研究流水线
make docker-up         # Docker Compose 启动
```

---

## API

完整文档见 [`docs/api.md`](docs/api.md)，或启动后访问 <http://127.0.0.1:8000/docs>。

Phase 1 核心端点：

```
GET  /api/v1/stocks/search?q=600519
GET  /api/v1/stocks/{code}
POST /api/v1/stocks/{code}/birth-profile
POST /api/v1/stocks/{code}/analysis/bazi
GET  /api/v1/analysis/{id}/charts/bazi
GET  /api/v1/analysis/{id}/huangli
GET  /api/v1/analysis/{id}/factors
GET  /api/v1/analysis/{id}/backtest
GET  /api/v1/analysis/{id}/evidence
```

所有错误统一返回：

```json
{ "error": { "code": "...", "message": "...", "detail": "...", "retryable": true } }
```

---

## 数据库

SQLite（主库）+ Alembic（migration）。16 张业务表：

```
股票      stock_master / stock_birth_profile / exchange_session_calendar
行情      market_bar_daily / market_fetch_log
引擎      engine_version / engine_run / chart_artifact
因子      factor_definition / factor_observation
古籍      classical_book / classical_entry / evidence_link
研究      backtest_experiment / backtest_result
编排      analysis_run
```

详见 [`docs/database.md`](docs/database.md)。

---

## 因子体系

65 个因子，六个命名空间：

| 前缀 | 数量 | 内容 |
|---|---|---|
| `B_NATAL_` | 18 | 原局结构（日主强弱/财星/食伤/官杀/印星/比劫/格局/用神/五行/合冲/调候） |
| `B_YEAR_` | 10 | 流年（天干地支喜忌/财星/食伤/冲合刑害/十二长生/三合） |
| `B_MONTH_` | 12 | 流月（同上 + 财星引动/食伤生财/官杀变化） |
| `B_DAY_` | 8 | 流日（用于周度聚合） |
| `H_DAY_` | 12 | 黄历 × 原局交叉（天干地支喜忌/冲合刑/建除/黄黑道/十二神/纳音/星宿） |
| `H_MONTH_` | 5 | 黄历月度聚合（黄道日占比/吉神日占比/合冲天数/喜神日占比） |

每个因子都带：

```
factor_id / name / engine / category / definition / computation
raw_value / normalized_value / direction / rule_score / confidence
rule_version / engine_version / config_version / evidence / explanation
```

> `direction` 与 `rule_score` 表达的是**传统规则认为的方向与强度**，
> **不是预期收益率，也不是上涨概率**。这一点写在每个因子的 `rule_score_meaning` 字段里。

详见 [`docs/factor_dictionary.md`](docs/factor_dictionary.md)。

---

## 方法论要点

1. **禁止 LLM 参与计算** —— 所有排盘、因子、标签、统计全部由确定性代码产生。
2. **负对照是硬性要求** —— 没有负对照的"回测有效"在本项目里不算结论。
3. **样本不足必须明说** —— 返回 `sample_count: 0` 和解释，而不是看似精确的比例。
4. **指标口径不混用** —— 超额收益/最大回撤只与 20 日持有期一起给出。
5. **不美化结论** —— 真实因子弱于随机时，系统输出 `underperform` 并写明
   "本系统如实输出该结果：术数因子未显示正向信息量"。
6. **古籍同时检索反证** —— 避免"先有结论后找古籍"。
7. **古籍版权** —— 只收清代及以前公版原文，逐条记 `provenance` / `edition` / `license_status`。

详见 [`docs/methodology.md`](docs/methodology.md)。

---

## UI

三个页面已完成 1672×941 的参考图复刻：

| 页面 | 路由 | 参考图 |
|---|---|---|
| 首页 | `/` | `01_home.png` |
| 综合研判 | `/stock/[code]/overview` | `02_integrated_analysis.png` |
| 八字详情 | `/stock/[code]/bazi` | `03_bazi_detail.png` |

**两种数据模式：**

* 去掉参数时读取**真实 API**；
* 加 `?fixture=ui-reference` 时读取**固定演示数据**（用于逐像素比对参考图）。
  此模式下紫微为**纯展示 Mock**，页面右下角有明确浮标提示。

对比结果保存在 `apps/web/artifacts/ui-review/<page>/{reference.png, current.png, notes.md}`。

详见 [`docs/ui-implementation.md`](docs/ui-implementation.md)。

---

## Docker

```bash
docker compose up --build     # 启动 api(8000) + web(3000)
docker compose down
docker compose run --rm api python -m pytest -q
```

Phase 1 不需要 Redis / Kafka / Kubernetes（见架构文档 §68）。

---

## 常见问题

**Q：为什么 `data/smp.sqlite3` 是空的？**
A：需要先跑 `python -m alembic upgrade head` 建表，再跑 `python -m src.cli seed` 写种子数据。

**Q：行情接口报 `MARKET_PROVIDER_UNAVAILABLE`？**
A：AKShare 依赖外部接口，可能被网络/代理拦截。系统会自动降级到缓存或合成行情
（响应中带 `is_degraded: true`）。如需强制离线：`export SMP_MARKET_PROVIDER=synthetic`。

**Q：为什么紫微的分数是空的？**
A：Phase 1 不实现紫微，接口返回 `available: false` + `score: null`。
这是设计如此 —— **系统不会用 0 分伪装成"紫微认为中性"**。

**Q：Golden Case 失败了怎么办？**
A：**不要直接改期望值。** 先判断是"第三方库升级导致的口径变化"还是"代码 bug"；
如果是口径变化，写入 `docs/calculation-differences.md`，提升 `engine_version`，并重跑全部案例。

**Q：报告里的"规则分 68.19"是不是上涨概率？**
A：**不是。** 它是传统规则强度的加权聚合（0–100），与收益率无关。
它的历史有效性必须由 `POST /api/v1/research/run` 的事件研究与负对照来回答。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 系统架构、分层、数据流、契约 |
| [`AGENTS.md`](AGENTS.md) | 给 AI 编程助手的强制规则（Phase 2 必读） |
| [`THIRD_PARTY.md`](THIRD_PARTY.md) | 第三方依赖、版本锁定、许可证、Adapter 边界 |
| [`docs/IMPLEMENTATION_PLAN_PHASE1.md`](docs/IMPLEMENTATION_PLAN_PHASE1.md) | Phase 1 计划、风险、验收点 |
| [`docs/database.md`](docs/database.md) | 数据库表结构与字段说明 |
| [`docs/api.md`](docs/api.md) | API 参考与错误码 |
| [`docs/factor_dictionary.md`](docs/factor_dictionary.md) | 65 个因子的完整定义 |
| [`docs/methodology.md`](docs/methodology.md) | 研究纪律、统计方法、已知局限 |
| [`docs/ui-implementation.md`](docs/ui-implementation.md) | UI 组件、设计令牌、复刻流程 |
| [`docs/HANDOFF_PHASE1.md`](docs/HANDOFF_PHASE1.md) | **Phase 2 接手必读** |
| [`docs/ADR/`](docs/ADR/) | 架构决策记录 |

---

## 免责声明

本系统是**研究与教育用途的实验平台**，不是投资顾问，也不是荐股系统。

* 传统术数与股票未来收益之间不存在经现代金融科学确认的稳定因果关系；
* 系统输出的所有分数、方向、统计结果都不构成投资建议；
* 历史统计结果不代表未来表现；
* 使用者需自行承担全部决策风险。

平台**不提供**：自动交易、券商下单、资金账户、收益保证。
