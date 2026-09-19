# Phase 2 实施计划 · Multi-Engine Productization

| 项 | 值 |
|---|---|
| 上游基线 | `6d4d5d7`（Phase 1 交付）+ Phase 1.1 加固（未提交工作区） |
| 基线测试 | **551 pytest PASS / 43 Playwright PASS / Golden 129 PASS / 泄漏 12 PASS** |
| 上游结论 | `PASS WITH CONDITIONS — GO ENGINEERING / BLOCK RESEARCH CLAIMS` |
| 本文档角色 | Phase 2 的唯一执行清单；每完成一个子阶段就地更新状态 |

---

## 0. 不可动摇的前置约束

1. **Phase 1 契约不得破坏**（`AGENTS.md` §2、`HANDOFF_PHASE1.md` §16）。任何契约变更先写 ADR。
2. **紫微股票的映射不是传统定论**，只能标记 `research_mapping`，并版本化为 `ziwei_stock_mapping_v1`。
3. **ResearchStatus 是硬约束**。`NO_SIGNAL` / `INCONCLUSIVE` / `INVALID_CONTROL` / `NO_REAL_DATA`
   是合法成功状态，禁止在 UI/文案/Narrator 中被弱化或改写为"有效"。
4. **股票没有性别**。紫微需要性别参数时，改用方向 variant（见 §2A-3），禁止默认男/女。
5. **不得用简单平均掩盖分歧**。Consensus 必须保留每个模型的方向。
6. **多重比较警告**：组合搜索必须记录 `experiment_count` / `parameter_count` / `selection_method`
   并产出 FDR / multiple-testing warning（本轮做到接口 + 警告，不做完整学术级校正）。
7. 每一个子阶段结束立即跑相关测试，**不等全部做完再测**。

---

## 1. 阶段总览

| 阶段 | 内容 | 关键产出 |
|---|---|---|
| **2A** | 紫微确定性计算 | `services/ziwei-service/` + `ZiweiEngine` Adapter + `ZiweiChart` + Golden Cases |
| **2B** | 紫微 Factor Engine | `Z_*` 因子 30–50 个 + 质量审计 |
| **2C** | Opinion / Consensus / Conflict | 三个独立 Opinion + `ConsensusEngine` + `ConflictDetector` + 历史共振研究 + 负对照 |
| **2D** | 时间窗口 | 未来 12 月 / 12 周（交易日聚合，禁止发明"流周"） |
| **2E** | Knowledge + EvidenceBundle + Narrator | 紫微语料 + `EvidenceBundle` + LLM 解释 + `NarratorValidator` |
| **2F** | 完整 UI + 导出 + 验收 | 04/05/06/07/08/09/10 七页 + 01/02/03 回归 + Markdown/HTML 报告 |

依赖方向：`2A → 2B → 2C → 2D`；`2E` 依赖 2C 的 `EvidenceBundle` 输入；`2F` 最后。

---

## 2. PHASE 2A · 紫微斗数确定性计算

### 2A-1 第三方核查（已完成）

| 项 | 值 |
|---|---|
| 包 | `iztro` |
| 锁定版本 | **2.6.1**（精确版本，非 `^`） |
| 仓库 | https://github.com/SylarLong/iztro |
| 许可证 | **MIT**（已由 npm registry 元数据核实） |
| 运行时依赖 | `dayjs` / `i18next` / `lunar-lite` / `lunar-typescript` |
| 决策 | 允许接入，作为 `ZiweiEngine` 的唯一排盘后端，**只能经 Adapter** |

> 与 bazi-pro 的关键区别：iztro 有明确 LICENSE（MIT）与可核实的仓库归属，因此**不需要排除**。
> 但仍必须锁版本、锁 commit、写 ADR、更新 `THIRD_PARTY.md`。

### 2A-2 服务形态

```
services/ziwei-service/          Node.js + TypeScript + iztro
  package.json                   锁 iztro@2.6.1
  src/chart.ts                   纯函数：输入 → ZiweiRawChart（本项目自有结构）
  src/cli.ts                     stdin/stdout JSON（批量）—— 默认 transport
  src/server.ts                  POST /internal/ziwei/chart（HTTP）—— 部署 transport
```

**为什么默认是 subprocess 而非 HTTP**：
Phase 2 的研究流水线需要为 ~20 股 × 多个 as_of × 2 variant 批量排盘。
常驻 HTTP 服务在本地开发/测试环境需要额外进程管理，且单测必须能离线跑。
因此 Adapter 提供三种 transport，按 `http → subprocess → unavailable` 顺序降级：

