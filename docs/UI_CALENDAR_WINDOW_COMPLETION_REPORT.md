# UI 日历与时间窗口补全交付报告（品牌视觉 / 黄历 / 时间窗口 / R1 收口）

- **分支**：`codex/ui-calendar-window-completion`
- **基线**：`codex/ui-refinement-r1` @ `2d90c8f`（含 R1 整改 `1acee3d` 与零请求测试 `2d90c8f`，已核对）
- **本轮范围**：前端（`apps/web/**`）、后端只读查询与研究计算（新增模块与端点、`timeline` 批量求值）、测试、文档
- **未做**：不改已有排盘口径、不改因子权重与模型分数、不改已公开的 `/api/v1/**` 既有路径与字段、不重跑 Phase 4、不自动合并 main、不部署

---

## 0. 一句话结论

黄历页的「未来 N 个交易日」与「证据与历史表现」两个区块、时间窗口页的研究型信息结构已**用真实数据跑通**（隔离后端 + 真实 hfq 行情 + 实测交易日历），品牌字体改为自托管 OFL 子集并新增独立矢量 Logo；R1 遗留的 hydration 时序问题改为**可观测的就绪信号**；后端全量 1352 项、前端全量 108 项测试全绿。

**仍未达成的**：与参考图的像素级一致性（参考图字体未提供，见 §7）。

---

## 1. 分支、基线与提交

| 项目 | 值 |
|---|---|
| 工作分支 | `codex/ui-calendar-window-completion`（从 `codex/ui-refinement-r1` 的 HEAD 新建，未创建 worktree、未复制项目） |
| 基线提交 | `2d90c8f`（= R1 整改 `1acee3d` + 零请求测试 `2d90c8f`） |
| 基线核实 | `git log --oneline -8` 确认两个提交都在 HEAD；`codex/ui-remediation` 为历史分支，未改动 |
| 本轮提交 | `0cd1a76`（`feat(ui): 黄历未来交易日与历史表现、时间窗口研究视图、品牌视觉校准`） |
| 同名分支 | 建立前检查过 `git branch -a --list "*calendar-window*"`，无同名分支，未发生覆盖 |

---

## 2. 目标区块—现有能力—缺失能力—实现位置—验收用例

| 目标区块 | 实现前能力 | 缺失 | 实现位置 | 验收用例 |
|---|---|---|---|---|
| 品牌字体 | `globals.css` 只有 `font-family` 回退列表，无任何字体资源；Windows 实际落到 SimSun / 雅黑 | 真正加载的字体文件与字重 | `apps/web/public/fonts/*.woff2`（Noto Serif/Sans SC 子集，OFL 1.1）、`apps/web/app/fonts.css`、`app/layout.tsx` 预加载 | `capture-r2.mjs` 断言 `document.fonts` 中 `SMP Serif SC` / `SMP Sans SC` 均为 `loaded`；截图并列对照 |
| 品牌 Logo | 顶栏用**功能图标** `IconTaiji`（线性 1em）放大充当 | 独立的品牌标 | `apps/web/components/brand/BrandMark.tsx`（实心阴阳 + 不等粗笔触外圈 + 金色渐变） | 与参考图并排截图；`data-brand-mark-version="brand-mark-v1"` 可追溯 |
| 页面标题/装饰 | Hero 高 ~70px、标题 34px，竖联与题词被星盘压住 | 参考图级标题尺度与互不重叠的装饰区 | `components/shell/TopBar.tsx`（`PageHero`）、`components/shell/Decorations.tsx`（保留星盘，独立设计） | 几何测量 + 截图；首页/黄历/时间窗口三页 |
| 未来 20 个交易日黄历 | 后端有 `HuangliEngine.day_for`（4.4ms/日）与 `TradingCalendarProvider`（SSE 1990-12-19 ~ 2026-09-18）；前端只展示单日 | **无接口**、前端无交易日历、**无版本化吉凶分类** | `src/core/orchestration/huangli_day_class.py`、`huangli_outlook.py`、`GET /huangli/outlook`、`components/huangli/HuangliTradingDayGrid.tsx` | `tests/core/test_huangli_outlook.py`（12 项）、`r2-calendar-window.spec.ts` 5 项 |
| 黄历证据与历史表现 | 有 `market_bar_daily`（hfq / composite_none）、`IDX000300`、`compute_forward_returns`；**无按日课分类的统计** | **无接口**、无研究计算 | `src/research/huangli/day_class_returns.py`、`GET /huangli/performance`、`components/huangli/HuangliPerformancePanel.tsx` | `tests/research/test_huangli_day_class_returns.py`（10 项）、`r2-calendar-window.spec.ts` 3 项 |
| 时间窗口 | 接口已有 `timeline/months`、`timeline/weeks`（后者**已含逐日三模型结果**）；前端只渲染两张表 | 前端未展示逐日粒度；无缓存，页面每次重算 | `GET /timeline/days`、`src/core/orchestration/result_cache.py`、`timeline.py` 批量求值、`app/stock/[code]/timeline/page.tsx` 重写 | `tests/core/test_timeline_batch_equivalence.py`（5 项）、`r2-calendar-window.spec.ts` 5+3 项 |
| R1 hydration 残留 | `ResearchPage` 已改用 `useSearchParams`，但测试用固定延时等就绪 | 就绪条件不可观测 | `components/shell/AppShell.tsx` 的 `data-app-ready` / `data-fixture-mode`；`r1-refinement.spec.ts` 改为等待该信号 | 单测重复回放 15 次通过；并发节点探针峰值恒为 1 |

