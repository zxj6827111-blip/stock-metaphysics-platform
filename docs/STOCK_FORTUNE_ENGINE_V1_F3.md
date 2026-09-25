# Stock Fortune Engine V1 / F3 验收记录

- **日期**：2026-09-26
- **分支**：`feat/stock-fortune-engine-v1`
- **范围**：内部 Snapshot schema、统一 orchestration、既有 Calendar/Bazi/Ten-God/Relation 复用、Golden/契约测试、ADR-0019
- **当前结论**：实现已落地，最终验收等待测试与 CI 证据；不得据此文档的存在推断 F3 PASS。
- **F4 readiness**：NO，直到本文件的阻塞门禁有当前提交的 PASS 证据。

## 结果结构

`StockFortuneSnapshot` 位于 `src/core/schemas/fortune.py`，由 `StockFortuneEngine.evaluate(StockFortuneEvaluationRequest)` 统一生成。请求包含 `stock_identity`、已解析 `birth_profile`、F2 `evaluation_context`、输入来源/版本以及可选的大运极性证据。

Snapshot 聚合：

- `natal_context`：年、月、日、时柱，日主、阴阳、五行、逐柱藏干（十神/五行/本中余气/权重）和 BaziEngine 版本；无安全 `birth_datetime` 时整个原局为 unavailable，不补时。
- `luck_cycle_context`：ADR-0017 方向/约定、兼容算法参数、周期列表、当前周期、边界、干支、周期规则版本和 unavailable 原因。
- `annual_context` / `monthly_context` / `daily_context`：均从同一个 `CalendarSnapshot` 提取。
- `ten_god_context`：原局四柱干十神、流年/流月/流日天干十神、原局各柱藏干十神及规则版本。
- `relation_context`：原局事件及流年/月/日/当前大运到原局年/月/日柱的结构化事件和类型计数；不生成金融分数。
- `raw_chart` / `chart_artifact_ids`：Calendar 与 Bazi 原始盘面及既有 artifact 表中的可追溯 ID。
- `provenance` / `rule_versions` / `assumptions` / `warnings`：记录各输入与计算层来源、版本、推定和降级信息。

Snapshot 为内部契约，本轮没有新增临时 API 或修改 `/api/v1/**`。Artifact writer 复用既有 `chart_artifact` 表；因 F2 冻结的 birth profile version 为 22 字符，F3 用 Alembic migration 将该列扩到 32 字符，保留完整版本值。

## 规则与算法来源

| 上下文 | 复用来源 | 版本/边界 |
|---|---|---|
| 出生基准 | F2 resolver 的 `StockFortuneBirthProfile` | `fortune-birth-v2`；真实时刻、推定时刻、date-only 分离 |
| evaluation 时间 | `resolve_temporal_input` + `CalendarEngine` | exact / market session / civil date-only；23:00 换日不变 |
| 原局 | `BaziEngine.build_chart`，并注入已创建的 birth/reference `CalendarSnapshot` | Bazi engine version；不复制干支历法或藏干实现 |
| 大运方向 | `resolve_first_day_yinyang_luck_cycle` | `stock-luck-cycle-first-day-yinyang-v1`；方向缺证据时不可用 |
| 大运时段 | BaziEngine 内唯一 `lunar-python 1.4.8` Adapter | 起运日 + 十年周期，按 `[start_at, end_at)` 选择当前周期 |
| 十神 | `src.core.relations.ten_god`，并与 BaziEngine 字段交叉校验 | 当前 ten-god rule version |
| 关系 | 原局 `BaziChart.relations` + Date Scan 的 relation helpers | 当前 relation rule version；Date Scan 12:00 采样未更改 |

## 十神五类

1. 原局：年、月、日、时四柱天干相对日主的十神。
2. 流年：当前年柱天干相对日主。
3. 流月：当前月柱天干相对日主。
4. 流日：当前日柱天干相对日主。
5. 藏干：原局年、月、日、时各地支的藏干十神。

