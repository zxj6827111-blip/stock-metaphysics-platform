# 分歧方法论（Conflict Methodology）

> 决策记录：[ADR-0011](ADR/ADR-0011-consensus-not-averaging.md)
> 实现：`src/core/orchestration/consensus.py::ConflictDetector`

---

## 1. 一句话

**分歧是信息，不是噪声。** 系统的职责是把分歧完整、可读、可追溯到因子地呈现出来，
而不是把它平均掉。

---

## 2. 四个检测层面

| 层面 | `conflict_*` 字段 | 判据 |
|---|---|---|
| 方向 | `major_conflicts` | 引擎方向向量同时出现 +1 与 −1 |
| 因子 | `factor_conflicts` | **跨引擎**、同 tag、方向相反 |
| 时间尺度 | `time_horizon_conflicts` | 同一引擎内部，长周期因子均值与短周期因子均值反号 |
| 假设 | `assumption_conflicts` | 引擎依赖的假设不同（如运限方向假设） |

冲突级别：`none` / `minor` / `major` / `severe`（当前实现产出前三档）。

### 2.1 方向冲突

输出 `major_conflicts[]`，每项含：

```
kind / engine / direction / direction_label / score / confidence
reasons[]      ← 该引擎 top_positive/negative_reasons 的可读文本（中文引擎名）
factor_ids[]   ← 可追溯到具体因子
```

`reasons` 为空时填 `["该引擎无明细理由"]` —— **不允许留空**，
一条没有原因的冲突对研究者没有价值。面向人的文本一律用中文引擎名
（`engine_label()`），不直接抛 `bazi` / `ziwei` 这类内部 key。

### 2.2 因子冲突

只在**不同引擎之间**比较。同一引擎内部两个因子方向相反不是"模型分歧"，
而是该模型自己的结构（例如"原局偏强但流日偏弱"），那属于时间尺度层面。

判据：共享至少一个 `tag`，且方向乘积 < 0，且两侧 `normalized_value` 非 0。
最多返回 20 条。

### 2.3 时间尺度冲突

对每个引擎分别计算：

```
long  = mean(normalized_value of category ∈ {natal, year})
short = mean(normalized_value of category ∈ {day, month})
若 long × short < 0 且 |long| > 0.05 且 |short| > 0.05 → 冲突
```

`description` 固定包含这句说明：

> 传统术数偏中长周期，短周期噪声更大，**不代表两者可以互相抵消**。

### 2.4 假设冲突

扫描各引擎 opinion 的 `assumptions`，若 ≥ 2 个引擎的假设含 "variant"，
产出一条 `variant_assumption` 冲突：

> 以下引擎的结论依赖**运限方向假设**（顺行/逆行）：八字、紫微。
> 股票没有真实性别，该假设不是事实；两个方向不能互相验证。

**为什么这算冲突**：如果两个引擎的分歧其实来自"用了不同的方向假设"，
那不是模型分歧，而是假设差异 —— 必须让读者能分辨。

---

## 3. 历史冲突统计

`historical_conflict_stats` 默认 `{"status": "NOT_RUN"}`。

未运行时：

* API 返回 `NOT_RUN`；
* UI 显式显示"未运行"，**不显示任何示意案例**；
* Narrator 在解读中说明"历史类似冲突的后续表现尚未被统计过"。

理由：参考图里有"历史类似分歧案例"列表（2023-08-15 茅台相似度 82% …）。
那些是设计稿数据。在真实统计跑出来之前，任何"历史上冲突后如何"的说法都是编造。

要产生真实数据，运行：

```
POST /api/v1/research/consensus
```

---

## 4. 与共识的关系

分歧与共识是**同一份观点向量的两种视角**，但它们不是互斥的：

| 状态 | 共识 | 分歧 |
|---|---|---|
| 三模型全正 | `POSITIVE_CONSENSUS` | `none` |
| 两正一负 | `MIXED` | `major` |
| 两正一中性 | `NEUTRAL` | `minor`（强度分歧） |
| 全部不可用 | 不可评估 | `none`（无法比较） |

注意第三种：方向不冲突，但强度分歧 —— 系统把它记为 `minor`，
并在 reason 里说明"属于强度分歧而非方向对立"。

---

## 5. 已知限制

1. 因子冲突依赖 `tag` 体系的质量；tag 过粗会产生噪音，过细会漏检；
2. 时间尺度冲突用的是**类别均值**，样本很少时不稳定；
3. 假设冲突目前只识别 variant 类假设，其他假设差异（如黄历流派）尚未自动比对；
4. 冲突"级别"是启发式阈值，不是统计量。
