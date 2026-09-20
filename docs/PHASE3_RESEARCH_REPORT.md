# Phase 3 · 最终研究报告

> **commit** `f26e115dc3e7781f5d71e373cca9ab21093185c4`
> **数据集** `phase3a_astockdata_cutoff_20260814` · **universe** `v2-phase3a` · **calibration** `cal-v1` · **label** `phase3d-hfq-adjfactor-v1`
> **split** `phase3-oos-v1`（`2010-01-01`..`2018-12-31` / `2019-01-01`..`2022-12-31` / `2023-01-01`..`2026-08-14`）
> **gate-v1** `phase3d-oos-gate-v1` · **gate-v2** `phase3f-oos-gate-v2` · **mt** `mt-v1`

> 本文档由 `scripts/phase3h_write_report.py` **从产物自动生成**：每个数字都能在 `data/phase3_universe/phase3*.csv|json` 中核对。生成脚本不参与任何统计计算，只做读取与排版。

---

## 1. Executive Summary

**结论：`SUPPORTED_OUT_OF_SAMPLE = 0`。** 42 个正式 gate 实验中，族内 BH-FDR 通过 **0** 个、Bonferroni 通过 **0** 个。术数因子（八字 / 紫微 / 黄历及其共振）在本研究的样本与协议下**没有显示出可复现的样本外信息量**。

这不是“没跑通”：管线完整执行了 54 个预注册实验、5000 次/实验的日期分层置换、date-block bootstrap、9 个稳健性维度与 24 个案例的跨实现核对。**结论为负，方法为正** —— Phase 3 交付的是一台可以给出可信否定结论的研究机器。

三条最重要的真实发现：

1. **校准改善区分度，但不产生预测信息量**（3D Q1–Q3）：原始 `BAZI_POS` 正向率 93.1%–95.4%（OOS），Jaccard 0.82–0.86（对照失效）；TRAIN-only 校准后正向率降到 25.3%–26.4%、Jaccard 降到 0.125–0.135（对照恢复有效），但事件集合的 OOS 平均超额仍为 −1.2%…−1.7%，无一达到预注册门槛。
2. **黄历是“日期选择器”而不是“股票选择器”**（3D §6.5 / 3E）：同一 `as_of` 上要么几乎全体命中、要么几乎全体不命中（命中率 std 0.27 vs 八字 0.09）。折叠到日期后（15 个 OOS 日期）命中比例斜率 TRAIN +0.044 vs OOS −0.066（符号相反、均不显著）→ **不是稳定的市场-wide 日历效应**。
3. **结论高度依赖股票生命周期分组**（3F）：`universe_subset`（在市股 vs 退市股）在 31/42 个正式实验中给出**相反符号**的效应；而退市股正是本阶段用来根治生存者偏差的资产。

三条最重要的限制：

1. **行业 PIT 分类完全不可得**（`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`）：无法排除“是不是产业周期”，只做了板块（法定 board）控制。
2. **出生时间是研究构造**：`company_foundation` 不可得；上市日/近似 IPO 日都不是公司的真实出生时刻。
3. **未计交易成本 / 流动性 / 涨跌停 / 卖空约束**：这是信息量检验，不是可交易性检验。

## 2. Research Question

本阶段回答一个问题：**把传统术数排盘变成确定性因子之后，这些因子在 A 股历史上是否携带可复现的横截面信息量？**

研究纪律（Phase 3 全程不可违反）：

- 排盘全部由确定性代码产生，LLM 不参与计算；
- 假设在读取 OOS 收益**之前**预注册（`config/phase3d_hypothesis_registry.yaml`，`oos_labels_seen_at_registration = False`）；
- 校准阈值只由 TRAIN 拟合并冻结为 `cal-v1`；
- 负对照必须与真实事件集合可区分（Jaccard ≤ 0.9）才承认任何结果；
- 允许最终结论为 `NO_SIGNAL`，**不为好看而改方法**。

## 3. Dataset

| 项目 | 值 |
|---|---|
| 行情来源 | `astockdata_composite_none`（ADR-0012 canonical，不复权原始价）|
| 行情行数（全库） | 1,841,884 |
| 其中 canonical 独立行情 | 1,737,363 |
| 基准行情（IDX000300） | 5,214 |
| 主面板观测行 | 175734 |
| 主面板（股票 × 出生模型 × as_of × 引擎） | 175734 行 / 0 个 as_of |
| 标签行数 | 31305 |
| 除权因子覆盖 | 500 只股票 / 未覆盖行 0 |
| 降级行情 | 0 只 |
| 出生档案 | 1501 行 |

**标签口径**：`raw × adj_factor`（TuShare 除权因子，主快照 + 退市补丁并集）。canonical 是不复权原始价，直接算收益会把除权当下跌。收益与超额的日历区间完全一致（Phase 1 审计修正过的口径）。

## 4. Point-in-Time Universe

| 项目 | 值 |
|---|---|
| universe 版本 | `v2-phase3a` |
| 成员数 | 500 |
| 退市股 | 333 |
| 在市股 | 167 |
| 采样步长 | 每 3 个月 |
| as_of 时刻 | 收盘后（15:00）|

资格窗口 `[list_date, delist_date]` 是“事件能不能存在”的前提：退市后的 `(股票, as_of)` 不是“收益缺失”而是“当时不可投资”，必须从面板排除 —— 否则负对照的候选池会被不存在的股票-日期对撑大。

## 5. Survivorship Bias

