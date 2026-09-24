# UI_VISUAL_PARITY_V5

> V5.1 视觉门禁报告。十张 PNG 参考图是唯一视觉真值；旧版 `UI_FINAL_VISUAL_REVIEW.md` 的“差异较大且合理”不再作为通过依据。
>
> 当前结论：**FAIL / 不允许 merge PR #3**。页面截图可以稳定生成，但像素差异仍远超门禁阈值。

> **CI 归属说明（2026-09-23 更新，未改动本页任何实测数据、门禁阈值与结论）**：应显式决策，`visual-regression` 已从 `V5.1 acceptance` workflow 的 job 列表中移除——这是**范围推迟**而非通过。 PR #3 的 CI 验收范围现为 backend core / ziwei / typecheck / build / functional e2e。本页 FAIL 状态**未解决**；本门禁（脚本、阈值、reference、e2e spec 全部原样）将在单独的 `ui-visual-parity` 分支上恢复为独立 CI job，并作为该分支工作的通过前提。

> **2026-09-24（V3-B0）更新**：`ui-visual-parity` 分支上已新增独立 job
> **`frontend-ui-structure`**（`.github/workflows/v51.yml`），在**生产构建**上跑几何与真实性门：
> `npm ci` → `npm run build` → `next start -p 3112` → 显式 readiness → 四个结构 spec
> （`v3a-backtest` / `v3b-visual` / `viewport-1440-pages` / `r1-refinement`）。
> 原 `frontend-e2e`（`npm run dev` + seeded date-scan）**未替换、未缩小**。
>
> **`ui-parity-r1.spec.ts` 首次上远端就红，已从本 job 移出并登记为独立工作包**
> （run `36003562575`：58 passed / 7 failed，7 条**全部**在该 spec 内；
> 任务书原本就把它列为"如成本允许"的可选项）：
>
> | 类 | 用例 | 现象 | 判定 |
> |---|---|---|---|
> | A | `:55`、`:110`、`:126`、`:246`、`:272`、`:313` | `SyntaxError: Cannot use import statement outside a module` —— 这些用例在 **Node 侧** `await import("../lib/…")` 动态导入 `testDir` 之外的 TS 模块 | Windows/Node 24 本地全绿（清掉 Playwright 转译缓存后复测仍绿），Ubuntu/Node 20 干净环境红 ⇒ **平台相关**；要进 CI 得先改成静态导入 |
> | B | `:470`「02 第二行两张卡与第三行卡顶 ±12px」 | `关键证据卡高 304.625 vs 参考 278`（Δ 26.6 > 12），而 Windows 本地同一断言在 ±12 内 | 02 是本轮**未改**的冻结页 ⇒ 绝对像素门对**字体/平台**敏感，不是层级退化 |
>
> 两类都**不靠放宽阈值掩盖**：A 要动导入方式，B 要么锁字体度量、要么把判据从绝对像素
> 改成相对量。已登记在下方「遗留」。
>
> **区分两件事，不许互相顶替**：
> * **普通 CI green**（5 个原 job）= Python/引擎/构建/功能 e2e 通过，**不含**视觉结构门；
> * **UI structure CI green**（新增 job）= 首屏层级与不可用语义没退化，
>   **不等于**像素差异门通过 —— 十页 pixel diff 仍是 FAIL，阈值 3% / 1.5% 一字未动。
>
> 为什么必须独立成 job：`frontend-e2e` 跑 `npm run dev`，dev 会注入 `<nextjs-portal>`
> 与左下角指示器，在它上面宣称 production parity 是假的；且它只跑
> `v51-regression` + `date-scan-v3`，从来**不覆盖** V3-A/V3-B 的几何门。

## 固定环境

| 项目 | 值 |
|---|---|
| Reference | `doc/ui-reference/01_home.png` … `10_time_window.png` |
| Reference SHA | 以仓库当前文件 SHA 为准，见下方命令 |
| Candidate | Playwright fixture `?fixture=ui-reference` |
| viewport | `1672 × 941` |
| deviceScaleFactor | `1` |
| locale | `zh-CN` |
| theme | dark |
| animations | 由 Playwright 稳定等待；仍需补充统一禁用 CSS |
| clock | fixture 顶栏固定为 `2024-11-15 15:00:27` |
| font | `document.fonts.ready` 后截图 |
| diff command | `cd apps/web && npm run visual:diff` |
| 取图构建 | **必须 production**（`npm run build` + `next start` 到独立 dist / 端口）；`visual-reference.spec.ts` 断言 `[data-build-mode="production"]` 存在且 `nextjs-portal` 不存在 |
| 结构门是否依赖后端 | **不依赖**：全部走 fixture，`[data-fixture-mode="fixture"]` 有断言 |

## 门禁

- overall `pixel_diff_ratio <= 3%`
- 关键布局区域 `pixel_diff_ratio <= 1.5%`（**未计算**：需要先有"关键布局区域"的批准定义，
  目前 anchor 量测给的是几何矩形，不是区域像素比）
- anchor 几何：2026-09-24 起已实现（`npm run visual:anchors` →
  `test-results/visual-reference/anchors-<label>.json`，含 7 个关键矩形的
  x/y/width/height、与参考侧冻结值的 delta、以及 `firstFoldVisible`）。
  它**不是**通过/失败门，而是结构证据：像素比例掩盖的"区块掉出首屏"只有它能抓到。
  三口径分列：`candidateMeasured` / `referenceMeasured` / `alignedComparable`；
  参考侧为 null 的字段**不算 delta**，不补猜测值凑通过率。
- `ssim`：仍未接入，不能声称通过
- 人工视觉确认：**未批准**

## 当前实测结果

来源：`apps/web/test-results/visual-reference/metrics.json`。

> **2026-09-24 起本门禁只在生产构建上取图。** 复现命令已改：`next build` + `next start`
> 到独立 dist / 独立端口。此前用 `npm run dev` 取图，候选图左下角带 Next 开发指示器，
> 属于把开发工具混进像素差异（`docs/UI_INDEPENDENT_REVIEW_2026-09-22.md` §五）。
> `visual-reference.spec.ts` 现在断言 `[data-build-mode="production"]` 存在且
> `nextjs-portal` 不存在，并等待 `[data-charts-ready="true"]` 后才取图。

### 2026-09-24（V3-B：07 模型分歧 + 10 时间窗口层级恢复，UI structure CI 上线）

独立审核结论 `UI_V3A_1_INDEPENDENT_REVIEW = PASS_FOR_V3B`，05 正式冻结。
本轮作用域只有 07 / 10，外加 CI 硬化与 05 的一条下界保护。
02 / 05 / 08 / 首页 / 八字 / 紫微 / 因子 / 古籍 **一行未改**。

#### V3-B0：`frontend-ui-structure` job

