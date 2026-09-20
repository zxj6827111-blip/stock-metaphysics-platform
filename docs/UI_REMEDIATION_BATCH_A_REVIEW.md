# 股票玄学多模型研究平台 UI 整改复核报告（批次 A：展示正确性与验收基础）

> **复核结论摘要**：
> - **基线 Commit**：`d50a000`
> - **工作分支**：`codex/ui-remediation`（独立 worktree: `E:\Software Development\stock-metaphysics-platform-ui`）
> - **原仓库保护**：`E:\Software Development\stock-metaphysics-platform` 处于完全只读保护状态，未做任何修改与写入。
> - **阶段边界**：**严格只完成批次 A，已在批次 A 终点明确停止，未进入批次 B，未进行十页整体视觉重排**。
> - **测试结果**：57/57 全量 E2E 测试通过，10/10 页 1672×941 全屏截图比对完成（无控制台错误，退出码 0）。

---

## 一、修改文件清单与改动摘要

| 文件路径 | 改动类型 | 解决的问题与功能说明 |
|---|---|---|
| `apps/web/app/globals.css` | 样式增强 | 补全 `--color-line: #1e3444;` 映射；定义 `.smp-card-body` 与 dense 紧凑间距规范 |
| `apps/web/components/cards/Card.tsx` | 组件导出 | 导出 `CardBody` 组件，规范内边距封装 |
| `apps/web/components/cards/EngineCards.tsx` | 容错与真实性 | `ConsensusCard` 与 `ConflictCard` 增加 `null` 容错渲染，未计算时诚实展示不可用，不回退演示假数据 |
| `apps/web/components/shell/PageState.tsx` | 样式与文案 | 清理 `var(--color-line)` 为 `var(--color-border)`，转换 `**` 为 `<strong>` |
| `apps/web/components/shell/ResearchPage.tsx` | 样式 | 统一边框颜色令牌为 `var(--color-border)` |
| `apps/web/components/ziwei/ZiweiChart.tsx` | 样式 | 统一网格与标签边框颜色令牌 |
| `apps/web/lib/analysisStore.ts` | 缓存隔离 | `loadMultiAnalysis` 识别 `isFixtureActive()`，离线直接返回 fixture，避免向后端发起网络请求 |
| `apps/web/lib/types.ts` | 类型契约 | `OverviewPageData` 的 `consensus` 与 `conflict` 允许为 `null`（反映无数据真实状态） |
| `apps/web/lib/fixture.ts` | 数据准备 | 导出 `isFixtureActive()`，完善十页完整固定结构化演示数据（黄历、回测、因子字典、冲突中心、证据、时间窗口等） |
| `apps/web/lib/dataSource.ts` | 伪造数据清除 | `toDistribution` 与 `buildOverview` 增加 `isFixture` 判定，正常模式下彻底移除正弦波与高斯正态伪造分箱 |
| `apps/web/app/stock/[code]/huangli/page.tsx` | 真实映射 (P0) | 对齐 `primary` 真实对象；修复干支、生肖、建除十二值、纳音、神煞、冲煞、彭祖百忌、吉神方位、节气 9 大字段；新增传统宜忌卡片；清理样式 |
| `apps/web/app/stock/[code]/overview/page.tsx` | 真实性与降级 (P0) | 正常模式移除 `overviewFixture` 回退；外推时间窗口与收益分布在无数据时诚实展示“未运行/无样本”，不伪造走势；清理样式 |
| `apps/web/app/page.tsx` | 真实状态与空态 (P0/P1) | 系统状态右上角移除硬编码“全部正常”，根据真实引擎状态动态判定（全部正常/部分降级/后端未连接）；最近分析在正常模式无历史时展示诚实空态 |
| `apps/web/app/stock/[code]/backtest/page.tsx` | 离线隔离与样式 | 支持离线 fixture；清理 `var(--color-line)` 为 `var(--color-border)`；清理 raw markdown `**` |
| `apps/web/app/factors/page.tsx` | 离线隔离与样式 | 支持离线 fixture；清理 `var(--color-line)` 为 `var(--color-border)`；清理 raw markdown `**` |
| `apps/web/app/stock/[code]/conflicts/page.tsx` | 样式清理 | 清理 `var(--color-line)` 为 `var(--color-border)`；清理 raw markdown `**` |
| `apps/web/app/stock/[code]/ziwei/page.tsx` | 文案规范 | 清理小限说明中的 raw markdown `**` |
| `apps/web/app/stock/[code]/evidence/page.tsx` | 离线隔离 | 支持离线 fixture 数据，避免后端离线时报错 |
| `apps/web/app/stock/[code]/timeline/page.tsx` | 离线隔离 | 支持离线 fixture 数据，避免后端离线时报错 |
| `apps/web/app/settings/page.tsx` | 文案规范 | 清理 raw markdown `**` |
| `apps/web/scripts/capture-screenshots.mjs` | 验收工具优化 | 标题选择器兼容 `home-title` 与 `page-title`；增加对 `page-loading` 脱离 DOM 的等待；增加 CI 严格退出判定 |
| `apps/web/e2e/batch-a-remediation.spec.ts` | 新增回归测试 | 13 个独立测试，验证黄历映射、正常模式假数据隔离、十页离线 fixture 稳定渲染 |

