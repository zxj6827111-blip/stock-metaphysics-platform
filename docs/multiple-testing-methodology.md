# Phase 3F · 多重检验与稳健性方法学

> 生成基线：commit `b04a2b9` · `mt_version=mt-v1` · `gate_version=phase3f-oos-gate-v2`
> 数据源：`data/phase3_universe/phase3f_multiple_testing_results.csv`、
> `phase3f_family_correction.csv`、`phase3f_robustness_slices.csv`、`phase3f_run_summary.json`
> 实现：`src/research/multipletesting/`（families / fdr / resample / robustness / gate_v2 / runner）

---

## 0. 一句话结论

**42 个正式 gate 实验中，BH-FDR 通过 0 个、Bonferroni 通过 0 个；
`SUPPORTED_OUT_OF_SAMPLE = 0`。** 唯一通过校正的 1 条来自 `conflict`（探索性）族，
按预注册规则**不套用单向 gate、永不解锁**。这不是失败，是 Phase 3 的正确结果。

---

## 1. 假设族冻结（GOAL §4.2）

族定义写在 `config/phase3f_multiple_testing_families.yaml`，
**在读取任何最终校正结果之前**冻结（`final_results_seen_at_freeze: false`），
并带版本号 `mt-v1`。改动族定义必须新建 `mt-v2`，旧文件原样保留。

| 族 | 成员假设数 | 实验数 m | 单/双侧 | 是否套用 gate |
|---|---:|---:|---|---|
| `bazi` | 2 | 6 | 单侧 | 是 |
| `ziwei` | 2 | 6 | 单侧 | 是 |
| `huangli` | 2 | 6 | 单侧 | 是 |
| `consensus` | 8 | 24 | 单侧 | 是 |
| `conflict` | 4 | 12 | 双侧 | **否（`EXPLORATORY_NOT_GATED`）** |
| `birth_model_comparison` | — | 18 | 双侧 | 否（比较族） |

**为什么必须冻结**：BH 的校正强度直接取决于族内检验数。若允许看到 q 值后把 42 个检验
说成"其实是 6 个独立族"，校正就会失去约束。`FamilyRegistry.validate_against` 强制校验
"每个假设恰好属于一个族、无遗漏、无重复"，缺一即抛错。

**`birth_model_comparison` 族的定义**（回答 GOAL §20 的 Q2/Q9，不是新的信号假设）：
对 6 个单引擎对象 × 3 个出生模型两两配对 × 主持有期 20D = 18 个检验。
零假设 = "换出生模型不改变结论"，统计量为**逐日配对差的符号翻转置换**双侧 p。

---

## 2. BH-FDR（GOAL §4.1）

每个检验同时输出四个数：

| 字段 | 含义 |
|---|---|
| `raw_p_value` | 日期分层置换 p（族单侧/双侧口径） |
| `bonferroni_threshold` | `α / m`（族内），最保守 |
| `fdr_q_value` | BH 调整后的 q（step-up 单调化） |
| `fdr_pass` | `q ≤ α` |

* BH 在**族内**校正；禁止拆族降低强度。
* p 值为 `None`（不可判定）的检验被排除在 m 之外，**单独计数**（`missing_count`），
  不静默当作 1。
* 单调化是强制的：只按排名取阈值会给出自相矛盾的 q（`q(2) < q(1)`）。
* 实现用 **O(m²) 参考实现交叉验证**（`tests/research/test_multiple_testing.py` 中
  独立写了一份朴素算法，在随机 p 序列上逐位比对），并用 BH 1995 经典例子
  （α=0.05 恰好拒绝 4 个）做金标准。

---

## 3. 置换检验：为什么必须按日期分层（GOAL §4.4 / §4.7）

**这是 Phase 3F 最重要的口径修正。**

零假设 = "在每个 `as_of` 内部，命中标签可交换"。实现上：在每个日期内部打乱命中标签，
**严格保留每个日期的命中数量**。统计量 = 日期等权平均的 `(命中均值 − 未命中均值)`。

为什么不能在全池随机抽同样数量的位置：

* Phase 3D 实测：黄历命中集合的日期权重与全池完全不同；
* 全池随机抽样会打乱日期构成，对照因而测的是"日期构成差异"而不是"选股能力"；
* 构造实验（`tests/research/test_multiple_testing.py::test_date_stratified_permutation_does_not_flag_a_date_selector`）
  给出直接证据：一个**纯日期选择器**在分层置换下 p > 0.1（不显著），
  而在池化置换下 **p < 0.05**（假显著）。

**协议合法性（GOAL §4.7 的五条要求）**：

1. 这是 Phase 3D **已预登记**的未来改进项（3D 报告 §6.5 明确列为 3F 的改进项）✅
2. 不修改 Phase 3D 的任何结果：3D 的 54 条实验状态与对照统计**只读**引用 ✅
3. 新结果标记 `protocol_version = gate-v2`（`gate_version=phase3f-oos-gate-v2`）✅
4. `gate-v1` 与 `gate-v2` **并排输出**（结果表同时含 `gate_v1_status` 与 `gate_v2_status`）✅
5. 不选择性保留：所有实验两版状态都出现在同一份 CSV ✅