---

## 3. 新增接口 / 统计口径 / 分类规则及版本

### 3.1 新增端点（只新增，未改动既有路径与字段）

| 端点 | 说明 | 关键参数 |
|---|---|---|
| `GET /api/v1/analysis/{id}/huangli/outlook` | 未来交易日黄历 | `mode=today\|trading_days\|months`、`days`(1–90)、`months`(1–3) |
| `GET /api/v1/analysis/{id}/huangli/performance` | 日课分类的历史表现（描述性统计） | `window=1y\|3y\|5y\|custom`、`horizon=1\|5\|20`、`start`、`end` |
| `GET /api/v1/analysis/{id}/timeline/days` | as_of 之后连续交易日的逐日三模型结果 | `days`(1–60) |

契约测试：`tests/integration/test_api_huangli_outlook.py`（13 项），其中显式断言 `/huangli` 仍返回**已保存快照**（新端点未遮蔽它）。

### 3.2 版本号

| 版本常量 | 取值 | 位置 | 含义 |
|---|---|---|---|
| `HUANGLI_DAY_CLASS_VERSION` | `huangli-day-class-v1` | `huangli_day_class.py` | 吉/凶映射口径（改动必须提升） |
| `HUANGLI_OUTLOOK_VERSION` | `huangli-outlook-v1` | `huangli_outlook.py` | 未来交易日视图的序列化口径 |
| `HUANGLI_PERFORMANCE_VERSION` | `huangli-perf-v1` | `day_class_returns.py` | 研究窗口 / 聚合 / 序列定义 |
| `DAILY_WINDOW_VERSION` | `daily-v1` | `src/core/schemas/timeline.py` | 逐日窗口序列化口径 |
| `AGGREGATION_VERSION` | `agg-v1`（沿用） | 同上 | 周度聚合口径 |

**未提升**：`huangli_engine_version` / `bazi_engine_version` / `calendar_engine_version` / `factor_rule_version`。
理由：本轮的黄历批量取数是**同一 `_build_day` 实现的切片**（`tests/engines/test_huangli_window_slices.py` 逐字段断言相等），排盘口径与因子分数一个字节都没变。

### 3.3 分类规则（为什么只有两级）

后端通书口径 `HuangliDay.day_tian_shen_luck` 取值集合实测为 `{吉, 凶}`（十二神所属黄黑道的派生结论），**不存在「平」**。按 AGENTS.md §13 与用户要求，本系统：

- 只产出**吉 / 凶**两级，并在每次响应里带 `class_rule.third_category_supported = false` 与差异说明；
- 引擎未给出吉凶时返回 `class_label_cn = null`（"未给出分类"），**不用「平」补位**；
- 日期卡的"简短依据"直接取**通书宜忌原文**，不改写成"宜交易 / 忌追涨"。

### 3.4 研究统计口径（关键）

