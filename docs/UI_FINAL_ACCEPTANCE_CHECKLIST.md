# UI 最终收尾与发布前验收 · 执行清单

- **分支**：`codex/ui-final-polish-acceptance`（从 `e2ef2dd` 新建；主目录内切分支，未建 worktree、未复制项目、未合并 main）
- **基线提交**：`e2ef2dd`（= `28f3577` 黄历/时间窗口/品牌视觉 + `7e25d69` 报告哈希 + `e2ef2dd` 官方公布交易日历与剩余五页）
- **同名分支检查**：建立前 `git branch -a | grep final-polish` 无结果，未覆盖任何既有分支
- **并发写入检查**：发现另一会话在同一目录运行 `next dev -p 3000`（PID 32620/32620）与
  `uvicorn --port 8000`（PID 49116）；**全程未触碰这两个进程**，本轮所有构建与验收走独立端口与独立输出目录
- **状态定义**：待办 / 进行中 / 已验证 / 外部阻塞 / 待人工确认
  - 「外部阻塞」只用于有明确证据、且本轮无法通过任何本地操作解除的项
  - 「功能缺失」「数据缺失」「外部来源限制」三者严格区分

> 本清单是**过程记录**，最终结论见 `docs/UI_FINAL_POLISH_REPORT.md` 与
> `docs/UI_FINAL_RELEASE_READINESS.md`。

---

## 0. 验收环境（可复现）

| 项 | 值 |
|---|---|
| 隔离后端 | `uvicorn apps.api.main:app --port 8101`，`SMP_DATA_DIR=output/ui-final/iso/data`（共享库的 sqlite backup 快照，654 MB，`market_bar_daily=1,841,884` / `stock_master=6,104` / `backtest_experiment=56`） |
| 行情通道 | `SMP_MARKET_PROVIDER=vendor_parquet`（供应商全市场 Parquet，真实）+ `SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK=false`（**禁止静默降级到合成行情**） |
| 隔离前端 | `next build`（`NEXT_DIST_DIR=.next-e2e`，避免与另一会话的 dev 产物互相覆盖）→ `next start -p 3111`，`SMP_API_BASE=http://127.0.0.1:8101` |
| 隔离脚本 | `output/ui-final/isolate_db.py`（只读源库 + backup API，避免 WAL 丢失） |

**与上一轮的关键差别**：上一轮"真实模式"验收用的是 `SMP_MARKET_PROVIDER=synthetic`。
本轮改为真实供应商 Parquet 通道 —— "访问真实 API"不等于"使用真实行情"。

---

## 1. 上轮成果复核

| # | 项目 | 状态 | 证据 |
|---|---|---|---|
| 1.1 | 上轮真实模式验收用的是 synthetic 行情 | **已验证（本轮补上真实通道）** | 隔离实例 `SMP_MARKET_PROVIDER=vendor_parquet`；`output/ui-final/real-acceptance.json` 45 项全通过；`688981` 数据来自供应商仓库（1,495 bars，`2020-07-16`~`2026-09-18`） |
| 1.2 | Playwright 119 passed / 4 skipped 的 4 项 live 跳过条件 | **已验证（已执行）** | 跳过条件为 `apps/web/e2e/r2-calendar-window.spec.ts:275` 的 `test.skip(!LIVE, "需要 SMP_E2E_LIVE_API=1 与隔离后端")`；本轮以 `SMP_E2E_LIVE_API=1` + 隔离后端执行，4 项全通过 |
| 1.3 | 1440×900 项目可能只匹配 `layout.spec.ts` | **已验证并修复** | 原配置 `testMatch: /layout\.spec\.ts/`；改为包含新增的 `viewport-1440-pages.spec.ts`（十页逐页适配 + 关键交互 + 几何门禁），见 `apps/web/playwright.config.ts` |
| 1.4 | 日历/时间窗口/黄历缓存身份是否真正包含"会改变结果的内容" | **发现缺陷并修复** | 见 §4.1 |
| 1.5 | 紫微首屏压缩后完整星曜是否可访问 | **发现缺陷并修复** | 见 §4.2 |

---

## 2. 公共视觉

