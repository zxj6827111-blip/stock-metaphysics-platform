# 股票玄学多模型研究平台 UI Reference Pack V1.1

本压缩包专门针对 Windows 做了兼容处理：

- ZIP 内所有文件名与目录名均使用 ASCII 英文/数字，避免中文文件名乱码。
- 所有中文 Markdown/TXT 文档使用 UTF-8 with BOM 编码。
- `images/` 内包含 10 张 1672x941 正式页面 PNG，以及 1 张总览图。

## 页面与文件对应

| 编号 | 页面 | 文件 |
|---|---|---|
| 00 | 全套缩略总览 | `images/00_overview.png` |
| 01 | 首页 | `images/01_home.png` |
| 02 | 综合研判 | `images/02_integrated_analysis.png` |
| 03 | 八字详情 | `images/03_bazi_detail.png` |
| 04 | 紫微斗数详情 | `images/04_ziwei_detail.png` |
| 05 | 历史验证 | `images/05_backtest_validation.png` |
| 06 | 因子字典 | `images/06_factor_dictionary.png` |
| 07 | 模型分歧中心 | `images/07_model_conflict_center.png` |
| 08 | 黄历 / 日课详情 | `images/08_huangli_detail.png` |
| 09 | 古籍证据检索 | `images/09_classics_evidence_search.png` |
| 10 | 时间窗口 | `images/10_time_window.png` |

## 如何放进本地项目

建议把本包整体解压后，将 `images/` 复制到：

```text
docs/ui-reference/
```

把 `docs/` 中三份方案复制到：

```text
docs/product-spec/
```

把 `prompts/` 中提示词留给本地 AI 会话使用。

## 如何要求本地 AI 读取图片

必须明确告诉 AI：

> `docs/ui-reference/*.png` 是本项目的视觉真值（Visual Source of Truth）。请逐张实际打开图片并分析，不得只根据文件名或 Markdown 猜测。页面必须以真实 React/Next.js 组件实现，不得把参考图直接作为网页背景或整页图片。

## 1:1 复核流程

参考页面统一尺寸：

```text
1672 x 941
```

开发时使用 Playwright 固定 viewport：

```ts
await page.setViewportSize({ width: 1672, height: 941 });
await page.screenshot({ path: 'artifacts/ui-review/current.png', fullPage: false });
```

每一页按以下循环：

```text
读取参考图
-> 拆解布局
-> 编码实现
-> 固定尺寸截图
-> 与参考图对比
-> 修改
-> 再截图
```

## 优先级

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

业务数字以真实 API 为准；视觉结构以 PNG 为准。

## 严禁作弊式复刻

禁止：

```css
background-image: url(reference.png);
```

也禁止把整页 `<img>` 作为最终页面。

八字盘、紫微盘、黄历、表格、图表都必须是实际 DOM / React / ECharts 组件。