- 样本 = 窗口内的该股交易日，且其持有期标签**在分析基准日之前已可观测**（标签结束日 ≤ as_of）。实现上把 bars 截断到 as_of，因此该性质是构造性保证，并额外断言一次。
- 持有期推进复用 `compute_forward_returns`（"第 N 个持有期 = 该股票自己的第 N 根后续 bar"），与 Phase 3D 标签口径同源。
- 复权：优先 `market_bar_daily.adjust='hfq'`（后复权，价差本身含复权）；否则 `astockdata_composite_none` + TuShare `adj_factor` 快照。实际用了哪一份写进响应（`labels.bar_source` / `bar_adjust`）。
- 序列定义：**扩展均值**（"截至各日期的平均持有期收益"），**不是净值、不是累计收益**。
- 重叠披露：多日持有期的日频样本重叠 `(H-1)/H`，同时给出**互不重叠子样本**的有效样本量。
- **不提供策略累计收益**：系统没有可复现的组合规则、仓位、交易成本与可执行性检验，因此刻意不产出净值曲线。

---

## 4. 真实数据来源与端到端验收证据

### 4.1 隔离环境（不触碰共享研究库）

```
DB 副本      output/acceptance/smp-copy.sqlite3（sqlite backup API，从 data/smp.sqlite3 复制）
后端         SMP_DATABASE_URL=<副本> SMP_MARKET_PROVIDER=offline uvicorn ... --port 3311
             （offline = data/import/bars 的真实腾讯 hfq 快照 + 真实基准指数）
前端         SMP_API_BASE=http://127.0.0.1:3311 next build && next start -p 3211
分析基准日   2024-11-15（可用 ?asOf= 指定，见 §5.4）
```

### 4.2 真实链路实测（curl → 隔离后端）

| 端点 | 结果 |
|---|---|
| `huangli/outlook?mode=trading_days&days=20` | 20 张卡，覆盖 `complete`，`huangli-engine-1.0.0`；日期 `2024-11-15,11-18…12-12`（跳过 11-16/17 周末）；分类序列 `吉吉吉凶吉凶…`；首日依据「十二神「明堂」属黄道，通书口径为「吉」」，宜 `祭祀/祈福/求嗣/开光` |
| `huangli/performance?window=1y&horizon=1` | `tencent_hfq_import / hfq`；`label_cutoff=2024-11-15`（=as_of）；243 交易日中 242 个标签完整（剔除 1 个）；吉 n=123 均值 −0.08%、凶 n=119 均值 +0.04%；重叠披露 242/242 |
| `huangli/performance?window=3y&horizon=5` | 724 样本 / 互不重叠 145；剔除 5 个标签不完整样本 |
| `huangli/performance?window=5y&horizon=20` | 1193 样本 / 互不重叠 **60**；剔除 20 个；重叠率 95% 已披露 |
| `timeline/days?days=20` | 20 天，三引擎全部可用；冷启动 **3.30s** → 命中缓存 **0.22s**（15×） |
| `timeline/weeks?weeks=12` | 冷启动 **6.99s**（批量求值前为 ~32s，4.5×）；命中缓存后瞬时 |

### 4.3 前端真实模式截图与请求清单

`output/capture-real.mjs` 采集，`output/r2-real/`：

- 每页后端请求 **4 个**、console/pageerror **0 个**：
  `analysis/multi`、`huangli/outlook`、`huangli/performance`、`huangli`、
  `timeline/months`、`timeline/weeks`、`timeline/days`
- 黄历页：20 张日期卡 + 收益统计（吉 123 / −0.08% / −0.16% / 45% / −0.17%；凶 119 / +0.04% / −0.21% / 40% / +0.03%）+ 口径条完整
- 时间窗口页：月度 12 / 周度 12 / 逐日 20 覆盖，三模型方向（八字 偏强 69.64、紫微 偏强 58.91、黄历 中性 56.87），20 个热力图格子

---

## 5. 实现要点（以及为什么这样做）

### 5.1 黄历：交易日 ≠ 自然日

`build_huangli_outlook` 用 `TradingCalendarProvider` 枚举**实测指数成交日**，并**只接受 `source == "observed_index_days"`**：`TradingCalendar` 在文件缺失时会退化为"周末规则"，那条路径识别不了长假（春节连休会被当成交易日），因此归为"未知"并让整个视图返回 `unavailable` + 原因。日历覆盖不足时只返回覆盖到的天数，绝不补造日期（`HUANGLI_OUTLOOK_CALENDAR_PARTIAL`）。

