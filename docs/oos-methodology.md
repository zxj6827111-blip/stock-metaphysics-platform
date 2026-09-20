# Phase 3D · 样本外（OOS）研究管线方法学

> 版本：`split_version = phase3-oos-v1`、`calibration_version = cal-v1`、
> `label_version = phase3d-hfq-adjfactor-v1`、`gate_version = phase3d-oos-gate-v1`
> 冻结日期：2026-09-20 · 数据快照：`phase3a_astockdata_cutoff_20260814`（宇宙 `v2-phase3a`）

本文件说明 Phase 3D 如何回答一个问题：**在严格样本外条件下，八字 / 紫微 / 黄历
及其共识组合是否具有可复现的历史信息量。** 它同时说明本管线**不**回答什么。

---

## 1. 结论边界（先读这一节）

* 本阶段最多产出 `OOS_CANDIDATE_SUPPORTED`（候选），**不会**产出
  `SUPPORTED_OUT_OF_SAMPLE` —— 正式解锁需要多重检验校正（BH-FDR），属 Phase 3F。
* 所有方向、分数、事件都是**传统规则强度的分布重表达**，不是上涨概率、预期收益
  或投资建议。
* 样本外"没有信号"是允许且预期内的结论；本阶段不得因为结果不好看而调整任何阈值。

---

## 2. 固定 holdout 切分（GOAL §3 / §5）

| 分区 | 区间 | 允许做的事 |
|---|---|---|
| TRAIN | 2010-01-01 .. 2018-12-31 | 拟合 cal-v1（P25/P75、均值/标准差、经验分位）、定义假设 |
| VALIDATION | 2019-01-01 .. 2022-12-31 | 方向一致性对照、参数稳定性检查 |
| OOS | 2023-01-01 .. 2026-08-14 | **最终一次性评估**；不得再调阈值/换因子/换出生模型/换事件定义 |

切分由**日历**决定，与行情、收益、标签无关，因此切分本身不引入未来信息。
`ResearchSplit` 在构造时即断言区间严格递增且不重叠（时间方向不得反转），
越界读取会 `raise`（`SplitContractError`），不静默丢弃。

`oos_end` = AStockData 快照截止日（2026-08-14），是**数据可得性**上界，不是研究截止日。

## 3. Calibration V1 冻结（GOAL §2）

```
calibration_version = cal-v1（= 仓库既有 research-calibration-v1）
fit_period          = 2010-01-01 .. 2018-12-31
fit_scope           = TRAIN_ONLY
oos_labels_seen     = false（冻结时）
冻结内容            = P25/P75 方向阈值、z-score 的均值/标准差、经验分位参考分布
```

* Phase 3C 只审计了特征分布，未读取未来收益标签；本阶段从第一次读取 OOS 收益起，
  上述产物**冻结**。任何修改必须新建 `cal-v2` 并重新定义 OOS 协议，不得静默覆盖。
* 冻结记录由 `src/research/oos/calibration_freeze.py` 的 `FREEZE_V1` 承担，
  并提供 `assert_fit_within_train` / `assert_partition` / `assert_holdout_fit` 三道断言。
* 采样是离散网格（季度），因此 fit 实际用到的最后一个 `as_of` 为 `2018-10-01`
  （网格点），与边界 `2018-12-31` 相差 91 天 —— 该滞后写入审计字段
  `fit_lag_days_vs_train_end`，不允许越界。

## 4. 采样设计

| 面板 | 步长 | 区间 | 用途 |
|---|---|---|---|
| 主面板 | 3 个月（季度） | 2010-01-01 .. 2026-08-14（68 点） | 全部 holdout 实验、walk-forward 的重拟合数据源 |
| 月度 OOS 子面板 | 1 个月 | 2023-01-01 .. 2026-08-14（44 点） | **仅**用于重叠窗口敏感性检查 |
| 出生平移面板 | 3 个月 | 2023-01-01 .. 2026-08-14（16 点）×（−7 天 / +7 天） | 出生日期平移负对照（仅 OOS） |

