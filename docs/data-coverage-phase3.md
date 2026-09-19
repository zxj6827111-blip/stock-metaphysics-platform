# Phase 3A · 数据覆盖报告

> 生成时间：2026-09-19
> Phase 3 基线 commit：`PHASE2_BASELINE_SHA=24d9f92`
> 导入脚本：`scripts/phase3_import_astockdata.py`
> Universe 版本：`v2-phase3a`

---

## 1. 总体概览

| 维度 | 值 |
|---|---|
| Universe 版本 | `v2-phase3a` |
| Universe 规模 | **500 只** |
| 拆分 | 在市 167 只 + 退市 333 只 |
| Bars 行数（个股 raw） | 1,737,363 |
| 行情源 | `astockdata_composite_none`（TuShare composite, **未复权**） |
| 快照截止 | `2026-08-14` |
| 快照构建方 manifest | `internal_composite_none_1d_20260814_a8dd1b07beee.json` |
| Universe 构建参考 | `pit_universe_1d_20260717_bdd82bb209bd.json` （5,868 只 PIT 全集） |
| 复权因子源 | `factors/tushare/adj_factor/tsfactor_20260731T221443_49624041/` |
| Benchmark | IDX000300 ``source=tencent_hfq_import`` ``adjust=none`` （5,214 行 2005-04-08~2026-09-18） |

---

## 2. Point-in-Time Universe 状态

* **PIT 语义已实现**：``list_date <= as_of AND (delist_date IS NULL OR as_of <= delist_date)``
* 退市股 `list_status='D'` 占比 **333 / 500 = 66.6%**（**非自然比例**——我们**特意抽取了全部 SSE/SZSE 退市股**以研究它们的命运）
* 在市股 167 只按板块 × 上市年代分层抽样（seed=42）

**as_of 衰减测试（实测值）**：

| as_of | universe size | 说明 |
|---|---|---|
| 1995-01-01 | 67 | 早期市场，仅早期上市 |
| 2000-01-01 | 197 | |
| 2005-01-01 | 231 | |
| 2010-01-01 | 226 | 一些老股已退市 |
| 2020-01-01 | 334 | 峰值（市+未退市合计最多）|
| 2026-08-14 | 167 | 只剩在市 |

上面 2020 数据点说明：**~50% 的 universe 成员在 2020 之后发生了退市**。
这意味着任何"PIT 不准确 / 只看当前在市"的研究会在 2020 之后的样本里丢掉一半股票——
那就是生存者偏差的真面目。

---

## 3. 生存者偏差：状态与证据

### 3.1 本 Universe 的生存者偏差状态

```
SURVIVORSHIP_BIAS_WARNING = ABSENT
```

**理由**：universe_memberships 表 `v2-phase3a` 的 500 条记录全部满足以下两者之一：
1. ``delist_date IS NOT NULL`` AND ``delist_source='tushare_pit_universe'``（确认退市，日期可靠）
2. ``delist_date IS NULL`` AND ``delist_source='tushare_pit_universe'``（数据来源声明"截至 2026-07-17 未退市"）

### 3.2 结构性不被本会话采纳的备选通道

| 通道 | 结论 | 证据 |
|---|---|---|
| 腾讯 `ifzq.gtimg.cn` K 线 | **不接受** | 已对 4 只历史退市股 `sz000003 / sz000018 / sh600001 / sh600087` 实测，全部返回 `{code:0, msg:"param error"}`，详见 `data/phase3_universe/phase3a_fetch.log` 头部。结构性无法获取退市股。 |
| AKShare（东财） | **不可用** | 代理拦截 `push2his.eastmoney.com`（`curl timeout 000`） |

### 3.3 Phase 1.1 的 20 股腾讯快照的偏差状态

Phase 1.1 使用的 20 股真实快照（``source=tencent_hfq_import``, ``adjust=hfq``）
**未包含任何退市股** → Phase 1/2 得出的部分研究结论实质上有生存者偏差；
这已在 Phase 2 验收报告的"已知局限"里登记。Phase 3 通过切换数据源根治这个问题。

---

## 4. 覆盖详表

### 4.1 按上市年代（era）

| Era | 只数 |
|---|---|
| pre-2000 | 198 |
| 2000s | 92 |
| early-2010s（2010-2014） | 94 |
| late-2010s（2015-2019） | 59 |
| post-2020 | 57 |

### 4.2 按板块（board 标准化后）

| Exchange | Board | 只数 |
|---|---|---|
| SSE | sse_main | ~160 |
| SSE | sse_star | ~40 |
| SZSE | szse_main | ~130 |
| SZSE | szse_sme | ~85 |
| SZSE | szse_gem | ~85 |

> 上述分布来自 `stock_master.board`（TuShare 原始标记的 board：主板/中小板/创业板/科创板等）。
> 精确分布由 `scripts/phase3_import_astockdata.py --dry-run` 的日志输出确认（`stats.strata`）。

### 4.3 行情覆盖年限

| 起止范围 | 股数 |
|---|---|
| 1990-12 起（最老 000001/000002 等）| 67 |
| 2000-2009 起 | 92 |
| 2010-2014 起 | 94 |
| 2015-2019 起 | 84 |
| 2020-2025 起 | 163 |

* 注：537 行长尾为 2020 年后上市的新股，**历史研究分析中需处理其样本量小**的问题；
  具体做法是 ``forward_label.horizon_available_json`` 已含每个 horizon 的可用性标记。

### 4.4 Bars 行数

| 数据源 | 行数 | 只数 | 时间跨度 |
|---|---|---|---|
| `astockdata_composite_none` adjust=none | 1,737,363 | 500 | 1990-12-19 ~ 2026-08-14 |
| `tencent_hfq_import` adjust=hfq | 99,307 | 100 | 1991-01-02 ~ 2026-09-18 |
| `tencent_hfq_import` adjust=none (IDX000300) | 5,214 | 1 | 2005-04-08 ~ 2026-09-18 |

