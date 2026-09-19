# Phase 3 实施计划 · 研究验证与模型校准

> **基线**：Phase 2 accepted（commit `24d9f92`）
> **分支**：`feature/phase3-research-validation`
> **开始**：2026-09-19
> **原则**：严格遵循 GOAL MODE — PHASE 3 指令；允许最终 `NO_SIGNAL`；不为了好看而改结果。
> **本文档**：随阶段推进持续更新，每个子阶段完成后回填"完成状态 / 关键产物 / 遇到的限制"。

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
- `docs/factor-calibration-methodology.md`
- `docs/bazi-opinion-bias-analysis.md`
- `tests/research/test_calibration.py`

---

## 4. Phase 3D：Out-of-Sample Pipeline

### 范围
- Train 2010–2018 / Validation 2019–2022 / OOS 2023–2026（如果数据起始较晚则自动调整）
- `WalkForwardResearch`：Train 2010–2014→Test 2015, Train 2010–2015→Test 2016 …
- OOS 状态机：gate 条件 ≥ {足够事件数 / negative control 有效 / 方向一致 / OOS 优于 control / 显著 / effect size 非零 / 跨年稳定 / FDR 通过或可解释}
- `oos_used` / `RESEARCH_REUSE_WARNING`

### 产出物
- `src/research/oos/`
- `docs/oos-methodology.md`
- `docs/walk-forward-methodology.md`
- `tests/research/test_oos_no_leak.py`

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
- `tests/research/test_neutralization.py`

---

## 6. Phase 3F：多重检验 + 稳健性

### 范围
- BH-FDR（Benjamini-Hochberg）；保留 raw p / Bonferroni / q-value
- Bootstrap CI（mean return / excess return / RankIC）
- Permutation test（对高价值结果）
- 稳健性维度：年 / 板块 / 股票池 / birth model / horizon / variant / 复权快照
- effect_size：mean diff / Cohen's d / RankIC magnitude

### 产出物
- `src/research/stats/` 扩展
- `docs/multiple-testing-methodology.md`
- `tests/research/test_multiple_testing.py`

---

## 7. Phase 3G：紫微第二实现源 Cross-check

### 范围
- 调研：Tianji / py-ziwei / 其他 iztro 替代
- License / 维护活跃 / 排盘口径 分析
- 只做 Reference，不进 Consensus
- 对 Golden Cases 比对十二宫 / 命宫 / 身宫 / 主星 / 四化 / 流年 / 流月
- 差异登记：字段 / iztro / reference / 可能原因 / 学派差异 / resolved?

### 产出物
- `src/engines/ziwei/reference/`
- `docs/ziwei-cross-engine-differences.md`
- `tests/golden/test_ziwei_cross_engine.py`

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
| 3C | PENDING | 依赖 3A + 3B |
| 3D | PENDING | 依赖 3A + 3B + 3C |
| 3E | PENDING | 依赖 3A 行业表 |
| 3F | PENDING | 依赖 3D |
| 3G | PENDING | 可并行（只读调研） |
| 3H | PENDING | 终章 |

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

