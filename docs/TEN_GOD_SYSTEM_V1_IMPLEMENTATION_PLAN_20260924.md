# 股票玄学多模型研究平台：十神系统 V1.0 完整改造与验收方案

> 文档状态：**实施基线 / 验收合同**
>
> 编制日期：2026-09-24
>
> 仓库：`zxj6827111-blip/stock-metaphysics-platform`
>
> 编制时 `origin/main`：`7f951390d1033f579e56c985aa7704eedc18d15b`
>
> 编制时并行 UI 分支：`codex/ui-visual-parity-r1`，远端已见 HEAD `c32b5eca7c3ed0dfe98d0e7e120e3192408bb10b`
>
> 目标分支建议：`feat/ten-god-system-v1`
>
> 目标 worktree 建议：`../stock-metaphysics-ten-god-v1`
>
> 本文档用于：**实施、代码评审、阶段验收、最终验收、后续回归**。后续实现如果改变本文中的核心语义、API 方向、时间边界或验收标准，必须先更新本文或新增 ADR，不允许代码先漂移、文档后补。

---

## 0. 一句话目标

把仓库中已经存在但分散的十神能力，升级成一套**传统语义明确、时间边界严谨、可双向查询、可筛选、可追溯、可测试、与“日期×股票干支关系矩阵”严格分离**的完整十神系统：

1. **输入股票**：查看该股票的原局十神、藏干十神、未来流年十神、未来流月十神、未来流日十神；
2. **输入日期**：从股票池中筛选当天属于指定流日十神、十神组、喜用匹配状态的股票；
3. 底层**计算全部自然日**；
4. 股票未来日历页面默认**仅显示交易日**，支持一键切换“全部日期”；
5. 默认查看范围：
   - 流年：未来 **10 年**；
   - 流月：未来 **24 个节气月**；
   - 流日：未来 **365 个自然日**；
   - 流日快捷范围：30 / 90 / 180 / 365 天；
6. **十神与喜用神是两套独立维度**，严禁把“正财=适合”“七杀=不适合”写死；
7. 所有计算继续遵守仓库的研究边界：**不把传统结构直接解释为收益、上涨概率或交易建议**。

---

# 1. 已冻结的产品决定

以下三项由产品侧明确确认，V1.0 不再作为待定项：

### 1.1 自然日与交易日

- 底层十神时间轴：**全部自然日计算**；
- 股票→未来日期页面：默认视图为 **仅交易日**；
- 页面必须提供：
  - `仅交易日`
  - `全部日期`
- 非交易日的十神结果不能丢失，只是默认隐藏。

### 1.2 “十神”与“适合”不能混为一谈

页面必须把以下两个筛选拆开：

- **十神条件**
  - 比肩
  - 劫财
  - 食神
  - 伤官
  - 偏财
  - 正财
  - 七杀
  - 正官
  - 偏印
  - 正印
- **喜用匹配**
  - 匹配
  - 不匹配
  - 未知

可继续增加：

- 十神组：
  - 比劫
  - 食伤
  - 财星
  - 官杀
  - 印星
- 五行角色：
  - 用神
  - 喜神
  - 忌神
  - 仇神
  - 闲神
  - 未知

严禁：

- `正财 = 吉`
- `正印 = 吉`
- `七杀 = 凶`
- `某十神 = 推荐买入`

### 1.3 默认时间范围

- 流年：未来 10 年；
- 流月：未来 24 个节气月；
- 流日：未来 365 个自然日；
- UI 快捷切换：30 / 90 / 180 / 365 天。

---

# 2. 十神唯一传统语义合同

## 2.1 唯一中心：股票自己的日干是固定日主

如果股票原局为：

`壬申 · 乙巳 · 癸未 · （时柱）`

则：

- 股票自己的**日干 `癸`** = 固定日主；
- 原局其他天干、原局地支藏干、流年天干、流月天干、流日天干，以及对应流年/月/日地支的藏干，**全部相对于这个固定日主 `癸` 计算十神**。

公式只有一个：

`ten_god(day_master, other_stem)`

其中：

- `day_master` = 股票日主，固定；
- `other_stem` = 当前要判断的天干。

## 2.2 十神定义

仓库当前 `src/core/constants.py::ten_god(day_stem, other_stem)` 已采用以下规则：

- 同我：
  - 同阴阳 = 比肩
  - 异阴阳 = 劫财
- 我生：
  - 同阴阳 = 食神
  - 异阴阳 = 伤官
- 我克：
  - 同阴阳 = 偏财
  - 异阴阳 = 正财
- 克我：
  - 同阴阳 = 七杀
  - 异阴阳 = 正官
- 生我：
  - 同阴阳 = 偏印
  - 异阴阳 = 正印

V1.0 **必须复用这一函数**，不得在 API、页面、服务层复制第二套十神查表。

## 2.3 十神组

沿用当前 `TEN_GOD_GROUP`：

- 比肩、劫财 → 比劫
- 食神、伤官 → 食伤
- 偏财、正财 → 财星
- 七杀、正官 → 官杀
- 偏印、正印 → 印星

前端不得再手写第二份分组表，目录必须由后端下发。

---

# 3. 五类十神在系统中的正式定义

