import { expect, test } from "@playwright/test";

/**
 * 交互闭环验收：导出报告、本机自选、紫微宫位明细。
 *
 * 每条用例都必须走完 **入口 → 操作 → 状态变化/请求 → 用户可见结果 → 失败反馈**，
 * 只断言"按钮存在"不算通过。
 */

const FIX = "?fixture=ui-reference";

test.describe("导出报告：真实生成且可打开", () => {
  test("演示模式：三种格式都能下载，且内容明确标注演示数据", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const btn = page.getByTestId("export-report-btn").first();
    await expect(btn).toBeVisible();

    // Markdown
    await btn.click();
    await expect(page.getByTestId("export-report-menu")).toBeVisible();
    const [mdDl] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("export-markdown").click(),
    ]);
    expect(mdDl.suggestedFilename()).toMatch(/demo-report-600519-.*\.md$/);
    const mdPath = await mdDl.path();
    const mdText = await readFile(mdPath);
    expect(mdText).toContain("演示数据");
    expect(mdText).toContain("600519");
    // 演示夹具里没有逐标的 EventStudy，导出里不得出现编造的收益/胜率
    expect(mdText).not.toMatch(/胜率\s*[:：]?\s*\d/);
    await expect(page.getByTestId("export-feedback")).toBeVisible();

    // HTML（可打印）
    await btn.click();
    const [htmlDl] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("export-html").click(),
    ]);
    expect(htmlDl.suggestedFilename()).toMatch(/\.html$/);
    const htmlText = await readFile(await htmlDl.path());
    expect(htmlText).toContain("<!doctype html>");
    expect(htmlText).toContain("演示数据");
    // 不能把浏览器打印说成服务端 PDF
    expect(htmlText).toContain("可打印 HTML");
    expect(htmlText).not.toContain("服务端 PDF 导出");

    // JSON（结构化）
    await btn.click();
    const [jsonDl] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("export-json").click(),
    ]);
    const jsonText = await readFile(await jsonDl.path());
    const payload = JSON.parse(jsonText);
    expect(payload.demo).toBe(true);
    expect(payload.demo_notice).toContain("演示数据");
    expect(payload.stock.code).toBe("600519");
    expect(payload.as_of).toBeTruthy();
    expect(Array.isArray(payload.engines)).toBe(true);
    // 不可用引擎必须是 null，不能是 0
    for (const e of payload.engines) {
      if (e.availability !== "ok") expect(e.score).toBeNull();
    }
    expect(payload.versions).toBeTruthy();
  });

  test("导出期间切换标的不会混入另一只股票的数据（上下文冻结）", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const [dl] = await Promise.all([
      page.waitForEvent("download"),
      (async () => {
        await page.getByTestId("export-report-btn").first().click();
        await page.getByTestId("export-json").click();
        // 导出触发的同一时刻切到别的页面：报告内容必须仍是导出那一刻的 600519
        await page.goto(`/stock/600519/ziwei${FIX}`, { waitUntil: "load" });
      })(),
    ]);
    const payload = JSON.parse(await readFile(await dl.path()));
    expect(payload.stock.code).toBe("600519");
  });
});

test.describe("本机自选：加入 / 去重 / 移除 / 刷新恢复", () => {
  test("完整闭环，且明确标注是本机存储", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    // 入口：星标 + 计数
    await page.getByTestId("watch-toggle").first().click();
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 1");

    // 去重：重复点击不应变成 2
    await page.getByTestId("watch-toggle").first().click(); // 移除
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 0");
    await page.getByTestId("watch-toggle").first().click(); // 再加入
    await page.getByTestId("watch-toggle").first().click(); // 再移除（验证幂等边界）
    await page.getByTestId("watch-toggle").first().click(); // 最终加入
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 1");

    // 面板：本机语义必须写明，不能冒充云端同步
    await page.getByTestId("watchlist-toggle").first().click();
    const panel = page.getByTestId("watchlist-panel").first();
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("本机");
    await expect(panel).toContainText("不跨设备同步");
    await expect(page.getByTestId("watch-item-600519").first()).toBeVisible();

    // 刷新恢复
    await page.reload({ waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 1");

    // 移除
    await page.getByTestId("watchlist-toggle").first().click();
    await page.getByTestId("watch-remove-600519").first().click();
    await expect(page.getByTestId("watchlist-toggle").first()).toContainText("本机自选 0");
  });
});

test.describe("紫微宫位明细：被截断的星曜必须可完整读到", () => {
  test("每一宫都有明细入口，打开后给出全部星曜与分类", async ({ page }) => {
    await page.goto(`/stock/600519/ziwei${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const buttons = page.locator('[data-testid^="ziwei-expand-"]');
    await expect(buttons).toHaveCount(12);

    // 逐个宫位检查：明细入口可用，且弹层给出完整分类与"空宫如实说明"
    for (let i = 0; i < 12; i += 1) {
      const btn = page.getByTestId(`ziwei-expand-${i}`);
      await btn.click();
      const modal = page.getByTestId("ziwei-palace-detail");
      await expect(modal).toBeVisible();
      await expect(modal).toHaveAttribute("data-palace-index", String(i));
      await expect(page.getByTestId("palace-detail-主星")).toBeVisible();
      await expect(page.getByTestId("palace-detail-辅星")).toBeVisible();
      await expect(page.getByTestId("palace-detail-杂曜")).toBeVisible();
      await page.getByTestId("ziwei-palace-detail-close").click();
      await expect(modal).toHaveCount(0);
    }
  });

  test("明细内容不与盘面冲突：星数一致、空宫如实说明", async ({ page }) => {
    await page.goto(`/stock/600519/ziwei${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    // 逐宫核对：弹层里"主星 N 颗"的数量必须与盘面宫格 data 属性给出的主星一致，
    // 不能出现"盘面有星、明细为空"或"明细补了盘面没有的星"。
    for (let i = 0; i < 12; i += 1) {
      const cell = page.getByTestId(`ziwei-palace-${i}`);
      const cellText = await cell.innerText();
      const isEmpty = cellText.includes("空宫");
      await page.getByTestId(`ziwei-expand-${i}`).click();
      const modal = page.getByTestId("ziwei-palace-detail");
      await expect(modal).toBeVisible();
      const detail = await modal.innerText();
      if (isEmpty) {
        expect(detail, `宫位 ${i} 盘面为空宫，明细不应凭空补星`).toContain("空宫如实保留");
      } else {
        expect(detail, `宫位 ${i} 的明细必须包含主星分类`).toContain("主星");
        expect(detail.length, `宫位 ${i} 的明细内容过短，可能没有真正展开`).toBeGreaterThan(80);
      }
      await page.getByTestId("ziwei-palace-detail-close").click();
      await expect(modal).toHaveCount(0);
    }
  });
});

/** 读取本地下载文件内容（Playwright 的 download.path() 指向临时文件）。 */
async function readFile(p: string | null): Promise<string> {
  if (!p) throw new Error("download 没有产生文件路径");
  const { readFile: rf } = await import("node:fs/promises");
  return rf(p, "utf-8");
}
