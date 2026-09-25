# AGENTS.md · 股票玄学多模型研究平台

> 本文件是**给 AI 编程助手的强制规则**，并且是本仓库规则的**唯一权威源**。
> 任何在本仓库工作的 AI（Codex / Claude Code / ZCode / OpenCode / Qoder …）
> 在修改代码前必须先读完本文件。
>
> **Phase 2 不得破坏本文档中标注为「契约」的条目。**
>
> 分工：**本文件只写"当前必须遵守的事实与边界"**；
> "为什么这么设计、否决过什么、踩过什么坑、现在处在什么阶段"见
> [`.agents/notes/README.md`](.agents/notes/README.md)（索引 `docs/ADR/` 与 NOTE-001/002）。
> 按任务只读相关的 1–2 篇，**不要**无差别全量加载历史文档。
>
> 本文件**只追加、不重编号**：§1–§14 的编号被 20+ 处代码/测试注释直接引用
> （如 `AGENTS.md §2.4`、`§5`、`§9.7`）。新增规则一律从 §15 起挂。
> 若必须改历史章节，先开 ADR 并同步全部引用点。

---

## 0. 一分钟理解这个项目

```
第三方库负责"算盘"
  → 自研 Factor Engine 把盘变成可研究变量
  → Research 层验证这些变量有没有历史信息量
  → Knowledge Center 说明古籍依据
  →（Phase 2）Consensus Engine 判断多模型是否共振或冲突
  →（Phase 2）LLM 只负责把确定性结果解释成人能看懂的报告
```

**这不是荐股系统，是研究系统。**

---

## 1. 二十条铁律

1. 所有术数排盘必须由**确定性代码**产生，**禁止 LLM 计算**。
2. LLM 只能解释结构化结果，不得重新排盘、不得改分数。
3. 每个引擎必须保留 `raw_chart`，且必须落 `chart_artifact`。
4. 每个因子必须有唯一 `factor_id`。
5. 每个因子必须有 `rule_version`。
6. 每个结果必须记录 `engine_version`。
7. 所有历史测试必须遵守 `as_of`，**不得读取未来数据**（特征侧）。
8. 模型分歧不得被平均值隐藏。
9. 古籍必须带 `source` / `edition` / `provenance` / `license_status`。
10. 不得编造古籍条文。
11. 第三方代码必须通过 Adapter 接入。
12. **禁止在业务层直接依赖第三方对象**。
13. 所有第三方依赖必须锁版本。
14. 新术数必须实现 `MetaphysicsEngine` 接口。
15. 新行情源必须实现 `MarketDataProvider` 接口。
16. 新回测框架必须实现 `BacktestProvider` 接口。
17. 所有计算必须有单元测试。
18. 所有关键算法必须有 Golden Case。
19. **不允许因为"输出更好看"而修改计算结果。**
20. 所有结论必须可追溯到：盘面 → 因子 → 规则 → 证据。

---

## 2. 硬性契约（Phase 2 不得破坏）

### 2.1 六个核心接口

| 接口 | 路径 | 契约内容 |
|---|---|---|
| `MetaphysicsEngine` | `src/engines/base.py` | `metadata` / `calculate_chart` / `extract_factors` / `explain_rules` / `build_evidence_query` / `score` |
| `CalendarEngine` | `src/engines/calendar/calendar_engine.py` | 返回 `CalendarSnapshot`（本项目类型，非 lunar-python 对象） |
| `HuangliEngine` | `src/engines/huangli/huangli_engine.py` | 返回 `HuangliSnapshot`，含 `raw_huangli` |
| `BaziEngine` | `src/engines/bazi/bazi_engine.py` | 返回 `BaziChart`，含四柱/藏干/十神/旺衰/格局/喜用忌/刑冲合害/时间流 |
| `MarketDataProvider` | `src/market/providers/base.py` | `search` / `get_stock` / `get_daily_bars` / `get_benchmark_bars` |
| `KnowledgeProvider` | `src/knowledge/retrieval/provider.py` | `search(EvidenceQuery) -> EvidenceBundle`（**必须含 counter_evidence**） |
| `BacktestProvider` | `src/research/backtest/provider.py` | `evaluate_factor` / `evaluate_signal` / `evaluate_negative_controls` |

### 2.2 数据契约

