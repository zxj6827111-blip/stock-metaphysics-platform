# 择日关系扫描 / 关系历史研究：口径变更登记（bazi-relation-v2 → v3）

> 适用模块：`src/core/relations/date_relation.py`、`src/core/orchestration/date_relation_scan.py`、
> `src/research/relation_study.py`、`src/research/relation_runner.py`、
> `/api/v1/research/date-scan`、`/api/v1/research/relation-study`。
>
> 本文件按 AGENTS.md §12 的"口径变化必须登记"要求编写。**本 PR 尚未 merge 进入 main**，
> 因此 API 直接在 `/api/v1` 上收敛为最终契约，不另建 `/api/v2`（date-scan / relation-study
> 本身就是本 PR 新增、尚未发布的接口）。

## 0. 版本矩阵

| 版本号 | 变更前 | 变更后 | 说明 |
|---|---|---|---|
| `relation_rule_version` | `bazi-relation-v2` | **`bazi-relation-v3`** | 关系语义、矩阵范围、聚合范围、十神判定、喜忌判定、分组规则全部变化 |
| `relation_matrix_schema_version` | （无） | **`relation-matrix-v2`** | 矩阵目标列 4 → 3；行级 `relation_types` |
| `relation_fingerprint_version` | `date-relation-fingerprint-v1` | `date-relation-fingerprint-v1`（**不变**） | 指纹是"日期 → 候选模板"，与股票矩阵口径解耦 |
| `calendar_engine_version` | `lunar-python-1.4.8` | 不变 | |
| `bazi_engine_version` | `smx-bazi-native-1.0.0` | 不变 | 喜用神仍来自完整四柱 |
| `birth_profile_version` | `v2-phase4b-listing_open` | 不变 | |

## 1. 3×4 → 3×3：矩阵范围收窄

* 变更前：`3 行（流年/流月/流日）× 4 列（股票年/月/日/时）= 12 格`。
* 变更后：`3 行 × 3 列（股票年/月/日）= 9 格`；股票时柱退出择日关系研究范围。
* 常量：`EXTERNAL_POSITIONS = ("year","month","day")`、`NATAL_POSITIONS = ("year","month","day")`
  （不再使用含糊的 `POSITIONS`，避免与 BaziEngine 自己的四柱 `POSITIONS` 混淆）。
* **没有**修改 `src/engines/bazi/bazi_engine.py` 的四柱定义，也**没有**修改
  `src/engines/bazi/rules.py::relations_with_external`（该函数仍服务个股八字页与 `B_*` / `H_*` 时间流因子）。
* 影响：`流年×股票时柱`、`流月×股票时柱`、`流日×股票时柱` 三格及其关系事件不再产生。

## 2. all-row → external_day_row：聚合范围收窄

* 变更前：S/V/U、`relation_types`、`stem_relations` / `branch_relations` / `compound_relations`、
  `hit_explanations`、`relation_type` 过滤、`sort=s/v/u` 全部基于 12 格全部事件。
* 变更后：以上全部**只读流日行**（`RelationEvent.source_pillar == "day"` 及其三格），
  由共享 helper `events_for_source_pillar(matrix, "day")` 提供；Date Scan 与 Relation Study 共用。
* 响应回显：`aggregate_scope = "external_day_row"`、`matrix_source_scope = ["year","month","day"]`、
  `matrix_target_scope = ["year","month","day"]`。
  `external_day_row` 的 `day` 指**日期侧流日柱**，不是股票日柱列。
* 3×3 范围内的九格事件仍**全部保留**（矩阵不隐藏 cell 内部事件）；
  但不能表述为"所有四柱关系均完整保留"——`时柱` 相关关系已主动退出本功能研究范围。

## 3. 流日十神改为直接计算

* 变更前：`ten_gods = unique(event.ten_god for event in flatten_events(matrix))`，
  即用事件集合决定十神 → 只要某条流年/流月事件长期存在，十神列表就被"锁死"
  （实证：平安银行 000001 在 2026 全年的 365 天里 `正财` 出现 335 天）。
* 变更后：`day_stem_verdict.ten_god = ten_god(股票日主, 流日日干)`——与当天是否发生
  五合/相冲/生/克/同五行无关，**必然存在**且每天由日柱干支决定。
  行级 `ten_gods` 收窄为 `[day_stem_verdict.ten_god]`。

