# Stock Fortune Engine V1 — F1 审计与规则冻结提案

> As of: 2026-09-25
>
> 审计基线：branch `feat/stock-fortune-engine-v1`，初始 HEAD `2ea01996ac04fbc26cf529871fc82614f36005aa`
>
> 范围：只审计并新增 Fortune 内部契约、最小 Adapter、ADR 草案和边界案例；不改 `/api/v1`、数据库、现有排盘行为、研究结论或 UI。

## IN SCOPE / OUT OF SCOPE

**IN SCOPE**：出生基准与时间精度、极性/顺逆语义分离、同一历法快照、市场时段 Adapter、十神/关系的复用边界、财富因素/共振/可信度结构、边界 Golden Cases、能力审计。

**OUT OF SCOPE**：完整 Fortune 编排和评分、因子权重、市场预测概率、行业五行、市场天地人因素、历史金融统计、公开 API、数据库迁移、UI、改写现有 `StockBirthProfile` 或生产排盘行为。

## Capability matrix

| 能力 | 当前实现位置 | 当前状态 | 可复用性 | F1 新增契约 |
|---|---|---|---|---|
| 股票元数据 | `src/core/schemas/stock.py::StockMaster`；`src/db/models/stock.py` | 有 symbol/交易所/板块/listing date 等基础资料；主干也有 `first_day_yinyang` / `first_day_pct_chg` 字段，但字段存在不代表它是已接受排运规则。 | 复用证券标识与来源；字段缺失必须保留 unavailable。 | Fortune profile 只保留证券标识及明确出生来源，不把首日涨跌自动映射成真实极性或方向。 |
| 股票出生档案 | `src/core/schemas/stock.py::StockBirthProfile`；`src/core/stock/birth_profile.py::build_birth_profile` | 旧默认 `LISTING_OPEN` 会先找首个正式交易日，再按交易时段开盘生成时间；`first_trade` 预留但没有逐笔来源，`FIRST_TRADE` 请求会报错。不是实际首笔成交时间。 | 复用交易所时段解析和来源元数据；旧模型/API 保持原样。 | Fortune 专用 `StockFortuneBirthProfile`；明确 `listing_date`、`first_trade_datetime`、`birth_basis`、来源、版本和精度。 |
| 出生时辰精度 | 旧出生档案有 `DataQuality`，没有 `EXACT/INFERRED/DATE_ONLY/UNKNOWN` 精度枚举 | 不能单凭旧时间字段区分实测时间与推定开盘。 | 旧质量说明可作为来源之一，不能替代精度。 | `BirthTimePrecision`；日期级资料只允许三柱状态，未知资料不可用。 |
| 八字 / 旺衰 / 喜忌 | `src/engines/bazi/bazi_engine.py`、`src/engines/bazi/rules.py`、`src/core/schemas/bazi.py` | 已有确定性四柱、五行力量、日主旺衰、格局、喜用忌、藏干十神、原局关系；强弱和喜忌方法已在 schema 中分别表达。 | 复用 BaziEngine 输出；不在 Fortune 中另算旺衰/格局/喜忌。 | `NatalPillarSet` 表达三柱/四柱/不可用，不复制计算逻辑。 |
| 大运 | `src/engines/bazi/bazi_engine.py::_da_yun`；`src/core/schemas/common.py::VariantMode`；ADR-0003 | 正式默认 `not_applicable`，不输出大运；显式 `forward/reverse` 才调用库。当前实现把 `forward` 映射为第三方 gender 参数 `1`，`reverse` 映射为 `0`；异常被折叠为空列表。标签不是可证明的实际顺逆方向。 | 可复用第三方计算 Adapter 作为候选实现，但不能据现有标签冻结 Fortune 方向。 | `FortunePolarity`、`LuckCycleDirection`、`CompatibilityGender` 分开；默认方向不可用。 |
| 十神 | `src/core/relations/ten_god.py::ten_god`；`src/core/schemas/ten_god.py`；`src/core/orchestration/ten_god_calendar.py` | PR #5 合入后的共用映射覆盖原局天干、藏干及已支持的流年/月/日；已有契约和 Golden 回归。仓库没有独立 `TenGodService` 类。流时尚未接入该日历输出。 | 复用唯一映射、`TenGodRef` / `TenGodHiddenStem` 与现有 orchestration；不得另造映射表。 | `FortuneTenGodObservation` 可承载既有映射输出，并预留 `hour` 层。 |
| 刑冲合害破 | `src/engines/bazi/rules.py::compute_relations`；`src/core/relations/date_relation.py`；`src/core/schemas/relation.py::RelationEvent` | 有原局关系和 relation V3；日期关系矩阵覆盖流年/月/日 × 原局年/月/日，已有关系类型和 rule version。现有事件没有统一的 Fortune `direction/severity/weight` 口径。 | 复用原始事件及 `rule_version`；不把“合”自动判成财富正向。 | `FortuneRelationEvent` 统一保存类别、原始类型、参与者、范围；方向/严重度/权重允许未知，不预设数值。 |
| 历法与流年/月/日/时 | `src/engines/calendar/calendar_engine.py::CalendarEngine.snapshot`；`src/core/schemas/calendar.py::CalendarSnapshot` | 年柱用 exact 立春口径、月柱用 exact 节气口径；日柱使用 exact 日干支；时柱由 CalendarEngine 提供。快照当前按传入的 Asia/Shanghai 本地时间解释。 | 复用一个 `CalendarSnapshot`，不让下游重新各算年月日时。 | `TemporalFortuneContext` 只保存一个快照；provider 只调用一次。 |
| 黄历 | `src/engines/huangli/huangli_engine.py`；`src/core/schemas/calendar.py::HuangliSnapshot` | 独立黄历 Adapter 与原始结果已存在。 | 若后续纳入 Fortune，复用快照，不把黄历吉凶改写成收益判断。 | F1 不增加黄历计算或财富映射。 |
| A 股市场时段 | `src/core/stock/exchange_sessions.py`、`config/exchange_session_calendar.json` | 旧配置解析开盘/收盘，不表达连续时段与午休状态。 | 复用交易所枚举和 session 数据来源；不把 tradable 状态塞入历法快照。 | `MarketSessionAdapter` 端口与 A 股 Adapter；午休时 `tradable=false`，传统午时仍从同一日历快照读。 |
| date-scan / relation-scan / relation-study | `apps/api/routers/research.py` (`/date-scan`、`/relation-study`)；`apps/api/routers/ten_gods.py` (`/date-scan`)；`src/core/orchestration/date_relation_scan.py`、`ten_god_date_scan.py`；`src/research/relation_runner.py` | 现有研究实验室链路与 Fortune 领域层分开，集成测试覆盖两个 date-scan 与 relation-study。 | 保持原路径和行为，后续可通过 Adapter 复用结果。 | F1 不改端点、不重解释研究结论。 |
| 公共 API / 数据库 | `apps/api` schemas / routes；`src/db` / migrations | 现有 `/api/v1/**` 和数据库契约继续生效。 | 无需改动。 | Fortune 类型仅内部使用，不由 v1 直接暴露；无 migration。 |
| 历史研究结论 | `docs/PHASE1_ACCEPTANCE_REPORT.md`、`docs/PHASE2_ACCEPTANCE_REPORT.md`、`docs/PHASE3_RESEARCH_REPORT.md`、`docs/ADR/ADR-0013-research-validity-boundary.md` | Phase 1 为工程通过、研究主张受阻；Phase 2 为 `PASS WITH CONDITIONS — PLATFORM V2 READY / RESEARCH CLAIMS BLOCKED`，当时整体多模型研究为 `INVALID_CONTROL`；Phase 3 为 42 个 gate 实验中 OOS 支持数 `0`，多引擎为 `MULTI_ENGINE_NO_SIGNAL`。 | ADR-0013 是财富分数语义与金融证据隔离的现有权威决策。 | 不新增重复的 Score Semantics ADR，不声称上涨概率/买入信号。 |

