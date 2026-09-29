import { expect, test } from "@playwright/test";

test.describe("时间窗口按需计算", () => {
  test("八字大运明确显示当前与对照性别兼容假设", async ({ page }) => {
    await page.goto("/stock/600519/bazi", { waitUntil: "load" });
    const note = page.getByTestId("bazi-dayun-compatibility");
    await expect(note).toBeVisible({ timeout: 60_000 });
    await expect(note).toContainText("女命兼容参数");
    await expect(note).toContainText("男命兼容参数");
    await expect(note).toContainText("对应顺行");
    await expect(note).toContainText("对应逆行");
    await expect(note).toContainText("股票不存在真实性别");
  });

  test("首屏只请求逐日窗口，月与周在用户选择后才计算", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 760 });
    const requested: string[] = [];
    let daysRequestStartedAt = 0;
    page.on("request", (request) => {
      const url = request.url();
      if (url.includes("/timeline/months")) requested.push("months");
      if (url.includes("/timeline/weeks")) requested.push("weeks");
      if (url.includes("/timeline/days")) {
        requested.push("days");
        daysRequestStartedAt = Date.now();
      }
      if (url.includes("/api/v2/research/fortune/timeline")) requested.push("fortune");
    });

    const daysResponse = page.waitForResponse((response) =>
      response.url().includes("/timeline/days?days=20") && response.request().method() === "GET",
    );
    await page.goto("/stock/600519/timeline", { waitUntil: "load" });
    expect((await daysResponse).status()).toBe(200);
    expect(daysRequestStartedAt).toBeGreaterThan(0);
    console.log(`real GET /timeline/days response: ${Date.now() - daysRequestStartedAt}ms`);
    await expect(page.getByTestId("timeline-step-chart")).toBeVisible({ timeout: 60_000 });
    expect(requested.filter((item) => item === "days")).toHaveLength(1);
    expect(requested.filter((item) => item === "months")).toHaveLength(0);
    expect(requested.filter((item) => item === "weeks")).toHaveLength(0);

    const monthsResponse = page.waitForResponse((response) =>
      response.url().includes("/timeline/months") && response.request().method() === "GET",
    );
    const monthsStartedAt = Date.now();
    await page.getByTestId("timeline-gran-months").click();
    expect((await monthsResponse).status()).toBe(200);
    console.log(`real /timeline/months response: ${Date.now() - monthsStartedAt}ms`);
    await expect.poll(() => requested.filter((item) => item === "months").length).toBe(1);
    await expect(page.locator('[data-testid^="month-row-"]')).toHaveCount(12);

    const weeksResponse = page.waitForResponse((response) =>
      response.url().includes("/timeline/weeks") && response.request().method() === "GET",
    );
    const weeksStartedAt = Date.now();
    await page.getByTestId("timeline-load-weeks").click();
    const response = await weeksResponse;
    expect(response.status()).toBe(200);
    console.log(`real /timeline/weeks response: ${Date.now() - weeksStartedAt}ms`);
    await expect(page.getByTestId("week-ranking-table").locator("tbody tr")).toHaveCount(12);
    expect(requested.filter((item) => item === "weeks")).toHaveLength(1);
    await expect.poll(() => requested.filter((item) => item === "fortune").length).toBe(1);
  });
});