见上面「CI 归属说明（2026-09-24 V3-B0 更新）」。要点：
新增独立 job 跑**生产构建**上的结构门，原 `frontend-e2e`（dev + seeded date-scan）不动。
本地先验证过：该 job 覆盖的四个 spec 在 production build 上全绿（40 passed）。
远端首次跑（run `36003562575`）把 `ui-parity-r1.spec.ts` 一起放进去，出现 7 条红，
两类原因见上方 CI 归属说明；已从 job 移出该 spec 并登记为独立工作包，
移出后该 job 在本地复跑为 40 passed。

#### 05 filterBar 下界保护（只改测试，UI 一行未动）

V3-A.1 的 05 门只给了上界 `height <= reference + 24`。
实测 54px 而参考 67px —— 也就是说**把它压成极薄的一条也照样绿**。
本轮补下界 `height >= reference − 20`（≈47px）：容得下正常措辞波动，拒绝"整带被压扁"。
`summaryMetrics` 的 72 vs 85 已由独立审核接受，本轮**不**继续补高度。

#### 07 模型分歧中心：从"五段纵向堆叠"恢复成"三条横向带"

参考图（V3-A 已重测冻结）是 `conflictBanner 250..352` / `mainRow 352..779` /
`bottomRow 779..937` 三条带；改造前页面是
`场景切换器 → 分歧摘要 → 观点总览 → ③两栏` 一路纵向堆到底。

| 锚点 | reference | before（`9832f62`） | after（V3-B） | before Δ | after Δ | 门 |
|---|---|---|---|---:|---:|---|
| conflictBanner y / h | 250 / 102 | 294.5 / 111.4 | **249.3 / 102.8** | +44.5 / +9.4 | **−0.7 / +0.8** | ±16 |
| mainRow y / h | 352 / 427 | 572.8 / 140.4¹ | **364.0 / 426.9** | +220.8 / −286.6 | **+12.0 / −0.1** | ±20 / ±24 |
| bottomRow y / h | 779 / 158 | 844.5 / 242.6¹ | **794.9 / 175.6** | +65.5 / +84.6 | **+15.9 / +17.6** | ±24 |
| 场景切换器足迹 | 非产品内容 | 独立整行 y=249.3 h=37.3 **w=1434** | 卡头内 y=258.3 h=20.5 **w=197** | 占一整行 | **不再占行** | — |
| pageHero h | 122 | 122 | 122 | 0 | **0** | ±12 |

¹ 改造前没有行级锚点，取旧页对应内容块（③ 两栏首卡 `conflict-matrix`、
右列末卡 `historical-conflict`）的位置作参照 —— **不是**同一元素，只用于说明"堆了多深"。

做法：
- `conflict-scenario-switcher` 从独立横条移进 conflictBanner 的卡头右侧；
  `scenario-no_conflict` / `scenario-conflict` / `scenario-engine_unavailable`
  三个 testid 与链接全部保留（验收工具不再破坏被验收的东西）；
- mainRow = 左（观点总览 + 对比矩阵 + 因子级冲突）/ 右（冲突归因 + 时间尺度与假设差异），
  分栏 6:5 按参考左边界 x=245..1010（765/1411）取；
- bottomRow = 左（冲突解释与研究限制）/ 右（历史类似冲突）；
  mainRow 与 bottomRow 之间按参考图（两条带共用 y=779）收成 4px，
  否则 12px 栏距累加会让 bottomRow 顶边卡在 +23.9（离 ±24 只剩 0.1px）。

**未做（按 §七 冻结）**：参考图右半的多维度能力雷达**不画** —— 后端没有统一能力维度契约；
历史冲突 `NOT_RUN` 不生成胜率 / 上涨概率 / 最佳模型；不为了贴参考 229 把产品侧栏改掉。

**已登记 trade-off**：统一侧栏 210 vs 参考 229 ⇒ 07 整列 x 偏 −21px、带宽 +23px。
横向比较一律看**内容宽度与相对分栏**，不看绝对 x。

#### 10 时间窗口：拆成第一屏与第二层

| 锚点 | reference | before（`9832f62`） | after（V3-B） | before Δ | after Δ | 门 |
|---|---|---|---|---:|---:|---|
| pageHero h | 106 | 122.0 | **106.0** | +16.0 | **0.0** | ±12 |
| summaryTiles y / h | 228 / 150 | 247.3 / 269.6 | **231.3 / 138.9** | +19.3 / +119.6 | **+3.3 / −11.1** | ±16 / ±20 |
| mainRow y / h | 388 / 247 | 528.9 / 354.1 | **382.1 / 263.3** | +140.9 / +107.1 | **−5.9 / +16.3** | ±20 / ±60² |
| rightSummary y / h | 388 / 247 | 528.9 / 112.6 | **382.1 / 263.3** | +140.9 / −134.4 | **−5.9 / +16.3** | ±20 / ±60² |
| 分栏比 | 959 : 477 ⇒ 66.8 : 33.2 | 995 : 427 ⇒ 70.0 : 30.0 | **949.9 : 472.1 ⇒ 66.8 : 33.2** | 偏 3.2pp | **0.0pp** | ±3pp |
| 主图 SVG 宽 | — | 993 | **948**（卡宽 950） | — | 占卡宽 99.8% | ≥95% |
| 主图序列绘制跨度 | — | 982/993 = 98.9% | **888/948 = 93.7%** | — | — | ≥60% |
| 1440 横向溢出 | — | 0 | **0** | — | **0** | ≤2px |

² 参考侧 `mainRow` / `rightSummary` 底边只到 frac=0.73（与图内网格线混叠），
fixture 标 `confidence=medium` ⇒ 高度容差放宽到 ±60，
并在断言消息里写明"参考值本身不确定"，不是"我们允许差这么多"。

做法：
- 热力图与周度排名从主行左右栏里**拿出来**，放进新的 `second-layer` 带 ——
  它们塞在第一屏是把 247px 主行撑到 354px 的直接原因；
- summaryTiles 首屏只留四张卡 + 一行状态（研究状态紧凑徽标含原始码 + 三模型方向 + 运限假设），
  聚合口径 / 交易日历三层覆盖 / 来源版本 / 风险解释下移到第二层审计卡，
  **内容一行未删**（`timeline-source-method` 仍在，只是换承载位置）；
- Hero 用 `statistics` 档 + `heroMinHeight={88}` ⇒ 88+16+2 = 106 逐像素贴参考。
  不为此新增第四档变体：十张参考图 Hero 高度是 94/102/106/109/117/121/124/141 的连续谱。

**未做（按 §十三 / §十五 / §十六 冻结）**：月度不插值成日线、缺失不填 0、不发明"流周"
（判据是**粒度切换器里没有周这一档**，而不是正文不许出现"流周"二字 ——
页面必须写"传统术数没有「流周」这一层"这条边界声明）；
「关键触发因子 / 高中权重 / 仓位建议」不生成，改为一条明确的
`窗口因子归因：不可用`；周度排名只描述规则强度，不升级成投资排名。

#### 门禁不是空门：变异构建

四处故意退化（07 banner 前加 60px 假带、10 主行卡内加 400px、10 分栏改回 50/50、
逐日序列截断到 5 个点），重新 build + start 跑真实 spec ⇒ **5 failed / 7 passed**：

