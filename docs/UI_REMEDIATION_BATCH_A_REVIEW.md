# 股票玄学多模型研究平台 UI 整改复核与补验交付报告（批次 A 及补验完整版）

> **复核结论摘要**：
> - **基线 Commit**：`d50a000`
> - **工作分支**：`codex/ui-remediation`（独立 worktree: `E:\Software Development\stock-metaphysics-platform-ui`）
> - **Phase 4 行情剥离分支**：`phase4/market-fallback-split`（后端修改已全量剥离至该分支，UI 分支保持零后端变更）
> - **后端差异校验**：`git diff d50a000 HEAD -- "src/**/*.py" "apps/api/**/*.py"` 为**完全空**（0 diff）。
> - **阶段边界**：**严格只处理批次 A 及“批次 A 补验”，在批次 A 终点明确停止，未进入批次 B，未合并至主分支**。
> - **自动化测试结果**：**65/65 全量 Playwright E2E 测试通过**（其中专项补验测试 21/21 通过）。
> - **截图与视觉验证**：10/10 页面 1672×941 全屏截图采集成功，等待超时具备严格退出失败保障（退出码 0）。

---

## 一、补验五项核心问题修复清单

根据复核反馈，本次补验严格聚焦于前端展示正确性与测试断言，并在 `codex/ui-remediation` 上完成了以下五项问题的彻底解决：

### 1. P1 Fixture 零后端请求与非支持标的严格隔离
- **问题**：在 `?fixture=ui-reference` 演示模式下，重新计算仍向后端发送真实请求；切换到非 600519 标的时，悄悄向后端发送真实分析请求并持久化落库。
- **解决**：
  1. `apps/web/lib/analysisStore.ts`：在 fixture 模式下发起分析时，若非 `600519` 标的直接抛出拦截错误，严禁向后端发起 `api.post`；
  2. `apps/web/lib/dataSource.ts`：在 `loadAnalysis` 中增强阻断，fixture 模式仅允许 600519；
  3. `apps/web/app/stock/[code]/overview/page.tsx`：重新计算按钮在 fixture 模式下直接重载本地 `overviewFixture`，不产生任何后端网络请求；
  4. **全页面隔离遮罩与警示**：在 `overview`、`bazi`、`huangli`、`ziwei`、`timeline`、`backtest`、`evidence`、`conflicts` 8 个路由中，若检测到 `code !== "600519" && isFixtureActive()`，统一渲染专用隔离容器 `[data-testid=unsupported-fixture-error]`，明确提示：“演示数据模式当前仅内置贵州茅台 (600519) 样本。检测到您正在访问非支持标的，为保证演示数据与真实研究严格隔离，已阻断向后端发起真实分析与数据持久化”，并提供「切换至真实分析模式」按钮；
  5. `StockSearch.tsx` 与 `StockSwitchModal.tsx`：在 fixture 激活时，搜索建议直接使用本地内置标的清单，禁止向 `/api/v1/stocks/search` 发起后端请求。
- **验证**：E2E 测试 `在演示模式下点击「重新计算」，严禁向后端发起任何网络请求` 与 `访问非 600519 标的且带 fixture 参数时，阻断真实分析与持久化，展示明确隔离警告` 均稳定通过。

### 2. P1 时间窗口 Fixture 结构对齐真实 Schema 与具体可用值
- **问题**：`timeline` 页面的 fixture 存在强制类型转换 `as unknown as ApiOpinion/ApiConsensus/ApiConflict`，掩盖了字段缺失；且存在“不可用”状态及基准分析日期为“—”的破损情况。
- **解决**：
  1. `apps/web/lib/fixture.ts`：彻底重构 `timelineMonthsFixture`，严格对齐后端 `ApiOpinion`、`ApiConsensus`、`ApiConflict` 类型定义，完全移除全部 `as unknown as ...` 伪类型断言；
  2. 四个月份（2024-11 至 2025-02）的八字、紫微、黄历三模型均给出具体的 `availability: "ok"`、具体的分数（78, 65, 82, 85 等）与具体研判方向（`bullish`/`bearish`/`neutral`），严禁出现 `unavailable` 或 `不可用`；
  3. 补全 `multiAnalysisFixture.as_of = "2024-11-15 14:32:00"`，确保时间窗口页面基准分析日期正常渲染出具体时间戳，而非破折号 `—`。
