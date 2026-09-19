# Phase 2 UI 实现说明

> 参考图（Visual Source of Truth）：`doc/ui-reference/*.png`（1672×941）
> 截图产物：`apps/web/artifacts/ui-review/<page>/{reference.png, current.png, notes.md}`
> E2E：`apps/web/e2e/`（44 项 Playwright）

---

## 1. 页面清单（十个参考图全部落地）

| 参考图 | 路由 | 状态 | 后端数据源 |
|---|---|---|---|
| `01_home.png` | `/` | ✅ Phase 1 完成，Phase 2 未改动 | `/stocks/search`、`/system/*` |
| `02_integrated_analysis.png` | `/stock/[code]/overview` | ✅ **Phase 2 重做数据源** | `/analysis/multi` + `/consensus` + `/conflicts` + `/backtest` + `/evidence` |
| `03_bazi_detail.png` | `/stock/[code]/bazi` | ✅ Phase 1 完成 | `/analysis/bazi` 系列 |
| `04_ziwei_detail.png` | `/stock/[code]/ziwei` | ✅ **新增** | `/analysis/multi` 的 `ziwei_charts` |
| `05_backtest_validation.png` | `/stock/[code]/backtest` | ✅ **新增** | `/analysis/{id}/backtest` |
| `06_factor_dictionary.png` | `/factors` | ✅ **新增** | `/research/factor-definitions`、`/factor-dictionary` |
| `07_model_conflict_center.png` | `/stock/[code]/conflicts` | ✅ **新增** | `/analysis/multi` 的 `conflict` |
| `08_huangli_detail.png` | `/stock/[code]/huangli` | ✅ **新增** | `/analysis/{id}/huangli` |
| `09_classics_evidence_search.png` | `/stock/[code]/evidence` | ✅ **新增** | `/analysis/{id}/evidence`（真实 KnowledgeProvider） |
| `10_time_window.png` | `/stock/[code]/timeline` | ✅ **新增** | `/analysis/{id}/timeline/{months,weeks}` |

---

## 2. 数据层

### 2.1 `lib/analysisStore.ts` —— 会话级分析缓存

Phase 2 的 `/analysis/multi` 同时跑八字 + 黄历 + 紫微（Node 子进程排盘），
一次约 0.5–1.5 秒。而 7 个页面都需要同一份结果。

* 以 `code|variant|asOf` 为键缓存在内存 + `sessionStorage`；
* 显式 `reload()` 才重新计算；
* **不做静默后台刷新** —— 研究结论必须是"这一份"，不是"大概这一份"。

### 2.2 `lib/api.ts` 的 POST 注意事项

`api.post()` **不得**再传 `content-type` 头：`request()` 已默认设置。
传两次会让 fetch 合并成 `"application/json, application/json"`，
FastAPI 会因此把请求体当成无法解析的字节流并返回 422
`model_attributes_type`。这个坑在 2F 的 E2E 里真实踩到过，已在代码注释中记录。

### 2.3 前端不重算术数

* 三模型分数直接消费后端 `opinion.score`（Phase 1 曾在综合页对黄历因子做前端聚合，
  Phase 2 **已移除**）；
* 星曜分类、庙旺、四化都直接用后端字段；
* 前端只做字段映射与展示格式整理。

---

## 3. 组件

| 组件 | 位置 | 说明 |
|---|---|---|
| `ZiweiChartGrid` | `components/ziwei/ZiweiChart.tsx` | 十二宫盘面，**传统 4×4 环形排布**（巳午未申 / 辰…酉 / 卯…戌 / 寅丑子亥），中央为命身四化摘要 |
| `ZiweiTrine` | 同上 | 三方四正（本宫 / 对宫 / 财帛位 / 官禄位） |
| `ZiweiHoroscope` | 同上 | 大限 / 小限 / 流年 / 流月 / 流日 / 流时 |
| `VariantSwitcher` | 同上 | 顺行 / 逆行切换（默认不替用户选） |
| `PageLoading` / `PageError` / `PageEmpty` / `UnavailableBlock` / `ResearchStatusBadge` | `components/shell/PageState.tsx` | 三态与状态徽标，7 个新页面统一复用 |
| `ResearchPage` | `components/shell/ResearchPage.tsx` | 页面外壳：AppShell + PageHero + StockContextBar + 三态 |

### 3.1 环序为什么重要

紫微的三方四正（本宫 / 对宫 / 财帛 / 官禄）只有在**正确的地支环**上才直观可读。
排错顺序会让读者看到错误的相邻关系 —— 这不是审美选择，是正确性问题。

---

## 4. 参考图的"刻意偏差"清单

参考图是**视觉**真值，但其中一部分内容本项目**刻意不做**，
因为它们需要本项目没有的口径，或者属于投资建议：

| 参考图元素 | 处理 | 理由 |
|---|---|---|
| 时间轴折线（10） | 未实现 | 分数是规则强度聚合、不是时间序列指标；画曲线会暗示"分数随时间连续演化" |
| 日历热力图（10/08） | 未实现 | 需要逐日吉凶分级口径，不在 UI 造这套分级 |
| 能力雷达图（07） | 未实现 | 需要"模型能力维度"评分体系，本项目没有 |
| 语义聚类图（09） | 未实现 | 当前只有 BM25，无 embedding |
| "最佳布局窗口 / 风险提示期"（10） | 未实现 | 属于投资建议 |
| "综合评分 / 交易胜率 / 建议仓位"（08） | 未实现 | 最容易被当成投资建议的字段 |
| 量化辅助模型卡（07/02） | 未实现 | 不把"量化因子"伪装成术数模型参与共识 |
| 参考图里的书目 / 数字 / 案例 | **不内置** | 全部来自真实 API；未运行的研究不显示示意值 |

**这些偏差都写在每个页面的 `notes.md` 里。**

---

## 5. 视觉分区（Phase 2 的硬要求）

| 页面 | 分区 |
|---|---|
| 历史验证（05） | ① 术数规则强度 ② 统计有效性 —— 两块之间用左边框色带与标题明确分隔 |
| 黄历（08） | ① 传统黄历数据（通书口径） ② 与研究映射（`H_*` 因子） |
| 模型分歧（07） | 各模型方向独立卡片 + 冲突归因 + "禁止用平均分掩盖分歧"声明 |
| 古籍证据（09） | 支持 / 反证 / 中性 三栏**永远同时渲染**（空栏也要说明"为空意味着什么"） |

---

## 6. 验收流程

```bash
# 1. 构建并启动
cd apps/web && npm run build && npx next start -p 3000

# 2. E2E
npx playwright test

# 3. 截图（真实数据）
node scripts/capture-screenshots.mjs --live
#  → artifacts/ui-review/<page>/{reference.png, current.png}
#  → artifacts/ui-review/capture-report.json

# 4. 人工核对
#  逐页打开 artifacts/ui-review/<page>/notes.md 中列出的"已知差异"
```

---

## 7. 已知限制

1. 截图对比是**结构化核对**（标题、关键 testid、文本内容），不是逐像素 diff；
   中文字形跨平台差异会导致像素级差异，因此不做像素阈值判定；
2. 参考图 01/02/03 在 Phase 2 数据下未重新人工核对（E2E 覆盖结构与无控制台错误）；
3. 未做移动端适配；
4. 综合研判页 First Load JS 约 513 kB（含 ECharts），可用 `next/dynamic` 进一步优化。