```
conflictBanner.top：candidate 321.3 vs reference 250 超出 ±16
mainRow.height：candidate 663.3 vs reference 247 超出 ±60（参考底边 frac=0.73、confidence=medium）
左栏占比 50.0% 偏离参考 66.8% 超过 3pp
主行又被第二层内容撑高了
x 轴标签里没有逐日覆盖的末日 12-13（序列被截短：摘要带说有 12-13，图上没有）
```

第 5 条是本轮补的：只测"序列线覆盖绘图区 ≥60%"**抓不到数据被截短** ——
category 轴会把 5 个点也铺满整个宽度。改成拿摘要带的「逐日覆盖 … ~ 末日」
与 x 轴标签交叉核对，才是能真正抓住"20 个点只画 5 个"的判据。

#### 十页像素差异（阈值 3% / 1.5% 一字未动，十页仍全 FAIL）

| 页 | V3-A.1 | V3-B | Δpp |
|---|---:|---:|---:|
| 01-home | 46.46% | 46.46% | 0 |
| 02-overview | 49.66% | 49.66% | 0 |
| 03-bazi | 45.59% | 45.59% | 0 |
| 04-ziwei | 40.41% | 40.41% | 0 |
| **05-backtest** | 44.13% | **44.13%** | **0** |
| 06-factors | 43.57% | 43.57% | 0 |
| **07-conflicts** | 54.74% | **54.11%** | **−0.63** |
| 08-huangli | 55.04% | 55.04% | 0 |
| 09-evidence | 44.51% | 44.51% | 0 |
| **10-timeline** | 45.05% | **46.89%** | **+1.84** |

只有 07 / 10 变化 ⇒ 共享组件（`TopBar` / `ResearchPage` 新增可选 `heroMinHeight`）
**没有回归任何冻结页**；05 的全部锚点与 V3-A.1 逐字段一致（脚本比对，非目测）。

10 升高 1.84pp 的原因与 V3-A.1 记录的同类现象一致：
把热力图与周度排名从第一屏挪走之后，第一屏右栏（窗口解释）从 112px 长到 263px 去贴参考的
等高带，而该处参考内容是"最佳布局窗口 / 最佳观察窗口 / 风险提示期间"三条**演示结论**，
本系统未选中窗口时只能给空态。像素比例奖励"内容像不像"，不奖励"结构对不对"。

#### 验证（Level 2 + 生产构建 E2E；UI structure CI 已提交待远端复跑）

- `npm run typecheck` 0 错误；`NEXT_DIST_DIR=.next-e2e npm run build` 通过。
- 全量本地 E2E：**201 passed / 0 failed / 23 skipped**（V3-A.1 是 188；本轮新增 13 条 V3-B 用例）。
- `e2e/v3a-backtest.spec.ts` 9 条全过（含新加的 filterBar 下界）；
  `e2e/v3b-visual.spec.ts` 13 条全过；`viewport-1440-pages.spec.ts:121` 阈值 `<=900` 未动。
- `visual:anchors`：07 `candidateMeasured=8 / referenceMeasured=8 / alignedComparable=8`；
  10 同为 8/8/8。参考侧 null 的字段不计 delta。
- 后端仍是隔离副本（sqlite backup API，源库 `mode=ro`），收尾已杀掉 8000 并删副本。

#### 本轮新经验

1. **验收工具会破坏被验收的东西。** 07 的场景切换器是给截图用的，
   它自己占了 37px 一整行，直接把摘要带从参考的 250 推到 294.5。
   以后给"可切换场景"这类验收钩子加位置约束：默认进卡头或 `<details>`，不许新增整行。
2. **禁词式断言会把披露文字判成违规。** 我写 `not.toMatch(/流周/)`、
   `not.toMatch(/最佳模型/)`，结果页面**必须**存在的边界声明
   （"传统术数没有「流周」这一层"、"不会给出最佳模型"）自己触发了失败。
   真实性门应该断言**数据结构不存在**（没有那一档、没有那张表、没有那个徽标），
   不是断言**字数不存在**。
3. **折叠内容不能用 `toBeVisible()`。** `<details>` 关闭时其正文不在渲染树里，
   `innerText()` 也拿不到。判据分两层：先 `toHaveCount(1)` 证明没被删，
   再展开断言内容 —— 或直接读 `textContent`。
4. **"覆盖度"类几何判据有盲区。** 截断数据在 category 轴上照样铺满宽度，
   必须找一条**独立来源**（这里是摘要带的日期区间）交叉核对。

#### V3-B 遗留（已登记，未自行绕门）

1. **`ui-parity-r1.spec.ts` 不能作为可移植 CI 门**：A 类 6 条依赖 Node 侧动态 import
   `testDir` 外的 TS 模块，Ubuntu/Node 20 直接 SyntaxError；
   B 类 1 条把 02 的卡高锁在绝对 ±12px，跨平台字体度量一变就红。
   两者都要专门处理，不能靠放宽阈值或 `skip` 静默。
2. **07 `bottomRow` 整带底边 970.5 落在 941 之外**（参考 937）：
   外壳 12px + 4px 栏距 vs 参考三条带紧贴。门禁改用"带顶进入首屏"，
   没有为塞进 941 砍栏距或压内容。
3. **07 `mainRow` 右列在 `no_conflict` 场景留白 ~130px**：参考该处是能力雷达 + 4 条归因；
   本系统拒绝伪造雷达，而无冲突时真实归因就是 0 条。`conflict` 场景会填满。
4. `filterBar` 高 54px 仍**低于**参考 67px（本轮只补 −20 下界保护，未改 UI）。
5. 十页 pixel diff 仍全 FAIL；`key_layout_pixel_diff_ratio` / `ssim` 仍未接入。
6. 首页 / 八字 / 紫微 / 因子 / 古籍 的参考锚点仍是 R1 旧法测值，未重测。

### 2026-09-24（V3-A.1：05 历史验证收口，删除两条过大 semantic exception）

独立审核结论 `UI_V3A_INDEPENDENT_REVIEW = CHANGES_REQUIRED`。作用域**只有 05**；
07 / 10 / 首页 / 八字 / 紫微 / 因子 / 古籍 / 综合研判 / 黄历 未开工。
05 的参考侧数值**未重测、未改动**（V3-A 新测值已由独立审核接受并冻结为本轮真源）。

#### 删掉的两条例外，以及为什么不能留

| 被删门禁 | 它放行的实测偏差 |
|---|---|
| `chart.y <= reference.y + 220` | `primaryChart` 顶边 **+203.4px** |
| `filter.height <= reference.height + 102` | `filterBar` 高度 **+90.0px** |

+203px 已经不是"容差"而是"把没对齐登记成已解释"。本轮改为**通过布局收口**达到逐项容差，
并把阈值表写回 `e2e/v3a-backtest.spec.ts`（6 条 → 9 条）。

#### 布局收口的四个手段

