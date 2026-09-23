# 功能存在性审计报告（干支 / 八字 / 黄历 × 股票）

> **审计日期**：2026-09-22
> **审计对象**：股票玄学多模型研究平台（当前分支 `codex/ui-final-polish-acceptance`）
> **审计问题**：给定一个具体交易日（如丙午年丁酉月己亥日），系统能否自动计算"当天干支关系指纹"并与全市场每只股票的八字做匹配，输出用于选股/回测/因子研究的结构化特征？
> **审计方式**：只读。沿真实调用链验证（数据来源 → 计算 → 是否被主流程调用 → 是否落库 → 是否进入回测 → 是否有测试）
> **本轮未修改任何代码、未改动数据库、未删除文件**

> **2026-09-23 后续状态（防止把本审计误读为现状）**：本报告是 2026-09-22 的时点审计。此后本 PR 落地了择日关系扫描/关系历史研究的 **v3 口径**，关闭了正文中部分缺口：
>
> * 「日期→全市场入口不存在」→ `POST /api/v1/research/date-scan`（PIT 全市场扫描）；
> * 「无关系指纹」→ `GET /api/v1/research/date-relations/{date}`（`date-relation-fingerprint-v1`）；
> * 「外部路径缺半合/三会/组合型关系」→ 新的 3×3 日期关系矩阵补齐（目录 22 项，含天干受生/受克），并由 120×120 穷尽测试锁定「引擎可 emit 的类型 == 目录」（`tests/engines/test_date_relation_engine.py`）；
> * 「引擎级而非关系级回测」→ `POST /api/v1/research/relation-study`（REL_* 关系级事件研究 + 负对照 + BH 校正范围声明）。
>
> **仍保持旧定义的部分**：`src/engines/bazi/rules.py::relations_with_external`（个股八字页的 4 柱外部关系）与 `B_*` / `H_*` 因子**未改动、未升级**——不要把 v3 误读为"全部八字关系因子都已换代"。口径差异登记与证据见 [`calculation-differences-relation.md`](calculation-differences-relation.md) 与 [`relation-v3-evidence/`](relation-v3-evidence/)。

---

## 目录

