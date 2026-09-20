# Phase 3 实施计划 · 研究验证与模型校准

> **基线**：Phase 2 accepted（commit `24d9f92`）
> **分支**：`feature/phase3-research-validation`
> **开始**：2026-09-19
> **原则**：严格遵循 GOAL MODE — PHASE 3 指令；允许最终 `NO_SIGNAL`；不为了好看而改结果。
> **本文档**：随阶段推进持续更新，每个子阶段完成后回填"完成状态 / 关键产物 / 遇到的限制"。

---

## ⚠ 2026-09-20 · PHASE 3 FINAL SPRINT IN PROGRESS

**状态**：`3E → 3F → 3G → 3H` 连续执行中（GOAL MODE FINAL SPRINT）。

**冻结纪律（FINAL SPRINT 期间不得违反）**：

* 不重新调 `cal-v1`；不修改 Phase 3D 的 P25/P75 阈值；
* 不根据 OOS 表现重新选因子 / 出生模型 / 持有期；
* 不自由搜索新组合；不删除失败假设；
* 不为提高显著性改统计协议（`gate-v2` 只能是 Phase 3D 已预登记的改进项，
  且必须与 `gate-v1` **同时**报告）；
* 不扩展六爻 / 奇门；不修改传统术数原始 score 语义。

**启动核查（2026-09-20 实测）**：

| 项目 | 实测结果 |
|---|---|
| HEAD | `b04a2b9`（docs: record Phase 3D result artifacts against commit 66939bb） |
| 工作树 | 干净（仅 `.zcodeignore` 未跟踪） |
| 3D 产物 | `phase3d_*.csv/json` 22 个文件齐全；`phase3d_cache/` 主/月度/平移分片齐全 |
| OOS 状态 | 54 条实验全部 `oos_used=true`；`phase3d_calibration_freeze.json` 冻结记录存在 |
| 结论 | 0 候选 / 0 `SUPPORTED_OUT_OF_SAMPLE` —— 与 `docs/phase3d-oos-results.md` 一致 |

---

## 0. 启动基线核查（2026-09-19 实测）

| 项目 | 状态 |
|---|---|
| Git | master @ `24d9f92`，工作树干净，已切出 `feature/phase3-research-validation` |
| 数据快照 | `data/import/` 腾讯 hfq 快照 2026-09-18T20:40:34+08:00，20 股 + IDX000300，104,521 行已入库 |
| stock_master | 1 条 synthetic_demo 残留（**待清理**：Phase 3 必须只存真实档案） |
| 网络 | 腾讯 `ifzq.gtimg.cn` ✅；新浪 `hq.sinajs.cn` ✅；AKShare 上游 `push2his.eastmoney.com` ❌（代理拦截）|
| 退市股 | 腾讯 K 线接口对 `000003/000018/600001/600003` 等已退市股返回 `param error` —— **结构性不可得**，必须发布 `SURVIVORSHIP_BIAS_WARNING` |
| 行业分类 | 腾讯快照 payload 不含行业；sina quote payload 不含行业 —— 需要使用**自建的、可审计的 IndustrClassificationMap**，标注 `source=manual_curated_v1` |
| Phase 2 测试 | `make test` 应全绿（Phase 2 验收基线 368 pytest + 40 playwright） |

**说明**：Phase 3 扩容不能依赖 AKShare / TuShare / wind 等付费或被封源。
统一走**腾讯通道**（与 Phase 1.1 相同）。快照标识沿用 `fetched_at`。

---

## 1. Phase 3A：数据扩容 + Point-in-Time Universe

### 范围
- 从 20 股 → **100 股**真实数据（受退市股不可得限制，暂不追求 500）
- 建立 `universe_memberships` 表：物理表达"哪个 as_of 哪些股票可见"
- 建立 `PointInTimeUniverse` 查询接口 + 泄漏测试
- 数据覆盖报告 + 生存者偏差公示

### 关键决策记录
| 决策 | 理由 |
|---|---|
| universe_size = 100 | 腾讯单股抓取 ~25s（全历史 + 校验），100 股约 45 分钟；500 股约 3.5h，受单人研究交付窗口限制。且退市股不可得使"更像真 A 股"的收益边际递减。Phase 3G/3H 以后视情况扩展到 500。 |
| 从同一快照重新抓取 100 股 | 现有 20 股快照与新增 80 股若分两次抓取，复权锚点不一致。违反 §3A-3"不同快照禁止静默混用"。统一在 Phase 3 新快照下重抓。 |
| 选择标准：分层抽样（板块 × 上市年代 × 行业） | 完全随机/完全市值排序都会强化偏差。分层抽样的**随机种子**与**完整抽样框**入档到 `_meta.json`。 |
| 退市股不可得 → `SURVIVORSHIP_BIAS_WARNING` | 腾讯端点结构性失败（已实测）。按 §3A-2 路径处理：显式标记 + 数据覆盖报告公示 + 研究报告 §4 强制章节。 |
| 行业分类源 | 腾讯/新浪实时 quote 均不返回申万/中信行业。为避免伪装成权威源，用一份**人工审核的 `docs/data/industry_v1.csv`** 并在文档里明确 `source=manual_curated_v1`、`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`（§3E-2正当理由）。 |

