# UI_VISUAL_PARITY_V5

> V5.1 视觉门禁报告。十张 PNG 参考图是唯一视觉真值；旧版 `UI_FINAL_VISUAL_REVIEW.md` 的“差异较大且合理”不再作为通过依据。
>
> 当前结论：**FAIL / 不允许 merge PR #3**。页面截图可以稳定生成，但像素差异仍远超门禁阈值。

> **CI 归属说明（2026-09-23 更新，未改动本页任何实测数据、门禁阈值与结论）**：应显式决策，`visual-regression` 已从 `V5.1 acceptance` workflow 的 job 列表中移除——这是**范围推迟**而非通过。 PR #3 的 CI 验收范围现为 backend core / ziwei / typecheck / build / functional e2e。本页 FAIL 状态**未解决**；本门禁（脚本、阈值、reference、e2e spec 全部原样）将在单独的 `ui-visual-parity` 分支上恢复为独立 CI job，并作为该分支工作的通过前提。

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

## 门禁

- overall `pixel_diff_ratio <= 3%`
- 关键布局区域 `pixel_diff_ratio <= 1.5%`（**未计算**：需要先有"关键布局区域"的批准定义，
  目前 anchor 量测给的是几何矩形，不是区域像素比）
- anchor 几何：2026-09-24 起已实现（`npm run visual:anchors` →
  `test-results/visual-reference/anchors-<label>.json`，含 7 个关键矩形的
  x/y/width/height、与参考侧冻结值的 delta、以及 `firstFoldVisible`）。
  它**不是**通过/失败门，而是结构证据：像素比例掩盖的"区块掉出首屏"只有它能抓到。
- `ssim`：仍未接入，不能声称通过
- 人工视觉确认：**未批准**

## 当前实测结果

来源：`apps/web/test-results/visual-reference/metrics.json`。

> **2026-09-24 起本门禁只在生产构建上取图。** 复现命令已改：`next build` + `next start`
> 到独立 dist / 独立端口。此前用 `npm run dev` 取图，候选图左下角带 Next 开发指示器，
> 属于把开发工具混进像素差异（`docs/UI_INDEPENDENT_REVIEW_2026-09-22.md` §五）。
> `visual-reference.spec.ts` 现在断言 `[data-build-mode="production"]` 存在且
> `nextjs-portal` 不存在，并等待 `[data-charts-ready="true"]` 后才取图。

### 2026-09-24（R1.2 样板收口：02 第二行高度 + 08 纵向偏移 + 右栏拆卡）

分支 `codex/ui-visual-parity-r1-clean`，基线 `7f95139`，PR #4（Draft）。
提交构成：**4 个视觉提交 + 5 个 R1.1 整改提交 + R1.2 收口提交**
（R1.1 汇报里写的「7 commits」是错的，实际相对 main 是 9 笔，加本轮后按最终数量为准）。

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
