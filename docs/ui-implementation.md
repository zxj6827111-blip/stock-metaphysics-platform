# UI 实施说明 · Phase 1

> 面向前端开发者与 Phase 2 接手者。
> 设计规范原文：[`doc/architecture/uiux_spec_v1.md`](doc/architecture/uiux_spec_v1.md)
> 视觉真值：[`doc/ui-reference/*.png`](doc/ui-reference/)（1672 × 941）

---

## 1. 本轮交付范围

| 页面 | 路由 | 参考图 | 状态 |
|---|---|---|---|
| 首页 | `/` | `01_home.png` | ✅ 完成 |
| 综合研判 | `/stock/[code]/overview` | `02_integrated_analysis.png` | ✅ 完成 |
| 八字详情 | `/stock/[code]/bazi` | `03_bazi_detail.png` | ✅ 完成 |
| 其余 9 个模块 | `/stock/[code]/huangli` 等 | `04`–`10` | 占位页（明确说明未实现，避免 404） |

**核心约束（README/AGENTS.md UI_RULES）**：

1. 页面风格偏研究终端，不做娱乐算命风；
2. 评分只是摘要，**原始盘面必须可见**；
3. 共识与冲突必须同时支持，**不允许用平均分掩盖冲突**；
4. 历史统计与术数判断必须视觉分区；
5. 任一模型失败不能拖垮整页；
6. 前端**禁止重新计算术数**，只展示后端确定性数据；
7. 禁止 `background-image: url(reference.png)` 或整页 `<img>`（有测试强制）。

---

## 2. 技术栈

```
Next.js 15.5（App Router，React 19）
TypeScript 5（strict）
Tailwind CSS v4（CSS-first 配置，@theme）
ECharts 6 + echarts-for-react（SVG renderer）
Zustand 5
Playwright 1.63（E2E + 截图）
```

> **未引入第三方图标库**：`components/shell/Icons.tsx` 为内联 SVG（16px 网格、1.5px 描边），
> 避免额外依赖并精确控制尺寸。

---

## 3. 设计令牌

定义在 [`apps/web/app/globals.css`](apps/web/app/globals.css) 的 `@theme` 块中。

### 3.1 色板来源与一处偏差说明

规范文档 `uiux_spec_v1.md` §2 给出的暗色令牌是偏中性灰的（`Canvas #0B0F14` 等）。
但**实际参考图是偏蓝的深色系并带金色主色**。

处理方式：**以参考图为准落地具体色值，保留规范文档的 Token 命名与语义。**

取色方式（可复现）：对参考 PNG 做像素采样与 HSV 分桶统计。

```python
# 提取脚本思路（Phase 1 实际执行过）
from PIL import Image
import colorsys
im = Image.open("doc/ui-reference/02_integrated_analysis.png").convert("RGB")
# 统计高饱和像素的色相分布 → 金色 / 红色 / 绿色三个主色簇
```

### 3.2 Token 表

| Token | 值 | 来源 | 用途 |
|---|---|---|---|
| `--color-canvas` | `#09141F` | 参考图页面背景采样 | 页面底色 |
| `--color-surface-1` | `#0D1A25` | 参考图卡片下部 | 卡片渐变终点 |
| `--color-surface-2` | `#101F2B` | 参考图卡片上部 | 卡片渐变起点 |
| `--color-surface-3` | `#162835` | 推导 | 悬浮 / 次级面板 |
| `--color-surface-4` | `#1B3140` | 推导 | 进度条底槽 |
| `--color-border` | `#1E3444` | 参考图卡片描边 | 常规边框 |
| `--color-border-strong` | `#2A4457` | 参考图 | 强调边框、分隔 |
| `--color-ink` | `#E8EDF2` | 规范文档 | 主文本 |
| `--color-ink-sub` | `#9FAEBC` | 规范文档 | 次级文本 |
| `--color-ink-muted` | `#6F7D8A` | 规范文档 | 弱化文本 |
| `--color-ink-faint` | `#55636F` | 推导 | 提示文本 |
| `--color-gold` | `#D4B87A` | 参考图主色 | 品牌强调 |
| `--color-gold-strong` | `#ECD79F` | 参考图大标题 | 标题 / 高亮 |
| `--color-gold-dim` | `#9A8551` | 推导 | 金色边框 |
| `--color-up` | `#E8585A` | 参考图 600519 `+1.24%` 为红色 | **上涨 / 正向** |
| `--color-down` | `#4FD39B` | 参考图 000001 `-0.39%` 为绿色 | **下跌 / 负向** |
| `--color-flat` | `#7C8FA3` | 推导 | 中性 |
| `--color-warn` | `#E0A458` | 推导 | 警告（与金色区分：更暖更饱和） |
| `--color-info` | `#6B8FD4` | 推导 | 信息 |
| `--color-conflict` | `#B07CD6` | 推导 | 分歧 |

