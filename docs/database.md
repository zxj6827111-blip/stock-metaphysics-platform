# 数据库设计 · Phase 1

> 主库：SQLite（`data/smp.sqlite3`） · Migration：Alembic（`migrations/`）
> 研究层（Phase 2 扩展）：DuckDB + Parquet（`data/research.duckdb`、`data/raw/parquet/`）

---

## 1. 总览

| # | 表 | 作用 | 关键约束 |
|---|---|---|---|
| 1 | `stock_master` | 股票基础资料 | PK `stock_code` |
| 2 | `stock_birth_profile` | 股票出生研究档案（**版本化，不覆盖历史**） | UNIQUE (`stock_code`,`birth_basis`,`birth_profile_version`) |
| 3 | `exchange_session_calendar` | 交易所交易时段（**开盘时刻的唯一来源**） | UNIQUE (`exchange`,`board`,`session_name`,`effective_from`) |
| 4 | `market_bar_daily` | 日行情（含 benchmark） | UNIQUE (`stock_code`,`trade_date`,`adjust`) |
| 5 | `market_fetch_log` | 行情抓取日志（缓存 TTL / 故障诊断） | — |
| 6 | `engine_version` | 引擎版本登记 | UNIQUE (`engine_id`,`engine_version`) |
| 7 | `engine_run` | 引擎运行记录（耗时 / 状态 / 警告） | — |
| 8 | `chart_artifact` | **原始术数盘面（一等数据）** | PK `chart_id` |
| 9 | `factor_definition` | 因子定义（因子字典） | UNIQUE (`factor_id`,`rule_version`) |
| 10 | `factor_observation` | 因子观测值 | UNIQUE (`stock_code`,`as_of`,`factor_id`,`rule_version`) |
| 11 | `classical_book` | 古籍书目 | PK `book_id` |
| 12 | `classical_entry` | 古籍条目（结构化） | PK `entry_id` |
| 13 | `evidence_link` | 证据关联（因子/规则 ↔ 古籍条目） | — |
| 14 | `backtest_experiment` | 研究实验 | PK `experiment_id` |
| 15 | `backtest_result` | 研究结果（按 variant × horizon） | — |
| 16 | `analysis_run` | 分析运行索引（API 查询入口） | PK `analysis_id` |
| — | `alembic_version` | Migration 版本 | — |

**Migration 文件**：`migrations/versions/<rev>_phase1_initial_schema.py`

```bash
python -m alembic upgrade head                  # 应用
python -m alembic revision --autogenerate -m "…" # 生成
python -m alembic downgrade -1                  # 回滚一步
```

> ⚠️ **`alembic.ini` 必须保持纯 ASCII**：Alembic 用系统 locale 编码（中文 Windows 为 GBK）
> 读取该文件，含中文注释会导致 `UnicodeDecodeError`。

---

## 2. 表结构详情

### 2.1 `stock_master` — 股票基础资料

| 列 | 类型 | 说明 |
|---|---|---|
| `stock_code` | TEXT PK | 6 位代码，如 `600519` |
| `wind_code` | TEXT | 带后缀代码，如 `600519.SH` |
| `name` | TEXT | 股票名称 |
| `exchange` | TEXT | `SSE` / `SZSE` / `BSE` / `UNKNOWN` |
| `board` | TEXT | `主板` / `创业板` / `科创板` / `北交所` |
| `industry` | TEXT | 行业 |
| `listing_date` | DATE | **上市日期（出生档案的关键输入）** |
| `total_market_cap` / `circulating_market_cap` | REAL | 市值 |
| `is_active` | BOOL | 是否在市 |
| `source` | TEXT | 数据来源（akshare / builtin / code_prefix_only） |
| `data_quality_json` | JSON | 数据质量（等级 + 说明） |
| `created_at` / `updated_at` | DATETIME | — |

### 2.2 `stock_birth_profile` — 股票出生研究档案

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | — |
| `stock_code` | TEXT FK | → `stock_master` |
| `exchange` | TEXT | 编制时的交易所 |
| `birth_basis` | TEXT | `listing_open` / `ipo_date` / `company_foundation` / `first_trade` / `custom` |
| `birth_datetime` | DATETIME | **出生时刻（naive 本地时间，时区见 `timezone`）** |
| `timezone` | TEXT | 默认 `Asia/Shanghai` |
| `source` | TEXT | 来源描述（`derived:listing_open` 等） |
| `birth_profile_version` | TEXT | 版本（`v1`） |
| `evidence_json` | JSON | **证据链**：上市日 / 首个交易日 / session / 开盘时刻 / 推导过程 / 命中键 |
| `assumptions_json` | JSON | 假设列表（含 `bazi.variant_mode`） |
| `data_quality_json` | JSON | 质量等级 + 分数 + 说明 |
| `variant_mode` | TEXT | `not_applicable`（默认）/ `forward` / `reverse` / `both` |
| `variant_note` | TEXT | 运限假设说明 |
| `ipo_date` / `company_foundation` / `first_trade` / `custom_datetime` | DATE/DATETIME | **预留候选基准** |

