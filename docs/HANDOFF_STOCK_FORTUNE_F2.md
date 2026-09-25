# Stock Fortune Engine V1 / F2 交接与验收

- **状态**：PASS（实现 commit CI 全绿；文档提交的当前 head CI 由 PR #7 继续验证）
- **As-of**：2026-09-25
- **分支**：`feat/stock-fortune-engine-v1`
- **PR**：#7（Draft）
- **起始 HEAD**：`f35d66c3f658bee8a8a0f4f7631d13d5d68491de`
- **验收实现 commit / CI run**：`fee90843ba9b1a0826cc9da096802b8f83523c21` / [36154464013](https://github.com/zxj6827111-blip/stock-metaphysics-platform/actions/runs/36154464013)

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
| 1 日线只表达最早可观测交易日期 | PASS | `DailyBarFirstTradeProvider` 与 provider contract tests；backend CI |
| 2 session 开盘推定值标记 INFERRED | PASS | birth resolver/profile contract tests；backend CI |
| 3 无 intraday 时 `first_trade_datetime=null` | PASS | provider / resolver contract tests；backend CI |
| 4 推定值保存 provenance/version | PASS | source、source version、首个观测日期、timezone、session/config/policy version、reason、assumptions 与 precision assertions |
| 5 First Trade Provider 可扩展到 VERIFIED 数据源 | PASS | `FirstTradeProvider` 与 `VERIFIED_DATETIME` observation contract |
| 6 当前没有 VERIFIED provider 可接受 | PASS | 正式日线 adapter 仅报告 observed date；未伪造 verified provider |
| 7 polarity 与顺逆规则 deterministic | PASS | polarity/year-stem Golden Cases 与 deterministic replay tests |
| 8 ADR-0017 与实现一致 | PASS | ADR-0017 `已接受(Accepted)`；代码及 CI run 36154464013 |
| 9 规则不读未来行情/收益优化 | PASS | 收盘时点 `as_of` guard 与 fail-closed tests；方向 resolver 不接收价格或收益序列 |
| 10 三类 temporal input 分离 | PASS | exact/session-date/civil-date contract tests，含 22:59、23:00、23:01、09:30、15:00 与 timezone-aware cases |
| 11 CalendarEngine 23:00 行为未改 | PASS | Calendar Golden / backend suite；改动未触及 CalendarEngine |
| 12 Date Scan 12:00 行为未改 | PASS | `EVALUATION_TIME = "12:00:00"` contract 与 seeded Date Scan E2E |
| 13 测试与 CI 无回归 | PASS（实现 commit） | PR #7 run 36154464013 的五个 required jobs 全部 success；文档提交后的 workflow 另由 PR 实时追踪 |

## 验证记录

| 验证 | 本地结果 | 备注 |
|---|---|---|
| 修改 Python 文件 AST parse | PASS | Codex bundled Python 对 11 个源文件/测试文件完成语法解析 |
| `git diff --check` | PASS | 无 whitespace error |
| Python backend suite | PASS in CI | `python -m pytest -q -m "not ziwei_live"`: 2144 passed, 20 skipped, 28 deselected；run 36154464013 |
| Ziwei + Golden regression | PASS in CI | Node transport availability asserted; engine/factor/golden/cross-engine tests: 331 passed；run 36154464013 |
| Calendar/Bazi/Date Scan regression | PASS in CI | Included in backend suite; Date Scan seeded E2E also passed |
| Frontend typecheck | PASS in CI | `frontend-typecheck` job; run 36154464013 |
| Frontend build | PASS in CI | `frontend-build` job; run 36154464013 |
| Seeded E2E | PASS in CI | `frontend e2e (seeded date-scan)`: 7 passed; run 36154464013 |
| CI run 与各 job conclusion | PASS | `backend core (python)`, `frontend e2e (seeded date-scan)`, `frontend-build`, `frontend-typecheck`, `ziwei engine + golden (node services)` 全部 success；run [36154464013](https://github.com/zxj6827111-blip/stock-metaphysics-platform/actions/runs/36154464013) |

> 上述 run 验收的是实现代码 commit `fee90843ba9b1a0826cc9da096802b8f83523c21`。本 handoff 与 ADR 的后续文档提交不改动代码；其 PR #7 CI 必须保持全绿，才视为最终分支交付无回归。PR 维持 Draft，未 merge、未标记 Ready。