| transport | 触发 | 用途 |
|---|---|---|
| `http` | `SMP_ZIWEI_SERVICE_URL` 已设置 | Docker / 生产部署 |
| `subprocess` | `node` 可用且 `services/ziwei-service` 已构建 | 本地开发、研究批量、测试 |
| `none` | 两者都不可用 | 引擎返回 `Availability.UNAVAILABLE`，其余引擎继续 |

**故障隔离**：紫微失败绝不影响八字 / 黄历 / 历史数据；`Consensus` 的
`available_engine_count` 降低，**不得**把紫微当 0 分计入。

### 2A-3 股票无性别 → 方向 variant（复用 ADR-0003 精神）

iztro 的 `astrolabe()` 需要性别参数，而性别**只影响大限/小限的顺逆行**，
不影响命宫/身宫/星曜/四化。因此把自由度直接定义为「方向」而不是「性别」：

| variant | 语义 | 实现 |
|---|---|---|
| `variant_forward` | 强制**顺行**运限 | 阳年→`男`，阴年→`女` |
| `variant_reverse` | 强制**逆行**运限 | 阳年→`女`，阴年→`男` |
| `not_applicable` | 不适用（Phase 1 默认） | 紫微不产出，返回 unavailable |

* 两者**分别保存 `raw_chart`，不平均**；
* 历史研究分别比较谁更稳定；无足够数据时 `ResearchStatus = INCONCLUSIVE`；
* 假设写入 `assumptions`（键 `ziwei.variant_mode`）。

### 2A-4 `ZiweiChart` 与 `raw_chart`

`raw_chart` 至少保留：十二宫 / 宫干支 / 命宫 / 身宫 / 主星 / 辅星 / 煞曜 /
四化（生年 + 流年）/ 三方四正 / 大限 / 小限 / 流年 / 流月 / 流日 / 流时（预留）。

全部由 iztro 计算后**转成本项目 Pydantic 模型**，第三方对象在 Adapter 内被丢弃
（ADR-0001）。

### 2A-5 Golden Cases

覆盖不同年份 / 月份 / 日期 / 出生时辰 / 两个 variant；结构性不变量（十二宫恒为 12、
命宫与迁移宫恒相对、四化落于四宫、五行局恒定）。若发现与第二实现源不一致，
写入 `docs/calculation-differences-phase2-ziwei.md`，**不得静默覆盖**。

---

## 3. PHASE 2B · 紫微因子

30–50 个 `Z_*` 因子，复用 Phase 1 的统一 `FactorDefinition` / `FactorObservation` Schema：

| 命名空间 | 内容 |
|---|---|
| `Z_LIFE_*` | 命宫（主星组合、庙旺、辅煞） |
| `Z_FIN_*` | 财帛宫 |
| `Z_CAREER_*` | 官禄宫 |
| `Z_MOVE_*` | 迁移宫 |
| `Z_MUTAGEN_*` | 生年四化 / 流年四化 |
| `Z_TRINE_*` | 三方四正 |
| `Z_YEAR_*` | 流年 |
| `Z_MONTH_*` | 流月 |
| `Z_DAY_*` | 流日（用于周度聚合） |

**质量审计**（复用 Phase 1 审计脚本）：`activation_rate` / `null_rate` /
`direction_distribution` / `unique_value_count` / `sample_count` / `mean` / `std` /
`pairwise correlation`；`activation_rate > 95%` 或 `< 0.5%` → `LOW_DISCRIMINATION_FACTOR`；
相关性 `> 0.98` → `POTENTIAL_DUPLICATE_FACTOR`。

---

## 4. PHASE 2C · 多模型 Opinion / Consensus / Conflict

### 2C-1 三个独立 Opinion

`BaziOpinion` / `ZiweiOpinion` / `HuangliOpinion`，统一契约：

```
engine / direction / score / confidence
positive_reasons / negative_reasons / factor_ids
research_status / historical_validity / data_quality / assumptions
```

`score` 是**该术数内部规则强度指标**，不是上涨概率。历史统计另存
`Empirical Statistics`，两者在 API 与 UI 中必须分栏。

### 2C-2 ConsensusEngine（替换 `display_only`）

六分类：`STRONG_POSITIVE_CONSENSUS / POSITIVE_CONSENSUS / MIXED / NEUTRAL /
NEGATIVE_CONSENSUS / STRONG_NEGATIVE_CONSENSUS`。