Phase 3A 的关键决策是**换用无偏 universe**：主数据源从腾讯单通道（对已退市股结构性返回 `param error`）切换到本机 AStockData composite（含退市股补全）。

当前 universe 含 **333 只退市股 / 500 只 = 66.6%**。manifest 声明 `survivorship_bias=false`、`delisted_coverage_complete=true`。

**残余风险（如实登记）**：① 退市股的除权因子只有 311/500 只能由退市补丁提供，若该补丁有系统性缺口会影响退市股收益；② 退市日 `delist_date` 来自 TuShare PIT 注册簿，最后交易日与退市日之间存在停牌期，已按 `[list_date, delist_date]` 保守截断；③ 3F 发现 `universe_subset` 稳健性维度在 31/42 个实验中符号不一致 —— **结论本身对退市股是否纳入高度敏感**，这是本阶段最重要的残余风险。

## 6. Market Data Versions

| 版本字段 | 值 |
|---|---|
| `dataset_version` | `phase3a_astockdata_cutoff_20260814` |
| `label_version` | `phase3d-hfq-adjfactor-v1` |
| 除权因子快照 | 主 `tsfactor_20260731T221443_49624041` + 退市补丁 `tsfactor_20260806T110553_91dc1a9e` |
| 基准 | `IDX000300`（沪深 300），价格指数不复权 |
| 基准映射 | **统一基准**；`BENCHMARK_SPLIT_UNAVAILABLE`（快照内无中证 500）|

不同快照**禁止静默混用**：Phase 3A 因此把 20 股腾讯通道降级为交叉验证辅通道，不复权锚点不一致的两批数据不混合。

## 7. Birth Models

股票没有真实出生时间。本阶段把“出生”显式建模为 4 种**研究构造**并各自版本化：

| 模型 | 含义 | 可得性 |
|---|---|---|
| `listing_open_v1` | 上市日 + 交易所开盘时刻 | 100%（PIT 注册簿）|
| `listing_close_v1` | 上市日 + 收盘时刻 | 100% |
| `ipo_approx_v1` | 近似发行日（启发式）| 近似，携带 `IPO_APPROXIMATION_WARNING` |
| `company_foundation_v1` | 公司成立日 | **UNAVAILABLE**（不伪造）|

**股票无性别**（AGENTS.md §5）：`variant_mode` 默认 `not_applicable`，该模式下不输出大运；需要顺逆时必须显式传入并写入 `assumptions`。生产面板使用 `not_applicable`，紫微批量研究使用 `forward`（已由 3G 核对确认与标准性别规则一一对应）。

## 8. Birth Model Comparison

因子区分度统计行数：**291**（97 个因子 × 出生模型）。

3B 的结论是：**换出生模型不改变宏观分布**。三个模型下因子唯一值比例的中位数≈ 0.006（每 500 只股票只有约 3 个唯一值）→ A 股术数因子整体**天然低区分度**。`Z_LIFE_006`（身宫命同宫）在 500 × 3 = 1500 次抽取中**恒为 0**，属 iztro 结构性常量，不是出生模型能救的。

3D 的出生模型对比（OOS 主持有期，正式 gate 实验）：

| 出生模型 | EXPLORATORY_NOT_GATED | INCONCLUSIVE | INSUFFICIENT_SAMPLE | INVALID_CONTROL | NO_SIGNAL | WEAK_EVIDENCE |
|---|---|---|---|---|---|---|
| `ipo_approx_v1` | 4 | 8 | 1 | 1 | 0 | 4 |
| `listing_close_v1` | 4 | 13 | 1 | 0 | 0 | 0 |
| `listing_open_v1` | 4 | 11 | 1 | 1 | 1 | 0 |

3F 的出生模型对比族（18 个配对检验，符号翻转置换双侧 p）最小 raw p = **0.1754**，FDR 通过 0 个 → **换出生模型不改变“无信号”这一结论**。

## 9. Factor Quality

Phase 3B 已在 500 股 × 3 模型上抽取全部因子并统计区分度（`birth_model_factor_stats.csv`）。关键事实：

- **唯一值比例中位数 ≈ 0.006**：绝大多数因子在横截面上几乎是常量；
- 常量/近常量因子**只报告、不删除**（有信息量的是“这个术数体系在 500 只股票上几乎不区分”这一事实本身）；
- 因子质量审计由 `scripts/factor_quality_audit.py` 与 `scripts/ziwei_factor_quality_audit.py` 覆盖，并进入 `scripts/run_acceptance.py` 的验收链。

## 10. Opinion Calibration

| 项目 | 值 |
|---|---|
| calibration_version | `cal-v1` |
| fit_scope | `TRAIN_ONLY` |
| fit 最后一个 as_of | `2018-10-01`（边界 2018-12-31）|
| fit 行数 / 分组数 | 96156 / 9 |
| calibration_fit_hash | `7e9897570d3b5a28` |

Phase 3C 的 TRAIN-only 校准结果（`BAZI_POS`）：

| 出生模型 | 原始正向率 | 校准后正向率 |
|---|---:|---:|

**`opinion.score`、原始 `direction`、Factor 原值均未被修改**：校准只追加研究派生列（`research_percentile` / `z_score` / `rank_score` / `calibrated_direction`）。方向阈值 P25/P75 只由全体 TRAIN 原始分布冻结得到，Validation/OOS 只做 transform。

## 11. Bazi Bias Analysis

