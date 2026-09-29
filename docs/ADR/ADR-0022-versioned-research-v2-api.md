# ADR-0022：版本化研究 v2 API

- **状态**：已接受(Accepted)
- **日期**：2026-09-28
- **影响**：研究 API、Fortune v2 入参解析、W4 Parquet 数据集查询与 W6 实验报告读取
- **关联**：[ADR-0004](ADR-0004-as-of-time-isolation.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0018](ADR-0018-fortune-first-trade-and-temporal-resolution.md)、[ADR-0019](ADR-0019-stock-fortune-snapshot-contract.md)、[ADR-0020](ADR-0020-stock-fortune-timeline-and-cross-section.md)、[ADR-0021](ADR-0021-runtime-readiness-and-fail-closed-calendar.md)

## 背景

W3/W4 已建立版本化事件筛选和 manifest 驱动的 Parquet 历史面板。v1 路由继续服务原有请求，但其入参、存储和历史口径不能代表新研究闭环。新页面需要服务端解析 Fortune 输入、PIT 股票池和研究数据，并能追溯数据集与实验。

## 决策

1. 增加 `/api/v2/research/fortune/timeline`、`/api/v2/research/fortune/scan`、`/api/v2/research/event-study`、`/api/v2/research/datasets/{dataset_id}` 和 `/api/v2/research/experiments/{experiment_id}`。沿用 ADR-0021 的 `/api/v2/system/readiness`；不改写 v1 路径或响应。
2. Timeline 请求只接受证券代码、日期范围和结构筛选条件。服务端读取证券元数据，并用当前 `MarketDataProvider` 的非降级首个日线观测解析 Fortune birth profile；日线只证明最早可观测日期，解析出的开盘时刻必须标为 INFERRED 并保留假设。降级/合成数据不得作为首笔证据；无法解析时保持 unavailable。
3. Scan 请求只接受已登记的 `universe_version`、研究日期、结构条件和分页/排序。成员由 `PointInTimeUniverse` 服务端按 v2 半开区间 `list_date <= T < delist_date` 解析（旧 `at()` 的含退市日语义保持不变），并先通过 `resolve_universe_evidence_as_of` 核验来源截止日；未登记、证据不完整或日期超出证据范围时 fail closed。服务端解析各证券资料与首个日线观测，再调用 F4 scanner。该路由描述 Fortune 结构，不据此宣称行情认证或历史有效性。
4. Event-study 请求必须显式指定 dataset、股票/日期范围、至少一个 factor 条件、activation、目标周期及完整版本对象。服务端只读取固定配置根目录下 W4 manifest 登记且 SHA-256 匹配的 Parquet 分片；客户端不能提供本地路径。股票模式限于指定股票；日期模式报告匹配日期数和证券-日期-因子观察数，市场层指标先按日期等权。
5. Event-study 返回命中组、条件补集与整体的描述统计，逐项列出事件、标签可用性和缺失原因，并使用稳定的 `stock_code + research_date + factor_id` 排序分页。它不运行或冒充确认性显著性检验；数据集未认证时返回 `EXPLORATORY_NOT_GATED` 或 `NO_REAL_DATA`，不得提升研究资格。
6. Dataset 查询只暴露 manifest、逐片状态/校验、数据版本、范围、限制和资格。Experiment 查询只读取 W6 生成的版本化 JSON 报告；ID 只能是安全路径组件，路径固定在 `settings.data_dir/research_experiments`。
7. `/api/v2/system/readiness` 继续由 ADR-0021 实现；W5 只添加契约/兼容测试，不重复或覆盖其状态逻辑。

## 备选方案

- **扩展 v1**：会破坏已公开请求/响应或混淆历史口径；拒绝，新增版本路径。
- **让前端提交出生盘、PIT 成员或本地文件路径**：会把确定性计算/成员资格移到展示层或允许访问任意本机文件；拒绝。
- **把未认证样本包装为显著结论**：会混淆工程回放、描述统计与研究资格；拒绝，资格状态与统计输出分离。

## 后果与限制

- 数据源、首日观测和版本缺失时，响应可用性会降低，但不会用 listing date、合成行情或零值回填。
- PIT API 的可用日期受登记证据截止日约束；W2 未完成的范围仍不可认证。
- v2 的描述统计不等于 W6 的冻结实验、多重检验、负对照或 gate-v2 结果。
- 实验文件由受信任的本地 W6 生成器写入；API 只按安全 ID 读取，不接受请求路径。

## 接受依据

- 实施提交：W5 package commit（见 `docs/research/W5-2026-09-28.md` 的 Git 记录）。
- 契约和路由测试：v2 timeline 服务端解析、PIT v2 退市日边界、超大 universe fail-closed、显式版本事件统计、版本不匹配、超大候选集 fail-closed、dataset/experiment 固定根路径、防路径穿越、v1 health 和 W1 readiness 兼容均通过。
- 回归：Stock Fortune v1、system readiness、PIT universe、W4 historical dataset 和 `test_no_future_data_access.py` 均通过；Ruff 与 `git diff --check` 通过。
- W2 的数据认证和完整历史面板仍未完成；W5 不改变其资格，不把 W4 工程样本升级为研究证据。