选择季度作为主步长的理由：**20D/60D 持有窗口在季度网格下天然不重叠**
（相邻采样点相距约 63 个交易日）。这从设计上消除了"重叠标签伪样本"问题，
而不是事后修补。月度子面板则专门用于量化"如果采样更密会发生什么"。

`as_of` 统一取每月 1 日 15:00（与 Phase 3C 一致）；基准日取该股票
`trade_date >= as_of` 的第一个交易日。`as_of` 可以是非交易日。

## 5. 对象与事件定义（GOAL §9 / §21）

事件定义**只能来自预注册文件** `config/phase3d_hypothesis_registry.yaml`
（`registry_version = phase3d-hypotheses-v1`，`oos_labels_seen_at_registration: false`），
共 18 个假设 × 3 个出生模型 = 54 个正式实验：

* 单引擎（raw + calibrated）：`bazi` / `ziwei` / `huangli` 各 2 个
* 两两共振（raw + calibrated）：`bazi+ziwei` / `bazi+huangli` / `ziwei+huangli`
* 三模型共振（raw + calibrated）：`ALL_THREE`
* 预定义冲突组合（calibrated，**探索性**）：4 个

命中语义：

| logic | 含义 |
|---|---|
| `single` | 该引擎方向为正（raw: score ≥ 58；calibrated: opinion_score > TRAIN 冻结 P75） |
| `all_positive` | 参与引擎**全部**为正；任一引擎缺失 → 不命中（缺数据不得当 0 或当命中） |
| `conflict` | 指定正引擎为正、负引擎为负；用于预定义冲突形态 |

`expected_direction`：`positive` 进入单向 OOS 状态门；`exploratory`（冲突组合）
不做方向性预测，**执行全部负对照与诊断但不套用单向 gate**，结果以双侧描述统计给出，
状态记为 `EXPLORATORY_NOT_GATED`。

出生模型：`listing_open_v1` / `listing_close_v1` / `ipo_approx_v1` 逐个研究、不合并；
`company_foundation` 仍为 `UNAVAILABLE`（不造数据）。`ipo_approx_v1` 的**所有**结果
强制携带 `IPO_APPROXIMATION_WARNING` —— 它是近似口径，不是真实公司成立时间。

## 6. 未来收益标签（GOAL §12）

统一入口：`src/research/labels/horizon_returns.py`（唯一允许计算标签的模块）。

* 持有期：`ret_5d/10d/20d/60d` + `excess_return_5d/10d/20d/60d`（同口径同补丁）。
* **基于真实交易日**：第 N 个持有期 = 该股票自己的第 N 根后续 bar；停牌造成的
  "实际跨度更长"是真实风险，不做平滑。若 `as_of` 落在停牌区间，基准日顺延到
  复牌后的第一个交易日（与 Phase 1 的 `compute_labels` 口径一致）—— 这意味着停牌
  股票的持有窗口起点可能晚于 `as_of`，该性质在事件表里保留 `trade_date` 可核对。
* **复权**：canonical 行情是 `composite_none`（不复权原始价）。直接用它算收益会把
  除权除息当成下跌，因此收益一律用 `close × adj_factor` 计算
  （`raw × adj_factor / adj_factor[ref]` 中参考点自动抵消）。
  adj_factor 来自 TuShare 快照 `tsfactor_20260731T221443_49624041`，并以
  `tsfactor_20260806T110553_91dc1a9e`（311 只退市股）补齐 —— **两个快照的并集覆盖全部
  500 只**，覆盖率诊断（`matched_rows` / `filled_rows` / `uncovered_rows`）在
  `phase3d_calibration_freeze.json` 中披露。
* **超额收益**与 `ret_Nd` 使用**完全相同的日历区间**（股票端点 trade_date 之间），
  基准（沪深 300，`IDX000300`）按同区间取价 —— 避免停牌股票跨越远超 N 个自然日、
  而基准只走 N 个交易日造成的口径错配。