### 5.2 时间窗口：性能与口径分离

逐日视图若逐日调用原 `_score_at`，每天要重建 31 天黄历（0.28s）并单独启动一次 Node 排紫微（0.23s），20 天要 17 秒。`TimelineBuilder.evaluate_days` 把两处可批量的部分批起来：

- 黄历：一次构造覆盖整段的连续日历再按天切片（`HuangliEngine.snapshots_for_window`）；
- 紫微：一次 `calculate_charts` 批量请求。

**分数一个都没变**——`tests/core/test_timeline_batch_equivalence.py` 对同一批交易日逐字段比对两条路径的 `direction / score / availability / rule_score / normalized_value`。这是把"性能优化"与"口径变化"分开的必要代价。

### 5.3 缓存键必须含版本

`result_cache.ResultCache` 的键包含：分析 id、区间参数、as_of、三个引擎版本、`AGGREGATION_VERSION`、`DAILY_WINDOW_VERSION`、`factor_rule_version`、`ziwei_factor_rule_version`、`variant_mode`。**少任何一个版本都可能把旧口径结果当新口径返回**——那比慢更糟。响应里带 `cache: {key, hit}`，不隐藏缓存行为。

### 5.4 前端

- **`?asOf=YYYY-MM-DD[THH:mm[:ss]]`**（`lib/useAsOfParam.ts`）：研究复核与验收都需要一个确定的基准日；非法值一律忽略，不静默取今天。经 `useSearchParams` 读取，SSR/CSR 同源。
- **分区三态**（`components/shell/SectionState.tsx`）：黄历与时间窗口页都是"多个独立数据源拼一页"，任何一块慢或失败都不吞掉其他块，且可**单独重试**。
- **阶梯线而非平滑曲线**：月度/周度数据在两个观测之间没有值，`step: "end"` 明确表达"该窗口内取这个值"；缺失模型 `connectNulls: false` 断开，不填 0。
- **热力图着色 = 该交易日可用引擎规则强度的均值**（可由三个后端分数直接核对）。不用 `combined_direction` 着色：它是相对 50 分的三档方向，实测整段窗口恒为 +1，全部格子同色等于没有信息。
- **右栏不做伪归因**：后端没有为单个窗口提供因子贡献分解，因此不生成参考图里的「关键触发因子（高权重/中权重）」，改为展示原始结果、依据、可用性、假设、版本与风险。

### 5.5 字体与 Logo

- 自托管 **Noto Sans SC / Noto Serif SC 子集**（OFL 1.1，`apps/web/public/fonts/README.md` 记录来源、SHA-256、子集化配方与字重策略）。字符集 = 前端源码全部非 ASCII 字符 **+ 后端引擎 2015–2030 全部黄历/八字输出词表**（宜忌、神煞这类文本只在运行时出现，源码里扫不到，漏掉就会混排）。
- 已知缺失字形：`▴ ▸ ▾` 与 `U+FE0F`（Noto CJK 不含），按 font-family 回退到系统字体。
- `preload` 两个 woff2：字体是"迟发现"资源，不 preload 会先用回退字体渲染一次标题，正是上一轮被指出的问题。
- **不声称识别了参考图原字体**：参考图未提供字体文件。选 Noto 系是"OFL 下最接近且可合法分发"的替代，残余差异见 §7。

---

## 6. 测试命令、数量与结果

### 6.1 后端

```bash
.venv/Scripts/python.exe -m pytest -q        # 1352 passed, 1 warning, 258.6s
```