### 任务分解
- [ ] 3A-1 `universe_memberships` Alembic migration（含 PIT 查询索引）
- [ ] 3A-2 `src/research/universe/` 模块：`PointInTimeUniverse.at(date) -> list[str]`
- [ ] 3A-3 `scripts/phase3_expand_universe.py`：分层抽样 + 抓取 + 落库 + 校验
- [ ] 3A-4 同步重建 `stock_master`（清掉 synthetic 残留，全部改为 `tencent_hfq_import`）
- [ ] 3A-5 写入 `universe_memberships`（当前宇宙：list_date → null/None，标记 active）
- [ ] 3A-6 `docs/data-coverage-phase3.md`（行业覆盖 / 板块覆盖 / 年份覆盖 / 退市缺失声明 / 质量告警）
- [ ] 3A-7 `tests/research/test_point_in_time_universe.py`（含泄漏硬断言）
- [ ] 3A-8 更新 `IMPLEMENTATION_PLAN_PHASE3.md` 状态 → 3A DONE → commit

### 产出物
- `data/import_phase3/`（新快照，不动旧 20 股目录；最终研究报告选择启用哪一份）
- `src/db/models.py` + Alembic 迁移
- `src/research/universe/`
- `docs/data-coverage-phase3.md`
- `tests/research/test_point_in_time_universe.py`

---

## 2. Phase 3B：出生模型对比研究

### 范围
- 已有：`listing_open`（实现于 Phase 1）
- 新增：`ipo_date` / `company_foundation` / `first_trade`（依据 §3B-0，至少这 4 种）
- 每种 birth model 独立建 `BaziChart` / `ZiweiChart` / Factor / Opinion
- 用 `factor discrimination / negative-control quality / IC / RankIC / OOS stability` 比较
- 重测 `Z_LIFE_006` 等 CONSTANT_FACTOR 在换 birth model 后是否恢复区分度

### 关键决策
- **birth_model 必须版本化**：`listing_open_v1` / `ipo_date_v1` / `company_foundation_v1` / `first_trade_v1`
- 不破 Phase 2 契约：`stock_birth_profile` 表已含 `(stock_code, birth_basis, birth_profile_version)` 联合唯一 —— 新增 version 安全
- **company_foundation** 数据源：A 股招股书披露公司成立日。手工收集 100 股成本太高。**策略**：用腾讯公司资料接口（如果能拿到）或使用 `DATA_INCOMPLETE` + `MANUAL_SUBSET` 标注 —— 不伪造。
- **first_trade**：即"第一个交易日的开盘时刻"—— 与 listing_open 的差别在于：listing_open 是既定交易时段开盘时刻（09:30），first_trade 可能是新股首日实际集合竞价结束时刻 / 或重新上市日。**Phase 3 暂定 first_trade = 首日 09:30**（已在 Phase 1 使用），差别化理由需要在研究中说明。如果无法与 listing_open 产生有意义的差异 → 合并。

### 产出物
- `src/research/birth_models/`
- `docs/birth-model-study.md`
- `tests/research/test_birth_models.py`

---

## 3. Phase 3C：Factor / Opinion Calibration

### 范围
- 每个引擎 raw score 的分布分析（按 year / industry / market phase / birth model 切片）
- 新增 `research_percentile` / `cross_sectional_percentile` / `historical_percentile` / `z_score` / `rank_score` —— **不改 `opinion.score`**
- 方向校准阈值**只用 TRAIN** 数据
- **BAZI_POS 97% 问题专项分析** → `docs/bazi-opinion-bias-analysis.md`

### 产出物
- `src/research/calibration/`
- `scripts/phase3_calibration_audit.py`
- `data/phase3_universe/phase3c_factor_distribution.csv`
- `data/phase3_universe/phase3c_opinion_distribution.csv`
- `data/phase3_universe/phase3c_calibration_metadata.json`
- `docs/factor-calibration-methodology.md`
- `docs/bazi-opinion-bias-analysis.md`
- `tests/research/test_calibration.py`

---

## 4. Phase 3D：Out-of-Sample Pipeline