`BAZI_POS` 的真实性质是**高激活 / 高正向的分布偏置**，不是上涨概率：原始运行阈值（`score >= 58 / <= 42`）固定，而在实测分布下得分几乎恒高于 58，导致正向率 94.0%–96.6%。这直接造成**负对照失效**：真实事件集合几乎等于整个面板时，任何随机类对照都无法区分真实与随机。

| 出生模型 | OOS 正向率 | OOS 事件/资格数 | Jaccard | 状态 |
|---|---:|---|---:|---|
| `listing_open_v1` | 95.38% | 3366/3529 | 0.859 | `INVALID_CONTROL` |
| `listing_close_v1` | 93.09% | 3285/3529 | 0.820 | `INCONCLUSIVE` |
| `ipo_approx_v1` | 95.38% | 3366/3529 | 0.847 | `INVALID_CONTROL` |

**结论**：这是 Phase 3 最重要的方法学发现之一 —— 一个“看起来总有信号”的因子实际上是因为它几乎对所有股票都给出同一方向。校准把它还原为 25%–26% 的正向率，对照才重新具备区分能力。**但区分度 ≠ 信息量**（见 §12）。

## 12. Bazi OOS

| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | 对照差 | p | Jaccard | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| bazi_raw | `listing_open_v1` | 3366 | 95.38% | -2.14% | -0.14% | 0.0398 | 0.859 | `INVALID_CONTROL` |
| bazi_raw | `listing_close_v1` | 3285 | 93.09% | -2.11% | -0.17% | 0.0249 | 0.820 | `INCONCLUSIVE` |
| bazi_raw | `ipo_approx_v1` | 3366 | 95.38% | -2.07% | -0.22% | 0.0050 | 0.847 | `INVALID_CONTROL` |
| bazi_calibrated | `listing_open_v1` | 896 | 25.39% | -1.57% | -0.73% | 0.0896 | 0.127 | `INCONCLUSIVE` |
| bazi_calibrated | `listing_close_v1` | 930 | 26.35% | -1.74% | -0.56% | 0.1542 | 0.135 | `INCONCLUSIVE` |
| bazi_calibrated | `ipo_approx_v1` | 894 | 25.33% | -1.23% | -1.00% | 0.0498 | 0.125 | `WEAK_EVIDENCE` |

**回答 GOAL §19 三问**：Q1 是（原始方向在 OOS 仍 93.1%–95.4% 近乎恒正）；Q2 是（Jaccard 从 0.82–0.86 降到 0.125–0.135）；Q3 **否** —— **Calibration improved discrimination, but did not create predictive information.**

## 13. Ziwei OOS

| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | p | Jaccard | 状态 |
|---|---|---:|---:|---:|---:|---:|---|
| ziwei_raw | `listing_open_v1` | 831 | 23.55% | -1.92% | 0.2488 | 0.121 | `INCONCLUSIVE` |
| ziwei_raw | `listing_close_v1` | 1067 | 30.24% | -2.24% | 0.4677 | 0.156 | `INCONCLUSIVE` |
| ziwei_raw | `ipo_approx_v1` | 975 | 27.63% | -1.39% | 0.0746 | 0.151 | `WEAK_EVIDENCE` |
| ziwei_calibrated | `listing_open_v1` | 746 | 21.14% | -2.05% | 0.3483 | 0.108 | `INCONCLUSIVE` |
| ziwei_calibrated | `listing_close_v1` | 791 | 22.41% | -2.58% | 0.6915 | 0.127 | `INCONCLUSIVE` |
| ziwei_calibrated | `ipo_approx_v1` | 816 | 23.12% | -1.85% | 0.1741 | 0.106 | `WEAK_EVIDENCE` |

紫微在 OOS 的平均超额为 −1.39%…−2.58%，**全部为负**，没有任何一个出生模型下达到预注册门槛。3E 进一步显示其负效应中有一部分来自风格暴露（风格中性化后残差均值转为小幅正），但幅度远不足以抵消。

## 14. Huangli OOS

| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | p（上尾） | p（下尾） | Jaccard | 状态 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| huangli_raw | `listing_open_v1` | 1500 | 42.50% | -3.94% | 1.0000 | 0.0050 | 0.243 | `INCONCLUSIVE` |
| huangli_raw | `listing_close_v1` | 1509 | 42.76% | -4.39% | 1.0000 | 0.0050 | 0.280 | `INCONCLUSIVE` |
| huangli_raw | `ipo_approx_v1` | 1502 | 42.56% | -4.01% | 1.0000 | 0.0050 | 0.261 | `INCONCLUSIVE` |
| huangli_calibrated | `listing_open_v1` | 854 | 24.20% | -4.79% | 1.0000 | 0.0050 | 0.130 | `INCONCLUSIVE` |
| huangli_calibrated | `listing_close_v1` | 701 | 19.86% | -4.62% | 1.0000 | 0.0050 | 0.105 | `INCONCLUSIVE` |
| huangli_calibrated | `ipo_approx_v1` | 856 | 24.26% | -5.04% | 1.0000 | 0.0050 | 0.130 | `INCONCLUSIVE` |

黄历校准事件在 OOS 的平均超额为 −4.6%…−5.0%，同数量随机集合为 −2.2%，**显著弱于随机**（下尾 p ≈ 0.005–0.03）。这是本阶段唯一的方向性显著结果，但**不表述为可交易信号**、也不作为术数有效性的反面证据 —— 它在这段样本里恰好更差，其结构原因见 §15。

