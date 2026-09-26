# ADR-0018：Fortune 首笔观测、出生时间推定与时间输入精度

- **状态**：已接受(Accepted)
- **日期**：2026-09-25
- **影响**：Fortune First Trade Provider、出生档案解析、Fortune 时间上下文
- **关联**：[ADR-0004](ADR-0004-as-of-time-isolation.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0015](ADR-0015-stock-fortune-birth-basis-and-precision.md)、[ADR-0016](ADR-0016-fortune-temporal-boundaries-and-market-session.md)

## 背景

当前行情仓库提供日线，但没有 tick、trade 或分钟 bar。日线可证明某个日期有行情记录，不能证明当日首笔成交时刻。Fortune 需要表达观测日期、推定出生时刻、真实 intraday 观测与不可用状态，避免把 session 开盘伪装成实际成交。F1 ADR-0015 的上市日期来源选择现被新证据契约取代；其“观察、推定与真实时刻不可混淆”的目标继续保留。

时间输入也需要区分明确时刻、交易日场景下的 market-session anchor，以及没有市场语境的 civil date-only。CalendarEngine 的 23:00 日界和 Date Scan 的 12:00 采样分别属于既有契约。

## 决策

### First Trade 与出生时刻

1. 行情层通过 `FirstTradeProvider` 返回 `FirstTradeObservation`；该端口只报告可观察证据，不在行情 Adapter 中推定出生时刻。
2. 观测状态区分 `VERIFIED_DATETIME`、`OBSERVED_TRADING_DATE`、`UNAVAILABLE`。tick/trade 可报告实时时刻，minute bar 以 `MINUTE_BAR` 标明分钟精度，daily bar 只报告 `first_trade_date`。
3. 日线日期定义为 `min(bar.trade_date)`，语义为 `earliest_observed_trading_date`。它不表示历史行情覆盖完整，也不等于真实首笔成交时间。
4. Fortune birth resolver 可将 `OBSERVED_TRADING_DATE` 与适用于该交易所、该日期且已版本化的 market-session 开盘时间组合，生成 `birth_datetime_status=INFERRED` 的计算时刻。`first_trade_datetime` 始终为 null；来源、来源版本、first_trade_date、timezone、session/config 版本、推定原因和 assumptions 必须保留。
5. 找不到可靠交易日时返回 `UNAVAILABLE`，不使用 listing/IPO 元数据、当前日期、任意日期或 00:00 回填。存在可靠日期但无法证明适用 session/版本时保留 `DATE_ONLY`，不生成 timestamp。
6. inference policy 版本与 session/config 版本分别保存。更改日线证据选择或开盘锚定方式必须升级相应 rule/profile version，旧结果按存储的输入、来源与版本保持可回放。

### Fortune 时间输入

7. `EXACT_DATETIME` 必须是带时区 datetime，直接复用现有 CalendarEngine 行为；CalendarEngine 的 23:00 日界保持不变。
8. `MARKET_SESSION_DATE` 必须显式提供交易所与交易日证据，并记录 market-session policy/config 版本。resolver 从 session 配置取开盘时刻并标记 `MARKET_SESSION_INFERRED`，不可标为 exact。
9. `CIVIL_DATE_ONLY` 不补 00:00、09:30 或 12:00，返回 `TIME_REQUIRED` 且不构造 CalendarSnapshot，因为纯日期在 23:00 换日规则下不能表示唯一全天四柱。
10. Date Relation Scan 与 Ten God Date Scan 继续使用既有 `12:00:00` 业务采样；Fortune 的三种 temporal input 不复用或更改该采样规则。
11. 本决策不修改 CalendarEngine、现有 `/api/v1/**` 或数据库 Schema，因此不要求公开 API 版本迁移或 Alembic revision。

## 后果

- 当前日线 Adapter 可以提供正式的 observed date 路径；09:30 作为计算时间会明确输出为推定值，而不是首笔成交事实。
- 未来接入 tick、trade 或分钟 bar 时可以增加 VERIFIED provider，而不改变日线语义。
- 无可靠数据和无 session 版本会显式降级为 `UNAVAILABLE` 或 `DATE_ONLY`，不发生精度伪造。
- 调用方需要带上 source、version、交易日证据和 temporal input kind；研究回放可以识别每个推定边界。

## 接受依据

FirstTrade/Birth provider 契约测试、时间边界及 Session/Civil Date Golden Cases、相关后端回归与 PR #7 的实现 commit `fee90843ba9b1a0826cc9da096802b8f83523c21` 均已通过 CI run [36154464013](https://github.com/zxj6827111-blip/stock-metaphysics-platform/actions/runs/36154464013)。Backend 全量套件为 2144 passed、20 skipped、28 deselected；Ziwei engine/factor/golden/cross-engine 套件为 331 passed；前端 typecheck、build 与 seeded E2E（7 passed）也全部通过。该 run 对应实现代码 commit；后续文档验收 commit 的 workflow 结果仍由 PR #7 追踪。
