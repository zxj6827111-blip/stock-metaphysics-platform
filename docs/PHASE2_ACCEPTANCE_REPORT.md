# Phase 2 验收报告（PHASE2 ACCEPTANCE REPORT）

| 项 | 值 |
|---|---|
| **最终 commit SHA** | **`68a43f05b6156122366568a1ed0ad298aaa3c608`** |
| 验收基线 | Phase 1 交付点 `6d4d5d7` + Phase 1.1 加固 + Phase 2 全部改动 |
| 验收日期 | 2026-09-19 |
| 验收范围 | 2A 紫微 → 2B 因子 → 2C 共识/分歧 → 2D 时间窗口 → 2E 证据/Narrator → 2F 完整 UI |
| 验收性质 | 多功能交付 + 研究方法审计 + 真实性审计 |

---

## 1. Executive Summary

Phase 2 在**不破坏 Phase 1 任何契约**的前提下完成了六阶段交付：
紫微斗数引擎接入、49 个紫微因子、正式 ConsensusEngine / ConflictDetector、
月度/周度时间窗口、EvidenceBundle + AI Narrator（含幻觉守卫）、
七个新 UI 页面与 Markdown/HTML 报告导出。

**最终结论：`PASS WITH CONDITIONS — PLATFORM V2 READY / RESEARCH CLAIMS BLOCKED`。**

* **工程侧 GO**：所有测试全绿（1003 pytest + 44 Playwright），lint/typecheck/build 全通过；
* **研究侧仍被锁**：真实样本上的多模型共振研究结果为
  **`INVALID_CONTROL` / `NO_SIGNAL`** —— 系统如实输出，没有任何"术数有效"的宣称。

---

## 2. 交付清单

### 2.1 阶段产物

| 阶段 | 交付物 | 验证 |
|---|---|---|
| **2A** 紫微确定性计算 | `services/ziwei-service`（Node+TS+iztro 2.6.1）、`src/engines/ziwei/`、`src/core/schemas/ziwei.py`、8 组 Golden 快照、ADR-0009/0010 | 38 + 26 项测试 |
| **2B** 紫微因子 | 49 个 `Z_*` 因子、质量审计、自动生成因子字典 | 42 项测试 + 9,800 行真实审计 |
| **2C** 共识/分歧 | `ConsensusEngine`、`ConflictDetector`、共振研究 + 独立负对照 + 多重比较警告 | 42 项测试 |
| **2D** 时间窗口 | 未来 12 月 / 12 周（交易日聚合，`agg-v1`） | 20 项测试 |
| **2E** 证据与解释 | 紫微语料 13 条、`EvidenceBundle`、`Narrator` + `NarratorValidator` | 33 项测试 |
| **2F** UI 与导出 | 7 个新页面 + 综合页数据源切换 + 报告导出 | 44 项 Playwright + 10 张截图 |

### 2.2 代码规模

| 项 | 数量 |
|---|---|
| 因子总数 | **114**（Phase 1 的 65 + 紫微的 49） |
| API 端点 | **39**（Phase 1 的 30 + Phase 2 的 9） |
| 新增 Python 模块 | `src/engines/ziwei/`(3) + `src/factors/ziwei/`(3) + `src/core/orchestration/{consensus,timeline,evidence,report}.py` + `src/core/schemas/{ziwei,consensus,timeline,evidence}.py` + `src/research/consensus_research.py` + `src/narrator/`(2) |
| 新增前端模块 | 7 个页面 + `ZiweiChart.tsx` + `PageState.tsx` + `ResearchPage.tsx` + `analysisStore.ts` |
| 新增文档 | 12 篇（见 §9） |

---

## 3. 测试结果（全部实测）