**唯一约束的意义**：切换出生模型或提升版本会**插入新行**，绝不覆盖历史，
这样才能做"不同出生模型谁更稳定"的对比回测。

### 2.3 `exchange_session_calendar` — 交易所交易时段

| 列 | 类型 | 说明 |
|---|---|---|
| `exchange` | TEXT | 交易所 |
| `board` | TEXT | 板块（`DEFAULT` 为兜底） |
| `session_name` | TEXT | 时段名（`continuous_trading`） |
| `open_time` | TEXT | **正式开盘时刻**（`09:30:00`） |
| `close_time` | TEXT | 收盘时刻 |
| `timezone` | TEXT | `Asia/Shanghai` |
| `effective_from` / `effective_to` | DATE | 生效区间（如科创板 2019-07-22 起） |
| `note` | TEXT | 说明 |
| `source` | TEXT | 配置来源 |

**这是"股票出生时刻"的唯一样板来源。**
业务代码中**禁止**出现 `09:30` 字面量（由 `tests/test_birth_profile.py` 的 AST 检查强制）。

配置文件：[`config/exchange_session_calendar.json`](config/exchange_session_calendar.json)
（数据库表可由运维覆盖，优先级高于配置文件）。

### 2.4 `market_bar_daily` — 日行情

| 列 | 类型 | 说明 |
|---|---|---|
| `stock_code` | TEXT | 股票代码或指数代码 |
| `trade_date` | DATE | 交易日 |
| `open` / `high` / `low` / `close` | REAL | 价格 |
| `volume` | REAL | 成交量 |
| `amount` | REAL | 成交额 |
| `turnover` | REAL | 换手率 |
| `pct_change` | REAL | 涨跌幅（%） |
| `adjust` | TEXT | 复权方式：`none` / `qfq` / `hfq` |
| `is_benchmark` | BOOL | 是否基准指数 |
| `source` | TEXT | 数据来源 |
| `is_degraded` | BOOL | **是否为降级/合成数据** |

### 2.5 `chart_artifact` — 原始术数盘面（一等数据）

| 列 | 类型 | 说明 |
|---|---|---|
| `chart_id` | TEXT PK | `{engine}-{code}-{as_of}-{rand}` |
| `stock_code` | TEXT | — |
| `engine` | TEXT | `bazi` / `huangli` / `calendar` / … |
| `engine_version` | TEXT | 引擎版本 |
| `config_version` | TEXT | 配置版本 |
| `birth_profile_version` | TEXT | 出生档案版本 |
| `as_of` | DATETIME | 分析基准时间 |
| `input_json` | JSON | **输入**（出生时刻 / 基准 / variant_mode） |
| `raw_chart` | JSON | **完整原始盘面** |
| `assumptions_json` | JSON | 假设 |
| `warnings_json` | JSON | 警告（如格局判定置信度低） |
| `calculated_at` | DATETIME | — |

**为什么必须存原始盘面**：未来规则升级后要能重新审计
"同一时刻、不同引擎版本，盘面是否一致"。只存分数就无法回答。

### 2.6 `factor_definition` / `factor_observation`

**`factor_definition`**（因子字典）

| 列 | 说明 |
|---|---|
| `factor_id` | 如 `B_MONTH_003` |
| `name` / `engine` / `category` | 名称 / 引擎 / 层级 |
| `definition` / `computation` | 定义 / 计算规则 |
| `raw_unit` / `normalized_hint` | 原始值单位 / 归一化说明 |
| `default_direction` | 默认方向（研究假设，非收益方向） |
| `rule_score_meaning` | **显式声明"规则分不是预期收益率"** |
| `rule_version` / `enabled` | 版本 / 启用状态 |
| `requires_json` / `tags_json` | 依赖盘面字段 / 标签 |

**`factor_observation`**（因子观测）

| 列 | 说明 |
|---|---|
| `factor_id` / `stock_code` / `as_of` / `trade_date` | 定位 |
| `engine` / `category` / `name` | 冗余（便于查询） |
| `raw_value_json` | 原始值（可为标量/列表/字典） |
| `normalized_value` | 归一化值（−1 ~ 1） |
| `direction` | −1 / 0 / 1 |
| `rule_score` | **传统规则强度 0–10（不是收益率）** |
| `confidence` | 0–1 |
| `availability` | `ok` / `unavailable` / `partial` / `error` |
| `rule_version` / `engine_version` / `config_version` | 版本 |
| `evidence_json` / `explanation` / `warnings_json` | 可追溯性 |

