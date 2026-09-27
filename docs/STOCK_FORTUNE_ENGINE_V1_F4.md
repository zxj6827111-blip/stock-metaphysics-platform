# Stock Fortune Engine V1 / F4 验收记录

- **日期**：2026-09-26
- **分支**：`feat/stock-fortune-engine-v1`
- **基线**：F4 开始 HEAD `f0166d85f7bc39a12a8ea8043a5b2554e83a4985`
- **范围**：Stock → Date Range Timeline、Date → Explicit Universe Scan、Research API、性能结构验证
- **状态**：`STOCK_FORTUNE_F4 = PASS`。实现与验收文档 parent head `de29c195fb10096babae66bb1ffcc3748ec0aada` 的 run `36241192474` 六个 job 全部成功；本次更新补记 F5 readiness，当前文档提交仍须通过 PR #7 的 head CI。
- **F5 就绪**：`READY_FOR_STOCK_FORTUNE_F5 = YES`，前提是调用方为每个历史日期提供有来源/版本、与日期匹配的 PIT universe；F5 研究统计有效性，不代表 F4 已证明预测能力。
- **ADR**：[ADR-0020](ADR/ADR-0020-stock-fortune-timeline-and-cross-section.md)，已接受(Accepted)。

## 架构与契约

### Stock → Timeline

入口为 `StockFortuneTimelineEngine.build(StockFortuneTimelineRequest)`，输出 `StockFortuneTimeline`。响应把 F3 稳定上下文与按日期变化的 point 分开：稳定区保存原局四柱、藏干、原局十神/关系、大运方向/周期、来源、版本和 chart artifact ID；每天只保留时间柱、流日/流月/流年十神、当前大运引用、与原局的结构化关系、交易日状态和 availability。请求 filters 和 include flags 也会回显，便于结果解释和重放。

支持 `ALL_CALENDAR_DAYS` 和 `TRADING_DAYS_ONLY`。Exact local time 默认中午且可显式设为 23:00；`MARKET_SESSION_DATE` 只允许在交易日模式使用，并要求可解析的交易所、session 与 config 版本。未确认交易日历覆盖时，交易日状态为 `null`；`TRADING_DAYS_ONLY` 不会把周末规则当成真实日历。若区间没有已确认交易日，响应 points 为空、availability 为 partial，并保留稳定上下文，不伪造日期点。

大运点位使用 F3 的 `[start_at, end_at)` 周期语义，并受 `polarity_observed_at` 限制。Timeline 的稳定 F3 Snapshot 锚定最后一个返回日期；没有日期点时锚定请求结束日的 exact-noon，只为建立稳定上下文。

### 月份、十神和关系

流月段直接复用 `ten_god_calendar.segment_boundaries(..., kind="month")` 的精确十二节边界，区间为 `[start_at, end_at)`；`gregorian_months` 只用于分组，因此同一公历月可以含两个流月段。Ten-god 日索引包括流年、流月、流日；原局和藏干十神留在稳定区。过滤必须明确指定十神层和柱位；关系过滤明确限定关系类型、来源上下文/柱、原局目标柱及可选干支组件。多个条件按 AND 处理。筛选不表示收益方向或投资判断。

### Date → Cross-Section Scan

入口为 `StockFortuneCrossSectionScanner.scan(StockFortuneScanRequest)`。请求只接受显式 typed 股票目标，不自动扩建全部市场股票池；扫描返回 compact item、matched conditions、必要的 chart `snapshot_ref`、规则版本、limit/offset/total、排序、universe digest 和 request digest。Sort 仅为 symbol、命中条件数量或关系事件数量，平局按 symbol 排序。

横截面扫描的 universe 由调用方提供来源、版本和逐股出生档案；接口不独立证明历史成分股资格，响应会明确提示调用方传入与研究日期相符的 PIT 集合。`MARKET_SESSION_DATE` 由服务器的正式交易日历二次核验；只有 `observed_index_days` / `published_exchange_calendar` 可通过，并将来源及日历内容指纹回显。

## API

- `POST /api/v1/research/fortune/timeline`
- `POST /api/v1/research/fortune/scan`

两条路由使用 typed request/response schema，并通过已有 `chart_artifact` writer 保存 F3 原始盘面；没有新增每日 Snapshot 持久化表或 API v1 旧字段修改。