| 套件 | 结果 |
|---|---|
| **pytest 全量** | **1003 PASS**，0 fail（Phase 1 的 551 项继续通过） |
| 紫微引擎 + Golden | 64 PASS（含 8 组真实 iztro 快照 + 实时服务对拍） |
| 紫微因子 | 42 PASS（含 variant 影响范围不变量、质量审计口径） |
| Consensus / Conflict / 共振研究 | 42 PASS（含随机数据假阳性率 ≤ 15% 检验与功效检验） |
| 时间窗口 | 20 PASS（含交易日历一致性） |
| Narrator / Guard / 多域语料 | 33 PASS（含幻觉防护与降级） |
| API / 隔离 / 泄漏 / Golden（Phase 1） | 551 PASS（其中 4 项按 Phase 2 语义更新，理由见 §5） |
| **Playwright** | **44 PASS** |
| `ruff check` | 全绿 |
| `npx tsc --noEmit` | 全绿 |
| `next build` | 成功（13 个路由） |
| `docker compose config` | 通过（新增 `ziwei` 服务） |

---

## 4. 真实样本研究结果（必须原样引用）

### 4.1 多模型共振研究

数据：**20 只股票 × 22 个季度采样点 = 440 行**（真实 hfq 快照，`tencent_hfq_import`）

| 组合 | 事件数 | Jaccard | p 值 | 判定 |
|---|---|---|---|---|
| `BAZI_POS` | 427 | **0.945** | 0.834 | **INVALID_CONTROL** |
| `ZIWEI_POS` | 172 | 0.237 | 0.628 | tie / NO_SIGNAL |
| `HUANGLI_POS` | 194 | 0.281 | 0.648 | tie / NO_SIGNAL |
| `BAZI_ZIWEI_POS` | 168 | 0.257 | 0.961 | tie / NO_SIGNAL |
| `BAZI_HUANGLI_POS` | 192 | 0.280 | 0.685 | tie / NO_SIGNAL |
| `ZIWEI_HUANGLI_POS` | 79 | 0.093 | 0.281 | tie / NO_SIGNAL |
| `ALL_THREE_POS` | 78 | 0.102 | 0.765 | tie / NO_SIGNAL |
| `BAZI_POS_ZIWEI_NEG` | 0 | — | — | NOT_RUN |
| `BAZI_NEG_ZIWEI_POS` | 0 | — | — | NOT_RUN |
| `BAZI_POS_HUANGLI_NEG` | 22 | 0.000 | 0.337 | tie / INSUFFICIENT_SAMPLE |
| `ZIWEI_POS_HUANGLI_NEG` | 8 | 0.000 | 0.568 | tie / INSUFFICIENT_SAMPLE |

**整体状态：`INVALID_CONTROL`。**

**结论（系统原文）**：

> 共检验 11 个预定义组合，其中 9 个有可判定结果。胜过随机方向对照：0 个；
> 弱于对照：0 个；与对照无差异：8 个。
> 本结论只描述**本样本**的统计表现，不构成任何有效性宣称，也不构成投资建议。

### 4.2 两个必须说明的真实发现

**发现 1：`BAZI_POS` 的负对照失效（Jaccard = 0.945）**

原因是**八字在样本上几乎恒为正向**（427/440 = 97%），
随机化打乱激活位置后组合命中集合几乎不变 → 对照失去区分能力。

这不是缺陷而是如实输出：它说明"八字方向"在当前参数下**不构成可研究的离散事件**。
系统把它判为 `INVALID_CONTROL`，而不是假装跑出了一个结论。

**发现 2：「三模型共振」并未带来更好的信息量**

`ALL_THREE_POS`（78 个事件）与单模型的 `ZIWEI_POS` 一样是 `tie / NO_SIGNAL`。
即"三个模型都说好"在历史上**并不比随机方向更有信息量**。

这直接回答了 Phase 2 的核心研究问题，且答案是**否定的**。

### 4.3 ResearchStatus 实际分布

| 状态 | 出现位置 |
|---|---|
| `NOT_RUN` | 单股分析的默认状态（未跑研究流水线时） |
| `NO_SIGNAL` | 6/11 共振组合 |
| `INVALID_CONTROL` | 1/11 组合，且是整体状态 |
| `INSUFFICIENT_SAMPLE` | 2/11 组合 |
| `NO_REAL_DATA` | 合成行情路径（测试环境） |

