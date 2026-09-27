# ADR-0021：核心历法失败关闭与实例就绪状态

- **状态**：已接受(Accepted)
- **日期**：2026-09-27
- **影响**：CalendarEngine、Bazi/Huangli 编排、API 错误与系统 readiness、行情来源状态
- **关联**：[ADR-0004](ADR-0004-as-of-time-isolation.md)、[ADR-0013](ADR-0013-research-validity-boundary.md)、[ADR-0019](ADR-0019-stock-fortune-snapshot-contract.md)

## 背景

核心农历日期、四柱和节气字段决定盘面边界。将这些字段的异常吞掉并填入“甲子”等合法文本，会把计算失败伪装成正常盘面。另一方面，v1 health 是存活接口，不能证明数据库迁移已就绪；Provider 初始化失败也不应令版本和质量状态接口无法描述故障。

## 决策

1. 核心 Solar→Lunar 转换、农历年月日、四柱干支和前后节气名称/时刻均为必需字段。读取异常、空值、非法范围、非法干支或节气区间未覆盖目标时间时，CalendarEngine 抛出带字段和原因的 `CalendarCalculationError`。仅对不影响核心计算的展示字段保留安全降级。
2. 单引擎 API 把该异常映射为结构化 HTTP 503 `ENGINE_UNAVAILABLE`。多引擎编排将失败的 Calendar/Huangli/Bazi 观点标为 unavailable、分数为 null、不写入伪盘面 artifact，并继续保留独立可用引擎的结果。
3. `/api/v1/system/health` 继续作为兼容的 liveness 接口。新增 `/api/v2/system/readiness`：数据库查询与唯一 Alembic head 是核心必需条件；紫微服务和已认证行情数据单独报告为可降级组件。核心检查失败时 HTTP 503 且 `ready=false`；核心通过但可选组件未就绪时 HTTP 200 且 `status=degraded`。
4. 行情 Provider 通过非抽象状态描述提供来源、来源版本、实际截止日、质量等级、降级和研究资格。未知值返回 null/unavailable；请求范围不能冒充实际覆盖范围；记录数量本身不能提高质量等级。缺少逐证券认证时不授予研究资格。
5. `allow_synthetic_market_fallback` 默认关闭。需要演示合成数据的场景必须显式设置开关，并保留 synthetic 来源和 degraded 标记。
6. 版本分别标识失败处理/来源追溯行为：CalendarEngine 与 BaziEngine 小版本提升，默认运行配置版本提升。正常日期的排盘数值保持由 Golden Case 约束。

## 备选方案

- **保留默认值并只记 warning**：会继续产出外观合法但未经计算的盘面，拒绝。
- **把所有可选组件纳入 readiness 硬门**：紫微服务或未认证行情会阻止本机基础 API 可用；本轮将核心存储/迁移与可选研究能力分开报告，拒绝把两类故障合并。
- **只扩展 v1 health**：会改变既有响应语义并仍混淆 liveness 与 readiness；保留 v1，新增 v2。

## 后果与限制

- 核心历法依赖异常时，单项结果由可读的正常响应变为明确不可用；这是失败语义修复，不应通过补默认值恢复表面可用。
- 多引擎结果允许部分可用，但每个失败引擎必须在 `engines_failed`/warnings 中可见，且不可用分数保持 null。
- readiness 只说明该实例的数据库迁移和可选组件状态，不证明本机行情通过 W2 物理认证或足以用于正式研究。
- Provider 状态中无法从可信 manifest/观测行核实的截止日必须留空；W2 将负责建立逐证券认证范围。

## 接受依据

实现由异常注入、API 兼容、readiness、第三方隔离及正常 Golden Case 回归验证。最终 W1 相关定向集合通过 **181 项**，包含 Provider 初始化/状态读取异常注入和 F4 API 回归。后端全量命令 `PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider --basetemp <workspace-temp> -m "not ziwei_live" -q` 通过 **2222 项**，**1 项既有 skip**、28 项按标记排除，1 条 Starlette/httpx 弃用警告；全量后对 Provider 状态读取异常处理做了局部扩展，并由上述最终定向集合验证。正常 Golden Case 没有数值变化。

接受范围仅包括核心历法失败语义、引擎故障隔离、readiness 和行情状态展示；它不证明行情数据已通过 W2 认证，也不代表本机完整服务已通过 W8 运行验收。若未来 Golden 数值变化，必须先解释并按 `AGENTS.md §12` 处理，不得仅更新期望值。