五类内容不是五套算法，只是同一个 `ten_god()` 的五种来源。

| 类型 | 参照中心 | other_stem 来源 | 变化频率 | V1 是否必须 |
|---|---|---|---|---|
| 原局天干十神 | 股票日主 | 股票原局年/月/时干等 | 固定 | 必须 |
| 原局藏干十神 | 股票日主 | 原局各地支藏干 | 固定 | 必须 |
| 流年十神 | 股票日主 | 当前/未来年柱天干 | 每立春换年 | 必须 |
| 流月十神 | 股票日主 | 当前/未来月柱天干 | 每“节”换月 | 必须 |
| 流日十神 | 股票日主 | 每日天干 | 每自然日变化 | 必须 |

此外，为完整展示，流年/月/日地支都应同时展示：

- 地支；
- 藏干；
- 每个藏干相对股票日主的十神。

---

# 4. “原局十神”与“日主”的显示规则

仓库当前 `BaziEngine._build_pillar()` 对日柱天干采用：

`stem_ten_god = "日主"`

而纯函数：

`ten_god("癸", "癸") == "比肩"`

两者都合理，但语义不同：

- 算法关系：同一日干相对于自身是“比肩关系”；
- 盘面展示：日柱天干应优先显示“日主”。

V1.0 必须显式处理，避免出现“同一处有时叫日主、有时叫比肩”的歧义。

建议新十神 Schema 对原局天干提供：

- `stem`
- `ten_god`：规范关系，如 `比肩`
- `display_label`：日柱时为 `日主`
- `is_day_master: true|false`

UI 显示建议：

`癸｜日主（比肩关系）`

而不是修改 `ten_god()` 让它特殊返回“日主”。

---

# 5. 必须和传统十神分开的实验性算法

此前讨论过的：

> 用“当日日干”分别去比较股票年干、月干、日干

例如：

`庚 → 壬/乙/癸 = 食神/正财/伤官`

这可以作为研究因子，但它**不是本 V1.0 的传统流日十神定义**。

必须隔离命名为类似：

- `date_stock_stem_relation`
- `experimental_stem_relation_matrix`
- 中文：`日期—股票天干关系矩阵`

严禁在传统十神页面或 API 中将其混写成：

- 流日十神
- 原局十神
- 标准十神

现有 3×3 “流年/流月/流日 × 股票年/月/日”关系矩阵继续负责：

- 天干五合
- 天干相冲
- 生克关系
- 六合
- 六冲
- 三合
- 三会
- 刑
- 害
- 破
- 伏吟
- 反吟
- 天合地合
- 天克地冲

它和“以股票日主为中心的十神时间轴”是**两条独立轴**。

---

# 6. 用户案例：必须固化为 Golden Case

股票示例：

`壬申 · 乙巳 · 癸未`

股票日主：

`癸`

## 6.1 原局天干

- 壬 → 劫财
- 乙 → 食神
- 癸 → 日主；规范关系为比肩

## 6.2 原局地支藏干

### 申藏：庚、壬、戊

- 庚 → 正印
- 壬 → 劫财
- 戊 → 正官

### 巳藏：丙、庚、戊

- 丙 → 正财
- 庚 → 正印
- 戊 → 正官

### 未藏：己、丁、乙

- 己 → 七杀
- 丁 → 偏财
- 乙 → 食神

## 6.3 日期 `丙午 · 丁酉 · 庚子`

以股票日主癸为中心：

- 流年天干丙 → 正财
- 流月天干丁 → 偏财
- 流日天干庚 → 正印

地支藏干：

- 午藏丁、己 → 偏财、七杀
- 酉藏辛 → 偏印
- 子藏癸 → 比肩

## 6.4 日期 `丙午 · 丁酉 · 辛丑`

- 流年：丙 → 正财
- 流月：丁 → 偏财
- 流日：辛 → 偏印

丑藏：

- 己 → 七杀
- 癸 → 比肩
- 辛 → 偏印

## 6.5 日期 `丙午 · 丁酉 · 壬寅`

- 流年：丙 → 正财
- 流月：丁 → 偏财
- 流日：壬 → 劫财

寅藏：

- 甲 → 伤官
- 丙 → 正财
- 戊 → 正官

这三组必须进入自动测试，不允许仅作为文档示例。

---

# 7. 当前仓库代码审计结论

以下结论基于编制时 `origin/main = 7f951390...`。

## 7.1 已有能力：不应重写

### `src/core/constants.py`

已经存在：

- `TEN_GODS`
- `TEN_GOD_GROUP`
- `BRANCH_HIDDEN_STEMS`
- `ten_god(day_stem, other_stem)`

结论：

**十神核心纯函数已经存在，V1 应复用，不新建第二份计算器。**

### `src/engines/bazi/bazi_engine.py`

`_build_pillar()` 已经：

- 计算原局天干十神；
- 计算原局藏干十神；
- 对日柱显示 `日主`；
- 使用 `ten_god(day_master, hs)`。

结论：

**原局十神与藏干十神底层已经存在。**

### `src/core/schemas/bazi.py`

`TemporalPillar` 已经有：

- `stem_ten_god`
- `branch_ten_gods`
- `stem_is`
- `branch_is`