### 3.3 ⚠️ 重要偏差：涨跌配色

**规范文档 §2 写的是「Positive 偏青绿 / Negative 偏朱红」，
但参考图中的实际配色是「红涨绿跌」（A 股惯例）。**

本实现选择**遵循参考图与 A 股惯例**：

```
上涨 / 正向 → 红（#E8585A）
下跌 / 负向 → 绿（#4FD39B）
```

理由：

1. 参考图是用户指定的「Visual Source of Truth」，其中 `600519 +1.24%` 为红色、
   `000001 -0.39%` 为绿色；
2. A 股用户对「红涨绿跌」有强预期，用绿表示上涨会造成严重误读；
3. 系统的所有方向指示都同时使用**颜色 + 箭头符号（↑↓→）+ 数值符号（+ − 0）**，
   不依赖颜色单独传达信息（满足 uiux_spec §31 的可访问性要求）。

**Phase 2 若要改回规范文档的配色，必须同步：
令牌值 → 所有页面 → `apps/web/artifacts/ui-review/*/notes.md`。**

### 3.4 五行配色（仅作视觉标识）

```css
--color-wood:  #4FAE6D  木
--color-fire:  #E0605C  火
--color-earth: #C9A961  土
--color-metal: #B9C4CC  金
--color-water: #5B8FD4  水
```

> 五行配色**不表达吉凶**，只用于区分（uiux_spec §2 "禁止用吉凶颜色表达结果"）。

### 3.5 尺寸与字体

```css
--spacing-sidebar: 232px;   /* 实测参考图 231px */
--spacing-topbar:  64px;    /* 实测参考图 67px，实现取 68px */
--radius-card:     10px;
--radius-chip:     4px;

--font-sans:      "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, …
--font-mono:      "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, …
--font-serif-cn:  "Songti SC", "STSong", "SimSun", "Noto Serif SC", serif;  /* 干支大字 */
```

---

## 4. 组件清单

### 4.1 外壳（三页复用，禁止各页各写一套）

| 组件 | 文件 | 说明 |
|---|---|---|
| `AppShell` | `components/shell/AppShell.tsx` | TopBar + Sidebar + 主内容区 + 页脚 |
| `TopBar` | `components/shell/TopBar.tsx` | Logo / 副标题 / 全局搜索 / 数据状态 / 时钟 / 设置 |
| `PageHero` | `components/shell/TopBar.tsx` | 页面大标题 + 副标题 + 印章 + 右侧装饰 |
| `FooterNote` | `components/shell/TopBar.tsx` | 三段式页脚 |
| `Sidebar` | `components/shell/Sidebar.tsx` | 分组导航，未实现模块显示 `P2` 徽标并禁用 |
| `Phase2Placeholder` | `components/shell/Phase2Placeholder.tsx` | 占位页（明确说明未实现） |

### 4.2 业务组件

| 组件 | 文件 | 对应 uiux_spec §29 |
|---|---|---|
| `Card` / `CardHeader` / `Chip` / `DirectionMark` / `StatPair` / `AvailabilityChip` | `components/cards/Card.tsx` | 基础 |
| `StockSearch` | `components/stock/StockSearch.tsx` | `StockSearch` |
| `StockContextBar` | `components/stock/StockContextBar.tsx` | `StockContextBar` |
| `EngineScoreCard` | `components/cards/EngineCards.tsx` | `EngineScoreCard` |
| `ConsensusCard` | `components/cards/EngineCards.tsx` | `ConsensusCard` |
| `ConflictCard` | `components/cards/EngineCards.tsx` | `ConflictCard` |
| `DataQualityBadge` | `components/cards/EngineCards.tsx` | `DataQualityBadge` |
| `BacktestMetricCard` | `components/cards/EngineCards.tsx` | `BacktestMetricCard` |
| `EvidenceRow` | `components/cards/EngineCards.tsx` | 证据行 |
| `BaziChart` | `components/bazi/BaziChart.tsx` | `BaziChart` |
| `WuxingDistribution` | `components/bazi/BaziChart.tsx` | 五行分布 |
| `FateSummary` | `components/bazi/BaziChart.tsx` | 命局摘要 |
| `TimeStructure` | `components/bazi/BaziChart.tsx` | 时间轴 |
| `FactorBadge` / `FactorList` / `FactorTable` / `FactorDisclaimer` | `components/factor/Factor.tsx` | `FactorBadge` / `FactorTable` |
| `HuangliPanel` | `components/huangli/HuangliPanel.tsx` | `HuangliPanel` |
| `EvidenceDrawer` | `components/evidence/EvidenceDrawer.tsx` | `EvidenceDrawer` |
| `TimeWindowChart` / `DistributionChart` / `MiniTrend` | `components/charts/Charts.tsx` | 图表 |