### 范围（GOAL MODE §3D）
- Train 2010–2018 / Validation 2019–2022 / OOS 2023–2026-08-14
- `WalkForwardResearch`：扩窗 fold（Train 2010–2014→Test 2015 … Train through 2025→Test 2026）
- OOS 状态机：GOAL §15 的十项条件
- `oos_used` / `RESEARCH_REUSE_WARNING`

### 实施记录（设计决策与理由）

| 决策 | 选择 | 理由 |
|---|---|---|
| 采样步长 | **季度（主面板）** + 月度 OOS 子面板 | 季度网格下 20D/60D 持有窗口**天然不重叠**（相邻点相距约 63 个交易日），从设计上消除重叠伪样本；月度子面板专门用于量化"采样更密会怎样"（GOAL §13） |
| 出生平移对照范围 | 仅 OOS 区间、±7 天 | 对照只在 gate 里用于 OOS 比较；采集成本与收益权衡后不在 TRAIN/Validation 重复采集，并在方法学中声明该限制 |
| 平移对照的阈值 | 使用**真实 TRAIN 冻结阈值** | 平移面板未采集 TRAIN 区间；同一阈值语义下的反事实，已在 `oos-methodology.md` §7 披露 |
| 冲突组合 | 预注册为 `exploratory`，**不套用单向 gate** | 冲突形态没有方向性预测；套用单向 gate 会诱导事后选方向。执行全部负对照 + 双侧 p 值，状态记 `EXPLORATORY_NOT_GATED` |
| 事件登记 | 复用既有 `backtest_experiment` / `backtest_result`（`kind="oos"`） | GOAL §20「优先复用」；版本元数据放 `params_json`，**不新增表、不改 schema、不写 ADR** |
| 标签 | 新增 `src/research/labels/horizon_returns.py` | AGENTS.md §6 要求标签计算只能放在 `src/research/labels/`；并统一 5/10/20/60D 的 ret 与 excess（原库只有 20D excess） |
| 复权 | `raw × adj_factor`（TuShare 因子，两快照并集） | canonical 是 `composite_none`（不复权）；直接算收益会把除权当下跌。500 只中 308 只（退市股）只存在于第二个快照 |

### 关键纪律（本阶段 P0）

1. **cal-v1 在读取 OOS 标签前冻结**：fit 只允许 2010–2018；任何改动须新建 `cal-v2`。
2. **Walk-forward 不得复用全 TRAIN 校准**：四道结构性闸门（内部按日期过滤 / layer 的
   `fit_max_as_of` 断言 / transform 帧守卫 / 禁止 fold 使用 `cal-v1` 版本号），
   并以 `calibration_fit_hash` 逐 fold 留痕。
3. **假设预注册**：`config/phase3d_hypothesis_registry.yaml` 在读取 OOS 收益前写死
   （`oos_labels_seen_at_registration: false`），18 个假设 × 3 个出生模型 = 54 个实验。
4. **OOS 只用一次**：读取后 `oos_used=true` 写入实验登记；二次使用须新建版本并附
   `RESEARCH_REUSE_WARNING`。

### 产出物

- `src/research/oos/`（splits / calibration_freeze / gates / walk_forward / diagnostics / registry / runner）
- `src/research/labels/horizon_returns.py`（多持有期标签统一入口）
- `scripts/phase3d_collect_panel.py`、`scripts/phase3d_oos_pipeline.py`、`scripts/phase3d_write_report.py`、`scripts/phase3d_smoke.py`
- `config/phase3d_hypothesis_registry.yaml`
- `docs/oos-methodology.md`、`docs/walk-forward-methodology.md`、`docs/phase3d-oos-results.md`
- `data/phase3_universe/phase3d_*.csv` / `phase3d_*.json`
- 测试：`tests/research/test_oos_no_leak.py`（GOAL §23 全清单）、`test_oos_gates.py`、
  `test_walk_forward.py`、`test_oos_runner.py`、`test_oos_diagnostics.py`、
  `test_horizon_returns.py`、`test_oos_registry.py`

### 顺带修复（Phase 3C 遗留的正确性问题）

* `ResearchCalibrationLayer.transform` 用 DataFrame **索引标签**去索引 numpy **位置**数组：
  输入来自 `.loc[mask]` 切片时会越界或**静默写错行**。已在 `transform` 入口
  `reset_index(drop=True)` 修复，并在 `tests/research/test_calibration.py`
  增加回归测试 `test_transform_is_position_safe_for_sliced_frames`。
  Phase 3D 的 walk-forward 恰好会传入切片帧，因此该 bug 必须先修。

---

## 5. Phase 3E：市场 / 行业 / 风格中性化

### 范围
- Market neutral：个股收益 - benchmark 收益（已有基础，封装成 standard helper）
- Industry neutral：`industry_return` / `industry_excess_return`
  - **POINT_IN_TIME_INDUSTRY_UNAVAILABLE** 显式声明（Phase 3 只有当前行业，无历史分类变更）