结论：

**当前时间流数据模型已有十神与喜用角色基础。**

### `src/core/relations/date_relation.py`

`build_day_stem_verdict()` 已明确：

- `ten_god(day_master, day_stem)`
- 十神与喜用角色分离；
- `verdict = 匹配/不匹配/未知`；
- 不把“未知”冒充“不匹配”。

结论：

**当前择日关系扫描的流日十神方向是正确的。**

### `src/core/orchestration/date_relation_scan.py`

当前每只股票已经计算：

- `day_stem_verdict.ten_god`
- `day_stem_verdict.ten_god_group`
- `wuxing_role`
- `verdict`

结论：

**“算不出来”不是当前问题；真正缺的是目录、筛选、未来时间轴与完整展示。**

### `apps/web/components/research/RelationStockTable.tsx`

当前已展示：

- 流日十神；
- 流日喜忌；
- 说明文字明确十神与喜忌是两套独立维度。

结论：

**展示已有，但页面没有十神筛选。**

---

# 8. 当前明确缺陷与技术债

## P0-1：现有 Date Scan 只能按关系类型筛选，不能按十神筛选

当前 `DateScanRequest` 只有：

- `relation_type`
- `sort`
- `offset`
- `limit`

没有：

- `ten_god`
- `ten_god_group`
- `wuxing_role`
- `verdict`

但 `RelationStockResult.day_stem_verdict` 已有这些值。

由于 `AGENTS.md` 明确规定 `/api/v1/**` 已公开契约不能直接修改，V1.0 **不得粗暴给原有 DateScanRequest 增字段并假装兼容**。

建议新增独立十神 API，保留旧接口原样。

## P0-2：流年、流月的“有效日期范围”当前不严谨

当前 `BaziEngine`：

- `_year_range()` = 1 月 1 日 ～ 12 月 31 日；
- `_month_range()` = 公历月 1 日 ～ 月末。

但 `CalendarEngine` 明确采用：

- 年柱：`getYearInGanZhiExact` → **立春换年**
- 月柱：`getMonthInGanZhiExact` → **节气换月**

因此存在：

> 柱的干支算法正确，但范围标签不是严格八字边界。

十神时历不能沿用这个公历范围作为权威边界。

## P0-3：八字盘前端“十神”行实际显示的是藏干十神

当前 `apps/web/components/bazi/BaziChart.tsx`：

- 已有 `stemTenGod` 数据；
- 但“十神”行实际渲染 `hiddenTenGods`。

V1 最终应分成：

- 天干十神
- 藏干
- 藏干十神

但该文件目前正被并行 UI 分支修改，因此**不得在并行阶段抢改**，见 worktree 策略。

## P1：交易日未来覆盖不能静默猜

`src/core/stock/trading_calendar.py` 已区分：

- `observed_index_days`
- `published_exchange_calendar`
- `out_of_coverage`
- `weekend_rule_fallback`

V1 必须把来源和降级状态透传到十神日历。

如果未来日期超出正式日历覆盖：

- 不得把“周一到周五”伪装为确定交易日；
- 必须显示未知/降级原因；
- “仅交易日”默认视图应对未知覆盖给出显式告警。

---

# 9. V1 系统结构：两个对称入口

---

## 9.1 入口 A：股票 → 未来十神

建议新页面：

`/stock/[code]/ten-gods`

中文名称：

`十神时历`

### 页面结构

#### A. 股票原局摘要

必须显示：

- 股票代码、名称；
- 出生档案依据；
- `birth_basis`
- `birth_profile_version`
- 出生时间；
- 时区；
- 四柱；
- 日主；
- 日主五行；
- 数据质量与 assumptions。

#### B. 原局十神

完整四柱展示：

- 年柱天干十神；
- 月柱天干十神；
- 日柱“日主（比肩关系）”；
- 时柱天干十神；
- 每个地支藏干；
- 每个藏干对应十神；
- 本气/中气/余气层级可以显示；
- 工程权重如果展示，必须明确标注“工程近似，不是传统定论”。

#### C. 流年十神

默认未来 10 年。

每行至少：

- 年柱干支；
- 流年天干；
- 天干十神；
- 年支；
- 年支藏干十神；
- 精确起点；
- 精确终点；
- 时区；
- 喜用角色；
- 喜用匹配状态。

#### D. 流月十神

默认未来 24 个节气月。

每行至少：

- 月柱；
- 月干十神；
- 月支藏干十神；
- 精确交节开始；
- 精确下一节结束；
- 时区；
- 喜用角色；
- 匹配状态。

禁止用“9 月 1 日～9 月 30 日”代替流月范围。

#### E. 流日十神

默认计算 365 个自然日。

每行至少：

- 日期；
- 日柱；
- 日干；
- 流日十神；
- 十神组；
- 日支；
- 日支藏干十神；
- 五行角色；
- `匹配/不匹配/未知`；
- 是否交易日；
- 交易日历来源；
- 交易日历是否降级；
- 降级原因。

### 页面筛选

- 日期范围：30 / 90 / 180 / 365；
- 日历显示：
  - 仅交易日（默认）
  - 全部日期
- 十神；
- 十神组；
- 五行角色；
- 喜用匹配状态。