> `ZiweiChart` / `LiuyaoHexagram` / `QimenNinePalace` 属于 Phase 2。

---

## 5. 数据模式：fixture vs 生产

这是本轮 UI 复刻的关键设计。

| 模式 | 触发 | 数据来源 | 用途 |
|---|---|---|---|
| **生产 runtime**（默认） | 无 `fixture` 参数 | 真实 API（`lib/api.ts` → `/api/backend/*` → FastAPI） | 日常使用 |
| **UI 复刻模式** | `?fixture=ui-reference` | `lib/fixture.ts` 固定演示数据 | 逐像素比对参考图 |

生产模式的数据映射逻辑全部在 [`apps/web/lib/dataSource.ts`](apps/web/lib/dataSource.ts)，
**前端不做任何术数计算**，只做字段映射与展示格式整理。

### 5.1 fixture 模式的边界（重要）

* fixture 数据**只存在于前端**，不写入任何分析数据库；
* fixture 中的**紫微斗数数据是纯展示 Mock**，代表的是参考图上的数字，
  不代表系统实现了紫微引擎；
* fixture 模式页面右下角有常驻浮标：「UI 复刻模式 · 固定演示数据 · 紫微为 Mock」，
  其 `title` 属性包含完整说明；
* `apps/web/e2e/core-flow.spec.ts` 有测试断言该浮标存在。

### 5.2 生产模式下紫微的处理

```
紫微卡片：显示「未启用」徽标 + available: false + score: null
          + 说明"引擎尚未启用（Phase 2 实现）。本系统不提供任何紫微结果，
                  也不以 0 分参与任何聚合。"
共识卡：  紫微列在"未启用（不计入）"分区，不进入 directions
```

**绝不显示 0 分。** 这是 `tests/integration/test_api.py::TestZiweiNeverFaked` 与
`apps/web/e2e/core-flow.spec.ts` 双重覆盖的契约。

---

## 6. UI 1:1 复刻流程

### 6.1 固定尺寸

参考图统一 **1672 × 941**，因此截图严格固定 viewport：

```ts
// apps/web/playwright.config.ts
{ name: "reference-1672x941",
  use: { ...devices["Desktop Chrome"], viewport: { width: 1672, height: 941 } } }
```

### 6.2 截图命令

```bash
make web-build && make web          # 或 npx next start -p 3000
make shots                          # → apps/web/artifacts/ui-review/<page>/current.png
make shots-live                     # 用真实 API 数据截图
```

脚本：[`apps/web/scripts/capture-screenshots.mjs`](apps/web/scripts/capture-screenshots.mjs)
（同时把参考图复制到对比目录，并记录控制台错误到 `capture-report.json`）。

### 6.3 对比产物

```
apps/web/artifacts/ui-review/
├── capture-report.json
├── 01-home/       reference.png  current.png  notes.md
├── 02-overview/   reference.png  current.png  notes.md
└── 03-bazi/       reference.png  current.png  notes.md
```

`notes.md` 结构：

```markdown
## 已匹配        ← 逐项列出结构与视觉已对齐的部分
## 仍有差异      ← 诚实列出未对齐的部分与原因
## 下一轮调整    ← 具体可执行的改进项
```

### 6.4 复刻优先级（按参考图包说明）

```
1. 整体结构与栅格
2. Header / Sidebar 尺寸
3. 卡片比例和位置
4. 信息密度
5. 间距
6. 字体层级
7. 色彩、边框、阴影
8. 图表尺寸
9. 图标
10. 演示文案
```

### 6.5 布局测量（实测参考图）

| 元素 | 参考图实测 | 实现值 |
|---|---|---|
| 顶栏高度 | 67px | 68px |
| 侧栏宽度 | 231px | 231px |
| 侧栏导航项高度 | ~40px | 40px（`py-[12px]`） |
| 主内容左内边距 | 14px | 14px |
| 卡片圆角 | 10px | 10px |

---

## 7. 路由与页面结构

```
/                                   首页（Hero + 最近分析 + 系统状态 + 平台能力）
/stock/[code]/overview              综合研判（引擎卡 + 共识 + 分歧 + 时间窗口 + 证据 + 验证 + 质量）
/stock/[code]/bazi                  八字详情（五行 / 四柱 / 命局摘要 / 时间结构 / 正负因素 / 古籍 / 统计）
/stock/[code]/huangli               占位（后端已就绪，UI 属第二轮）
/stock/[code]/ziwei                 占位（引擎未实现）
/stock/[code]/timeline              占位（Phase 2）
/stock/[code]/backtest              占位（Phase 2）
/stock/[code]/evidence              占位（Phase 2）
/stock/[code]/conflicts             占位（Phase 2）
/research                           占位（Phase 2）
/factors                            占位（Phase 2）
/settings                           占位（Phase 2）
```

