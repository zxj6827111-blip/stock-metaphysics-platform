# ADR-0015：Fortune 出生基准与出生时间精度

- **状态**：已接受（F1 CI contract tests）
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

本决策接受的是“缺少实际成交时如何显式推定”的内部契约，不表示交易所开盘时刻等于真实第一笔成交，也不声称现有行情源已覆盖实际 first trade。合同、来源版本、配置版本、精度及 assumption 由 `tests/core/test_fortune_contract.py` 覆盖；现有 birth profile 回归包含在 PR #7 的 backend CI 中。

## 接受门槛

接受证据：Fortune contract tests 检查 INFERRED、source/source_version、confidence、birth_profile_version、rule_version、config_version 与显式 assumptions；PR #7 的 backend core job 对 `-m "not ziwei_live"` 全套执行为 2119 passed、20 skipped、28 deselected。真实首笔成交来源仍未接入，结果必须继续标为 INFERRED。