* `StockBirthProfile` 字段：`stock_code` / `exchange` / `birth_basis` / `birth_datetime` /
  `timezone` / `source` / `birth_profile_version` / `assumptions` / `data_quality` / `variant_mode`。
* `FactorObservation` 字段：`factor_id` / `name` / `engine` / `category` / `raw_value` /
  `normalized_value` / `direction` / `rule_score` / `confidence` / `rule_version` /
  `evidence` / `explanation`。
* `FactorSet` / `EventStudyResult` / `NegativeControlReport` 的字段名与语义。

### 2.3 已公开 API

`/api/v1/**` 下的路径、请求体字段名、响应结构不得在不加版本号的情况下修改。
如果必须改，新增 `/api/v2/` 并保留 v1。

### 2.4 不可用语义

**任何不可用字段必须返回 `null` / `"unavailable"`，禁止用 `0` 冒充。**
（例：紫微自 Phase 2A 起已真实接入（ADR-0009），但服务不可用、或
`variant_mode = not_applicable` 使某类结果不成立时，仍必须返回
`available: false, score: null`，绝不允许 `score: 0`。
锁定该语义的测试：
`tests/timeline/test_time_windows.py::TestVariantInteraction::test_not_applicable_leaves_ziwei_unavailable_not_zero`。）

0 是一个真实数值，unavailable 是一个状态，两者语义不得混淆。

---

## 3. 分层与依赖方向

```
apps/web  →  apps/api  →  src/core/orchestration  →  engines / factors / research / market / knowledge
                                                        ↓
                                                      db / schemas
```

**禁止反向依赖**：

* `src/engines` 不得 import `apps/*`
* `src/factors` 不得 import `apps/*` 或行情模块
* `src/research` 不得 import `apps/*`
* 任何业务层不得 import `lunar_python` / `akshare`

以上由 `tests/test_third_party_isolation.py` 自动校验，**不要绕过它**。

---

## 4. 允许 `import lunar_python` / `import akshare` 的位置

```python
# 白名单（唯一允许的位置）
src/engines/calendar/calendar_engine.py     # lunar_python
src/engines/bazi/bazi_engine.py             # lunar_python（仅大运/胎元等辅助字段）
src/market/providers/akshare_provider.py    # akshare
```

新增位置必须先改测试白名单，并在 `THIRD_PARTY.md` 中说明理由。

---

## 5. 关于"股票无性别"

修改任何涉及运限的代码前，请重读这一节。

* 股票没有真实性别；
* **禁止**为了实现"完整功能"而默认填 `男命`；
* `variant_mode` 默认 `not_applicable`，该模式下**不输出大运**；
* 如必须计算顺逆，必须：
  1. 显式传入 `forward` / `reverse` / `both`；
  2. 写入 `assumptions`；
  3. 在输出中标注"运限推演基于假设规则"；
  4. **不得**将其纳入 Phase 1 的正式因子（需先回测）。

---

## 6. 关于 as_of

任何新增的特征计算路径都必须经过 `clip_to_as_of` / `visible_slice`。
新增标签计算必须放在 `src/research/labels/` 下，并且：

* 只能读 as_of **之后**的数据；
* 数据不足时 **raise** 或返回 `None`，**不得填 0**；
* 必须在 `LabelSet.horizon_available` 中标记可用性。

改完必须跑：

```bash
make test-leak
```

---

## 7. 关于因子

* 新因子必须有 `FactorDefinition`（含 `definition` / `computation` / `rule_score_meaning`）；
* `rule_score_meaning` **必须**声明"不代表预期收益率/上涨概率"；
* 新因子的 `explanation` 不得出现肯定式涨跌断言（`必涨` / `一定上涨` / `保证上涨` …）；
  否定式（"不代表股价一定上涨"）是允许的，测试会区分；
* 计算不出来时用 `_unavailable(...)`，返回 `availability="unavailable"`。

改完必须跑：

```bash
make test  # 含 tests/factors/
```

---

## 8. 关于古籍

* 只收**清代及以前**的公版原文；
* 现代整理本 / 白话翻译 / 注释本**一律不收**；
* 每条必须带 `provenance` / `edition` / `license_status`；
* `modern_note` 必须是本项目自撰，不得复制未授权的现代整理本文字；
* 检索必须同时返回支持与反证（`include_counter` 默认 `True`）。

---

## 9. 关于 UI

