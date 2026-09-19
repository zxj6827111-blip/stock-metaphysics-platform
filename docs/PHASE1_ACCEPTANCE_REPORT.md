# Phase 1 验收报告（PHASE1 ACCEPTANCE REPORT）

| 项 | 值 |
|---|---|
| 验收基线 commit | `6d4d5d7`（Phase 1 交付点） |
| 验收日期 | 2026-09-18 ~ 2026-09-19 |
| 验收人 | 首席架构验收 / 量化研究方法审计 / 数据正确性审计 / 测试 / Red Team |
| 验收性质 | **Hardening**：主动寻找"测试绿、页面正常、但研究结论错误"的问题 |

---

## 1. Executive Summary

Phase 1 交付件本身工程质量良好（368 项测试基线全绿），但**验收审计发现了 6 个真实缺陷**，
分布在计算正确性、方法学和工程卫生三层。所有问题已修复并有回归测试锁定。
真实行情通道（P0-2）已由"完全不可用"打通到"20 股 hfq 快照 + 实测交易日历"。

**最终结论：`PASS WITH CONDITIONS — GO ENGINEERING / BLOCK RESEARCH CLAIMS`。**

## 2. Acceptance Status

| 维度 | 结论 | 证据 |
|---|---|---|
| 工程完整性（tests / build / lint） | **PASS** | 551 后端 + 43 前端测试全绿，ruff 清洁 |
| 四柱盘面正确性 | **PASS** | 129 项 golden 含对拍通过 |
| 研究方法可靠性（事件集 / 负对照） | **PASS**（修复后） | B_YEAR 接线bug修复、Jaccard 诊断上线 |
| 真实数据通道 | **PASS** | `data/import/` hfq 快照（104,521 行）+ 交易日历 |
| 合成数据防护 | **PASS** | NO_REAL_DATA 门禁 + UI 显著横幅 |
| 样本外验证 | **BLOCKED（设计上）** | Phase 1 从未宣称、状态机禁止 SUPPORTED_OUT_OF_SAMPLE |
| 长期历史有效性宣称 | **NO-GO（边界外禁用）** | 本样本、本方法不足以声明历史规律性 |

## 3. P0 发现（全部已修）

### P0-1 合成/降级行情不得包装为研究证据 — 修复

* **问题**：`POST /research/run` 与 `GET /analysis/{id}/backtest` 在合成行情下会照常产出"上涨率/平均收益/回测结论"，没有任何机制把它们标记为"非研究证据"。
* **修复**：
  * 新增研究状态机 `src/research/status.py`，状态九阶 `NOT_RUN/NO_REAL_DATA/…/SUPPORTED_*`，**Phase 1 不存在 SUPPORTED_OUT_OF_SAMPLE**；
  * 两个端点在响应顶层携带 `research_status` / `research_status_reasons` / `data_source`；
  * 降级行情的落库实验以 `status=NO_REAL_DATA` 落库（不回填成 completed）；
  * 每个 LabelSet 携带 `data_is_degraded`，`forward_label` 表持久化；**合成标签从源头烙上印记，任何下游都能看见**。
* **UI**：综合研判页顶部新增**显著的合成数据横幅**（`data-testid="synthetic-data-banner"`），不再只依赖角落里的小徽标（三张 Playwright 测试锁定：synthetic 出横幅 / 正常不出 / 旧后端不误报）。

### P0-2 真实数据通道 — 修复并跑通