---

## 二、关键问题根因与处理验证

### 1. 黄历 primary 字段映射与宜忌缺失 (P0)
- **根因**：后端 `/api/v1/analysis/{id}/huangli` 实际数据保存在 `huangli.primary`（模型 `HuangliDay`），前端原先读取 `h.today` / `h.day`，且 `fixture.ts` 中取了不存在的 `raw_huangli` 导致初值为 `undefined`，造成全部 9 个字段显示破折号 `—`。
- **处理**：
  1. `huangli/page.tsx` 改为读取 `primary = (h.primary ?? h.today ?? h.day ?? h)`，直接映射 `day_ganzhi`、`zodiac`、`day_nayin`、`duty_officer`、`day_tian_shen`、`chong_desc`、`sha_direction`、`pengzu_gan/zhi`、`cai/xi/fu_shen_direction`、`jieqi`；
  2. 修复 `fixture.ts` 读取 `rawAnalyze.huangli`；
  3. 新增传统宜忌卡片（`day_yi`、`day_ji`）。
- **验证结果**：E2E 测试 `黄历页面正确读取 primary 真实字段，不为全破折号破损态` 通过；截图显示真实生肖“龙”、值日“成日”、黄道“明堂”、纳音“杨柳木”及宜忌列表。

### 2. 正常模式下演示数据与伪造曲线回退 (P0)
- **根因**：
  - `overview/page.tsx` 在 API 请求失败时静默回退 `overviewFixture.consensus` 和 `conflict`，伪造 82 分共识；
  - `dataSource.ts` 在 `buildOverview` 中无条件计算 `Math.sin(i / 1.9 + phase) * 11` 伪造外推趋势曲线；
  - `dataSource.ts` 在 `toDistribution` 中无条件按正态假设伪造分箱直方图。
- **处理**：
  1. 仅在显式 `fixture === true`（即 `?fixture=ui-reference`）时才允许使用 fixture；正常模式若 API 失败或无数据，赋 `null`；
  2. `ConsensusCard` 和 `ConflictCard` 增加 `null` 降级渲染；
  3. 正常模式下 `timeWindow.series = []`，UI 展示诚实空态：“未来时间窗口外推尚未运行（系统不提供伪造预测曲线）”；
  4. 正常模式下 `distribution = []`，UI 展示诚实空态：“尚无历史验证样本分布数据（不采用正态假设伪造分箱）”。
- **验证结果**：E2E 拦截网络请求测试通过，确认在断网或后端未运行时绝不展示 82 分或正弦波假走势。

### 3. 首页系统状态与最近分析 (P0/P1)
- **根因**：
  - 首页系统状态右上角硬编码“全部正常”，在后端离线时依然亮绿灯；
  - 最近分析在正常模式下仍旧展示硬编码 3 只股票及伪造 sparkline 三角函数曲线。
- **处理**：
  1. 系统状态右上角改为动态计算：后端未连接时红字显示“后端未连接”，有未启用/降级引擎时显示“部分降级/未启用”，全部就绪才显示“全部正常”；
  2. 正常模式下，若本地无真实分析历史，展示诚实空态 `[data-testid=recent-empty]`：“暂无最近分析记录。在上方搜索框输入股票代码即可发起分析”。