1. 页面风格必须偏**研究终端**，不做娱乐算命风。
2. 评分只是摘要，**原始盘面必须可见**。
3. 八字 / 黄历 / （Phase 2 的）紫微独立展示。
4. 共识与冲突必须同时支持。
5. **不允许用平均分掩盖冲突**。
6. 历史统计与术数判断必须视觉分区。
7. 任一模型失败不能拖垮整个页面。
8. 所有关键组件必须有 Loading / Empty / Error 状态。
9. 所有原始盘面组件必须独立封装。
10. 所有数据卡提供 source / version。
11. 所有图表必须有文本摘要。
12. **前端禁止重新计算术数**，只负责展示后端确定性数据。
13. 禁止 `background-image: url(reference.png)` 或把整页做成 `<img>`。
14. 演示数据只能放在 `lib/fixture.ts`，且必须由 `?fixture=ui-reference` 显式启用。

---

## 10. 修改流程

```
1. 读文档         README.md → ARCHITECTURE.md → 本文件 → 相关 docs/
2. 找测试         tests/ 下有没有对应测试？没有就先写
3. 改代码         最小必要变更，不要顺手重构
4. 跑测试         make test（P0 全绿才能继续）
5. 跑 UI 测试     make test-ui（如果改了前端）
6. 跑金案例       make test-golden（如果改了引擎或规则）
7. 更新版本号     改了引擎/规则 → 提升 engine_version / rule_version
8. 更新文档       受影响 docs/ + docs/HANDOFF
```

---

## 11. 版本号提升规则

| 改动类型 | 需要提升 |
|---|---|
| 排盘逻辑、历法口径 | `calendar_engine_version` 或 `bazi_engine_version` |
| 因子判定规则、权重 | `factor_rule_version` |
| 出生档案推导方式 | `birth_profile_version` |
| 全局配置默认值 | `config_version` |
| 古籍语料增删 | `knowledge_version` |
| 行情源或复权方式 | `market_data_version` |

**不提升版本号 = 未来无法解释"为什么同一只股票上个月算 83 分，今天变成 76 分"。**

---

## 12. Golden Case 失败时怎么办

**不要直接改期望值。**

```
1. 判断：是第三方库升级导致的口径变化，还是代码 bug？
2. 如果是 bug → 修代码
3. 如果是口径变化 →
   a. 写入对应阶段的差异登记（`docs/calculation-differences-phase1.md` /
      `docs/calculation-differences-phase2-ziwei.md` / `docs/calculation-differences-relation.md`）
   b. 提升对应 engine_version
   c. 重新生成全部 Golden Case 期望值
   d. 全量回归
```

`tests/golden/test_golden_cases.py` 中还有**结构性不变量**测试
（日柱 60 甲子推进、年柱一年一变、月柱一年十二变、五鼠遁时柱），
这些比逐点期望值更能发现"整体错位"类错误，**不要删除**。

---

## 13. 禁止事项

```
✗ 让 LLM / 手算代替确定性排盘
✗ 在业务层 import lunar_python / akshare
✗ 放弃 raw_chart，只存分数
✗ 用 0 表示"不可用"
✗ 隐藏模型分歧
✗ 用平均值掩盖冲突
✗ 用全部历史数据调参后宣布预测有效
✗ 伪造古籍条文或引用未授权整理本
✗ 把降级/合成数据伪装成真实数据
✗ 未经回测就把"财星/三合/食伤生财"解释成利好
✗ 删除或弱化负对照
✗ 在没有 ADR 的情况下修改已公开 API 契约
```

---

## 14. 参考

* 总体架构：[`doc/architecture/architecture_v1.md`](doc/architecture/architecture_v1.md)
* 两会话计划：[`doc/architecture/two_session_plan_v1.md`](doc/architecture/two_session_plan_v1.md)
* UI 规范：[`doc/architecture/uiux_spec_v1.md`](doc/architecture/uiux_spec_v1.md)
* 视觉真值：[`doc/ui-reference/*.png`](doc/ui-reference/)
* Phase 1 交接：[`docs/HANDOFF_PHASE1.md`](docs/HANDOFF_PHASE1.md)（历史）
* Phase 2 交接：[`docs/HANDOFF_FINAL.md`](docs/HANDOFF_FINAL.md)
* 规则/决策/笔记分工与索引：[`.agents/notes/README.md`](.agents/notes/README.md)
* 环境与命令实测值：[`.agents/notes/NOTE-001-development-test-and-ci.md`](.agents/notes/NOTE-001-development-test-and-ci.md)
* 阶段事实快照：[`.agents/notes/NOTE-002-current-project-state-2026-09-23.md`](.agents/notes/NOTE-002-current-project-state-2026-09-23.md)