输出：`consensus_class / agreement_score / available_engine_count /
positive_engine_count / negative_engine_count / neutral_engine_count /
engine_opinions / research_status / historical_consensus_stats / data_quality`。

**禁止简单平均**：`80/20/50` 必须产出 `MIXED` 并列出冲突原因，而不是"整体一般"。

### 2C-3 ConflictDetector

输出：`conflicting_engines / directions / major_conflicts / factor_conflicts /
time_horizon_conflicts / assumption_conflicts / historical_conflict_stats / conflict_level`。
每一条冲突必须给出**可读原因**。

### 2C-4 历史共振研究 + 负对照

研究组合：单模型正 / 两两同向 / 三模型同向 / 冲突组合（`Bazi+ / Ziwei-` 等）。
每格输出 `sample_count / event_count / Jaccard / up_rate / mean_return /
excess_return / control_result / research_status`。

**共振必须有自己的负对照**：随机时间 / 随机模型方向 / 随机因子组合。
`Jaccard > 0.9` → `INVALID_CONTROL`。

### 2C-5 多重比较

记录 `experiment_count / parameter_count / selection_method`；组合数超过阈值时
产出 `MULTIPLE_TESTING_WARNING`（含 Bonferroni 参考阈值），不做虚假的"显著"宣称。

---

## 5. PHASE 2D · 时间窗口

* **月度**：未来 12 个月，每月独立输出 `BaziOpinion / ZiweiOpinion / HuangliOpinion /
  Consensus / Conflict / ResearchStatus / Historical Similar Cases` —— 不是单一数字。
* **周度**：**禁止发明"流周"**；由交易日流日结果聚合，支持
  `mean / median / min / max / positive_day_ratio / weighted_mean`，
  带 `aggregation_version`。
* 所有窗口基于 Phase 1 的 `TradingCalendarProvider`（实际交易日），**不得退化回自然日**。

---

## 6. PHASE 2E · Knowledge + EvidenceBundle + Narrator

* 知识库域从 `domain=bazi` 扩展到 `domain=ziwei`，新增条目必须带
  `book / chapter / topic / school / source / edition / provenance / license_status`；
  版权不清晰者不得进入默认生产知识库。
* 继续强制 `supporting_evidence` + `counter_evidence`（不同流派/相反解释）。
* `EvidenceBundle`：`stock / birth_profile / market_data_quality / bazi_chart /
  ziwei_chart / huangli / factors / engine_opinions / consensus / conflicts /
  research_status / historical_stats / negative_control_stats / classical_support /
  classical_counter_evidence / versions / assumptions / warnings`。
  **这是 Narrator 唯一允许读取的数据。**
* `NarratorValidator`：禁止词/高风险陈述（必涨/必跌/稳赚/高概率上涨/历史证明有效/
  准确率很高）在 EvidenceBundle 不支持时拒绝输出或自动重写。
* 无 API Key 时 Narrator 走**确定性模板**（仍逐条遵守 ResearchStatus 约束），
  并在响应中显式标注 `narrator_mode = "template"` / `"llm"`。

---

## 7. PHASE 2F · 完整 UI + 导出 + 验收

| 参考图 | 路由 | 内容 |
|---|---|---|
| `04_ziwei_detail` | `/stock/[code]/ziwei` | 真 `ZiweiChart` 组件：十二宫 / 主星 / 辅星 / 四化 / 三方四正 / 流年流月 |
| `05_backtest_validation` | `/stock/[code]/backtest` | 术数规则强度 **vs** 统计有效性分栏；样本数/上涨率/平均收益/超额/回撤/负对照/状态 |
| `06_factor_dictionary` | `/factors` | 65 Phase 1 + `Z_*` 因子；definition / computation / version / activation rate / 历史统计 / 关联证据 |
| `07_model_conflict_center` | `/stock/[code]/conflicts` | 数据来自真实 `ConflictDetector` |
| `08_huangli_detail` | `/stock/[code]/huangli` | 黄历原盘 + 交易日窗口 + 证据与历史表现 |
| `09_classics_evidence_search` | `/stock/[code]/evidence` | **只展示真实 `KnowledgeProvider` 数据** |
| `10_time_window` | `/stock/[code]/timeline` | 12 月 / 12 周窗口 |

* 01/02/03 重新验证不跑版；综合页数据源从 fixture aggregation 切换为真实
  `BaziOpinion / ZiweiOpinion / HuangliOpinion / Consensus / Conflict`。