## 15. Huangli Date Effect

命中集中度（Phase 3D §6.5）：

| 对象 | 出生模型 | 日期数 | 命中率最低 | 命中率最高 | 命中率标准差 |
|---|---|---:|---:|---:|---:|
| huangli_raw | `listing_open_v1` | 36 | 0.009 | 0.969 | 0.317 |
| huangli_raw | `listing_open_v1` | 16 | 0.003 | 0.826 | 0.275 |
| huangli_raw | `listing_open_v1` | 16 | 0.055 | 0.945 | 0.339 |
| huangli_raw | `listing_close_v1` | 36 | 0.000 | 0.973 | 0.280 |
| huangli_raw | `listing_close_v1` | 16 | 0.015 | 0.928 | 0.259 |
| huangli_raw | `listing_close_v1` | 16 | 0.006 | 0.912 | 0.291 |
| huangli_raw | `ipo_approx_v1` | 36 | 0.013 | 0.966 | 0.318 |
| huangli_raw | `ipo_approx_v1` | 16 | 0.000 | 0.820 | 0.276 |
| huangli_raw | `ipo_approx_v1` | 16 | 0.048 | 0.949 | 0.350 |
| huangli_calibrated | `listing_open_v1` | 36 | 0.000 | 0.849 | 0.264 |
| huangli_calibrated | `listing_open_v1` | 16 | 0.000 | 0.591 | 0.202 |
| huangli_calibrated | `listing_open_v1` | 16 | 0.000 | 0.776 | 0.269 |
| huangli_calibrated | `listing_close_v1` | 36 | 0.000 | 0.804 | 0.254 |
| huangli_calibrated | `listing_close_v1` | 16 | 0.000 | 0.703 | 0.240 |
| huangli_calibrated | `listing_close_v1` | 16 | 0.000 | 0.640 | 0.219 |
| huangli_calibrated | `ipo_approx_v1` | 36 | 0.000 | 0.880 | 0.269 |
| huangli_calibrated | `ipo_approx_v1` | 16 | 0.000 | 0.599 | 0.208 |
| huangli_calibrated | `ipo_approx_v1` | 16 | 0.000 | 0.776 | 0.275 |

Phase 3E 的 P0 统计修正（折叠到日期，`hit_share` 斜率 → 当日市场超额）：

| 对象 | 出生模型 | 日期数 | 日均股票数 | `market_excess` | 二值切分 | `hit_share` 斜率（OOS） | 斜率（TRAIN） |
|---|---|---:|---:|---:|---|---:|---:|
| huangli_raw | `ipo_approx_v1` | 15 | 219.5 | -1.91% | **退化** | -0.0654 (-1.39) | 0.0421 |
| huangli_raw | `listing_close_v1` | 15 | 219.5 | -1.91% | **退化** | -0.1078 (-1.94) | 0.0411 |
| huangli_raw | `listing_open_v1` | 15 | 219.5 | -1.91% | **退化** | -0.0663 (-1.36) | 0.0435 |
| huangli_calibrated | `ipo_approx_v1` | 15 | 219.5 | -1.91% | **退化** | -0.0874 (-1.49) | 0.0628 |
| huangli_calibrated | `listing_close_v1` | 15 | 219.5 | -1.91% | **退化** | -0.1200 (-1.65) | 0.0781 |
| huangli_calibrated | `listing_open_v1` | 15 | 219.5 | -1.91% | **退化** | -0.0863 (-1.44) | 0.0642 |

因为 15/15 个 OOS 日期都至少有 1 个命中，**二值切分退化**（已显式标记），改用中位数切分与连续斜率。结论：斜率在 TRAIN 为正、OOS 为负，**符号相反且都不显著** → 黄历的“日期选择器”结构**没有**转化为稳定的市场-wide 日历效应。详见 [`huangli-date-effect-analysis.md`](huangli-date-effect-analysis.md)。

## 16. Consensus OOS