1. [EXECUTIVE SUMMARY](#1-executive-summary)
2. [逐项检查结果](#2-逐项检查结果)
3. [REAL CALL CHAIN](#3-real-call-chain)
4. [IMPLEMENTATION MATRIX](#4-implementation-matrix)
5. [SAMPLE VERIFICATION](#5-sample-verification)
6. [TEST COVERAGE](#6-test-coverage)
7. [GAP LIST](#7-gap-list)
8. [ARCHITECTURE RISKS](#8-architecture-risks)
9. [RECOMMENDED NEXT STEP](#9-recommended-next-step)
10. [附录：审计方法与证据边界](#10-附录审计方法与证据边界)

---

## 1. EXECUTIVE SUMMARY

**核心结论：设想的能力，底层零件约 70% 存在；"日期 → 全市场扫描"这条产线不存在；"适合/不适合交易"这个判断被系统架构性拒绝输出。**

按真实可执行代码判定：**当前处于 Level 2（未完整达成）**，在 Level 3/4 上有**引擎级**但不完整的覆盖。

四句话概括：

1. **干支关系引擎真实可用**——六合、六冲、三合、三会、三刑（含自刑）、六害、天干五合、天干相冲全部正确实现，且**一个地支可同时保留多个关系，不会互相覆盖**（已实测验证）。
2. **"日期 × 股票八字"的匹配已经存在**——`relations_with_external()` 会把流年/流月/流日逐个与原局四柱做匹配，事实上是 4×4 矩阵。但**缺三块**：半合、三会（外部路径），以及全部组合型关系（伏吟/反吟/天克地冲/天合地合）。
3. **关系进入了因子，但没有进入"选股"**——`H_DAY_001~012`、`B_DAY_001~008` 等因子确实落库、确实进回测，但回测粒度是**引擎级 score**，不是关系级特征。而且**"日期 → 全市场"的入口不存在**：全部 API 端点以 `analysis_id` 或股票代码为中心。
4. **"适合交易/不适合交易"是禁止项，不是遗漏**——`direction_from_score()` 用 `score ≥ 58 → 正向` 的硬编码阈值，而 Phase 3 已用实测证明这套口径在 OOS 无支持（`SUPPORTED_OUT_OF_SAMPLE = 0`）。

### 最终 Level 判定

| Level | 定义 | 当前状态 |
|---|---|---|
| Level 0 | 只有黄历/干支基础数据 | ✅ 已超越 |
| Level 1 | 可计算单个合冲刑害破 | ✅ 达成（**破除外**） |
| Level 2 | 可计算"日期 × 股票八字"完整关系 | 🟡 **部分达成**（缺半合/三会/伏吟/反吟/天克地冲/天合地合） |
| Level 3 | 关系已结构化成量化特征 | 🟡 部分（关系进了因子，但无关系指纹、无 S/V/U） |
| Level 4 | 关系已进入历史回测 | 🟡 **引擎级**已进入（非关系级） |
| Level 5 | 可按 S/V/U 对全市场扫描 | 🔴 未达成 |
| Level 6 | 已验证收益/波动/趋势/反转/成交量 | 🔴 未达成 |

**当前代码真实处于 Level 2（未完整），并在 Level 3/4 有引擎级但不完整的覆盖。**

---

## 2. 逐项检查结果

### §2 股票八字是否已存在

#### 2.1 出生规则

枚举定义：`src/core/schemas/common.py:43` `BirthBasis`

| 枚举 | 语义 | 生产是否默认 |
|---|---|---|
| `LISTING_OPEN` | 上市首个正式交易日 + 交易所开盘时刻（**09:30**） | ✅ **是默认** |
| `FIRST_TRADE` | 首日收盘时刻（**15:00**） | 研究用 |
| `IPO_DATE` | IPO 发行日期 | 研究用 |
| `COMPANY_FOUNDATION` | 公司成立日 | ❌ 枚举存在，**数据库 0 条** |
| `CUSTOM` | 自定义 | 需显式传参 |

- **生产默认**：`apps/api/routers/analysis.py:60` → `birth_basis: BirthBasis = BirthBasis.LISTING_OPEN`
- **推导逻辑**：`src/core/stock/birth_profile.py`
- **配置开关**：请求参数 `birth_basis` + `variant_mode`（默认 `NOT_APPLICABLE`，符合"股票无性别"铁律）
- **是否统一**：主流程统一为 `listing_open`；但数据库里**三套并存**（`v2-phase4b-listing_open` / `listing_close` / `ipo_approx`，各 6104 条）

实测三套模型对 600519 的产出（`BaziEngine.build_chart`）：

```
listing_open  09:30  -> 辛巳 丙申 壬戌 乙巳   日主壬水，用神木
listing_close 15:00  -> 辛巳 丙申 壬戌 戊申   日主壬水，用神土   ← 时柱不同 → 喜用神不同
ipo_approx    08-20  -> 辛巳 丙申 乙卯 辛巳   日主乙木，用神水   ← 日柱都不同
```

> **⚠️ 重要**：出生模型的选择会**改变喜用神**，从而改变 `H_DAY_001/002` 全部后续取值。"日期 × 八字"的匹配结果**完全依赖于选了哪套出生协议**。

⚠️ **隐患**：`load_birth_profile(version=None)` 用 `ORDER BY updated_at DESC LIMIT 1` 选版本，而三套 v2 版本**时间戳完全相同**——取哪条不保证。见 §8 R3。

#### 2.2 是否生成四柱

**完整四柱，含时柱。** 因为 `listing_open` 带 09:30 时刻。

- 字段：`BaziChart.year_pillar / month_pillar / day_pillar / hour_pillar`
- 每柱含 `ganzhi`（stem/branch/text/nayin）、`hidden_stems`、`stem_ten_god`、`hidden_ten_gods`

#### 2.3 是否持久化

| 内容 | 表 | 字段 |
|---|---|---|
| 完整八字盘 | `chart_artifact` | `raw_chart`（完整 JSON）、`engine='bazi'`、`engine_version`、`birth_profile_version` |
| 出生档案 | `stock_birth_profile` | `birth_basis` / `birth_datetime` / `timezone` / `source` / `assumptions_json` / `data_quality_json` / `variant_mode` |
| 因子观测 | `factor_observation` | `factor_id` / `raw_value_json` / `normalized_value` / `direction` / `rule_score` / `rule_version` |

**覆盖率严重不足**：`stock_birth_profile` 有 **6104** 只股票，但 `chart_artifact` 里 `engine='bazi'` 只有 **8** 只（排盘为交互式按需触发）。

---

### §3 交易日期干支能力

| 检查项 | 结果 | 证据 |
|---|---|---|
| 算法来源 | lunar-python 1.4.8 | `src/engines/calendar/calendar_engine.py:21` |
| 是否自己实现 | 历法用第三方；**纳音自研** | `nayin_of()` from `src.core.constants`（修正 lunar-python 柱/纳音口径冲突，见 `docs/calculation-differences-phase1.md`） |
| 立春换年 | ✅ `lunar.getYearInGanZhiExact()` | `calendar_engine.py:124` |
| 节气换月 | ✅ `lunar.getMonthInGanZhiExact()` | `calendar_engine.py:125` |
| 时辰 | ✅ `eight_char.getTime()` | `calendar_engine.py:127` |
| 时区 | ⚠️ **固定 Asia/Shanghai，按 naive 本地时间解释** | 写进 `assumptions`，未做真实时区转换 |
| 公历/农历转换 | ✅ `solar.getLunar()` | `calendar_engine.py:81` |
| 日柱验证 | ✅ 有测试 | `tests/golden/test_golden_cases.py`（60 甲子推进等结构不变量） |
| 边界风险 | ⚠️ `_safe()` 吞异常返回 `"甲子"` 默认值 | `calendar_engine.py:38`——**失败会静默产出错误干支** |

---

### §4 天干关系

| 关系 | 状态 | 证据 |
|---|---|---|
| 五合（甲己/乙庚/丙辛/丁壬/戊癸） | ✅ 完整含化气五行 | `STEM_FIVE_HARMONY` `src/core/constants.py:217` |
| 五行生 | ✅ 表存在 | `WUXING_GENERATES`，用于旺衰分组 |
| 五行克 | ✅ 表存在 | `WUXING_OVERCOMES` |
| 同五行 / 比和 | 🟡 部分——按五行归组（比劫），**不区分同/异阴阳** | `rules.py:237` |
| 天干相冲 | ✅ 4 组（甲庚/乙辛/丙壬/丁癸） | `STEM_CLASH` `constants.py:224`，**与五行克分开** |

**天干五合（甲己合土 / 乙庚合金 / 丙辛合水 / 丁壬合木 / 戊癸合火）在 `compute_relations` 中产出结构化结果**：

```python
{
  "relation_type": "天干五合",
  "positions": ["year", "hour"],
  "branches_or_stems": ["辛", "丙"],
  "transform_element": "水",
  "note": "year干辛 与 hour干丙 相合",
}
```

⚠️ **天干五合与相冲均无断言测试**（`甲己`/`乙庚`/`丙辛`/`戊癸` 在 `tests/` 中 0 命中）。

---

### §5 地支关系

| 关系 | 状态 | 证据 |
|---|---|---|
| 六合 | ✅ 6 组完整 | `BRANCH_SIX_HARMONY` `constants.py:181` |
| 六冲 | ✅ 6 组完整 | `_SIX_CLASH_KEYS` `rules.py:540` |
| 三合 | ✅ 4 局 + **半合** | `rules.py:644-663` |
| 三会 | ✅ 4 方（**仅四柱内部**） | `BRANCH_TRIPLE_MEETING` `constants.py:195` |
| 三刑 | ✅ 寅巳申 / 丑戌未 / 子卯 | `_PUNISHMENT_SETS` `rules.py:553` |
| 自刑 | ✅ 辰辰/午午/酉酉/亥亥 | `rules.py:562` |
| 六害 | ✅ 6 组完整 | `BRANCH_SIX_HARM` `constants.py:200` |
| **六破** | 🔴 **完全未实现**（全局 0 处命中） | — |
| 同支 | 🟡 只在自刑时处理（辰午酉亥），其他同支不记录 | `rules.py:562` |

**⚠️ 半合不区分中神**：`elif len(matched) == 2` 一律标为"半合"，没有区分有中神（生旺半合）与无中神（墓库半合）。

**三合判定**：`_match_combo()` 用"轮流消耗"算法匹配位置，能识别完整三合；半合仅要求 2 个支都在。

---

### §6 组合型关系

| 关系 | 状态 | 说明 |
|---|---|---|
| 天合地合 | 🟡 **可推断但无标签** | 实测流年丙午 vs 原局辛未 会输出 `stem_harmonies=['year干辛']` + `harmonies=['year']`，但不产出"天合地合"抽象 |
| 天克地冲 | 🔴 未实现（0 处） | — |
| 伏吟 | 🔴 未实现（0 处） | — |
| 反吟 | 🔴 未实现（0 处） | — |
| **多重关系并存** | ✅✅ **正确实现，不覆盖** | 见下方实测 |

**6.5「多重关系」专门验证结果**：

```python
# Case C 八字 甲寅 丁巳 辛未 壬子 vs 流日己亥
clashes=['month']      # 亥冲巳
harmonies=['year']     # 亥合寅
```

**同一个流日支亥，对寅合、对巳冲，两者全部保留。**

四柱内部同样正确（`compute_relations`）：

```
天干五合 ['month','hour'] 丁壬 -> 木
相害     ['year','month']  寅巳
相刑     ['year','month']  寅巳      ← 寅巳同时"害"和"刑"，并存
相害     ['day','hour']    未子
```

实现原因：`compute_relations` 中六合/六冲/六害/相刑是**4 个独立 `if`**（非 `elif`），且三合/三会在两两循环**之外**单独一轮。

---

### §7 五行层

**不是简单计数**，是加权模型：

| 参数 | 值 | 位置 |
|---|---|---|
| `STEM_WEIGHT` | 1.0（日干 0.8） | `rules.py:46` |
| `MONTH_BRANCH_MULTIPLIER` | 1.5（月令司权） | `rules.py:48` |
| `DAY_BRANCH_MULTIPLIER` | 1.2（日支坐下） | `rules.py:50` |
| 藏干权重 | 本气/中气/余气（`hidden_stem_weight`） | `constants.py` |
| `SEASON_STATE` | 五行在四季的 旺/相/休/囚/死 | `rules.py:62` |

**但**：
- 🟡 **没有逐干支的"生克泄耗助"作用计算**——只有五行力量统计 + 按生克表做的**分组**（比劫/印/食伤/财/官杀）
- 作者自标为"**工程近似，可版本化调整**"（`rules.py:41`）

> **结论**：**不是"仅有五行数量统计"**，但也**不等于完整旺衰模型**。它是"藏干加权力量分布 + 季节状态 + 位置权重"的工程化近似。

---

### §8 十神

✅ 完整实现。`ten_god(day_master, other)`（`constants.py:152`）

实测输出：

```
流日天干 己 相对日主 壬 → 「正官」
流日天干 戊 相对日主 壬 → 「七杀」
流日天干 癸 相对日主 壬 → 「劫财」
```

| 检查项 | 状态 |
|---|---|
| 日主来源 | ✅ 股票八字日干（`stems["day"]`） |
| 基于股票日干 | ✅ |
| 流年天干十神 | ✅ `TemporalPillar.stem_ten_god` |
| 流月天干十神 | ✅ |
| 流日天干十神 | ✅ |
| **地支藏干参与十神** | ✅ `branch_ten_gods`（`bazi_engine.py:303-315`） |
| 进入特征工程 | ✅ `B_DAY_005` 等因子 |

**十神全集**（比肩/劫财/食神/伤官/偏财/正财/七杀/正官/偏印/正印）均可产出，并有 `TEN_GOD_GROUP` 分组。

---

### §9 喜用神 / 旺衰

**是结构化算法，不是"缺什么补什么"**（`compute_strength` `rules.py:190`）：

| 维度 | 实现 |
|---|---|
| **得令** | 日主五行在月令是否"旺"（用 `SEASON_STATE`） |
| **得地** | 四支藏干有根，按位置加权（day 1.0 > month 0.9 > hour 0.7 > year 0.5），根力量 ≥ 1.0 |
| **得势** | 帮扶（比劫+印）vs 耗泄（食伤+财+官杀）占比 ≥ 0.5 |
| **通根** | ✅ `roots` 字段记录每个根的位置与藏干 |
| **透干** | ✅ 十神统计区分可见/藏干 |
| **分级** | 身强/偏强/中和/偏弱/身弱，带 confidence |
| **喜/用/忌/仇/闲** | ✅ 五级（`compute_yongshen` `rules.py:451`） |
| **调候** | 🟡 有，但**只是参考**（冬月加火、夏月加水到喜神） |

**标记为简化版**：

- ⚠️ **`compute_yongshen(strength)` 只接收 strength 参数，不使用格局**——`compute_pattern()` 算了格局却未用于喜用神（格局只作为 `B_NATAL_*` 分类因子）
- ⚠️ **扶抑法为主，非传统完整模型**（无调候为主的取用、无通关/病药等传统取用法）
- ⚠️ confidence 是**人为常量**（0.4~0.78），未经回测

---

### §10 日期 × 股票八字全矩阵

**已实现，而且是 4×4 而非 3×4**（含时柱）。

核心函数：`src/engines/bazi/rules.py:699` `relations_with_external()`

```python
for pos, br in natal_branches.items():          # year/month/day/hour 全遍历
    if BRANCH_CLASH_OF.get(br) == ext_branch:  out["clashes"].append(pos)
    if BRANCH_HARMONY_OF.get(br) == ext_branch: out["harmonies"].append(pos)
    if BRANCH_HARM_OF.get(br) == ext_branch:    out["harms"].append(pos)
    if _punishment_hit(br, ext_branch):         out["punishments"].append(pos)
```

**不是"同位置匹配"** ✅（流年不只对年柱，而是对全部四柱）。

调用点：`BaziEngine._build_temporal()`（`bazi_engine.py:363`），每条 `TemporalPillar` 都携带 `clashes_with_natal` / `harmonies_with_natal` / `triple_harmonies` / `punishments_with_natal` / `harms_with_natal`。

**但覆盖不完整**：

| 关系 | 四柱内部 (`compute_relations`) | 外部×原局 (`relations_with_external`) |
|---|---|---|
| 六合 / 六冲 / 六害 / 三刑 / 自刑 | ✅ | ✅ |
| 天干五合 / 天干相冲 | ✅ | ✅ |
| 三合 | ✅ | ✅（仅完整三合） |
| **半合** | ✅ | 🔴 **缺** |
| **三会** | ✅ | 🔴 **缺** |
| 六破 / 伏吟 / 反吟 / 天克地冲 | 🔴 | 🔴 |

实测确认（外支子 + 原局申，应有半合水）：输出 `无`。

---

### §11 当天「关系指纹」

🔴 **不存在**。

全局搜索 `fingerprint` 只命中交易日历的内容指纹（`trading_calendar.py:88`），与术数无关。

**没有**设想中的 `date_relation_fingerprint` 统一数据结构。最接近的是 `relations_with_external` 返回的 7 键 dict，但它是**即时计算**、不落库、不缓存、无版本号。

对比理想的指纹结构：

| 期望字段 | 现状 |
|---|---|
| `stem_combine` | 🟡 可由 `STEM_FIVE_HARMONY` 推导，无现成接口 |
| `stem_generate` | 🟡 常量表在，无"当天模板"接口 |
| `stem_control` | 🟡 同上 |
| `branch_liuhe` | 🟡 可由 `BRANCH_HARMONY_OF` 推导 |
| `branch_chong` | 🟡 同上 |
| `branch_xing` | 🟡 同上 |
| `branch_hai` | 🟡 同上 |
| `branch_po` | 🔴 常量表都不存在 |
| `branch_sanhe` | 🟡 可由 `BRANCH_TRIPLE_HARMONY` 推导 |
| `branch_sanhui` | 🟡 同上 |

**结论**：原料齐全（除破），但**没有"给定日期 → 关系模板"的封装**。

---

### §12 协同度 S / 扰动度 V / 不确定度 U

🔴 **完全不存在**。

`协同度` / `扰动度` / `不确定度` / `cohesion` / `disturbance` 在全仓库（含 `docs/`）**0 处命中**。

⚠️ **不要混淆**：

| 系统里有的 | 语义 | 与 S/V/U 的区别 |
|---|---|---|
| `ConsensusLabel`（`common.py:116`） | 多引擎观点是否一致（MIXED=模型分歧） | 是**引擎观点层面**，不是关系层面 |
| `CONFLICT_COMBO_SPECS`（`schemas/consensus.py:25`） | 引擎组合的分歧规定 | 同上 |
| `conflict_bazi_pos_ziwei_neg` 等假设 | OOS 检验引擎冲突 | 同上 |

**没有任何"关系层面的协同/扰动/不确定"抽象。**

---

### §13 是否直接定义「吉 / 凶」

**存在，且是三层硬编码**——这正是"规则先验过强"的所在。

#### 第一层：因子级人为权重（`normalized_hint`）

位置：`src/factors/registry/definitions.py`

```
六合命中 → +1，未命中 → 0         (H_DAY_004)
六冲命中 → -1，未命中 → 0         (H_DAY_003)
相刑命中 → -1，未命中 → 0         (H_DAY_012)
建除十二值：开/成/定/危/除 → 偏正；破/闭/平 → 偏负   (H_DAY_006)
黄道 → +1，黑道 → -1              (H_DAY_007)
星宿：吉 → +1，凶 → -1             (H_DAY_011)
```

#### 第二层：加权求和

位置：`src/core/orchestration/analysis_service.py:293` `build_opinion()`

```python
weights = [max(o.confidence, 1e-6) for o in obs]   # 权重 = 人为 confidence 常量
vals = [o.normalized_value or 0.0 for o in obs]
raw = sum(v * w for v, w in zip(vals, weights, strict=True)) / wsum
score = max(0.0, min(100.0, 50.0 + raw * 50.0))     # → 0-100 分
```

#### 第三层：阈值判吉凶

位置：`src/core/orchestration/analysis_service.py:103` `direction_from_score()`

```python
def direction_from_score(score: float | None) -> int:
    if score is None:
        return 0
    if score >= 58:
        return 1      # 正向（吉）
    if score <= 42:
        return -1     # 负向（凶）
    return 0          # 中性
```

#### 四个追问的答复

| 追问 | 答复 |
|---|---|
| 具体位置 | 如上三处 |
| 当前权重 | `confidence`（因子定义时硬编码 0.6~0.8）+ 阈值 58/42 |
| 是否人为设定 | **是** |
| 是否经过回测验证 | **否**。Phase 3C 反而证明该口径有严重偏差——正向率 **94.0%–96.6%**（几乎全市场都判"正向"），Phase 3D 用 TRAIN-only P25/P75 校准才降到 ~26% |
| 规则先验过强风险 | **确实存在**，且已被自己的研究证伪 |

**系统已建立的防护**：

- `MetaphysicsOpinion` docstring 明写"传统规则强度，**不是收益预测**"
- UI 有 `research_status` 徽章
- Phase 3 用 `hit_share` 重新定义信号口径
- 因子字典开篇声明（`definitions.py:8`）：`财星 ≠ 股票上涨；食神生财 ≠ 股票一定上涨；三合 ≠ 股票上涨`

**关于把关系映射为波动/趋势/突破/反转**：🔴 **完全没有**。当前只有"方向"一个维度（+1/0/-1）。

---

### §14 术数关系是否真正进入量化因子系统

见 §3 真实调用链。八个追问的答复：

| 问题 | 答案 |
|---|---|
| 特征名称 | `H_DAY_001`~`H_DAY_012`、`H_MONTH_001`~`005`、`B_DAY_001`~`008`、`B_MONTH_*`、`B_YEAR_*`、`B_NATAL_*` |
| 是否进入训练集 | ✅ 进入研究面板（Phase 3C 单因子分布、Phase 3D 引擎级回测） |
| 是否进入回测 | ✅ **引擎级**（`huangli_raw` / `bazi_raw` / `all_three_raw` 等 18 个假设） |
| 是否只算没用 | 🟡 **存在实例**：`compute_pattern()` 算出格局但**未用于喜用神推导** |
| 是否被配置关闭 | 否 |
| 是否 feature flag 禁用 | 否 |
| 是否只是实验脚本 | 因子的生产计算路径 ✅；但**批量扫描只在实验脚本里**（`scripts/phase3e_neutralization.py` 等） |
| **是否进入生产选股** | 🔴 **没有"选股"功能**。最接近的是 `direction_from_score` 的 ±1 方向，以及 Phase 3D 的引擎级 hit 集合 |

**⚠️ 回测粒度的重要限定**：

Phase 3D 的 18 个假设全部是**引擎级**：

```
bazi_raw / bazi_calibrated / ziwei_raw / ziwei_calibrated
huangli_raw / huangli_calibrated
bazi_ziwei_raw / bazi_ziwei_calibrated / bazi_huangli_raw / bazi_huangli_calibrated
ziwei_huangli_raw / ziwei_huangli_calibrated
all_three_raw / all_three_calibrated
conflict_bazi_pos_ziwei_neg / conflict_ziwei_pos_bazi_neg
conflict_bazi_pos_huangli_neg / conflict_ziwei_pos_huangli_neg
```

**没有单因子级的 OOS 假设**。单因子只在 Phase 3C 做过分布与校准分析（`data/phase3_universe/phase3c_factor_distribution.csv`，含 `activation_rate` / `p25/p50/p75` / `calibrated_*` / `calibration_status`）。

---

### §15 目标变量支持

**只有收益类，其余全部未实现。**

表 `forward_label` 实际字段：

```
ret_1d / ret_5d / ret_10d / ret_20d / ret_60d          ✅ 收益
max_return_20d / max_drawdown_20d                       ✅ 最大涨/最大跌（仅 20D）
bench_ret_20d / excess_return_20d                       ✅ 超额
absolute_up_20d / excess_up_20d / strong_up_20d         ✅ 二元标签
drawdown_controlled_up_20d                              ✅
horizon_available_json                                  ✅ 可用性标记
```

`HORIZONS = (5, 10, 20, 60)`，`PRIMARY_HORIZON = 20`（`src/research/labels/horizon_returns.py:37`）

| 你要的类别 | 状态 | 说明 |
|---|---|---|
| 收益类（next_1d/3d/5d） | ✅ | 有 1/5/10/20/60d |
| 波动类（振幅/ATR/realized vol/最大涨跌） | 🟡 | 只有 `max_return_20d`/`max_drawdown_20d`；**无 ATR、无 realized volatility、无振幅** |
| 趋势类（延续率/MA方向/突破成功率） | 🔴 | 无 |
| 反转类（次日/3日反转/假突破） | 🔴 | 无 |
| 成交类（成交量变化/换手率/量比） | 🔴 | 无（但 `market_bar_daily` **有** `volume`/`amount`/`turnover` 原料，1,841,884 行） |
| 极端事件（涨跌停/跳空） | 🔴 | 无 |

**框架缺什么**：`LabelSet` schema 围绕收益设计，要加波动/趋势/反转标签需扩展 `horizon_returns.py` 与 `forward_label` 表结构。

---

### §16 历史回测数据泄漏

**防护相当强**：

| 检查项 | 状态 | 证据 |
|---|---|---|
| 未来数据算特征 | ✅ 防护 | `clip_to_as_of` `src/market/normalization/frames.py:165` |
| 未来复权因子 | ✅ 已处理 | 收益用 `close × adj_factor`，端点抵消 |
| 未来股票池 | ✅ | universe 版本化（`v2-phase3a`），有断言防扩张 |
| 幸存者偏差 | ✅ 已根治 | ADR-0012，全 A + 退市股（500 股含 333 退市） |
| 未来 ST 状态 | ⚠️ | 未见专门防护 |
| 未来退市信息 | ✅ | 退市股随码交付 |
| 测试集调参 | ✅ 防护 | Phase 3D 预注册 `hypothesis_registry` + `oos_labels_seen_at_registration: False` |

**专门测试**（`tests/test_no_future_data_access.py`，12 个）：

```
test_clip_removes_all_future_bars
test_clip_keeps_as_of_day_itself
test_visible_slice_is_the_only_entry_point
test_clip_preserves_metadata
test_clipped_features_identical_under_contamination   ← 污染测试
test_visible_statistics_identical
test_factor_inputs_have_no_market_fields              ← 因子不得含行情字段
test_factor_as_of_not_after_requested
test_label_fields_are_forward_looking_only
test_labels_do_change_under_contamination             ← 反向验证测试有效
test_no_label_field_used_as_factor_input              ← 标签不得作因子输入
test_labels_raise_when_no_forward_data
```

**关于"先看回测结果 → 改玄学规则 → 同一测试集验证"**：

✅ **有制度性防护**：假设预注册（`frozen_at: 2026-09-20`、`oos_labels_seen_at_registration: False`）、TRAIN/VALIDATION/OOS 三分区、`gate_thresholds` 冻结。

⚠️ **存在一个真实的研究者自由度**：`docs/phase3d-oos-results.md` 记录 Phase 3D 发现统计错误后，Phase 3E **重新定义了检验口径**（`hit_share` 日期级聚合）。这属于方法学修正（有正当理由、有文档），但它确实是在看到结果之后修改的检验方式——文档中有如实披露。

---

### §17 测试覆盖

| # | 测试项 | 状态 | 证据 |
|---|---|---|---|
| 1 | 天干五合 | 🔴 **缺失** | 0 命中 |
| 2 | 六合 | ✅ | `test_six_harmony_detected` `tests/engines/test_bazi_engine.py:164` |
| 3 | 六冲 | ✅ | `test_six_clash_detected` `:180` |
| 4 | 三合 | ✅ | `test_triple_harmony_detected` `:171` |
| 5 | 三会 | 🔴 **缺失** | 0 命中 |
| 6 | 三刑 | ✅ | `test_known_punishment_fulfilled` `:152` |
| 7 | 六害 | 🔴 **缺失** | 0 命中 |
| 8 | 六破 | 🔴 缺失（本就未实现） | — |
| 9 | 自刑 | 🟡 间接（内含于相刑测试） | 无独立断言 |
| 10 | 五行生克 | ✅ | `TestWuxingAndStrength` `:65` |
| 11 | 十神 | ✅ | `TestTenGodConsistency` `:265` |
| 12 | 日期干支 | ✅ | `tests/golden/test_golden_cases.py` |
| 13 | 股票八字 | ✅ | `tests/test_birth_profile.py` |
| 14 | **流日 × 股票八字** | 🔴 **缺失** | `relations_with_external` 无直接测试 |
| 15 | 边界日期 | ✅ | golden cases 结构性不变量 |
| 16 | 节气切换 | ✅ | `tests/engines/test_calendar_engine.py` |
| 17 | 时辰切换 | 🟡 间接 | 无专门边界断言 |

**缺失项汇总**：天干五合、三会、六害、`relations_with_external`（最核心的外部关系函数）、时辰边界。

**其他相关测试文件**：

```
tests/engines/test_calendar_engine.py
tests/engines/test_huangli_engine.py
tests/engines/test_huangli_window_slices.py
tests/engines/test_ziwei_engine.py
tests/factors/test_factor_calculation.py
tests/factors/test_year_relation_wiring.py
tests/golden/test_bazi_cross_validation.py
tests/golden/test_golden_cases.py
tests/golden/test_golden_cases_extended.py
tests/test_third_party_isolation.py
tests/test_no_future_data_access.py
tests/core/test_huangli_day_class.py
tests/core/test_huangli_outlook.py
tests/timeline/test_time_windows.py
```

---

## 3. REAL CALL CHAIN

真实调用链（逐段已实机验证）：

```
日期 (datetime)
  │
  ▼ CalendarEngine.snapshot()                       src/engines/calendar/calendar_engine.py:75
干支 (year/month/day/hour_ganzhi)                    ← lunar-python 1.4.8 Exact 版
  │                                                   （立春换年、节气换月）
  ▼ BaziEngine.build_chart()                         src/engines/bazi/bazi_engine.py:104
股票八字 (BaziChart)
  ├─ 四柱 + 藏干 + 十神
  ├─ 旺衰 (compute_strength)                         rules.py:190
  ├─ 喜用忌仇闲 (compute_yongshen)                    rules.py:451
  └─ 时间流 (TemporalPillar)
       └─ relations_with_external()                  rules.py:699  ← 4×4 关系矩阵
  │
  ▼ compute_huangli_factors() / compute_bazi_factors()
关系因子                                              src/factors/registry/compute.py:616 / :598
  H_DAY_001~012 / H_MONTH_001~005
  B_DAY_001~008 / B_MONTH_001~012 / B_YEAR_001~010 / B_NATAL_*
  │
  ▼ 落库                                             ✅ 实测 21,280 行
factor_observation 表
  │
  ▼ build_opinion()  ← ⚠️ 加权求和                    analysis_service.py:293
引擎观点 score (0-100)
  │
  ▼ direction_from_score()  ← ⚠️ 阈值 58/42          analysis_service.py:103
方向 (+1 / 0 / -1)
  │
  ▼ extract_event_keys()                             src/research/event_study/engine.py:143
事件集 hit = {(stock_code, trade_date)}               （同时满足所有指定因子）
  │
  ▼ BacktestProvider.evaluate_factor / evaluate_signal
Phase 3D OOS 检验                                     docs/phase3d-oos-results.md
  │
  ▼
报告 + gate 判定（gate-v2, mt-v1）
```

**关键断点**：这条链是**引擎级**的。链条上**没有**"日期 → 全市场股票列表"这一步——所有入口都以 `analysis_id` 或股票代码为起点。

| 环节 | 状态 |
|---|---|
| 日期 → 干支 | ✅ 完整 |
| 干支 + 股票八字 → 关系 | ✅ 完整（4×4，缺半合/三会） |
| 关系 → 因子 | ✅ 完整 |
| 因子 → DB | ✅ 完整（`factor_observation`） |
| DB → 引擎 score | ✅ 存在（人为权重） |
| 引擎 score → 事件集 | ✅ 存在（阈值 58/42） |
| 事件集 → OOS 回测 | ✅ 存在（引擎级） |
| **日期 → 全市场扫描** | 🔴 **不存在** |
| **关系 → 波动/趋势/反转标签** | 🔴 **不存在** |
| **S/V/U 扫描** | 🔴 **不存在** |

---

## 4. IMPLEMENTATION MATRIX

| 模块 | 状态 | 完整度 | 进入主流程 | 有测试 | 证据 |
|---|---|--:|---|---|---|
| 股票八字 | ✅ 已完整实现 | 95% | 是 | 是 | `birth_profile.py` + `BaziEngine.build_chart` |
| 日期干支 | ✅ 已完整实现 | 95% | 是 | 是 | `calendar_engine.py:124-127` |
| 天干五合 | ✅ 已完整实现 | 100% | 是 | 🔴 否 | `STEM_FIVE_HARMONY` `constants.py:217` |
| 天干生克 | ✅ 已完整实现 | 100% | 是 | 是 | `WUXING_GENERATES` / `WUXING_OVERCOMES` |
| 六合 | ✅ 已完整实现 | 100% | 是 | 是 | `BRANCH_SIX_HARMONY` `constants.py:181` |
| 六冲 | ✅ 已完整实现 | 100% | 是 | 是 | `_SIX_CLASH_KEYS` `rules.py:540` |
| 三合 | ✅ 已完整实现 | 95% | 是 | 是 | `BRANCH_TRIPLE_HARMONY` `constants.py:187` |
| 半合 | 🟡 部分实现 | 50% | 是 | 🔴 | 内部有；外部×原局缺；不分中神 |
| 三会 | 🟡 部分实现 | 50% | 是 | 🔴 否 | 内部有；外部×原局**缺** |
| 三刑 / 自刑 | ✅ 已完整实现 | 100% | 是 | 是 | `_PUNISHMENT_SETS` `rules.py:553` |
| 六害 | ✅ 已完整实现 | 100% | 是 | 🔴 否 | `BRANCH_SIX_HARM` `constants.py:200` |
| 六破 | 🔴 未实现 | 0% | 否 | 否 | 全局 0 命中 |
| 天合地合 | 🔴 未实现（可推断无标签） | 10% | 否 | 否 | — |
| 天克地冲 | 🔴 未实现 | 0% | 否 | 否 | 全局 0 命中 |
| 伏吟 | 🔴 未实现 | 0% | 否 | 否 | 全局 0 命中 |
| 反吟 | 🔴 未实现 | 0% | 否 | 否 | 全局 0 命中 |
| 十神 | ✅ 已完整实现 | 100% | 是 | 是 | `ten_god()` + 藏干十神 |
| 五行力量 | ✅ 已完整实现 | 80% | 是 | 是 | 加权模型（非简单计数） |
| 旺衰（得令/得地/得势） | ✅ 已完整实现 | 85% | 是 | 是 | `compute_strength` `rules.py:190` |
| 喜用神 | 🟡 部分实现（简化扶抑法） | 60% | 是 | 是 | `compute_yongshen` `rules.py:451`，**不用格局** |
| **日期×股票全矩阵** | 🟡 **部分实现** | **70%** | 是 | 🔴 否 | `relations_with_external` `rules.py:699` |
| 关系指纹 | 🔴 未实现 | 0% | 否 | 否 | — |
| S/V/U 评分 | 🔴 未实现 | 0% | 否 | 否 | 全局 0 命中 |
| **全市场日期扫描** | 🔴 **未实现** | 0% | 否 | 否 | 全部端点以 `analysis_id`/`code` 为中心 |
| 回测接入 | 🟡 部分实现（引擎级） | 60% | 是 | 是 | Phase 3D 18 假设，**非关系级** |
| 波动率研究 | 🔴 未实现 | 5% | 否 | 否 | 仅 `max_return_20d` |
| 趋势研究 | 🔴 未实现 | 0% | 否 | 否 | — |
| 反转研究 | 🔴 未实现 | 0% | 否 | 否 | — |
| 成交量研究 | 🔴 未实现 | 0% | 否 | 否 | 数据有，标签无 |

---

## 5. SAMPLE VERIFICATION

**测试日期**：2026-09-22 = **丙午年 丁酉月 己亥日**（与需求示例一致）

日期干支由生产代码 `CalendarEngine.snapshot()` 得出，非硬编码。

### 5.1 Case A：高「合」关系

**构造八字**：辛未 / 壬辰 / 甲寅 / 丙子

设计意图——命中全部 6 个目标关系：
- 丙辛合（流年干丙 → 原局年干辛）
- 丁壬合（流月干丁 → 原局月干壬）
- 甲己合（流日干己 → 原局日干甲）
- 午未合（流年支午 → 原局年支未）
- 酉辰合（流月支酉 → 原局月支辰）
- 亥寅合（流日支亥 → 原局日支寅）

**实机输出**：

```
流年(丙午) 与原局: clashes=['hour']  harmonies=['year']
                   stem_harmonies=['year干辛']  stem_clashes=['month干壬']
流月(丁酉) 与原局: harmonies=['month']  stem_harmonies=['month干壬']
流日(己亥) 与原局: harmonies=['day']    stem_harmonies=['day干甲']
```

**结果：6/6 全部识别正确。** 额外识别出午冲子、丙壬冲。

### 5.2 Case B：高「冲」关系

**构造八字**：甲子 / 乙卯 / 丁巳 / 戊午

设计意图：
- 午冲子（流年支午 → 原局年支子）
- 酉冲卯（流月支酉 → 原局月支卯）
- 亥冲巳（流日支亥 → 原局日支巳）

**实机输出**：

```
流年(丙午) 与原局: clashes=['year']  punishments=['hour']
流月(丁酉) 与原局: clashes=['month']
流日(己亥) 与原局: clashes=['day']   stem_harmonies=['year干甲']
```

**结果：3/3 全部识别正确。** 额外识别出午午自刑。

### 5.3 Case C：又合又冲

**构造八字**：甲寅 / 丁巳 / 辛未 / 壬子

**实机输出**：

```
流年(丙午) 与原局: clashes=['hour']  harmonies=['day']
                   stem_harmonies=['day干辛']  stem_clashes=['hour干壬']
流月(丁酉) 与原局: stem_harmonies=['hour干壬']
流日(己亥) 与原局: clashes=['month']  harmonies=['year']  stem_harmonies=['year干甲']
```

**关键结论**：流日己亥同时 **冲月支巳**、**合年支寅**——**两个关系全部保留，没有互相覆盖**。

四柱内部关系（同一八字）也正确保留多重：

```
天干五合 ['month','hour'] 丁壬 -> 木
相害     ['year','month']  寅巳
相刑     ['year','month']  寅巳      ← 寅巳同时"害"和"刑"，并存
相害     ['day','hour']    未子
```

### 5.4 边界验证

| 测试 | 期望 | 实机结果 |
|---|---|---|
| 外支辰 + 原局申子 | 三合水局 | ✅ `['申子辰三合水局']` |
| **外支子 + 原局申**（半合水，缺辰） | 半合 | 🔴 **`无`** |
| **外支寅 + 原局卯辰**（三会木，完整） | 三会 | 🔴 **`无`** |
| 天合地合：流年丙午 vs 原局辛未（同柱） | — | 🟡 分别输出 `stem_harmonies=['year干辛']` + `harmonies=['year']`，**无组合标签** |

### 5.5 真实股票扫描实测

对已落库的 8 只股票的八字盘，用 2026-09-22 实跑 `H_DAY_*` 因子：

| 股票 | 日柱 | 当日天干 | 当日地支 | 合冲净值 | 刑日支 |
|---|---|---|---|---|---|
| 600519 | 壬戌 | 闲神 0 | 闲神 0 | −0.58（冲2） | 0 |
| 002594 | 丙辰 | **喜神 +0.6** | **用神 +1.0** | −0.32 | 0 |
| 300059 | 戊辰 | 闲神 0 | 喜神 +0.6 | 0（合1冲1） | 0 |
| 002008 | 乙亥 | 忌神 −1.0 | 用神 +1.0 | −0.32 | **−1（相刑）** |
| 000024 / 300750 / 000001 | — | 忌神 −1.0 | 喜/用神 | −0.32 | 0 |

**同时发现"日期型因子"问题**：`H_DAY_007`（黄黑道）对全部 8 只都是 −1.00，`H_DAY_011`（星宿）对全部 8 只都是 +1.00。

> **这些是纯日期因子，同一天对所有股票同值，无法用来区分股票。** 设计"日期→选股"时必须只按交叉型因子（`H_DAY_001/002/005/009/010/012`）分组。

### 5.6 出生模型敏感性实测

同一只股票（600519），三套出生协议产出**不同的四柱与喜用神**：

```
listing_open  09:30  -> 辛巳 丙申 壬戌 乙巳   用神木  喜火
listing_close 15:00  -> 辛巳 丙申 壬戌 戊申   用神土  喜木火  忌金水
ipo_approx    08-20  -> 辛巳 丙申 乙卯 辛巳   用神水  喜木    忌金土
```

**时柱差 2 位 → 喜用神完全不同。** 这直接影响 `H_DAY_001/002` 的全部取值。

---

## 6. TEST COVERAGE

见 §2 §17。摘要：

| 类别 | 覆盖 | 缺失 |
|---|---|---|
| 干支关系 | 六合/六冲/三合/三刑 | **天干五合/三会/六害/六破** |
| 外部关系函数 | 无 | **`relations_with_external` 完全无测试** |
| 五行/十神/旺衰 | ✅ 完整 | — |
| 历法边界 | ✅ golden cases | 时辰边界仅间接 |
| 防泄漏 | ✅ 12 个测试，含污染测试 | 未来 ST 状态 |
| 出生档案 | ✅ | — |
| 时间窗口 | ✅ | — |

---

## 7. GAP LIST

### P0 — 不解决就不能实现"当天扫描全市场"

| # | 缺口 | 涉及文件 | 建议模块 | 改 schema | 重算历史 | 重跑回测 | 工作量 | 风险 |
|---|---|---|---|---|---|---|---|---|
| P0-1 | **无"日期→全市场"入口**，全部端点以 `analysis_id`/`code` 为中心 | `apps/api/routers/analysis.py` | 新增 `POST /api/v1/scan/date` | 否 | 否 | 否 | **M** | 低 |
| P0-2 | **八字盘只落库 8 只**（`birth_profile` 有 6104） | `chart_artifact` 表 | 批量排盘脚本 + 缓存表 | 可能需新表 | 是（一次性） | 否 | **M** | 中：6104 只全排盘耗时 |
| P0-3 | **出生模型选择不确定**：`load_birth_profile(version=None)` 靠 `updated_at`，三套 v2 时间戳相同 | `analysis_service.py:1142` | 显式 canonical 版本常量 | 否 | 否 | 否 | **S** | **高**：不同股票可能落到不同模型 |

### P1 — 影响研究质量

| # | 缺口 | 证据 | 工作量 | 风险 |
|---|---|---|---|---|
| P1-1 | 外部×原局**缺半合、三会** | 实测返回"无" | **S** | 中：三合判定含时序语义争议 |
| P1-2 | 缺**六破/伏吟/反吟/天克地冲/天合地合** | 全局 0 命中 | **M** | 中：六破流派不统一，需先定口径 |
| P1-3 | 半合**不区分中神** | `rules.py:653` | **S** | 低 |
| P1-4 | `confidence` 权重与 58/42 阈值**人为设定、未经回测** | `build_opinion` + `direction_from_score` | **M** | **高**：Phase 3C 已证正向率 94-96% 有偏 |
| P1-5 | 标签**只有收益类**，无波动/趋势/反转/成交/极端 | `horizon_returns.py` | **L** | 中：需扩展表结构 + 重算 |
| P1-6 | `relations_with_external` **无任何测试** | tests/ 0 命中 | **S** | 中：最核心函数却无测试 |
| P1-7 | 天干五合/三会/六害**无断言测试** | 0 命中 | **S** | 低 |
| P1-8 | 格局算了但**未用于喜用神** | `compute_yongshen(strength)` 签名 | **M** | 中：改动会影响所有既有因子 |
| P1-9 | 单因子级 **OOS 假设缺失**（只有引擎级） | 18 假设全为引擎级 | **M** | 中：多重检验负担会剧增 |
| P1-10 | `_safe()` 静默吞异常返回"甲子" | `calendar_engine.py:38` | **S** | 中：会产出错误干支而不报错 |

### P2 — 增强功能

| # | 缺口 | 工作量 | 风险 |
|---|---|---|---|
| P2-1 | **S/V/U 评分**（协同/扰动/不确定） | **L** | 高：需先定义语义并接受"未经检验" |
| P2-2 | **关系指纹**统一数据结构 + 版本号 | **M** | 低：纯增量 |
| P2-3 | 把关系映射到**波动/趋势/突破/反转**而非涨跌方向 | **L** | 高：需要新的标签体系 |
| P2-4 | 六破规则口径 | **S** | 中：流派分歧 |

---

## 8. ARCHITECTURE RISKS

### R1｜出生模型的三套并存是一个未被管理的维度

`listing_open`（09:30）与 `listing_close`（15:00）对同一只股票产出**不同的时柱**，进而**不同的喜用神**（实测：600519 用神 木 vs 土）。而 `H_DAY_001/002` 的全部取值都建立在喜用神上。

这意味着**"这只股票今天的黄历关系好不好"这个问题的答案，取决于选了哪套出生协议**，而系统没有把这个依赖显式暴露给使用者。

### R2｜"加总成单一分数"与研究结论自相矛盾

系统一边用 `build_opinion` 把 12 个 `H_DAY` 因子加权求和成 0-100 分，一边用 Phase 3 证明这套加总在样本外无支持。

加总本身**掩盖了模型分歧**——这正是 `AGENTS.md` 铁律 8/9 禁止的行为，却在 `build_opinion` 里以"观点"的名义存在。**这是本次审计发现的最深层的设计张力。**

### R3｜`load_birth_profile` 的不确定性

`ORDER BY updated_at DESC LIMIT 1` 在三套 v2 版本时间戳相同时**依赖 SQLite 返回顺序**。

实测 000004 三套 v2 的 `updated_at` 完全相同（`2026-09-20 11:58:34.379472`）。该查询是详情接口 `GET /api/v1/stocks/{code}`（`apps/api/routers/stocks.py:118`）的数据源。

另：做过交互式分析的 6 只股票（含 600519）因写入 `v1` 记录（`updated_at` 更新），会落到 `v1` 而非 `v2-phase4b`。

### R4｜`as_of` 参数语义陷阱

`compute_bazi_factors(chart, as_of)` 的 `as_of` **不驱动计算**，只用于标注。

实测：取 2026-09-21 落库的盘、传 `as_of=2026-09-22`，返回的流日是 **戊戌（09-21）** 而不是 **己亥（09-22）**，**不报错**。

任何想按日期批量算流日的人都会踩这个坑——而 P0-1 正要做这件事。

**正确做法**（已验证）：原局不变，只重建时间流：

```python
tp = engine._build_temporal("day", 目标日干支, day_master, natal_stems, natal_branches, span)
engine._annotate_temporal(tp, chart.yong_shen)
_temporal_factors(chart, tp, "B_DAY", out, target)
```

实测能正确算出己亥日的全部 `B_DAY_*`。**成本极低——不需要重排整个八字盘**（原局字段如日主、喜用忌神与日期无关）。

### R5｜日期型因子污染「选股」语义

`H_DAY_007`（黄黑道）、`H_DAY_011`（星宿）等对**同一天所有股票同值**（实测 8 只全部 −1.00 / +1.00）。用它们排序等于没排。

设计"日期→选股"时必须只按交叉型因子分组。

### R6｜因子字典与运行时代码的张力（提醒）

`definitions.py:8` 明确声明 `财星 ≠ 股票上涨；食神生财 ≠ 股票一定上涨；三合 ≠ 股票上涨`，且每个 `H_DAY` 因子的 explanation 都带免责（如"该倾向来自传统黄历分类，与股票收益无实证关系"）。

但 `build_opinion` 仍然把这些因子加总成单一 score 并映射到吉凶方向。**声明与实现之间存在张力**，需要产品层面明确取舍。

---

## 9. RECOMMENDED NEXT STEP

**第一步（建议优先）：P0-3（半天内可完成，风险最高）**

理由：它不需要新增任何功能，只需把一个隐式依赖变成显式常量——但如果不做，P0-1 和 P0-2 做出来的结果**可能是不可复现的**。

具体：在 `src/core/config.py` 增加 `canonical_birth_profile_version = "v2-phase4b-listing_open"`，让 `load_birth_profile` 默认使用它而非 `updated_at` 排序。

**第二步：P0-2 批量排盘 + 日期切片预计算落库**

这是 500 只面板级的成本（不是全市场）。做完这一步，"当天扫描"的数据基础就具备了，且能同时避开 R4 的参数陷阱。

**第三步：P0-1 前端/API 入口**

约束：
- **只按交叉型因子分组**（避开 R5）
- 输出形式为"按单一维度的描述性分组"（如"今天亥日：与 N 只日支六合、与 M 只相冲"）
- **不产出"适合/不适合"标签**

**关于 S/V/U（P2-1）与波动/趋势标签（P1-5）：建议暂缓。**

它们都需要先确定语义与检验口径，而在 P0 未解决前做，只会增加后面重做的成本。

---

## 10. 附录：审计方法与证据边界

### 10.1 审计方法

本轮审计遵循以下纪律（对应 `AGENTS.md` 第 10 节修改流程与验证原则）：

1. **不按文件名/函数名/README 判断**——所有结论均沿真实调用链验证
2. **实机执行生产代码**——直连 `data/smp.sqlite3`（只读 URI）与调用 `src/` 模块
3. **区分"计算了"与"被使用了"**——逐项检查是否进入主流程
4. **明确当前生产实际使用哪套实现**——不因存在多个版本就模糊处理

### 10.2 使用的工具与命令

```bash
# 数据库只读查询（避免任何写操作）
sqlite3.connect('file:data/smp.sqlite3?mode=ro', uri=True)

# 实机调用生产模块
PYTHONUTF8=1 .venv/Scripts/python.exe -c "..."
```

实际调用的生产函数：

| 函数 | 用途 |
|---|---|
| `CalendarEngine.snapshot()` | 日期 → 干支 |
| `BaziEngine.build_chart()` | 出生档案 → 四柱 |
| `rules.relations_with_external()` | 外部干支 × 原局四柱 |
| `rules.compute_relations()` | 四柱内部关系 |
| `compute_huangli_factors()` | H_DAY / H_MONTH 因子 |
| `compute_bazi_factors()` | B_DAY / B_MONTH / B_YEAR 因子 |
| `build_huangli_outlook()` | 未来交易日黄历 |

### 10.3 证据边界

| 部分 | 验证方式 |
|---|---|
| 因子层 / 关系层 / 落库层 | ✅ **实机执行生产代码** |
| 数据库实际分布 | ✅ **只读 SQL 查询** |
| 前端页面渲染 | ⚠️ **未验证**（未启动服务），结论来自代码阅读 |
| `apps/api` HTTP 层实际响应 | ⚠️ **未验证**（未启动服务），结论来自代码阅读 |

### 10.4 本轮未做的事

- 未修改任何代码
- 未改动数据库
- 未删除文件
- 未启动任何服务
- 未重新训练模型
- 未为了通过测试伪造结果

审计过程中创建过的临时探针目录 `output/_probe/` 已在第一次查证后删除。

---

**报告结束**