1. **新增 `statistics` Hero 变体**（`HeroVariant` / `ResearchPageProps.heroVariant` / `HERO` 三处）。
   05 属统计/证据型页面，参考 Hero 只有 94px：`minH 104→76`、标题 `40→34px`、副标题 `14→13px`、
   星盘 `214→168` 并左移、山脊不透明度 `0.24→0.16`、竖联字号 `13→12`。
   **02 / 08 已批准的 `default` / `research` 两档数值一字未改**，未全站套 `statistics`。
2. **① 术数规则强度与 ② 统计有效性合并**为 `research-status-card` 内的两行紧凑结构，
   独立整宽 `rule-strength` 横条删除（每行 ≈36px 是首屏累计偏高的直接来源）；
   置信度/一致度与 NO_SIGNAL 口径解释进 `<details>`；
   `section-deterministic` / `section-empirical` / `rule-strength` 三个 testid 全部保留。
3. **持有期卡恢复"图为主角"**：实验选择器与状态徽标移入 CardHeader，
   INVALID_CONTROL 大警告移入对照区，outperform/underperform 方法论提醒移入第二屏，
   完整区间/基准/方法压成一行 metadata。收益分布不可用卡首屏只留一句话，
   "为什么不能高斯生成 / 不能反推"进 `<details>`，两栏改 `items-stretch` 使两卡等高。
4. **stats-summary 在无真实数据时九块磁贴照排**（`—` / `不可用` / `未验证`，不填 0），
   警告压成一行可展开 summary。此前该带是 `UnavailableBlock`，
   `summary-metrics` 锚点**根本不存在**，几何测试无从测起。
5. **controlRow 恢复参考图的四列结构**：年度稳定性 / 牛·熊·震荡分组 / 随机对照 / 出生日期平移对照。
   前两列后端没有 ⇒ 如实"不可用 / 未计算"且卡体内不画图；
   后两列只做 `random_birth_date` / `random_factor` / `shift_plus_7d` / `shift_minus_7d` 的字段映射，
   不重新计算、不为填满四张卡伪造数据。
   为此把 `reference-anchors.json` 中 05 `controlRow` note 里**已冻结**的四条列边界
   改写成机器可读的 `controlColumns` 键（数值一字未改），新增 `referenceControlColumns()` 读取口，
   避免测试里出现第二份数字。

#### before / after 实测（1672×941，production build）

| anchor | reference | V3-A | V3-A.1 | 本轮目标 | 结果 |
|---|---|---|---|---|---|
| pageHero 高 | 94 | 122.0（+28.0） | **94.0（+0.0）** | ±12 | PASS |
| filterBar 顶 y / 高 | 218 / 67 | 292.8（+74.8）/ 157.0（+90.0） | **219.3（+1.3）/ 54.0（−13.0）** | ±12 / ≤ +24 | PASS |
| summaryMetrics 顶 y / 高 | 299 / 85 | 锚点未渲染 | **292.3（−6.7）/ 72.0（−13.0）** | ±16 | PASS |
| primaryChart 顶 y / 高 | 395 / 194 | 598.4（**+203.4**）/ 166.1 | **403.8（+8.8）/ 202.5（+8.5）** | ±20 / ±24 | PASS |
| holdingPeriodCard 顶 y / 高 | 395 / 194 | 598.4（**+203.4**）/ 397.5（**+203.5**） | **403.8（+8.8）/ 202.5（+8.5）** | ±20 / ±24 | PASS |
| controlRow 顶 y / 高 | 599 / 172 | 1007.9（+408.9）/ 165.6 | **618.3（+19.3）/ 164.5（−7.5）** | ±24 / ±16 | PASS |
| resultTable 顶 y | 781 | 1185.5（+404.5） | **794.8（+13.8）** | ±24 | PASS |
| 持有期卡顶（1440×900） | — | 618.9 | **403.8** | ≤900（阈值未放宽） | PASS |
| `main` / 整页横向溢出 | — | 0 | **0** | ≤2 | PASS |

对照行内部（1672）：candidate 列左边界 `224/585/945/1306`、宽度 `353×4`、间距 `8/7/8`；
reference 列左边界 `224/586/942/1291`、宽度 `352/346/340/366` ⇒ 逐列偏差 ≤ 15px（门禁 ±20px）。
`visual-anchors.mjs` 独立口径：05 `anchorsTotal=22 / candidateMeasured=11 / alignedComparable=11`
（V3-A 时 `summaryMetrics` 测不到）。

#### 门禁不是空门：两种独立验证

删除 `ref+220` 之后必须证明新阈值会拒绝那种偏差：

1. **变异构建**：源码改回 `xl:grid-cols-4`→`2`、持有期图高 `108`→`320`（+220px），
   重新 build + start 跑真实 spec ⇒ **3 failed / 6 passed**，
   首条即 `primaryChart.height：candidate 414.5 vs reference 194 偏差 220.5px，超出 +24`。
2. **同构建 CSS 注入自检**（`apps/web/artifacts/v3a1/gate-selftest.mjs` 可重跑）：
   基线 0 条不通过，注入同样两处退化后 6 条不通过。

#### 十页像素差异：05 反而升高，如实记录

`05-backtest` 40.19% → **44.13%**（阈值 3% 与参考图未动，十页仍全 FAIL）。
分带归因：`pageHero` −4.39pp、`controlRow` −2.83pp、`summaryMetrics` −1.38pp、
`stockContextBar` −0.51pp 都在改善；升高集中在 `resultTable` 带 **+21.74pp**（y=850–940）。

已排查两种解释：
- **14px 纵向错位**：把候选在该带上移 0/10/13/14px 重比，变化率 76.02% → 77.01/77.26/77.23%，
  **不降**，假设不成立。
- **内容替换**：V3-A 在这一带是持有期卡下方的大片深色空白，V3-A.1 换成了真实的
  「持有期逐组明细」表头与灰字数据行，而参考图是 5 行带红绿彩色数字与色块的演示明细表。
  **用真实的表替换一块空白，反而离参考更远。**

与 R1.1 记录的同类现象一致：像素差异比例奖励"内容像不像"，不奖励"结构对不对"。
参考图 05 的九宫格数值、收益分布直方图、四张对照图全是演示数据，
本系统在这些位置必须显示不可用 ⇒ **这几带在拿到真实数据前不可能收敛**。
本轮未为收敛比例补画任何伪图。

#### 验证（Level 2 + 生产构建 E2E，非完整 CI）

- `npm run typecheck` 0 错误；`NEXT_DIST_DIR=.next-e2e npm run build` 通过。
- 全量本地 E2E：**188 passed / 0 failed / 23 skipped**（V3-A 是 185，本轮 spec 6→9 条）。
- `viewport-1440-pages.spec.ts:121` 阈值 `<=900` 一字未动，仍绿。
- `ui-parity-r1.spec.ts` / `r1-refinement.spec.ts` / `visual-reference.spec.ts` 全过。
- **首轮全量曾 9 条失败，全部是"本机没有后端"的环境缺口**（指纹：`factor-search` 等元素找不到，
  与本轮改动无关）。用 `output/ui-final/isolate_db.py`（sqlite backup API，源库 `mode=ro`）
  出 676 MB 快照 + `uvicorn --port 8000` 后复跑 ⇒ 50 passed，再跑全量 ⇒ 0 failed。
  前端起在 `NEXT_DIST_DIR=.next-e2e` + `next start -p 3111`，未抢他会话占用的 3000。

