import { expect, test } from "@playwright/test";

const fixture = "?fixture=ui-reference";

test.describe("V5.1 真实模式与研究入口", () => {
  test("真实首页不预填股票且无记录时为空态", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
    await expect(page.getByRole("main").getByTestId("stock-search-input")).toHaveValue("");
    await expect(page.getByTestId("recent-empty")).toBeVisible();
    await page.screenshot({ path: "test-results/v51-home-live-empty.png" });
  });

  test("fixture 首页仍使用冻结 600519", async ({ page }) => {
    await page.goto(`/${fixture}`);
    await expect(page.getByRole("main").getByTestId("stock-search-input")).toHaveValue("600519");
    await expect(page.getByTestId("fixture-banner")).toBeVisible();
    await page.screenshot({ path: "test-results/v51-home-fixture.png" });
  });

  test("无标的股票入口展示选择页而不是跳默认股", async ({ page }) => {
    await page.goto("/stock?target=bazi");
    await expect(page.getByTestId("stock-selection-gate")).toBeVisible();
    await expect(page.getByText("请选择研究标的")).toBeVisible();
    await expect(page.getByText("暂无近期搜索股票")).toBeVisible();
    await page.screenshot({ path: "test-results/v51-stock-selection.png" });
  });

  test("关系扫描默认先显示关系选择态", async ({ page }) => {
    await page.goto("/research/date-scan");
    await expect(page.getByTestId("date-scan-controls")).toBeVisible();
    const resultState = page.getByRole("heading", { name: "请选择一种关系查看命中股票" });
    const errorState = page.getByText("择日关系扫描失败");
    await expect(resultState).toBeVisible({ timeout: 90_000 });
    await expect(errorState).toHaveCount(0);
    await page.screenshot({ path: "test-results/v51-date-scan-relation-first.png" });
  });

  test("fixture 下关系研究不伪造统计", async ({ page }) => {
    await page.goto(`/research/relation-study${fixture}`);
    await expect(page.getByText("UI fixture 只冻结十张视觉样本")).toBeVisible();
    await expect(page.getByTestId("relation-study-run")).toBeDisabled();
    await page.screenshot({ path: "test-results/v51-relation-study-fixture.png" });
  });
});