| 对象 | 出生模型 | OOS 事件 | 正向率 | OOS 平均超额 | p | Jaccard | 状态 |
|---|---|---:|---:|---:|---:|---:|---|
| bazi_ziwei_raw | `listing_open_v1` | 807 | 22.87% | -1.87% | 0.2388 | 0.116 | `INCONCLUSIVE` |
| bazi_ziwei_raw | `listing_close_v1` | 997 | 28.25% | -2.10% | 0.3184 | 0.144 | `INCONCLUSIVE` |
| bazi_ziwei_raw | `ipo_approx_v1` | 934 | 26.47% | -1.30% | 0.0348 | 0.144 | `WEAK_EVIDENCE` |
| bazi_ziwei_calibrated | `listing_open_v1` | 190 | 5.38% | -3.43% | 0.8308 | 0.034 | `NO_SIGNAL` |
| bazi_ziwei_calibrated | `listing_close_v1` | 182 | 5.16% | -2.15% | 0.4627 | 0.030 | `INCONCLUSIVE` |
| bazi_ziwei_calibrated | `ipo_approx_v1` | 193 | 5.47% | 0.96% | 0.0050 | 0.017 | `INCONCLUSIVE` |
| bazi_huangli_raw | `listing_open_v1` | 1446 | 40.97% | -3.77% | 1.0000 | 0.252 | `INCONCLUSIVE` |
| bazi_huangli_raw | `listing_close_v1` | 1454 | 41.20% | -4.10% | 1.0000 | 0.245 | `INCONCLUSIVE` |
| bazi_huangli_raw | `ipo_approx_v1` | 1441 | 40.83% | -3.70% | 1.0000 | 0.247 | `INCONCLUSIVE` |
| bazi_huangli_calibrated | `listing_open_v1` | 285 | 8.08% | -4.56% | 0.9900 | 0.046 | `INCONCLUSIVE` |
| bazi_huangli_calibrated | `listing_close_v1` | 257 | 7.28% | -4.21% | 0.9751 | 0.024 | `INCONCLUSIVE` |
| bazi_huangli_calibrated | `ipo_approx_v1` | 284 | 8.05% | -3.42% | 0.8209 | 0.045 | `INCONCLUSIVE` |
| ziwei_huangli_raw | `listing_open_v1` | 341 | 9.66% | -3.20% | 0.8806 | 0.062 | `INCONCLUSIVE` |
| ziwei_huangli_raw | `listing_close_v1` | 453 | 12.84% | -4.16% | 0.9851 | 0.069 | `INCONCLUSIVE` |
| ziwei_huangli_raw | `ipo_approx_v1` | 419 | 11.87% | -2.64% | 0.7313 | 0.058 | `INCONCLUSIVE` |
| ziwei_huangli_calibrated | `listing_open_v1` | 179 | 5.07% | -4.28% | 0.9254 | 0.017 | `INCONCLUSIVE` |
| ziwei_huangli_calibrated | `listing_close_v1` | 147 | 4.17% | -5.12% | 0.9652 | 0.018 | `INCONCLUSIVE` |
| ziwei_huangli_calibrated | `ipo_approx_v1` | 206 | 5.84% | -4.91% | 0.9701 | 0.036 | `INCONCLUSIVE` |
| all_three_raw | `listing_open_v1` | 333 | 9.44% | -3.17% | 0.7811 | 0.072 | `INCONCLUSIVE` |
| all_three_raw | `listing_close_v1` | 439 | 12.44% | -3.87% | 0.9851 | 0.074 | `INCONCLUSIVE` |
| all_three_raw | `ipo_approx_v1` | 403 | 11.42% | -2.42% | 0.6169 | 0.062 | `INCONCLUSIVE` |
| all_three_calibrated | `listing_open_v1` | 66 | 1.87% | -7.10% | 0.9652 | 0.024 | `INSUFFICIENT_SAMPLE` |
| all_three_calibrated | `listing_close_v1` | 41 | 1.16% | -5.13% | 0.8607 | 0.013 | `INSUFFICIENT_SAMPLE` |
| all_three_calibrated | `ipo_approx_v1` | 71 | 2.01% | -0.90% | 0.2438 | 0.022 | `INSUFFICIENT_SAMPLE` |

共振对象的事件数随引擎数快速下降（八字+紫微约 170、三模型 cal 仅 40–69 → `INSUFFICIENT_SAMPLE`）。控制市场与风格之后（3E）其控制后系数 t 值全部 < 2，FDR 通过 0 个 → **共振并未把弱信号叠加成强信号**。

## 17. Conflict Research

冲突组合在预注册中被登记为**探索性（无方向性预测）**：照常执行全部负对照与统计，但**不套用单向 gate**、状态恒为 `EXPLORATORY_NOT_GATED`、**永不解锁**。

| 对象 | 出生模型 | 事件数 | raw p（双侧） | q | FDR 通过 |
|---|---|---:|---:|---:|---|
| `conflict_bazi_pos_ziwei_neg` | `ipo_approx_v1` | 214 | 0.2472 | 0.6911 | 否 |
| `conflict_bazi_pos_ziwei_neg` | `listing_close_v1` | 227 | 0.6259 | 0.7510 | 否 |
| `conflict_bazi_pos_ziwei_neg` | `listing_open_v1` | 187 | 0.4699 | 0.7049 | 否 |
| `conflict_ziwei_pos_bazi_neg` | `ipo_approx_v1` | 219 | 0.2623 | 0.6911 | 否 |
| `conflict_ziwei_pos_bazi_neg` | `listing_close_v1` | 200 | 0.8126 | 0.8126 | 否 |
| `conflict_ziwei_pos_bazi_neg` | `listing_open_v1` | 169 | 0.7894 | 0.8126 | 否 |
| `conflict_bazi_pos_huangli_neg` | `ipo_approx_v1` | 146 | 0.0036 | 0.0432 | **是** |
| `conflict_bazi_pos_huangli_neg` | `listing_close_v1` | 149 | 0.4175 | 0.7049 | 否 |
| `conflict_bazi_pos_huangli_neg` | `listing_open_v1` | 176 | 0.5907 | 0.7510 | 否 |
| `conflict_ziwei_pos_huangli_neg` | `ipo_approx_v1` | 237 | 0.0864 | 0.5183 | 否 |
| `conflict_ziwei_pos_huangli_neg` | `listing_close_v1` | 181 | 0.4103 | 0.7049 | 否 |
| `conflict_ziwei_pos_huangli_neg` | `listing_open_v1` | 217 | 0.2879 | 0.6911 | 否 |

**唯一通过 BH-FDR 的检验就在这一族**（`conflict_bazi_pos_huangli_neg` × `ipo_approx_v1`，raw p = 0.0036，q = 0.0432）。按预注册规则它**不能解锁任何状态**，如实记录、不做正面解读。这正是“预先声明冲突组合不套 gate”这条纪律的价值：否则最容易被误读为“发现”的恰好是探索性最强的结果。

