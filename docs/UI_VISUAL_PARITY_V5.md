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
