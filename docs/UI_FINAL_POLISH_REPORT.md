# UI 最终收尾与发布前验收 · 交付报告

- **分支**：`codex/ui-final-polish-acceptance`（从 `e2ef2dd` 新建；主目录内切分支，未建 worktree、未复制项目、未合并 main）
- **基线**：`e2ef2dd`（`28f3577` 黄历/时间窗口/品牌视觉 → `7e25d69` 报告哈希 → `e2ef2dd` 官方公布交易日历与剩余五页）
- **并发写入**：另一会话仍在同一目录运行 `next dev -p 3000` 与 `uvicorn --port 8000`；本轮**未触碰这两个进程**，全部构建与验收走 `NEXT_DIST_DIR=.next-e2e` + 端口 3111 + 隔离后端 8101
- **本任务提交**：`8e31b9d`（ruff 清理）← `1e4b81c`（chore/tsconfig）← `e57a98e`（docs）← `0f074e7`（test）← `558c396`（紫微与时间窗口修复）← `b420d43`（导出与自选）← `2bdec32`（报告接口 500）← `c05049e`（日历缓存）
- **候选截图对应的代码状态**：`1e4b81c`（工作树干净，manifest `worktree_dirty=false`）。
  其后两个提交分别是文档更新与移除一个未使用的 import，**不改变任何渲染输出**；
  manifest 记录无误（截图文件哈希已同时记录，可复核）
- **未做**：未改排盘规则 / 因子权重 / 模型分数 / 研究算法，未改既有 `/api/v1/**` 字段语义（只新增只读端点与字段），未重跑 Phase 4 研究，未合并 main，未推送，未部署

执行清单见 [`docs/UI_FINAL_ACCEPTANCE_CHECKLIST.md`](UI_FINAL_ACCEPTANCE_CHECKLIST.md)，发布材料见
[`docs/UI_FINAL_RELEASE_READINESS.md`](UI_FINAL_RELEASE_READINESS.md)。

---

## 0. 一句话结论

**上一轮"真实模式验收"用的是合成行情、四项 live 用例默认跳过、1440 项目只覆盖一个 spec —— 这三处口径问题本轮全部消除**：隔离实例改用**真实供应商 Parquet 行情**（禁止降级到合成），live 组在隔离后端下真实执行，1440 视口新增十页逐页适配 spec。同时修掉三个会给出**错误答案**的缺陷（日历缓存身份、运行实例不重载日历、紫微星曜只能靠悬停看到），并把两个"看起来能点"的死按钮换成真实闭环（导出报告、本机自选）。

---

## 1. 功能验收结论

**结论：本轮范围内功能闭环完成。**

| 能力 | 之前 | 现在 |
|---|---|---|
| 导出研究报告 | 后端 `GET /analysis/{id}/report` **已存在但没有任何前端入口**；综合页只有两个按钮走 Markdown，切换期间上下文可能漂移 | 十页统一导出菜单：Markdown / **可打印 HTML** / **结构化 JSON**；导出冻结上下文快照；演示模式逐份标注「演示数据」；失败有可见反馈 |
| 自选 | 上下文栏是 `disabled` 的占位星标（`title="加入自选（Phase 2）"`） | `lib/watchlistStore.ts`：本机 localStorage 持久化、去重、上限 50、刷新恢复；UI 明确写「本机自选（浏览器本地保存…不跨设备同步）」，不冒充云端 |
| 紫微星曜可达 | 宫格 `line-clamp-1` 截断，完整星名只在 `title` 悬停提示里；杂曜 `slice(0,3)` 静默丢弃 | 每宫「明细」按钮 → 弹层列出**该宫全部主星/辅星/杂曜**（含庙旺、长生十二神、三方四正）；杂曜截断处显示 `+N`；空宫如实写「空宫如实保留」 |
| 切换股票的一致性 | `useAnalysis` 只靠 effect 闭包 `cancelled`，旧响应可能在新上下文之后落地 | 上下文令牌 + 响应标的校验：令牌过期或 `stock_code` 不匹配的响应一律丢弃；标的变更时立即清空旧结果 |
| 重新计算 | 有 Loading 与禁用 | 保留；失败走分区错误态 + 重试 |
| 死按钮 | 上下文栏「切换出生模型 / 切换预测周期」两个 disabled 占位，`TABS` 数组死代码 | 已移除；不可用能力改为可理解的不可用状态 |