---

## 15. 证据优先级（信息冲突时怎么判）

本项目**事实**的权威顺序：

```
当前运行代码 / Schema / Migration
      ↓
自动化测试与 Golden Cases
      ↓
机器可验证配置与 CI（.github/workflows、pyproject、config/*.json）
      ↓
已接受 ADR（docs/ADR/）
      ↓
正式技术文档（docs/*.md、ARCHITECTURE.md、THIRD_PARTY.md）
      ↓
README / 阶段报告 / 交接文档 / 记忆与提示词
```

冲突时**禁止** silently 选择对自己改动最方便的一种解释。必须：

1. 指出冲突，给出具体文件与行号/字段；
2. 判定哪个是 current fact、哪个是 stale documentation（`README.md` 与 `HANDOFF_*` 已知滞后，
   见 NOTE-002 G6）；
3. 未获授权前不做高风险语义迁移（改契约、改口径、改结论）；
4. **提示词、任务书、记忆里的"现状"一律不是事实** —— 开工前重新 `git` / `gh` / 读码核实。

## 16. 研究语义与结论边界（§1 铁律的补充）

完整决策依据见 [`docs/ADR/ADR-0013-research-validity-boundary.md`](docs/ADR/ADR-0013-research-validity-boundary.md)。

1. **概念不得互相指代**：传统规则方向 / `rule_score`（规则强度）/ 结构强度 / 模型间共识 /
   历史统计关系 / 未来收益 / 交易建议，是七件不同的事。
   禁止把 `财星 / 食神生财 / 三合 / 六合 / 黄道 / 紫微方向 / 多模型共振`
   直接说成"会上涨 / 上涨概率更高 / 适合买入 / 未来收益为正"。
2. **Consensus ≠ 历史有效性**：允许并预期真实输出"共识很高 + 历史无显著信号"
   （`ResearchStatus = NO_SIGNAL`）。不得为了产品体验把无信号包装成有效信号。
3. **负结果是合法结果**：`SUPPORTED_OUT_OF_SAMPLE = 0`、`MULTI_ENGINE_NO_SIGNAL` 这类结论
   **不得**通过改样本、改窗口、改定义、偷换基准、删除失败实验、只展示有利子集来"修复"。
   研究代码可以改进，研究结论不能因为不好看而改。
4. **synthetic / synthetic_demo 严格隔离**：只用于开发、UI 演示、联调、降级测试；
   必须带来源与 `is_degraded` 标记；不得冒充真实行情、不得进入正式研究证据、
   不得在报告中省略来源。`ResearchStatus` 与 `DEGRADED_SOURCES` 见 `src/research/status.py`。
5. **禁止偷偷补充研究假设**：股票不是人。除 §5 的性别外，任何现实不存在的属性都不得由 AI 补值。
   假设必须显式记录（`assumptions`）、版本化、可切换、可独立回测。
6. **原始盘面是一等数据**（§1 铁律 3 的落地约束）：不得为省事把
   `chart_artifact` / `raw_chart` / `engine_version` / `config_version` / `birth_profile_version`
   扁平化成一个分数。
7. 表述层红线：`rule_score_meaning` 必须声明"不代表预期收益率/上涨概率"；
   任何输出（含 LLM 解释）不得出现肯定式涨跌断言。

## 17. 分层职责（§3 依赖方向之外，谁能做什么）

