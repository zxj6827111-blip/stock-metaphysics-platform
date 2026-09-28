# 股票月份、每日十神与阴阳运限闭环验收

- 日期：2026-09-28
- 范围：股票时间轴页面、股票月历 v2、上市档案、首日阴阳来源、研究兼容运限
- 基线：`codex/research-closure-remediation`，实施前 HEAD `4da4e1b7936ce8dcb14b0e2bbece346b6ffb30d9`
- PR：[#8（draft）](https://github.com/zxj6827111-blip/stock-metaphysics-platform/pull/8)
- CI：本记录撰写时的远端检查属于基线提交；本轮最终提交的 CI 结果待推送后核验

## 用户路径与结果

从股票的“时间窗口”页 `/stock/{代码}/timeline` 打开“股票月份与每日十神 · v2”，选择公历年份和月份，保留“全部自然日”显示并运行查询。也可以改用自定义日期范围，或将明细切为“仅已确认交易日”。页面显示实际股票、请求范围、出生口径、日采样时刻和显示条件；月柱由服务端按精确节气时刻切段，日柱和十神也全部来自服务端。

本地真实页面与 `/api/v2/research/fortune/month-calendar` 逐项比对：

| 实际股票/场景 | API 与页面结果 |
|---|---|
| 600519，2026-09-01 至 2026-09-30 | 30 个自然日；9 月跨立秋、白露两个节气月段；9 月 1/2/3 日流日十神依次为七杀、正官、偏印；首日阳，兼容男命假设，实际逆行，运限可用 |
| 002561，同一公历月 | 30 个自然日；9 月 1 日流日十神为伤官；首日阴，兼容女命假设，实际顺行，运限可用 |
| 002561，2026-09-05 至 2026-09-06，筛选已确认交易日 | API 保留 2 个自然日；页面显示明确空状态“所选条件下没有已确认交易日”，不渲染空白表格 |
| 000003，首日阴阳缺失 | 本地上市日出生档案仍生成完整 30 天月/日十神；页面说明阴阳来源缺失，只有运限不可用 |
| 600609，首日交易日证据冲突 | 保留工作簿中的原始阳标签和来源；API 返回 `conflict`，页面显示市场日历冲突原因并禁用运限，月/日结果仍可用 |
| 600519，首日观测日 2001-08-27 | 14:59 查询时方向为 null、运限不可用；15:00 查询时证据才可用并得到 REVERSE，满足收盘可见时点限制 |
| 上游返回 502 | 页面显示服务端错误消息和重试入口，Fortune 时间轴其它区块仍挂载 |

最终隔离验收使用本地真实数据的 `smp.validation.sqlite3` 副本和独立 API 缓存目录。浏览器回归为 4/4 通过；截图保存在本机隔离目录 `data/research-closure-runtime/month-calendar-polarity-20260928-221647/browser-evidence-13/`，Playwright 结果保存在同目录下 `playwright-results-13/`。其中包含 600519、002561 和冲突样本 600609 的首日/运限、节气月段及每日明细截图。

## 出生与计算口径

- `listing_open` 复用本地 `stock_birth_profile`；输出明确标为 `INFERRED`，上市开盘时刻是研究假设，`first_trade_datetime` 仍为 null。
- 2026-09-29 补充核对：工作簿 `总表` 的 `上市日期` 列有 5,395 条可解析记录；其中 5,389 个代码匹配本地 `stock_master`，日期全部与 `listing_date` 及对应 `v2-phase4b-listing_open` 档案的日期一致，未发现缺失或差异；另 6 个代码不在本地主档。因此出生日期无需再写入或覆盖，页面继续复用数据库中已有、与工作簿一致的出生日期及上市开盘假设。
- `MARKET_FIRST_TRADE` 无已观测首笔日期/时间时返回不可用，不回退到上市日期。行情最早观测日还必须与主档上市日期一致。
- 月历、Fortune 时间轴和运限在同一请求里使用相同股票出生档案。历法/十神可用性与历史收益认证范围分离。
- 用户工作簿 `日柱.xlsx` 的 SHA-256：`57a26df309b769d723cc8da8afb4fb6f6a90561b0857c8bae07c5e1289d49eb9`。工作簿涨跌幅按来源原值保留，并核验 `收盘价/开盘价-1`；阴阳标签直接保留工作簿值，不以涨跌幅重新推算。该假设及价格基准在页面展示。
- 600519：观测日 2001-08-27，阳，收盘可见 `2001-08-27T15:00:00+08:00`，对应 REVERSE。
- 002561：观测日 2011-03-03，阴，收盘可见 `2011-03-03T15:00:00+08:00`，对应 FORWARD。
- 项目兼容“男女”仅作为 `stock-luck-cycle-first-day-yinyang-v1` 研究假设输入；界面明确标注股票没有真实性别。未新增财富评分、收益方向或交易结论。

当前 2026-09 月查询实际版本：`cfg-2026.09.1`、`ten-god-v1`、`smx-calendar-1.0.1+lunar-python-1.4.8`、`smx-bazi-native-1.0.1`、`bazi-relation-v3`、`relation-matrix-v2`、`a-share-session-v1`、`stock-luck-cycle-first-day-yinyang-v1`、`fortune-dayun-period-lunar-python-1.4.8-v1`。Fortune 月日结构计算未使用行情收益数据；本机离线行情快照 `tencent_ifzq_gtimg@2026-09-18T20:40:34+0800` 仍为未逐证券认证数据，`research_eligible=false`，不构成已认证或确认性研究资格。

## 工作簿导入与数据库边界

先在备份及验证副本上检查并迁移，再将带来源证据的迁移和导入应用到实际本机数据库：

- 实际库：`data/smp.sqlite3`；Alembic revision `b9c7d81a6e34`；当前完整性检查 `ok`。
- 导入前备份：`data/research-closure-runtime/month-calendar-polarity-20260928-221647/smp.sqlite3.backup`；备份完整性 `ok`。
- 有效工作簿来源记录 5,394 条；与 `stock_master` 匹配 5,388 条，未匹配 6 条。
- 写入字段级证据 5,388 条：5,373 条可用、15 条冲突。已有阴阳及涨跌幅字段 0 条需要更新；冲突标签未覆盖，来源不足的 716 条继续缺失。
- 导入前后主档阴阳分布相同：阳 3,630、阴 1,758、缺失 716；6,104 条 `listing_open` 档案均保留，未改写出生档案。
- 交易日来源/观测日期冲突的 15 条记录仅登记为冲突，不参与运限。无可靠来源的缺失数据没有补造。
- 初期页面联调曾短暂指向实际库。与导入前备份相比，实际库 `chart_artifact` 从 939 条增至 1,011 条（增加 72 条，由本轮真实请求生成）；没有删除或覆盖既有产物。随后最终浏览器验收切换到独立验证副本和新缓存目录。该副作用保留在库中以遵守资产保护要求。
- 最终隔离验证副本 `smp.validation.sqlite3` 在验收前从实际数据副本验证迁移/导入；本轮页面回归对该副本生成结果产物，不再写实际库。

## 验证

- `python -m pytest -m "not ziwei_live" --basetemp=<隔离临时目录>`：2,298 passed、1 skipped、28 deselected；2 个环境警告（Starlette deprecation、pytest cache 目录权限）。
- `python -m pytest -m golden -v --basetemp=<隔离临时目录>`：410 passed、1,917 deselected；仅 pytest cache 目录权限警告。
- 明确泄漏检查（`tests/test_no_future_data_access.py`、两项 `test_asof_*`、`test_oos_no_leak.py`）：41 passed；仅 pytest cache 目录权限警告。
- Web `npm run typecheck`：通过。
- Web 生产 `npm run build`：通过；独立产物目录 `.next-month-calendar-acceptance-3-20260928`，build ID `NjlkC9dRQi6iy28zBY3vW`。
- 本机真实浏览器 `npx playwright test e2e/stock-month-calendar-real-data.spec.ts --project=reference-1672x941 --workers=1`：4 passed。断言页面行数、每条实际十神/干支/藏干、两个节气边界、首日来源/运限状态、API/UI 一致、筛选空状态、缺失/冲突降级和上游错误。
- `python -m alembic heads`：单一 head `b9c7d81a6e34`。
- `services/ziwei-service` smoke：iztro 2.6.1、12 宫、0 errors（该服务代码未改动，按既有运行实例复用）。

本地验证不代替最终 PR CI。提交推送后应在 PR #8 报告每个必需 job 的实际状态；本记录不把旧提交 CI 记作本轮通过。

## 仍然适用的边界

- 首日来源/日期/交易日/市场时段不完整或互相冲突时，运限保持不可用；月日十神独立显示。
- 716 条无可靠阴阳来源记录继续缺失，15 条真实冲突保留并 fail closed。
- 离线行情研究数据尚未认证；本轮闭环只证明本地档案上的传统结构计算和证据呈现，不提供确认性研究资格、股价预测或交易建议。
- 不合并 main，不部署；完成 PR #8 更新和 CI 核验后等待独立复验。