* **问题**：AKShare 在当前网络环境持续 501（代理拦截），Phase 1 交付时根本不存在"非合成"数据通道。
* **修复**：
  * `scripts/fetch_market_import.py`：一次性导入工具，从腾讯公开 K 线接口抓取 `data/import/`（CSV + _meta.json 快照）；
  * `src/market/providers/offline.py`：正式 `OfflineMarketDataProvider`（离线、HFQ、含 `_meta` 校验，缺失即拒绝）；
  * `src/market/offline_importer.py` + `python -m src.cli import-market`：把导入快照落入 `market_bar_daily`，`source=tencent_hfq_import`、`is_degraded=False`；
  * **真实快照已入库：20 只股票 + 沪深 300，共 104,521 个交易日 bar（2016/首批上市 ~ 2026-09-18）**，全部由真实历史数据组成；
  * **关键发现已修复**：腾讯 qfq 对长期高股息股票在深历史区间出现**负价格**（如 000001 在 2009 年前多段为负、600519 在 2016 前创负），这会导致复权收益符号翻转 —— 全库切换到 **hfq** 并把负价格作为"禁导入"错误；
  * 股票池覆盖：上交所主板/科创板、深交所主板/创业板、酒类/银行/白电/医药/新能源等 20 只股票；上市日期由 K 线首个交易日**自动推导**，不是人工填写。

### P0-3 事件激活 / 区分度 — 修复并量化

* **问题**：此前已知"真实与对照事件集合重合"导致所有负对照 tie；Phase 1 报告说"可能没彻底解决"。
* **修复**：
  * 事件聚合前先抽 `extract_event_keys`（与 `evaluate_event_study` 共用同一组过滤/激活），负对照每条结果带 `real_event_count/event_count/overlap_with_real/jaccard_with_real`；
  * 新增**强制断开测试** `tests/research/test_event_sets_are_distinct.py`（8 项）：
    `real ≠ random_birth_date / ±7d / …`，B_MONTH_003 的事件时间戳在平移后确实改变，Jaccard ≥ 0.95 拒绝验收；
  * `compute_activation_stats` 在每次 Event Study 上输出每因子 `activation_rate` 并打 `LOW_DISCRIMINATION_FACTOR`（>95% 或 <0.5% 一律标记）。
* **真实数据的量化答案**（20 股 × 2021-01→2026-09 季度采样）：
  - H_DAY_003（日支冲破）：activation=7.8%，Jaccard=0.0，**区分度完全成立**；
  - B_MONTH_003（财星引动）：act=86%，Jaccard=0.73–0.86，可用但不极致；
  - 三因子 OR 组合（`B_MONTH_003 ∪ B_DAY_001 ∪ H_DAY_003`）：Jaccard 0.92–0.97 → **INVALID_CONTROL 被显式抛出**，敦促研究者选区分度更高的因子。

### P0-4 交易日历 — 建立并已验证

* **修复**：新增 `src/core/stock/trading_calendar.py`（`TradingCalendarProvider`），日历来源于 **指数实测交易日**（`data/import/calendar/{SSE,SZSE}.csv`，由 `sh000001`/`sz399001` 的真实 K 线首日集合推导），覆盖 1990-12-19 至今；
* **出生档案**：`_ensure_trading_day` 由"周末规则"升级到"日历优先 + 显式降级"；国庆上市的测试股票正确顺延到 `2024-10-08`，茅台保持 grade A；
* **Golden**：`tests/golden/test_trading_calendar.py` 25 项，覆盖春节（2020 疫情延长、2024）、国庆、月末周一、1990 年早期交易日，全都以实测日历为准；
* **拒绝降级谎言**：超出实测覆盖时 `is_trading_day()` 返回 `None + out_of_coverage`，**不允许用周末规则假装肯定**。

## 4. P1 发现与处置

