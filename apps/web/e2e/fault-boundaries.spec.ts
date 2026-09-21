import { expect, test } from "@playwright/test";

/**
 * 故障与边界验收（真实模式，需要隔离后端）。
 *
 * 与 `real-mode-live.spec.ts` 的分工：
 *  * 那边验证**真实来源**（真实 provider / 真实行情 / 真实日历）；
 *  * 这里验证**故障注入**下的降级行为，两者分开记录，不互相冒充。
 *
 * 覆盖任务书 §七 点名的三类此前的空白：
 *  1. **无行情**：`stock_master` 有记录不等于有行情 —— 供应商仓库里没有该标的时必须
 *     给出"可理解的不可用"，而不是编造结果或 500；
 *  2. **样本不足**：历史验证必须如实呈现样本量与 ResearchStatus，不得因为样本少就
 *     悄悄给个数字；
 *  3. **超时与重试**：首请求挂起 → 分区报错 → 重试成功。
 */

const LIVE = process.env.SMP_E2E_LIVE_API === "1";
const REAL_BASE = process.env.SMP_E2E_REAL_BASE ?? "http://127.0.0.1:3111";

test.describe("故障与边界（真实模式）", () => {
  test.skip(!LIVE, "需要 SMP_E2E_LIVE_API=1 与隔离后端");

  test("无行情标的：给出可理解的不可用，不编造结果", async ({ request }) => {
    // 供应商 Parquet 仓库里不存在的代码 —— 这是"有代码、无行情"的真实形态
    const res = await request.post(
      "http://127.0.0.1:8101/api/v1/stocks/999999/analysis/multi",
      { headers: { "Content-Type": "application/json" }, data: { variant_mode: "forward", persist: false } },
    );
    expect(res.status(), "无行情标的应当是确定的客户端错误，而不是 500").toBe(404);
    const body = await res.json();
    expect(body.error.code).toBe("STOCK_NOT_FOUND");
    expect(String(body.error.message)).toContain("不在供应商");
    expect(body.error.retryable).toBe(false);
    // 不得返回任何分数
    expect(body.opinions).toBeUndefined();
  });

  test("无行情标的在页面上显示错误态并可返回，而不是白屏", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/999999/overview`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const main = page.locator("main");
    // 必须出现可读的错误信息（来自后端结构化错误），不是空白也不是演示数据
    await expect(main).toContainText(/不在供应商|无法|失败|错误|不存在/, { timeout: 60_000 });
    await expect(main).not.toContainText("演示数据（固定样本）");
    // 页面必须仍是完整外壳（有导航与标题），不是崩溃页
    await expect(page.getByTestId("page-title").first()).toBeVisible();
  });

  test("样本不足：历史验证如实给出 ResearchStatus 与样本量，不编造统计", async ({
    page,
  }) => {
    await page.goto(`${REAL_BASE}/stock/688981/backtest`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const main = page.locator("main");
    await expect(main).toBeVisible();

    // 研究状态必须可见（真实取值来自库内实验：INCONCLUSIVE / WEAK_EVIDENCE /
    // INVALID_CONTROL / NO_SIGNAL / NOT_RUN 之一，绝不允许出现"已验证有效"式表述）
    await expect(main).toContainText(/研究状态|ResearchStatus/);
    await expect(main).toContainText(
      /未运行|无真实数据|样本不足|负对照失效|未发现稳定信号|结论不明确|弱证据|样本内支持/,
    );
    // 不得出现策略可用性宣称
    await expect(main).not.toContainText(/已验证有效|胜率显著|可放心使用|建议买入|建议卖出/);
  });

  test("超时：逐日接口挂起 → 分区报错可重试 → 重试成功", async ({ page }) => {
    let attempt = 0;
    await page.route("**/timeline/days*", async (route) => {
      attempt += 1;
      if (attempt === 1) {
        // 模拟超时：让请求一直挂起，直到页面侧的等待超时
        await new Promise((resolve) => setTimeout(resolve, 120_000));
        return;
      }
      await route.continue();
    });

    await page.goto(`${REAL_BASE}/stock/600519/timeline`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });

    // 该分区必须报错，且不影响其它分区
    const err = page.getByTestId("timeline-days-error");
    await expect(err).toBeVisible({ timeout: 120_000 });
    await expect(page.getByTestId("timeline-summary")).toBeVisible();

    // 重试后成功
    await page.unroute("**/timeline/days*");
    await err.getByRole("button", { name: "重试本区" }).click();
    await expect(page.getByTestId("timeline-days-error")).toHaveCount(0, { timeout: 120_000 });
    await expect(page.getByTestId("timeline-step-chart")).toBeVisible({ timeout: 120_000 });
  });

  test("零收益与缺失收益在真实页面上可区分", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/600519/huangli`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const main = await page.locator("main").innerText();
    // 缺失必须写成 — 或"不可用"，不得写成 0
    expect(main, "缺失收益被写成了 0").not.toMatch(/平均收益[:：]\s*0\.0%/);
    expect(main).toMatch(/不可用|—|暂无|没有/);
  });
});