- **验证**：E2E 测试 `时间窗口页面基准日期展示正常，四个月份三模型评分与方向具体可用，绝不显示「不可用」` 验证通过，页面中无任何 `不可用` 徽标。

### 3. P1 后端行情代码变更完全剥离
- **问题**：工作分支 `codex/ui-remediation` 曾混入对 `akshare_provider.py` 和 `analysis.py` 的修改，违反了“仅处理前端与测试，不修改或覆盖 Phase 4 工作”的原则。
- **解决**：
  1. 将所有涉及 AKShare 本地兜底和行情解析的后端变更，单独提取并创建独立分支 `phase4/market-fallback-split`，留待后续 Phase 4 专项目标评审；
  2. 在 `codex/ui-remediation` 分支上执行完全回退，撤销全部后端修改；
  3. 执行 `git diff d50a000 HEAD -- "src/**/*.py" "apps/api/**/*.py"` 校验，确认后端代码 diff 严格为 0。
- **验证**：已自动化断言确认 UI 分支对 Python 后端代码无任何侵入。

### 4. P2 首页最近分析记录真实会话流转
- **问题**：首页最近分析此前为固定空态或硬编码卡片，未实现真实会话内的分析历史流转。
- **解决**：
  1. 新建 `apps/web/lib/historyStore.ts`，基于浏览器 `sessionStorage`（key: `smp_recent_analyses_session`）实现真实分析会话记录管理；
  2. 严格限制最大记录上限为 3 条，按分析完成时间逆序排列（最新在前），并提供数据防篡改校验；
  3. 在 `analysisStore.ts` 成功完成股票分析后，自动调用 `recordAnalysis({ stock_code, name, analyzed_at, overall_score, summary })`；
  4. 首页（`apps/web/app/page.tsx`）在正常模式下，初次加载若无历史展示诚实空态 `[data-testid=recent-empty]`；当会话中产生分析记录后，动态读取并呈现历史分析卡片 `[data-testid=recent-analysis-card]`。
- **验证**：E2E 测试 `正常模式下无记录显示空态，完成分析后返回首页记录真实呈现（最多保留 3 条）` 完整模拟“无记录空态 → 发起分析 → 返回首页 → 显示该股票分析卡片”全流程并通过。

### 5. P2 截图等待超时严格失败与主分析成功共识/冲突失败容错
- **问题**：
  - `capture-screenshots.mjs` 在 `waitForSelector` 超时时使用了 `.catch(() => null)` 吞噬了异常，导致截图破损时依然报告成功；
  - 缺乏“主分析接口成功、但共识/冲突计算接口返回 500”的真实容错测试；
  - 缺乏各页面关键内容层级 DOM 结构断言。
- **解决**：
  1. 改造 `capture-screenshots.mjs`：移除所有 `.catch(() => null)` 容错，一旦页面渲染超时（如超过 15000ms）、关键标题缺失或 loading 未能在超时内脱离 DOM，立即抛出未捕获异常并以非 0 状态码退出脚本；
  2. 在 `e2e/batch-a-remediation.spec.ts` 中为全部 10 个页面补充深层内容断言（如 `factor-table`、`four-pillars-table`、`twelve-palaces-grid`、`evidence-filter`、`conflict-accordion` 等）；
  3. 新增专项测试 `主分析接口成功但共识与冲突接口返回 500 时，页面优雅降级且不崩溃`，拦截 `/api/v1/analysis/{id}/consensus` 和 `conflicts` 为 HTTP 500，验证页面八字及主盘面照常呈现，共识与冲突卡片显示“服务暂不可用”，控制台与 UI 均无白屏与崩溃。
