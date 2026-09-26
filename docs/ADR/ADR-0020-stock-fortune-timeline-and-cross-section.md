# ADR-0020：Stock Fortune Timeline 与横截面研究契约

- **状态**：Draft
- **日期**：2026-09-26
- **影响**：Stock Fortune V1 F4 typed schemas、Timeline Engine、Cross-Section Scanner、Research API
- **关联**：[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0016](ADR-0016-fortune-temporal-boundaries-and-market-session.md)、[ADR-0017](ADR-0017-fortune-polarity-and-dayun-direction.md)、[ADR-0018](ADR-0018-fortune-first-trade-and-temporal-resolution.md)、[ADR-0019](ADR-0019-stock-fortune-snapshot-contract.md)

## 背景

F3 已冻结单股票、单时点 `StockFortuneSnapshot`。历史重放和日期横截面需要复用该契约，但不能每天复制完整原局，也不能为同一日期的每只股票重复建立 CalendarSnapshot。F4 还需要明确自然日与已验证交易日、流月节气边界、十神层、关系参与者、显式 universe、分页和重放语义。

## 决策

1. 股票时间轴使用 `StockFortuneTimelineRequest` / `StockFortuneTimeline`。`stable_context` 只保存一次 F3 原局、藏干、原局十神、原局关系、大运规则上下文和版本；`points` 只保存每个日期的年/月/日柱、当日十神、大运引用、时间到原局关系、交易日状态与可用性。
2. 时间轴分开支持 `ALL_CALENDAR_DAYS` 与 `TRADING_DAYS_ONLY`。Exact anchor 保留显式本地时刻，默认中午；`MARKET_SESSION_DATE` 只用于交易日模式，并沿用 F2 版本化 session/config 解析。只有 `observed_index_days` 或 `published_exchange_calendar` 能产生非空交易日布尔值；未知覆盖和周末回退不得被当成交易日。
3. 时间轴用最后一个返回日期的一次 F3 Snapshot 建立稳定上下文；若没有返回日期，则用请求结束日的 exact-noon Snapshot 仅建立稳定上下文，不制造 point。大运点位继续服从 `[start_at, end_at)` 和 `polarity_observed_at`，不能把较晚观察到的方向倒灌进更早日期。
4. 年/月/日点位复用 `CalendarEngine`、`ten_god_ref` 与 `StockFortuneEngine._external_relation_events`。流月区间复用既有 `segment_boundaries(..., kind="month")` 的十二节精确边界；公历月仅作为分组信息，不参与推算。日期十神索引基于请求日期集合生成，原局与藏干十神留在稳定上下文。
5. 十神过滤必须指定 `NATAL` / `HIDDEN_STEM` / `ANNUAL` / `MONTHLY` / `DAILY` 层；原局/藏干还必须定位柱位。关系过滤必须精确指定类型、时间来源柱、原局目标柱，并可限定干/支/整柱组件。列表中条件使用 AND。过滤只选择结构，不产生吉凶、收益、概率或推荐语义。
6. 日期横截面使用 `StockFortuneScanRequest` / `StockFortuneScanResponse`，只扫描请求内显式、去重的证券目标，不默认为“全部股票”。响应回显 filters、交易日历证据、universe/request digest、规则版本、总数、limit/offset、确定性排序和警告。调用方负责提供与研究日期相符的点时证券集合；接口会明确警告它不独立证明历史成分股资格。
7. 横截面扫描按股票流式执行一次 F3 Snapshot；同请求日期的 CalendarSnapshot 固定复用，其他出生参考 CalendarSnapshot 使用 128 项 LRU。每只股票仅构造一次稳定原局。排序仅支持 symbol、匹配条件数量、关系事件数量，平局按 symbol 稳定排序。
8. 横截面 `MARKET_SESSION_DATE` 必须由服务器正式交易日历再次确认；未知、回退、休市及未来未覆盖日期均 fail closed。响应及 request digest 记录交易日历来源与内容版本。
9. F4 不增加每日 Snapshot 持久化表。F3 的 chart-artifact 契约继续有效：时间轴写入其 seed Snapshot 的原始盘面；横截面扫描为每只被评估股票保留其 F3 Calendar/Bazi 原始盘面 artifact。已有 Date Relation Scan / Ten God Date Scan 的 API 与输出保持不变；在旧响应的 12:00 anchor、3×3 relation matrix 和既有缓存契约未通过 parity 测试前，不将它们切换到 F4 core。
10. 同一版本化请求必须得到相同结构结果、digest 和 artifact ID。不得读取系统当前日期、行情、收益或其他未来市场数据参与 Fortune 结果。

## 备选方案

- **每天生成完整 F3 Snapshot**：实现简单，但会按日期重复排原局、重复保存字段并放大扫描成本；拒绝。
- **重写现有 Date Scan 接口统一模型**：会把 Date Scan 的 12:00 与其关系矩阵语义迁入新 contract，缺少当前版本 parity 证据；本轮保留旧契约，记录为后续迁移工作。
- **另建缓存基础设施**：会增加跨请求失效和版本治理；F4 的瓶颈可由稳定/变化分层与请求内缓存解决，暂不引入。

## 后果与限制

- Timeline 响应不重复完整原局，但会在请求范围内返回日期点、精确节气月段和 ten-god 日期索引。
- 横截面内存不保留数千个完整 Snapshot；ChartArtifact 仍按 F3 语义落库，反复的大 universe 扫描仍可能产生大量原始盘面行，后续需结合实际请求量决定 artifact 保留策略。
- explicit universe 保证本次输入可回放，不自动保证 PIT 成分股的历史有效性；正式研究必须由调用方提供有来源/版本的点时成员集合。
- F4 结果属于 calendar-derived research context；F5 才能研究这些状态与后续市场结果的统计关系。

## 接受依据

本 ADR 保持 Draft，直到 F4 contract/Golden/API/performance 测试及 PR #7 当前代码的完整 CI job 全部核实通过。F3 的历史 CI 不作为 F4 接受依据。