- Style controls：`size / momentum / volatility / value`（最基础四因子）
- `cross-sectional rank IC` / `Spearman RankIC` / `group return` / `long-short research spread`

### 产出物
- `src/research/neutralization/`
- `docs/neutralization-methodology.md`
- `docs/huangli-date-effect-analysis.md`
- `tests/research/test_neutralization.py`、`test_style_exposures.py`、`test_huangli_date_effect.py`、`test_research_dataset.py`

### §3E 完成回填（2026-09-20）

**真实运行规模**：500 只 × 3 出生模型 × 18 预注册对象 × 4 持有期 × 3 分区 = **648 行结果**；
数据集 58,578 行；风格暴露覆盖率 98.4%–99.7%（不足即 NaN，不填 0）；耗时 101s。

| 项目 | 结果 |
|---|---|
| 市场中性 | 统一基准 `IDX000300`；**`BENCHMARK_SPLIT_UNAVAILABLE`**（快照内无中证 500，不做市值分层映射） |
| 行业中性 | **双重不可用**：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE` + `INDUSTRY_CLASSIFICATION_UNAVAILABLE`（canonical 快照 / 本地 TuShare / PIT 注册簿均无行业字段） |
| 替代控制 | `SEGMENT_CONTROL_BOARD`（法定板块，5 类）：明确声明**不是行业** |
| 风格可用 | momentum 60/120D、volatility 20/60D、**size 用流动性代理**（20 日均成交额对数） |
| 风格不可用 | `MARKET_CAP_UNAVAILABLE`（无股本表）、`VALUE_FACTOR_UNAVAILABLE`（无 PIT 基本面） |
| 风格解释力 | `style_r2_mean = 0.1992`（OOS 20D 横截面方差） |
| **黄历日期效应（P0 修正）** | 折叠到日期：15 个日期 × 219.5 只/日；二值切分**退化**（15/15 日期都有命中）；`hit_share` 斜率 TRAIN **+0.044** vs OOS **−0.066**（符号相反、均不显著）→ **不是市场-wide calendar effect** |
| Q-E5 风格解释 | **符号双向翻转**：紫微+黄历 cal +3.03%→−1.96%、三模型 cal +0.90%→−4.99%、八字 raw −1.91%→−0.04%；只有 2 个对象控制后 |t| ≥ 2（黄历 cal 1.97、八字+黄历 cal 2.15），在 42–54 个实验下属噪声水平 |

**顺带完成的基础设施收敛**（避免 3E/3F 出现"两次构建、两个口径"）：
- 标签面板构建上移到 `src/research/labels/panel.py`（3D 脚本改为薄封装）；
  已用**逐位等价校验**确认搬运前后输出完全相同（6 只真实股票 × 13 个 as_of = 50 行标签 SHA 一致）。
- 校准拟合上移到 `src/research/oos/calibration_freeze.fit_holdout_calibration`；
  已确认 `cal-v1` 的 `fit_hash` / `fit_max_as_of` / 分组数与 3D 内联实现完全一致。

---

## 6. Phase 3F：多重检验 + 稳健性

### 范围
- BH-FDR（Benjamini-Hochberg）；保留 raw p / Bonferroni / q-value
- Bootstrap CI（mean return / excess return / RankIC）
- Permutation test（对高价值结果）
- 稳健性维度：年 / 板块 / 股票池 / birth model / horizon / variant / 复权快照
- effect_size：mean diff / Cohen's d / RankIC magnitude

### 产出物
- `src/research/multipletesting/`
- `config/phase3f_multiple_testing_families.yaml`（族定义，结果前冻结）
- `docs/multiple-testing-methodology.md`
- `tests/research/test_multiple_testing.py`

### §3F 完成回填（2026-09-20）

**真实运行规模**：54 个实验 + 18 个出生模型对比 = **72 行**；日期分层置换 **5000 次/实验**；
date-block bootstrap 2000 次；稳健性维度 9 个 × 54 = 324 行切片；耗时 121s。

| 项目 | 结果 |
|---|---|
| 假设族 | 6 个（bazi 6 / ziwei 6 / huangli 6 / consensus 24 / conflict 12 / birth_model_comparison 18），`mt-v1` 冻结，代码强制校验"恰好归属一个族" |
| **BH-FDR 通过** | **正式 gate 实验 0 个**；仅 `conflict`（探索性）族通过 1 个，按预注册**不解锁** |
| **Bonferroni 通过** | 同上：正式 0 个 |
| Bootstrap | 42 个正式实验的命中均值 95% CI **全部跨 0** |
| 置换 | 日期分层（保留每日命中数量）；构造实验证明池化置换会把"纯日期选择器"误判为显著 |
| **`SUPPORTED_OUT_OF_SAMPLE`** | **0 个** |
| gate-v1 vs gate-v2 | 32 INCONCLUSIVE/4 WEAK/3 INSUFFICIENT/2 INVALID/1 NO_SIGNAL → 20/17/3/2/0，**两版并排输出** |
| 稳健性最弱维度 | `universe_subset` 在 **31/42** 个实验中符号不一致（在市股 vs 退市股结论相反） |
| 名义 p 最小的 6 个 | 全部同时未通过 C（方向一致）/ F（FDR）/ G（CI 跨零）/ I（跨年稳定） |

**协议合法性**（GOAL §4.7 五条）：只实现 3D 已预登记的改进项；不改 3D 结果（只读）；
标记 `protocol_version=phase3f-oos-gate-v2`；两版并排；不选择性保留。

---

## 7. Phase 3G：紫微第二实现源 Cross-check

### 范围
- 调研：Tianji / py-ziwei / 其他 iztro 替代
- License / 维护活跃 / 排盘口径 分析
- 只做 Reference，不进 Consensus
- 对 Golden Cases 比对十二宫 / 命宫 / 身宫 / 主星 / 四化 / 流年 / 流月
- 差异登记：字段 / iztro / reference / 可能原因 / 学派差异 / resolved?

### 产出物
- `src/engines/ziwei/reference/`、`services/ziwei-reference-service/`
- `config/ziwei_cross_engine_cases.json`
- `docs/ziwei-cross-engine-differences.md`
- `tests/golden/test_ziwei_cross_engine.py`

### §3G 完成回填（2026-09-20）

**采用**：`airicyu/fortel-ziweidoushu` v1.3.4（**中州派**，MIT，唯一运行时依赖 `util`，
自带 jjonline 日历，**不依赖 iztro**）→ **`REFERENCE_AVAILABLE`**（不是 UNAVAILABLE）。

**关键审计结论**：星标最高的"紫微排盘引擎"`Renhuai123/ziwei-doushu`（4169★）的
`lib/ziwei/algorithm.ts` 首行即 `import { astro } from 'iztro'` —— **不是独立实现**；
Python 侧候选（`py-iztro` / `iztro-py` / `mingli-master`）同为 iztro 移植；
`Wolke/ziwei-doushu` / `cubshuang` 许可证不明确；`ziweiknows/ziwei-chart` 为 GPL-3.0 应用；
GOAL 提到的 "Tianji"（`nihaisha-tianji`）是语料库/MCP，不含排盘算法。共 11 个候选逐个记录理由。

| 项目 | 结果 |
|---|---|
| 案例数 | **24**（1940s–2026、12 个月份、21 个不同小时、早/晚子时、4 个闰月、forward 16 + reverse 8） |
| 字段比较 | **2280 项**，其中 **2183 项完全一致（95.75%）** |
| 完全一致的关键字段 | 十二宫位置、十二宫天干、五行局、命宫、身宫、**辅星、三方四正、大限、长生十二神**（性别相关字段在匹配性别下 24/24 一致） |
| 差异 1 | `晚子时换日` —— iztro 归次日 / 中州派归当日（32 条中的 24 条）；实测证明 iztro 晚子时盘 == 次日早子时盘，且 iztro 的 `lunar_date` 显示与安放口径不一致 |
| 差异 2 | `十干四化「科」星` —— 戊（右弼/太阳）、庚（太阴/天府）、壬（左辅/天府）三干流派分歧（8 条） |
| 差异 3 | `命主取用` —— 参考实现以**生年支**索引命主表（标准应为**命宫支**），源码级证据，判定为**参考实现疑似问题**（17 条） |
| 不可比对字段 | 流年 / 流月（参考实现只暴露十年运接口）（48 条） |
| 对研究结论的影响 | 无：500 只股票出生时刻为日间时刻（非晚子时）；因子不使用命主字段；四化差异已固定为"实现选择敏感点"并冻结版本 |

---

## 8. Phase 3H：最终研究报告与冻结

### 范围
- 26 章 `docs/PHASE3_RESEARCH_REPORT.md`
- 结论只能落到：`NO_SIGNAL` / `INCONCLUSIVE` / `SUPPORTED_OUT_OF_SAMPLE` / `MULTI_ENGINE_NO_SIGNAL`
- 最佳/最差/失败/空结果全部列出
- 回答 Phase 3 指令 §20 的 Q1–Q10

### 产出物
- `docs/PHASE3_RESEARCH_REPORT.md`
- `docs/HANDOFF_PHASE3.md`
- 必要的 ADR
- 最终 commit + tag

---

## 9. 工作节奏（约定）

- 每个子阶段结束：跑测试 → 记录 → 提交 → 更新本文件的 `Status` 行
- 遇到**真正无法解决的环境限制**时：
  1. 在数据覆盖报告中如实登记
  2. 给出 `*_WARNING` / `*_UNAVAILABLE` 显式状态
  3. 不阻塞主线，但仍需跑已完成部分的测试

---

## 10. 当前状态看板

| 子阶段 | 状态 | 备注 / 卡点 |
|---|---|---|
| 3A | **DONE** (commit `17c3fbc`) | `universe_memberships v2-phase3a` 500 只 (333 退市 + 167 在市)；ADR-0012 切换主数据源 |
| 3B | **DONE** (commit `c9fee4a`) | 4 birth model 注册（company_foundation 显式 UNAVAILABLE，无伪造）；500股×3模型 factor 对比 → `docs/birth-model-study.md` |
| 3C | **DONE** (Phase 3C commit) | 500 股 × 3 birth model × 18 采样点；Factor 5814 行摘要、Opinion 153 行摘要；BAZI 原始正向率 94.0%–96.6%，TRAIN-only Calibration 正向率 25.5%–26.7%；无失败；行业切片显式 `POINT_IN_TIME_INDUSTRY_UNAVAILABLE` |
| 3D | **DONE** (Phase 3D commit) | 固定 holdout + 扩窗 walk-forward；18 假设 × 3 出生模型 = 54 实验；**0 个 OOS 候选、0 个 SUPPORTED_OUT_OF_SAMPLE**；见下方 §3D 完成回填 |
| 3E | **DONE** | 648 行中性化结果；风格中性化后符号双向翻转；黄历日期效应 = 非市场日历效应 |
| 3F | **DONE** | 族内 BH-FDR：正式实验通过 **0**；`SUPPORTED_OUT_OF_SAMPLE = **0**`；gate-v2 与 gate-v1 并排 |
| 3G | **DONE** | 第二实现源 `fortel-ziweidoushu`（中州派）可用；2280 项比较 95.75% 一致；3 类差异全部定位 |
| 3H | IN PROGRESS | 终章：最终报告 / 模型限制 / HANDOFF / 全量回归 / tag |

---

## §3D 完成回填（2026-09-20）

### 真实运行规模（全部来自产物，可核对）

| 项目 | 值 |
|---|---|
| 主面板 | 500 只（333 退市 + 167 在市）× 3 出生模型 × 3 引擎 × **68 个 as_of**（2010-01-01..2026-08-14，季度）= **175,734** 行观测，排盘失败 **0** |
| 月度 OOS 子面板 | 45 个 as_of = 90,792 行（仅用于重叠敏感性） |
| 出生平移对照面板 | ±7 天 × 16 个 as_of（仅 OOS） |
| 标签 | 31,305 行；除权因子覆盖 **500/500** 只、未覆盖行 **0**；降级行情 **0** |
| 固定 holdout 实验 | **54**（18 个预注册假设 × 3 出生模型），全部 `oos_used=true` |
| Walk-forward | 12 条序列 × **12 个 fold** = 144 行；逐 fold `calibration_fit_hash` 互不相同 |
| 负对照 | 每实验 5 类（随机事件位置 / 随机出生指派 / 随机模型方向 / 出生平移 ±7 天） |
| 实验结果登记 | 54 条写入 `phase3d_experiment_registry.csv` + 既有 `backtest_experiment`（`kind="oos"`，无 schema 变更） |

### 关键结果（如实记录，不美化）

* **OOS 候选：0 个**；`SUPPORTED_OUT_OF_SAMPLE`：**0 个**（结构上不可能，FDR 属 3F）。
  状态分布：`INCONCLUSIVE` 32 / `EXPLORATORY_NOT_GATED` 12 / `WEAK_EVIDENCE` 4 /
  `INSUFFICIENT_SAMPLE` 3 / `INVALID_CONTROL` 2 / `NO_SIGNAL` 1。
* **GOAL §19 三问**：Q1 **是**（原始 BAZI_POS 在 OOS 仍 93.1%–95.4% 近乎恒正）；
  Q2 **是**（Jaccard 从 0.82–0.86 降到 0.11–0.14）；
  Q3 **否**（校准后事件 OOS 平均超额仍为 −1.2%…−1.7%，单侧置换 p = 0.05–0.15，
  无一达到预注册显著性门槛，且绝对收益为负）→
  **Calibration improved discrimination, but did not create predictive information.**
* **唯一显著为负的发现**：`huangli_calibrated` 事件集合在 OOS 显著弱于同数量随机集合
  （下尾 p ≈ 0.005–0.03）。已按描述性结果输出，不表述为可交易信号。
* **结构性发现**：黄历（`H_*`）方向是「日历开关」—— 每个 as_of 的命中率在
  0.00–0.78 之间摆动（std 0.27），而八字 std 0.09、紫微 std 0.04。
  这解释了为什么两类负对照给出相反结论：位置对照混合了日期构成，
  逐日数量守恒对照（出生指派 / 随机方向）保留日期构成。
  **协议未因此改动**（改协议＝看到结果后调参），但已列为 3F 的改进项。
* **FDR 前瞻**：42 个正式 gate 实验中最小 p = 0.00498，BH 最小门槛 0.00119
  → **0 个通过**。这是把正式解锁留给 3F 的实证理由。
* **稳健性**：无任何实验出现单一股票依赖（top1 ≤ 19%、LOO 无符号翻转）；
  主面板 20D/60D 天然非重叠（`overlap_ratio = 0`），月度子面板的重叠修正不改变结论。

### 顺带修复的问题（Phase 3C 遗留正确性）

* `ResearchCalibrationLayer.transform` 的**位置/标签索引错位**（切片输入会越界或静默写错行）
  → 已在 `transform` 入口归一索引，并加回归测试。

### 验证记录

* 全量 pytest：见提交信息；Phase 3D 新增测试 69 项（7 个文件）。
* 3D 定向 lint（`src/research/oos/`、`labels/horizon_returns.py`、4 个脚本、7 个测试文件）：**通过**。
* 两次分析运行（缓存复用）状态分布完全一致 → 管线**确定性**。

*创建于 2026-09-19；3A 完成于 2026-09-19；3B 完成于 2026-09-19；3C 完成于 2026-09-20；3D 完成于 2026-09-20*

---

## §3B 完成回填（2026-09-19）

### 成果

* `src/research/birth_models.py`：4 个 Birth Model（合同 ``listing_open / listing_close / ipo_approx / company_foundation``）
* `scripts/phase3_generate_birth_profiles.py`：500 股 × 3 模型 → 1500 行 ``stock_birth_profile``
* `scripts/phase3_birth_model_study.py`：500 股 × 3 模型 factor 抽取 + 区分度统计（耗时 ~7min）
* `docs/birth-model-study.md`：研究报告
* `data/phase3_universe/birth_model_factor_stats.csv`：291 行（97 因子 × 3 模型）

### 关键判断（不在报告里下结论，仅记录事实）

* Z_LIFE_006（身宫命同宫）**恒为 0**（500 × 3 = 1500 次全 0）→ iztro 结构性常量，非 birth model 能救
* 中位数 unique_ratio ≈ 0.006（含义：每 500 股票只有 ~3 个唯一值）→ A 股术数因子整体**天然低区分度**
* 三模型的 "Is factor discrimination sensitive?" → 答：no，宏观分布相似

*创建于 2026-09-19；3A 完成于 2026-09-19；3B 完成于 2026-09-19*

---

## §3C 完成回填（2026-09-20）

### 真实审计范围与产物

* 主宇宙：`v2-phase3a`，500 只股票（333 退市 + 167 在市）；Phase 3A canonical 快照截止 `2026-08-14`。
* Birth model：`listing_open_v1` / `listing_close_v1` / `ipo_approx_v1`，共 1500 个可用出生档案；`company_foundation` 仍显式 UNAVAILABLE，不造数据。
* 日历采样：18 个点（2010-01-01、每年 1 月及 2026-08-14），覆盖 TRAIN `2010–2018`、Validation `2019–2022`、OOS 描述区间 `2023–2026-08-14`。
* 原始 Opinion 观测：68,520 行；Factor 摘要：5814 行；Opinion 摘要：153 行；单点计算失败：0；紫微批量排盘失败：0。
* 产物：`scripts/phase3_calibration_audit.py`、`src/research/calibration/`、`data/phase3_universe/phase3c_factor_distribution.csv`、`data/phase3_universe/phase3c_opinion_distribution.csv`、`data/phase3_universe/phase3c_calibration_metadata.json`、`docs/bazi-opinion-bias-analysis.md`、`docs/factor-calibration-methodology.md`、`tests/research/test_calibration.py`。

### 真实研究结果（仅分布诊断，不是有效性结论）

| Birth model | 原始 BAZI_POS 正向率 | 原始 +1 / 0 / -1 | TRAIN-only Calibration +1 正向率 | 解释 |
|---|---:|---:|---:|---|
| `listing_open_v1` | **96.4%** | 7336 / 276 / 0 | **25.9%** | 原始固定 58/42 阈值高度偏正；校准只重表达分布 |
| `listing_close_v1` | **94.0%** | 7156 / 456 / 0 | **25.5%** | 时柱变化没有消除原始方向偏置 |
| `ipo_approx_v1` | **96.6%** | 7359 / 257 / 0 | **26.7%** | 日柱近似变化也没有消除原始方向偏置 |

* `opinion.score`、原始 `direction`、Factor `normalized_value` / `rule_score` / `direction` 均未被修改；Calibration 只追加研究派生列。
* 方向阈值只由全体 TRAIN 原始分布的 P25/P75 冻结得到；Validation/OOS 只做 transform，没有参与任何 threshold、均值、标准差或分位点拟合。
* 行业切片状态为 `POINT_IN_TIME_INDUSTRY_UNAVAILABLE`，没有用当前行业资料伪装历史 PIT 分类。
* 本结果说明 BAZI_POS 是当前参数下的高激活/高正向分布偏置，**不说明上涨概率、收益率或术数有效性**；正式 walk-forward/OOS gate 尚未开始，留在 3D。

### 验证记录

* 等价于 `make test` 的 `.venv/Scripts/python.exe -m pytest -q`：**1043 passed**（1 个既有 FastAPI deprecation warning）。
* 等价于 `make test-leak`：**28 passed**。
* 等价于 `make test-golden`：**262 passed**。
* 3C 定向 lint（Calibration、批量紫微、审计脚本及相关测试）：**通过**。
* `scripts/run_acceptance.py --skip-ui`：compile、unit/integration、leakage、Golden、event-set distinctness、negative controls、third-party isolation、factor-quality audit 全部 PASS；总状态因仓库既有全量 ruff 历史问题为 FAIL。该 lint 失败不由 3C 新增文件引入，未在本阶段扩大范围修复。
* 当前环境没有 `make` 命令，因此上述 Makefile 目标均用等价 Python 命令执行；UI 未纳入本阶段，且 3C 未修改前端。

---

## §3A 完成回填（2026-09-19）

### 重要偏差 re-plan

用户告知本机存在 `E:\AStockData`（81G，TuShare composite，**含 337 只退市股**）。
原计划基于腾讯通道的"强制 SURVIVORSHIP_BIAS_WARNING"策略被推翻——
改为直接采用无偏 universe（`ADR-0012`）。

### 决策树（最终态）

```text
Phase 3A 主数据源
  = AStockData.CompositeNone(2026-08-14)   [5,541 只 raw]
