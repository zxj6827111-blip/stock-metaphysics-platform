# 系统架构 · 股票玄学多模型研究平台 Phase 1

> 面向开发者与 Phase 2 接手者的技术架构说明。
> 产品侧的规则与纪律见 [`AGENTS.md`](AGENTS.md)；方法论见 [`docs/methodology.md`](docs/methodology.md)。

---

## 1. 设计目标

用一句话概括：

> **第三方库负责"算盘"，自研 Factor Engine 负责"把盘变成可研究变量"，
> Research 层负责"验证这些变量有没有历史信息量"，
> Knowledge Center 负责"说明古籍依据"，
> （Phase 2）Consensus Engine 负责"判断多个术数是否共振或冲突"，
> （Phase 2）LLM 最后只负责把以上确定性结果解释成人能看懂的研究报告。**

由此推出的四个硬性架构约束：

| # | 约束 | 理由 |
|---|---|---|
| 1 | 术数排盘全部由确定性代码产生 | 可复现、可审计、可回归 |
| 2 | 第三方库只能经 Adapter 进入 | 第三方升级/更换不应波及业务层 |
| 3 | 原始盘面是一等数据，必须落库 | 未来规则升级后要能重新审计 |
| 4 | `as_of` 单向时间隔离 | 防止未来数据泄漏（研究可信度的前提） |

---

## 2. 分层

```
┌────────────────────────────────────────────────────────────────────┐
│ apps/web   Next.js 15 研究终端                                      │
│   AppShell / Sidebar / TopBar / StockContextBar                     │
│   首页 · 综合研判 · 八字详情（+ Phase 2 占位页）                     │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ HTTP / OpenAPI
┌──────────────────────────▼─────────────────────────────────────────┐
│ apps/api   FastAPI（唯一对外出口）                                   │
│   routers: stocks / analysis / research / knowledge / system        │
│   errors.py: 统一结构化错误                                          │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│ src/core/orchestration   AnalysisService（唯一业务入口）             │
│   串联：股票 → 出生档案 → 历法 → 黄历 → 八字 → 因子 → 落库           │
│   产出：opinion / 展示层 consensus / 展示层 conflict                 │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
   ┌───────────────────────┼────────────────────────┬────────────────┐
   ▼                       ▼                        ▼                ▼
engines/*              factors/*               research/*       market/*
 CalendarEngine        FactorRegistry          labels           MarketDataProvider
 HuangliEngine         65 个因子               event_study      ├ AkshareProvider
 BaziEngine            B_* / H_*               validation       ├ 缓存层
 MetaphysicsEngine     (fusion 预留)           backtest         └ SyntheticProvider
   │                       │                        │                │
   └───────────────────────┴────────────┬───────────┴────────────────┘
                                        ▼
                     knowledge/*                  db/*
                     KnowledgeProvider            SQLAlchemy 模型
                     BM25 + 权威权重 + 反证        Alembic migration
```

### 依赖方向（单向，不可逆）

```
apps/*  →  core/orchestration  →  {engines, factors, research, market, knowledge}  →  {db, schemas}
```

由 `tests/test_third_party_isolation.py` 强制校验：

* `src/factors`、`src/research`、`src/knowledge`、`apps/*` 均不得 import `lunar_python` / `akshare`；
* Schema 模块的类型注解中不得出现第三方类型（AST 精确判定）。

---

## 3. 核心模块

### 3.1 `src/core/constants.py` — 静态查表

干支 / 五行 / 阴阳 / 藏干 / 十神 / 刑冲合害 / 三合三会 / 十二长生 / 建除 / 黄黑道。
**不含任何历法计算**（那属于 CalendarEngine），以及**纯函数**：

* `ten_god(day_stem, other_stem)` — 十神判定
* `twelve_stage(day_stem, branch)` — 十二长生（阳干顺行、阴干逆行）

设计意图：把"命理定义"和"历法换算"分开。前者由本项目保证一致，后者交给 lunar-python。

### 3.2 `src/engines/calendar/` — CalendarEngine

lunar-python 的 Adapter。输出 `CalendarSnapshot`：

