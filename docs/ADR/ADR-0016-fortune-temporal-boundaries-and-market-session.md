# ADR-0016：Fortune 历法边界与市场时段分层

- **状态**：已接受（F1 Golden Cases + backend CI）
- **日期**：2026-09-25
- **影响**：Fortune 时间上下文、CalendarEngine Adapter、交易择时数据
- **关联**：[ADR-0001](ADR-0001-adapter-isolation.md)、[ADR-0004](ADR-0004-as-of-time-isolation.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)

## 背景

当前 `CalendarEngine` 已输出一个时刻的年、月、日、时四柱及节气信息。Fortune 若让每个下游模块分别计算时间柱，会造成同一时刻结果不一致。A 股午间休市同时说明传统时辰与市场可交易性不能共用一个布尔值：午休仍属于传统午时，但没有市场交易 session。

## 提案

1. `TemporalFortuneContext` 持有一个 `CalendarSnapshot`；构造器将带时区输入转换为配置的本地时区，并且只调用一次 CalendarSnapshotProvider。流年/月/日/时全部复用该对象。
2. 年柱边界沿用 CalendarEngine 的立春 exact 口径；月柱边界沿用节气 exact 口径。自然公历年/月只可用于展示，不替代流年/流月。
3. Fortune 当前日柱和时柱沿用 CalendarEngine exact 行为，不另加早子/晚子切换。当前实现 23:00 精确日界必须由 Golden Cases 固定后再接受该选择。
4. `MarketSessionAdapter` 独立分类 `CONTINUOUS_TRADING/BREAK/CLOSED/UNKNOWN` 与 `tradable`。A 股常规窗口使用左闭右开上午/下午两个交易区间，午间休市显式 `BREAK`；传统时辰只从 CalendarSnapshot 读取。
5. 周末/非交易日的自然历法照算；市场时段为 `tradable=false`。缺少交易日历证据时，常规时段内返回 `UNKNOWN/null`，不猜测开市。

## 后果

- 正面：所有时间规则有单一来源；可以同时报告“午时”和“市场休市”；未来港股、美股和期货可添加各自 session adapter。
- 代价：调用方需要为 market-session 提供交易日状态；“自然日可排盘”不会自动给出“可交易”。
- 不改 `/research/date-scan`、现有 CalendarEngine 口径、API 或数据库。

## 接受门槛

接受证据：`tests/golden/test_fortune_temporal_boundaries.py` 的立春、惊蛰 exact-minute、22:59/23:00/23:01/次日 00:00，以及 10 个 A 股传统时辰/市场 session 组合均通过 PR #7 backend core CI；backend core 全套为 2119 passed、20 skipped、28 deselected。CalendarEngine 的当前 exact 日柱选择已锁定；未增加第二套早子/晚子算法。