| 新增测试 | 数量 | 内容 |
|---|---|---|
| `tests/core/test_huangli_day_class.py` | 6 | 只有吉/凶、缺失不补「平」、未知取值不就近归类、宜忌原样保留、口径说明 |
| `tests/core/test_huangli_outlook.py` | 12 | 跨周末、春节长假不出现、非交易日基准日、日历越界 unavailable/partial、月分组、上限钳制、无实测日历的交易所显式降级 |
| `tests/core/test_timeline_batch_equivalence.py` | 5 | 批量 vs 逐日的 opinions 与 factor_set 逐字段相等；月/周窗口同数；逐日窗口日历与上限；日历不足报 warning |
| `tests/engines/test_huangli_window_slices.py` | 5 | 切片 vs 逐日 `snapshot(days=31)` 逐字段相等（含 `hour_ganzhi` 时刻分量） |
| `tests/research/test_huangli_day_class_returns.py` | 10 | **可手工核验的小样本**：吉日 +1.00% / 凶日 −2.00% 时均值、中位数、上涨占比精确相等；5 日持有期用第 5 根 bar；as_of 截止剔除；重叠与独立样本量；无净值类字段；缺行情/上市前/自定义窗口缺 start/非法持有期的空态与报错 |
| `tests/integration/test_api_huangli_outlook.py` | 13 | 三个新端点契约；**既有 `/huangli` 未被遮蔽**；缓存命中；错误码 |

基线对比：本轮前 **1301** 项（R1 报告口径）→ 本轮 **1352** 项（**+51**，六个新增文件合计 51 项，无既有测试被放宽或删除）。

**防泄漏**：`tests/test_no_future_data_access.py` 在本轮全量中通过；新增的研究模块只读 as_of 之前的 bars，标签侧不进入任何特征路径。

### 6.2 前端

```bash
cd apps/web && npx tsc --noEmit            # 0 error
cd apps/web && npm run build               # 通过（13 条路由）
cd apps/web && npx playwright test         # 108 passed（含 4 项 live 组）
```

| 套件 | 结果 |
|---|---|
| 既有套件（batch-a / batch-b / core-flow / layout / research-status-banner / r1-refinement） | 全部通过 |
| 本轮新增 `e2e/r2-calendar-window.spec.ts` | **16 项全通过**（12 项 fixture 模式 + 4 项 live 组，需 `SMP_E2E_LIVE_API=1`） |

**数量差异说明（对应 R1 报告的"17/18 专项、91/92 全量"）**：
R1 报告记录的是当时的运行结果（18 项专项中 1 项偶发失败、全量 92 项中 1 项失败）。本轮把 R1 的 flake 归类处理后将默认全套跑满：**108/108 通过**，其中既有套件 92 项、本轮新增 16 项；R1 报告中的 17/18 与 91/92 是**修复前**的数字，已不再适用，不作为本轮交付依据。

### 6.3 fixture 模式隔离

`capture-r2.mjs` 在 fixture 模式下实测：**真实 `/api/` 请求 0 个、console.error 0 个、pageerror 0 个**（首页、黄历、时间窗口三页），且断言 `document.fonts` 中两个自托管字体均为 `loaded`。
新增的 4 组 fixture（today / 20d / 3m / performance / days / months / weeks）**全部由真实后端算出后冻结**——手写样本的单位与真实后端不一致（旧周度样本 `mean=73.6` vs 真实语义为方向均值），会让演示模式与真实模式给出两种数字。

---

## 7. 截图索引（1672×941 / 1440×900）

目录：`output/`（本地检查产物，**未入库**，`.gitignore` 已排除）。

| 文件 | 内容 |
|---|---|
| `r2/01-home-compare.png` | 首页：参考图 ｜ 当前实现（同宽并排） |
| `r2/08-huangli-compare.png` | 黄历页：参考图 ｜ 当前实现 |
| `r2/10-timeline-compare.png` | 时间窗口：参考图 ｜ 当前实现 |
| `r2/0X-*-1672.png` / `-1672-lower.png` / `-1672-mid.png` | 三页 1672 首屏 / 内部滚动后的下半页 / 黄历历史表现区 |
| `r2/0X-*-1440.png` | 三页 1440×900 |
| `r2/el-chart.png` | 逐日阶梯线（2× DPR，逐个模型分数可读） |
| `r2/el-heatmap.png` | 交易日热力图（真实交易日 + 强度色带 + 其余月份粒度说明） |
| `r2-real/real-08-huangli-*.png` | **真实模式**（隔离后端 + 真实 hfq）：首屏 / 历史表现区 / 下半页 / 1440 |
| `r2-real/real-10-timeline-*.png` | 真实模式时间窗口四张 |
| `r2-real/backend-calls.txt` | 真实模式实际发生的后端请求清单（逐条可核对） |
| `fontwork/brandmark-preview.png` | 品牌标三档尺寸（38/46/80px）的光栅预览 |