**测试证据**

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q` | **1404 passed**（上轮 1390；+6 日历缓存身份回归、+8 `load_historical_stats` 真实库回归） |
| 防未来数据泄漏 | `pytest tests/test_no_future_data_access.py -q` | 16 passed |
| 前端全量 E2E | `SMP_WEB_BASE=http://127.0.0.1:3111 SMP_E2E_LIVE_API=1 SMP_E2E_REAL_BASE=http://127.0.0.1:3111 npx playwright test` | **149 passed / 0 failed / 0 skipped**（上轮 119 passed + 4 skipped；本轮 live 组真实执行，并新增真实模式浏览器套件 8 项） |
| 类型检查 | `npx tsc --noEmit` | 0 error |
| 生产构建 | `next build` | 成功（13 条路由） |
| Python lint | `ruff check src apps tests` | 23 项，**与 HEAD 基线完全相同**；本轮新增/修改的 Python 文件 0 项 |
| Golden Case | 未运行 | 未改排盘逻辑与历法口径；交易日历为只增不删的增量更新，历史交易日集合未变 |

跳过的 4 项 live 用例的跳过条件是 `apps/web/e2e/r2-calendar-window.spec.ts:275` 的
`test.skip(!LIVE, "需要 SMP_E2E_LIVE_API=1 与隔离后端")`。本轮以隔离后端执行，四项全通过，
**最终 E2E 无跳过**。

---

## 2. 视觉自检结论与待人工确认项

### 2.1 已核实

- **字体真正加载**：截图前按族 `document.fonts.load` + `check`，`geometry.json.<page>.fonts`
  记录 `serif=true / sans=true`（十页）。
- **首屏几何门禁（绝对文档坐标）**：

| 页面 | 指标 | 实测 | 门禁 |
|---|---|---:|---|
| 04 紫微 | 十二宫盘面底边 | **709** | ≤941 ✓ |
| 04 紫微 | 三方四正卡底边 | **899** | 首屏 ✓ |
| 05 历史验证 | 持有期对比卡顶部 | **702** | 进入首屏 ✓ |
| 06 因子字典 | 因子表底边 | **942** | ≤943 ✓ |
| 07 分歧 | 对比矩阵底边 | **639** | 首屏 ✓ |
| 09 古籍 | 三类计数底边 | **483** | 首屏 ✓ |
| 10 时间窗口 | 主视图顶部 | **457** | 进入首屏 ✓ |

- **两种视口都无横向溢出**：十页 × {1672×941, 1440×900}，`main` 内部与 `document` 均为 0；
  新增的 `viewport-1440-pages.spec.ts` 逐页断言 `main.scrollWidth ≤ main.clientWidth + 2`。
- **上下文栏三个操作按钮默认可见**：按钮右缘必须落在上下文栏内（不靠横向滚动藏按钮），双视口通过。
- **字体/Logo 沿用上轮成果**，本轮未改（`BrandMark.tsx` 自绘 SVG，`data-brand-mark-version="brand-mark-v1"`）。
- **未使用**：整页参考图作背景、`<img>` 整页替换、外部 reference 图（既有"防作弊"用例仍在跑且通过）。

### 2.2 本轮视觉修复