---

## 9.2 入口 B：日期 → 股票

继续保留：

`/research/date-scan`

但加入十神筛选能力。

输入：

`目标日期`

支持筛选：

- 流日十神；
- 十神组；
- 五行角色；
- 喜用匹配；
- 现有关系类型；
- 可选组合筛选。

例如：

- `流日十神 = 正财`
- `喜用匹配 = 匹配`
- `关系类型 = 六合`

这里的“正财”只表示传统十神分类，不自动等于“适合”。

---

# 10. 新 API 设计

为遵守 `AGENTS.md` 的公开 API 契约，建议**不修改现有 `/api/v1/research/date-scan` 请求/响应结构**。

新增独立端点。

## 10.1 十神目录

`GET /api/v1/research/ten-gods/catalog`

返回：

- 10 个十神；
- 5 个十神组；
- 五行角色枚举；
- 匹配状态枚举；
- `ten_god_rule_version`
- 算法方向说明：
  - `day_master_source = stock_natal_day_stem`
  - `other_stem_source = temporal_or_natal_stem`
- disclaimer。

前端所有十神筛选项必须以此为唯一来源。

## 10.2 股票十神时历

建议：

`GET /api/v1/research/ten-gods/stocks/{code}/calendar`

参数：

- `start_date`：可选；
- `years=10`
- `months=24`
- `days=365`
- 不建议由后端默认删除非交易日；应返回全部自然日，并由 UI 默认过滤；
- 若为控制响应大小，可保留 `view=all|trading`，但计算层仍必须先构造自然日结果。

响应主要部分：

- `stock`
- `birth_profile`
- `natal`
- `years`
- `months`
- `days`
- `versions`
- `trading_calendar`
- `warnings`
- `disclaimer`

## 10.3 日期十神扫描

建议：

`POST /api/v1/research/ten-gods/date-scan`

请求：

- `date`
- `universe`
- `birth_basis`
- `birth_profile_version`
- `ten_god`
- `ten_god_group`
- `wuxing_role`
- `verdict`
- `relation_type`（可选复合）
- `sort`
- `offset`
- `limit`

注意：

- 这是新 API，不是偷偷扩展旧 DateScanRequest；
- 内部可以复用现有 PIT universe、出生档案、`build_day_stem_verdict()` 与关系矩阵函数；
- 不能复制十神算法。

响应：

- `scan_id`
- `target_date`
- `versions`
- `universe_as_of`
- `filtered_count`
- `ten_god_counts`
- `ten_god_group_counts`
- `verdict_counts`
- `rows`
- `warnings`
- `disclaimer`

---

# 11. 新 Schema 建议

建议新增：

`src/core/schemas/ten_god.py`

至少包括：

- `TenGodCatalogResponse`
- `TenGodNatalStem`
- `TenGodHiddenStem`
- `TenGodNatalPillar`
- `TenGodNatalProfile`
- `TenGodTemporalSegment`
- `TenGodDayRow`
- `TenGodCalendarVersions`
- `TenGodStockCalendarResponse`
- `TenGodDateScanRequest`
- `TenGodDateScanRow`
- `TenGodDateScanResponse`

## 11.1 TenGodTemporalSegment 必须包含精确时刻

不要只用：

- `start_date`
- `end_date`

应至少有：

- `start_at`
- `end_at`
- `timezone = Asia/Shanghai`

建议使用半开区间：

`[start_at, end_at)`

这样交节瞬间不会出现两个流月都包含同一时刻。

---

# 12. 时间边界算法

## 12.1 时区

统一：

`Asia/Shanghai`

CalendarEngine 当前返回的是本地壁钟语义，十神时历输出必须把时区元数据显式带出。

如新 Schema 输出 offset-aware datetime，应在十神服务层用 `ZoneInfo("Asia/Shanghai")` 规范化。

## 12.2 流年

流年不是公历年。

定义：

- 以 `CalendarEngine.year_ganzhi` 的实际切换点为准；
- 切换点应与立春一致；
- 区间：
  - `[本年立春交节时刻, 下一年立春交节时刻)`

## 12.3 流月

流月不是公历月。

定义：

- 以 `CalendarEngine.month_ganzhi` 的实际切换点为准；
- 只在十二“节”切换月柱；
- 区间：
  - `[本次换月节气时刻, 下一次换月节气时刻)`

## 12.4 流日

十神日历是日级产品，和现有 Date Scan 保持一致：

- 每个自然日以 `12:00:00 Asia/Shanghai` 取日柱；
- 这样不把 23:00 晚子时口径混进“整日择日”产品；
- 如果未来要做时辰级十神，另开版本和独立功能。

## 12.5 边界实现建议

不要在十神服务直接 import `lunar_python`。

允许的方法：

1. 只调用 `CalendarEngine.snapshot()`；
2. 通过 `year_ganzhi/month_ganzhi` 的变化识别区间；
3. 使用 `jieqi.prev_at/next_at/current_at` 作为边界证据；
4. 对换柱日做二分/细化定位，直到需要的时间精度；
5. Golden Case 验证边界前后 1 秒/1 分钟的柱值。

---

# 13. 交易日历语义

底层始终有 365/366 个自然日行。