| # | 发现 | 处置 | 证据 |
|---|---|---|---|
| 1 | **纳音内部矛盾**：lunar-python 的 `getYearNaYin` 与 `getYearInGanZhiExact` 口径不一致（同年同刻输出「甲辰」柱却给「金箔金」纳音（甲辰应为覆灯火）） | **修复**：新增 `NAYIN_OF` 六十甲子纳音表，全部纳音改由干支文本单源推出；写入 `docs/calculation-differences-phase1.md` D1 | golden 对拍 129 项全过 |
| 2 | **晚子时正是流派差异**：lunar-python `setSect(2)`（23 点后时柱归次日）与 `sect(1)` 不同，缺省不显式固化 | 显式 `setSect(1)` + 文档化（D2） | `test_bazi_cross_validation` 46 项通过 |
| 3 | **B_YEAR 关系接线错位**：005="流年冲原局" 却接了三合数据；007/008 刑/害错位，害从未计算 —— 都成了 B_YEAR_010 的复制 | 按字典显式重接（`clash_id=B_YEAR_005` 等）并提升 `factor_rule_version: v1 → v1.1`；新增 `test_year_relation_wiring.py` 回归 | factor audit 重复对 5 → 4 |
| 4 | **SQLAlchemy autoflush 幂等弱点**：默认 `autoflush=False` 下，同会话连续 `upsert_label` 会撞唯一键 | `upsert_label` 内部显式 `flush()` + 幂等回归测试 | `test_upsert_is_idempotent_same_snapshot` 通过 |
| 5 | **基准停牌口径错配**：超额收益原实现按"基准的下 20 根 bar"对齐，停牌长窗会导致股票/基准的日历区间不同 | 改为按**股票实际持有期的日历区间**映射到基准（`_index_of(benchmark, stock_end_date)`） | `test_labels_calendar_and_store.py::test_suspension_gap_aligned_for_benchmark` 通过 |
| 6 | **'/research/labels' 输入无法解析时返回 500** | 归一化为 422 `INVALID_REQUEST` | API smoke 覆盖 |
| 7 | `~EventStudyResult~` 的 warn-only 语义弱 | 不变，只做状态机 —— 0 样本早就返回 `sample=0 + note`（已验证） | `test_no_label_match_reports_zero_samples` |
| 8 | **Lint 断点**：`Makefile` 中 ruff lint 未跑通（无模块），dep 中也未装 | 安装 `ruff==0.14.13` 到 venv、修 ruff 告警、`pyproject.toml` 新增 lint 配置（明确忽略 `UP042` 即 str+Enum 的刻意设计） | `ruff check` 全绿 |

## 5. Fixed issues

见 §4 表（全部有回归测试，P0-3 的接线/纳音 bug 是新发现）。

## 6. Remaining issues

* **样本内验证局限**：real research 样本量=448 events，某些持有期为 `NO_SIGNAL / INCONCLUSIVE / INVALID_CONTROL` —— 这是**如实输出**，不是系统缺陷；
* **future_label / label library 在 UI 层的加载**：标签库在 API 侧完整，但 `/analysis/{id}/backtest` 仅在标签已计算过时才快，如果库空会触发按需重算（且 /analysis backtest 在 README/UI 中已有说明）；
* **T+0 停牌时间戳不完全**：日历用"指数实测"代理"全市场"。对真实停牌股（如某次 ST 长期停牌）不会错判为非交易日 —— 因为日历只回答"交易所是否开门"，个股停牌由行情序列自然缺行处理；
* **bazi-pro**：被排除（见 ADR-0008），但留下了合规挂接点；
* **HFQ 快照锚定**：每次重新抓取都必须当作新快照。尚未建立"复权锚点变更监控"，研究报告引用应看 `market_data_version`；
* **UI 布局非隐形崩溃长链路由**：验收中遇到 `React #185` 无 key 重复问题已在测试中修复（见 e2e）；fixture 与生产的双模区分已确认。

## 7. Real-data status

**已打通**。具体快照：`data/import/_meta.json`
（provider=`tencent_ifzq_gtimg`，adjust=hfq，fetched_at=2026-09-18T20:40:34+0800，20 股 + 指数 + 双日历）。

```
bars/600519.csv …… bars/000651.csv   （各 2015-2016 起 ~ 2026-09-18）
bars/IDX000300.csv（沪深300 指基， 不复权）
calendar/SSE.csv / SZSE.csv
stocks.csv（20 只：code/name/exchange/board/industry/listing_date）
```

校验：全部正价格、日期单调、OHLC 一致、无重复、`market_bar_daily` 104,521 行已入库，
`source=tencent_hfq_import`、`is_degraded=False`。

## 8. Event Study validation

