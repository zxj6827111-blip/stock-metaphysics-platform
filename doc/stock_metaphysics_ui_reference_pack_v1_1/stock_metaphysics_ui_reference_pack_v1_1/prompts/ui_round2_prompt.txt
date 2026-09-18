# UI 1:1 复刻：第二轮 Prompt

上一轮已经完成并验收 App Shell、首页、综合研判和八字详情。

继续逐张实际读取：

- `docs/ui-reference/04_ziwei_detail.png`
- `docs/ui-reference/05_backtest_validation.png`
- `docs/ui-reference/06_factor_dictionary.png`
- `docs/ui-reference/07_model_conflict_center.png`
- `docs/ui-reference/08_huangli_detail.png`
- `docs/ui-reference/09_classics_evidence_search.png`
- `docs/ui-reference/10_time_window.png`

不得推翻已验收的 Design Tokens、Header、Sidebar、StockContextBar 与页面基础栅格。

## 本轮完成

- 紫微斗数详情
- 历史验证
- 因子字典
- 模型分歧中心
- 黄历 / 日课详情
- 古籍证据检索
- 时间窗口

要求：

1. 保持上一轮视觉系统；
2. 先 Mock Data，视觉通过后再接真实 API；
3. 固定 1672 x 941 截图验收；
4. 每页保存 reference/current/notes；
5. 紫微十二宫必须是真实 DOM/组件；
6. 黄历必须是真实组件；
7. 历史验证必须使用真实 ECharts；
8. 因子和古籍证据必须是真实表格/列表；
9. 模型分歧必须展示冲突，不得简单平均；
10. 禁止使用参考图作为网页背景或整页图片。

最后运行 lint、typecheck、tests，并对全部 10 个页面运行截图检查。
生成：

`artifacts/ui-review/FINAL-UI-REVIEW.md`

其中逐页列出仍存在的明显差异。