**置换规模**：默认 **5000 次**（GOAL 要求 ≥1000），种子由
`sha256(base_seed | hypothesis_id | birth_model | salt)` 派生 —— 可复现且实验间不共用随机序列。

---

## 4. Bootstrap 置信区间（GOAL §4.3）

重采样单位是**日期**，不是行（行级 bootstrap 会把"同一天 200 只股票"当成 200 个独立样本，
给出虚假的窄区间）。

| 项 | 口径 |
|---|---|
| 统计量 | ① 命中子集的市场超额均值 ② 命中−未命中的差 |
| 重采样 | 对 `as_of` 有放回重采样（n = 日期数），每次重算日期等权统计量 |
| 次数 / 置信度 | 2000 / 95% |
| 种子 | 由实验标识派生，固定 |
| 关键字段 | `point_estimate` / `ci_lower` / `ci_upper` / `crosses_zero` |

**实测结果**：42 个正式 gate 实验中，**每一个**的命中均值 95% CI 都**跨过 0**
（下界约 −5.1%、上界约 +1.1%），这是"没有可靠正效应"的直接证据。

---

## 5. 效应量（GOAL §4.5）

不只报告 p 值：`mean_difference`（命中−未命中）、`cohen_d`、`event_rank_ic_mean`。
判定条件 E 要求 `|Cohen's d| ≥ 0.02` **且** `|OOS 市场超额| ≥ 2%`
（"非零"与"有实际意义"是两件事）。

---

## 6. 稳健性维度（GOAL §4.6）

| 维度 | 口径 | 实测可用性 |
|---|---|---|
| `year` | 逐年份效应 + 符号一致性 | 可用（40/42） |
| `birth_model` | 三模型各自效应 | 可用（另有独立比较族） |
| `segment` | 交易所**板块**（不是行业） | 可用（39/42）；行业 PIT 不可用 |
| `universe_subset` | 在市股 vs 退市股 | 可用（41/42） |
| `horizon` | 5/10/20/60D | 可用（3E 全表） |
| `variant` | raw vs calibrated | 可用（每个对象两版） |
| `market_regime` | 按 `as_of` **当时可得**的基准 trailing 60D 收益划分 up/down | 可用（41/42） |
| `non_overlapping` | 用**交易日历**精确计算相邻采样点间隔 vs 持有期 | 可用（季度网格 → 重叠比例 0） |
| `adj_snapshot` | 除权因子来源（主快照 / 退市补丁）覆盖占比 | 可用；退市补丁独有 **311/500** 只 |

测不了的维度一律显式记 `ROBUSTNESS_DIMENSION_UNAVAILABLE` 并给出原因 ——
不允许"这一维没测"被静默省略成"这一维通过了"。

### 6.1 实测不稳定的维度（正式 gate 实验，n=42）

| 维度 | 不稳定的实验数 | 含义 |
|---|---:|---|
| `universe_subset` | **31** | 在市股与退市股给出**相反符号**的效应 |
| `year` | 8 | 跨年份符号不一致 |
| `market_regime` | 6 | 多头区间与空头区间符号不一致 |
| `segment` | 4 | 板块间符号不一致 |

`universe_subset` 的 31/42 是本次最值得注意的稳健性发现：**结论高度依赖股票生命周期分组**，
而退市股恰恰是 Phase 3A 用来根治生存者偏差的那部分资产。

---

## 7. gate-v2：A–L 十二项条件（GOAL §4.8）

| 条件 | 内容 | 映射 |
|---|---|---|
| A | 足够 OOS 事件数（≥100，有效样本 > 0） | `A_oos_event_count` |
| B | 负对照有效（Jaccard ≤ 0.9 且至少一类可判定） | `B_control_valid` |
| C | Validation 与 OOS 方向一致 | `C_direction_consistent_with_validation` |
| D | OOS 效应优于每一类有效对照 | `D_oos_beats_all_controls` |
| E | 效应量非零**且**有实际意义 | `E_effect_size_nonzero_and_meaningful` |
| F | FDR q ≤ α（族内 BH） | `F_fdr_pass` |
| G | 95% bootstrap CI 不跨 0 且下界为正 | `G_bootstrap_ci_excludes_zero` |
| H | 日期分层置换单侧 p ≤ α 且置换次数 ≥ 1000 | `H_date_stratified_permutation` |
| I | 跨年份稳定（≥3 年、正向比例与符号一致性 ≥ 0.6） | `I_year_stability` |
| J | 非单一股票驱动（top1 ≤ 0.5 且 LOO 无符号翻转） | `J_not_single_name_driven` |
| K | 风格中性化后保留 ≥ 50% 且板块中性后仍为正 | `K_not_style_or_segment_driven` |
| L | 无合成/降级/泄漏类严重告警 | `L_data_quality_clean` |

