# UI 1:1 复刻：第一轮 Prompt

你现在负责“股票玄学多模型研究平台”的第一轮前端视觉复刻。

先阅读：

- `docs/product-spec/uiux_spec_v1.md`
- `docs/product-spec/architecture_v1.md`
- `docs/ui-reference/00_overview.png`
- `docs/ui-reference/01_home.png`
- `docs/ui-reference/02_integrated_analysis.png`
- `docs/ui-reference/03_bazi_detail.png`

这些 PNG 是 Visual Source of Truth。必须逐张实际打开图片分析，不能只根据文件名或文字说明猜。

## 本轮只完成

- Design Tokens
- App Shell
- Header
- Sidebar
- StockContextBar
- 首页
- 综合研判
- 八字详情

先使用 Mock Data，不要同时接真实后端。

## 技术要求

使用 React/Next.js + TypeScript + Tailwind CSS + ECharts。
页面必须是真实组件，禁止把参考 PNG 当 background-image 或整页 img。

## 视觉验收

固定 viewport：1672 x 941。

每个页面必须：

1. 生成 Playwright screenshot；
2. 与参考图逐项对比；
3. 至少完成一轮修正；
4. 将结果保存到 `artifacts/ui-review/<page>/`；
5. 保存 `reference.png`、`current.png`、`notes.md`。

## 视觉优先级

1. 整体布局
2. Sidebar / Header 尺寸
3. 栅格与卡片比例
4. 信息密度
5. 间距
6. 字体层级
7. 色彩边框
8. 图表位置
9. 图标
10. 演示文字

完成后运行 lint、typecheck、tests，并告诉我：

- 修改文件；
- 三个页面截图路径；
- 尚未对齐的差异；
- lint/typecheck/test 结果。

不要只给计划，直接在仓库里实施。
