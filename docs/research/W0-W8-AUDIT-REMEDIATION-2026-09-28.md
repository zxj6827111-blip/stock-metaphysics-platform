# W0–W8 独立审计整改与限域验收

- **验收日期**：2026-09-28
- **范围**：R1–R5 的限域软件整改、本机验收与 F5 资产清点
- **整改分支**：`codex/research-closure-remediation`
- **W1–W8 起点**：`55dc4fd7f5d9976a995ee0176aa5f803b35a2ddd`（当时本地 `main`；含既有 W1–W8 成果）
- **最近核对的远端 main 快照**：`4345cdaa19c709a97ee15d963ec0e833ff268344`
- **交付边界**：此报告只记录本机证据。PR、最终提交和 CI 结论由本轮交付回报按最终远端状态给出；本轮不合并 main、不部署。

## 整改与验收对应

| 审计项 | 修复位置 | 回归覆盖 | 实际结果 |
|---|---|---|---|
| R1 认证范围准入 | `src/research/certified_scopes.py`、`src/research/historical_dataset_event_study.py`、`src/core/schemas/research_v2.py` | `tests/integration/test_api_research_v2.py`：部分/完整越界、错误证券、证书和版本不匹配、未登记数据集、缺失标签、范围内零命中 | 2010–2020 与部分越界请求返回 `OUTSIDE_CERTIFIED_SCOPE`、保留原始日期且不统计裁剪子集；600519 返回证券未认证；错误版本和证书明确不可用；范围内无事件与样本不足使用不同结果状态。真实 API 与集成回归均通过。 |
| R2 条件表达与传递 | `apps/web/app/research/date-scan/page.tsx`、`apps/web/app/research/history/page.tsx`、`apps/web/lib/reportExport.ts`、v2 查询 API | 精确 relation/Ten-God 集成用例；`w7-research-closure.spec.ts`、`w8-local-runtime.spec.ts` | 日期扫描链接保留关系类型、激活、来源/目标上下文、柱位和组件；目标日与历史区间分开。正财按类别字段精确匹配。条件组合为 AND；证券—日期—因子观察数及证券日期数分别报告，保留旧统计单位。浏览器 JSON/Markdown 报告回显执行条件和 API 结果。 |
| R3 指标、页面与 Fortune 时间轴 | `src/research/labels/horizon_returns.py`、`src/research/historical_dataset.py`、`apps/web/app/stock/[code]/backtest/page.tsx`、`apps/web/components/research/StockHistoricalV2Panel.tsx`、`apps/web/components/research/FortuneTimelineV2Panel.tsx` | 标签边界/缺失测试、API 风险指标测试、W7/W8 浏览器流程 | 1/5/10/20/60 个后续交易 bar 均贯通个股、基准、超额收益及 MFE/MAE/MDD；原股票历史页读取 v2，v1 明示 legacy。Fortune 时间轴可调整日期范围、日期口径、流日十神及服务端关系目录条件；页面回显服务端实际条件。 |
| R4 F5 与 W6 | `docs/research/F5-ASSET-RECONCILIATION-2026-09-28.md`、`docs/ADR/ADR-0025-f5-historical-research-asset-boundary.md`、`docs/ADR/README.md` | 逐项对照 Fortune worktree 文件状态及 W6 冻结协议/报告 | Fortune 未提交候选资产留在原 worktree；主仓库没有整体导入或删除。ADR-0021 同号冲突由 ADR-0025 Draft 说明。78 项真实限域结果均为 `INSUFFICIENT_SAMPLE`；置换=0、bootstrap=0，均为 `NOT_RUN`；无 confirmation/OOS 资格，EXP-003 未配置。 |
| R5 本机验收 | `scripts/astrology_calendar.py`、`tests/test_astrology_calendar.py`、隔离验收数据库和缓存 | Python、泄漏、W7/W8 Playwright、TypeScript、Next production build、W4 独立审计 | 使用本机 8100/8000/3000 端口；数据复制到 `data/research-closure-runtime/` 隔离根，原数据库与冻结产物未改写。每轮冷扫描前重启本任务 API；服务结束后 3000/8000/8100 均无响应。 |

## 认证范围、数据与独立复算

| 项目 | 实测值 |
|---|---|
| W4 dataset | `w4-certified-002561-20120223-20180514-v3-path-risk`；SHA-256 `1be932385a9531c9e7b7ce0847fb872b273248f06453d3a73d6fb0970d34b852`；schema `w4-historical-panel-v2` |
| W2 certificate | `w2-szse-002561-20120223-20180514-v1`；SHA-256 `f8eabbf0223d6dbd28ea3343438c68944731ffc46a7d33eff359a91a6b19cb75`；W2 manifest SHA-256 `e60d137e47073f1891d83544d0b382e9010be1063ca3764eee85f878e7da9d6e` |
| 资格范围 | SZSE 002561，2012-02-23 至 2018-05-14，1,513 行、features/outcomes 各 7 个分片；仅限域探索，非确认性/OOS |
| 输入版本 | label `w3-hfq-adjfactor-v3`；raw `overlay_v1_l2_composite_r3_tushare_none_1d_20260814_f8d20d528543_wm20260924_seq00000005`；factor `overlay_v1_factor_r3_tushare_adjfactor_1d_20260814_a4a1109b4c91_wm20260924_seq00000006`；config `cfg-2026.09.1`；Bazi `smx-bazi-native-1.0.1`；rule `v1.1` / `bazi-relation-v3`；benchmark `000300`、Tencent snapshot、`adjustment=none` |
| 盘面引用 | 独立重建并核验 SQLite canonical payload 4,539 个，mismatch=0 |
| 收益标签 | 独立计算 7,565 个有效收益窗口和 7,565 个基准窗口，容差 0；1/5/10/20/60 日每项 return/benchmark/excess 均为 1,513/1,513 |
| 路径风险 | 独立复算 22,695 个 MFE/MAE/MDD 值，容差 0。MFE/MAE 是事件日收盘后至周期末 adjusted high/low 相对事件日 adjusted close 的变动；MDD 是事件日收盘起，峰值至后续谷值的最大非负回撤，和样本最大亏损分列。缺少路径或标签保留 null/缺失计数；盈亏比缺少正收益或负收益组时为不可用，不产生无穷值。 |

