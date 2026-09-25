# ADR-0019：Stock Fortune Snapshot 聚合契约与语义边界

- **状态**：Draft
- **日期**：2026-09-26
- **影响**：Stock Fortune Snapshot、Bazi/Calendar 编排、十神上下文、关系事件与 chart_artifact
- **关联**：[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0015](ADR-0015-stock-fortune-birth-basis-and-precision.md)、[ADR-0016](ADR-0016-fortune-temporal-boundaries-and-market-session.md)、[ADR-0017](ADR-0017-fortune-polarity-and-dayun-direction.md)、[ADR-0018](ADR-0018-fortune-first-trade-and-temporal-resolution.md)

## 背景

F1/F2 已经定义股票出生档案、首日阴阳大运约定和三种 evaluation time 输入。后续历史研究、关系扫描和展示需要一个统一时点结果，避免调用方各自拼接原局、流年/月/日、十神和关系，也避免以自由字典丢失字段语义。

## 决策

1. `StockFortuneSnapshot` 是内部聚合契约，包含证券身份、出生档案、时间解析、原局、大运、流年/月/日、十神、关系、来源/规则版本、可用性、原始盘面和警告。本 ADR 不新增或修改 `/api/v1/**`。
2. 原局四柱只由 `BaziEngine` 构造。只有 F2 解析后存在带时区的 `birth_datetime` 才调用 Bazi；`DATE_ONLY` / `UNKNOWN` 不填 00:00、09:30 或 12:00。缺出生时刻时原局及其依赖上下文返回 unavailable，其他已解析的时间柱仍可用，Snapshot 标为 partial。
3. 十神上下文固定区分原局、流年、流月、流日和原局藏干五类。映射复用 `src.core.relations.ten_god`，并与 BaziEngine 已有原局/流时柱结果逐项比对；不在 Fortune 中新增十神映射表。
4. 大运方向严格沿用 ADR-0017 的首日阴阳约定。只有方向约定可用时才向 BaziEngine 传兼容 `variant_mode`。大运日期由 `lunar-python 1.4.8` Adapter 的起运日与十年周期计算；Snapshot 用 `[start_at, end_at)` 选定当前周期。缺少方向、出生时刻、Adapter 周期或覆盖 evaluation time 的周期时，相应方向/周期字段保持 unavailable/null。
5. 关系事件只包装已有 Bazi natal relations 和 Date Scan relation helpers。每个事件保留底层类型，并用 `source`、`target`、参与柱位、干/支/整柱组件、作用范围和 relation rule version 精确定位；Fortune 层不复制合冲刑害破算法，不给事件附加吉凶或市场方向。
6. Snapshot 同时保存输入来源与版本、出生推定 assumptions、时间解析 assumptions、各引擎/规则版本和 chart artifact ID。Bazi 原始盘面持久化时剔除运行时 `calculated_at`；系统当前时间、价格、收益和外部实时行情不进入 Snapshot 核心结果。
7. `PARTIAL` 表示部分独立上下文可用；`UNAVAILABLE` 表示对应上下文没有安全计算依据。不可用数值用 `null` 或 unavailable 表达，不用 0 填充。
8. Snapshot 只描述确定性术数结构。不得由十神、关系数量、大运或共识直接生成上涨概率、收益、买入建议或投资信号；这些语义受 ADR-0013 约束。
9. 改动算法或输入/输出语义时提升对应 rule/engine version；聚合字段或序列化语义改变时提升 snapshot contract/rule version。已有版本结果保持可追溯。

## 后果

- 上层只需提交 typed `StockFortuneEvaluationRequest`，通过 `StockFortuneEngine.evaluate` 获得可回放结构，不再负责手动编排底层引擎。
- 对同一版本化输入，排盘、关系、十神和大运周期的核心字段可以重复计算并比较；外部数据库写入的创建时间不属于 Snapshot 计算结果。
- Snapshot 明确区分日线日期推定、精确时刻和无法计算，减少研究样本因隐式补时而产生的口径漂移。
- F2 已冻结的 `stock-fortune-birth-v2` 长于当前 `chart_artifact.birth_profile_version` 的 16 字符列宽。为保留该版本并支持 PostgreSQL 等严格长度数据库，F3 将列扩展到 32 字符并提供 Alembic migration；downgrade 在存在超过 16 字符的值时必须中止，避免截断 provenance。

## 接受依据

本 ADR 仍为 Draft。只有当 migration upgrade/downgrade 安全检查、后端契约/Golden 回归、前端既有门禁和对应 CI run 均有当前提交的证据后，才可改为 `已接受(Accepted)`。在此之前，F3 不得报告 PASS 或 F4 readiness。