#### 本轮新经验

1. **"锚点未渲染"比"锚点偏 200px"更危险。** V3-A 的 `summary-metrics` 因为空态走
   `UnavailableBlock` 而根本不存在，几何测试对它无话可说，于是"这条没红"被读成"这条没问题"。
   空态必须保留可测的结构槽位（值给 `—` / `不可用`），否则门禁是瞎的。
2. **整行外框对齐 ≠ 内部结构对齐。** V3-A 的 controlRow 宽高都在 ±12 内，
   内部却是两张 50/50 卡而参考是四列。结构测试必须逐列量，且列边界要有机器可读的冻结来源。
3. **删掉一条放宽的门禁，就要同时交一份"它会拒绝"的证据。**
   否则无法区分"收紧了"与"换了一种写法继续放行"。变异构建与 CSS 注入自检成本很低（各一次 build / 零 build）。
4. **解释像素回归前先做排除实验。** "14px 错位导致 resultTable 带变差"听起来合理，
   实测平移后不降反升，才把归因落到"真实表替换空白"上。未验证的归因不写进结论。

### 2026-09-24（V3-A：05 历史验证首屏层级 + 05/07/10 参考锚点重测）

#### V3-0 参考锚点重测（先测后改）

按 R1.1 批准的方法重测 05 / 07 / 10：亮度边缘剖面 → 分栏区间分别测 → 把候选边界画回图上人工判读；
检测不出唯一边界的写 null，不估算。**旧 R1 的 sidebar / primaryCard / primaryChart / rightSummary 数值一律不复用。**

| 页 | 项 | R1 旧值 | V3-A 重测 | 说明 |
|---|---|---|---|---|
| 05 | sidebar | 224 | **206** | 旧值偏 18px |
| 05 | primaryCardTop | 298 | **218**（研究条件条顶） | 旧值把整条研究条件漏掉了，量到的是统计磁贴行 |
| 05 | topbar / Hero底 / 上下文栏底 | 60 / 155 / 208 | **61 / 155 / 209** | 基本一致 |
| 05 | 新增 | — | filterBar 218..285、summaryMetrics 299..384（9 磁贴）、primaryChart 395..589（708 宽）、holdingPeriodCard 942..1657（715 宽）、controlRow 599..771（四等分）、resultTable 顶 781 | 每行边界都由 5–16 条探测行一致给出 |
| 07 | sidebar | 229 | **229** | 新法复测同值 |
| 07 | 新增 | — | conflictBanner 250..352、mainRow 352..779、bottomRow 779..937 | 中/右再细分只有 2/4 强度，`columnSplit.right` 记 null |
| 10 | sidebar | 223 | **210** | 旧值偏 13px |
| 10 | 新增 | — | summaryTiles 228..378、mainRow/rightSummary 分栏 x=1182（16/16 一致） | 第三行顶边最强只到 frac≈0.48，如实 null |

**05 / 07 / 10 三页的参考侧矩形现已全部出自新法**，V3 后续阶段不再依赖已失效的 R1 数值。

#### 05 首屏重排

根因：页面上排着 **6 张「研究卡位」空占位卡**（每张 ~160px，合计 ~960px），
把唯一有真实数据的持有期对比推到 y=1255，于是 `viewport-1440-pages.spec.ts:121` 长期红。
空卡位既撑高页面又虚报能力。

按参考图 05 实测结构重排为：研究条件/状态 → 统计指标 → 收益分布 | 持有期对比 → 对照行 → 明细（第二屏）。

| anchor | R1.2 candidate | V3-A candidate | reference | R1.2 Δ | V3-A Δ |
|---|---|---|---|---:|---:|
| topbar 高 | 68 | 62 | 61 | +7 | **+1** |
| sidebar 宽 | 210 | 210 | 206 | +4 | **+4** |
| pageHero 宽 | 1434 | 1434 | 1433 | +1 | **+1** |
| primaryChart 宽 | — | 709.4 | 708 | — | **+1.4** |
| holdingPeriodCard 宽 | — | 716.6 | 715 | — | **+1.6** |
| controlRow 宽 / 高 | — | 1434 / 165.6 | 1433 / 172 | — | **+1 / −6.4** |
| resultTable 宽 | — | 1434 | 1433 | — | **+1** |
| holdingPeriodCard 高 | 1397.5 | 397.5 | 194 | +1203.5 | **+203.5** |
| primaryChart 顶边 y | 776.6 | 598.4 | 395 | +381.6 | **+203.4** |
| 持有期卡顶（1440） | 1255.75 | **进入 900 内** | — | FAIL | **PASS** |

已声明的 **semantic exception**（写进 `e2e/v3a-backtest.spec.ts` 并钉上界，不是静默放宽）：

> **这两条例外已在 V3-A.1 删除**（独立审核判定 +203px 不能作为永久例外）。
> 下面保留原文是为了记录当时的判断与它被推翻的过程；现行门禁见本节上面那条 V3-A.1。
1. `filterBar` 高度 +90：参考图这一带是 67px 的一行筛选条，本系统同一承载位必须放
   研究状态徽标 + 数据源标记 + 四项条件（AGENTS §9.10、§7 关键失败状态必须可见），压不进 67px。
2. 图表行顶边 +203.4：逐项可查为统一 Hero token +28（R1.2 已批准）、条件卡 +90、统计卡空态 +50。
   上界钉在「参考 +220」，并要求显著优于整改前的 776.6。

其余：删除 6 张占位卡后，没有真实数据的两个槽位（收益分布、年度稳定性/牛熊分组）
**如实标不可用且卡体内不画任何图**；持有期逐 variant × 持有期明细表从首屏卡移到第二屏「明细」，
内容一行未删（r3 的 `horizon-table` 断言随之改落点）。

#### 顺带修掉的两个残留

- **`Chip` 的 testid 从来没渲染出来**：页面写的是 `<Chip data-testid="data-source-chip">`，
  而 `Chip` 只接受 `testId` prop ⇒ 该审计钩子静默消失（新加的 V3-A 用例第一次触到才暴露）。已改为 `testId=`。
- **黄历 outlook 请求测试的过度声明**：注释原先暗示它保证"真实模式只请求一次"，
  实际它只证明 fixture 不发请求。已改为事实性表述，并**新增源码级守卫**
  `08：useHuangliOutlook 只在页面调用一次，三张展示卡不得自己取数`
  （真实模式需要 analysis_id 与后端，属结构问题就直接查结构）。
- PR #4 描述里的固定 commit 数已删除，统一改为 `git rev-list --count 7f95139..HEAD` 现算。

#### 验证

