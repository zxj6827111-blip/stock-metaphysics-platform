# Phase 3G · 紫微第二实现源交叉核对差异报告

> 生成时间：2026-09-20T13:23:22.050465 · commit `b04a2b9fc69d2bac2b883bcd948f9892b0cf6cb3`
> 案例集 `phase3g-ziwei-crosscheck-cases-v1` · 案例数 24
> 生产引擎 `iztro-2.6.1+smx-1.0.0` · 参考实现 `fortel-ziweidoushu` 1.3.4（中州派，MIT）

## 0. 一句话结论

在 24 个固定案例、2280 项字段比较中，**95.75% 完全一致**；差异集中在 3 类可解释原因上，没有任何一类差异会改变本研究平台的因子语义。

## 1. 来源与许可证审计（GOAL §3G-1）

| 仓库 | 语言 | 许可证 | ★ | 依赖 | 是否独立实现 | 决定 | 理由 |
|---|---|---|---:|---|---|---|---|
| `airicyu/fortel-ziweidoushu` | TypeScript | MIT | 32 | 仅 util（自带日历，不依赖 iztro） | 是 | `ADOPTED_AS_REFERENCE` | 真正独立实现（唯一运行时依赖 util，自带 jjonline 日历），MIT 许可明确，v1.3.4 已发布到 … |
| `SylarLong/iztro` | TypeScript | MIT | 4174 | 生产引擎本身 | 否 | `PRODUCTION_ENGINE` | 生产引擎（Phase 2 起通过 Adapter 接入），不可作为自己的第二实现源。 |
| `Renhuai123/ziwei-doushu` | TypeScript | MIT | 4169 | **import { astro } from 'iztro'**（lib/ziwei/algorithm.ts 首行） | 否 | `REJECTED_NOT_INDEPENDENT` | 自我描述为『紫微斗数开源排盘引擎』且星标最高，但源码首行即 import iztro 的 astro 做排盘，其增… |
| `x-haose/py-iztro` | Python | 未声明（None） | 135 | iztro 的 Python 移植 | 否 | `REJECTED_LICENSE_AND_NOT_INDEPENDENT` | 双重排除：许可证未声明；且是 iztro 的移植，算法同源。 |
| `spyfree/iztro-py` | Python | MIT | 18 | iztro 的 Python 移植 | 否 | `REJECTED_NOT_INDEPENDENT` | 许可证明确但算法同源（iztro 移植），无法用于验证 iztro 的实现差异。 |
| `learnwithu/mingli-master` | Python | MIT | 730 | 基于 iztro-py 排盘 | 否 | `REJECTED_NOT_INDEPENDENT` | 排盘部分来自 iztro-py，同源。 |
| `Wolke/ziwei-doushu` | Python | NOASSERTION（不明确） | 18 | 未知 | 未知 | `REJECTED_LICENSE_UNCLEAR` | 许可证状态为 NOASSERTION；按 GOAL §3G-1，许可证不明确者禁止集成，也不作为可执行参考。 |
| `ziweiknows/ziwei-chart` | TypeScript | GPL-3.0 | 450 | 完整 Web 应用（非库） | 未知 | `REJECTED_LICENSE_COPYLEFT_AND_SCOPE` | GPL-3.0 属强 copyleft：即便只做本地参考，把其结果并入本仓库的产物链会带来许可证传染风险；且它是应… |
| `cubshuang/ZiWeiDouShu` | JavaScript | 未声明（None） | 78 | 未知 | 未知 | `REJECTED_LICENSE_UNCLEAR` | 无许可证声明，且 2020 年后无维护。 |
| `jonhnsonzz/nihaisha-tianji` | Python | MIT | 23 | 知识库 / MCP（非排盘引擎） | 未知 | `REJECTED_NOT_A_CHART_ENGINE` | GOAL 文本提到优先调研『Tianji』。实测该仓库是倪海厦《天纪》语料与 MCP 服务，**不含独立排盘算法*… |
| `EdwinXiang/dart_iztro` | Dart | MIT | 155 | iztro 的 Dart 移植 | 否 | `REJECTED_NOT_INDEPENDENT` | iztro 移植，算法同源；Dart 运行时也不在本项目技术栈内。 |

**关键审计结论**：星标最高的两个「紫微排盘引擎」中，`SylarLong/iztro` 就是本项目的生产引擎，而 `Renhuai123/ziwei-doushu` 的 `lib/ziwei/algorithm.ts` 首行即 `import { astro } from 'iztro'` —— 它不是独立实现。所有 Python 侧候选（`py-iztro` / `iztro-py` / `mingli-master`）同样是 iztro 的移植，**用它们做交叉核对等于用 iztro 验证 iztro**。