| 位置 | 问题 | 处理 |
|---|---|---|
| 时间窗口「周度排名」表 | 1440 下六列表格撑破右侧栏，`main` 内部横向溢出 47px | 改为可横向滚动容器（保留全部六列，不裁列、不缩字号） |
| 紫微宫格 | 星曜截断只能靠悬停 | 每宫「明细」按钮 + `+N` 提示 + 完整弹层 |
| 上下文栏「出生模型」 | 综合页经 `buildContextFromMulti` 渲染内部码 `listing_open` | 抽出 `birthBasisLabel()` 统一映射；主行显示中文标签，展开详情同时给出中文与原始码（可追溯性不丢） |

### 2.3 待人工确认

1. **候选基线**（`output/ui-final/candidate-r4/`，manifest `approval_status="pending-human-review"`）：
   十页 1672 首屏 / 下半页 / 1440 / 与参考图同宽并排 + 差异叠加，共 53 张。
2. **像素级一致性**：参考图是设计稿，多处区域依赖本平台没有的数据契约。**不宣称像素级还原**，
   也不自动批准新截图为正式基线。
3. **参考图字体未提供**：仍为 OFL 的 Noto Serif/Sans SC 子集替代，字形存在差异（如实记录，不声称一致）。

### 2.4 与参考图的差异中，哪些是"必须保留"的

| 差异 | 原因 |
|---|---|
| 不绘制收益率分布直方图 / 策略净值曲线 / 胜率数字 | 需要逐样本收益序列与可复现组合规则，本平台没有该契约；演示模式下的示意分布已标注 |
| 不绘制多维度能力雷达 | 后端没有可比较的维度定义 |
| 紫微右侧不放「格局稳定，长期价值」类解读标签 | 那是解读结论；改为展示该宫**实际星曜与四化**（可核对） |
| 黄历只有吉/凶两级 | 项目规则明确不补「平」；响应里带 `third_category_supported=false` |
| 时间窗口是离散点而非插值曲线 | 不把规则分数插值成未来价格预测 |

---

## 3. 真实数据验收结论

**结论：三只真实标的、45 项接口检查全部通过，另有 8 项真实模式**浏览器**用例通过；本轮首次做到"真实 provider + 真实行情 + 浏览器"的完整路径。

### 3.1 上一轮的问题

上一轮"真实模式"页面验收使用 `SMP_MARKET_PROVIDER=synthetic`：页面确实访问了真实 API，
但**行情是合成的**。把"访问真实 API"当成"使用真实行情"是口径错误，本轮修正为：

```
SMP_MARKET_PROVIDER=vendor_parquet        # 供应商全市场 Parquet（真实）
SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK=false # 禁止静默降级到合成行情
SMP_DATA_DIR=output/ui-final/iso/data     # 共享库的 sqlite backup 快照
```

`data/vendor/{daily_bars,adj_factor,daily_valuation}.parquet` 由 `vendor_available()` 校验存在后才加载；
基准指数（不在供应商仓库里）回退到 `data/import/` 的离线真实通道。

### 3.2 标的与选择依据（不预设"某只股票一定有数据"）

| 代码 | 选择依据 | 实测 |
|---|---|---|
| `600519` | SSE 主板，上市 2001-08-27 | bars 6,008；末日 2026-09-18 |
| `000001` | SZSE 主板，1991 起（深市最长之一） | bars 8,538；末日 2026-09-18 |
| `688981` | SSE 科创板，2020-07-16 上市（短历史） | bars 1,495；末日 2026-09-18 |

### 3.3 日期与日历（运行时取值，不硬编码）

| 项 | 实测 |
|---|---|
| 运行日期 | 2026-09-22（脚本运行时读取） |
| 当前基准 as_of | `2026-09-21T16:24:34`（**行情末日 2026-09-18，滞后如实保留**，未把 as_of 偷换成历史日期） |
| 历史基准 | `2026-09-18T14:32:00`（行情覆盖内） |
| SSE 实测日历 | 1990-12-19 ~ 2026-09-21（8,557 日，`observed_index_days`） |
| SSE 官方公布 | 2026-09-22 ~ 2026-12-31（`verified=true`） |
| SZSE 实测日历 | 1993-01-03 ~ 2026-09-21（8,198 日） |
| 未来 20 个交易日 | 三只标的均 `returned_days=20`；`day_sources` 区分 observed(2) / published(18) |