| 层 | 职责 | 禁止 |
|---|---|---|
| `apps/api` | FastAPI，唯一对外出口（`/api/v1/**`） | 为绕开 UI 问题直接把内部对象当公共 Schema 暴露 |
| `apps/web` | Next.js 展示与交互 | 在前端重新实现八字/黄历/紫微/研究算法（§9.12） |
| `src/core/orchestration` | 唯一业务编排入口 | 被引擎层反向依赖 |
| `src/engines` | 确定性排盘与规则内核 | 非确定性输入（随机、时间、网络）参与排盘结果 |
| `src/core/relations` | 干支关系矩阵与目录 | 让统计需求反向改关系口径 |
| `src/factors` | 因子定义与计算 | 用历史结论倒推因子规则（先回测，后改口径） |
| `src/research` | 事件研究、标签、负对照、多重检验、OOS 门 | 用统计结论反向污染传统规则计算 |
| `src/market` | 行情来源、归一化、`as_of` 裁剪、缓存、降级 | 让降级/合成数据失去可追踪标记 |
| `src/knowledge` | 古籍检索（支持 + 反证） | 检索只返回支持证据 |
| `src/narrator` | 模板优先解释，LLM 输出必须过 `guard.py` | LLM 参与任何计算（§1.1） |
| `src/db` + `migrations` | SQLAlchemy 模型 + Alembic | 只改 ORM 不改 migration |
| `services/ziwei-service` | Node + iztro 第三方能力 Adapter | API 层依赖 iztro 内部对象结构 |
| `tests/` | 契约、Golden、泄漏、隔离、集成回归 | 用 `xfail` / `skip` 让失败静默（§21） |
| `docs/` | 方法论、口径差异、阶段报告 | 用文档措辞掩盖实测结果 |

## 18. 工作树保护与 Git 安全