### 几何核对（1672×941，生产构建）

| 指标 | R1 目标 | 本轮实测 | 参考图人工估读 |
|---|---:|---:|---:|
| 八字 正负因素 y | ≤720 | **667** | ~690 |
| 八字 古籍证据 y | ≤900 | **856** | ~859 |
| 上下文栏高度 | ≤82 | **37**（已删除参考图中不存在的二级导航行） | ~45 |
| 页面 Hero 高度 | — | **112** | ~115–130 |
| 上下文栏内部横向溢出 | 无 | 无 | — |

### 视觉复核方式与结论边界

- 固定 1672×941 / 1440×900、`locale=zh-CN`、DPR 1、`page.clock` 冻结时钟（2024-11-15 15:00:27）、等待字体真正 `loaded` 后采集。
- **DOM 测试通过不等于视觉还原通过**，本报告不宣布「1:1」。参考图与当前实现为**并排人工目视**用，不作为自动像素回归基线（任务书 §4：人工批准后才可作基线）。

---

## 8. 与效果图仍存在的差异及原因

| # | 差异 | 原因 / 处置 |
|---|---|---|
| 1 | **字体不同源**。参考图在 macOS 上渲染，字体文件未随图提供 | 无法识别原字体，也不声称识别。改用 OFL 授权的 Noto Serif/Sans SC 子集，使字形在所有平台确定。字面宽度、笔画对比与 macOS 宋体仍有可见差异 |
| 2 | 品牌标是**自绘笔触风**矢量，不是原 Logo | 参考图未提供原始 Logo 文件。按构图与配色复刻（实心双色阴阳体 + 不等粗外圈 + 金色渐变 + 24° 倾斜），笔触断口位置与原始手绘不同 |
| 3 | 黄历日期卡是**两级**（吉/凶），参考图是三级（吉/平/凶） | 后端通书口径只有两级，没有可解释、可版本化的第三类规则。页面显式说明该差异并解释依据字段 |
| 4 | 日期卡"简短依据"是**通书宜忌原文**（如「宜：祭祀 · 祈福 · 求开光」），参考图写的是「宜交易 / 宜观望 / 忌追涨」 | 后者是行情改写，属于把传统择日观念伪装成买卖建议，按铁律禁止。原文可追溯、可核对 |
| 5 | 历史表现区**没有 +12.6% / 72% / 仓位建议** | 参考图数字未给出口径。本页给的是可核对的研究统计（区间/持有期/复权/数据截止/样本量与重叠披露），并明确不是策略回测 |
| 6 | 时间窗口右栏没有「关键触发因子（高权重/中权重）」 | 后端未为单个窗口提供因子贡献分解，生成权重即伪造。改为展示该窗口原始结果、依据、可用性与风险 |
| 7 | 时间窗口主视图是**阶梯线 + 离散点**，参考图是平滑曲线 | 月度/周度数据在两点之间没有观测，平滑插值会暗示"每天都有预测值"。按用户要求改为阶梯线并在图注说明 |
| 8 | 热力图是**单色强度带**，参考图是四档色块（强共振/次强日/普通日/低关注） | 后端没有四档分类规则；用"可用引擎规则强度均值"的连续色带，色带含义写在图例里，且不使用红涨绿跌语义 |
| 9 | 分档较多（全窗口三模型方向恒为"偏强"） | 真实数据的特征：规则分集中在 50–70，`direction` 为相对 50 分的三档方向，因此长期为 +1。页面已把"连续强度"与"方向"两个量都展示，读者可直接看分数本身 |
| 10 | 时间窗口页仍有**首屏冷启动 3–7 秒** | 逐日/月度/周度都要按交易日逐日求值。已批量求值（4.5×）+ 进程内缓存（命中 0.2s）；未做后台预计算 |
| 11 | 部分页面（综合/八字/紫微/古籍）的**信息架构未重排** | 本轮范围是品牌视觉校准 + 黄历 + 时间窗口；R2 的页面结构整改仍待后续批次 |

---

## 9. R1 遗留问题的处置

### 9.1 002008 隔离页的瞬时重复元素

**排查过程（不是猜测）**：