+ TuShare adj_factor.snapshot_20260731     [5,554 只 因子历史]
+ TuShare.PIT_universe_20260717            [5,868 只 PIT 注册簿]

交叉验证辅通道（不撤销）
  = Tencent.ifzq.hfq(2026-09-18)           [100 股 + IDX000300]

被否决
  = Tencent 单通道                          [结构性无退市股 → survivorship bias]
```

### 3A 产出物清单

| 类型 | 路径 |
|---|---|
| ADR | `docs/ADR/ADR-0012-phase3a-astockdata-canonical.md` |
| Universe 抽样脚本 | `scripts/phase3_import_astockdata.py` |
| 数据库迁移 | `migrations/versions/c3e8a91f0b22_phase3a_universe_memberships.py` |
| PIT 查询模块 | `src/research/universe/point_in_time.py` |
| Blob 读取层 | `src/market/providers/astockdata_store.py` |
| Coverage 报告 | `docs/data-coverage-phase3.md` |
| 抽样清单 | `data/phase3_universe/phase3a_astock_sample_500.json` |
| 测试：PIT | `tests/research/test_point_in_time_universe.py`（15 tests） |
| 测试：discipline | `tests/research/test_universe_query_discipline.py`（5 tests） |
| 腾讯通道（对照） | `scripts/phase3_expand_universe.py`（100 股） |
| **数据库最终态** | `market_bar_daily`: 1,737,363 (astockdata) + 104,521 (tencent_jqka_xval) + 5,214 (IDX000300) |

### 关键数字

* universe v2-phase3a：**500 只 = 333 退市 + 167 在市**
* 时间跨度：1990-12-19 ~ 2026-08-14（35.7 年）
* SQLite 落库 1.7M 行，耗时 592s
* 排序测试 15/15 过；discipline 测试 5/5 过；Phase 1+2 回归 1023/1023 过

### 已知遗留问题（Phase 3B+ 要解决）

* 行业分类无 PIT（Phase 3E 依赖目标）
* benchmark（IDX000300）的 source 与个股不同（腾讯 vs 本地），
  OOS 时需按"都有数据的区间"对齐（`max(first_stock, first_benchmark)`）
* 500 只 universe 的**行业分布**待写（依赖行业分类）
* 腾讯通道 100 股仍可用但与 canonical 不再同一快照
  （``market_data_version`` 逻辑需在 3B 里收紧）

*创建于 2026-09-19；3A 完成于 2026-09-19*

