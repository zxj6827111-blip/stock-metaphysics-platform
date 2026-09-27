# 计算口径差异登记 · Phase 1.1

> 记录验收过程中确认的**口径差异**与**修复**。 Golden Case 失败时先看这里。
>
> 规则（AGENTS.md §12）：口径变化 → 记录本文档 → 提升 engine_version → 全量回归。

---

## D1. 纳音与干支口径错配（lunar-python）— **已修复（CalendarEngine 侧）**

| 项 | 值 |
|---|---|
| 发现于 | Phase 1.1 四柱对拍（`tests/golden/test_bazi_cross_validation.py`） |
| 现象 | `lunar.getYearInGanZhiExact()` 与 `lunar.getYearNaYin()` 在立春当日不是同一口径；如 2024-02-04 20:00 年柱=**甲辰**、但 `getYearNaYin()` 返回**金箔金**（=癸卯的纳音），内部矛盾。月柱同类问题（乙丑柱配了"炉中火"） |
| 根因 | lunar-python 的纳音接口走的不是"精确节气"换柱口径，且各方法之间不自洽 |
| 修复 | 纳音改为本项目自持的**六十甲子纳音表**（`src/core/constants.py::NAYIN_OF`），从干支文本直接查表——柱与纳音永不再可能不一致 |
| 版本 | `calendar_engine_version` 不变（纳音只是换实现源，对外字段值不变；回归见下） |
| 回归 | `tests/golden/` 129 项全过（其中对拍 46 项） |

## D2. 晚子时归次日（sect）— **有意为之的流派选择，已自洽对齐**

| 项 | 值 |
|---|---|
| 现象 | 23:00–23:59 的日柱：lunar-python 默认 `sect=2`（仍算当日），本项目用 `sect=1`（归次日，子平通行口径） |
| 判定 | **两口径均合法**，属流派差异；本项目显式选 sect=1 并在引擎文档注明 |
| 处理 | 对拍测试显式 `setSect(1)` 再比较 —— 对齐流派后全量一致 |
| 回归 | `tests/golden/test_bazi_cross_validation.py::TestCrossValidation` 全过 |

## D3. 流年关系因子接线错误（B_YEAR_005/007/008）— **factor_rule_version 提升 v1 → v1.1**

| 项 | 值 |
|---|---|
| 发现于 | Phase 1.1 因子质量审计（相关性 > 0.98 的疑似重复对） |
| 现象 | `B_YEAR_005`（字典定义"流年冲原局"）实际被接到**三合**数据，与 B_YEAR_010 corr=1.0；B_YEAR_007（刑）与 B_YEAR_008（害）错位，且"流年害"从未真实计算 |
| 根因 | `_rel_factors(...)` 位置参数顺序与因子字典声明不一致，且没有测试断言"因子语义=字典语义" |
| 修复 | 显式关键字接线（`clash_id=B_YEAR_005` / `harmony_id=B_YEAR_006` / `punish_id=B_YEAR_007` / `extra_harm_id=B_YEAR_008` / `triple_id=B_YEAR_010`） |
| 版本 | **`factor_rule_version: v1 → v1.1`**；新增回归测试 `tests/factors/test_year_relation_wiring.py` |
| 影响 | 历史已落库的 v1 观测行保留不动（审计追溯需要）；新计算一律 v1.1 语义 |

## D4. 复权口径选择：qfq 被淘汰，改用 hfq（市场快照）

| 项 | 值 |
|---|---|
| 发现于 | Phase 1.1 真实数据导入验收 |
| 现象 | 腾讯前复权（qfq）对长期高股息股票会产生**负价格**（如 600519 在 2016 年前、000001 在 2009 年前后 qfq 为负）——由"累计现金分红从现价里扣减再回头乘"的锚定方式所致，跨零点附近收益比值失真 |
| 处理 | 离线快照统一**后复权（hfq）**：价格恒为正、与累计回报一致；`data/import/_meta.json` 记录 adjust=hfq 与原因 |
| 影响 | 标签/事件研究的收益率口径全部基于 hfq；任何来自其他源的 qfq 输入**不得**与该快照混算（provider 显式拒绝其他 adjust） |
| 落库标记 | `market_bar_daily.source = 'tencent_hfq_import'`、`is_degraded = False` |

## D5. `eight_char` 时间柱换日（晚子时 23:30+）的年柱纳音关联

已并入 D1 —— 换实现源后，时柱纳音同样来自 `NAYIN_OF[干支]`，与干支一定一致。

## D6. 核心历法字段失败关闭与来源版本（W1）

| 项 | 值 |
|---|---|
| 发现于 | 2026-09-27 运行正确性审查 |
| 现象 | 核心农历日期、四柱或节气字段异常时，旧路径可能吞掉错误并以合法外观的 `甲子` 等默认文本继续构造结果；运行状态也无法区分数据库迁移未就绪与服务存活 |
| 修复 | 核心日期、干支与前后节气读取失败时抛 `CalendarCalculationError`；单项分析返回结构化 `ENGINE_UNAVAILABLE`，多模型分析将受影响观点设为 unavailable 并保留其他可用模型；增加 v2 readiness，v1 health 保持兼容 |
| 正常结果 | 通过 Golden Case 对正常日期的盘面值作回归；本修复只改变异常输入/依赖故障的处理，不改正常日期的排盘口径 |
| 版本 | `calendar_engine_version` 提升为 `smx-calendar-1.0.1+lunar-python-1.4.8`；八字结果来源版本字段跟随实际 CalendarEngine，`bazi_engine_version` 提升为 `smx-bazi-native-1.0.1`；合成行情 fallback 默认关闭，`config_version` 提升为 `cfg-2026.09.1` |
| 限制 | Provider 的请求窗口不等于实际数据截止日；未取得实际最大交易日或逐证券认证时，截止日/研究资格仍保持未知或未认证，不据记录数量给高等级 |
| 状态 | 已接受（W1；正常 Golden 数值未变） |

---

## 处理记录

| 日期 | 决策人 | 动作 |
|---|---|---|
| 2026-09-18 | Phase 1.1 验收 | 四项口径全部记录；D3 触发 `factor_rule_version` 提升 |
