# Stock Fortune Engine V1 / F2 交接与验收

- **状态**：PENDING
- **As-of**：2026-09-25
- **分支**：`feat/stock-fortune-engine-v1`
- **PR**：#7（Draft）
- **起始 HEAD**：`f35d66c3f658bee8a8a0f4f7631d13d5d68491de`
- **验收 commit / CI run**：待提交与 CI

## 本工作包

F2 为 Fortune 增加 provenance-aware first-trade observation 与 birth-time resolver、明确标注的 `first_day_yinyang` 股票大运研究约定，以及 `EXACT_DATETIME` / `MARKET_SESSION_DATE` / `CIVIL_DATE_ONLY` 三种时间输入。没有 tick 或分钟行情不构成 F2 阻塞；当前日线只用于产生最早可观测交易日期。

## 最终契约

### First Trade / Birth

- `DailyBarFirstTradeProvider` 对无日期过滤的可信日线取 `min(bar.trade_date)`，只返回 `OBSERVED_TRADING_DATE` / `DAILY_BAR`。
- 日线 observation 不包含 `first_trade_datetime`。无可靠日期、合成/降级行情或数据源失败都返回 `UNAVAILABLE`，不会回退到上市/IPO 日期。
- birth resolver 将 observed date 与带版本的 A 股 session 开盘时间推导为 `birth_datetime_status=INFERRED`。推定 profile 保留首个观测日期、原行情 source/source_version、timezone、session/config/policy 版本和 assumptions；`first_trade_datetime` 为 null。
- 有可信日期但无法解析版本化 session 时只返回 `DATE_ONLY`；未来 tick/trade/minute adapter 可提供 `VERIFIED_DATETIME`，并保留其分辨率。

### 大运研究约定

- `阳 → YANG → male compatibility input`，`阴 → YIN → female compatibility input`。
- 出生年干与首日阴阳同极性则 `FORWARD`，异极性则 `REVERSE`；兼容输入不等于实际方向。
- 首日阴阳单独携带 polarity observation date 与交易日证据，不借用 Fortune birth 的 `first_trade_date`。`as_of` 早于 session close、来源缺失或来源/session 版本未知时返回 `UNAVAILABLE`。
- 规则版本为 `stock-luck-cycle-first-day-yinyang-v1`。这是股票研究约定，不宣称为传统八字对股票的 canonical doctrine，不使用未来行情或收益优化，不自动成为正式因子。

### Temporal 输入

- `EXACT_DATETIME`：必须带时区，直接交给现有 CalendarEngine，23:00 日界不变。
- `MARKET_SESSION_DATE`：必须明确交易所与交易日证据，使用版本化 session 开盘锚点并标记 `MARKET_SESSION_INFERRED`。
- `CIVIL_DATE_ONLY`：返回 `TIME_REQUIRED`，不构造 CalendarSnapshot，不填 00:00、09:30 或 12:00。
- Date Relation Scan / Ten God Date Scan 继续使用 `12:00:00`。

## F2 Gate 状态

| Gate | 状态 | 证据 |
|---|---|---|
| 1 日线只表达最早可观测交易日期 | 实现待测 | `DailyBarFirstTradeProvider` 与 contract test |
| 2 09:30 推定值标记 INFERRED | 实现待测 | birth resolver 与 profile status contract test |
| 3 无 intraday 时 `first_trade_datetime=null` | 实现待测 | provider / resolver tests |
| 4 推定值保存 provenance/version | 实现待测 | profile assertions |
| 5 First Trade Provider 可扩展到 VERIFIED 数据源 | 实现待测 | Protocol 与 observation contract |
| 6 当前没有 VERIFIED provider 可接受 | 已确认输入边界 | 当前适配器只读日线 |
| 7 polarity 与顺逆规则 deterministic | 实现待测 | 四种 polarity/year-stem Golden Cases |
| 8 ADR-0017 与实现一致 | Draft | ADR-0017 等 CI 证据后接受 |
| 9 规则不读未来行情/收益优化 | 实现待测 | close-time `as_of` guard；resolver 无行情/收益参数 |
| 10 三类 temporal input 分离 | 实现待测 | temporal contract tests |
| 11 CalendarEngine 23:00 行为未改 | 待回归 | Calendar Golden Cases |
| 12 Date Scan 12:00 行为未改 | 已保留 | `EVALUATION_TIME = "12:00:00"` contract test |
| 13 测试与 CI 无回归 | PENDING | PR #7 当前 commit 的 workflow 尚待运行 |

## 验证记录

| 验证 | 本地结果 | 备注 |
|---|---|---|
| 修改 Python 文件 AST parse | PASS | Codex bundled Python 对 11 个源文件/测试文件完成语法解析 |
| `git diff --check` | PASS | 无 whitespace error |
| Python target/backend tests | NOT RUN | 当前工作树无 `.venv`，系统未安装 Python；bundled Python 不含 pytest，按任务要求交由 PR CI 验证 |
| Calendar/Bazi/Ziwei/Date Scan 回归 | PENDING CI | 需要当前 PR workflow |
| Frontend typecheck/build | NOT RUN locally | `apps/web/node_modules` 不存在，交由 PR CI |
| Seeded E2E | NOT RUN locally | 交由 PR CI |
| CI run 与各 job conclusion | PENDING | 需记录 run id、链接及每个 job 结论 |

> 本文是进行中的验收记录。只有更新为当前 commit 的 CI job 证据后，才能把 F2 写成 PASS 或 ADR-0017/0018 改成 Accepted。