## 主干与 ADR-0014 候选差异

当前 main/本分支基线只含 ADR-0001 至 ADR-0013。远端候选提交 `ad4594a89615d79fc4ec4835d0bb6b730d58a688` 在自己的分支包含 ADR-0014，提出用 `stock_master.first_day_yinyang` 选择传统算法的兼容参数；它尚未进入本分支基线，不能作为正式规则。

| 项目 | 当前 main 正式规则 | ADR-0014 候选规则 | F1 结论 |
|---|---|---|---|
| 默认大运 | ADR-0003：`not_applicable`，不输出大运；显式 variant 才作研究 | 显式选择 `first_day_yinyang` basis；数据缺失时仍不可用 | 保持 ADR-0003；不迁移生产默认值。 |
| 输入含义 | 当前 `forward/reverse` 名称与实现参数混合 | 首日收涨/收跌被映射成传统算法调用参数 | 首日阴阳是候选研究属性，不是股票性别，也不是已验证的真实顺逆方向。 |
| 第三方算法语义 | `_da_yun` 将 `forward/reverse` 映射成 `getYun(gender)` 输入 | 以阳/阴选出男/女兼容输入，再让算法按年干阴阳算实际方向 | Fortune 必须分别存“极性、兼容输入、实际方向”；没有明确规则前实际方向不可用。 |
| F1 处理 | 不改 | 不 cherry-pick、不宣称 Accepted | ADR-0017 保留 Draft；后续需单独决策及回测，不进入因子。 |