```
solar / lunar / year-month-day-hour ganzhi / jieqi / duty_officer /
day_tian_shen / huangli 各类字段 / raw_source（审计用）
```

关键口径：

* 年柱以**立春**换年（`getYearInGanZhiExact`），不是农历正月初一；
* 月柱以**节**换月（`getMonthInGanZhiExact`）；
* 时柱用五鼠遁，23:00 后归次日子时。

### 3.3 `src/engines/huangli/` — HuangliEngine

依赖 CalendarEngine，把黄历字段结构化，并保存 `raw_huangli`（一等数据）。
支持多日扫描（`days` 参数，上限 400），用于月度聚合因子。

### 3.4 `src/engines/bazi/` — BaziEngine

```
bazi_engine.py   装配 BaziChart（四柱 / 时间流 / 元信息）
rules.py         纯函数规则内核：
                   compute_wuxing_scores   五行力量估算
                   compute_strength        日主旺衰（得令/得地/得势）
                   compute_pattern         月令本气/透干取格
                   compute_yongshen        扶抑法 + 调候法
                   compute_relations       刑冲合害（两两 + 三合/三会）
                   relations_with_external 流年/月/日与原局的互动
```

**ADR-0002**：仓库尚未 fork bazi-pro，Phase 1 使用自研确定性内核 `smx-bazi-native-1.0.0`。
所有规则输出 `rationale` 与 `confidence`，无法可靠判定时返回 `unavailable`。
Phase 2 可挂 bazi-pro adapter 做双引擎交叉验证。

### 3.5 `src/factors/` — Factor Registry

```
registry/definitions.py   65 个 FactorDefinition（因子字典的数据源）
registry/compute.py       计算引擎：BaziChart + HuangliSnapshot → FactorSet
```

关键设计：

* 每个因子显式声明 `rule_score_meaning`（"传统规则强度，不是预期收益率"）；
* `direction` 只表达"传统规则认为的方向"，不预设收益方向；
* 数量型因子（财星数量、食伤结构…）的 `direction` 一律为**中性**——
  数量多寡本身不构成方向判断，方向必须由回测回答；
* 算不出来的因子走 `_unavailable()`，返回 `availability="unavailable"` + warning。

### 3.6 `src/market/` — 行情层

```
providers/base.py              MarketDataProvider 抽象
providers/akshare_provider.py  AKShare Adapter + 缓存 + 重试 + 降级链
providers/synthetic.py         确定性合成行情（synthetic_demo）
normalization/frames.py        列归一化 / 异常检测 / clip_to_as_of
normalization/errors.py        结构化错误类型
```

**降级链**（保证第三方挂了应用不崩）：

```
1. 本地 SQLite 缓存（未过期）→ source=cache
2. AKShare（retry ×3 + 指数退避）
3. 过期缓存兜底 → is_degraded=true
4. 确定性合成行情 → source=synthetic_demo, is_degraded=true, error 级 warning
5. 抛 ProviderUnavailableError（若禁用合成兜底）
```

`clip_to_as_of(series, as_of)` 是**防未来数据泄漏的唯一裁剪入口**。

### 3.7 `src/research/` — 研究层

```
labels/forward_returns.py         未来收益标签（1/5/10/20/60D + 回撤 + 超额 + 四种上涨定义）
event_study/engine.py             事件研究（activation 语义 + 多持有期统计）
validation/negative_controls.py   四类负对照 + 判定 + 汇总
backtest/provider.py              BacktestProvider 抽象与本地实现
pipeline.py                       端到端流水线（面板构建 + 事件研究 + 负对照）
```

几个不显然但重要的设计：

* **activation 语义**：事件默认要求 `normalized_value != 0`（该传统结构确实成立）。
  如果"命中"只表示"这个因子被计算过"，真实组与对照组的事件集合会完全相同，
  负对照就毫无意义。这曾经是一个真实 bug，见 `docs/methodology.md` §5。
* **指标口径不混用**：`mean_excess_return` / `max_drawdown` / `mean_max_return`
  只在 20 日持有期输出，其他持有期返回 `None` 并在 `note` 中说明。
* **as_of 对齐**：`_align_observation_trade_dates` 把因子观测的 `trade_date`
  对齐到标签的 `trade_date`（as_of 可能落在非交易日），未匹配的观测直接剔除。