- typecheck 0；production build 通过（隔离 `.next-visual` / 3111）。
- **本地全量 E2E：185 passed / 0 failed / 23 skipped** ——
  `viewport-1440-pages.spec.ts:121` 这条从 09-21 起长期红的硬门**首次转绿**，
  阈值仍是 `<= 900`，未放宽、未 skip、未改 viewport。
- 新增 `e2e/v3a-backtest.spec.ts` 6 条；`ui-parity-r1.spec.ts` 25 条全过。
- `visual:diff` 十页仍全 FAIL（05 41.13% → **40.19%**，−0.94pp），阈值 3% / 1.5% 未动。
- `visual:anchors`：05 = candidate 10 / reference 11 / **alignedComparable 10**；
  07 = 5 / 8 / 5；10 = 5 / 3 / 3。



分支 `codex/ui-visual-parity-r1-clean`，基线 `7f95139`，PR #4（Draft）。
### 2026-09-24（R1.2 样板收口：02 第二行高度 + 08 纵向偏移 + 右栏拆卡）

提交构成：**4 个视觉提交 + 5 个 R1.1 整改提交 + R1.2 收口提交**。
总数**不背数字**，一律现算：`git rev-list --count 7f95139..HEAD`
（记录这一点本身也会新增提交，任何写死的总数都会在下一笔提交后失效）。
R1.1 汇报里写的「7 commits」是错的，当时实际是 9 笔。

**批准的产品决定**：Sidebar 统一取 **210px** 作为产品 token。
理由不是「所有参考图都是 210px」——十张参考图本身不一致（174..230，极差 56px），
无约束 L1 median interval 约 **206–209.5**；而是正式 AppShell 需要统一尺寸，
且既有 `layout.spec` 要求 `sidebar >= 210px`。不为 02 单独改 174px，也不逐页改。

**废止的门禁**：`r1-refinement.spec.ts` 的「综合研判：历史摘要标题 y<=730」。
参考图 02 第三行顶边实测 742，主图卡按参考补高后标题必然落到 ~760，
两者不可能同时成立。改为测 `[data-testid="backtest-summary"]` **整张卡的顶边**，
阈值直接读 `e2e/fixtures/reference-anchors.json` 的 `historySummary.y`（±12px），
测试里不再抄第二份数字。`risk-summary` 的可用性首屏门保留，
但从「顶边 y<=820」改成「**完整**落在 941px 内」。

| 页面 | Diff R1.1 后 | Diff R1.2 后 | Δ | 本轮结构结论 |
|---|---:|---:|---:|---|
| 01 | 44.89% | 46.46% | +1.57pp | 壳层 token 变更的连带位移 |
| 02 | 48.22% | 49.66% | +1.44pp | anchor 全面收敛，diff 反向 |
| 03 | 44.10% | 45.59% | +1.49pp | 同上 |
| 04 | 39.54% | 40.41% | +0.87pp | — |
| 05 | 40.96% | 41.13% | +0.17pp | — |
| 06 | 43.93% | 43.57% | −0.36pp | — |
| 07 | 55.45% | 54.74% | −0.71pp | — |
| 08 | 54.62% | 55.04% | +0.42pp | anchor 大幅收敛，diff 反向 |
| 09 | 44.25% | 44.51% | +0.26pp | — |
| 10 | 43.61% | 45.05% | +1.44pp | — |

**这张表第三次证明同一件事**：结构 anchor 与总体 pixel ratio 会反向。
02 的历史摘要卡顶从 −31.9px 收到 −0.4px、主图卡高从 −59.5 收到 −10.5，
diff 反而 +1.44pp；因为补高后的卡片里是**与参考图不同的真实数值与曲线**，
面积越大不匹配像素越多。按任务书 §7，本轮判据是 anchor 与首屏信息密度，不是 diff。

**02 结构 delta（candidate − reference，px）**

| anchor | R1.1 | R1.2 |
|---|---:|---:|
| topbar height | +7 | **+1** |
| primaryCard y / h | +17.3 / +9.4 | **+3.3 / +5.9** |
| primaryChart y / h | +29.6 / −59.5 | **+12.1 / −10.5** |
| rightSummary y / h | +29.6 / −19.4 | **+12.1 / −9.4** |
| historySummary y | −31.9 | **−0.4** |
| dataQuality y | +8.3 | **+0.8** |
| risk-summary y / 底边 | 未单独记录（旧断言只测顶边 <=820） | **784.1 / 839.1（完整在 941 内）** |
| x 偏移（整列） | +33 | +33（02 参考侧栏 174 是离群值，已批准不逐页对齐） |

**08 结构 delta**

| anchor | R1.1 | R1.2 |
|---|---:|---:|
| dayGrid y | **+156.3** | **+11.9** |
| dayGrid height | −6.5 | −6.5 |
| rightSummary height | **+419.5** | **−4.5** |
| primaryCard y | +67.8 | **+17.3** |
| primaryChart y / h | +105.6 / +56.4 | +18.6 / +24.3 |
| mainColumn h | +117.8 | **+12.6** |
| detailColumn h | +324.4 | **+41.7** |

达成手段（内容一条未删）：
① ② ③ ④ 的独立整行 `SectionLabel` 改为卡头内 `SectionTag`（`data-testid` 随标签保留）；
outlook 卡的口径行长文压成一行紧凑状态 + `<details>`，并与图例一起移到网格**下方**；
右栏拆成 A（选中日期/今日结论 ≈191.5px）、B（时辰窗口，短状态常驻）、C（数据状态与分类口径）
三张**纯展示**卡，数据仍由页面单次 `useHuangliOutlook()` 提供，
用例 `08：拆成三张卡后 /huangli/outlook 仍然只请求一次` 锁住这一点；
壳层统一 topbar 62px（十页实测 59..66，均值 62.1）并去掉 main 顶部 8px 留白（参考图 Hero 直接接顶栏）。

**未达成 / 待办**：
- 08 `primaryChart` 高度 +24.3px：口径行与图例现在都在网格下方，卡片因此比参考高。
- 02 `primaryChart` y +12.1px：刚好在 ±12 边界外 0.1px，未继续压（再压要动首行卡高）。
- **进入 V3 前必须用 R1.1 新测法重测 05 历史验证、07 模型分歧、10 时间窗口的 reference-side anchors**：
  这三页当前的参考矩形仍来自已宣布失效的 R1 测法（尤其侧栏 224/229/223 三个值不可信）。
  本轮未提前修改那三页布局。
- `viewport-1440-pages.spec.ts:121` 仍红：持有期对比卡顶边 1269.75 → **1255.75**
  （−14 正好等于 topbar −6 与 main 留白 −8），根因未变，仍属历史验证页布局，V3 恢复为硬回归用例。



### 2026-09-24（R1.1 整改：分支解污 + 语义反例 + 锚点口径三分）

