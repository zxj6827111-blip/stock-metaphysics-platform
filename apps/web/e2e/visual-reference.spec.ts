import { expect, test } from "@playwright/test";

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
    await page.goto(url);
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator('[data-testid="page-loading"]')).toHaveCount(0);
    await page.screenshot({ path: `test-results/visual-reference/${key}/candidate.png`, fullPage: false });
  });
}