每个日行增加：

- `is_trading_day: true | false | null`
- `trading_calendar_source`
- `trading_calendar_authoritative: bool`
- `trading_calendar_degraded_reason`
- `trading_calendar_version_token`

对 SSE / SZSE 继续复用：

`src/core/stock/trading_calendar.py`

优先级：

1. observed
2. published
3. out_of_coverage
4. weekend fallback（降级）

UI 默认“仅交易日”时：

- `true`：显示；
- `false`：隐藏；
- `null`：不能静默当成休市，应显示覆盖不足提示；
- weekend fallback：必须有明显的“估算/降级”标记。

---

# 14. 未来日期的股票池语义

历史日期：

- 使用 Point-in-Time universe；
- 继续遵守 survivorship-bias 防护。

未来日期：

- 系统无法知道未来新上市、未来退市事件；
- 不得伪造“未来 PIT 股票池”。

建议 V1 规则：

- 若目标日期 > 当前 universe 可证据化范围：
  - 使用**最新已知 canonical universe**；
  - 响应显式给出：
    - `universe_mode = latest_known_for_future`
    - `universe_as_of`
    - `future_universe_assumption`
  - 页面显示“未来股票池按当前已知成分冻结；不包含未知的未来上市/退市变化”。

这一规则必须进入 API、测试和免责声明。

---

# 15. 版本治理

新增独立版本：

`ten_god_rule_version = "ten-god-v1"`

不要借用：

- `relation_rule_version`
- `factor_rule_version`

建议每个十神结果返回：

- `ten_god_rule_version`
- `calendar_engine_version`
- `bazi_engine_version`
- `birth_profile_version`
- `universe_version`
- `trading_calendar_version_token`（涉及交易日时）

如果修正立春/节气边界导致 `BaziEngine` 时间流字段语义变化，再按仓库规则评估是否提升：

- `bazi_engine_version`
- 或单独时间段 Schema 版本

---

# 16. 缓存设计

## 股票十神时历缓存键至少包含

- stock_code
- birth_profile_version
- birth_profile fingerprint / source identity
- start_date
- years
- months
- days
- ten_god_rule_version
- calendar_engine_version
- bazi_engine_version
- trading calendar version token

## 日期十神扫描缓存键至少包含

- date
- evaluation_time
- timezone
- universe_version
- universe_digest
- birth_basis
- birth_profile_version
- ten_god_rule_version
- calendar_engine_version
- 关系规则版本（只有复合 relation_type 时）
- 过滤条件不一定进入“全量底表缓存”，但必须进入响应/query/scan_id 语义。

不得因为交易日历更新而继续返回旧的“仅交易日”结果。

---

# 17. 与现有 Date Relation 的复用边界

可复用：

- `build_day_stem_verdict()`
- `build_relation_matrix()`
- PIT universe
- 出生档案解析
- 静态原局缓存
- `TradingCalendarProvider`

不应复用为十神真值来源：

- 3×3 矩阵中的每格 `event.ten_god` 聚合；
- “流日行三个格”中的三份十神事件；
- 任何“年对年、月对月、日对日”十神解释。

权威流日十神始终只有：

`ten_god(stock_day_master, target_day_stem)`

---

# 18. 前端整改

## 18.1 新建十神时历页

建议：

`apps/web/app/stock/[code]/ten-gods/page.tsx`

配套组件建议新建：

- `TenGodNatalPanel.tsx`
- `TenGodYearTable.tsx`
- `TenGodMonthTable.tsx`
- `TenGodDayCalendar.tsx`
- `TenGodFilters.tsx`
- `TenGodLegend.tsx`

尽量新建组件，降低与并行 UI 分支的冲突。

## 18.2 现有 BaziChart 最终修正

最终必须将当前：

- `藏干`
- `十神（实际上是 hiddenTenGods）`

拆成至少：

- `天干十神`
- `藏干`
- `藏干十神`

但这一改动必须在并行 UI 分支合并后再做。

## 18.3 Date Scan 增加十神筛选

现有 `/research/date-scan` 增加：

- 十神
- 十神组
- 五行角色
- 喜用匹配

筛选目录全部读取后端 catalog。

前端禁止自己执行：

- 五行生克
- 阴阳正偏
- ten_god 推导
- 喜用判定

只展示后端确定性结果。

---

# 19. 并行 UI 任务与 worktree 冲突策略

编制本文时，并行分支：

`codex/ui-visual-parity-r1`

已修改或正在涉及的文件包括：