- **验证**：截图脚本执行 10 页全绿；5 项专项补验测试全部通过。

---

## 二、人工比图与自动视觉回归的区别明确

根据交付要求，在此对本系统采用的两种验证体系进行明确的职责与边界划分：

| 维度 | 人工比图 (Manual Visual Comparison) | 自动视觉回归 (Automated Visual Regression) |
|---|---|---|
| **执行载体** | `apps/web/scripts/capture-screenshots.mjs` | `apps/web/e2e/*.spec.ts` (Playwright Test Runner) |
| **产物形态** | 1672×941 物理分辨率全屏 PNG 图片集合（存放在 `artifacts/ui-review/`） | 结构化测试通过报告、控制台断言日志、退出码（0 或 1） |
| **比对基准** | 设计规范真值图 `doc/ui-reference/*.png` | 代码中显式编写的 DOM 结构断言、数据属性及文本规则 |
| **验证重心** | **宏观排版与视觉美学**：全局间距节奏、色彩对比度、字体对齐、图表留白、栅格对称性 | **功能与数据正确性**：元素存在性、状态机流转（Loading/Empty/Error）、字段映射、隔离阻断、网络容错 |
| **失败判定** | 人工肉眼评审：发现与参考图存在明显间距失衡、配色违规、排版错位时打回 | 自动化硬性门禁：任何断言不满足、选择器等待超时、抛出非预期 Console Error 即失败 |
| **超时与异常保障** | **严格失败**：脚本内移除所有吞噬异常的 `catch`，任何元素超时或页面挂起立即进程退出码 1 | **严格失败**：Playwright 默认 30s 元素动作超时，发生即标红失败 |
| **互补关系** | **自动测试保障“内容真实且结构对齐”，人工比图保障“视觉还原与设计质感”**。二者缺一不可，构成双层安全网。 |

---

## 三、修改文件清单（补验累计）

| 文件路径 | 改动类型 | 说明 |
|---|---|---|
| `apps/web/lib/historyStore.ts` | **新建** | 真实会话历史分析存储管理（sessionStorage，最多 3 条） |
| `apps/web/lib/analysisStore.ts` | 强化 | 增加分析完成时自动入库会话历史；fixture 模式下非 600519 强阻断 |
| `apps/web/lib/dataSource.ts` | 强化 | fixture 模式非 600519 强阻断；空态与非伪造数据逻辑保持 |
| `apps/web/lib/fixture.ts` | 重构 | 完善时间窗口具体值（无 unknown 断言，availability 为 ok，补全 as_of） |
| `apps/web/lib/stockCatalog.ts` | **新建** | 通用股票基础清单与字典常量，解除底层 Store 对 UI 组件的反向依赖 |
| `apps/web/app/page.tsx` | 动态化与合规 | 接入 `historyStore`，无记录展示诚实空态；正常模式无行情时不伪造正弦波动折线 |
| `apps/web/app/stock/[code]/overview/page.tsx` | 隔离与重新计算 | 增加非 600519 fixture 隔离态；重新计算在 fixture 下 0 网络请求 |
| `apps/web/app/stock/[code]/bazi/page.tsx` | 隔离 | 增加非 600519 fixture 隔离态 |
| `apps/web/components/shell/ResearchPage.tsx` | 隔离 | 6 个子页面（黄历/紫微/时间窗口/回测/证据/冲突）统一支持非 600519 fixture 隔离态 |
| `apps/web/components/stock/StockSearch.tsx` | 隔离与解耦 | fixture 模式下搜索建议仅使用本地数据；解耦引入 `stockCatalog` |
| `apps/web/components/stock/StockSwitchModal.tsx` | 隔离与解耦 | fixture 模式下切换标的仅使用本地数据；解耦引入 `stockCatalog` |
| `apps/web/components/stock/StockContextBar.tsx` | 解耦 | 解耦引入 `stockCatalog` |
| `apps/web/scripts/capture-screenshots.mjs` | 健壮性 | 移除超时 swallow catch；增加 `document.fonts.ready` 字体解析等待 |
| `apps/web/e2e/batch-a-remediation.spec.ts` | 扩充 | 由原 13 项扩充至 21 项（增加 5 大专项补验测试及 3 项标的切换测试） |
| `docs/UI_REMEDIATION_BATCH_A_REVIEW.md` | 文档 | 完整记录补验过程、两类测试区别、测试数量与当前 Commit SHA |