### 3.8 `src/knowledge/` — 古籍知识中心

```
ingest/loader.py           JSON 语料 → ClassicalBook / ClassicalEntry
retrieval/provider.py      KnowledgeProvider（BM25 + 主题匹配 + 权威权重 + 域过滤）
```

评分公式：

```
score = (BM25 × 0.4 + topic_bonus + factor_bonus) × authority_weight
```

**必须同时返回 supporting / counter / neutral 三类**，避免"先有结论后找古籍"。

### 3.9 `src/core/orchestration/analysis_service.py` — 编排

唯一业务入口。负责：

* 串联引擎调用与落库（`chart_artifact` / `factor_observation` / `engine_run`）；
* 聚合 `MetaphysicsOpinion`（引擎观点契约）；
* 构建 **展示层** `ConsensusSnapshot` / `ConflictSnapshot`（`display_only: true`）；
* 紫微固定返回 `unavailable` + `score: null`。

`AnalysisRun.payload_json` 的额外信息放在 `_extras` 键下，
避免污染严格模型（`extra="forbid"`）。

---

## 4. 数据流（一次完整分析）

```
POST /api/v1/stocks/{code}/analysis/bazi  { as_of }
  │
  ├─ 1. MarketDataProvider.get_stock(code)
  │      → StockMaster（交易所 / 板块 / 上市日期）
  │      → 失败时降级到内置清单（数据质量降级并记录）
  │
  ├─ 2. build_birth_profile(stock, listing_open)
  │      → 上市首日对齐交易日（周末顺延；有行情时用行情校验）
  │      → exchange_session_calendar 解析开盘时刻（不硬编码 09:30）
  │      → StockBirthProfile（含 evidence / assumptions / data_quality）
  │
  ├─ 3. HuangliEngine.snapshot(as_of, days=31)
  │      → HuangliSnapshot（含 raw_huangli）
  │
  ├─ 4. BaziEngine.build_chart(birth_datetime, as_of, variant_mode)
  │      → BaziChart（四柱 / 藏干 / 十神 / 五行 / 旺衰 / 格局 / 喜用忌 /
  │                   刑冲合害 / 流年 / 流月 / 流日 / 胎元命宫）
  │
  ├─ 5. compute_factor_set(chart, huangli, as_of)
  │      → FactorSet（65 个 FactorObservation）
  │
  ├─ 6. 落库
  │      chart_artifact × 2（bazi / huangli，含 raw_chart）
  │      factor_observation × 65
  │      stock_master / stock_birth_profile / engine_version / engine_run
  │      analysis_run（含 payload/_extras）
  │
  └─ 7. 返回 BaziAnalysisResponse
         chart（原始盘面）+ factors + opinion（八字）
         + versions（全部版本号）+ warnings
```

研究流水线（`POST /api/v1/research/run`）在此基础上：

```
for variant in [real, random_birth_date, shift_+7d, shift_-7d]:
    for (stock, as_of_date) in universe × sample_dates:
        重排盘 → 重算因子 → 对齐标签
    事件研究 → HorizonStats
对比真实组与三个对照组的 20 日统计 → verdict → 汇总 conclusion
```

---

## 5. 版本管理与可追溯

每次结果都记录以下版本号（`VersionStamp`）：

```
engine_version          smx-bazi-native-1.0.0
rule_version            v1
config_version          cfg-2026.09
birth_profile_version   v1
knowledge_version       kb-1.0.0
market_data_version     akshare-1.18.96
```

**没有这些版本号，未来无法解释"为什么同一只股票上个月算 83 分、今天变成 76 分"。**

可复现性保证：

```
stock_code + as_of + engine_version + config_version  →  完全相同的输出
```

由 `tests/golden/test_golden_cases.py::TestGoldenStability` 校验（同输入三次调用结果一致）。

---

## 6. 错误处理

统一结构化错误（`apps/api/errors.py`）：

```json
{
  "error": {
    "code": "MARKET_PROVIDER_UNAVAILABLE",
    "message": "无法获取 600519 的行情数据",
    "detail": "ProxyError: ...",
    "retryable": true
  }
}
```

