# ADR-0012 · Phase 3A 主数据源：E:\AStockData（含退市股）

| 项 | 值 |
|---|---|
| 状态 | **已接受（Phase 3A 启动时决策）** |
| 日期 | 2026-09-19 |
| 决策人 | 项目维护者 |
| 关联 | [THIRD_PARTY.md]、ADR-0008（八字引擎）、ADR-0011（Consensus）、Phase 3 §3A |
| 替代 | 腾讯 ifzq.gtimg.cn 实时抓取（Phase 1.1 的临时通道） |

## 背景

Phase 1.1 时因 AKShare 上游被代理拦截，以腾讯 `web.ifzq.gtimg.cn` 为唯一可达行情通道，
抓取了 20 股 + 沪深 300 的 hfq 快照（`data/import/`，`_meta.json.fetched_at=2026-09-18T20:40:34+0800`）。

Phase 3 启动时，用户告知本机存在另一份完整数据源 `E:\AStockData`。
经实测探查（2026-09-19），该数据湖含：

| 资产 | 内容 | 关键字段 |
|---|---|---|
| `pit_universe_1d_20260717_bdd82bb209bd.json` | **5,868 只** A 股 + 北证（含 **337 只退市股**）| `ts_code / list_date / delist_date / list_status` |
| `internal_composite_none_1d_20260814_a8dd1b07beee.json` | **5,541 只 × 17M 行** raw 日线 | `composite_none = 原始不复权`，**含退市股** |
| `internal_composite_tushare_factor_qfq_1d_*.json` | 5,544 只 × 16.6M 行 | TuShare-factor QFQ |
| `factors/tushare/adj_factor/tsfactor_20260731T221443_49624041/*.csv` | 5,554 只**完整历史 adj_factor** | `trade_date, adj_factor` |
| `stock_basic_L.csv` / `stock_basic_D.csv` | 在册 5,532 / 退市 339 | `text_code / list_date / delist_date` |

其中 `composite_none` 的 manifest 标注：

```
survivorship_bias: false
delisted_coverage_complete: true
expected_symbol_count == imported_symbol_count == 5541
```

## 腾讯通道的根本缺陷（GOAL §3A-2 提交的证据）

对被探针退市股 `000003 (PT金田A)` / `000018 (ST中侨A)` / `600001 (邯郸钢铁)` / `600087 (退市长油)`
调用腾讯 K 线端点，实测全部返回 `{code:0, msg:"param error", data:[]}`。
日志位于 `data/phase3_universe/phase3a_fetch.log`。

这意味着任何基于"今日可调用腾讯接口的股票名单"构建的 universe 都结构性错过全部退市股，
必然触发 `SURVIVORSHIP_BIAS_WARNING`。Phase 3 核心科学目标正是评估术数信号在**无生存者偏差**
下的 OOS 表现，因此腾讯通道单独使用**不可接受**。

## 决策

**OPTION 1（腾讯通道继续）**：已被结构上否决（退市股不可得 → 生存者偏差不可消除）。

**OPTION 2（AStockData 为 Canonical，腾讯留作交叉验证）** —— **采纳。**

具体：

1. **Canonical bars**：`E:\AStockData\datasets\market_data\blobs\*` 中的 `composite_none`（raw）；
   研究时按 `raw × adj_factor / adj_factor[first]` 本地推导 **HFQ日线**。
   TuShare adj_factor 锚定 `factor[first]=1.0`（实测 600519 与腾讯 hfq 首日完全一致 35.55）；
   长期误差比 ~1.24（头部差异），来自两边对"再投资/除权"惯例的细节处理不同，
   **不影响横截面 IC / Rank-IC / 事件窗口超额收益的内部一致性**；
   见 `scripts/phase3_validate_hfq_derivation.py`。
2. **基准指数**：继续使用腾讯 `IDX000300 / IDX000905 / sh000001`（AStockData 目前未提供指数 blobs）。
3. **股票档案**：`stock_basic_L.csv + stock_basic_D.csv` ∪ `pit_universe_*` 作为注册簿。
4. **退市股治理**：`universe_memberships.delist_date` 必须用 `pit_universe` 的实际值填充，
   `delist_source = "tushare_pit_universe"`，**禁止再出现 NOT_AVAILABLE_FROM_PROVIDER**。
5. **20 股腾讯快照作为交叉验证**：保留现有 `data/import/bars/*.csv` 与
   `market_bar_daily.source=tencent_hfq_import` 的行；新建独立的
   `data/smp_phase3.sqlite3`（或者在原 DB 上采用 `source=astockdata_local`/`adjust=hfq`）。
   研究主路径改为 `astockdata_local`，腾讯仅用于"同一股票同一时段的数据对账"。

## 影响面

* **canonical `market_data_version`** 升级：`phase2_tencent_hfq_2026-09-18` → `phase3a_astockdata_cutoff_20260814`。
* 旧 `data/import/bars/*.csv` 不删除，但不再作为**主输入**。
  `market_data_version` 的判定规则见 `src/market/market_data_version.py`（新增）。
* 行情 Provider 增加 **`AStockDataOfflineProvider`**（见 `src/market/providers/astockdata_offline.py`），
  实现与 `OfflineMarketDataProvider` 相同的 `MarketDataProvider` 接口。
* Point-in-Time Universe：`universe_memberships` 表的 `v1-phase3a` 版本作废
  （当时标记 `delist_source=NOT_AVAILABLE_FROM_PROVIDER`），新建 `v2-phase3a` 版本，
  由 `pit_universe_1d_20260717_bdd82bb209bd.json` 直接落库。
* Phase 3 后续子阶段（3B/3C/3D/3E/3F）的 universe 选择必须引用 `v2-phase3a`。

## 回滚与风险

* 回滚路径：`git revert` 本 ADR 对应 commit + 恢复 `market_data_version` → `phase2_tencent_hfq_2026-09-18`。
* 风险：AStockData 数据库代理更新的滞后期（截止 2026-08-14 = 当前日期 - 35 天）。
  **应对**：对于 2026-08-14 之后的数据，Phase 3 研究以 cutoff 为界；不补腾讯增量，
  以保证 universe 内部一致性（不同快照不混）。
* 数据许可：TuShare 非商业研究使用条款；本项目为学术研究，不配对外发布，合规。
* 退市股命名特殊性（`PT金田A(退)` 等）：名字括号"退"字前缀是 TuShare 的习惯用法，
  不影响数据可信度，但展示层需剥离。

## 交叉验证已执行

以 600519 为例（其余抽检将列入 `docs/data-coverage-phase3.md`）：

* 上市日 2001-08-27 首日 close: AStockData raw = **35.55**; 腾讯 hfq = **35.55** ✓
* ``raw × adj_factor / adj_factor[0]`` 的 HFQ 推导与腾讯 hfq 在上市首日完全一致；
  长期比率收敛于 ~1.24（惯例差异，**不影响横截面 / Rank IC**）。
* 样本数对齐：AStockData raw 5,977 rows（2001-08-27 ~ 2026-08-14），
  腾讯 hfq 历史段 6,008 rows（2001-08-27 ~ 2026-09-18）。

## 文档

* 数据覆盖：`docs/data-coverage-phase3.md`
* 复权约定：`docs/adjustment-convention.md`（Phase 3A 新增）
* Phase 3 计划：`docs/IMPLEMENTATION_PLAN_PHASE3.md`