## 4. 新增 `day_stem_verdict`（流日判定）

Schema `RelationDayVerdict`：`day_stem` / `day_stem_wuxing` / `day_master` / `ten_god` /
`ten_god_group` / `wuxing_role` / `is_yong_or_xi` / `verdict` / `reason`。

* `ten_god_group` 复用现有公共映射 `constants.TEN_GOD_GROUP`（比劫/食伤/财星/官杀/印星）。
* `wuxing_role ∈ {用神, 喜神, 忌神, 仇神, 闲神, 未知}`：
  按 用神 → 喜神 → 忌神 → 仇神 → 闲神 的优先级取第一个命中集合；
  **禁止**把"不在喜用"推断成"忌神"。
* `verdict ∈ {匹配, 不匹配, 未知}`：
  匹配 = 流日干五行 ∈ 用神 ∪ 喜神；不匹配 = 已知属于忌/仇/闲且不在喜用；
  未知 = 原局喜忌资料不足或该五行未被归类（**未知 ≠ 不匹配**）。
* `reason` 严格分开两套维度，例如：
  `流日干己属土；相对甲日主的十神为「正财」；该五行（土）在当前原局喜忌判定中属于「仇神」，不属于用神/喜神集合（水/金），判定为「不匹配」。`
  禁止出现「正财属于忌神」这类跨维度断言。
* `yong_shen_relations` 保留但标注 **deprecated / legacy relation list**，且只来源于流日行；
  权威喜忌结论只能是 `day_stem_verdict`。新 UI 不再使用它表达"喜用"。

## 5. 喜用神仍基于完整四柱原局

* `matrix_target_scope = ["year","month","day"]`，但 `yongshen_basis = "full_four_pillars"`。
* 结论：矩阵不再使用股票时柱参与匹配，**不等于**喜用神与出生时辰无关；
  `day_stem_verdict` 的喜忌部分仍可能间接受出生时辰模型影响（同股不同出生模型可能给出不同用神）。
* 未重新生成 `data/phase4_cache/astrology_natal_cache.pkl`；读取时只抽取
  `year/month/day` 三柱给矩阵，`day_master` 与喜用五类字段用于流日判定；
  旧条目缺少 `chou_shen` / `xian_shen` 时按空元组兼容，**不触发整份缓存重算**。

## 6. 关系类型目录补全（引擎 emit 但 catalog 不承认的问题）

* 变更前：引擎会 emit `天干受生` / `天干受克`，但 `RELATION_CATALOG` / `RELATION_TYPES` /
  `relation_type_counts` / 前端筛选中都不存在 → 矩阵里出现的关系在 catalog/filter 不可见，
  且 Relation Study 的 `RELATION_OPTIONS` 与后端相比漏了 `三刑`。
* 变更后：`RELATION_CATALOG` 天干组补齐两项，最终 **22 项**：

  | 组 | 关系类型 |
  |---|---|
  | 天干（7） | 天干五合、天干相冲、天干生、天干受生、天干克、天干受克、天干同五行 |
  | 地支（11） | 六合、六冲、三合、半合、三会、相刑、三刑、自刑、相害、六破、同支 |
  | 组合（4） | 伏吟、反吟、天合地合、天克地冲 |

* 强制不变量（测试 `test_all_emitted_relation_types_are_in_canonical_catalog`）：
  `all_emitted_relation_types ⊆ set(RELATION_TYPES)`。
* `天干受生` / `天干受克` 的 S/V 归属：二者表示"原局去生/克流日"，**不计入 S 也不计入 V**
  （既非协同亦非扰动），只作为结构信息参与目录、计数与展示。
* 新增只读目录接口 `GET /api/v1/research/relation-catalog`：返回 `groups` 与
  `RELATION_DEFINITION_INDEX` 的因子元数据；Date Scan 与 Relation Study 的选项均由后端目录构建，
  **前端不再维护第二份术数关系清单**（漂移根因）。

## 7. 结构型分组取代阈值分组