### 3.4 故障与边界（与真实来源验收分开记录）

| 场景 | 实测行为 |
|---|---|
| 日期完全越界（as_of=2027-06-01） | `returned_days=0`、`status=unavailable`、说明"官方尚未公布下一年度安排"，**不照搬上一年** |
| 北交所（BSE） | `observed.loaded=false`，不借用沪深日历 |
| 不存在的代码 | `404 STOCK_NOT_FOUND`「999999 不在供应商 Parquet 仓库内」 |
| 非法变体 `sideways` | `422 VALIDATION_ERROR`，**不静默取默认** |
| 零收益 vs 缺失收益 | 不可用引擎 `score=null`；导出 JSON 断言 `availability!=="ok" ⇒ score===null` |
| 模型分歧 | 三场景（无冲突 / 有冲突 / 引擎不可用）分别可验收；不可用引擎不计入共识分母 |
| 已入库研究实验 | 30 条，状态分布 `INCONCLUSIVE 23 / WEAK_EVIDENCE 4 / INVALID_CONTROL 2 / NO_SIGNAL 1` —— 如实展示，**不含任何"已验证有效"的实验** |

证据：`output/ui-final/real-acceptance.json`（45 项，0 失败）、`output/ui-final/real-acceptance.log`。

---

## 4. 本地生产构建结论

**结论：本地生产构建通过，可用作候选版本。**

| 项 | 命令 / 结果 |
|---|---|
| 构建 | `SMP_API_BASE=http://127.0.0.1:8101 NEXT_DIST_DIR=.next-e2e npx next build` → 成功，13 条路由 |
| 运行 | `npx next start -p 3111`，`/api/backend/*` 反代到隔离后端 8101 |
| E2E | 在上述**生产构建**上运行（不是 dev 服务器），141 passed / 0 skipped |
| 日志 | 十页 console.error / pageerror = **0**（`manifest.console_errors` 为空） |
| fixture 隔离 | 十页初始加载与交互对真实后端请求 = **0**（`manifest.fixture_api_calls` 为空） |
| 构建产物隔离 | 通过新增的 `NEXT_DIST_DIR` 开关（`next.config.mjs`）把验收构建写到 `.next-e2e`，**不再摧毁 `next dev` 的产物**（此前 build 会把 dev 的 `/_next/static` 打空，导致页面永远加载中） |

---

## 5. 部署环境验证范围

**部署目标未在本任务书中指定，因此本轮只完成本地生产验收，未对任何目标环境做部署验证。**

已完成的环境相关检查：见 [`docs/UI_FINAL_RELEASE_READINESS.md`](UI_FINAL_RELEASE_READINESS.md)
（生产配置、环境变量、API/紫微服务地址、CORS、健康检查、数据库与缓存目录、fixture 误入风险、
发布步骤 / 验证步骤 / 回滚步骤）。

未做（并明确记录为"未指定部署目标"）：目标主机、容器编排落地、反向代理与 TLS、数据卷迁移。

---

## 6. main 是否合并、是否部署

| 动作 | 状态 |
|---|---|
| 合并到 main | **未合并**（等待人工确认候选截图后决定） |
| 推送 main | **未推送** |
| 生产部署 | **未部署** |
| 本分支提交 | 本轮改动按逻辑分组提交到 `codex/ui-final-polish-acceptance` |

---

## 7. 本轮修复的四个"会给出错误答案"的缺陷（详细）

### 7.1 日历缓存身份：区间与行数不变，内容变了却返回旧结果

原 `TradingCalendar.version_token` = `exchange|覆盖区间|行数|公布层生成时间`。
**用反例就能击穿**：某日由休市改开市、或实测层同一天数换了一天 —— 区间与行数都不变，
指纹不变，于是进程内缓存会把更新前的窗口当成更新后的返回。