每个结果带柱位、干支、TenGodRef/藏干记录与 rule version。实现复用现有十神函数，并逐柱核对 BaziEngine 输出；不把十神映射复制到 Fortune 层。流年/月/日支的藏干不在本阶段扩展。

## 大运与关系定位

大运方向按已接受 ADR-0017：首日阳/阴映射到兼容算法参数，再按出生年干阴阳同类顺、异类逆。只有显式、带来源和版本的首日阴阳证据才产生方向。当前周期取决于周期列表和 evaluation time；无当前周期时 `cycle_index`、起止边界、干支为 null，周期可用性为 unavailable。

`FortuneRelationEvent` 的每一端是 `FortuneRelationParticipant(context, pillar, component, value)`。例如“流日支子与原局年支午冲”会把 source 定位到 `day/branch/子`，target 定位到 `natal/year/branch/午`，并保留底层 relation type、scope、rule version 和参与对象。Fortune 包装 Date Scan 现有计算，不自建五合/合冲刑害破算法。

## 可用性、追溯与语义边界

- `CIVIL_DATE_ONLY` 保持 `TIME_REQUIRED`，不创建日历快照。
- `MARKET_SESSION_DATE` 需显式交易所、交易日证据、session/config 版本；时间是 inferred anchor。
- 出生档案为 `DATE_ONLY` 时，年/月/日时点上下文可用，但原局、十神、大运和依赖它们的关系不可用，整体为 `PARTIAL`。
- 不可用规则或方向用 null/unavailable 表示，禁止用 0 代替。
- Bazi 原始 artifact 排除运行时 `calculated_at`；相同版本化输入的核心 Snapshot 与 artifact ID 应稳定一致。持久化行的数据库创建时间不进入核心输出。
- Snapshot 不含收益、涨跌概率、推荐、买入信号或金融评分。

## 验证与门禁

| 检查 | 结果 | 证据 |
|---|---|---|
| F3 核心契约测试 | 待执行/待记录 | `tests/core/test_stock_fortune_engine.py` |
| F3 Golden | 待执行/待记录 | `tests/golden/test_stock_fortune_snapshot_golden.py` |
| Alembic upgrade/downgrade | 待执行/待记录 | 新增 `chart_artifact.birth_profile_version` 16→32 migration；downgrade 有长值时中止 |
| F1/F2、Bazi、Calendar、Date Scan、Ten-God、Relation、Ziwei 回归 | 待执行/待记录 | 当前提交测试 run |
| 前端 typecheck/build、seeded E2E | 待执行/待记录 | 当前提交 workflow run |
| CI | 待触发/待记录 | PR #7 当前提交的 run/job conclusion |

本机 `.venv` 不存在，启动器 `py -3.12` 未发现已安装 Python；Codex bundled Python 3.12.14 缺少 `pytest`、SQLAlchemy 和 `pydantic-settings`，目标 pytest 因 `No module named pytest` 未能启动。11 个修改后的 Python 文件通过了 AST syntax parse。前端 `apps/web/node_modules` 不存在，本机 Node 为 v24.14.0（CI 锁定 Node 20），因此 typecheck/build/E2E 未在本机运行。不得把未执行写为通过。最终更新本表时需记录准确命令、计数、run ID/链接和 job conclusion。

## 尚存限制

- 大运方向依赖首日阴阳研究约定证据，不是股票真实性别或收益结论。
- Fortune relation scan 复用现有 Date Scan 的原局年/月/日目标集合，未扩展新的关系族或时空两两扫描。
- `/api/v1/**`、UI、排行榜、信号、研究优化和投资建议不属于 F3。

## 结论

在 backend/Golden 与既有回归、前端 build/typecheck/E2E 及 CI 全部取得当前提交的通过证据前，`STOCK_FORTUNE_F3` 保持 FAIL，`READY_FOR_STOCK_FORTUNE_F4` 保持 NO。验证完成后以实际测试输出替换上述待记录项，并按 ADR-0019 的接受门槛更新状态。