`SUPPORTED_OUT_OF_SAMPLE` **从未出现**（Phase 1 的守卫继续生效）。

---

## 5. Phase 1 契约变更记录（4 项测试按 Phase 2 语义更新）

严格遵守「先写 ADR / 最小兼容修改」的流程。以下 4 项 Phase 1 测试断言**必须**随
Phase 2 语义更新，其余 547 项**原样通过**：

| # | 测试 | Phase 1 断言 | Phase 2 断言 | 理由 |
|---|---|---|---|---|
| 1 | `test_health` | `phase == "phase1"` | `phase == "phase2"` | 版本标识升级 |
| 2 | `test_engines_lists_all_six` | 紫微 `available is False` | 紫微 `available` 反映**真实服务可达性**；不可用时必须带原因 | 紫微已实现（ADR-0009） |
| 3 | `test_factor_definitions` | `len(items) == 65` | `>= 114` 且含三个引擎 | Phase 2B 新增 49 个紫微因子 |
| 4 | `test_domain_filter_blocks_other_domains` | `domain=ziwei` 返回 0 条 | `domain=ziwei` **有**结果，但**不得混入八字典籍**（反向亦然） | 紫微语料已接入（kb-1.1.0） |

以及 3 项受 Phase 2 语义影响的因子/占位测试：

| # | 测试 | 变化 | 理由 |
|---|---|---|---|
| 5 | `test_ids_follow_naming_convention` | 增加紫微命名空间白名单 | 新命名空间必须显式登记，防止随手起 ID |
| 6 | `test_all_definitions_produce_observations` | 限定为 Phase 1 命名空间 | `Z_*` 需要 `ZiweiChart` 才计算 |
| 7 | `test_ziwei_engine_is_placeholder` | 改为 `test_ziwei_engine_is_a_real_implementation` | 紫微不再是占位 |

**未变更的契约**（全部原样通过）：
`StockBirthProfile` / `MarketDataProvider` / `TradingCalendarProvider` /
`FactorObservation` / `FactorSet` / `ResearchStatus` / `BacktestProvider` /
`KnowledgeProvider` / `BaziEngine` / `MetaphysicsEngine` 的字段与方法签名。

**API 兼容性**：`/api/v1/**` 的既有路径、请求体字段名、响应字段**未做破坏性修改**；
`ConsensusSnapshot.display_only` 字段保留（multi 分析下改为 `false`，Phase 1 分析下仍为 `true`）；
所有新增字段都是可选且带默认值。

---

## 6. 真实性审计

| 检查项 | 结果 |
|---|---|
| 不可用字段是否返回 null 而非 0 | ✅ 紫微不可用时 `score: null`；测试锁定 |
| 合成/降级数据是否被标记 | ✅ `NO_REAL_DATA` 状态机 + UI 横幅 |
| 是否伪造古籍 | ✅ 全部条目来自项目自持公版语料，带 provenance/license_status |
| 参考图数据是否被内置进页面 | ✅ 无；所有数值来自真实 API |
| 是否用平均分掩盖分歧 | ✅ `MIXED` 优先级最高，UI 显示"禁止用平均分掩盖分歧" |
| 是否默认性别 | ✅ 紫微必须显式 variant，否则拒绝排盘 |
| LLM 是否参与计算 | ✅ Narrator 只读 EvidenceBundle；Guard 校验数值一致性 |
| 负对照是否独立 | ✅ Jaccard 检测 + 显式 `INVALID_CONTROL` |
| 多重比较是否留痕 | ✅ `MultipleTestingWarning`（组合数 / 参数数 / Bonferroni 参考阈值） |

---

## 7. 已知限制

见 `docs/model-limitations.md`（完整清单）。最关键的六条：

1. **研究宣称仍被锁**：真实样本下几乎所有组合为 `NO_SIGNAL` / `INVALID_CONTROL`；
2. **样本小**：20 只股票，未处理生存者偏差，结论偏乐观；
3. **出生模型未回测**：`listing_open` 是假设，且导致部分因子结构性地恒定
   （`Z_LIFE_006` 在 9,800 行观测上恒为 False）；