| # | 项目 | 状态 | 证据 |
|---|---|---|---|
| 2.1 | 字体实际加载（按族断言 `document.fonts`） | 已验证 | `capture-final.mjs` 的 `waitForFonts()` 逐族 `load` + `check`；`geometry.json.<page>.fonts` 记录 `serif/sans` 命中结果 |
| 2.2 | Logo 轮廓/大小/留白 | 已验证（沿用上轮成果） | `components/brand/BrandMark.tsx` 自绘 SVG，`data-brand-mark-version="brand-mark-v1"`；本轮未改动 |
| 2.3 | 页面背景/纹理/边框/阴影/图标 | 已验证 | `globals.css` design tokens（无位图底纹，`body::before` 为径向渐变） |
| 2.4 | 上下文栏操作区默认可见 | 已验证 | `viewport-1440-pages.spec.ts`「上下文栏三个操作按钮默认可见」在 1672/1440 双视口通过：按钮右缘必须落在上下文栏内 |
| 2.5 | 新增操作不得把上下文栏挤出容器 | 已验证 | 新增「导出报告」菜单 + 「本机自选」后重跑上述用例通过 |
| 2.6 | Loading / Empty / Error / Partial 状态齐备 | 已验证 | 各页保留 `SectionState` 分区三态；本轮新增导出失败反馈（`export-feedback`）与空态说明 |
| 2.7 | 全站不缩小文字、不裁切按钮以过首屏检查 | 已验证 | 无字号下调改动；周度排名表改为**可横向滚动容器**（保留全部六列，不裁列） |

---

## 3. 十页逐页

| # | 页面 | 状态 | 证据 |
|---|---|---|---|
| 3.1 | 01 首页 | 已验证 | `candidate/01-home-1672.png` + `01-home-compare.png` |
| 3.2 | 02 综合研判 | 已验证 + 交互增强 | 导出菜单三格式（Markdown / 可打印 HTML / 结构化 JSON）实际下载并校验内容 |
| 3.3 | 03 八字详情 | 已验证 | `candidate/03-bazi-*` |
| 3.4 | 04 紫微斗数详情 | 已验证 + 缺陷修复 | 十二宫逐宫明细入口（12/12 可展开、内容与盘面一致）；首屏几何门禁通过 |
| 3.5 | 05 历史验证 | 已验证 | 持有期对比卡进入首屏；负对照失效实验醒目 |
| 3.6 | 06 因子字典 | 已验证 | 真实因子注册表（114 条），历史验证区为空态而非编造 |
| 3.7 | 07 模型分歧中心 | 已验证 | 三场景（no_conflict / conflict / engine_unavailable）各自截图 |
| 3.8 | 08 黄历 / 日课 | 已验证 | 未来交易日日期卡三层日历来源逐卡标注 |
| 3.9 | 09 古籍证据 | 已验证 | 三类计数首屏可见，反证排首位，含来源/版本/版权 |
| 3.10 | 10 时间窗口 | 已验证 + 缺陷修复 | 1440 下 `main` 内部横向溢出 47px → 修复为可滚动容器 |
| 3.11 | 双视口覆盖 | 已验证 | `viewport-1440-pages.spec.ts` 十页 × 1440 全通过；1672 由既有 spec + 本轮几何门禁覆盖 |
| 3.12 | 与参考图像素级一致 | **待人工确认** | 参考图字体未提供；已交付同宽并排图与差异叠加图，**不宣称像素级还原**，也不自动批准为正式基线 |

---

## 4. 交互闭环