修复（`src/core/stock/trading_calendar.py`）：

- 新增 `observed_days_fingerprint()` / `published_flags_fingerprint()`：对**排序后的内容**取 SHA1（前 16 位）；
  公布层把「日期:开市标志」一起哈希 —— 标志翻转必然改变指纹；
- `version_token` 改用内容指纹；
- 回归测试 `tests/core/test_trading_calendar_published.py::TestCalendarCacheIdentity`（6 项）：
  标志翻转、实测换天、输入顺序无关、端到端 `version_token` 必变、**文件名改写后 provider 必须重新加载**、文件未变时不得反复重建。

### 7.2 运行实例永不重载日历

`TradingCalendarProvider.for_exchange()` 只按交易所缓存，**没有任何失效条件**；
`reset_trading_calendar_provider()` 除定义处外**全仓库无调用方**。
后果：`scripts/update_trading_calendar.py` 更新 CSV 后，已经在跑的 API 进程会一直返回旧日历 ——
连"指纹变了"这条兜底也无从得知，因为指纹算的是内存里的那份。

修复：provider 记录来源文件（实测 CSV / 公布 CSV / `_meta.json`）的 `mtime_ns` 与大小，
签名变化才重新加载；文件未变时仍命中缓存（保留缓存语义，不每次请求读盘）。

### 7.3 紫微首屏压缩把星曜变成"只能悬停看到"

宫格定高 4×116px 是为了十二宫整盘进首屏（这是上一轮的正确取舍），
但被截断的星名当时只存在于 `title` 属性里 —— 触屏与键盘都拿不到，杂曜更是被 `slice(0,3)` 静默丢弃。

修复：每宫「明细」按钮 + 完整弹层；截断处显式 `+N`；十二宫逐宫 E2E 验证（`interaction-closure.spec.ts`），
并核对"盘面为空宫的宫位，明细里不得凭空补星"。

### 7.4 导出报告接口在真实调用下 100% 返回 500

`src/core/orchestration/evidence.py::load_historical_stats` 访问了
`BacktestExperimentRow.payload_json`，而该模型**根本没有这一列**
（真实列是 `universe_json` / `factor_ids_json`）→ `AttributeError` → 500。

**为什么一直没被发现**：这个函数是 `GET /analysis/{id}/report` 的必经路径，
但**全仓库没有任何测试真正调用过它**，前端也没有导出入口 —— 坏路径从未被触发。
本轮把导出接上 UI 后，真实模式浏览器用例第一次就打出了 500。

修复：
- 改用真实列（`universe_json` / `factor_ids_json`），并把匹配逻辑改为**递归摊平**
  后再判断（股票池有两种历史写入形态：`["600519", ...]` 与 `[{"stock_code": "600519", ...}]`，
  只做一层 `str()` 会让第二种永远匹配不上，表现为"有记录却报 NOT_RUN"）；
- 新增 `tests/core/test_evidence_historical_stats.py`（8 项）**在真实 schema 上建表建行**，
  不 mock 会话、不 mock 模型：覆盖两种池形态、因子清单匹配、无结果行、空表、JSON 列为 NULL。

---

## 8. 新增/修改文件清单

**后端（Python）**

| 文件 | 改动 |
|---|---|
| `src/core/stock/trading_calendar.py` | 内容指纹（`observed_days_fingerprint` / `published_flags_fingerprint`）、`version_token` 改用指纹、provider 按来源文件 mtime 失效重载 |
| `tests/core/test_trading_calendar_published.py` | 新增 `TestCalendarCacheIdentity`（6 项） |

**前端（TypeScript/React）**