### 2.7 古籍三表

**`classical_book`**：`book_id` / `title` / `author` / `dynasty` / `domain` / `school` /
`edition` / `provenance` / `license_status` / `authority_weight` / `note`

**`classical_entry`**：`entry_id` / `book_id` / `book` / `domain` / `school` / `chapter` /
`section` / `topic_json` / `original_text` / `normalized_text` / `modern_note` /
`commentary` / `authority_weight` / `source` / `edition` / `provenance` /
`license_status` / `stance_hint` / `applies_to_json`

**`evidence_link`**：`target_type`（factor/rule/analysis）/ `target_id` / `entry_id` /
`stance` / `relevance` / `note`

> `stance_hint` ∈ `supporting` / `counter` / `neutral`。
> 语料中必须同时存在 supporting 与 counter 条目（由测试强制）。

### 2.8 研究两表

**`backtest_experiment`**：`experiment_id` / `kind`（event_study / negative_control）/ `name` /
`factor_ids_json` / `logic` / `universe_json` / `horizons_json` / `date_from` / `date_to` /
`benchmark_code` / `params_json` / `methodology` / `seed` / `status`

**`backtest_result`**：`experiment_id` / `variant`（real / random_birth_date / shift_plus_7d /
shift_minus_7d / random_factor）/ `horizon` / `sample_count` / `up_rate` / `excess_up_rate` /
`mean_return` / `median_return` / `std_return` / `mean_excess_return` / `max_drawdown` /
`mean_max_return` / `extra_json`

> `variant` 字段让真实组与三个对照组共用同一张表，便于对比查询。

### 2.9 `analysis_run` — 分析索引

| 列 | 说明 |
|---|---|
| `analysis_id` | PK，`AN-{as_of}-{code}-{rand}` |
| `stock_code` / `as_of` / `horizon` | 定位 |
| `engines_requested_json` / `engines_completed_json` / `engines_failed_json` | 引擎执行情况 |
| `payload_json` | 完整 `AnalysisRun` 序列化 + `_extras`（黄历快照、因子计数） |
| `versions_json` / `warnings_json` / `duration_ms` | 版本 / 警告 / 耗时 |

> **`_extras` 约定**：`AnalysisRun` 是严格模型（`extra="forbid"`），
> 附加信息统一放在 `_extras` 下，避免污染模型校验。

---

## 3. 典型查询

```sql
-- 某股票的全部出生档案版本（对比不同基准）
SELECT birth_basis, birth_profile_version, birth_datetime, data_quality_json
FROM stock_birth_profile WHERE stock_code = '600519' ORDER BY updated_at DESC;

-- 某次分析的全部正向因子
SELECT factor_id, name, rule_score, confidence, explanation
FROM factor_observation
WHERE stock_code = '600519' AND as_of = '2024-11-15 14:32:00' AND direction = 1
ORDER BY rule_score DESC;

-- 事件研究：真实组 vs 对照组 20 日表现
SELECT variant, sample_count, up_rate, mean_return, mean_excess_return
FROM backtest_result WHERE experiment_id = 'EXP-…' AND horizon = 20;

-- 古籍反证条目
SELECT book, chapter, original_text, provenance
FROM classical_entry WHERE stance_hint = 'counter' AND domain = 'bazi';
```

---

## 4. 备份与迁移

```bash
# 备份（SQLite 需要连同 WAL 一起）
sqlite3 data/smp.sqlite3 ".backup 'data/backup-$(date +%F).sqlite3'"

# 迁移到 PostgreSQL（Phase 2 多用户场景）
export SMP_DATABASE_URL="postgresql+psycopg://user:pass@host/db"
python -m alembic upgrade head
```

> SQLite 已启用 `PRAGMA foreign_keys=ON` 与 `journal_mode=WAL`（见 `src/db/base.py`）。

---

## 5. 已知限制

1. **无独立交易日历表**：交易日仅按周末规则 + 行情数据校验，
   节假日上市会被错误对齐到节假日。Phase 2 应引入 `trading_calendar` 表。
2. **标签未落库**：`_load_label_rows` 每次请求重算（约 1–3 秒）。
   Phase 2 应建 `forward_label` 表并增量更新。
3. **无分区/归档**：`factor_observation` 会随研究规模快速增长
   （3000 股票 × 3000 交易日 × 65 因子 ≈ 5.85 亿行）。
   Phase 2 应把大规模因子搬到 Parquet + DuckDB。
4. **DuckDB 尚未实际使用**：依赖已就位（`src/core/config.py` 中有 `duckdb_path`），
   Phase 1 的查询规模用 SQLite 足够。
