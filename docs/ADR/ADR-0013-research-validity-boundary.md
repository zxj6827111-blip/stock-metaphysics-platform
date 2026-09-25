# ADR-0013：研究有效性边界（规则强度 ≠ 市场预测）

- **状态**：已接受（Phase 4 之后追加为总纲；决策本身早已在代码/测试中落地）
- **日期**：2026-09-23
- **影响**：Factor 层、Consensus / Conflict、Research 层、Narrator、UI、对外文案
- **关联**：[ADR-0004](ADR-0004-as-of-time-isolation.md)（时间隔离）、[ADR-0011](ADR-0011-consensus-not-averaging.md)（禁止平均）、[ADR-0001](ADR-0001-adapter-isolation.md)（Adapter 隔离）、[ADR-0003](ADR-0003-no-gender-variant-mode.md)（股票无性别）

## 背景

本平台的输入是传统术数规则，输出对象是股票历史数据。这两者一旦进入同一个产品，
就存在一条持续存在的滑坡：**把"传统规则认为吉"读成"股票要涨"**。

滑坡在工程上有三个具体入口：

1. **分数语义漂移** —— `rule_score` 是 0–100 的数字，前端展示、LLM 复述、用户转述时
   会被自然理解成"概率"或"预期收益"；
2. **共识被当成证据** —— 三个模型方向一致，看起来"更像真的"，但共识只是规则之间的
   一致性，与历史有效性无关；
3. **结论不好看就被修** —— 改窗口、换基准、删失败实验，比如实报告"没有信号"更省事。

Phase 3 的实测把第三条逼到了明面上：42 个正式 gate 实验，族内 BH-FDR 通过 **0** 个，
`SUPPORTED_OUT_OF_SAMPLE = 0`，多引擎共振为 `MULTI_ENGINE_NO_SIGNAL`
（见 [`docs/PHASE3_RESEARCH_REPORT.md`](../PHASE3_RESEARCH_REPORT.md)）。
如果"能出正结论"是系统目标，这份报告本身就会被视为待修 bug。

因此需要一篇 ADR 把"什么算有效结论、什么话不允许说"定成不可协商的边界，
而不是散落在各文档的提醒里。

## 决策

### 1. 七个概念必须分层，禁止互相指代

```
传统规则方向     → 术数体系认为的吉凶方向
rule_score      → 传统规则强度（0–100），不是收益率、不是概率
传统结构强度     → 盘面结构本身的分量（与市场无关）
模型间共识       → 多套规则在**同一输入**下方向是否一致
历史统计关系     → 在已声明样本与协议下，特征与未来收益是否可复现相关
未来收益         → 标签侧，只能在 as_of 之后计算
交易建议         → 本平台不输出
```

`rule_score → 上涨概率`、`共识 → 历史有效`、`吉 → 适合买入` 这三条推断链在本系统内**一律禁止**。

### 2. 分数语义必须写进数据，不能只写在文档里

每个 `FactorDefinition` 必须携带 `rule_score_meaning`，显式声明"不代表预期收益率/上涨概率"；
`explanation` 不得出现肯定式涨跌断言（`必涨` / `一定上涨` / `保证上涨`）。
该约束由测试锁定，不是措辞建议：见 [`tests/factors/test_factor_calculation.py`](../../tests/factors/test_factor_calculation.py)
与 [`tests/engines/test_ziwei_engine.py`](../../tests/engines/test_ziwei_engine.py)。

### 3. 共识与历史有效性在结构上是两个字段

沿用 ADR-0011：`ConsensusSnapshot` 同时携带 `label`/`agreement_score`（模型之间是否一致）
与 `research_status`（这种一致历史上是否有支持）。
"高共识 + `NO_SIGNAL`" 是**合法且常见**的正常输出，不是待修状态。

### 4. 负结果是合法结果，结论不因"不好看"被修改

`ResearchStatus` 是显式枚举（[`src/research/status.py`](../../src/research/status.py)）：
`NOT_RUN` / `NO_REAL_DATA` / `INSUFFICIENT_SAMPLE` / `INVALID_CONTROL` / `NO_SIGNAL` /
`INCONCLUSIVE` / `WEAK_EVIDENCE` / `SUPPORTED_IN_SAMPLE` / `OOS_CANDIDATE_SUPPORTED` /
`EXPLORATORY_NOT_GATED` / `SUPPORTED_OUT_OF_SAMPLE`。

允许改进研究代码；**不允许**通过改样本、改窗口、改定义、偷换基准、删除失败实验、
只展示有利子集来"修复"结论。`SUPPORTED_OUT_OF_SAMPLE` 只能由
`gate-v2`（[`src/research/multipletesting/gate_v2.py`](../../src/research/multipletesting/gate_v2.py)）
的 A–L 十二项条件解锁，其中包含负对照有效性与多重检验校正。

负对照不是可选项：`MIN_SUPPORTED_SAMPLE = 30`、`JACCARD_INVALID_THRESHOLD = 0.9`
（真实组合与随机对照重合度过高即判 `INVALID_CONTROL`），测试见
[`tests/research/test_negative_controls.py`](../../tests/research/test_negative_controls.py)。

### 5. 合成/降级数据永远不能作为研究证据

`DEGRADED_SOURCES = {"synthetic_demo", "synthetic"}`（同文件）。
synthetic 只允许用于开发、UI 演示、联调、降级测试；进入研究流水线必须被拒绝，
由 [`tests/research/test_synthetic_never_research_evidence.py`](../../tests/research/test_synthetic_never_research_evidence.py) 锁定。
universe 与时间点纪律另见 `tests/research/test_point_in_time_universe.py`、
`tests/research/test_universe_query_discipline.py`。

### 6. LLM 只做解释，且只能读受控数据

排盘、因子、标签、统计全部由确定性代码产生。Narrator 只能消费 `EvidenceBundle`，
输出必须通过幻觉守卫 [`src/narrator/guard.py`](../../src/narrator/guard.py)：
"历史验证有效 / 统计上显著 / 胜率较高"只允许出现在 `SUPPORTED_IN_SAMPLE` /
`SUPPORTED_OUT_OF_SAMPLE` 状态下；`NO_SIGNAL` 等状态必须配对应的否定文案。
守卫测试见 [`tests/knowledge/test_narrator.py`](../../tests/knowledge/test_narrator.py)。

### 7. 真实研究结论必须自带可复现证据

一份结果要被称为"正式验证"，必须能回答：commit、数据源、数据版本、时间范围、
universe、样本量、参数、`rule_version`、`engine_version`、是否含 synthetic、
是否做了泄漏检查、有哪些负对照、哪些测试通过/失败。
缺任一项 → 只能表述为"初步观察"。

## 后果

**正面**

* "无信号"成为可交付结论，Phase 3/4 的零支持结果不需要被包装；
* 分数语义、共识语义、负对照有效性都在 schema 与测试里，不依赖人的自觉；
* 对外文案有机器可判的白名单，Narrator 无法自行拔高结论。

**负面 / 代价**

* 系统大多数研究分支的真实输出是"没有统计支持"，产品观感弱于同类"预测软件"；
* 任何"想证明有效"的改动都必须走 gate-v2，迭代成本显著高于放宽阈值；
* UI 需要同时呈现"传统规则判断"和"历史统计"两个分区，信息密度高。

## 不适用范围

本 ADR 不禁止研究**假设**本身（如 `variant_mode` 的顺逆推演、出生基准候选集）。
它要求的是：假设必须显式记录、版本化、可切换、可独立回测，
且不得在结论层被静默当作事实。见 ADR-0003 / ADR-0010。
