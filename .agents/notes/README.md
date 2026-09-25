# .agents/notes · 项目知识库入口

> 本目录是**给 AI 编程助手用的知识地图**，不是规则源，也不是 ADR 编号源。
> 规则在 `AGENTS.md`；架构决策在 `docs/ADR/`；本目录只放**索引**和**操作性/阶段性笔记（NOTE）**。

---

## 一、三类文档的分工（不许混）

| 类型 | 位置 | 回答什么 | 可变性 |
|---|---|---|---|
| **AGENTS.md** | 仓库根 | 当前**必须遵守**的项目事实、硬约束、操作规约 | 稳定；只追加、不重编号（代码里 20+ 处按 `§编号` 引用它） |
| **ADR** | [`docs/ADR/`](../../docs/ADR/) | **为什么这么设计**、被否决的方案、不可逆决策 | 一次决策一篇；状态只有 `Draft` / `已接受` / `Superseded` / `Rejected` |
| **NOTE** | 本目录 | **阶段性事实**、事故复盘、坑、环境与操作经验 | 会过期；每篇必须有 `As-of`；结论被推翻按 §四 处理 |

**硬性边界**：

1. **ADR 编号只有一个源**：`docs/ADR/ADR-0NNN-*.md`。本目录**不得**再建第二套 ADR 编号空间
   （历史背景：2026-09-23 初始化本目录时，仓库已有 ADR-0001…0012；某外部任务书要求在
   `.agents/notes/` 下另建 `ADR-001…003`，会造成两套编号竞争，已明确否决）。
2. 本目录与 NOTE 里**禁止**出现密钥、API Key、账号可用性、服务器地址与口令——那些属于
   开发者本机记忆，不进仓库。
3. NOTE 可以写"当前 CI 实测是什么样"，但**不能**取代 ADR 表达设计决策。
4. 代码回答"现在是什么"；ADR 回答"为什么如此、哪些边界不能改"；NOTE 回答"现在处在什么阶段、
   踩过什么坑、哪些结论已被实测推翻"。

---

## 二、架构决策索引（正文在 `docs/ADR/`）

| ADR | 一句话内容 | 什么时候必须读 |
|---|---|---|
| [0001](../../docs/ADR/ADR-0001-adapter-isolation.md) | 第三方引擎必须经 Adapter 隔离 | 接触 `lunar_python` / `akshare` / `iztro` 或新增依赖 |
| [0002](../../docs/ADR/ADR-0002-bazi-engine-backend.md) | Phase 1 八字用自研确定性内核，bazi-pro 为可插拔后端 | 改八字引擎前 |
| [0003](../../docs/ADR/ADR-0003-no-gender-variant-mode.md) | 股票无性别 → `variant_mode`，默认 `not_applicable` | 任何涉及运限/大运的代码 |
| [0004](../../docs/ADR/ADR-0004-as-of-time-isolation.md) | `as_of` 单向时间隔离与未来数据泄漏防护 | 改 market / factors / labels / research / backtest / timeline / cache |
| [0005](../../docs/ADR/ADR-0005-sqlite-duckdb-storage.md) | SQLite 主库 + DuckDB/Parquet 研究层 | 改存储、导出研究面板数据 |
| [0006](../../docs/ADR/ADR-0006-ui-fixture-mode.md) | UI fixture 模式与生产 runtime 分离 | 改前端数据源、演示数据 |
| [0007](../../docs/ADR/ADR-0007-red-up-green-down.md) | 涨跌配色按 A 股惯例（红涨绿跌），覆盖 UI 规范文档 | 改前端配色/视觉语义 |
| [0008](../../docs/ADR/ADR-0008-bazi-engine-strategy.md) | 自研内核为 Canonical，bazi-pro 仅作 Phase 2 参考 | 有人想引入外部八字库时（先读这篇） |
| [0009](../../docs/ADR/ADR-0009-ziwei-engine-iztro.md) | 紫微采用 iztro：Node 服务 + Python Adapter | 改紫微链路（服务 / transport / adapter） |
| [0010](../../docs/ADR/ADR-0010-ziwei-no-gender-variant.md) | 紫微"无性别"用方向 variant 表达，不做性别默认 | 改紫微排盘参数或因子 |
| [0011](../../docs/ADR/ADR-0011-consensus-not-averaging.md) | Consensus 禁止简单平均，冲突必须显式保留 | 改共识/冲突/聚合逻辑或相关 UI |
| [0012](../../docs/ADR/ADR-0012-phase3a-astockdata-canonical.md) | Phase 3A 主数据源切换（含退市股，根治 survivorship bias） | 改行情导入、universe、复算历史面板 |
| [0013](../../docs/ADR/ADR-0013-research-validity-boundary.md) | 研究有效性边界：规则强度≠市场预测，负结果是合法结果 | 写任何结论文案、改阈值/负对照/多重检验、被要求"让结论更好看" |

---

## 三、NOTE 索引

| NOTE | 一句话内容 | As-of |
|---|---|---|
| [NOTE-001](NOTE-001-development-test-and-ci.md) | 本机开发/测试/CI 的真实可跑命令、环境坑与门禁清单 | 2026-09-23 |
| [NOTE-002](NOTE-002-current-project-state-2026-09-23.md) | 阶段事实快照：分支/PR/CI/视觉/研究结论/仍成立的缺口 | 2026-09-23 |

---

## 四、运转契约

**读（三跳，禁止全量载入）**

1. 读 `AGENTS.md` 的全局红线；
2. 用本文件的索引定位到 1–2 篇 ADR / NOTE（或让 AI 用仓库检索定位）；
3. 只读命中的那几篇，重点吸收 ADR 的"被否决方案"和 NOTE 的"事故/坑"，再动手。

不需要、也不允许把 `docs/` 下 50+ 篇报告一次性塞进上下文。

**写（强同步）**

改 DDL / migration、状态机、计算公式、核心入参签名、公共 API 字段、或重命名模块 →
**同一个提交内**更新对应 ADR/NOTE 正文与其"代码落地点"，并刷新本索引行与 `As-of`。
`As-of` 是"最后一次对照代码核实"的日期，不是撰写日期。

**结论被推翻时**

不在旧 NOTE 里原地改判断。**新开一篇**，旧篇顶部写 `Status: superseded` 与
`Superseded-by: <文件名>`，并在两篇里都保留新旧结论各自的证据出处。
历史判断链本身就是防御信息，覆盖掉就没了。

**门禁（当前状态）**

本仓库**尚未**引入 `.agents/scripts/check_notes.mjs` 之类的结构门禁脚本
（2026-09-23 初始化时明确推迟，避免与业务任务混提交）。当前生效的机器门禁仍只有：
`tests/test_third_party_isolation.py`、`tests/test_no_future_data_access.py`、
`tests/golden/*`、`tests/factors/*`。若未来引入 Note 结构门禁，需单开一个提交并在此登记。