分支：`codex/ui-visual-parity-r1-clean`（基于 `7f95139`），HEAD 见 PR。
上一轮 `codex/ui-visual-parity-r1` 保留不删；其中非视觉的 `7b00ce4` + `ad4594a`
（ADR-0013 / ADR-0014 首日阴阳运限）另置保护分支 `feat/bazi-first-day-yinyang-variant`
→ `ad4594a` 单独审核。`git diff 7f95139..HEAD` 已不含 `apps/api/routers/analysis.py`、
`src/core/stock/variant_basis.py`、`src/engines/bazi/bazi_engine.py`、
`tests/integration/test_api_variant_basis.py`、ADR-0014 与 DaYunStrip。

| # | 页面 | Reference | Diff R1 后 | Diff R1.1 后 | Δ | Anchor（candidate / reference / 双方可比较） | 结论 |
|---:|---|---|---:|---:|---:|---|---|
| 01 | 首页 | `01_home.png` | 44.36% | 44.89% | +0.53pp | 3 / 1 / 1（侧栏按 R1.1 方法重测） | FAIL |
| 02 | 综合研判 | `02_integrated_analysis.png` | 47.53% | 48.22% | **+0.69pp** | 10 / 10 / **10** | FAIL |
| 03 | 八字详情 | `03_bazi_detail.png` | 43.36% | 44.10% | +0.74pp | 6 / 5 / 5 | FAIL |
| 04 | 紫微详情 | `04_ziwei_detail.png` | 39.83% | 39.54% | −0.29pp | 5 / 5 / 5 | FAIL |
| 05 | 历史验证 | `05_backtest_validation.png` | 41.40% | 40.96% | −0.44pp | 6 / 5 / 5 | FAIL |
| 06 | 因子字典 | `06_factor_dictionary.png` | 44.04% | 43.93% | −0.11pp | 5 / 5 / 5 | FAIL |
| 07 | 模型分歧 | `07_model_conflict_center.png` | 55.21% | 55.45% | +0.24pp | 5 / 5 / 5 | FAIL |
| 08 | 黄历 | `08_huangli_detail.png` | 54.50% | 54.62% | +0.12pp | 10 / 10 / **10** | FAIL |
| 09 | 古籍证据 | `09_classics_evidence_search.png` | 44.22% | 44.25% | +0.03pp | 5 / 3 / 3 | FAIL |
| 10 | 时间窗口 | `10_time_window.png` | 43.59% | 43.61% | +0.02pp | 5 / 4 / 4 | FAIL |

**口径纠正**：R1 版那句「7 个 anchor 全部量到」把 *candidate 找到了 DOM* 说成了
接近对齐的结论。R1.1 起三个量分开报：`candidateMeasured`（DOM 找到）、
`referenceMeasured`（参考侧有人工冻结矩形）、`alignedComparable`（两侧都有值、
至少一个字段可算 delta）。只有第三种才产生 delta。

**R1 侧栏测法作废**：旧实现「#1E3444 边框长程段 + 在 x=200..261 内找最大亮度跳变」
把边界限制在了内容区里，因此 02 得到 231px。按「侧栏背景→更暗槽区」的亮度过渡
逐页重测（每页在 y=250..800 取 4–6 条探测行，同页读数完全一致）：
01=229 / 02=174 / 03=230 / 04=190 / 05=206 / 06=213 / 07=229 / 08=203 / 09=204 / 10=209.5。
极差 56px 说明参考稿自身页间不统一，故侧栏宽度不作为产品标准；
实现取 210px（十页 L1 最优区间 206–210 的上限，同时兼容既有 `layout.spec` 的 210–250 下限）。
效果：02 侧栏宽度偏差 +57→+36、首行左卡宽度偏差 −14→−3；08 侧栏 +29→+7。

**02 / 08 结构 delta（candidate − reference，px）**：
02 = topbar 高 +7、Hero 高 −2、上下文栏高 −3.7、首行卡 高 +9.4 / 宽 −3、
主图卡 高 **−59.5**、关键证据卡 高 −19.4、整列 x 偏移 +33（02 参考侧栏 174 是十页离群值）。
08 = topbar 高 +5、侧栏宽 +7、Hero 高 +13、今日摘要卡 高 −3.6、
日期网格 高 **−6.5**（自身几乎等尺寸）但顶边 y **+156.3**（被上方各层逐层推下）、
右栏首卡 高 **+419.5**（本轮把选中日详情/分类依据/原始字段/时辰不可用/数据状态合并为一张卡）。

**未调校并登记为待裁决**：02 主图卡补到参考的 278px 高，会把历史验证摘要标题推到 ~746，
与既有 `r1-refinement` 门禁「标题 y ≤ 730」互斥 —— 参考图自身的第三行顶边是 742。
本轮保持既有门禁优先，不改别人的期望值。

**本轮 pixel ratio 上升的归因**：02 在结构 anchor 全面变近的同时 +0.69pp，
因此不是几何退化，而是演示模式数据质量卡不再显示四个伪造绿勾
（改「未提供 / 未验证」并替换卡底总括句）带来的文本像素差。
该推断由锚点实测支撑，未做逐变更 A/B 拆分。按任务书 §7，总体 pixel ratio 不作为 R1.1 判据。

### 2026-09-24（ui-visual-parity R1：V0 + V1 + V2 两个样板页）

| # | 页面 | Reference | Diff 本轮前 | Diff 本轮后 | Δ | Anchor 结果 | 结论 |
|---:|---|---|---:|---:|---:|---|---|
| 01 | 首页 | `01_home.png` | 44.40% | 44.36% | −0.04pp | 已量测（Hero/上下文栏该页无对应矩形，如实标 not derivable） | FAIL |
| 02 | 综合研判 | `02_integrated_analysis.png` | 47.06% | 47.53% | **+0.47pp** | 7 个 anchor 全部量到，首屏内 | FAIL |
| 03 | 八字详情 | `03_bazi_detail.png` | 44.40% | 43.36% | −1.04pp | 已量测 | FAIL |
| 04 | 紫微详情 | `04_ziwei_detail.png` | 39.90% | 39.83% | −0.07pp | 已量测 | FAIL |
| 05 | 历史验证 | `05_backtest_validation.png` | 41.83% | 41.40% | −0.43pp | 已量测 | FAIL |
| 06 | 因子字典 | `06_factor_dictionary.png` | 43.91% | 44.04% | +0.13pp | 已量测 | FAIL |
| 07 | 模型分歧 | `07_model_conflict_center.png` | 54.48% | 55.21% | **+0.73pp** | 已量测 | FAIL |
| 08 | 黄历 | `08_huangli_detail.png` | 57.08% | 54.50% | −2.58pp | 7 个 anchor 全部量到，首屏内 | FAIL |
| 09 | 古籍证据 | `09_classics_evidence_search.png` | 44.19% | 44.22% | +0.03pp | 已量测 | FAIL |
| 10 | 时间窗口 | `10_time_window.png` | 43.50% | 43.59% | +0.09pp | 已量测 | FAIL |