另一个需明示的当前行为：锁定的 `lunar-python` 1.4.8 中 `getYun(gender)` 的方向还会依据出生年干阴阳；所以项目 `VariantMode.FORWARD/REVERSE` 当前实质是兼容 gender 输入标签，不保证总是同名实际方向。当前 CalendarEngine 使用 `getDayInGanZhiExact`，23:00 的日柱行为由该 exact 口径决定；F1 不新增早子/晚子切换选项。

## F1 契约决策（提案，未改变现有生产行为）

1. Fortune 默认出生基准提案为 `MARKET_FIRST_TRADE`。若只有上市日，A 股 Adapter 可按现有交易时段配置推定开盘时刻，但结果标记 `INFERRED`，`first_trade_datetime=null`，并记录“上市日期作为首个公开交易日”和“交易所开盘时刻作为出生时刻”两条假设。
2. `EXACT` 只用于来源证明的真实时刻；`INFERRED` 必须带假设；`DATE_ONLY` 不生成时柱；`UNKNOWN` 不生成命盘字段。真实首笔成交数据可覆盖推定结果。
3. 流年使用 CalendarEngine 立春 exact 边界，流月使用 exact 节气边界；流日/流时直接取同一个快照。
4. 当前 CalendarEngine 的 23:00 exact 日柱口径记录为待接受决策；项目不增加第二套子时算法。周末与休市日仍计算自然历法，但 market-session 显示不可交易。
5. A 股连续交易时段按左闭右开区间 `[09:30, 11:30)` 和 `[13:00, 15:00)`；`[11:30,13:00)` 不可交易。交易日已确认时标记 `BREAK`，交易日未知时状态为 `UNKNOWN` 但仍保留 `tradable=false`。市场层状态和传统时辰是两个字段/层次。
6. 十神、旺衰、喜忌、格局、关系均复用现有实现；F1 不新增分数权重。关系方向/严重度/权重没有依据时为未知/空值。
7. `FortuneResonance` 的 `4/5` 表示在已评估的五层时间规则中四层匹配，不是收益概率。数据可信度拆为出生、历法、规则、计算完整度；不叫 prediction confidence。
8. 研究统计接口与规则接口分离；市场上下文与行业五行只留扩展端口，不进入当前财富因素。

## Golden matrix

`tests/golden/test_fortune_temporal_boundaries.py` 提供 20 个边界/时间矩阵断言：

| 组 | 案例 | 断言 |
|---|---|---|
| 流年 | 立春前一分钟 / 精确时刻 / 后一分钟 | 年柱 `癸卯 → 甲辰`，交节时刻归新年柱。 |
| 流月 | 惊蛰前一分钟 / 精确时刻 / 后一分钟 | 月柱 `丙寅 → 丁卯`，交节时刻归新月柱。 |
| 子时 | 22:59 / 23:00 / 23:01 / 次日 00:00 | 当前 exact 日柱、子时地支行为明确锁定。 |
| A 股交易日 | 09:30、10:59、11:00、11:30、12:00、13:00、14:59、15:00 | 传统时辰分别来自 CalendarEngine；午休 11:30–13:00 明确不可交易。 |
| 自然日/交易日 | 周末自然日、明确非交易日 | 日历仍计算；市场层 `tradable=false`。 |

## ADR 处理

- 新增并接受 ADR-0015：出生基准与时间精度（内部推定规则；真实 first trade 数据源仍未接入）。
- 新增并接受 ADR-0016：历法边界与市场时段分层。
- 新增 ADR-0017：极性、大运方向与兼容性别参数（Draft）。
- Fortune Score Semantics 由已接受 ADR-0013 覆盖；不复制创建第二个同义 ADR。
- ADR-0017 的实际大运方向映射仍为 Draft；当前唯一正式默认继续遵循 ADR-0003：`not_applicable` / unavailable。

## 验收限制

本机没有项目 `.venv`，可用 Codex Python 缺少 `pytest`、`pydantic_settings` 与 `lunar_python`，因此本机 pytest 未运行。PR #7 的 GitHub Actions run `36124108854`（head `5e13ffa`）验证了 F1 契约测试：backend core **2119 passed / 20 skipped / 28 deselected**；ziwei engine + golden、frontend typecheck、frontend build、frontend seeded date-scan E2E 均 PASS。最初 run `36121932797` 有一个周末 fixture 错误，已在 `413ec00` 修正；随后全量回归及本轮五个 job 均通过。

F1 的契约、当前可复用规则和边界测试已完成，`STOCK_FORTUNE_F1 = PASS`。`READY_FOR_STOCK_FORTUNE_F2 = NO`：ADR-0017 的实际大运方向/极性映射未决；真实首笔成交数据源未接入；仅有日期时，23:00 exact 换日带来的日柱歧义仍需由后续结果契约明确表达。
