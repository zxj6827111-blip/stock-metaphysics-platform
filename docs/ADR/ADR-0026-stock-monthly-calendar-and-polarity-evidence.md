# ADR-0026：股票月份日历与首日阴阳证据闭环

- Status: 已接受(Accepted)
- Date: 2026-09-28
- Supersedes: None
- Related: ADR-0017, ADR-0018, ADR-0019, ADR-0020, ADR-0022

## Context

现有股票十神日历与 Fortune v2 时间轴分别解析出生档案；首日阴阳只存为 `stock_master` 的裸字段，缺少该字段自己的来源版本、观测日、交易日证据和可见时点。现有页面也没有把精确节气月段、每日十神/藏干和大运依据一起呈现。

同一用户查询必须使用同一个明确出生档案。`listing_open` 是上市开盘时刻的研究假设，不能描述为首笔成交；`MARKET_FIRST_TRADE` 缺证时不得回退到上市日期。日柱、月柱及十神仍按已有 Calendar/Bazi/Ten-God 内核计算，前端只消费结构化响应。

## Decision

1. 新增版本化 `/api/v2/research/fortune/month-calendar`，并保持 `/api/v1/**` 与现有 v2 时间轴语义不变。该响应同时返回自然日十神日历、精确节气月段、Fortune 日历关系事件、统一出生档案、首日阴阳证据、实际运限状态和各子结果的可用性/原因。
2. `listing_open` 与 `MARKET_FIRST_TRADE` 由请求显式选择。`listing_open` 复用已存的 `stock_birth_profile` 行；`MARKET_FIRST_TRADE` 只复用行情 Adapter 的已观测数据，日线最早观测日期必须与可核实上市交易日期一致，否则该出生口径不可用。两套算法在同一请求中共享转换后的单一出生档案。
3. 将首日阴阳来源证据单独存入 `stock_master.first_day_evidence_json`。字段级证据包括来源、内容摘要版本、阴阳与涨跌值、观测日期、交易日证据、市场时段版本和收盘可见时刻。冲突值保留并标为不可用；来源缺失不补造。首日阴阳仅在证据声明的收盘可见时刻之后参与运限。
4. `FortuneLuckCycleEvidence.visible_at` 必须与版本化交易时段解析出的当日收盘时刻相符。极性/兼容性别/实际顺逆/运限周期作为独立字段公开；兼容性别只作为传统算法输入假设，不表示股票具有真实性别。
5. 月份展示以自然日为范围，流月严格按现有十二节交节时刻半开切段；每日采样继续使用 `Asia/Shanghai 12:00`，CalendarEngine 原有 23:00 日界不变。公历日期筛选和“仅交易日”是展示维度，不改写术数结果。
6. 月、日十神、藏干、喜忌和结构关系仅作传统结构分类说明，不产生财富评分、收益/上涨断言或交易建议。缺少出生档案、阴阳证据、交易日覆盖或运限引擎时按部分可用语义返回，不阻断其他可计算部分。

## Consequences

- 新 v2 契约和新增 nullable JSON 列需要单独回归及可逆 Alembic migration；旧 API 保持兼容。
- 页面可重放展示算法使用的出生档案、交易日历/市场时段、规则版本与来源证据。
- 历史收益认证范围不限制历法结构计算；它仍由研究数据证书独立控制。
- 本决策仅在实现、回归、真实本地数据和浏览器证据均通过后改为 `已接受(Accepted)`。

## Acceptance evidence

本地实现、2,298 项后端回归、410 项 Golden、41 项 as-of/无未来数据检查，以及基于真实本地股票档案的 4 项 Playwright 用户流程均已通过；详见 [`STOCK-MONTHLY-CALENDAR-POLARITY-ACCEPTANCE-2026-09-28.md`](../research/STOCK-MONTHLY-CALENDAR-POLARITY-ACCEPTANCE-2026-09-28.md)。PR #8 的本轮 CI 需在最终提交推送后单独核验。
