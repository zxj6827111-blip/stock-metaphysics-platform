import { expect, test } from "@playwright/test";

/**
 * 十页 × 双视口的逐页验收（1672×941 与 1440×900）。
 *
 * 为什么单独一个 spec
 * -------------------
 * 旧配置把 1440 限制在 `layout.spec.ts` 上，于是"配置里有 1440 项目"被误当成
 * "1440 已逐页验收"。这个 spec 补的就是这件事：**十页在两种视口下都必须**
 *  1. 主容器内部无横向溢出（不是只看 document 滚动条 —— `main` 是独立滚动容器）；
 *  2. 关键内容可见（不是"元素存在于 DOM"）；
 *  3. 上下文栏的三个操作按钮默认可用（不靠横向滚动藏起来）；
 *  4. 首屏几何门禁：关键区块必须落在视口内。
 *
 * 测试跑在**生产构建**上（见交付报告的环境记录）。
 */

const FIX = "?fixture=ui-reference";

const PAGES: { key: string; path: string; title: string }[] = [
  { key: "01-home", path: `/${FIX}`, title: "股票玄学多模型研究平台" },
  { key: "02-overview", path: `/stock/600519/overview${FIX}`, title: "综合研判" },
  { key: "03-bazi", path: `/stock/600519/bazi${FIX}`, title: "八字详情" },
  { key: "04-ziwei", path: `/stock/600519/ziwei${FIX}`, title: "紫微斗数详情" },
  { key: "05-backtest", path: `/stock/600519/backtest${FIX}`, title: "历史验证" },
  { key: "06-factors", path: `/factors${FIX}`, title: "因子字典" },
  { key: "07-conflicts", path: `/stock/600519/conflicts${FIX}`, title: "模型分歧中心" },
  { key: "08-huangli", path: `/stock/600519/huangli${FIX}`, title: "黄历 / 日课详情" },
  { key: "09-evidence", path: `/stock/600519/evidence${FIX}`, title: "古籍证据检索" },
  { key: "10-timeline", path: `/stock/600519/timeline${FIX}`, title: "时间窗口" },
];

/** 这些页面在 fixture 模式下允许有非 /api/ 的静态请求，但**不允许**任何后端 API 请求。 */
const API_PATTERN = /\/api\/(backend\/)?(api\/)?v1\//;

test.describe("十页逐页适配（两种视口）", () => {
  for (const p of PAGES) {
    test(`${p.key} ${p.title}：无内部横向溢出且主内容可见`, async ({ page }, testInfo) => {
      const apiCalls: string[] = [];
      page.on("request", (req) => {
        if (API_PATTERN.test(req.url())) apiCalls.push(req.url());
      });

      await page.goto(p.path, { waitUntil: "load" });
      await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(350); // 图表/动画稳定

      // 1) main 是独立滚动容器：只看 document 会漏掉内部溢出
      const overflow = await page.evaluate(() => {
        const main = document.querySelector("main") as HTMLElement | null;
        const doc = document.documentElement;
        return {
          mainScroll: main?.scrollWidth ?? 0,
          mainClient: main?.clientWidth ?? 0,
          docScroll: doc.scrollWidth,
          docClient: doc.clientWidth,
        };
      });
      expect(
        overflow.mainScroll,
        `main 内部横向溢出 @${testInfo.project.name} ${p.key}`,
      ).toBeLessThanOrEqual(overflow.mainClient + 2);
      expect(
        overflow.docScroll,
        `document 横向溢出 @${testInfo.project.name} ${p.key}`,
      ).toBeLessThanOrEqual(overflow.docClient + 2);

      // 2) 页面标题可见。
      //    首页用的是自有 Hero（没有 PageHero 的 page-title），因此首页断言主标题文本，
      //    其余页面断言 PageHero 的 page-title。
      if (p.key === "01-home") {
        await expect(
          page.getByRole("heading", { level: 1, name: /股票玄学多模型研究平台/ }).first(),
        ).toBeVisible();
      } else {
        await expect(page.getByTestId("page-title").first()).toBeVisible();
      }

      // 3) 演示模式零真实后端请求（隔离）
      expect(apiCalls, `演示模式不应请求真实后端：${apiCalls.join(", ")}`).toHaveLength(0);
    });
  }

  test("上下文栏三个操作按钮默认可见（不靠横向滚动）", async ({ page }, testInfo) => {
    await page.goto(`/stock/600519/ziwei${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const bar = page.getByTestId("stock-context-bar").first();
    const barBox = await bar.boundingBox();
    expect(barBox).not.toBeNull();

    for (const id of ["switch-stock-btn", "recalculate", "export-report-btn"]) {
      const btn = page.getByTestId(id).first();
      await expect(btn, `${id} 不可见 @${testInfo.project.name}`).toBeVisible();
      const b = await btn.boundingBox();
      expect(b, `${id} 没有几何尺寸`).not.toBeNull();
      // 按钮必须完全落在上下文栏内 —— 超出即意味着被 overflow 裁掉
      expect(
        b!.x + b!.width,
        `${id} 右缘超出上下文栏 @${testInfo.project.name}`,
      ).toBeLessThanOrEqual(barBox!.x + barBox!.width + 1);
    }
  });

  test("首屏几何门禁：紫微十二宫整盘与三方四正落在一屏内", async ({ page }, testInfo) => {
    await page.goto(`/stock/600519/ziwei${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(300);

    const viewportH = page.viewportSize()!.height;
    const grid = await page.getByTestId("ziwei-chart-grid").first().boundingBox();
    expect(grid).not.toBeNull();
    expect(grid!.y + grid!.height, `十二宫底边 ${grid!.y + grid!.height} > ${viewportH}`)
      .toBeLessThanOrEqual(viewportH);
    // 十二宫必须齐：每宫都可展开明细（不被截断到不可访问）
    await expect(page.locator('[data-testid^="ziwei-expand-"]')).toHaveCount(12);
  });

  test("首屏几何门禁：古籍三类计数与历史验证持有期卡进入首屏", async ({ page }) => {
    await page.goto(`/stock/600519/evidence${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    const vh = page.viewportSize()!.height;
    const counts = await page.getByTestId("evidence-counts").first().boundingBox();
    expect(counts).not.toBeNull();
    expect(counts!.y + counts!.height).toBeLessThanOrEqual(vh);

    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    const horizon = page.getByTestId("horizon-comparison").first();
    await expect(horizon).toBeVisible();
    const hb = await horizon.boundingBox();
    expect(hb, "持有期对比卡应有几何尺寸").not.toBeNull();
    expect(hb!.y, "持有期对比卡顶部应进入首屏").toBeLessThanOrEqual(vh);
  });
});
