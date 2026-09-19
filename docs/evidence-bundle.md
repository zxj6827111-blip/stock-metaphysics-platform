# EvidenceBundle（证据包）

> 实现：`src/core/schemas/evidence.py`（模型）、`src/core/orchestration/evidence.py`（构建）
> 消费方：`src/narrator/`（AI Narrator）、`GET /api/v1/analysis/{id}/evidence-bundle`

---

## 1. 一句话

**EvidenceBundle 是 AI 解释层唯一允许读取的数据。**

bundle 里的每一个数字都来自确定性代码；任何不在 bundle 里的数字，
解释层都不许说；任何在 bundle 里的数字，解释层都不许改。

---

## 2. 结构

| 区块 | 字段 | 含义 |
|---|---|---|
| 基础事实 | `stock` / `birth_profile` / `market_data_quality` | 股票资料、出生模型（**研究假设**）、行情质量 |
| 原始盘面 | `bazi_chart` / `ziwei_charts` / `huangli` | 确定性排盘结果；Narrator 不得重算 |
| 因子与观点 | `factors` / `engine_opinions` / `consensus` / `conflicts` | 三个**独立**观点 + 共识 + 分歧 |
| 历史验证 | `research_status` / `historical` / `negative_control_stats` | 统计有效性的全部信息 |
| 古籍 | `classical_support` / `classical_counter_evidence` / `classical` | **支持与反证必须同时存在** |
| 元信息 | `versions` / `assumptions` / `warnings` | 可追溯性与已知限制 |

外加一个自我说明字段：

```
allowed_data_note:
  "本 bundle 是 AI 解释层**唯一**允许读取的数据。
   禁止重新排盘、禁止修改任何分数/方向/状态、禁止编造古籍、
   禁止删除负面证据、禁止隐藏模型冲突。"
```

---

## 3. 构建纪律

`build_evidence_bundle()` **只做组装，不做计算**：

* 所有数字来自已落库的分析结果（`AnalysisRun` / `chart_artifact` / `factor_observation`）；
* 不得在此处调用任何引擎；
* 古籍检索是唯一的外部输入，且**强制同时返回支持与反证**。

### 3.1 检索失败不能拖垮报告

古籍检索抛异常时：

* 返回空的 `classical`，并在 `corpus_warnings` 中写明失败原因；
* **不伪造任何条文**；
* 报告其余部分照常生成。

### 3.2 反证为空必须显式警告

`counter_evidence` 为空**不等于**"古籍一致支持"。Narrator 的模板会输出：

> 本次未检索到反证 —— 这本身是一个需要警惕的信号：古籍检索同时返回支持与反证
> 是本项目的强制要求，反证为空可能意味着检索词覆盖不足，
> **不得**据此认为「古籍一致支持」。

### 3.3 语料警示固定附带

每个 bundle 的 `classical.corpus_warnings` 固定包含：

* 语料**未逐字校勘**（`knowledge/*/classical_seed.json` 的 `_meta`）；
* 古籍条文**不构成对股票收益的任何判断**；
* 检索同时包含支持与反证，以避免"先有结论后找古籍"。

---

## 4. 历史统计的读取

`load_historical_stats(db, stock_code)`：

* `backtest_result` 表按 `experiment_id` 关联（不直接存 `stock_code`），
  因此先用 `backtest_experiment.payload_json` 中的股票池过滤实验；
* **没有记录就如实返回 `{"status": "NOT_RUN"}`**，绝不编造统计数字。

---

## 5. 与 Narrator 的关系

Narrator 的 LLM 路径把整个 bundle JSON 作为**唯一**的用户消息内容
（系统提示是固定常量，见 `docs/narrator-safety.md`）。
`tests/knowledge/test_narrator.py::test_bundle_is_the_only_input` 锁定这一点。

---

## 6. 已知限制

1. `market_data_quality.bar_rows` 目前来自历史统计记录，不是逐股的行情行数统计；
2. `ziwei_charts` 在 `both` 模式下含两个变体，但 `factors` / `engine_opinions`
   只反映主 variant —— bundle 中的 `warnings` 会说明这一点；
3. bundle 体积较大（紫微全盘约 17 KB/盘），LLM 路径需注意上下文长度。