| # | 项目 | 状态 | 证据 |
|---|---|---|---|
| 4.1 | 日历缓存身份 | **修复**：`version_token` 由「区间+行数+生成时间」改为**内容哈希**；并修 provider 进程内缓存**永不重载**的缺陷（改按来源文件 mtime 失效） | `src/core/stock/trading_calendar.py`；回归测试 `tests/core/test_trading_calendar_published.py::TestCalendarCacheIdentity`（6 项）：同行数同区间但内容改变 → 指纹必须变；文件重写后 provider 必须重新加载 |
| 4.2 | 紫微星曜可达 | **修复**：每宫新增「明细」按钮 → 弹出该宫**全部**主星/辅星/杂曜（含庙旺、长生十二神、三方四正）；悬停 title 不再是唯一入口；杂曜截断处显示 `+N` | `components/ziwei/ZiweiChart.tsx`；`interaction-closure.spec.ts` 12/12 宫逐宫验证 + 空宫不补星 |
| 4.3 | 上下文一致（切换股票后不显示上一只） | **修复**：`useAnalysis` 增加上下文令牌 + 标的校验；标的变更时立即清空旧结果 | `lib/analysisStore.ts` |
| 4.4 | 快速连续切换竞态 | **修复**：旧响应（令牌过期或 `stock_code` 不匹配）一律丢弃，不覆盖新上下文 | 同上 |
| 4.5 | 重新计算：Loading / 防重复 / 错误恢复 | 已验证 | 按钮 `disabled={recalculating}` 且文案切换「计算中…」；失败走 `PageError` + 「重试」 |
| 4.6 | 本机自选：加入/移除/去重/刷新恢复 | **新实现** | `lib/watchlistStore.ts`（localStorage，去重，上限 50）；UI 明确写「本机自选（浏览器本地保存…不跨设备同步）」；`interaction-closure.spec.ts` 全流程通过 |
| 4.7 | 导出必须真实生成且可打开 | **新实现（复用已存在但未接线的能力）** | 后端 `GET /api/v1/analysis/{id}/report?format=markdown\|html`（`render_report`）此前**没有任何前端入口**；本轮接入统一导出菜单并补结构化 JSON |
| 4.8 | 导出冻结当前上下文 | 已验证 | 综合页保留整份 `multi` 快照；`interaction-closure.spec.ts`「导出期间切换标的不会混入另一只股票的数据」 |
| 4.9 | 演示模式导出必须标注演示 | 已验证 | 三种格式的演示导出均含「【演示数据】…」；JSON `demo=true`；不与后端 report 端点混用 |
| 4.10 | 不把浏览器打印说成后端 PDF | 已验证 | 菜单文案「可打印 HTML（.html）— 自包含页面，可浏览器打印（非服务端 PDF）」；导出文件页脚同样声明 |
| 4.11 | 不存在能力的选项不得假装可用 | 已验证 | 无法导出时按钮 `disabled` 且 `title` 给出原因；已移除上下文栏中两个「Phase 2 占位」死按钮；`TABS` 死代码删除 |
| 4.12 | 筛选/分页/排序/展开/重试等既有交互 | 已验证 | 沿用既有实现并由既有 spec 覆盖（因子字典筛选分页、古籍 stance 页签、分歧场景切换、分区重试） |

---

## 5. 真实数据验收

| # | 项目 | 状态 | 证据 |
|---|---|---|---|
| 5.1 | 三只真实标的分属不同交易所 / 不同完整度 | 已验证 | 选择依据写入 `real-acceptance.json`：`600519`（SSE 主板，2001-08-27 上市）、`000001`（SZSE 主板，1991 起）、`688981`（SSE 科创板，2020-07-16 起，短历史） |
| 5.2 | 当前实际日期基准 + 行情覆盖内历史基准 | 已验证 | 运行时日期 `2026-09-22`；当前基准 as_of `2026-09-21T16:24:34`（行情末日 `2026-09-18`，**滞后如实保留**）；历史基准取 `2026-09-18` |
| 5.3 | 三层日历覆盖分别记录 | 已验证 | SSE 实测 `1990-12-19~2026-09-21`（8,557 日）、公布 `~2026-12-31`；SZSE 实测 `1993-01-03~2026-09-21`（8,198 日） |
| 5.4 | provider / 复权口径 / 数据版本 | 已验证 | `vendor_parquet` + 基准指数回退离线真实通道；响应内 `bar_source`、`versions` 随附 |
| 5.5 | 未来 20 个交易日 | 已验证 | 三只标的均 `returned_days=20`；`day_sources` 区分 `observed_index_days`（2）与 `published_exchange_calendar`（18） |
| 5.6 | 日期完全越界 | 已验证 | `as_of=2027-06-01` → `returned_days=0`、`status=unavailable`，附「官方尚未公布」说明，**不照搬上一年** |
| 5.7 | 北交所（日历未接入） | 已验证 | `for_exchange("BSE")` → `observed.loaded=false`，不借用沪深日历 |
| 5.8 | 不存在的代码 | 已验证 | `999999` → `404 STOCK_NOT_FOUND`「不在供应商 Parquet 仓库内」 |
| 5.9 | 非法变体 | 已验证 | `variant_mode=sideways` → `422 VALIDATION_ERROR`，**不静默取默认** |
| 5.10 | 零收益与缺失收益可区分 | 已验证 | 不可用引擎 `score=null`（导出 JSON 断言 `availability!=="ok" ⇒ score===null`）；收益统计缺失显示 `—` 而非 `0` |
| 5.11 | 故障注入与真实来源验收分别记录 | 已验证 | 故障注入（路由 mock / 非法参数）与真实来源（供应商 Parquet + 真实日历）在报告中分开列示 |
| 5.12 | fixture 路径隔离 | 已验证 | 十页 fixture 初始加载与交互 **0 个** `/api/` 请求（`capture-final.mjs` 的 `fixture_api_calls` 为空）；非支持标的显示唯一错误卡；正常模式失败不回退 fixture |
| 5.13 | 真实模式 × 浏览器 × 本轮新交互 | 已验证 | `apps/web/e2e/real-mode-live.spec.ts`（8 项）：三只真实标的 × 六页无错误渲染、as_of 不被替换、导出后端报告实下载、本机自选刷新恢复、切换标的不残留、紫微注入 500 时分区降级 |