* 变更前：`高混合 = (u >= 3) or (s > 0 and v > 0)`、`高扰动 = v > s`、`高协同 = s > 0`，
  是旧 12 格聚合语境下的任意阈值（实测：68,926 个 stock-day 中 68,628 个落入"高混合"，
  99.6% 同组，分组几乎无区分度）。
* 变更后（无阈值、纯结构）：

  | 条件 | 分组 |
  |---|---|
  | S > 0 且 V == 0 | 协同型 |
  | V > 0 且 S == 0 | 扰动型 |
  | S > 0 且 V > 0 | 混合型 |
  | S == 0 且 V == 0 | 弱关系 |

  U（伏吟/反吟/天合地合/天克地冲）作为独立结构维度展示，不参与分组。
* 未使用任何收益/上涨率/未来 label 做阈值定标；本改动不引入 calibration。

## 8. S / V / U 取值范围（实测，不写死上界）

* 3 个 cell ≠ 最多 3 个事件：单 cell 可同时产生多个 RelationEvent。
* 实测分布（12 个采样日 × 全市场，n = 68,926 stock-day；见 `docs/relation-v3-evidence/`）：

  | 指标 | 版本 | min | P25 | P50 | P75 | P90 | P95 | max |
  |---|---|---|---|---|---|---|---|---|
  | S | v2（12 格） | 0 | 8 | 10 | 11 | 13 | 15 | 23 |
  | S | **v3（流日行）** | 0 | 2 | 2 | 3 | 4 | 5 | 10 |
  | V | v2 | 0 | 5 | 7 | 10 | 13 | 14 | 31 |
  | V | **v3** | 0 | 1 | 2 | 3 | 4 | 5 | 14 |
  | U | v2 | 0 | 0 | 1 | 2 | 3 | 4 | 9 |
  | U | **v3** | 0 | 0 | 0 | 0 | 1 | 2 | 4 |

* 分组分布（同批次）：v2 = 高混合 68,628 / 高协同 298；v3 = 混合型 54,766 / 协同型 11,055 /
  扰动型 2,867 / 弱关系 238。
* 命中股票数下降（例：2026-09-01 全市场，六合 5,796 → 1,177；相害 5,796 → 1,134；
  天干克 5,119 → 2,839）是"聚合范围收窄 + 日柱逐日变化"的**预期结果**，不是功能退化。

## 9. 行级 `relation_types`

`RelationMatrixRow.relation_types` 为该行全部 cell 事件类型的去重稳定序；
UI 直接展示"流年关系 / 流月关系 / 流日关系"，**前端不得遍历事件重新计算**。

## 10. 标准日级采样时点（`evaluation_time`）

* v3 固定 `evaluation_time = 12:00:00`、`timezone = Asia/Shanghai`，`DateScanRequest` 不再接受 `hour`。
* 理由是产品主动定义"日级研究标准采样时刻"，**不是**"hour 没有作用"：
  节气交界日不同时刻确实会改变月柱/年柱。
  Golden Case：`2024-02-04 立春`（约 16:27）→ 12:00 仍为 `癸卯/乙丑`，17:00 已换 `甲辰/丙寅`。
  固定 12:00 使同一日期在任意运行中可复现。
* 指纹接口 `/api/v1/research/date-relations/{date}` 仍保留可选 `hour`（诊断用途，指纹模板版本不变）。

## 11. Relation Study 同步采用 v3

* 观测构造 `build_relation_observations()` 使用同一个 `build_relation_matrix`（3×3）与
  同一个 `events_for_source_pillar(matrix, "day")`；
  `REL_*` 因子定义改为「指定 as_of 的流日柱与股票年/月/日三柱，在流日行命中 X 的事件次数」。
* `rule_version` 不再硬编码 `bazi-relation-v2`，改为 `settings.relation_rule_version`。
* 观测新增 `REL_TIANGAN_SHOUSHENG`（天干受生）、`REL_TIANGAN_SHOUKE`（天干受克）。
* 响应回显 `aggregate_scope` / `matrix_target_scope` / `yongshen_basis` /
  `evaluation_time` / `timezone` / `relation_rule_version` / `relation_matrix_schema_version`。
* `RELATION_DEFINITION_INDEX` 由 relation-catalog 与 relation-study 响应共同消费
  （不再是无人读取的"假 registry"）。

### 11.1 性能与统计语义修正

