import { expect, test } from "@playwright/test";

/**
 * 真实模式浏览器验收（需要隔离后端 + 真实行情）。
 *
 * 默认跳过：这类用例依赖外部进程（隔离后端），不该让默认套件依赖它；
 * 但它**不是"可以不跑"**——本轮以
 *   `SMP_E2E_LIVE_API=1` + `SMP_E2E_REAL_BASE=http://127.0.0.1:3111`
 * 真跑，并在交付报告中记录实际结果与后端请求清单。
 *
 * 覆盖：三只真实标的（SSE 主板 / SZSE 主板 / SSE 科创板）× 六个页面 ×
 * 当前基准与历史基准 × 本轮新增交互（导出、本机自选）。
 *
 * **不写共享研究库**：隔离后端使用 `output/ui-final/iso/data` 下的数据库副本。
 */

const LIVE = process.env.SMP_E2E_LIVE_API === "1";
const REAL_BASE = process.env.SMP_E2E_REAL_BASE ?? "http://127.0.0.1:3111";

/** 三只真实标的：不同交易所 + 不同完整度（选择依据见 real-acceptance.json）。 */
const STOCKS = [
  { code: "600519", exchange: "SSE", why: "SSE 主板，上市 2001-08-27" },
  { code: "000001", exchange: "SZSE", why: "SZSE 主板，1991 起" },
  { code: "688981", exchange: "SSE", why: "SSE 科创板，2020-07-16 起（短历史）" },
];

const PAGES = ["overview", "bazi", "ziwei", "huangli", "timeline", "backtest"] as const;

test.describe("真实模式：真实 provider + 真实行情", () => {
  test.skip(!LIVE, "需要 SMP_E2E_LIVE_API=1 与隔离后端（真实行情）");

  test.describe.configure({ mode: "serial" });

  for (const s of STOCKS) {
    test(`${s.code} 六个页面在真实数据下无错误渲染`, async ({ page }) => {
      const errors: string[] = [];
      const apiCalls: { url: string; status: number }[] = [];
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(m.text().slice(0, 200));
      });
      page.on("pageerror", (e) => errors.push(`pageerror: ${String(e).slice(0, 200)}`));
      page.on("response", (r) => {
        if (/\/api\/(backend\/)?(api\/)?v1\//.test(r.url())) {
          apiCalls.push({ url: r.url().replace(REAL_BASE, ""), status: r.status() });
        }
      });

      for (const p of PAGES) {
        await page.goto(`${REAL_BASE}/stock/${s.code}/${p}`, { waitUntil: "load" });
        await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
        // 真实模式必须有真实后端请求（否则说明掉进了演示数据）
        await expect(
          page.getByTestId("stock-context-bar").first(),
          `${s.code}/${p} 未渲染上下文栏`,
        ).toBeVisible({ timeout: 60_000 });
        // 上下文栏里的标的代码必须是当前标的（不是上一只股票的残留）
        const bar = await page.getByTestId("stock-context-bar").first().innerText();
        expect(bar, `${s.code}/${p} 上下文栏显示的标的与路由不一致`).toContain(s.code);
        // 页面主体必须出现，且没有"演示数据"角标
        await expect(page.locator("main")).not.toContainText("演示数据（固定样本）");
      }

      const failed = apiCalls.filter((c) => c.status >= 400);
      expect(failed, `${s.code} 出现失败请求：${JSON.stringify(failed)}`).toHaveLength(0);
      expect(errors, `${s.code} 出现 console/page 错误：${errors.join(" | ")}`).toHaveLength(0);
      // 真实模式必须真的打了后端
      expect(apiCalls.length, `${s.code} 没有任何后端请求，可能掉进了演示数据`).toBeGreaterThan(0);
    });
  }

  test("当前基准与历史基准给出不同的 as_of，且不做替换", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/600519/overview`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const barCurrent = await page.getByTestId("stock-context-bar").first().innerText();
    const asOfCurrent = /分析基准：\s*([0-9-]+[ T][0-9:]+)/.exec(barCurrent)?.[1] ?? "";
    expect(asOfCurrent, "上下文栏未给出分析基准").not.toBe("");

    await page.goto(`${REAL_BASE}/stock/600519/huangli?asOf=2026-09-18T14:32:00`, {
      waitUntil: "load",
    });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const barHist = await page.getByTestId("stock-context-bar").first().innerText();
    expect(barHist, "显式 asOf 未被采用").toContain("2026-09-18");
  });

  test("真实模式下导出报告：后端渲染 Markdown + 可打印 HTML 实际下载", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/600519/overview`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });

    const btn = page.getByTestId("export-report-btn").first();
    await expect(btn).toBeEnabled({ timeout: 60_000 });
    await btn.click();
    const [md] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("export-markdown").click(),
    ]);
    expect(md.suggestedFilename()).toMatch(/report-.*\.md$/);
    const { readFile } = await import("node:fs/promises");
    const text = await readFile((await md.path())!, "utf-8");
    // 后端报告必须包含研究状态、版本与限制（不是前端拼的简版）
    expect(text).toContain("研究状态");
    expect(text).toMatch(/ResearchStatus|NOT_RUN|NO_SIGNAL|INCONCLUSIVE|WEAK_EVIDENCE/);
    expect(text).toContain("600519");

    await btn.click();
    const [html] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("export-html").click(),
    ]);
    const htmlText = await readFile((await html.path())!, "utf-8");
    expect(htmlText).toContain("<!doctype html>");
    expect(htmlText).not.toContain("演示数据");
  });

  test("真实模式下本机自选：加入后刷新仍在", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/600519/ziwei`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    await page.getByTestId("watch-toggle").first().click();
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 1");
    await page.reload({ waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 1");
    await page.getByTestId("watchlist-toggle").first().click();
    await page.getByTestId("watch-remove-600519").first().click();
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 0");
  });

  test("切换股票后各区块身份一致（不显示上一只股票的旧结果）", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/600519/overview`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    await expect(page.getByTestId("stock-context-bar").first()).toContainText("600519");

    await page.goto(`${REAL_BASE}/stock/000001/ziwei`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const bar = page.getByTestId("stock-context-bar").first();
    await expect(bar).toContainText("000001");
    // 页面正文里不得残留上一只股票的代码
    const main = await page.locator("main").innerText();
    expect(main, "页面正文明细里仍出现上一只股票的代码 600519").not.toContain("600519");
  });

  test("故障注入：紫微接口 500 时该分区降级，其它分区仍可用", async ({ page }) => {
    await page.route("**/analysis/multi", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "INJECTED", message: "注入故障", retryable: true } }),
      });
    });
    await page.goto(`${REAL_BASE}/stock/600519/ziwei`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 30_000 });
    // 失败必须可见并给出重试，而不是白屏或伪造结果
    await expect(page.locator("main")).toContainText("注入故障");
    const retry = page.getByRole("button", { name: /重试|重新计算|刷新/ }).first();
    await expect(retry).toBeVisible();
    // 不伪造紫微数据
    await expect(page.locator("main")).not.toContainText("十四主星");
  });
});