---

## 四、自动化测试与执行结果汇总

### 1. 当前提交 SHA 状态
- 工作分支：`codex/ui-remediation`
- 最新提交 SHA：`2d4d5c8`
- 后端 diff 检验：
  ```bash
  git diff d50a000 HEAD -- "src/**/*.py" "apps/api/**/*.py"
  # 输出为空，零后端变更
  ```

### 2. TypeScript 类型检查
- **命令**：`npm run typecheck`
- **退出码**：`0`
- **结果**：全量编译 0 错误。

### 3. 前端生产构建（Next.js Build）
- **命令**：`npm run build`
- **退出码**：`0`
- **结果**：13 个路由页面全部成功生成，无类型错误，无静态构建异常。

### 4. 全量 Playwright E2E 测试集
- **命令**：`npx playwright test`
- **退出码**：`0`
- **实际测试总数**：**65 passed (3.2m)**
- **详细分布**：
  1. `e2e/batch-a-remediation.spec.ts`（21 passed）：
     - 黄历真实字段映射与宜忌验证（1 项）
     - 正常模式下演示数据与伪造曲线清除（2 项）
     - 正常模式下首页最近分析真实性（1 项）
     - 十页离线 Fixture 完整性与深层内容结构断言（10 项）
     - **补验专项 1**：Fixture 零后端请求验证（1 项）
     - **补验专项 2**：非支持标的演示模式隔离验证（1 项）
     - **补验专项 3**：时间窗口演示数据具体值与可用性验证（1 项）
     - **补验专项 4**：真实会话历史记录流转验证（1 项）
     - **补验专项 5**：主分析成功但共识/冲突接口 500 容错验证（1 项）
     - 标的切换与手动输入股票（如 002008）查询验证（3 项）
  2. `e2e/core-flow.spec.ts`（31 passed）：
     - 全局外壳、导航菜单、首页搜索、综合研判五大必答问题、八字 DOM 盘、古籍抽屉、Phase 2 页面导航与无控制台错误。
  3. `e2e/layout.spec.ts`（8 passed）：
     - 1672×941 与 1440×900 分辨率下无横向滚动条溢出，顶栏侧栏规范与设计令牌合规。
  4. `e2e/research-status-banner.spec.ts`（5 passed）：
     - 真实研究状态与合成数据横幅提示校验。

### 5. 截图脚本采集执行
- **命令**：`node scripts/capture-screenshots.mjs --ci`
- **退出码**：`0`
- **结果**：10 个页面全部于 1672×941 分辨率下采集完成，已保存至 `apps/web/artifacts/ui-review/`：
  - `01-home.png`
  - `02-overview.png`
  - `03-bazi.png`
  - `04-ziwei.png`
  - `05-backtest.png`
  - `06-factors.png`
  - `07-conflicts.png`
  - `08-huangli.png`
  - `09-evidence.png`
  - `10-timeline.png`

---

## 五、停止与等待复核声明

> [!IMPORTANT]
> **遵规与停止声明**：
> 1. 本次工作已完整落实用户提出的五项要求，完成“批次 A 补验”；
> 2. 后端行情修改已剥离至 `phase4/market-fallback-split` 分支，当前分支保持零后端代码侵入；
> 3. **严禁合并主分支**：当前代码严格保留在 `codex/ui-remediation` 工作分支；
> 4. **暂停批次 B**：未启动批次 B 的视觉排版整改；
> 5. **正式停下等待复核**。