| 错误码 | HTTP | 含义 |
|---|---|---|
| `VALIDATION_ERROR` | 422 | 请求参数校验失败 |
| `INVALID_REQUEST` | 422 | 业务参数非法（如代码无法解析） |
| `BIRTH_PROFILE_ERROR` | 422 | 出生档案无法构造（如缺少数据源） |
| `STOCK_NOT_FOUND` | 404 | 股票不存在 |
| `NOT_FOUND` | 404 | 分析记录 / 实验不存在 |
| `MARKET_INSUFFICIENT_DATA` | 422 | 行情数据不足 |
| `MARKET_PROVIDER_UNAVAILABLE` | 503 | 第三方数据源不可达（含 detail） |
| `FUTURE_DATA_ACCESS` | 500 | 检测到未来数据访问（P0，不可重试） |
| `INTERNAL_ERROR` | 500 | 未捕获异常（日志已记录） |

---

## 7. 已知技术债

| # | 位置 | 问题 | 影响 | Phase 2 建议 |
|---|---|---|---|---|
| 1 | `src/core/stock/birth_profile.py` | 无独立交易日历表，交易日仅按周末规则 + 行情校验 | 节假日上市会被错误对齐 | 引入 `trading_calendar` 表 |
| 2 | `apps/api/routers/analysis.py::_load_label_rows` | 每次请求重算全库标签 | 慢（约 1–3 秒） | 标签落库 + 增量更新 |
| 3 | `src/research/event_study/engine.py` | 返回汇总统计而非全量样本 | UI 无法绘制真实直方图 | 增 `include_histogram` |
| 4 | `src/knowledge/` | 无 Embedding / FAISS，仅 BM25 | 语义召回弱 | 接入 sentence-transformers |
| 5 | `apps/web/lib/dataSource.ts::toDistribution` | 用正态近似绘制分布 | 图注已标"示意" | 改为真实分箱数据 |
| 6 | `src/factors/registry/compute.py` | 五行力量权重为工程近似 | 影响旺衰/用神判定 | 用 Golden Case 回测校准 |
| 7 | `apps/api/routers/research.py` | 研究流水线同步执行 | 大规模股票池会超时 | 引入任务队列（RQ/Celery） |
| 8 | 全局 | 无用户体系与权限 | 仅本地单用户 | Phase 2 若需多用户再加 |
| 9 | `src/engines/ziwei` 等 | 空目录占位 | — | Phase 2 实现 |

---

## 8. 扩展点（Phase 2 往哪里加）

| 要加的东西 | 应该放哪 | 需要实现 |
|---|---|---|
| 紫微斗数 | `services/ziwei-service`（TS/iztro）+ `src/engines/ziwei/` | `MetaphysicsEngine` + `ZiweiEngine` adapter |
| 六爻 / 奇门 | `src/engines/liuyao/` `/qimen/` | `MetaphysicsEngine` |
| 多模型融合 | `src/factors/fusion/` + `src/core/orchestration/` | 消费 `MetaphysicsOpinion` |
| 正式 Consensus / Conflict | `src/core/orchestration/consensus.py` | 替换展示层实现，`display_only` 改 `false` |
| LLM 解释层 | `src/narrator/` | 输入必须是 `EvidenceBundle`（结构化证据包） |
| 新行情源（如 Tushare） | `src/market/providers/` | `MarketDataProvider` |
| 新回测框架（vectorbt） | `src/research/backtest/` | `BacktestProvider` |
| 交易日历 | `src/core/stock/trading_calendar.py` + 新表 | 替换周末规则 |

---

## 9. 参考

* 总体架构（原始需求）：[`doc/architecture/architecture_v1.md`](doc/architecture/architecture_v1.md)
* 两会话实施计划：[`doc/architecture/two_session_plan_v1.md`](doc/architecture/two_session_plan_v1.md)
* UI/UX 规范：[`doc/architecture/uiux_spec_v1.md`](doc/architecture/uiux_spec_v1.md)
* 架构决策：[`docs/ADR/`](docs/ADR/)
* 交接文档：[`docs/HANDOFF_PHASE1.md`](docs/HANDOFF_PHASE1.md)
