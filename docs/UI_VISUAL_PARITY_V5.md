# UI_VISUAL_PARITY_V5

> V5.1 视觉门禁报告。十张 PNG 参考图是唯一视觉真值；旧版 `UI_FINAL_VISUAL_REVIEW.md` 的“差异较大且合理”不再作为通过依据。
>
> 当前结论：**FAIL / 不允许 merge PR #3**。页面截图可以稳定生成，但像素差异仍远超门禁阈值。

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
- 关键布局区域 `pixel_diff_ratio <= 1.5%`（anchor 指标待补齐，当前记为未计算）
- `ssim`：当前未接入，不能声称通过
- 人工视觉确认：**未批准**

## 当前实测结果

来源：`apps/web/test-results/visual-reference/metrics.json`，截图由
`npx playwright test e2e/visual-reference.spec.ts --project=reference-1672x941 --workers=1`
生成。

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

1. 共享壳层：参考图的侧栏、顶部品牌区、页级 Hero、股票上下文栏尺寸/间距仍未 1:1 对齐。
2. 首页：候选图的系统时间此前取当前时钟，已改为 fixture 固定时钟；最近分析卡中的走势图形与参考图仍不同。
3. 紫微：候选保持矩形十二宫结构，与参考图方向一致；宫格尺寸、中央身份区、右侧观察栏及底部区块仍需按 1672×941 重新标定。
4. 历史验证：参考图的 9 个指标磁贴、收益分布、持有期收益、年度稳定性、牛/熊/震荡、随机对照、出生日期平移对照和实验表尚未形成同等首屏布局。
5. 黄历：参考图的今日结论、未来关键吉日、时辰窗口与底部统计区仍未形成同等布局；缺统计时只能显示 `—/未验证`，但卡位不能删除。
6. 时间窗口：参考图的 4 张摘要卡、主时间轴、右侧窗口解读、月历热力图、未来 12 周排名和触发因子卡尚未完全对齐。
7. `ssim`、anchor position/size diff 尚未实现；当前 pixel diff 只是硬门禁的第一层，不能作为完整视觉验收。

## 复现命令

```bash
cd apps/web
npm ci
npx playwright install chromium
npm run dev -- -p 3111
SMP_WEB_BASE=http://127.0.0.1:3111 npx playwright test e2e/visual-reference.spec.ts --project=reference-1672x941 --workers=1
npm run visual:diff
```

## 参考图 SHA 命令

```bash
git hash-object doc/ui-reference/01_home.png doc/ui-reference/02_integrated_analysis.png \
  doc/ui-reference/03_bazi_detail.png doc/ui-reference/04_ziwei_detail.png \
  doc/ui-reference/05_backtest_validation.png doc/ui-reference/06_factor_dictionary.png \
  doc/ui-reference/07_model_conflict_center.png doc/ui-reference/08_huangli_detail.png \
  doc/ui-reference/09_classics_evidence_search.png doc/ui-reference/10_time_window.png
```