- **验证结果**：E2E 测试 `正常模式下首页最近分析不伪造走势，若无记录显示诚实空态` 验证通过。

### 4. 样式令牌与文案规范 (P1)
- **根因**：多处直接引用未在 CSS 中定义的 `--color-line`，在部分浏览器回退为高亮色；多处直接在 JSX 文本中保留了 Markdown 的 `**` 粗体标记。
- **处理**：
  1. 全局搜索并清理全部 `var(--color-line)` 为 `var(--color-border)`；
  2. 全局替换 JSX 中的 `**` 为 `<strong>` 标签或标准中文引号；
  3. `Card.tsx` 导出 `CardBody` 组件规范内边距。

### 5. 十页离线 Fixture 隔离与截图能力 (P0/P1)
- **根因**：04-10 页面在离线模式下仍尝试请求后端 API，导致断网时无法进行离线 UI 验收；截图脚本未适配 `home-title` 且未等待 loading 态脱离。
- **处理**：
  1. `lib/fixture.ts` 补充完备全十页 fixture；各页面检测到 `isFixtureActive()` 时优先使用本地离线数据，无需后端运行；
  2. 截图脚本选择器适配 `[data-testid=page-title], [data-testid=home-title]`，增加 `[data-testid=page-loading]` 的 detached 状态等待与 CI 严格退出码判定。
- **验证结果**：10 页在后端离线拦截下全部秒级加载成功，`node scripts/capture-screenshots.mjs --ci` 退出码 0。

---

## 三、测试与自动化验证记录

### 1. TypeScript 类型检查
- **命令**：`npm run typecheck`
- **退出码**：`0`
- **输出**：`tsc --noEmit` 耗时约 8s，全工程 0 类型报错。

### 2. 前端生产打包（Next.js Build）
- **命令**：`npm run build`
- **退出码**：`0`
- **输出**：13 个路由页面（7 个静态 + 6 个动态）全部优化成功打包，First Load JS 共享 103 kB，无编译错误。

### 3. 全量 E2E 测试集
- **命令**：`npx playwright test`
- **退出码**：`0`
- **测试通过率**：**57 passed (3.4m)**
  - `e2e/batch-a-remediation.spec.ts`：13/13 通过（覆盖黄历真实字段映射、正常模式假数据隔离、离线十页完整渲染）
  - `e2e/core-flow.spec.ts`：31/31 通过（核心流程、五大必答问题、四柱盘表格、证据抽屉、Phase 2 页面导航）
  - `e2e/layout.spec.ts`：8/8 通过（1672×941 与 1440×900 无横向溢出、设计令牌合规）
  - `e2e/research-status-banner.spec.ts`：5/5 通过（合成数据横幅提示、P0-1 验收）

### 4. 截图与视觉验证
- **命令**：`node scripts/capture-screenshots.mjs --ci`
- **退出码**：`0`
- **输出目录**：`apps/web/artifacts/ui-review/`
- **页面清单**：
  - `01-home`: `✓ 01-home title="股票玄学多模型研究平台"`
  - `02-overview`: `✓ 02-overview title="综合研判"`
  - `03-bazi`: `✓ 03-bazi title="八字详情"`
  - `04-ziwei`: `✓ 04-ziwei title="紫微斗数详情"`
  - `05-backtest`: `✓ 05-backtest title="历史验证"`
  - `06-factors`: `✓ 06-factors title="因子字典"`
  - `07-conflicts`: `✓ 07-conflicts title="模型分歧中心"`
  - `08-huangli`: `✓ 08-huangli title="黄历 / 日课详情"`
  - `09-evidence`: `✓ 09-evidence title="古籍证据检索"`
  - `10-timeline`: `✓ 10-timeline title="时间窗口"`

---

## 四、批次 A 停止声明

> [!IMPORTANT]
> **保护与停止声明**：
> 1. 本次整改已严格完成《UI效果图差距分析与修正方案》中定义的**批次 A 全部任务**；
> 2. 原仓库 `E:\Software Development\stock-metaphysics-platform` 代码保持未变动；
> 3. 本智能体**已明确停止在批次 A 终点，未启动批次 B**（十页视觉精细重排）；
> 4. 现将本复核报告及分支 `codex/ui-remediation` 完整提交，等待 Codex 独立复核验收。
