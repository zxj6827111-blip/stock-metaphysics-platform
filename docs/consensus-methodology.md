# 共识方法论（Consensus Methodology）

> 决策记录：[ADR-0011](ADR/ADR-0011-consensus-not-averaging.md)
> 实现：`src/core/orchestration/consensus.py::ConsensusEngine`

---

## 1. 一句话

**共识只表示"多个术数模型之间方向的一致程度"，不表示"历史证明它有效"。**

这两件事在数据结构上就是两个字段：

| 字段 | 含义 |
|---|---|
| `label` / `consensus_class` / `agreement_score` | 模型之间的方向是否一致 |
| `research_status` / `historical_consensus_stats` | 这种一致在历史上是否有统计支持 |

系统完全可能输出 **`STRONG_POSITIVE_CONSENSUS` + `NO_SIGNAL`** —— 这不是 bug，
而是必须如实呈现的研究结果。

---

## 2. 分类规则

```
可用引擎 = {opinion.availability == ok 且 score != null}

若 可用引擎 == 0                    → 不可评估（label_cn = "不可评估"）
否则 若 正向数 > 0 且 负向数 > 0     → MIXED
否则 若 正向数 == 可用数             → STRONG_POSITIVE / POSITIVE
否则 若 负向数 == 可用数             → STRONG_NEGATIVE / NEGATIVE
否则                                → NEUTRAL
```

**`MIXED` 的优先级最高。** 只要存在反向引擎，就绝不允许被描述成"整体偏多/偏空"。

强共识的额外条件（`_strong_or_plain`）：

* 全部引擎方向一致；
* 平均规则分 ≥ 68（正向）/ ≤ 32（负向）；
* 平均置信度 ≥ 0.55。

三个条件同时满足才是 `STRONG_*`。避免"三个模型都微弱偏多"被渲染成"强正向共振"。

---

## 3. 禁止简单平均

`AGENTS.md` §2.4 的落地：

| 输入 | 输出 |
|---|---|
| 八字 90 / 紫微 20 / 黄历 50 | `MIXED`，正 1 / 负 1 / 中 1，方向向量完整保留 |
| ~~平均 53 → "整体一般"~~ | **禁止** |

`agreement_score` 的定义是**方向一致度**：

```
agreement_score = max(正向数, 负向数, 中性数) / 可用引擎数
```

它不是各引擎分数的平均，也不表示上涨概率。字段 description 与 UI `notes`
都显式写明该语义，并有测试锁定。

---

## 4. 不可用引擎的处理

* 不计入分母（`available_engine_count` 如实降低）；
* 列在 `unavailable_engines`；
* **绝不用 0 分计入**。

例如紫微排盘服务挂掉时：

```
available_engine_count: 2
unavailable_engines: ["ziwei"]
directions: { bazi: 1, huangli: 1 }     ← 没有 ziwei
```

故障隔离的验证见 `tests/engines/test_ziwei_engine.py` 与
`tests/timeline/test_time_windows.py::TestVariantInteraction`。

---

## 5. 统一解读文案

`ConsensusEngine._interpret()` 是**唯一**生成解读文案的地方。
它必须同时包含：

1. 一致性结论 + 各引擎方向；
2. 未计入的引擎；
3. 与 `research_status` 对应的历史有效性说明。

`research_status` 为 `NO_SIGNAL` 时，文案固定包含：

> **术数共识高，但历史统计未发现稳定信号**（ResearchStatus=NO_SIGNAL）。
> 本文的一致性不代表上涨概率较高。

UI 与 Narrator 都直接消费 `interpretation` 字段，不允许各处自行发挥
（`tests/knowledge/test_narrator.py` 有对应断言）。

---

## 6. 历史共振研究的组合集合

`src/research/consensus_research.py` 只允许研究**预定义**的 11 个组合：

| 类型 | 组合 |
|---|---|
| 单模型 | `BAZI_POS` / `ZIWEI_POS` / `HUANGLI_POS` |
| 两两同向 | `BAZI_ZIWEI_POS` / `BAZI_HUANGLI_POS` / `ZIWEI_HUANGLI_POS` |
| 三模型同向 | `ALL_THREE_POS` |
| 冲突组合 | `BAZI_POS_ZIWEI_NEG` / `BAZI_NEG_ZIWEI_POS` / `BAZI_POS_HUANGLI_NEG` / `ZIWEI_POS_HUANGLI_NEG` |

传入未定义组合会直接抛 `ValueError` —— 这是**数据挖掘防护的第一道闸门**：
自由组合搜索会迅速退化成"总有一个看起来显著"。

---

## 7. 负对照与判定

负对照 = **打乱每个引擎的激活位置**（保持各自的激活率），重算组合命中。

判定流程：

```
1. Jaccard(真实事件集合, 对照事件集合) > 0.9  → INVALID_CONTROL（对照失效）
2. 事件数 < 30                              → INSUFFICIENT_SAMPLE
3. Welch 双样本 t 检验，p ≥ 0.05             → tie / NO_SIGNAL
4. p < 0.05 且真实均值更高                    → outperform / WEAK_EVIDENCE
5. p < 0.05 且真实均值更低                    → underperform / NO_SIGNAL
```

**为什么用 Welch t 检验而不是经验带**：早期实现用"差值 > 半个标准误"，
在纯随机数据上 11 个组合里能冒出 7 个 `outperform`。
改成 t 检验后，随机数据下的假阳性率回到 5% 名义水平附近。
`tests/consensus/test_consensus.py::test_random_data_does_not_produce_false_outperformance`
与 `test_real_edge_is_detectable` 分别锁住假阳性与检验功效。

---

## 8. 多重比较

`MultipleTestingWarning` 记录：

* `experiment_count`（实际检验的组合数）
* `parameter_count`（组合 × 持有期 × variant）
* `selection_method`（固定为 `exhaustive_over_predefined_combos`）
* `bonferroni_alpha`（参考阈值 = 0.05 / 组合数）
* `warning_level`：`none`（< 5）/ `caution`（≥ 5）/ `high`（≥ 20）

**本项目不做学术级多重检验校正**，因此报告中对这些结果只能说"探索性观察"，
不能作为有效性宣称。

---

## 9. 已知限制

1. 三模型方向分别来自各自的规则体系，**量纲不可比** —— 这正是不能平均的根本原因；
2. `agreement_score` 是粗粒度指标（3 个引擎时只能取 1/3、2/3、1 三个值）；
3. 组合研究未做行业中性化、未处理生存者偏差；
4. `both` variant 下因子层只使用 primary variant（见 `ZIWEI_VARIANT_PRIMARY_SELECTED` 警告）。