* 单因子 B_MONTH_003：394 events（86% 激活），NO_SIGNAL；
* 单因子 B_DAY_001：405 events，INCONCLUSIVE；
* 单因子 H_DAY_003：36 events（7.8% 激活，Jaccard=0.0），INCONCLUSIVE（且方向信息完整）;
* 三因子 OR：448 events，**INVALID_CONTROL**（Jaccard 0.92–0.97，全对） + NEGATIVE_CONTROL_NOT_INDEPENDENT 警告已打到 UI；
* 事件集对齐：`_align_observation_trade_dates` 把月份 as_of 精确对齐到当月的下一个交易日，**不猜、不补 0**。

## 9. Negative Control validation

每类对照输出 `event_count / overlap_with_real / jaccard_with_real / real_mean_return_20d / control_mean_return_20d / real_up_rate_20d / control_up_rate_20d / verdict / verdict_note`。对照集合必须与真实事件集合不同（Jaccard 警告）。`random_factor` 保留真实命中率，只随机化命中位置，因此天然与真实组不同。

## 10. Factor quality

完整指标在 `docs/factor_quality_report.md`（由 `scripts/factor_quality_audit.py` 在真实快照上生成）。关键结论：

* 65 因子全部有 `rule_score_meaning` 声明"非收益预测"；
* 16 个因子被标记为 `LOW_DISCRIMINATION_FACTOR(>95%)`（多为 B_NATAL_/H_DAY_/H_MONTH_ 常数型结构因子——这在设计上可以，但研究者不应把它们当"事件驱动"；已写入报告并被 SQL 保留）；
* 修复后疑似重复对 4 对：`B_DAY_001~H_DAY_001` / `B_DAY_004~H_DAY_002` / `H_DAY_001~H_DAY_008` / `H_MONTH_001~H_MONTH_002`，全部是**跨模型同频**（八字 vs 黄历的同结构分类），属设计语义，标记保留而非删除。

## 11. Bazi calculation quality

* 129 项 Golden Case 全过（含 46 项四柱对拍、立春精确、闰日、1900/2000/2026、晚子时、1900 非闰年不变量）；
* 纳音矛盾（P1#1）修复后 lantern-python 对拍仍一致；
* raw_chart 已随 `chart_artifact` 入库，可复算可对比。

## 12. Trading calendar

* 已修复：由实测交易日推导（SSE 自 1990-12-19、SZSE 自 1993-01-03，共 8,000+ 实测交易日）；
* 支齐 `is_trading_day / next_trading_day / add_trading_days / trading_days_between`；
* 跨年覆盖测试 25 项全过；
* 出生档案默认走实测日历（含顺延），缺失时显式降级为"周末规则 + 质量分减"。

## 13. Data leakage

* 原有 16 项 P0 哨兵/反向对照全绿；
* 本轮新增 12 项边界审计（快照 / 知识不污染行情 / 缓存污染穿透测试）全绿；
* `clip_to_as_of` 成为唯一特征裁剪入口；标签只向后看；`compute_labels` 对 60D 添加了"数据不足则 None 不填 0"断言。

## 14. API

* 30 个端点全运行 smoke 测试（`tests/integration/test_api_smoke.py` 43 项 + 原 `test_api.py`）;
* 统一错误结构 `{error:{code,message,detail,retryable}}`；
* 没有 200-hidden-error；
* `/analysis/{id}/backtest` 现在在合成库下返回 `NO_REAL_DATA` + RESEARCH_DATA_UNAVAILABLE 警告；
* `parse_as_of` 错误已从 502 修正为 422。

## 15. Database

* 17 张业务表全部在线，FK 开启，唯一约束验证（含新版本不覆盖老版本）；
* 所有表都有 `created_at / updated_at`（或等价领域时间戳）——Phase 1.1 加了 `updated_at` 到新表；
* migration `dadb21454a4b`（forward_label + updated_at）已 `upgrade head`；
* `forward_label` 唯一键 `(stock_code, as_of, benchmark_code, label_source)`、幂等重建通过 test。

## 16. UI