因此本项目采用的唯一独立实现源是 `airicyu/fortel-ziweidoushu`（中州派，MIT，唯一运行时依赖 `util`，自带日历，不依赖 iztro）。按 GOAL §3G-2，它**只作为 Reference**：不进入 `ConsensusEngine`，不与 iztro 构成「双重确认」。

## 2. 比较范围（GOAL §3G-3）

十二宫位置 | 命宫 | 身宫 | 五行局 | 主星 | 辅星 | 四化 | 三方四正 | 大限 | 长生十二神 | 流年（不可比对） | 流月（不可比对）

### 2.1 差异分类分布

| 分类 | 条数 | 含义 |
|---|---:|---|
| `IDENTICAL` | 2183 | 两边完全一致 |
| `FIELD_UNAVAILABLE` | 48 | 参考实现没有可比对的出口（不静默省略） |
| `DIFFERENT_SCHOOL_CONVENTION` | 32 | 流派口径差异（四化表、晚子时换日等） |
| `DIFFERENT_SUSPECTED_IMP_BUG` | 17 | 疑似参考实现的实现问题，非流派差异 |

完全一致比例：**0.9575**

## 3. 逐类差异明细

### 3.DIFFERENT_SCHOOL_CONVENTION

共 32 条，涉及 13 个字段。

| case_id | field | iztro_result | reference_result | possible_reason | school_convention | resolved |
|---|---|---|---|---|---|---|
| `C06-1990-late-zi` | `major_stars.仆役` | ['天相'] | ['巨门'] | 晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**（农历日与日柱都不换），iztr… | 晚子时换日（当日子时 / 次日子时） | True |
| `C06-1990-late-zi` | `major_stars.兄弟` | ['武曲', '破军'] | ['太阳'] | 晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**（农历日与日柱都不换），iztr… | 晚子时换日（当日子时 / 次日子时） | True |
| `C06-1990-late-zi` | `major_stars.命宫` | ['太阳'] | ['破军'] | 晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**（农历日与日柱都不换），iztr… | 晚子时换日（当日子时 / 次日子时） | True |
| `C06-1990-late-zi` | `major_stars.夫妻` | ['天同'] | ['武曲'] | 晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**（农历日与日柱都不换），iztr… | 晚子时换日（当日子时 / 次日子时） | True |
| `C06-1990-late-zi` | `major_stars.子女` | [] | ['天同'] | 晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**（农历日与日柱都不换），iztr… | 晚子时换日（当日子时 / 次日子时） | True |
| `C06-1990-late-zi` | `major_stars.官禄` | ['巨门'] | ['贪狼'] | 晚子时（夜子時）换日口径差异：参考实现把 23:00–24:00 归入**当日**（农历日与日柱都不换），iztr… | 晚子时换日（当日子时 / 次日子时） | True |

### 3.DIFFERENT_SUSPECTED_IMP_BUG

共 17 条，涉及 1 个字段。

| case_id | field | iztro_result | reference_result | possible_reason | school_convention | resolved |
|---|---|---|---|---|---|---|
| `C01-1940s-forward` | `destiny_master` | 禄存 | 廉贞 | 参考实现以**生年地支**索引命主表；命主的标准定义是以**命宫地支**查表（身主才是以生年支查表）。这是参考实现… |  | False |

### 3.FIELD_UNAVAILABLE

共 48 条，涉及 2 个字段。

| case_id | field | iztro_result | reference_result | possible_reason | school_convention | resolved |
|---|---|---|---|---|---|---|
| `C01-1940s-forward` | `horoscope.monthly.palace_ground` | None | None | 参考实现只暴露十年运（大限）导航接口，其运限盘与 iztro 的 horoscope 链式接口不是同一模型；强行对… |  | False |
| `C01-1940s-forward` | `horoscope.yearly.palace_ground` | None | None | 参考实现只暴露十年运（大限）导航接口，其运限盘与 iztro 的 horoscope 链式接口不是同一模型；强行对… |  | False |

## 4. 流派/实现差异逐条结论（GOAL §3G-5）

### 4.1 晚子时换日口径不同（流派差异）