* **不可用一律为 `null`**：上市晚、已退市、接近数据末端时字段为 `None`，
  并在 `horizon_available` 显式标记；**绝不填 0**。

## 7. 负对照（GOAL §14）

| 对照 | 做法 | 适用性 / 已知局限 |
|---|---|---|
| `random_event_position` | 从同分区"可用 (股票, as_of) 池"随机抽取**同数量**事件，200 次置换 | 通用；对照值是置换分布均值，`p` 为单侧经验概率 `(#{draw ≥ real}+1)/(draws+1)` |
| `random_birth_assignment` | 在同一 `as_of` 内把命盘（引擎方向向量，全引擎一起置换）随机指派给池内其它股票 | 通用；只检验"股票↔命盘对应关系"的信息量 |
| `random_model_direction` | 保持每日命中数量，随机选择**哪些**股票命中 | 事件集合接近整个池时会退化（原始正向率 96% 即属此类） |
| `shifted_birth_date_±7d` | 出生时间平移 ±7 天后**重新排盘、重算因子**，用真实 TRAIN 冻结阈值重新求解事件 | 只覆盖 OOS 区间；使用真实 TRAIN 阈值（平移面板未采集 TRAIN）→ 是"同一阈值语义下的反事实" |

* 黄历（`H_*`）因子口径为「黄历 × 原局」（日干支五行与喜用神关系、与原局日支的刑冲合），
  因此三个引擎**都**依赖出生盘，出生平移对照对三者均适用。
* Jaccard > 0.9 判 `INVALID_CONTROL`（与 Phase 1/2 同口径）：对照与真实事件集合
  几乎相同意味着**方法失效**，任何"打平"都不能解读为"没有信息量"。
* 事件集合接近整个面板时（例如原始 BAZI_POS 正向率 94%–96.6%），随机类对照必然失效
  —— 这是 Phase 3C 的已知偏置在 OOS 阶段的**结构性后果**，如实输出为 `INVALID_CONTROL`。

## 8. OOS 状态门（GOAL §15）

`gate_version = phase3d-oos-gate-v1`，阈值写死在 `src/research/oos/gates.py`：

| 编号 | 条件 | 阈值 |
|---|---|---|
| G1 | 数据真实性 | 无合成/降级行情 |
| G2 | OOS 事件数 | ≥ 100（主持有期有效样本 ≥ 8） |
| G3 | 负对照有效 | 所有对照 Jaccard ≤ 0.9 且至少一类可判定 |
| G4 | 与 Validation 方向一致 | 符号相同且非零，Validation 事件数 ≥ 60 |
| G5 | 优于**每一类**有效对照 | 逐类比较，不允许"击败一类即通过" |
| G6 | 效应量非零 | \|Cohen's d\| ≥ 0.02 |
| G7 | 显著性 | 置换法单侧 p < 0.05（随机事件位置零假设） |
| G8 | 跨年份稳定 | 有效年数 ≥ 3，正向年份比例与符号一致性 ≥ 0.6 |
| G9 | 非单一股票驱动 | top1 绝对贡献份额 ≤ 0.5 且 LOO 无符号翻转 |
| G10 | 校准完全来自训练数据 | `fit_max_as_of ≤ train_end` 且 `fit_scope = TRAIN_ONLY` |

状态映射：G1 失败 → `NO_REAL_DATA`；无事件 → `NOT_RUN`；样本不足 → `INSUFFICIENT_SAMPLE`；
对照失效 → `INVALID_CONTROL`；未击败任何对照 → `NO_SIGNAL`；对照结论不一致或方向不一致
→ `INCONCLUSIVE`；其余强度/稳健性条件未满足 → `WEAK_EVIDENCE`；十项全过 →
`OOS_CANDIDATE_SUPPORTED`（携带 `pending_fdr = true`，见 §1）。

**报告纪律**：所有 4 个持有期（5/10/20/60D）全部报告，主持有期 20D 只用于 gate 判定，
禁止"挑最好的一档后只报告它"。