1. 写探针在页面里装 `MutationObserver`，对 `[data-testid="unsupported-fixture-error"]` 的**并发数量**取样，覆盖三种进入方式（硬导航 / reload / 软导航）× 多轮 — 并发峰值恒为 1；
2. 在 `soft` 场景下预热 `/_next/static` 磁盘缓存后再进 — 峰值仍恒为 1；
3. 用真实 spec 重复回放 12 次、15 次 — 全通过；
4. 分析服务端 HTML 结构，找到真实存在的中间态窗口：
   `<!--$?--><template id="B:0"></template>`（Suspense 占位）→ `<div hidden id="S:0">整页内容</div>` → 文档末尾 `<script>$RC("B:0","S:0")</script>` 把它搬进边界。
   在"内容已在 DOM 但尚未搬入边界"与"React 尚未 hydration 完成"之间，DOM 上是**过程态**。

**结论**：当前生产构建下未能复现两份并存；但原测试用固定 `waitForTimeout(1200)` 等就绪，会在这个过程态窗口上做严格模式断言——**测试写的是"猜时间"，不是"等状态"**。

**处置（结构性，不是掩盖）**：

- `AppShell` 在客户端挂载后写入 `data-app-ready="true"`（服务端渲染 `false`，SSR 与首次客户端渲染一致，不引入新的一致性差异），并写入 `data-fixture-mode`；
- `r1-refinement.spec.ts` 改为等待 `[data-app-ready="true"]`，并把隔离卡断言改为 `toHaveCount(1)` —— **显式断言唯一性**，而不是用 `.first()` 绕过。若服务端内容被重复插入，这项断言会立刻变红；
- 删除其余用例里的固定延时等待（保留搜索框输入后的防抖等待，那是真实防抖，不是就绪等待）。

### 9.2 报告数量同步

见 §6.2：R1 报告的 17/18 与 91/92 是修复前的数字；本轮默认全套 **108/108 通过**（既有 92 + 新增 16），并已在本报告与本轮提交的测试文件中如实对应。

### 9.3 顺带修掉的两处真实缺陷

| 缺陷 | 影响 | 处置 |
|---|---|---|
| 手写 fixture 与真实后端**量纲不一致**（周度 `mean=73.6` vs 真实为方向均值 ∈[−1,1]，`daily_results` 为空） | 演示模式与真实模式给出两种数字，读者无法分辨 | 月度/周度/逐日/黄历样本全部改为**由真实后端算出后冻结**的 JSON，与端点响应逐字段同构；`batch-a-remediation.spec.ts` 的期望值同步更新 |
| 演示模式下切档位复用同一份样本（"今日"渲染成 20 天、切到「5 个交易日」仍显示 1 日结果） | 粒度错误的演示数据会被当成结论 | 每个档位读自己的固定样本；样本里没有的参数组合显式提示「该参数组合在演示模式中没有样本」 |
| bazi 页多出一行参考图中不存在的二级导航（侧栏已有同样入口） | 上下文栏 72px，且占掉首屏 37px | 删除该行，上下文栏降至 37px；这也是本轮几何指标回到参考图区间的直接原因 |

---

## 10. 未验证 / 需人工确认

1. **像素级视觉回归基线**未建立：按任务书 §4，需人工批准网页截图后才可作为基线。本轮的并排对照图为人工目视用。
2. **真实模式数值的正确性依赖隔离后端与真实 hfq 快照**：`tencent_hfq_import` 快照的 `market_data_version` 与生产一致，但研究结论本身（吉/凶日收益差异）**不构成任何可交易结论** —— 页面已写明是描述性统计且不做显著性检验。
3. **交易日历覆盖边界**：SSE/SZSE 实测日历覆盖到 **2026-09-18**。以"今天（2026-09-21）"为基准日的分析，其"未来 20 个交易日"落在覆盖之外，页面会显示「日历覆盖不足」并说明原因 —— 这是**数据边界，不是功能缺陷**；验收因此使用 `?asOf=2024-11-15`（覆盖范围内）。
4. **BSE（北交所）无实测日历**，该交易所的标的会显式降级为「无法判定交易日」，不产出日期卡。
5. **`▴ ▸ ▾` 三个字形**不在 Noto CJK 子集内，会回退到系统字体（仅用于小尺寸排序箭头）。
6. 首次冷启动的时间窗口页仍需 3–7 秒（已批量 + 缓存），未做后台预计算或流式分段返回。
