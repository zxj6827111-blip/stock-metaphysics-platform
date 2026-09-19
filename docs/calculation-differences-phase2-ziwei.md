# 紫微计算口径差异与固化记录（Phase 2）

> 本文档记录 **iztro 2.6.1 → 本项目 `ZiweiChart`** 的口径决策点。
>
> 与 `docs/calculation-differences-phase1.md` 同等地位：任何口径变化都必须先在此登记，
> 再提升 `ziwei_engine_version`，最后重新生成 Golden 快照。
>
> **不要直接改 Golden 期望值。** 先判断是"第三方升级导致的口径变化"还是"代码 bug"。

---

## D1 · 小限层不携带流曜（`age.stars` 缺失）

| 项 | 值 |
|---|---|
| 现象 | iztro `horoscope().age` **没有 `stars` 字段**，只有 `index / heavenlyStem / earthlyBranch / name / mutagen / palaceNames / nominalAge` |
| 处理 | `ZiweiHoroscopeSection.stars` 对该层返回 `[]`，并在 Schema docstring 中显式声明"已知缺失" |
| **不做的事** | 不用大限层或流年层的星曜去"补全"小限层；不推测小限流曜 |
| 影响 | `Z_AGE_*` 类因子只能使用小限的**宫位 / 干支 / 四化**，不能使用流曜 |
| 下游约束 | 因子层遇到 `stars == []` 必须走 `_unavailable(...)`，不得把"空数组"当成"该宫无煞" |
| 锁定测试 | `tests/engines/test_ziwei_engine.py::test_horoscope_layers_present_with_12_slots`（对 `age` 层单独断言 `stars == []`） |

**为什么这是一条重要记录**：如果未来有人"顺手"把小限流曜补上，很可能引入一套
来源不明的规则，导致同一只股票在不同版本算出不同的小限结论。

---

## D2 · 晚子时归属：23:00–24:00 计入 `timeIndex = 12`

| 项 | 值 |
|---|---|
| 本项目口径 | 23:00:00–23:59:59 → `timeIndex = 12`（晚子时），**不并入次日子时** |
| 与八字引擎的关系 | `CalendarEngine` 采用 `setSect(1)`（23:00 后时柱归次日）——这是**历法**口径；紫微的 `timeIndex` 是**时辰编号**口径，两者不冲突但必须都显式 |
| 影响 | 23 点后出生（或流时落在 23 点）的命宫位置可能与其他流派相差一日 |
| 写入 | `assumptions` 键 `ziwei.time_index_sect` |
| 锁定测试 | `TestTimeIndexMapping::test_late_zishi_is_index_12_not_next_day` |

---

## D3 · 闰月口径：显式固定 `fixLeap = true`

| 项 | 值 |
|---|---|
| 本项目口径 | 显式传 `fixLeap=true`（不使用库默认值，避免随版本漂移） |
| 影响 | 闰月出生者的月支归属；闰月前后出生时刻的命宫位置可能与其他流派不同 |
| 写入 | `assumptions` 键 `ziwei.fix_leap` |
| 配置 | `SMP_ZIWEI_FIX_LEAP`（默认 `true`） |

---

## D4 · variant（顺行/逆行）影响范围的**完整清单**

这是 ADR-0010 的实测依据。对同一出生时刻分别以顺行/逆行排盘并**逐字段 diff**：

| 字段 | 是否随 variant 变化 |
|---|---|
| 十二宫宫名 / 宫干支 / 命宫 / 身宫 | ❌ 不变 |
| 十四主星 / 辅星 / 煞曜 / 杂曜位置 | ❌ 不变 |
| 生年四化（禄权科忌落宫） | ❌ 不变 |
| 三方四正 | ❌ 不变 |
| 流年 / 流月 / 流日 / 流时（宫名、星曜、四化） | ❌ 不变 |
| 大限年龄区间 `decadalRange` | ✅ 变 |
| 小限年龄 `ages` | ✅ 变 |
| 长生十二神 `changsheng12` | ✅ 变 |
| 博士十二神 `boshi12` | ✅ 变 |
| 运限层 `decadal` / `age` 的宫位、干支、四化、星曜 | ✅ 变 |

**由此推出两条硬约束**（写入 `assumptions` 与研究报告）：

1. 两个 variant **不是两条独立证据**，它们共享全部十二宫、全部星曜、全部四化、
   全部流年流月流日；`Variant A 与 Variant B 一致` **不能**当作"双重确认"；
2. 只有 `Z_DECADE_*` / `Z_AGE_*` / 长生十二神相关因子应当在两个 variant 之间产生差异；
   如果发现其他因子也跟着变，说明实现有 bug。

锁定测试：`TestVariantSemantics::test_forward_and_reverse_differ_only_in_direction_fields`。

---

## D5 · 宫干环回不是 +1（12 宫 vs 10 天干）

| 项 | 值 |
|---|---|
| 现象 | 宫干自寅宫起按五虎遁顺行，但 12 宫只有 10 天干，**绕回寅宫时差为 −1 而非 +1** |
| 正确结构 | `stems[i] == stems[0] + i (mod 10)`，对全部 12 宫成立 |
| 曾经写错的断言 | "相邻宫天干差恒为 1（含环回）" —— Golden Case 已捕获并纠正 |
| 锁定测试 | `test_palace_stems_follow_five_tiger_rule` |

**教训**：紫微中"12 宫 / 10 天干 / 12 地支"的不同步是固有性质，
凡是"环形恒等式"都要先验证环回项。

---

## D6 · 起运岁数 = 五行局数，命宫恒持第一个大限

| 项 | 值 |
|---|---|
| 结构 | 水二局 → 2 岁起运，木三局 → 3 岁，金四局 → 4 岁，土五局 → 5 岁，火六局 → 6 岁 |
| 结构 | 命宫**恒为**第一个大限所在宫（`decadal_range[0]` 最小） |
| 结构 | 12 段大限各 10 年，年龄覆盖连续、不重叠 |
| 顺逆判据 | 第二个大限在 `命宫+1` → 顺行；在 `命宫−1` → 逆行 |
| 锁定测试 | `test_decadal_start_age_matches_five_elements_class`、`test_decadal_ranges_are_contiguous_and_non_overlapping`、`test_direction_of_decadals_is_consistent_with_variant` |

---

## D7 · 本服务与"第二实现源"的关系

当前**没有**使用 Tianji 或其他紫微实现做 cross-check：

* Phase 2 未引入第二实现源（Tianji 许可证未核实，见 `THIRD_PARTY.md` §1.6）；
* 因此本版本的紫微结论**没有独立交叉验证**，只有结构性不变量与快照锁定；
* 这一点写入 `docs/model-limitations.md`。

> **Cross-check ≠ Truth**。将来若引入第二实现，两者不一致时必须记录为
> `calculation_diff` 并如实并列，**不得静默择一**。

---

## 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-19 | `iztro-2.6.1+smx-1.0.0` | 初始固化：D1–D7 |
