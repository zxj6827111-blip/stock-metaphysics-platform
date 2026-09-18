# AGENTS.md · 股票玄学多模型研究平台

> 本文件是**给 AI 编程助手的强制规则**。任何在本仓库工作的 AI（Codex / Claude Code / ZCode / OpenCode …）
> 在修改代码前必须先读完本文件。
>
> **Phase 2 不得破坏本文档中标注为「契约」的条目。**

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
（例：紫微在 Phase 1 返回 `available: false, score: null`，绝不允许 `score: 0`。）

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
   a. 写入 docs/calculation-differences.md（说明变化点与影响范围）
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
* Phase 1 交接：[`docs/HANDOFF_PHASE1.md`](docs/HANDOFF_PHASE1.md)
