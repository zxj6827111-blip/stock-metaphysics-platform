# ADR-0015：Fortune 出生基准与出生时间精度

- **状态**：Draft
- **日期**：2026-09-25
- **影响**：Fortune 内部出生档案、后续八字上下文
- **关联**：[ADR-0003](ADR-0003-no-gender-variant-mode.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)

## 背景

现有 `StockBirthProfile` 使用 `LISTING_OPEN`，先按交易日历定位首个正式交易日，再按交易时段开盘时间形成排盘时间。它没有单独表达“上市日期”和“首笔实际成交时刻”；现有 `FIRST_TRADE` 需要未接入的逐笔数据源。新 Fortune 领域不能把推定开盘写成真实成交事实，也不能改变既有 `/api/v1` 与旧档案语义。

## 提案

1. Fortune 使用并行的 `StockFortuneBirthProfile`，保留 `listing_date` 与 `first_trade_datetime` 两个独立字段。
2. V1 默认出生基准提案为 `MARKET_FIRST_TRADE`。缺少实际成交时间时，只有明确记录假设后才能用配置的首个公开交易日开盘时刻生成 `INFERRED` 的 `birth_datetime`；实际字段 `first_trade_datetime` 仍为 `null`。
3. 时间精度使用 `EXACT`、`INFERRED`、`DATE_ONLY`、`UNKNOWN`。`EXACT/INFERRED` 必须带时区时间；`INFERRED` 必须记录 assumptions；`DATE_ONLY/UNKNOWN` 不制造 timestamp。精度决定后续四柱/三柱/不可用状态。
4. A 股默认开盘时刻从现有 exchange-session 配置解析，不在 Fortune 业务层另写固定 `09:30`。source、source_version、confidence、config_version 和规则版本随档案保存。
5. `COMPANY_FOUNDING`、`CUSTOM`、`UNKNOWN` 作为显式候选基准；公司成立日不从公司名称/行业推断，自定义值标为用户来源。

## 后果

- 正面：真实事实、推定值与仅有日期可以区分；恢复真实首笔成交来源时不必更改字段语义。
- 代价：历史上市日作为首个正式交易日仍是明确研究假设；对早于 session 配置覆盖期的证券，不得宣称开盘时间已被历史规则证明。
- 不改变旧 `StockBirthProfile`、`birth_profile_version`、数据库或公开 API。

## 接受门槛

完成并运行 Fortune contract tests、现有 birth profile tests；证明来源与配置版本被保留、缺失值不被补零，并完成具体行情源覆盖范围审计。接受前保持 Draft。