**必须如实读这张表**：本轮的结构目标达成了（02 / 08 的 7 个关键矩形全部量到且
`belowFold` 为空；08 的日期网格从 y=848.9+192.5 移到 y=571.6+319.4，选中日详情从
y=1074.7 移到 y=261.3），但**像素差异比例不是完成度指标**：02 反而涨了 0.47pp，
07 / 06 / 10 也各涨 0.1–0.7pp —— 字号与字重按参考图放大后，与参考图里**不同的真实数值**
产生的不匹配像素变多。这正是复核报告 §一 警告的方向："大面积深色背景可能让结构差距很大
的页面获得较低像素差异"。十页仍全部 FAIL，3% 门禁未达成，也未尝试放宽。

证据：`output/ui-parity-r1/before/`、`output/ui-parity-r1/after/`
（每页 `candidate.png` / `reference.png` / `diff.png` / `overlay.png` / `metrics.json`，
外加 `anchors-before.json` / `anchors-after.json`）。

### 2026-09-23 及更早

| # | 页面 | Candidate | Reference | Diff Ratio | Anchor Result | 结论 |
|---:|---|---|---|---:|---|---|
| 01 | 首页 | `test-results/visual-reference/01-home/candidate.png` | `doc/ui-reference/01_home.png` | 44.47% | 未计算 | FAIL |
| 02 | 综合研判 | `test-results/visual-reference/02-overview/candidate.png` | `doc/ui-reference/02_integrated_analysis.png` | 47.22% | 未计算 | FAIL |
| 03 | 八字详情 | `test-results/visual-reference/03-bazi/candidate.png` | `doc/ui-reference/03_bazi_detail.png` | 44.40% | 未计算 | FAIL |
| 04 | 紫微详情 | `test-results/visual-reference/04-ziwei/candidate.png` | `doc/ui-reference/04_ziwei_detail.png` | 39.95% | 未计算 | FAIL |
| 05 | 历史验证 | `test-results/visual-reference/05-backtest/candidate.png` | `doc/ui-reference/05_backtest_validation.png` | 41.85% | 未计算 | FAIL |
| 06 | 因子字典 | `test-results/visual-reference/06-factors/candidate.png` | `doc/ui-reference/06_factor_dictionary.png` | 44.07% | 未计算 | FAIL |
| 07 | 模型分歧 | `test-results/visual-reference/07-conflicts/candidate.png` | `doc/ui-reference/07_model_conflict_center.png` | 54.55% | 未计算 | FAIL |
| 08 | 黄历 | `test-results/visual-reference/08-huangli/candidate.png` | `doc/ui-reference/08_huangli_detail.png` | 57.15% | 未计算 | FAIL |
| 09 | 古籍证据 | `test-results/visual-reference/09-evidence/candidate.png` | `doc/ui-reference/09_classics_evidence_search.png` | 44.26% | 未计算 | FAIL |
| 10 | 时间窗口 | `test-results/visual-reference/10-timeline/candidate.png` | `doc/ui-reference/10_time_window.png` | 43.53% | 未计算 | FAIL |

> 2026-09-23 复测（本轮 relation v3 口径改造后；**未改门禁阈值、未改 reference、未自动接受 candidate**）：
> 十页 39.95% ～ 57.15%，仍全部 FAIL；02 / 08 / 10 与上一轮相比在 ±0.06pp 内抖动。

> 05 的 45.08% → 41.85% 变化来自本轮补入的「9 指标磁贴 + 6 个参考卡位」；
> 其余页面的差异主要来自共享壳层尺寸与首屏区块数量，仍未进入 3% 门禁。

## 已确认的剩余差异

1. 共享壳层：侧栏实测 232px vs 参考图逐页 220–235px（参考图自身不一致，未强行统一）；
   顶栏 68px vs 参考图 59–66px；上下文栏 45.3px vs 参考图 47–65px。
2. `PageHero` 已有 `default` / `research` 两档；**首页 / 历史验证 / 古籍三页的专属 Hero
   尚未落地**：首页需要 ~330px 的大 Hero + 内嵌搜索卡，历史验证右侧是「历史统计 VS 传统术数」
   对照块，古籍页右侧是书影而非星盘。这三档留给各自页面整改时再接。
3. 装饰资产：`Decorations.tsx` 已加到 4 重山峦 + 顶部雾化渐隐 + 星盘 72 微刻度 / 12 向辐条，
   但仍与参考图的手绘质感不同；参考图未提供原始矢量资产，禁止整页切片。
4. 首页：最近分析卡的走势形态与参考图不同（参考图为演示曲线）。
5. 紫微：候选保持矩形十二宫结构；宫格尺寸、中央身份区、右侧观察栏及底部区块仍需按 1672×941 重新标定。
6. 历史验证：参考图的 9 个指标磁贴、收益分布、持有期收益、年度稳定性、牛/熊/震荡、随机对照、
   出生日期平移对照和实验表尚未形成同等首屏布局。
   **已知回归（本轮前即存在）**：`e2e/viewport-1440-pages.spec.ts` 的
   「持有期对比卡顶部应进入首屏」在 1440 与 1672 下都失败（实测 y=1269.75 > 900）。
   已实测归因：本轮共享排版只贡献 2.5px，其余来自 09-23 补入的 6 个卡位；该 spec 不在
   `V5.1 acceptance` CI 范围内，所以此前无人看到。留给历史验证页整改包。
7. 黄历：首屏已改成左 60% / 右 40%；参考图的「交易胜率 / 建议仓位 / 六格时辰吉凶 / 三级分类」
   在本系统**没有对应能力**，页面如实显示不可用并说明原因，不照搬、不画空卡位。
8. 时间窗口：参考图的 4 张摘要卡、主时间轴、右侧窗口解读、月历热力图、未来 12 周排名和触发因子卡尚未完全对齐。
9. `ssim` 仍未接入；anchor 的**参考侧**只覆盖能从 PNG 边框检测中确证的边界，
   检测不到的条目在 `e2e/fixtures/reference-anchors.json` 里是 `null`，不做估计。

## 复现命令

```bash
cd apps/web
npm ci
npx playwright install chromium

# 正式候选必须来自生产构建；dist 与端口都要与 next dev 隔离，
# 否则 build 会摧毁正在跑的 dev 产物（本机 3000 常有并行会话的 dev）。
NEXT_DIST_DIR=.next-visual npm run build
NEXT_DIST_DIR=.next-visual npx next start -p 3111 &

SMP_WEB_BASE=http://127.0.0.1:3111 npx playwright test e2e/visual-reference.spec.ts \
  --project=reference-1672x941 --workers=1
npm run visual:diff
SMP_WEB_BASE=http://127.0.0.1:3111 ANCHOR_LABEL=after npm run visual:anchors
```


## 参考图 SHA 命令

```bash
git hash-object doc/ui-reference/01_home.png doc/ui-reference/02_integrated_analysis.png \
  doc/ui-reference/03_bazi_detail.png doc/ui-reference/04_ziwei_detail.png \
  doc/ui-reference/05_backtest_validation.png doc/ui-reference/06_factor_dictionary.png \
  doc/ui-reference/07_model_conflict_center.png doc/ui-reference/08_huangli_detail.png \
  doc/ui-reference/09_classics_evidence_search.png doc/ui-reference/10_time_window.png
```