## 性能结构

- Timeline：每个请求只用一次 F3 Snapshot 构建稳定原局；每个自然日只解析一个变化日历上下文，不按日期重建 Bazi 原局。
- Cross-section：每只目标只评估一次 F3 Snapshot；同一日期的 evaluation CalendarSnapshot 在请求内 pinned 复用；其他参考 CalendarSnapshot 用最多 128 项 LRU，避免大量不同出生日期占满请求缓存。
- 单元性能用调用次数断言，不设易抖动的耗时门槛：1 只股票 × 365 天，以及 100 只股票 × 1 个日期。Acceptance run `36241192474` 的记录耗时分别为 **1.117995 秒**、**0.203184 秒**；仅作该 CI runner 的观测值，不设为毫秒门槛。
- F3 chart artifact 仍按契约落库；一次横截面会为每只已评估目标保留其 Calendar/Bazi 原始盘面。没有新增长期 Snapshot 表。反复大 universe 请求的 artifact 保留治理作为限制记录。

## 既有 Date Scan 兼容策略

旧 `/api/v1/research/date-scan` 与 `/api/v1/research/ten-gods/date-scan` 未切换内部算法或改变响应，避免破坏 12:00 锚点、关系矩阵及既有缓存/分页语义。旧路由当前回归由原集成测试覆盖。本轮交付 F4 core；后续迁移应先写 legacy response adapter，并以同一输入的逐字段 parity 测试通过为条件。

## 测试与验证

### 新增测试

- `tests/core/test_stock_fortune_engine.py`：stable/dynamic 分层、原局与藏干/流年流月流日过滤、结构化关系过滤、交易日未知 fail-closed、确定性 replay、1×365 与 100×1 调用次数和耗时记录。
- `tests/golden/test_stock_fortune_timeline_golden.py`：从 CalendarEngine 实际结果发现公历月内的精确节气换月；22:59 / 23:00 / 23:01 日界；正式 SSE 历史节假日。
- `tests/integration/test_api_stock_fortune.py`：两条新增 API 的真实 typed request/response 与 artifact ref smoke。

### 当前本机状态

- bundled Python 3.12.14 AST parse：修改/新增的 Python 文件均通过。
- `git diff --check`：通过。
- pytest/backend suite：未运行；本机没有 pytest、FastAPI、SQLAlchemy、pydantic-settings、lunar-python，也没有项目 `.venv`。
- Pydantic model smoke：F3 `StockFortuneEvaluationRequest` 可构造；F4 relation-filter guard 与六个 request/response JSON Schema 通过。
- PR #7 acceptance evidence head `de29c195fb10096babae66bb1ffcc3748ec0aada` run [36241192474](https://github.com/zxj6827111-blip/stock-metaphysics-platform/actions/runs/36241192474)：六个 job 全部 success。Backend `2192 passed, 20 skipped, 28 deselected, 1 warning in 331.90s`；Ziwei engine + Golden `331 passed in 7.97s`；seeded E2E `7 passed in 25.2s`；UI structure `40 passed in 43.4s`；frontend typecheck/build success。
- 首轮 F4 CI run `36239859413` 的 backend 有 24 个共同 `AttributeError`；根因为 F4 relation-filter guard 误放进 F3 request validator，已由 `796076e` 删除，并在全套成功 run 中回归。此记录不将首轮失败隐藏为通过。
- 以上 F4 代码验证不引用 F3 历史 run。PR 状态检查是最终分支 head 的权威结果；当前提交只补记 F5 readiness 与最新 run 证据，仍需核对该文档提交触发的所有 job。

## 限制与 F5 前置

- 横截面按显式 universe 工作，自动 PIT universe provider 接入未纳入 F4；历史研究前必须由调用方提供与日期相符、可追溯版本的股票成员集合。
- 旧 Date Scan core 迁移留待 parity 工作包。
- F4 输出只有 calendar-derived 结构，不含收益、胜率、推荐或价格预测。`READY_FOR_STOCK_FORTUNE_F5 = YES`：F5 可开始做历史研究有效性验证；每次研究必须传入可追溯且与 `as_of` 匹配的 PIT universe。F4 不证明术数条件与未来收益之间存在统计关系。