## 9. 重叠窗口与稳健性诊断（GOAL §13 / §16 / §17）

* `overlap_ratio`：同股票在持有期内还有其它事件的比例。主面板为季度采样，
  20D/60D 天然非重叠（`overlap_ratio = 0`）；月度 OOS 子面板用于量化密集采样的影响，
  并给出 `all_events` vs `non_overlapping_events` 的对照结果。
* 年份稳定性：逐年的平均超额收益、上涨率、方向，以及 `positive_year_ratio` /
  `sign_consistency`。整体正收益若只由某一极端年份驱动，不允许判"稳定"。
* 单一股票依赖：`top_1_contribution` / `top_5_contribution`（绝对贡献质量份额）
  与 leave-one-stock-out；删掉一只股票就翻转符号的结果标记 `SINGLE_NAME_DEPENDENT`。
* 效应量：真实组 vs 同分区可用池的 Cohen's d（合并标准差），以及 Welch t（正态近似 p）。

## 10. 实验登记与 OOS 复用纪律（GOAL §20 / §22）

* 每个正式实验在 `phase3d_experiment_registry.csv` 中登记：`experiment_id` /
  `hypothesis_id` / `git_sha` / `dataset_version` / `universe_version` /
  `birth_model_version` / `factor_version` / `calibration_version` / `split_version` /
  三段区间 / `horizon` / `parameters` / `random_seed` / `created_at` / `result_status`。
* 同时写入既有 `backtest_experiment` / `backtest_result` 表（`kind="oos"`，
  版本信息放 `params_json`）—— **复用现有表结构，不新增表、不改 schema、不写迁移**。
* OOS 一旦被真实读取，`oos_used = true` 写进实验元数据。此后修改阈值、因子选择、
  出生模型或事件定义，必须新建 experiment version 并附
  `RESEARCH_REUSE_WARNING`；原 OOS 不再被视为 untouched holdout。

## 11. 本阶段已知限制（必须与结果一起阅读）

1. **未做多重检验校正**：54 个实验共享同一 OOS 区间，`p` 值未做 BH-FDR / Bonferroni
   校正 → 这是 3D 不产出 `SUPPORTED_OUT_OF_SAMPLE` 的直接原因（3F 负责）。
2. **行业无 PIT**：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`，未做行业中性化（3E 负责）。
   OOS 结果可能混入行业/风格结构。
3. **基准与个股来源不同**：`IDX000300` 来自腾讯快照，个股来自 AStockData；
   按"都有数据的区间"对齐（2010 起benchmark 数据完整）。
4. **出生平移对照只覆盖 OOS**，且使用真实 TRAIN 冻结阈值（未采集平移面板的 TRAIN）。
5. **`listing_open` 不是真实成立时间**：三个出生模型都是"上市日派生"的口径，
   真实公司成立日 `company_foundation` 不可得；因此本阶段结论只适用于
   "上市时间派生盘"这一研究构造，不能外推到"公司真实命理"。
6. **退市股除权因子来自第二个快照**（311 只），其日期覆盖与主快照可能存在细微差异，
   已用覆盖率字段披露。
7. **未做交易成本 / 流动性 / 涨跌停约束**：本阶段是信息量检验，不是可交易性检验。

## 12. 复现方式

```bash
# 采集（8 进程并行，约 40–60 分钟）+ 全部分析与产物
python scripts/phase3d_oos_pipeline.py --parallel 8 --step-months 3 --persist-db
# 复用缓存重跑分析（不重新排盘）
python scripts/phase3d_oos_pipeline.py --skip-collect --persist-db
# 小样本连通性冒烟（不写正式产物）
python scripts/phase3d_smoke.py --codes 40 --step-months 12
```

产物：`data/phase3_universe/phase3d_*.csv`、`phase3d_run_summary.json`、
`phase3d_hypothesis_registry.json`、`phase3d_calibration_freeze.json`，
以及结果报告 [`phase3d-oos-results.md`](phase3d-oos-results.md)。