**动手前先记录**：

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --name-only && git diff --cached --name-only
```

用户已有的未提交修改 = **用户资产**：只记录，不覆盖、不 restore、不 stash、不 reset、
不 checkout 覆盖、不 clean、不顺手加入本次提交。

**绝对禁止**（除非用户逐项明确授权）：

```
git reset --hard / git restore . / git checkout -- . / git clean -fd[x] / git stash
```

另外：

* 测试会改脏被跟踪的 `__pycache__/*.pyc`（本仓库有 94 个 `.pyc` 在版本控制中）——
  收尾前把**这些自己产生的**变更按路径还原，不要留在提交里；
* 本分支存在**并行会话**（同一分支被其他会话提交/强推过）。汇报里的 HEAD 值必须临场重取；
* 不得顺手格式化与任务无关的文件、不得顺手升级依赖、不得顺手修 unrelated issue。

## 19. 任务作用域纪律

每个任务先写清 `IN SCOPE` / `OUT OF SCOPE`，只改完成该任务**最少必要**的文件。

调查中发现的别的问题，一律登记为

```
Finding / Known gap / Follow-up / ADR candidate
```

写进 NOTE 或汇报，**不要直接扩大施工范围**。
禁止"既然看到了，就顺手重构一下"。

## 20. Commit / Branch / PR 治理

默认允许：读、分析、改当前任务文件、跑测试。
默认**禁止**（只有用户明确要求才做）：`commit`、`push`、`merge`、`rebase`、`deploy`、`squash` 用户历史、
force push、改写已推送的公共历史。合并方式不由 AI 自行决定。

* 一个逻辑工作包一个 commit；commit message 必须描述真实变化；
* 中文提交说明用 `git commit -F <file>`，避免 shell 引号/编码问题；
* 不得把多个无关修改塞进同一 commit；不得为绿 CI 修改与任务无关的逻辑；
* **仓库对公网可见**：提交前自查 `deploy/`、`data/`、日志里的地址、路径、凭据（§13 + 本机规范）。

## 21. 验证矩阵（改什么，跑什么）

本机 `make` 未安装，下面命令须在 Git Bash 直接展开执行（完整清单见 NOTE-001）。

| 改动类型 | 必跑 |
|---|---|
| Python 核心 / API | `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <目标>` → 再按范围升到 `-m "not ziwei_live"` 全量 |
| market / factor / label / research / backtest / timeline / as_of / cache | `pytest tests/test_no_future_data_access.py -v`（+ `tests/research/test_asof_*`、`test_oos_no_leak.py`）。**该测试不存在时必须报缺口，不得宣称"无未来数据问题"** |
| 引擎 / 规则 / 因子定义（bazi、huangli、calendar、ziwei、relation） | `pytest -m golden -v` + 对应引擎与因子测试 + 跨引擎核对；并提升 `rule_version` / `engine_version`（§11） |
| 前端 | `npm run typecheck` + `npm run build`；交互变化跑对应 Playwright spec |
| 紫微链路 | Node build → 通道真实可用（transport 断言，不许 silent skip）→ Python adapter → Golden → 跨引擎 |
| 第三方库升级 | 全量 Golden + `tests/test_third_party_isolation.py`；口径变化按 §12 处理 |

**Golden 期望值失败**：不得直接改期望值。必须回答"为什么旧结果是错的"，
而不是"为什么新代码更方便"。结构性不变量测试（日柱 60 甲子推进、年柱一年一变、
月柱一年十二变、五鼠遁时柱）不得删除。

**视觉回归单独管理**：只有当任务本身就是 UI 视觉校准、或用户明确要求、或本阶段把 visual
定义为 blocking gate 时，它才是本任务的硬门。**不得**因为独立视觉基线失败把无关任务扩大成视觉整改；
但也**不得**删除、伪造或隐藏真实 visual FAIL —— 记录后交给独立工作包（当前处置见 NOTE-002 §2）。

验证等级要如实标注：`Level 1 快查` / `Level 2 相关测试` / `Level 3 完整 CI`。
功能完成 ≠ 验证完成 ≠ 生产可用。

## 22. CI 状态判定口径

不得根据 README、PR 描述或记忆判断 CI。必须看当前 commit 的实际 workflow run 与
**每个 job 的 conclusion**：

```bash
gh pr checks <PR>            # 或
gh run list --branch <branch> --limit 5 && gh run view <run-id>
```

必须区分 `local PASS` / `CI PASS` / `CI SKIPPED` / `CI NOT RUN` / `CI FAILURE`；
不得把 `not run` 写成 `pass`，也不得把一个 job 失败笼统说成"CI 全挂"。
最终报告必须列明**具体失败 job 名**与 run/attempt 链接。

## 23. 公共 API / Schema / Migration 变更流程

改 `/api/v1/**` 之前先搜齐：request schema、response schema、前端消费点、集成测试、OpenAPI 契约。
未经明确授权不得改：路径、字段名、`nullability`、enum 语义、错误码结构（§2.3）。
必须改时：新增 `/api/v2/` 并保留 v1，且**先写 ADR**（§13 最后一条）。

数据库字段变化必须有 Alembic revision（`make migration` 等价命令：
`python -m alembic revision --autogenerate -m "..."`）；
不得破坏既有历史数据可读性，若不兼容必须写明迁移/回滚策略。

## 24. 正式研究结论的证据清单

一份结果要被称为"正式验证"，必须能回答：

```
commit / 数据源 / 数据版本 / 时间范围 / universe / 样本量 /
参数 / rule_version / engine_version / 是否含 synthetic /
是否做泄漏检查 / 有哪些负对照 / 哪些测试通过、哪些失败
```

缺项只能表述为"初步观察"。
（阈值解锁条件见 `src/research/multipletesting/gate_v2.py`；负对照见 §13 与 ADR-0013。）

## 25. 文档分工与 ADR 状态词

```
AGENTS.md（本文件） = 当前必须遵守的规则        —— 只追加、不重编号
docs/ADR/           = 持久架构决策（唯一编号源） —— 为什么这么设计
.agents/notes/NOTE-* = 阶段性事实、事故、坑、环境 —— 必须带 As-of
docs/*.md           = 方法论与实测报告
```

禁止把历史讨论堆进本文件；禁止在 `.agents/notes/` 下另建一套 ADR 编号。
如果未来需要 `CLAUDE.md` / `CODEX.md` 等适配层，只能写成指回本文件的薄指针，
**不得复制整套规则**。

ADR 状态词只有四个：`Draft` / `已接受(Accepted)` / `Superseded` / `Rejected`。
**只有代码 + 测试 + 证据已经证明实施的决策才标 `已接受`**；未落地的一律 `Draft`。
NOTE 的结论被新实测推翻时：**新开一篇**，旧篇写 `Status: superseded` + `Superseded-by:`，
不得原地改写历史判断。

## 26. 停止条件（遇到就停下报告，不要绕门）

```
仓库身份与预期不一致（remote / branch / HEAD 与任务描述不符）
目标文件已有用户未提交修改，且与本任务冲突
当前实现与正式契约冲突，且无人授权决定语义
发现未来数据泄漏风险
发现数据来源无法证明（provider / version / universe 追不到）
需要破坏 API 兼容性
需要重写 migration 历史
需要 reset / clean / force push / 删分支
Golden Case 出现无法解释的变化
测试失败原因尚未定位
任务范围需要明显扩大
并行会话正在改动同一批文件
```

停止 ≠ 任务失败。正确行为是**保存证据并报告**，不是绕过硬门继续推进。
