# 架构决策记录（ADR）

每个 ADR 记录一个**不可逆或影响面大的技术决策**：背景、备选方案、选择、后果。

| # | 标题 | 状态 |
|---|---|---|
| [0001](ADR-0001-adapter-isolation.md) | 第三方引擎必须经 Adapter 隔离 | 已接受 |
| [0002](ADR-0002-bazi-engine-backend.md) | Phase 1 八字计算使用自研确定性内核，bazi-pro 作为 Phase 2 可插拔后端 | 已接受 |
| [0003](ADR-0003-no-gender-variant-mode.md) | 股票无性别 → `variant_mode`，默认 `not_applicable` | 已接受 |
| [0004](ADR-0004-as-of-time-isolation.md) | `as_of` 单向时间隔离与未来数据泄漏防护 | 已接受 |
| [0005](ADR-0005-sqlite-duckdb-storage.md) | SQLite 主库 + DuckDB/Parquet 研究层 | 已接受 |
| [0006](ADR-0006-ui-fixture-mode.md) | UI fixture 模式与生产 runtime 分离 | 已接受 |
| [0007](ADR-0007-red-up-green-down.md) | 涨跌配色采用 A 股惯例（红涨绿跌），覆盖 UI 规范文档 | 已接受 |
| [0008](ADR-0008-bazi-engine-strategy.md) | 八字引擎策略：自研内核为 Canonical，bazi-pro 仅作 Phase 2 参考 | 已接受（Phase 1.1） |
| [0009](ADR-0009-ziwei-engine-iztro.md) | 紫微斗数采用 iztro（Node 服务 + Python Adapter） | 已接受（Phase 2A） |
| [0010](ADR-0010-ziwei-no-gender-variant.md) | 紫微「无性别」处理：方向 variant 而非性别默认 | 已接受（Phase 2A） |
| [0011](ADR-0011-consensus-not-averaging.md) | Consensus 禁止简单平均，冲突必须显式保留 | 已接受（Phase 2C） |
| [0012](ADR-0012-phase3a-astockdata-canonical.md) | Phase 3A 主数据源切换（含退市股，根治 survivorship bias） | 已接受（Phase 3A） |
| [0013](ADR-0013-research-validity-boundary.md) | 研究有效性边界：规则强度 ≠ 市场预测，负结果是合法结果 | 已接受（2026-09-23 追加为总纲） |
| [0015](ADR-0015-stock-fortune-birth-basis-and-precision.md) | Fortune 出生基准与出生时间精度 | 已接受（F1） |
| [0016](ADR-0016-fortune-temporal-boundaries-and-market-session.md) | Fortune 历法边界与市场时段分层 | 已接受（F1） |
| [0017](ADR-0017-fortune-polarity-and-dayun-direction.md) | Fortune 极性、大运方向与兼容参数分离 | Draft |

编号 0014 已在未合入主干的远端候选分支中使用；该分支文档不是当前主干的正式 ADR。本表跳过该编号，避免将候选规则覆盖或误登记。财富分数语义沿用已接受的 ADR-0013，不重复建 ADR。

新增 ADR 时：复制模板 → 选用未占用编号 → 在本表登记 → 在适用阶段交接文档中引用。只有代码、测试和证据证明实施后，状态才能改为「已接受」。