- `apps/web/components/bazi/BaziChart.tsx`
- `apps/web/app/stock/[code]/bazi/page.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `src/core/schemas/bazi.py`
- `src/engines/bazi/bazi_engine.py`
- 以及多项 UI shell / dataSource 文件。

十神项目最终也可能需要其中部分文件。

因此 V1 实施必须采用以下并行策略：

### 阶段 A：UI 分支未合并前

十神 worktree：

**允许做：**

- 新文档；
- 新十神 Schema 文件；
- 新十神服务；
- 新 API；
- 新测试；
- `src/core/config.py` 的独立十神版本字段；
- 当前 UI 分支未触碰的 relation / research 后端文件（必要时）。

**禁止修改：**

- `BaziChart.tsx`
- `apps/web/lib/api.ts`
- `apps/web/lib/types.ts`
- `stock/[code]/bazi/page.tsx`
- `src/core/schemas/bazi.py`
- `src/engines/bazi/bazi_engine.py`

除非并行 UI 工作已经合并到 main 并完成 rebase。

### 阶段 B：UI 分支合并后

1. `git fetch origin`
2. 将十神分支 rebase 到最新 `origin/main`
3. 处理真实冲突
4. 全量回归
5. 再做 TG-4 前端集成与 BaziChart 修正

**禁止为了省事把 UI 分支的文件整文件覆盖。**

---

# 20. Worktree 创建方案

在现有主仓库目录执行，**不得 stash / clean / reset 当前 UI 工作树**：

```bash
git fetch origin --prune
git status --short
git worktree list
```

确认目标 worktree 和分支不存在后：

```bash
git worktree add ../stock-metaphysics-ten-god-v1 \
  -b feat/ten-god-system-v1 \
  origin/main