**任一关键条件失败即不得输出 `SUPPORTED_OUT_OF_SAMPLE`。**
探索性（`conflict`）对象直接返回 `EXPLORATORY_NOT_GATED`，**结构上不可能解锁**。

### 7.1 实测状态对比（正式 gate 实验，n=42）

| gate-v1（3D 原始） | 数量 | | gate-v2（3F） | 数量 |
|---|---:|---|---|---:|
| `INCONCLUSIVE` | 32 | | `INCONCLUSIVE` | 20 |
| `WEAK_EVIDENCE` | 4 | | `WEAK_EVIDENCE` | 17 |
| `INSUFFICIENT_SAMPLE` | 3 | | `INSUFFICIENT_SAMPLE` | 3 |
| `INVALID_CONTROL` | 2 | | `INVALID_CONTROL` | 2 |
| `NO_SIGNAL` | 1 | | `SUPPORTED_OUT_OF_SAMPLE` | **0** |

gate-v2 的 `WEAK_EVIDENCE` 从 4 升到 17，正是新增条件（FDR / bootstrap / 置换 / 中性化）生效的结果 ——
两版并排报告让这一差异**可见**，而不是被掩盖。

---

## 8. 实测结果全表（不美化）

### 8.1 族内校正

| 族 | m | 最小 raw p | Bonferroni 通过 | FDR 通过 |
|---|---:|---:|---:|---:|
| `bazi` | 6 | 0.0718 | 0 | 0 |
| `ziwei` | 6 | 0.1758 | 0 | 0 |
| `huangli` | 6 | 0.0394 | 0 | 0 |
| `consensus` | 24 | 0.0070 | 0 | 0 |
| `conflict` | 12 | 0.0036 | **1** | **1**（探索性，不解锁） |
| `birth_model_comparison` | 18 | 0.1754 | 0 | 0 |

### 8.2 名义 p 最小的 6 个正式实验及其失败条件

| 对象 | 出生模型 | 事件数 | raw p | q | 均值差 | Cohen's d | bootstrap 命中均值 CI | 风格中性均值 | 未通过条件 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| 八字+紫微 cal | `ipo_approx_v1` | 169 | 0.0070 | 0.096 | +3.42% | 0.190 | [−5.05%, +1.09%] | +2.84% | C, E, F, G, I |
| 三模型 raw | `ipo_approx_v1` | 388 | 0.0112 | 0.096 | −0.16% | −0.009 | [−5.14%, +1.04%] | +0.46% | C, E, F, G, I, K |
| 紫微+黄历 raw | `ipo_approx_v1` | 404 | 0.0150 | 0.096 | −0.40% | −0.022 | [−5.22%, +1.17%] | +0.38% | C, E, F, G, I, K |
| 紫微+黄历 cal | `listing_open_v1` | 172 | 0.0168 | 0.096 | −2.11% | −0.117 | [−5.07%, +1.07%] | −1.96% | C, F, G, I, K |
| 三模型 cal | `ipo_approx_v1` | 69 | 0.0236 | 0.096 | +1.41% | 0.078 | [−5.21%, +1.12%] | +1.04% | A, C, F, G, I, K |
| 八字+黄历 cal | `ipo_approx_v1` | 277 | 0.0240 | 0.096 | −1.23% | −0.068 | [−5.11%, +1.07%] | +2.50% | C, E, F, G, I |

**共同失败模式**：全部 6 个都未通过 **C（Validation 与 OOS 方向不一致）**、
**F（FDR）**、**G（bootstrap CI 跨 0）**、**I（跨年份不稳定）**。
这不是"差一点点"，而是四项**结构性**条件同时不满足。

### 8.3 唯一通过校正的一条（探索性，不解锁）

| 对象 | 出生模型 | 族 | raw p | q | 状态 |
|---|---|---|---:|---:|---|
| `conflict_bazi_pos_huangli_neg` | `ipo_approx_v1` | `conflict`（双侧） | 0.0036 | 0.0432 | `EXPLORATORY_NOT_GATED` |

预注册把冲突组合登记为**无方向性预测**的探索性对象，因此它**不套用单向 gate**、
**永远不解锁任何候选或支持状态**。如实记录，不做任何正面解读。

---

## 9. 纪律

1. **`SUPPORTED_OUT_OF_SAMPLE = 0` 是本阶段的正确结果**，不是失败。不为了让它变成 1 而调参。
2. **不修改 Phase 3D 结果**：3D 的状态、对照、分区统计全部只读引用。
3. **两版协议并排**：`gate_v1_status` 与 `gate_v2_status` 出现在同一张表里。
4. **族定义在结果之前冻结**，且用代码强制校验覆盖率。
5. **零结果照实输出**：42 个正式实验全部列出，含空结果与失败假设。

*创建于 2026-09-20*