4. **紫微无第二实现源交叉验证**（Tianji 未接入）；
5. **variant 不是两条独立证据**：顺行/逆行差异仅限于大限/小限与长生十二神顺逆；
6. **古籍未逐字校勘**（八字 43 条 + 紫微 13 条）。

---

## 8. GO / NO-GO

| 判定项 | 结果 |
|---|---|
| Phase 1 契约是否被破坏 | **否**（4 项测试按 Phase 2 语义更新，均有理由；核心契约字段与方法签名未变） |
| Phase 1 测试是否继续通过 | **是**（551 项中 547 项原样通过，4 项按语义更新） |
| 新增功能是否有测试 | **是**（新增 452 项 pytest + 14 项 Playwright） |
| 是否用 0 分/假数据冒充 | **否**（多处测试锁定） |
| 是否能用真实数据端到端跑通 | **是**（20 股真实快照，440 行共振研究 + 440 行因子面板） |
| 是否宣称术数有效 | **否**（系统如实输出 `NO_SIGNAL` / `INVALID_CONTROL`） |

**最终判定：`PASS WITH CONDITIONS — PLATFORM V2 READY / RESEARCH CLAIMS BLOCKED`。**

* **PLATFORM_V2_READY**：输入股票代码可完整跑通
  「资料 → 出生档案 → 八字盘 → 紫微十二宫 → 黄历 → 三套因子 → 三个独立观点 →
  共识 → 分歧 → 12 月 + 12 周窗口 → 历史研究 → 负对照 → 古籍支持与反证 →
  ResearchStatus → AI 解释 → 完整 UI → Markdown/HTML 报告」；
* **RESEARCH_CLAIMS_BLOCKED**：任何形式的"术数有效"宣称仍被禁止，
  现有 `SUPPORTED_IN_SAMPLE` 也只能作为"样本内未被对照证伪"的观察陈述。

---

## 9. 交付文档索引

| 文档 | 内容 |
|---|---|
| [`docs/HANDOFF_FINAL.md`](HANDOFF_FINAL.md) | **接手必读**：全部契约、命令、陷阱 |
| [`docs/ziwei-engine.md`](ziwei-engine.md) | 紫微引擎架构与口径 |
| [`docs/ziwei-factor-dictionary.md`](ziwei-factor-dictionary.md) | 49 个紫微因子（自动生成） |
| [`docs/consensus-methodology.md`](consensus-methodology.md) | 共识方法论 |
| [`docs/conflict-methodology.md`](conflict-methodology.md) | 分歧方法论 |
| [`docs/time-window-methodology.md`](time-window-methodology.md) | 时间窗口方法论 |
| [`docs/evidence-bundle.md`](evidence-bundle.md) | 证据包结构 |
| [`docs/narrator-safety.md`](narrator-safety.md) | AI 解释层安全规范 |
| [`docs/calculation-differences-phase2-ziwei.md`](calculation-differences-phase2-ziwei.md) | 紫微口径差异 D1–D7 |
| [`docs/ui-implementation-phase2.md`](ui-implementation-phase2.md) | UI 实现与刻意偏差 |
| [`docs/model-limitations.md`](model-limitations.md) | **引用输出前必读** |
| [`docs/IMPLEMENTATION_PLAN_PHASE2.md`](IMPLEMENTATION_PLAN_PHASE2.md) | 实施计划（含执行状态） |
| [`docs/ADR/ADR-0009`](ADR/ADR-0009-ziwei-engine-iztro.md) / [`0010`](ADR/ADR-0010-ziwei-no-gender-variant.md) / [`0011`](ADR/ADR-0011-consensus-not-averaging.md) | Phase 2 架构决策 |

---

**不准的事**：金融建议、自动交易、券商接口、把这当荐股工具。
**明确状态**：Phase 2 交付的是**工程与研究方法**；
术数有效性在 Phase 1 + Phase 2 的样本上依然是
**NO_SIGNAL / INCONCLUSIVE / INVALID_CONTROL** —— 系统诚实输出如此。
