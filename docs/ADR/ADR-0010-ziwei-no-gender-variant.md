# ADR-0010：紫微的「无性别」处理 —— 方向 variant 而非性别默认

- **状态**：已接受（Phase 2A）
- **日期**：2026-09-19
- **影响**：紫微引擎、紫微因子、变体对比研究、UI
- **关联**：[ADR-0003](ADR-0003-no-gender-variant-mode.md)、[ADR-0009](ADR-0009-ziwei-engine-iztro.md)

## 背景

`AGENTS.md` §5 / [ADR-0003](ADR-0003-no-gender-variant-mode.md) 已确立：**股票没有真实性别**，
禁止为了"功能完整"而默认填男命或女命。

紫微斗数的 `iztro.astro.bySolar()` **强制要求性别参数**。若直接传 `'男'`：

* 会得到一个"看起来完整"的盘；
* 但其中的大限/小限顺逆是**无依据的**；
* 更糟的是，用户会把"基于男命假设的大限"当成真实结论。

这是 ADR-0003 明确禁止的伪精确。

## 关键事实（实测，非推测）

对 2001-08-27 巳时（辛巳年，阴年）分别以男命/女命排盘并**逐字段 diff**，
得到 variant 影响的**完整清单**：

| 字段 | 是否随 variant 变化 |
|---|---|
| 十二宫宫名 / 宫干支 / 命宫 / 身宫 | ❌ 不变 |
| 十四主星 / 辅星 / 煞曜 / 杂曜位置 | ❌ 不变 |
| 生年四化（禄权科忌落宫） | ❌ 不变 |
| 三方四正 | ❌ 不变 |
| 流年 / 流月 / 流日 / 流时（宫名、星曜、四化） | ❌ 不变 |
| **大限年龄区间（`decadalRange`）** | ✅ **变** |
| **小限年龄（`ages`）** | ✅ **变** |
| **长生十二神（`changsheng12`）** | ✅ **变** |
| **博士十二神（`boshi12`）** | ✅ **变** |
| **运限层 `decadal` / `age`（宫位、干支、四化、星曜）** | ✅ **变** |

**结论：性别参数在紫微中只决定"顺行 / 逆行"这一个自由度。**

## 决策

把自由度**直接暴露为方向**，而不是伪装成性别：

| `VariantMode` | 语义 | 实现方式（审计字段 `gender_parameter`） |
|---|---|---|
| `forward` | 强制**顺行** | 阳年 → `男`；阴年 → `女` |
| `reverse` | 强制**逆行** | 阳年 → `女`；阴年 → `男` |
| `both` | 分别计算两者 | 编排层调用两次，**分别落库** |
| `not_applicable` | **拒绝排盘** | 抛 `ZiweiUnavailableError` |

具体规则：

1. `variant_mode` 默认 `not_applicable`；该模式下**紫微引擎拒绝排盘**，
   输出 `available: false, score: null`，与 Phase 1 的紫微语义一致（不以 0 分参与聚合）。
2. 只有显式传入 `forward` / `reverse` / `both` 才会排盘。
3. `variant_basis` 必须写明"股票无真实性别，此为方向变体假设"，
   同时写入 `assumptions`（键 `ziwei.variant_mode`）。
4. `gender_parameter` **必须保存**，但它的语义是"实现该方向所借用的规则参数"，
   **不是**"这只股票是男性/女性"。UI 与报告中的措辞必须是：
   「顺行假设（Variant A）」/「逆行假设（Variant B）」。
5. `both` 模式下**不得先平均盘面**；两套 `raw_chart` 分别落 `chart_artifact`。
6. 历史研究**必须分别回测两个 variant**，并如实输出谁更稳定；数据不足时
   `ResearchStatus = INCONCLUSIVE`。

## 为什么不是「默认男命 + 标注」

| 方案 | 问题 |
|---|---|
| 默认男命，UI 标注"假设为男" | 用户仍会看到一份**完整的大限盘**，"假设"提示无法阻止误读；违反 ADR-0003 |
| 默认女命 | 同上 |
| **方向 variant（本决策）** | 不再声称任何性别归属；变异来源被准确命名；两个 variant 可独立回测 |
| 两种都算并平均 | 违反"禁止用平均值掩盖分歧"（`AGENTS.md` §2.4） |

## 重要限制（必须写进研究结论）

> 由于 variant 只影响**大限/小限顺逆与长生十二神顺逆**，
> 两个 variant **不是两条独立证据**。
> `Variant A 与 Variant B 一致` 不能作为"双重确认"，
> 因为它们共享全部十二宫、全部星曜、全部四化与全部流年流月流日。

这一点写入 `docs/ziwei-engine.md`、`docs/model-limitations.md` 与紫微因子的 `research_mapping` 声明。

## 机器校验

`tests/engines/test_ziwei_engine.py`：

```
test_variant_not_applicable_refuses_to_chart     # 拒绝排盘，不返回盘面
test_variant_forward_and_reverse_differ_only_in_direction_fields
test_gender_parameter_is_recorded_for_audit
test_assumption_ziwei_variant_mode_recorded
test_no_default_gender_anywhere                  # 默认参数不得为 '男'/'女'
```

## 相关

- [`AGENTS.md`](../../AGENTS.md) §5
- [`src/engines/ziwei/ziwei_engine.py`](../../src/engines/ziwei/ziwei_engine.py)
- [`docs/model-limitations.md`](../model-limitations.md)