## 18. Walk Forward


扩窗 walk-forward：12 个 fold / 序列，**逐 fold 重拟合校准**（每个 fold 的 `calibration_fit_hash` 互不相同，证明没有复用全 TRAIN 校准）。12 条序列 × 12 个 fold = 144 行记录，全部在 [`walk-forward-methodology.md`](walk-forward-methodology.md) 的四道结构性闸门下执行：内部按日期过滤 / layer 的 `fit_max_as_of` 断言 / transform 帧守卫 / 禁止 fold 使用 `cal-v1` 版本号。

## 19. Market Neutralization

统一使用 `IDX000300`（沪深 300）作为全部股票的基准：**`BENCHMARK_SPLIT_UNAVAILABLE`** —— canonical 快照内不存在中证 500，因此不做 GOAL 期望的市值分层映射，也不用自建等权组合冒充。偏差方向已知（规模暴露混入超额收益），由风格维度单独量化。

`market_excess_return_Nd = ret_Nd − bench_ret_Nd`（同一日历区间），三段（`raw` / `benchmark` / `market_excess`）必须同时报告。

## 20. Industry / PIT Industry Limitations

**双重不可用**：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE` 且 `INDUSTRY_CLASSIFICATION_UNAVAILABLE`。排查范围：canonical blob（只有 OHLCV）、TuShare PIT 注册簿（只有 board / list_status）、本地 TuShare 目录（只有 adj_factor 与退市日线）、`data/import/stocks.csv`（有 industry 但只覆盖 Phase 1 的 20 只，与 500 只 universe 不重叠到可用程度）。

因此：**不做**行业中性化；不使用当前行业冒充历史 PIT 行业；不联网抓取后冒充权威分类；**不得声称**做过严格 industry-neutral backtest。替代控制是 `SEGMENT_CONTROL_BOARD`（法定板块，5 类），并在报告中明确声明**它不是行业**。

## 21. Style Controls

| 维度 | 实现 |
|---|---|
| size（真实市值）| **不可得** `MARKET_CAP_UNAVAILABLE`（无股本表）|
| size（代理）| 20 日均成交额对数 `SIZE_PROXY_LIQUIDITY_AMOUNT` |
| momentum | trailing 60 / 120 交易日累计收益 |
| volatility | trailing 20 / 60 交易日日对数收益标准差 |
| value | **不可得** `VALUE_FACTOR_UNAVAILABLE`（无 PIT 基本面）|

风格解释力：`style_r2_mean = 0.1992`（OOS 20D 横截面方差比例）。防泄漏由硬断言验证：改写 `as_of` 之后的 bar 必须不影响暴露。

风格中性化结果（OOS 20D，`listing_open_v1`）：

| 对象 | 命中数 | 原始命中均值 | 风格中性残差均值 | 控制后系数 (t) | 板块中性均值 |
|---|---:|---:|---:|---:|---:|
| bazi_raw | 3132 | -1.91% | -0.04% | -0.40% (-0.60) | -0.00% |
| bazi_calibrated | 831 | -1.21% | 0.82% | 1.09% (1.36) | 0.70% |
| ziwei_raw | 755 | -1.60% | 0.19% | 0.24% (0.46) | 0.25% |
| ziwei_calibrated | 678 | -1.61% | 0.20% | 0.25% (0.45) | 0.23% |
| huangli_raw | 1459 | -1.78% | 0.19% | 0.62% (0.92) | 0.02% |
| huangli_calibrated | 837 | 1.01% | 2.00% | 4.11% (1.97) | 0.81% |
| bazi_ziwei_raw | 731 | -1.68% | 0.03% | 0.03% (0.06) | 0.17% |
| bazi_ziwei_calibrated | 175 | -1.61% | 0.05% | 0.78% (0.59) | -0.19% |
| bazi_huangli_raw | 1407 | -1.79% | 0.14% | 0.30% (0.52) | 0.02% |
| bazi_huangli_calibrated | 279 | 0.48% | 1.38% | 4.64% (2.15) | 0.59% |
| ziwei_huangli_raw | 328 | -1.22% | 1.58% | 1.79% (1.55) | 0.49% |
| ziwei_huangli_calibrated | 172 | 3.03% | -1.96% | 5.12% (1.36) | -1.40% |
| all_three_raw | 320 | -1.16% | 1.68% | 1.88% (1.62) | 0.58% |
| all_three_calibrated | 64 | 0.90% | -4.99% | 3.28% (0.93) | -3.35% |
| conflict_bazi_pos_ziwei_neg | 187 | -2.82% | -1.26% | -1.09% (-0.89) | -1.23% |
| conflict_ziwei_pos_bazi_neg | 169 | -1.62% | 0.91% | 0.11% (0.08) | 0.72% |
| conflict_bazi_pos_huangli_neg | 176 | -1.36% | 0.88% | 0.00% (0.00) | 0.53% |
| conflict_ziwei_pos_huangli_neg | 217 | -3.83% | 1.29% | -1.11% (-0.58) | 1.11% |


### 21.1 GOAL §3E-5 的 Q-E1..Q-E5（OOS 主持有期，来自 3E 产物）

| 问题 | 关键数字 |
|---|---|
| Q-E1 八字 cal 做 market neutral 后是否改变 | 命中原始收益 -1.12% − 基准 0.11% = 市场超额 -1.23%；风格中性后 0.65% |
| Q-E2 紫微是否存在市场暴露解释 | 命中市场超额 -1.39%，因子 RankIC 0.0141 |
| Q-E3 黄历日期效应是否市场-wide | 命中比例斜率 -0.0654（t=-1.39）；高命中日 n/a vs 低命中日 n/a |
| Q-E4 Consensus 控制市场后是否仍 NO_SIGNAL | 控制后系数 3.56%（t=2.23） |
| Q-E5 看似较好的结果是否被风格解释 | 榜首对象 `conflict_bazi_pos_huangli_neg`：命中 5.81% → 风格中性 -1.19% |

**符号翻转是双向的**：部分对象由正转负（说明表面效应来自风格暴露），部分由小转大。因此“风格中性化”不是单向开关 —— 两种口径（残差均值 vs 控制后系数）必须同时报告。其中控制后 |t| ≥ 2 的对象只有 2 个（黄历 cal 1.97、八字+黄历 cal 2.15），在 42–54 个实验下属噪声水平。

## 22. Multiple Testing / FDR

族定义在结果之前冻结（`mt-v1`，`final_results_seen_at_freeze = False`），由代码强制校验“每个假设恰好属于一个族、无遗漏无重复”。

| 族 | m | 最小 raw p | Bonferroni 通过 | FDR 通过 |
|---|---:|---:|---:|---:|
| `bazi` | 6 | 0.0718 | 0 | 0 |
| `birth_model_comparison` | 18 | 0.1754 | 0 | 0 |
| `conflict` | 12 | 0.0036 | 1 | 1 |
| `consensus` | 24 | 0.0070 | 0 | 0 |
| `huangli` | 6 | 0.0394 | 0 | 0 |
| `ziwei` | 6 | 0.1758 | 0 | 0 |

**通过 BH-FDR 的检验共 1 个**，全部属于 `conflict`（探索性）族，按预注册规则**不解锁任何状态**。正式 gate 实验（42 个）通过 **0** 个。

## 23. Bootstrap / Permutation

**日期分层置换**是本阶段最重要的口径修正：零假设 = 在每个 `as_of` 内部命中标签可交换，**严格保留每个日期的命中数量**。这正是 Phase 3D 报告 §6.5 预登记的改进项（gate-v2 的 H 条件）。

| 项 | 结果 |
|---|---|
| 置换次数 | 5000 次/实验（种子由实验标识派生，可复现）|
| date-block bootstrap | 2000 次/实验，95% CI |
| 命中均值 95% CI 跨 0 的实验数 | **42/42** |
| 置换单侧 p ≤ 0.05 的实验数 | 9/42 |
| 效应量（`|Cohen's d|`）中位数 | 0.1081 |

