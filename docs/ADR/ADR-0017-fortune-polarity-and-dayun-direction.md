# ADR-0017：Fortune 极性、大运方向与兼容参数分离

- **状态**：Draft
- **日期**：2026-09-25
- **影响**：Fortune 出生档案、大运结果、未来研究变体
- **关联**：[ADR-0003](ADR-0003-no-gender-variant-mode.md)、[ADR-0010](ADR-0010-ziwei-no-gender-variant.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)

## 背景

股票没有真实性别。主干 ADR-0003 将大运设为默认不可用、显式 variant 才计算。当前 BaziEngine 把 `forward/reverse` 映射成 `lunar-python.getYun(gender)` 的参数，而该第三方算法还结合出生年干阴阳计算实际顺逆。因此 `VariantMode` 的名字不能证明 Fortune 的实际 `LuckCycleDirection`。

另有远端候选提交 `ad4594a89615d79fc4ec4835d0bb6b730d58a688` 包含 ADR-0014，提议使用首日涨跌阴阳选择传统算法兼容参数；它不在当前主干中，不能作为正式规则。本 ADR 不复述或接受其业务映射。

## 提案

1. Fortune 分别保存 `FortunePolarity`、`LuckCycleDirection`、`CompatibilityGender`；后者仅为传统库 Adapter 的输入参数，不表示股票性别。
2. 未选择并验证 Fortune 方向规则时，方向为 `UNAVAILABLE/null`，默认不输出大运。与 ADR-0003 一致，不根据缺失值默认男/女，不用 0 或其他值冒充可用。
3. 首日涨跌标记可以是带来源、版本的候选研究极性；不得静默转成实际顺逆方向，也不得将大运加入正式财富因子。
4. 任何未来方向规则必须独立版本化、把依据写入 assumptions、与底层兼容输入分别输出，并预注册比较顺逆假设的研究协议。

## 未决事项

- `FortunePolarity` 的正式来源及其与出生年干阴阳的关系尚未决定。
- 是否接受首日涨跌作为一个可回测的显式排运假设，需要独立方法论决策；它不能被描述为真实性别。
- 现有第三方 API 的性别参数与方向输出必须逐案例确认，不能从参数名字推导方向。

## 接受门槛

在主干形成单独的规则 ADR；提供顺/逆/兼容输入的黄金案例与缺失值测试；完成双变体预注册回测并保留全部负结果；未完成前保持 Draft、Fortune 大运不可用。