收益、benchmark、excess、胜率、样本最大收益/最大亏损和盈亏比按固定 horizon 收益样本汇总；MFE、MAE、MDD 使用路径数据，均以比例值记录，并携带样本数、缺失数和定义。1/5/20 日是页面主周期；数据集保留原计划登记的 1/5/10/20/60 日标签。v1 接口和历史语义保留，v2 新数据只写新 dataset ID。

## 页面、API、缓存和报告回放

- W7 浏览器：4/4 通过。W8 本机真实浏览器：4/4 通过。类型检查和 Next.js 15.5.25 production build 通过。
- W8 页面覆盖：首页数据截止/认证状态，日期与单股 v2 查询，JSON 导出一致性，冻结实验报告读取，真实 Fortune 时间轴；另覆盖缺失结果和模拟上游 503 状态。
- 日期扫描目标为 2026-09-29。API 重启后首次请求 `cache.hit=false`，没有 `RELATION_SCAN_NATAL_FALLBACK`；三次最终验收冷扫描分别为 9.7–11.5 秒，未将结果缓存命中作为冷启动通过。
- Fortune live provider 为 `akshare-1.18.96`，系统行情 cutoff 当前返回 null，002561 首笔日线请求实际不可用。Fortune v2 如实返回 `UNKNOWN`、空的首日/出生时刻和“不从 listing_date/IPO 元数据回填”的原因；浏览器验证范围及十神/六合条件可编辑、请求准确送达，响应逐项回显。缺少行情证据时不声称已产生可用原局事件。
- 六合直接 v2 全认证范围查询：`B_DAY_003`、day → natal/year、branch，命中 126 个证券日期观察；正财使用 `B_DAY_005.raw_value` 的 `DAILY/day` 类别条件，全范围 151/1,513。页面短区间验收的统计单位仍是因子观察；不会把 486 个观察误报为 486 个证券日期。
- 本机 API 版本 `0.2.0`；隔离 SQLite、W4 分片副本、六份冻结实验报告和运行缓存都留在未跟踪的 `data/research-closure-runtime/`，未加入 Git。

## Python 与前端验证

- 全 Python：`pytest -m "not ziwei_live"`：2,287 passed、1 skipped、28 deselected。默认数据根下跳过项依赖版本匹配的 natal cache；在隔离验收数据根用版本匹配输入单独运行后通过 1 项。
- 泄漏与时间边界：无未来数据测试 16 passed；as-of/OOS 相关测试 25 passed。
- 隔离路径变更后：`tests/test_astrology_calendar.py` 20 passed；相关两通道集成测试 1 passed。
- 前端：`npm run typecheck` PASS；`npm run build` PASS；W7 4/4、W8 4/4。
- 独立数据审计：`scripts/audit_w4_limited_scope.py` 对隔离数据副本通过；保留 0 mismatch/0 tolerance 结果。

## F5 资产及资格结论

`F5-ASSET-RECONCILIATION-2026-09-28.md` 将 Fortune worktree 的 `src/research/fortune_f5/`、对应测试、F5B/B.1 构建脚本、F5 Draft ADR 和数据认证报告列为保留的候选/历史依据；不导入整目录、不清理 worktree。主仓库 W6 协议和报告另行保留。算法测试 PASS 仅表示工程实现；真实限域运行有 78 个 `INSUFFICIENT_SAMPLE` 结果。没有可置换日期，置换与移动块 bootstrap 实际次数均为 0，置信区间/显著性检验 `NOT_RUN`。没有有效 VALIDATION/OOS 样本，不具确认性资格；`F5-EXP-003` 未配置。

## 仍然开放的边界

- 全 PIT 股票池仍是 `COVERAGE_INCOMPLETE`；本次仅准入单只 002561 与证书内日期，不扩大市场范围。
- Fortune v2 的真实首日行情在当前本机 provider 不可用；API 和页面保留 `UNKNOWN`，需要可核验行情来源后才能提升该链路的可用性。
- 真实结果是限域历史描述；W6 无确认性/OOS 结论。不得改窗口、股票池或规则制造显著性。
- 远端交付和 CI 状态按最终草稿 PR 与其实际 workflow jobs 单独报告；远端 main 未合并，本轮不部署。