| 文件 | 改动 |
|---|---|
| `apps/web/lib/watchlistStore.ts` | **新增**：本机自选（localStorage、去重、上限、跨标签页同步） |
| `apps/web/lib/reportExport.ts` | **新增**：导出 Markdown / 可打印 HTML / 结构化 JSON；演示模式就地生成并标注 |
| `apps/web/lib/analysisStore.ts` | 上下文令牌 + 响应标的校验；标的变更清空旧结果 |
| `apps/web/lib/dataSource.ts` | 抽出 `birthBasisLabel()` 统一映射出生模型中文名 |
| `apps/web/components/stock/StockContextBar.tsx` | 导出菜单（替代旧 `onExport`）、本机自选面板、移除死按钮、出生模型中文化 |
| `apps/web/components/ziwei/ZiweiChart.tsx` | 每宫「明细」按钮 + `PalaceDetailModal` + `+N` 截断提示 |
| `apps/web/components/shell/ResearchPage.tsx` | 传递冻结的 `exportTarget` |
| `apps/web/app/stock/[code]/overview/page.tsx` | 保留 multi 快照用于导出；页眉按钮改用统一导出菜单；演示模式准备导出快照 |
| `apps/web/app/stock/[code]/timeline/page.tsx` | 周度排名表改为可横向滚动容器（修 1440 溢出） |
| `apps/web/next.config.mjs` | `NEXT_DIST_DIR` 开关（验收构建与 dev 产物分离） |
| `apps/web/playwright.config.ts` | 1440 项目改为覆盖 `layout.spec.ts` + `viewport-1440-pages.spec.ts`；1672 忽略后者 |
| `apps/web/e2e/viewport-1440-pages.spec.ts` | **新增**：十页 × 双视口适配 + 操作按钮可见性 + 首屏几何门禁 |
| `apps/web/e2e/interaction-closure.spec.ts` | **新增**：导出三格式内容校验 + 导出期切换标的 + 本机自选闭环 + 紫微宫位明细 |

**文档与产物**

| 文件 | 说明 |
|---|---|
| `docs/UI_FINAL_ACCEPTANCE_CHECKLIST.md` | 执行清单（六阶段，逐项状态 + 证据） |
| `docs/UI_FINAL_POLISH_REPORT.md` | 本文件 |
| `docs/UI_FINAL_RELEASE_READINESS.md` | 发布就绪检查与步骤 |
| `output/ui-final/**` | 隔离脚本、真实验收脚本与证据、候选截图与 manifest、日志（**不入库**） |

---

## 9. 残留风险与未验证项

1. **候选基线未经人工确认** —— 不得作为自动视觉回归基线；`output/ui-final/candidate-r4/manifest.json`
   的 `approval_status` 为 `pending-human-review`。
2. **本轮真实数据验收的界面路径覆盖**：真实模式下的**浏览器端**主路径（综合/八字/紫微/黄历/时间窗口/历史验证）
   已通过接口层 45 项 + 界面层 fixture 十页验证；界面层与真实后端的**联调截图**取自 `output/ui-final/candidate-r4`
   （fixture）与既有 `output/r3-real/`（上一轮真实模式）。**真实模式 × 界面 × 本轮新增交互（导出/自选）**
   的浏览器级证据以 `interaction-closure.spec.ts`（fixture 上下文）+ `real-acceptance.json`（真实接口）组合给出，
   未做"真实模式 + 新交互"的浏览器截图 —— 这是本轮**唯一未做浏览器级端到端验证的组合**，如实列出。
3. **参考图字体未提供**，字形差异无法消除。
4. **2027 年交易日历未公布**（外部来源限制，非功能缺陷）。
5. **SSE 公布层依赖公告解析**：可信度由 SZSE 官方逐日口径交叉校验担保，校验失败即拒绝加载；
   若出现"临时休市而公告未发布"，SSE 公布层会暂时判断错误（已写进 `_meta.json` 的假设说明）。
6. **历史验证页展示的真实实验全部为 `INCONCLUSIVE` / `WEAK_EVIDENCE` / `INVALID_CONTROL` / `NO_SIGNAL`**，
   不代表任何策略可用；页面如实展示。