```

进入：

```bash
cd ../stock-metaphysics-ten-god-v1
git rev-parse HEAD
git status --short
```

把实际 base SHA 写入实施记录。

如果分支已存在，不要重复 `-b`：

```bash
git worktree add ../stock-metaphysics-ten-god-v1 feat/ten-god-system-v1
```

---

# 21. 实施阶段

---

## TG-0：Worktree + 合同冻结

### 工作

- 建 worktree；
- 记录：
  - base SHA
  - origin/main SHA
  - 并行 UI branch SHA
- 将本文档放入：
  - `docs/TEN_GOD_SYSTEM_V1_IMPLEMENTATION_PLAN_20260924.md`
- 不改业务行为。

### 验收

- 原 UI 工作树零写入；
- 新 worktree 独立；
- 分支正确；
- plan 已落库；
- 工作树状态可解释。

建议 commit：

`docs(ten-god): freeze v1 implementation and acceptance contract`

---

## TG-1：十神核心合同、Schema、Golden Case

### 工作

- 新增 `ten_god_rule_version`
- 新增 `src/core/schemas/ten_god.py`
- 新增 catalog
- 审计 `ten_god()` 方向
- 100 组映射全覆盖：
  - 10 日主 × 10 天干
- 加本文第 6 章 Golden Case
- 明确“日主显示”与“比肩关系”区别
- 不做 UI

### 禁止

- 不重写 `ten_god()`
- 不改并行 UI 重叠文件
- 不改旧 v1 API 契约

### 验收

- 100/100 映射通过
- 用户三组日期案例通过
- `make test`
- `make test-golden`
- `make test-leak`

建议 commit：

`test(ten-god): lock canonical ten-god contract and golden cases`

---

## TG-2：股票 → 未来十神时历后端

### 工作

新增建议：

- `src/core/orchestration/ten_god_calendar.py`
- 或按现有架构拆成 core service + orchestration

实现：

- 原局十神
- 藏干十神
- 10 年流年
- 24 节气月
- 365 自然日
- 精确节气边界
- 交易日状态
- 版本与 warnings
- 新 API：
  - catalog
  - stock calendar

### 关键要求

- 流年边界不是 1/1；
- 流月边界不是每月 1 日；
- 日级采用 12:00 Asia/Shanghai；
- 365 天底表不因交易日过滤丢行；
- 交易日覆盖不足显式告警。

### 验收

- 立春前/后边界测试
- 惊蛰、清明、立秋、白露、寒露、立冬、大雪、小寒等换月边界
- 边界前后时刻的柱值正确
- 365/366 自然日数量正确
- 交易日 `true/false/null/降级` 语义正确
- API 版本字段齐全
- 后端全绿

建议 commit：

`feat(ten-god): add stock temporal calendar api`

---

## TG-3：日期 → 全市场十神扫描后端

### 工作

新增：

`POST /api/v1/research/ten-gods/date-scan`

支持：

- ten_god
- ten_god_group
- wuxing_role
- verdict
- relation_type 可选复合
- sort
- offset
- limit

### 关键要求

- 权威流日十神：
  `stock day master × target date day stem`
- PIT 历史股票池；
- 未来日期使用 latest-known universe 并显式标记；
- 不修改旧 `/api/v1/research/date-scan` contract；
- 过滤前计数与过滤后计数含义明确；
- catalog 是前端唯一枚举来源。

### 验收

- 正财筛选结果逐股可重算；
- 十神组筛选与单十神一致；
- 喜用匹配过滤不改变十神定义；
- relation_type 与 ten_god 组合过滤是 AND；
- pagination 前先过滤；
- count 对得上；
- unavailable 不用 0 冒充。

建议 commit：

`feat(ten-god): add market date scan filters`

---

## TG-3.5：并行 UI 合流门

在 UI 分支合并前，TG-4 不得开始。

执行：

```bash
git fetch origin --prune
git rebase origin/main
```

输出：

- 新 base/main SHA；
- 冲突文件；
- 每个冲突如何解决；
- 全量测试。

如果 UI 分支尚未合并：

**停止，不抢改重叠 UI 文件。**

---

## TG-4：前端十神时历 + Date Scan 筛选

### 工作

- 新 `/stock/[code]/ten-gods`
- 原局/藏干完整显示
- 流年 10 年
- 流月 24 节气月
- 流日 365 自然日
- 默认仅交易日
- 一键全部日期
- 30/90/180/365
- 十神/十神组/喜用筛选
- `/research/date-scan` 加十神筛选
- 修 BaziChart 天干十神 / 藏干十神混淆
- 前端只展示，不重算

### 验收

- typecheck
- build
- Playwright
- loading / empty / error
- 交易日覆盖不足状态
- 手机/桌面不横向炸裂
- 现有 UI 视觉改造不被回滚

建议 commit：

`feat(web): add ten-god calendar and scan filters`

---

## TG-5：最终验收与文档封板

### 工作

- 全量测试
- Golden
- leak
- typecheck
- build
- UI E2E
- API contract 回归
- 性能报告
- 文档
- 变更清单
- 已知限制

建议 commit：

`docs(ten-god): close v1 acceptance evidence`

---

# 22. 测试矩阵

## 22.1 十神纯函数

必须测试：

- 10 × 10 = 100 组；
- 每个日主恰好产生：
  - 比肩 1
  - 劫财 1
  - 食神 1
  - 伤官 1
  - 偏财 1
  - 正财 1
  - 七杀 1
  - 正官 1
  - 偏印 1
  - 正印 1

这是极强的不变量。

## 22.2 原局

至少测试：

- 年/月/日/时天干；
- 所有地支藏干；
- 日柱显示 `日主`；
- 规范关系仍可追溯到 `比肩`。

## 22.3 时间边界

至少：

- 立春前 1 分钟 / 后 1 分钟；
- 月柱换柱的十二“节”抽样全覆盖；
- 交节同日早晚；
- 跨年；
- 闰年；
- 23:00 晚子时不影响日级产品的 12:00 固定采样规则。

## 22.4 交易日

- observed
- published
- out_of_coverage
- weekend fallback
- 非交易日仍有十神行
- “仅交易日”只是显示过滤，不改变自然日底表。

## 22.5 API

- catalog
- stock calendar
- date scan
- 错误枚举 422
- 版本不支持 422
- offset/limit
- filter counts
- unavailable
- old date-scan contract 未变化。

## 22.6 UI

- 股票十神页加载态
- 空态
- 错误态
- 默认交易日
- 切全部日期
- 10 个十神筛选
- 5 个十神组
- 喜用匹配
- Date Scan 联合筛选
- 详情与列表同一股票结果一致。

---

# 23. 必须新增的验收不变量

1. **同一股票、同一日期，在“十神时历”和“日期扫描”中的流日十神必须完全一致。**
2. **同一日主与同一外部天干，不得因页面不同返回不同十神。**
3. 前端不得实现自己的十神映射表。
4. 交易日过滤不得改变十神结果。
5. 喜用过滤不得改变十神结果。
6. 关系矩阵不得成为传统十神的权威来源。
7. 流年柱在立春才换。
8. 流月柱在“节”才换。
9. 旧 `/api/v1/research/date-scan` 请求与响应契约保持不变。
10. 未知必须是 `null/unknown`，不能是 `0/false` 的伪装。

---

# 24. 性能要求

本项目已有日期扫描缓存与静态原局缓存，十神扫描本身非常轻。

实现必须避免：

- 每个筛选操作都对每只股票重新完整排四柱；
- 前端翻页触发全量 BaziEngine 重算；
- 365 天 × 每天全量重建不必要原局；
- UI 同时重复请求同一 calendar endpoint。

最终报告必须给出：

- 冷缓存耗时；
- 热缓存耗时；
- 股票日历 365 天耗时；
- 全市场日期十神扫描耗时；
- 缓存命中率/描述；
- Bazi fallback 数量；
- 测试机器信息。

V1 首次不强行写死跨机器毫秒门槛，但要求：

- 无明显 N×全盘重算；
- 热缓存必须明显优于冷缓存；
- 相同参数重复请求必须命中可解释缓存；
- 性能数据必须进入验收报告，后续再冻结硬阈值。

---

# 25. 免责声明与研究边界

所有十神页面必须保留研究免责声明，至少表达：

- 十神是传统术数结构分类；
- 不代表预期收益率；
- 不代表上涨概率；
- 不构成交易建议；
- “喜用匹配”也是传统规则内的结构匹配，不等于市场有效性；
- 市场有效性必须通过独立历史研究、负对照、样本外验证确认。

不得新增：

- “正财日建议买入”
- “七杀日应卖出”
- “十神胜率”
- “十神上涨概率”

除非未来有独立研究模块且明确标注样本、区间、统计方法与 OOS 结果。

---

# 26. V1 不做的内容

以下不属于本轮 V1 强制范围：

- 用十神直接生成买卖建议；
- 自动打“吉/凶”总分；
- 根据十神给仓位；
- 将十神混入当前 S/V/U；
- 重新定义股票出生档案；
- 改大运男女顺逆规则；
- 时辰级十神扫描；
- 十神有效性历史回测正式结论。

后续如果做“十神历史研究”，应作为独立 Research Work Package，不能反向污染本 V1 的确定性计算层。

---

# 27. 最终文件级建议

预计新增：

```text
docs/TEN_GOD_SYSTEM_V1_IMPLEMENTATION_PLAN_20260924.md