---

## 6. 回归、生产构建、发布准备

| # | 项目 | 状态 | 证据 |
|---|---|---|---|
| 6.1 | `make test`（等价 `pytest -q`） | 已验证 | **1404 passed**（`output/ui-final/pytest-full.log`） |
| 6.2 | `make test-leak` | 已验证 | `tests/test_no_future_data_access.py` 全通过 |
| 6.3 | `make test-ui`（Playwright 全量） | 已验证 | **149 passed / 0 skipped**（`output/ui-final/e2e-final.log`），live 组与真实模式套件均真实执行 |
| 6.4 | 前端类型检查 | 已验证 | `npx tsc --noEmit` 0 error |
| 6.5 | 前端生产构建 | 已验证 | `next build` 成功（13 条路由） |
| 6.6 | Python lint | 已验证 | `ruff check src apps tests` |
| 6.7 | Golden Case | 不需要 | 本轮未改排盘逻辑与历法口径；交易日历为**只增不删**的增量更新，历史交易日集合未变 |
| 6.8 | 未弱化断言 / 未跳过用例 / 未改期望值 | 已验证 | 本轮只新增用例；修改仅一处测试选择器（`ziwei-palace-` → `ziwei-expand-`），原因是新增按钮与宫格 testid 前缀冲突，属**修正选择器**而非放宽断言 |
| 6.9 | 发布步骤 / 验证步骤 / 回滚步骤 | 已验证 | `docs/UI_FINAL_RELEASE_READINESS.md` |
| 6.10 | 部署目标环境 | **外部阻塞（部署目标未指定）** | 本任务书未指定部署目标；只检查本项目已有配置（`docker-compose.yml` / `deploy/` / `.env` 约定），完成本地生产验收；**不据其他项目信息自行选择部署目标** |

---

## 7. 未完成 / 待人工确认

| # | 项目 | 状态 |
|---|---|---|
| 7.1 | 正式视觉基准确认 | **待人工确认**：候选基线在 `output/ui-final/candidate/`，`manifest.approval_status="pending-human-review"` |
| 7.2 | 合并 main | **待人工确认**：本轮不合并、不推送 main |
| 7.3 | 生产部署 | **待人工确认**：本轮不部署 |
| 7.4 | 参考图字体识别 | **外部来源限制**：参考图未提供字体文件，仍用 OFL 的 Noto Serif/Sans SC 子集，残余差异如实记录 |
| 7.5 | 2027 年交易日历 | **外部来源限制**：国务院通常当年 11 月发布；公布窗口停在 `2026-12-31`，越界时如实报"未知" |
| 7.6 | 供应商 Parquet 覆盖 | **数据缺失（非功能缺陷）**：BSE 无官方日历，显式降级、不借用沪深日历 |