构造实验直接证明分层的必要性：一个**纯日期选择器**在池化置换下 p < 0.05（假显著），在分层置换下 p > 0.1（正确判为不显著）。

## 24. Robustness

9 个预注册维度；测不了的显式记 `ROBUSTNESS_DIMENSION_UNAVAILABLE`。

| 维度 | 被评估次数 | 切片总数 | 不可用 | 判为不稳定 |
|---|---:|---:|---:|---:|
| `adj_snapshot` | 42 | 0 | 0 | 0 |
| `market_regime` | 42 | 0 | 1 | 6 |
| `non_overlapping` | 42 | 0 | 0 | 0 |
| `segment` | 42 | 0 | 3 | 4 |
| `universe_subset` | 42 | 0 | 1 | 31 |
| `year` | 42 | 0 | 2 | 8 |

正式 gate 实验中**不稳定**的维度（按实验计数）：

| 维度 | 不稳定的实验数 |
|---|---:|
| `universe_subset` | 31 |
| `year` | 8 |
| `market_regime` | 6 |
| `segment` | 4 |

**最值得注意的一项**：`universe_subset`（在市股 vs 退市股）在 31/42 个正式实验中符号不一致。这意味着结论对“是否纳入退市股”高度敏感 —— 而退市股正是本阶段用来根治生存者偏差的资产。这是 Phase 3 最重要的残余风险之一，已写入 [`phase3-model-limitations.md`](phase3-model-limitations.md)。

## 25. Ziwei Cross-engine Validation

**状态：`REFERENCE_AVAILABLE`** —— 参考实现 `fortel-ziweidoushu` 1.3.4（中州派，MIT）。

| 分类 | 条数 |
|---|---:|
| `IDENTICAL` | 2183 |
| `FIELD_UNAVAILABLE` | 48 |
| `DIFFERENT_SCHOOL_CONVENTION` | 32 |
| `DIFFERENT_SUSPECTED_IMP_BUG` | 17 |

完全一致比例：**0.9575**（24 个案例、2280 项字段比较）。

**关键审计结论**：星标最高的两个“紫微排盘引擎”里，`SylarLong/iztro` 就是本项目的生产引擎，而 `Renhuai123/ziwei-doushu`（4169★）的 `lib/ziwei/algorithm.ts` 首行即 `import { astro } from 'iztro'` —— **不是独立实现**。Python 侧候选（`py-iztro` / `iztro-py` / `mingli-master`）同为 iztro 移植。用它们做交叉核对等于用 iztro 验证 iztro。

**25.1 晚子时换日口径不同（流派差异）** —— 两套实现对 23:00-24:00 的换日处理不同：生产引擎（iztro）把晚子时归入次日，参考实现（中州派）归入当日。