src/core/schemas/ten_god.py
src/core/orchestration/ten_god_calendar.py
src/core/orchestration/ten_god_date_scan.py

tests/core/test_ten_god_contract.py
tests/golden/test_ten_god_temporal_golden.py
tests/integration/test_api_ten_god_calendar.py
tests/integration/test_api_ten_god_date_scan.py

apps/web/app/stock/[code]/ten-gods/page.tsx
apps/web/components/ten-god/TenGodNatalPanel.tsx
apps/web/components/ten-god/TenGodYearTable.tsx
apps/web/components/ten-god/TenGodMonthTable.tsx
apps/web/components/ten-god/TenGodDayCalendar.tsx
apps/web/components/ten-god/TenGodFilters.tsx
```

预计修改（部分必须等 UI 分支合并后）：

```text
src/core/config.py
apps/api/routers/research.py
src/core/relations/date_relation.py            # 仅必要复用/小改时
src/core/orchestration/date_relation_scan.py   # 原 API 契约不得变
apps/web/app/research/date-scan/page.tsx
apps/web/components/research/RelationStockTable.tsx
apps/web/components/bazi/BaziChart.tsx          # UI 合流后
apps/web/lib/api.ts                             # UI 合流后
apps/web/lib/types.ts                           # UI 合流后
```

`src/engines/bazi/bazi_engine.py` 与 `src/core/schemas/bazi.py` 在并行 UI 阶段只读审计；如最终决定修复旧 TemporalPillar 范围语义，必须在 UI 合流后单独提交并提升/记录相应版本。

---

# 28. 最终验收清单

## A. 理论/语义

- [ ] 股票日干是唯一固定日主
- [ ] 原局十神正确
- [ ] 藏干十神正确
- [ ] 流年十神正确
- [ ] 流月十神正确
- [ ] 流日十神正确
- [ ] 十神和喜用独立
- [ ] 实验性天干矩阵未冒充传统十神

## B. 时间

- [ ] 年柱立春换
- [ ] 月柱按节换
- [ ] 精确交节时刻
- [ ] Asia/Shanghai 明示
- [ ] 日级固定 12:00

## C. 股票→日期

- [ ] 原局完整
- [ ] 藏干完整
- [ ] 未来 10 年
- [ ] 未来 24 节气月
- [ ] 未来 365 自然日
- [ ] 默认仅交易日
- [ ] 可切全部日期
- [ ] 30/90/180/365
- [ ] 交易日来源可追溯

## D. 日期→股票

- [ ] 可按 10 十神筛
- [ ] 可按 5 组筛
- [ ] 可按五行角色筛
- [ ] 可按匹配状态筛
- [ ] 可和 relation_type 组合
- [ ] 过滤、计数、分页一致

## E. API 治理

- [ ] 不破坏旧 v1 date-scan
- [ ] 新 catalog 是唯一枚举来源
- [ ] `ten_god_rule_version`
- [ ] calendar/bazi/birth/universe 版本齐
- [ ] unknown 不伪装

## F. 测试

- [ ] 100/100 十神映射
- [ ] 用户示例 Golden Case
- [ ] 立春边界
- [ ] 月节边界
- [ ] 自然日/交易日
- [ ] API integration
- [ ] typecheck
- [ ] web build
- [ ] Playwright
- [ ] make test
- [ ] make test-golden
- [ ] make test-leak

## G. 并行开发安全

- [ ] 原 UI 工作树零写入
- [ ] 十神独立 worktree
- [ ] UI 合流前未抢改重叠文件
- [ ] UI 分支合并后完成 rebase
- [ ] 未整文件覆盖 UI 改造结果

---

# 29. Definition of Done

只有同时满足以下条件，才能宣布 `TEN_GOD_SYSTEM_V1 = DONE`：

1. 五类十神全部可见；
2. 两个方向的查询都可用；
3. 365 自然日底表存在；
4. 交易日默认筛选不丢失自然日数据；
5. 精确立春/节气月边界通过 Golden；
6. 100 组十神映射通过；
7. 两个页面的同股票同日期流日十神一致；
8. 不破坏旧 v1 Date Scan API；
9. 不与并行 UI 分支发生未解释覆盖；
10. 后端、Golden、leak、typecheck、build、E2E 全部通过；
11. 最终提交提供完整验收证据与已知限制；
12. 没有把十神或喜用包装成收益预测。

---

# 30. 最终验收报告必须输出的证据

最终 AI 汇报必须包含：

- base SHA
- final HEAD
- commit 列表
- 修改文件列表
- 新 API 列表
- `ten_god_rule_version`
- 100 映射测试结果
- 用户案例测试结果
- 立春/月节边界测试结果
- 365 自然日计数
- 交易日日历来源与覆盖
- Date Scan 十神过滤计数样例
- 股票十神时历样例
- 所有测试命令与结果
- 性能数据
- 并行 UI 合流方式
- 未解决问题
- 是否满足本文第 28、29 章全部项目

任何一项缺失，都不应直接标记“全部完成”。