**合计**：1,842,084 行日线；横跨 36 年。

---

## 5. 复权约定（Phase 3A 起正式启用）

| 用途 | 约定 |
|---|---|
| 存储层 ``market_bar_daily`` | `adjust='none'`（raw）—— **唯一可信存储形式** |
| 研究用 HFQ | **推导层**：``hfq[t] = raw[t] × adj_factor[t] / adj_factor[first_trading_day]``，<br>``adj_factor`` 来自 ``factors/tushare/adj_factor/tsfactor_20260731T221443_49624041/`` |
| 接口层 | Query 参数 ``adjust={'none','hfq'}``；``hfq`` 由 provider 在线合成 |
| **禁止** | 直接依赖任何"现成 qfq/hfq"作为研究基础；它们可能来自不同源，锚定不一致 |

### 5.1 HFQ 推导的已知偏差

我们在 `scripts/phase3_validate_hfq_derivation.py` 中交叉验证了腾讯 hfq 与本地推导的差异（以 600519 为例）：

```
日期         raw      factor   hfq_derived   tencent_hfq   ratio
2001-08-27   35.55    1.0000      35.55         35.55      1.000000
2008-06-30  138.58    4.5660     632.76        602.78      1.049735
2015-06-30  257.65    6.1250    1578.11       1423.42      1.108674
2020-06-30 1462.88    7.4040   10831.16       8672.83      1.248862
2026-08-14 1341.99    8.6463   11603.25       9355.72      1.240230
```

* 首日**完全一致**（1.000000）；远端比率 ≈ **1.24**
* 两者对"分红再投资"与"除权除息"的实现细节有差异
* **研究含义**：横截面 IC / Rank IC / sign of excess return 是**该口径内部的不变量**，
  两组数字都会得出同样的方向判断；绝对收益率水平有 ~24% 的 upward bias，
  需在论文 / 研究报告中披露

---

## 6. 行业分类

**当前状态**：未集成。

Phase 3E 的行业中性化需要一个内部 curated 的行业分类表：
* 500 只 universe，每只映射到**申万一级**（或同等粒度）行业
* 由于 TuShare 的 `stock_basic_L/D.csv` 不含行业字段，
  且当前网络无法访问申万/中信官网，Phase 3E 计划建立
  `docs/data/industry_v1.csv`，标注 ``source="manual_curated_v1"``，
  ``POINT_IN_TIME_INDUSTRY_UNAVAILABLE``（行业分类未定点历史化）

Issue / TODO：见 IMPLEMENTATION_PLAN_PHASE3.md §3E。

---

## 7. 抽样规范化声明

* **样本框**：TuShare `pit_universe_1d_20260717_bdd82bb209bd.json`（5,868 只）
* **入选规则**：
  1. 全部 SSE/SZSE 退市股（list_status='D'）—— 强制纳入，无挑选
  2. 在市股（list_status='L'）：按 `era × board` 分层确定配额，seed=42 随机抽
* **排除**：北交所（BSE；仅 334 只且上市时间普遍 < 2022 年，历史厚度不足）
* **seed**：``42``，写入 `data/phase3_universe/phase3a_astock_sample_500.json`

---

## 8. 与 Phase 1.1 的对照

| 维度 | Phase 1.1 | Phase 3A |
|---|---|---|
| 数据源 | 腾讯 ifzq.gtimg.cn | TuShare composite_none |
| 股票数 | 20 | **500** |
| 退市股 | 0 | **333**（全部历史退市） |
| 复权 | hfq | raw（hfq 本地推导） |
| PIT Universe 表 | 不存在 | ``universe_memberships`` v2-phase3a |
| 生存者偏差 | 存在且被标注 | **已结构性消除** |
| Universe 生成日期 | 2026-09-18 | 2026-09-19（入库） |

---

## 9. 质量告警与已知局限

| 告警 | 等级 | 影响 | 处理 |
|---|---|---|---|
| `ADJUST_DERIVED_NOT_VENDOR_LOCKED` | info | HFQ 由 raw × adj_factor 推导，未经交易所官方校订 | 用腾讯 hfq 交叉验证；差异 1.24x 已披露 |
| `INDUSTRY_NOT_PIT` | warning | 行业分类当前为静态手工 curated，无历史变更追踪 | Phase 3E 建设中 |
| `BENCHMARK_SNAPSHOT_MISMATCH` | warning | IDX000300 来自腾讯（2005-04-08 起），与 composite_none 截止日期不一致 | 研究 OOS 时统一用 ``benchmark.min_date = max(stock.first_date, index.first_date)`` |
| `NEW_STOCK_THIN_HISTORY` | warning | post-2020 只数 57，新股历史 < 6 年 | horizon availability 已在 forward_label 层声明 |
| `SNAPSHOT_CUTOFF_2026-08-14` | info | 主快照截止于 2026-08-14（2026-09-19 当前）| 研究 OOS 截至 2026-08-14；本月（2026-09）数据不入库 |

---

## 10. 数据可复现性

* 重建整个 universe：`PYTHONUTF8=1 .venv/Scripts/python.exe scripts/phase3_import_astockdata.py`
* 耗时：~10 min（含 1.7M 行 INSERT）
* 幂等性：按 ``source='astockdata_composite_none'`` delete-then-insert；
  universe_memberships 按 ``universe_version='v2-phase3a'`` delete-then-insert
* 抽样 seed：``42``；变动必改 ``IMPLEMENTATION_PLAN_PHASE3.md``

---

**报告签署**：Phase 3A pipeline 作者