> 占位页存在的意义：导航结构完整（uiux_spec §3），未实现模块**明确说明未实现**，
> 而不是 404 或伪造内容。有 E2E 测试覆盖这 9 个占位页。

---

## 8. 状态处理

### 8.1 Loading

* 首页：骨架屏（`.smp-skeleton`，带 shimmer 动画）
* 综合研判 / 八字：整页骨架 + `StockContextBar` 的"计算中…"状态

### 8.2 Empty

* 因子列表为空 → "暂无正向因子"
* 证据为空 → "暂无可展示的古籍条目"
* 回测无数据 → "尚无历史验证数据"

### 8.3 Error

* 后端未连接 → 卡片内提示 + 启动命令 + 指向 `?fixture=ui-reference`
* TopBar 状态灯变红，文案"后端未连接"
* **任一引擎失败不影响其他引擎**（独立 `Promise.allSettled` + 分区渲染）

### 8.4 不可用（关键）

```tsx
// 引擎卡：score === null 时
<div>该引擎当前不可用</div>
<p>{engine.unavailableReason}</p>
// 绝不渲染 "0" 或 "0分"
```

---

## 9. 可访问性与响应式

| 要求 | 实现 |
|---|---|
| 方向不只靠颜色 | `DirectionMark` 同时输出 ↑ / ↓ / →，数值同时带 + / − / 0 |
| 图表有文本摘要 | 每个图表组件渲染 `<figcaption>`（`sr-only` 或可见） |
| 抽屉可键盘关闭 | `EvidenceDrawer` 监听 `Escape` |
| 搜索框可键盘操作 | Enter 提交、Escape 关闭建议、`aria-label` |
| 未实现项可感知 | `aria-disabled="true"` + `title` 说明 |
| 1440×900 无横向溢出 | Playwright `desktop-1440x900` 项目断言 `scrollWidth <= clientWidth + 2` |
| 1672×941 无横向溢出 | 同上（`reference-1672x941` 项目） |

---

## 10. 测试

```bash
make typecheck     # tsc --noEmit
make test-ui       # Playwright（需 web 已启动）
make shots         # 截图 + 控制台错误报告
```

E2E 覆盖（40 项）：

* `e2e/core-flow.spec.ts` — 三个页面渲染、搜索交互、四柱盘 DOM 结构、
  五行条、因子 ID、免责声明、证据抽屉开合、无控制台错误、9 个占位页、紫微不伪造
* `e2e/layout.spec.ts` — 1672×941 与 1440×900 无横向溢出、侧栏尺寸、设计令牌生效

**注意**：Next.js 流式渲染/水合期间同一元素可能短暂出现两次，
测试中对可能重复的 `data-testid` 一律使用 `.first()`（应用静止后 DOM 中只有一个元素）。

---

## 11. Phase 2 UI 待办

| 优先级 | 项 | 说明 |
|---|---|---|
| P0 | 紫微十二宫盘 | `ZiweiChart`（4×4 布局，参考图 `04`） |
| P0 | 正式 Consensus / Conflict 页 | 替换展示层实现，`display_only` → `false`（参考图 `07`） |
| P0 | 时间窗口页 | 月度 + 周度热力图（参考图 `10`） |
| P1 | 历史验证页 | 完整指标 + 分布/年度稳定性/牛熊分组（参考图 `05`） |
| P1 | 古籍证据检索页 | 三栏布局（参考图 `09`） |
| P1 | 黄历详情页 | 后端已就绪（参考图 `08`） |
| P1 | 因子字典页 | 后端已就绪（参考图 `06`） |
| P2 | 研究实验室图形化 | 后端已就绪 |
| P2 | 导出 Markdown / HTML | — |
| P2 | 移动端适配 | 当前仅做了桌面与 1440/1672 的溢出校验 |
| P3 | 罗盘纹样 SVG | 替换首页当前的同心圆装饰 |
| P3 | 字体自托管 | `next/font` + Noto Sans SC，消除跨平台字形差异 |
| P3 | 事件研究返回真实分箱 | 替换 `toDistribution` 的正态近似 |

---

## 12. 已知问题

1. **字体差异**：Windows 回退到 Microsoft YaHei / SimSun，比参考图的 PingFang SC 略宽，
   导致中文字形宽度存在系统性差异（非结构问题）。
2. **收益分布图为示意**：后端返回汇总统计而非全量样本，图注已标注"示意分布"。
3. **时间窗口曲线为展示层外推**：卡片底部有明确文字说明，非真实预测。
4. **首屏含水合闪烁**：`useSearchParams` + Suspense 在静态路由上会产生一次
   短暂的"加载中…"（已被测试用 `.first()` + `toBeVisible()` 兼容）。
5. **ECharts 首屏体积**：综合研判页 First Load JS 510 kB（含 ECharts）。
   可通过 `next/dynamic` 懒加载优化。