| 项目 | 变更前 | 变更后 |
|---|---|---|
| CalendarSnapshot | 每 `stock × sample_date` 各排一次历 | 按 `sample_date` 缓存，每日期一次 |
| `_return_values()` | 每行标签重建 key 集合（O(n·m)） | key 集合循环外构建一次 |
| p-value 对照 | `next(iter(controls.values()))`（首个面板） | 固定 `p_value_control_kind = random_birth_date`，并回显 |
| 展示的 control 均值/上涨率 | 来自 `RANDOM_FACTOR` 报告 | 与 p-value 同一对照面板（同源） |
| BH q-value 范围 | 文案暗示"全关系研究校正" | `multiplicity_scope = within_relation_split_horizon`，文案如实说明未跨 relation_type 联合校正 |
| 全市场默认 | 不传 `stock_codes` 即静默跑全市场十年 | 必须 `allow_full_universe = true`，否则 422；前端需显式勾选确认 |

## 12. 历史实验影响

* 旧 `REL_*` 且 `rule_version = bazi-relation-v2` 的实验结果**保持 legacy 语义，不原地解释成 v3**；
  新实验使用新 `experiment_id` + v3 版本，`params_json` 至少记录：
  `relation_rule_version` / `relation_matrix_schema_version` / `aggregate_scope` /
  `matrix_target_scope` / `yongshen_basis` / `evaluation_time` / `timezone` /
  `multiplicity_scope` / `p_value_control_kind` / `sample_step_months` / `stock_scope` / `stock_codes`。
* 因此未来可以明确回答："这个实验是按 3×4 全行关系还是 3×3 day-only 关系跑的"。
* 需要 v3 结论时必须重新登记实验（本 PR 不重跑任何 Phase 3 历史研究，也不覆盖既有结论）。

## 13. 既有 `B_*` / `H_*` 时间流因子不受影响

* Date Scan / `REL_*` 研究使用 3×3 day-row v3；
* `src/engines/bazi/rules.py::relations_with_external`（四柱全矩阵）仍服务个股八字页与
  `B_*` / `H_*` 时间流因子，**本 PR 不修改其定义，也不改变其数值**；
* 两者口径不同属于有意设计：一个是"择日扫描的研究 scope"，一个是"个股八字页的完整四柱视图"。

## 14. 复现与证据

* 证据脚本：`scripts/relation_scan_evidence.py`（v2 基线须在 `4c334e7` 上运行；v3 在整改后运行）。
* 产物：
  * `docs/relation-v3-evidence/baseline-v2.json` / `final-v3.json`
    （12 个采样日的逐关系命中股票数、日期间 Jaccard、S/V/U 分布、分组分布）
  * `docs/relation-v3-evidence/pingan-000001-2026-v2.csv` / `pingan-000001-2026-v3.csv`
    （平安银行 2026 全年逐日：干支、十神、五行角色、verdict、流日关系、S/V/U）
* 关键验收事实（000001，2026 全年 365 天）：
  * v2：`正财` 出现在 335/365 天的"事件十神集合"中（被流年/流月事件锁死）；
  * v3：流日十神按十天干循环均匀分布（每类 36–37 天），verdict = 匹配 144 / 不匹配 221，
    角色 = 用神 72 / 喜神 72 / 忌神 148 / 仇神 73——结果由**流日**驱动而非由某条固定事件驱动。

## 15. 不变量与测试

* `all_emitted_relation_types ⊆ set(RELATION_TYPES)`（引擎 emit 与 catalog 一致）。
* `relation_type_counts[T] == 按 T 过滤后的 filtered_count`（按命中股票数，同一股票当日多格命中只计一次）。
* `REL_` 因子命中次数 == Date Scan 同一 (股票, 日期, 关系) 的流日行事件数。
* 矩阵 3 行 × 每行 3 格；目标列不含 `hour`；行级 `relation_types` == 该行 cell 事件类型去重。
* 十神 Golden：固定日主遍历十天干；喜忌五角色 + 未知（未知 ≠ 不匹配）。
* 节气边界：固定 12:00 采样时点的 Golden Case（`2024-02-04` 立春）。
* 日期变化回归：同一股票不同日期 → 原局字段（三柱/日主/喜用）不变，流日字段按规则变化。