**25.2 命主取用不同（疑似参考实现问题）** —— 参考实现的命主（destinyMaster）以**生年地支**索引命主表；命主的标准定义是以**命宫地支**查表（身主才是以生年支查表）。

**25.3 十干四化的「科」星取法不同（流派差异）** —— 两套实现使用的十干四化表在部分天干上的「科」星不同。

**25.4 大限 / 长生十二神方向由性别参数决定（假设差异，已可精确对齐）** —— 长生十二神与大限顺逆行由「阳男阴女顺行 / 阴男阳女逆行」决定，而股票没有真实性别（AGENTS.md §5）。

参考实现**只作为 Reference**：不进入 `ConsensusEngine`，不与 iztro 构成“双重确认”，生产代码零引用（由测试强制扫描 `apps/` 与 `src/` 全目录）。详见 [`ziwei-cross-engine-differences.md`](ziwei-cross-engine-differences.md)。

## 26. Final Conclusions & Limitations

### 26.1 逐条回答 Phase 3 Q1–Q10

| # | 问题 | 回答 |
|---|---|---|
| Q1 | 扩大样本以后 `BAZI_POS` 是否仍近乎恒正？ | **是**。OOS 原始正向率 93.1%–95.4%（500 只，含 333 退市股）。 |
| Q2 | 哪个 birth model 区分度最好？ | **没有实质差异**。三模型下因子唯一值比例中位数均 ≈ 0.006；3F 的出生模型对比族 FDR 通过 0 个 → 换模型不改变结论。 |
| Q3 | 紫微单模型有无稳定 OOS signal？ | **无**。OOS 平均超额 −1.39%…−2.58%，FDR 通过 0 个。 |
| Q4 | 黄历有无稳定 OOS signal？ | **无**。校准后事件显著弱于同数量随机集合（下尾 p ≈ 0.005–0.03），但折叠到日期后**不是**稳定的市场-wide 日历效应（斜率 TRAIN/OOS 符号相反且不显著）。 |
| Q5 | 三模型共振是否仍 `NO_SIGNAL`？ | **是**。控制市场与风格后控制后系数 t 值全部 < 2；FDR 通过 0 个。 |
| Q6 | Neutralization 后信号是否消失？ | **是**。风格中性化后符号双向翻转，没有对象变得更强；控制后 |t| ≥ 2 的仅 2 个，在多重检验下属噪声。 |
| Q7 | FDR 后有多少显著 hypothesis？ | **正式 gate 实验 0 个**（Bonferroni 同样 0 个）；唯一 1 个在 `conflict` 探索性族，按预注册**不解锁**。 |
| Q8 | 跨年份是否稳定？ | **否**。8/42 个正式实验跨年份符号不一致；名义 p 最小的 6 个实验**全部**未通过跨年稳定性条件。 |
| Q9 | 换 birth model 结论是否改变？ | **不改变**（18 个配对检验，FDR 通过 0 个）。但 `universe_subset` 维度在 31/42 个实验中符号不一致 —— 结论对**退市股是否纳入**敏感。 |
| Q10 | 是否有任何 `SUPPORTED_OUT_OF_SAMPLE`？ | **0 个**。 |

### 26.2 最终状态

**`SUPPORTED_OUT_OF_SAMPLE = 0`** · **`MULTI_ENGINE_NO_SIGNAL`**

这不是失败。Phase 3 交付的是：

1. 一台可复现的研究机器（预注册 → 冻结校准 → 固定 holdout → 逐 fold 重拟合 → 日期分层置换 → 族内 FDR → gate-v2）；
2. 一组**可信的否定结论**：在 500 只无偏股票的 2010–2026 样本上，这些术数因子没有可复现的样本外信息量；
3. 一组**方法学发现**：BAZI_POS 的分布偏置如何让负对照失效、黄历的日期选择器结构如何制造两个相反的零假设、多重检验如何把名义显著清零。

### 26.3 gate-v1 / gate-v2 并排

| 状态 | gate-v1（3D） | gate-v2（3F，正式 gate 实验）|
|---|---:|---:|
| `INCONCLUSIVE` | 32 | 20 |
| `INSUFFICIENT_SAMPLE` | 3 | 3 |
| `INVALID_CONTROL` | 2 | 2 |
| `NO_SIGNAL` | 1 | 0 |
| `WEAK_EVIDENCE` | 4 | 17 |

gate-v2 的 `WEAK_EVIDENCE` 显著增加，正是新增条件（FDR / bootstrap / 置换 / 中性化）生效的结果。两版**并排报告**让这一差异可见，而不是被掩盖。

### 26.4 限制

完整清单见 [`phase3-model-limitations.md`](phase3-model-limitations.md)。最关键的五条：

1. **行业 PIT 分类完全不可得** —— 无法排除产业周期解释；
2. **出生时间是研究构造** —— `company_foundation` 不可得，上市日 ≠ 公司出生；
3. **结论对退市股是否纳入高度敏感**（`universe_subset` 31/42 符号不一致）；
4. **未计交易成本 / 流动性 / 涨跌停 / 卖空约束** —— 信息量检验，不是可交易性检验；
5. **多重检验仍不完美**：族划分是最少数量的合理划分，不同划分会给出不同的校正强度（但不会把 0 个变成多个）。

---

**最终定性：`PASS WITH CONDITIONS — RESEARCH PIPELINE READY / EVIDENCE INCONCLUSIVE`**

管线成熟可用；证据本身为负。`PASS` 仅代表研究管线成熟，**绝不等于术数有效**。
