# ADR-0017：Fortune 极性、大运方向与兼容参数分离

- **状态**：已接受(Accepted)
- **日期**：2026-09-25
- **影响**：Fortune 出生档案、大运方向研究结果、传统排运 Adapter
- **关联**：[ADR-0003](ADR-0003-no-gender-variant-mode.md)、[ADR-0010](ADR-0010-ziwei-no-gender-variant.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)

## 背景

股票没有真实性别。ADR-0003 要求缺少显式方向依据时默认 `not_applicable`，不能为股票填入男命或女命。候选 ADR-0014 提供了 `first_day_yinyang` 映射：阳映射到 male compatibility input，阴映射到 female compatibility input；传统顺逆仍由该输入与出生年干阴阳共同决定。

这条映射可确定性重放、可以单独版本化，也不需要用收益表现挑选方向。它是一项项目研究约定，不是传统八字对股票实体的 canonical doctrine。

## 决策

1. 本项目定义 `stock-luck-cycle-first-day-yinyang-v1` 研究约定。英文表述为：**This is a project research convention for stock entities. It is not asserted as a canonical traditional Bazi doctrine.**
2. 输入必须是带来源与来源版本的 `first_day_yinyang`。`阳` 映射为 `FortunePolarity.YANG` 与 `CompatibilityGender.MALE`；`阴` 映射为 `FortunePolarity.YIN` 与 `CompatibilityGender.FEMALE`。兼容 gender 只供传统算法 Adapter 使用，不是股票属性。
3. 实际方向依 ADR-0014 候选的原映射计算：出生年干与首日阴阳同极性时 `FORWARD`，异极性时 `REVERSE`。代码不得把兼容输入 `VariantMode` 直接当作实际 `LuckCycleDirection`。
4. 首日阴阳的观测日期与 Fortune `first_trade_date` 分开传入，且必须有显式交易日证据、source/source version 与 market-session version。resolver 记录指定观测日的 session close 为 `polarity_observed_at`；`as_of` 早于收盘时返回 `UNAVAILABLE`，不生成 polarity 或方向。
5. 缺少有效阴阳、观测日期/交易日证据、来源版本、session 版本、受支持的交易所/session 或出生年干时 fail closed。重复相同输入必须得到相同结果。
6. 规则只读取显式的 `first_day_yinyang`、出生年干与其来源/时间元数据。resolver 不读取后续价格或收益序列，也不依据历史收益表现选择顺逆。
7. polarity、实际方向、兼容输入、assumptions、来源、观测时点、session 版本及 `rule_version` 分开记录。该约定不自动把大运加入正式财富因子，不改变规则分数或金融研究结论。
8. 该规则只在显式调用研究约定时启用。项目原有 `variant_mode=not_applicable` 默认、不可用语义及现有 API 行为继续由 ADR-0003/公开 API 契约约束。
9. 如需改变首日阴阳映射、年干比较方法或观测可用时点，必须创建新规则版本并保留旧版本可回放；不得通过覆盖历史结果迁移。

## 后果

- 股票仍没有被赋予真实性别；legacy gender 参数只作为第三方排运算法的兼容输入。
- 研究输出可明确显示 polarity proxy 与真实方向规则，并能按版本复算。
- 首日阴阳在首日收盘前不可用；缺字段或来源无法验证时不产生大运方向。
- 多模型共识、传统规则方向、历史统计关系与未来收益仍是不同概念，符合 ADR-0013。

## 接受依据

代码、阴阳与年干组合 Golden Cases、缺失/收盘前 fail-closed 测试及 PR #7 的实现 commit `fee90843ba9b1a0826cc9da096802b8f83523c21` 均已通过 CI run [36154464013](https://github.com/zxj6827111-blip/stock-metaphysics-platform/actions/runs/36154464013)。Backend 全量套件为 2144 passed、20 skipped、28 deselected；Ziwei engine/factor/golden/cross-engine 套件为 331 passed。PR 同 run 的前端 typecheck、build 和 seeded E2E（7 passed）也全部通过。故本 ADR 状态更新为 `已接受(Accepted)`；它冻结的是项目研究约定，不将其表述为传统命理对股票的 canonical doctrine。