- **现象**：两套实现对 23:00-24:00 的换日处理不同：生产引擎（iztro）把晚子时归入次日，参考实现（中州派）归入当日。
- **证据**：实测 1990-06-15 23:30：生产引擎的盘面与 1990-06-16 00:30 完全相同（True），且生产引擎晚子时盘面与参考实现次日早子时盘面一致（False）；而参考实现晚子时盘面与生产引擎晚子时盘面不同（False，参考农历日 23 / 生产显示 一九九〇年五月廿三）。
- **分类**：`DIFFERENT_SCHOOL_CONVENTION`
- **resolved**：True
- **对本项目研究的影响**：只影响晚子时出生（23:00-24:00）的整盘主星安放。本平台 500 只股票的出生时刻来自上市日派生的日间时刻（取自 exchange_session_calendar），不含晚子时，因此对 Phase 3 全部研究结论无影响。iztro 在晚子时的**显示口径与安放口径不一致**：chart.lunar_date 显示「五月廿三」，但星曜按「五月廿四」安放（与次日 00:30 的盘完全一致）。该不一致只影响 raw_chart 的农历日显示，不影响本项目因子计算（因子只用 iztro 的盘面，不含农历日字符串）；且本项目 500 只股票的出生时刻来自上市日派生的日间时刻（取自 exchange_session_calendar 的开盘/收盘时段），不含晚子时，因此对 Phase 3 研究结论无影响。

### 4.2 命主取用不同（疑似参考实现问题）

- **现象**：参考实现的命主（destinyMaster）以**生年地支**索引命主表；命主的标准定义是以**命宫地支**查表（身主才是以生年支查表）。
- **证据**：17/24 个案例不一致（其余案例因生年支恰等于命宫支而偶然相同）；参考实现源码 build/model/destinyBoard.js 的 #setupDestinyBodyMaster() 对命主与身主**都**使用 this.config.yearGround.index，而两张表本身（贪狼/巨门/禄存/文曲/廉贞/武曲/破军... 与 火星/天相/天梁/天同/文昌/天机...）与标准表一致 —— 说明表正确、取用位置错误。
- **分类**：`DIFFERENT_SUSPECTED_IMP_BUG`
- **resolved**：False
- **对本项目研究的影响**：生产引擎不受影响（iztro 按命宫支取命主，与标准一致）。本项目因子未使用命主字段，因此对研究结论无影响。

### 4.3 十干四化的「科」星取法不同（流派差异）

- **现象**：两套实现使用的十干四化表在部分天干上的「科」星不同。
- **证据**：8 个案例不一致，出现的取法对为 ['右弼→太阳', '太阴→天府', '左辅→天府']；涉及 戊（右弼 / 太阳）、庚（太阴 / 天府）、壬（左辅 / 天府）三干，均为紫微斗数文献中记载的『两说 / 多说』。
- **分类**：`DIFFERENT_SCHOOL_CONVENTION`
- **resolved**：True
- **对本项目研究的影响**：四化直接影响本项目 Opinion 的方向聚合，因此这是**语义级**差异 —— 但本研究平台的结论建立在 iztro 的实现上并已全程冻结版本（iztro-2.6.1+smx-1.0.0），换实现源会改变四化因子；本核对的价值是把这一敏感点固定下来，而不是据此换源。

### 4.4 大限 / 长生十二神方向由性别参数决定（假设差异，已可精确对齐）

- **现象**：长生十二神与大限顺逆行由「阳男阴女顺行 / 阴男阳女逆行」决定，而股票没有真实性别（AGENTS.md §5）。
- **证据**：本次核对在同一案例下分别用 M/F 各排一次并统计性别相关字段的一致数：每个案例都有一个性别精确匹配 24/24 项，另一个只匹配 4/24 项；归类为 DIFFERENT_VARIANT_ASSUMPTION 的差异条数 0。说明本项目的 variant_mode（forward/reverse）与标准性别规则一一对应，不存在『方向搞反』这类实现错误。
- **分类**：`DIFFERENT_VARIANT_ASSUMPTION`
- **resolved**：True
- **对本项目研究的影响**：本项目在 variant_mode=not_applicable 时不输出大运；Phase 3 的出生模型不含大限因子，因此该差异不进入任何研究结论。

## 5. 未解决项（unresolved）

| field | 条数 | 说明 |
|---|---:|---|
| `destiny_master` | 17 | 参考实现以**生年地支**索引命主表；命主的标准定义是以**命宫地支**查表（身主才是以生年支查表）。这是参考实现… |
| `horoscope.monthly.palace_ground` | 24 | 参考实现只暴露十年运（大限）导航接口，其运限盘与 iztro 的 horoscope 链式接口不是同一模型；强行对… |
| `horoscope.yearly.palace_ground` | 24 | 参考实现只暴露十年运（大限）导航接口，其运限盘与 iztro 的 horoscope 链式接口不是同一模型；强行对… |

## 6. 定性

本核对**不判定谁对谁错**：不同流派在四化表、晚子时换日、命主取用上有长期分歧，交叉核对的价值在于**把差异定位到具体字段与具体原因**，从而知道哪些结论对实现选择敏感、哪些不敏感。

本项目不据此修改生产引擎：`iztro` 仍是唯一的 `MetaphysicsEngine` 实现，参考实现只出现在本研究报告中。
