import { expect, test } from "@playwright/test";

/**
 * 视觉候选截图（唯一视觉真值 = doc/ui-reference/*.png，1672×941）。
 *
 * 必须在**生产构建**上跑，不能在 `next dev` 上跑：
 *   * dev 会在左下角注入 Next 指示器（`<nextjs-portal>`），直接进像素差异；
 *   * dev 的 HMR 浮层与 hydration 行为都会让同一页面两次截图不一致。
 * 复现命令见 docs/UI_VISUAL_PARITY_V5.md「复现命令」（已改为 build + start）。
 *
 * 截图前的等待条件全部是**可观测事实**，没有任何固定 sleep：
 *   1. `[data-app-ready="true"]` —— 客户端已接管（避开流式 SSR 中间态）；
 *   2. `document.fonts.ready` —— 自托管 Noto 字形已应用，否则量到的是回退字体；
 *   3. `page-loading` 已消失 —— 分析数据已落地；
 *   4. `data-charts-ready="true"` —— 所有 ECharts 实例已画完（见 lib/chartReadiness）。
 *      这条是本轮补上的：图表原本带 300–400ms 入场动画，截图会抓到动画中间帧，
 *      时间窗口页曾因此画出"只到左侧一段"的曲线。
 */

const pages = [
  ["01-home", "/?fixture=ui-reference"],
  ["02-overview", "/stock/600519/overview?fixture=ui-reference"],
  ["03-bazi", "/stock/600519/bazi?fixture=ui-reference"],
  ["04-ziwei", "/stock/600519/ziwei?fixture=ui-reference"],
  ["05-backtest", "/stock/600519/backtest?fixture=ui-reference"],
  ["06-factors", "/factors?fixture=ui-reference"],
  ["07-conflicts", "/stock/600519/conflicts?fixture=ui-reference"],
  ["08-huangli", "/stock/600519/huangli?fixture=ui-reference"],
  ["09-evidence", "/stock/600519/evidence?fixture=ui-reference"],
  ["10-timeline", "/stock/600519/timeline?fixture=ui-reference"],
] as const;

for (const [key, url] of pages) {
  test(`${key} 1672x941 fixture screenshot`, async ({ page }) => {
    // 冻结时钟：顶栏时间、"N 天前"之类相对时间必须逐次一致。
    await page.clock.install({ time: new Date("2024-11-15T15:00:27+08:00") });
    await page.goto(url);

    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    // 页面身份：这必须是生产构建，不是开发服务器。
    await expect(page.locator('[data-build-mode="production"]')).toHaveCount(1);
    await expect(page.locator("nextjs-portal")).toHaveCount(0);

    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator('[data-testid="page-loading"]')).toHaveCount(0);
    // 区块级异步：黄历的「历史表现」等面板在主数据之后才挂载图表。
    // 先等网络静默，再等图表完成信号，否则可能在一个"暂时为 true"的时刻取图。
    await page.waitForLoadState("networkidle");

    await page.waitForFunction(
      () => document.documentElement.dataset.chartsReady === "true",
      undefined,
      { timeout: 60_000 },
    );

    await page.screenshot({ path: `test-results/visual-reference/${key}/candidate.png`, fullPage: false });
  });
}