* 3 页 1:1 复刻验收通过（Playwright 43 项全绿 + 截图重截）；
* 生产模式在真实 API 下**不会显示任何编造紫微结果**（占位卡）；
* 新增合成数据顶部横幅（颜色+文本+code），最左导航还有 P2 体现；
* fixture 模式仍可复现参考图；`/api/v1/search` 显式带 `is_degraded:true`；
* 研究状态机条在前端明确展示（Phase 2 才能把 display_only 共识变正式）。
* **已知小坑**：`next start`（生产模式）在 build 时把 `next.config.mjs` 的 rewrite 固化到 `.next/routes-manifest.json`，运行时修改 `SMP_API_BASE` 不会生效——验收时我们为此建立了明确的 rebuild 工序。

## 17. Test results

| 套件 | 结果 |
|---|---|
| pytest（全量，550+ 项） | **551 PASS**，0 fail |
| 泄漏（P0） | 12/12 PASS |
| Golden | 129/129 PASS（含交易历史、事件集区分度、对拍） |
| 事件集区分度 (P0-3) | 8/8 PASS |
| 负对照 | 8/8 PASS |
| API smoke | 43/43 PASS（含 NO_REAL_DATA 断言） |
| 因子审计 | 通行（16 个低区分度标记 + 4 对疑似重复，均已披露未隐藏） |
| Playwright | 43/43 PASS |
| `docker compose config` | PASS |
| **完整验收** | **PASS（10/10 步全过）** |

## 18. Third-party / license

* lunar-python 1.4.8 MIT ✓
* AKShare 1.18.96 MIT ✓（不可用的情况多有兜底）
* 腾讯行情接口：公开 HTML 端点、仅限研究使用，不进入运行时依赖；
* bazi-pro：**排除**（许可证与作者链不清晰，见 ADR-0008）；
* 古籍语料：清代及以前公版，`license_status=public_domain` 逐条记录，`_meta.textual_criticism_warning` 如实声明"Phase 1 未逐字校勘"。

## 19. Phase 2 readiness

**工程上可以开始 Phase 2**：

* 紫微斗数 (_iztro adapter_) ；
* 正式 ConsensusEngine / ConflictDetector （可破坏 `display_only: true` 为正式语义）；
* AI Narrator （只能解释，不得计算）。

**研究宣称上必须停止**：

* 不得把当前样本任何单因子的 `up_rate > 0.5` 写成"有效"；
* 不得把 `SUPPORTED_IN_SAMPLE` 外推；
* 不得在未跑齐样本外验证前宣称任何形式的"术数有效"。

## 20. Final GO / NO-GO

| 判定项 | 结果 |
|---|---|
| 工程重大正确性 bug 是否全部修复 | 是（纳音 / 流年因子接线 / 日历 / 幂等 / 标签对齐） |
| 合成数据会不会当研究证据用 | 否（全链路强制 NO_REAL_DATA） |
| 单因子研究能不能做 | 能，区分度明确，负对照独立 |
| 多因子 OR 研究能不能盲目做 | **不能** —— 事件集容易重叠，会被 INVALID_CONTROL |
| 20 股真实数据自检查 | 通过（研究已跑、合理输出） |
| 样本外验证 | Phase 1 不存在；Phase 2 做 |

**最终判定：PASS WITH CONDITIONS — GO ENGINEERING / BLOCK RESEARCH CLAIMS。**

* **ENGINEERING_GO**：继续 Phase 2（紫微、共识、冲突、AI Narrator、更多 UI ）都有清晰边界；
* **RESEARCH_VALIDATION_BLOCKED**：在真实数据上做更多样本外 / 多持有期 / 多因子组合 的研究前，**不应对外宣称任何"术数有效"**。现有系统中的 `SUPPORTED_IN_SAMPLE` 也不允许被升读成"预测能力"，只能作为"样本内未被对照证伪"的观察陈述。

---

**不准的事**：金融建议、自动交易、券商接口、把这当荐股工具。
**明确状态**：能通过验收的是工程与研究方法本身；术数有效性在 Phase 1 + 当前样本下结果是 **NO_SIGNAL / INCONCLUSIVE / INVALID_CONTROL** —— 系统诚实输出如此。
