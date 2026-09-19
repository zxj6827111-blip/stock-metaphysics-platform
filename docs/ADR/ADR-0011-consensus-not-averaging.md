# ADR-0011：Consensus 禁止简单平均，冲突必须显式保留

- **状态**：已接受（Phase 2C）
- **日期**：2026-09-19
- **影响**：ConsensusEngine、ConflictDetector、UI、Narrator
- **关联**：[ADR-0003](ADR-0003-no-gender-variant-mode.md)、[ADR-0010](ADR-0010-ziwei-no-gender-variant.md)

## 背景

多模型系统最自然、也最危险的做法是把各模型分数**平均**：

```
八字 90 / 紫微 20 / 黄历 50
  → 平均 53
  → "整体一般，偏中性"
```

这个输出在**每一层都是错的**：

1. **信息损失**：读者看不到"八字强烈看多、紫微强烈看空"这一最重要的事实；
2. **语义污染**：三个模型的分数各自来自不同的规则体系，量纲不可比，
   平均它们没有数学含义；
3. **决策误导**：53 会被读成"温和偏多"，而真实状态是"两个模型正面对立"。

`AGENTS.md` §2.4 已经规定"模型分歧不得被平均值隐藏"；本 ADR 把它落地为可执行的算法。

## 决策

### 1. 共识分类基于**方向投票**，不基于分数

| 情形 | 分类 |
|---|---|
| 存在正负两向 | `MIXED` |
| 全部为正 | `POSITIVE_CONSENSUS` / `STRONG_POSITIVE_CONSENSUS` |
| 全部为负 | `NEGATIVE_CONSENSUS` / `STRONG_NEGATIVE_CONSENSUS` |
| 其余（含中性，无对立） | `NEUTRAL` |
| 无可用引擎 | 不可评估（不用 0 分填补） |

`MIXED` 的优先级最高 —— 只要存在反向引擎，就绝不允许被描述成"整体偏多/偏空"。

### 2. `agreement_score` 是**方向一致度**，不是分数平均

定义：`max(正向数, 负向数, 中性数) / 可用引擎数`。

字段的 `description` 与 UI 的 `notes` 都显式写明这一点，
并有测试锁定该措辞（`test_notes_explain_agreement_semantics`）。

### 3. 强共识需要"分数 + 置信度"双条件

`STRONG_*` 只在方向完全一致、平均规则分越过阈值、且平均置信度 ≥ 0.55 时给出。
避免"三个模型都微弱偏多"被渲染成"强正向共振"。

### 4. 不可用引擎不参与分母，也不补 0

`available_engine_count` 如实降低，`unavailable_engines` 单列。
紫微服务挂掉时共识从 3 引擎降到 2 引擎 —— **不是**把紫微按 0 分计入。

### 5. 共识与历史有效性强制分离

`ConsensusSnapshot` 同时携带：

* `label` / `agreement_score` —— 模型之间方向是否一致；
* `research_status` / `historical_consensus_stats` —— 这种一致在历史上是否有统计支持。

`interpretation` 字段由 `ConsensusEngine._interpret()` **统一生成**，
任何 `NO_SIGNAL` / `NO_REAL_DATA` / `INVALID_CONTROL` 状态下，
文案必须同时说明"共识高"与"历史无支持"两件事。UI 与 Narrator 都直接消费该字段，
不允许各处自行发挥。

### 6. 冲突检测覆盖四个层面

| 层面 | 检测方式 |
|---|---|
| 方向 | 引擎方向向量出现正负对立 |
| 因子 | 跨引擎、同 tag、方向相反 |
| 时间尺度 | 同一引擎内部长周期与短周期因子均值反号 |
| 假设 | 引擎之间依赖的假设不同（如运限方向假设） |

每条冲突都必须带**可读原因**；`historical_conflict_stats` 未运行时必须为 `NOT_RUN`。

### 7. 共振研究必须有独立负对照

"三个模型都说好"不能成为更有效的理由。`src/research/consensus_research.py` 用
**打乱每个引擎的激活位置**（保持激活率）作为零假设，并用 **Welch t 检验**判定，
而不是用"差值大于某个经验带"。

实测教训：早期版本用"差值 > 半个标准误"的判定带，在**纯随机数据**上
11 个组合里能冒出 7 个 `outperform`（假阳性率 64%）。改成 Welch t 检验后
回到 5% 名义水平附近（66 次组合检验中 1 次，约 1.5%）。

## 后果

**正面**

* 分歧信息完整保留，且可被自动检测与展示；
* "共识高"与"历史有效"在数据结构上就是两个字段，无法被混为一谈；
* 组合搜索被限制在预定义集合内，配以多重比较警告。

**负面**

* 前端需要更多空间（不能只显示一个总分）；
* `MIXED` 是常见结果，"没有清晰结论"会让部分用户失望 —— 但这是**如实**的结论。

## 相关

- [`docs/consensus-methodology.md`](../consensus-methodology.md)
- [`docs/conflict-methodology.md`](../conflict-methodology.md)
- [`src/core/orchestration/consensus.py`](../../src/core/orchestration/consensus.py)
- [`tests/consensus/test_consensus.py`](../../tests/consensus/test_consensus.py)
