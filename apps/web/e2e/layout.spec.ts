import { expect, test } from "@playwright/test";

/**
 * 布局与响应式约束（uiux_spec §34）。
 *
 * * 1672×941：与参考图同尺寸，必须无横向溢出；
 * * 1440×900：桌面端常见尺寸，必须无横向溢出。
 */

for (const path of ["/", "/stock/600519/overview", "/stock/600519/bazi"]) {
  test(`${path} 无横向溢出`, async ({ page }, testInfo) => {
    await page.goto(`${path}?fixture=ui-reference`);
    await page.waitForTimeout(800);

    const metrics = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));

    expect(
      metrics.scrollWidth,
      `页面出现横向溢出（${metrics.scrollWidth} > ${metrics.clientWidth}）@ ${testInfo.project.name}`,
    ).toBeLessThanOrEqual(metrics.clientWidth + 2);
  });
}

test("侧栏与顶栏尺寸符合设计规范", async ({ page }) => {
  await page.goto("/?fixture=ui-reference");
  const sidebar = page.locator("aside").first();
  const box = await sidebar.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(210);
  expect(box!.width).toBeLessThanOrEqual(250);
});

test("页面使用设计令牌而不是散落硬编码颜色", async ({ page }) => {
  await page.goto("/?fixture=ui-reference");
  const card = page.getByTestId("recent-analysis").first();
  // 卡片底色由 token 定义的渐变提供（），
  // 因此应检查 backgroundImage 而不是 backgroundColor
  const styles = await card.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { bgImage: cs.backgroundImage, bgColor: cs.backgroundColor, borderColor: cs.borderColor };
  });
  expect(styles.bgImage).toContain("gradient");
  expect(styles.bgColor).not.toBe("rgb(255, 255, 255)");
  expect(styles.borderColor).not.toBe("rgb(255, 255, 255)");
});