* 截图仍为 1672×941，输出到 `apps/web/artifacts/ui-review/<page>/{reference,current}.png + notes.md`。
* 导出：Markdown + HTML，含版本 / 假设 / 限制 / ResearchStatus / 负对照。

---

## 8. 数据扩容（不阻塞工程）

现有 20 股 + 沪深300 + 104,521 行 hfq。目标 100 → 500 → 全 A point-in-time universe。
**扩容失败不得阻塞 Phase 2 开发**；样本不足时如实输出 `INSUFFICIENT_SAMPLE`。

---

## 9. 每阶段必做

```
1. 新增/修改引擎或规则 → 提升 engine_version / rule_version
2. 新增因子 → 更新 docs/factor_dictionary.md + docs/ziwei-factor-dictionary.md
3. 修改 UI → 更新 apps/web/artifacts/ui-review/*/notes.md
4. 阶段结束 → pytest 全绿（Phase 1 的 551 项必须继续通过）
5. 涉及契约改动 → 先写 ADR
```

---

## 10. 拒绝清单（本轮仍不做）

六爻正式引擎 / 奇门正式引擎 / 券商自动交易 / 自动买卖 / 资金账户 /
付费会员 / 复杂多租户 —— 只保留接口。

---

## 11. 交付物清单

```
docs/HANDOFF_FINAL.md
docs/PHASE2_ACCEPTANCE_REPORT.md
docs/ziwei-engine.md
docs/ziwei-factor-dictionary.md
docs/consensus-methodology.md
docs/conflict-methodology.md
docs/time-window-methodology.md
docs/evidence-bundle.md
docs/narrator-safety.md
docs/calculation-differences-phase2-ziwei.md
docs/ui-implementation-phase2.md
docs/model-limitations.md
docs/ADR/ADR-0009-ziwei-engine-iztro.md
docs/ADR/ADR-0010-ziwei-no-gender-variant.md
docs/ADR/ADR-0011-consensus-not-averaging.md
```

---

## 12. 执行状态（2026-09-19 完成）

| 阶段 | 状态 | 交付 |
|---|---|---|
| 2A 紫微确定性计算 | ✅ **完成** | `services/ziwei-service`（iztro 2.6.1）+ `ZiweiEngine` + 8 组 Golden 快照 + ADR-0009/0010 |
| 2B 紫微因子 | ✅ **完成** | 49 个 `Z_*` 因子 + 质量审计（9,800 行真实观测）+ 自动生成因子字典 |
| 2C Opinion / Consensus / Conflict | ✅ **完成** | `ConsensusEngine` + `ConflictDetector` + 共振研究（11 预定义组合 + 独立负对照 + 多重比较警告） |
| 2D 时间窗口 | ✅ **完成** | 未来 12 月 / 12 周，交易日聚合（`agg-v1`），禁止发明「流周」 |
| 2E Knowledge / Evidence / Narrator | ✅ **完成** | 紫微语料 13 条 + `EvidenceBundle` + `Narrator` + `NarratorValidator` |
| 2F UI / 导出 / 验收 | ✅ **完成** | 7 个新页面 + 综合页数据源切换 + Markdown/HTML 报告 + 10 张截图 + notes.md |

**测试**：1003 pytest + 44 Playwright 全绿。
**验收结论**：`PASS WITH CONDITIONS — PLATFORM V2 READY / RESEARCH CLAIMS BLOCKED`
（详见 [`docs/PHASE2_ACCEPTANCE_REPORT.md`](PHASE2_ACCEPTANCE_REPORT.md)）。

### 实施过程中的计划外发现（已修）

| # | 发现 | 处理 |
|---|---|---|
| 1 | iztro 小限层不提供流曜（`stars` 字段不存在） | 如实保留为空，写入计算差异 D1 |
| 2 | 12 宫 vs 10 天干导致宫干环回不是 +1 | 修正 Golden 不变量为 `stems[i] == stems[0] + i (mod 10)`（D5） |
| 3 | 经验判定带在纯随机数据上假阳性率 64% | 改用 Welch t 检验（假阳性回到 ~1.5%） |
| 4 | Next rewrite 转发 POST 时合并出重复 Content-Type | `api.post` 不再自行设置 content-type |
| 5 | `Z_LIFE_006` 在默认出生模型下结构性恒定 | 如实标记 `CONSTANT_FACTOR` 并写入限制文档 |
| 6 | 紫微盘面初版布局未按传统地支环 | 改为标准 4×4 环形排布 |
