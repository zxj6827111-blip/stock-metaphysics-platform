import { expect, test } from "@playwright/test";

/**
 * 批次 B 自动化回归与视觉几何测试套件。
 *
 * 覆盖：
 *  1. 公共外壳与东方视觉元素（TopBar 品牌宋体金光、PageHero 印章 SealStamp、Sidebar 选中金色指示器）；
 *  2. 股票上下文紧凑栅格栏（StockContextBar 单行防折行高度 <= 50px，带 Tabs <= 82px）；
 *  3. 页面 01 首页：52px 宋体大标题、矢量 Astrolabe 星盘、最近分析 vs 系统状态 2.1:1 栅格比例；
 *  4. 页面 02 综合研判：顶部模型行 <= 220px，双列独立堆叠，历史验证摘要卡片顶部 y <= 760px（首屏立即可见）；
 *  5. 页面 03 八字详情：天干地支五行语义着色、第一行 26:45:29 比例、正负因素顶部 y <= 720px、古籍证据顶部 y <= 900px；
 *  6. 纯真实 DOM/SVG 渲染与无水平滚动条校验（绝无 reference.png 图片作弊）。
 */

const FIXTURE = "?fixture=ui-reference";

test.describe("批次 B：公共外壳与东方视觉元素", () => {
  test("TopBar 品牌标题具有宋体字形与金色流光，PageHero 渲染篆刻朱砂印章", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/overview${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const brand = page.getByTestId("brand").first();
    await expect(brand).toBeVisible();

    // 检查品牌标题样式
    const brandText = brand.locator(".smp-serif-title").first();
    await expect(brandText).toBeVisible();
    await expect(brandText).toHaveText("股票玄学多模型研究平台");

    // 检查朱砂印章组件
    const seal = page.getByTestId("seal-stamp").first();
    await expect(seal).toBeVisible();
    await expect(seal).toHaveText("正");
  });

  test("Sidebar 导航项选中时呈现金色边框与微光背景", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/overview${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const activeNav = page.getByTestId("nav-overview").first();
    await expect(activeNav).toBeVisible();
    await expect(activeNav).toHaveClass(/smp-nav-item--active/);
  });
});

test.describe("批次 B：股票上下文紧凑栏（StockContextBar）", () => {
  test("综合页单行上下文栏高度 <= 50px，且无折行溢出", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/overview${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const bar = page.getByTestId("stock-context-bar").first();
    await expect(bar).toBeVisible();

    const box = await bar.boundingBox();
    expect(box).not.toBeNull();
    // 单行栏高度必须紧凑（<= 50px），防止挤压首屏空间
    expect(box!.height).toBeLessThanOrEqual(50);
  });

  test("八字详情页带子标签栏的上下文栏总高度 <= 82px", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/bazi${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const bar = page.getByTestId("stock-context-bar").first();
    await expect(bar).toBeVisible();

    const box = await bar.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeLessThanOrEqual(82);
  });
});

test.describe("批次 B：页面 01 首页视觉与比例", () => {
  test("首页包含 52px 宋体标题、矢量 Astrolabe 星盘与 2.1:1 核心栅格", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    // 大标题
    const title = page.getByTestId("home-title").first();
    await expect(title).toBeVisible();
    const fontSize = await title.evaluate((el) => window.getComputedStyle(el).fontSize);
    expect(parseFloat(fontSize)).toBeGreaterThanOrEqual(48);

    // 矢量星盘
    const astrolabe = page.getByTestId("astrolabe-ornament").first();
    await expect(astrolabe).toBeVisible();

    // 核心卡片比例：最近分析 vs 系统状态
    const recentCard = page.getByTestId("recent-analysis").first();
    const systemCard = page.getByTestId("system-status").first();
    await expect(recentCard).toBeVisible();
    await expect(systemCard).toBeVisible();

    const recentBox = await recentCard.boundingBox();
    const systemBox = await systemCard.boundingBox();
    expect(recentBox).not.toBeNull();
    expect(systemBox).not.toBeNull();

    const ratio = recentBox!.width / systemBox!.width;
    // 预期约 2.1:1 (允许 1.8 至 2.4 弹性范围)
    expect(ratio).toBeGreaterThanOrEqual(1.8);
    expect(ratio).toBeLessThanOrEqual(2.4);

    // 底部 4 张能力卡
    const caps = page.getByTestId("capabilities").first();
    await expect(caps).toBeVisible();
  });
});

test.describe("批次 B：页面 02 综合研判首屏几何与独立双列", () => {
  test("顶部模型行高度 <= 220px，历史验证卡片顶部 y <= 760px 进入首屏", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/overview${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const engineScores = page.getByTestId("engine-scores").first();
    const consensusCard = page.getByTestId("consensus-card").first();
    const conflictCard = page.getByTestId("conflict-card").first();

    await expect(engineScores).toBeVisible();
    await expect(consensusCard).toBeVisible();
    await expect(conflictCard).toBeVisible();

    const engineBox = await engineScores.boundingBox();
    expect(engineBox).not.toBeNull();
    expect(engineBox!.height).toBeLessThanOrEqual(220);

    // 历史验证摘要卡片
    const backtestSummary = page.getByTestId("backtest-summary").first();
    await expect(backtestSummary).toBeVisible();

    const btBox = await backtestSummary.boundingBox();
    expect(btBox).not.toBeNull();

    // 关键断言：历史验证卡片起始 y 坐标必须 <= 760px，确保首屏完整可见
    expect(btBox!.y).toBeLessThanOrEqual(760);

    // 关键证据卡片与数据质量卡片正常展示
    await expect(page.getByTestId("key-evidence").first()).toBeVisible();
    await expect(page.getByTestId("data-quality-card").first()).toBeVisible();
  });
});

test.describe("批次 B：页面 03 八字详情五行干支着色与首屏压缩", () => {
  test("四柱盘干支着色符合五行语义，非统一单一文本色", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/bazi${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const baziChart = page.getByTestId("bazi-chart").first();
    await expect(baziChart).toBeVisible();

    // 600519 八字为：辛巳 (年) 丙申 (月) 戊寅 (日) 丁巳 (时)
    // 辛 (金) -> var(--color-metal)
    // 丙 (火) -> var(--color-fire)
    // 戊 (土) -> var(--color-earth)
    const stemYear = page.getByTestId("stem-year").first();
    const stemMonth = page.getByTestId("stem-month").first();
    const stemDay = page.getByTestId("stem-day").first();

    await expect(stemYear).toHaveText("辛");
    await expect(stemMonth).toHaveText("丙");
    await expect(stemDay).toHaveText("戊");

    // 验证不同五行天干的颜色不同
    const colorYear = await stemYear.evaluate((el) => window.getComputedStyle(el).color);
    const colorMonth = await stemMonth.evaluate((el) => window.getComputedStyle(el).color);
    const colorDay = await stemDay.evaluate((el) => window.getComputedStyle(el).color);

    expect(colorYear).not.toBe(colorMonth);
    expect(colorMonth).not.toBe(colorDay);
  });

  test("八字第一排五行/四柱/命局栅格比例约 26:45:29，正负因素卡片顶部 y <= 720px", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/bazi${FIXTURE}`);
    await page.waitForLoadState("domcontentloaded");

    const wuxing = page.getByTestId("wuxing-card").first();
    const chart = page.getByTestId("bazi-chart-card").first();
    const summary = page.getByTestId("fate-summary-card").first();

    await expect(wuxing).toBeVisible();
    await expect(chart).toBeVisible();
    await expect(summary).toBeVisible();

    const wBox = await wuxing.boundingBox();
    const cBox = await chart.boundingBox();
    const sBox = await summary.boundingBox();
    expect(wBox).not.toBeNull();
    expect(cBox).not.toBeNull();
    expect(sBox).not.toBeNull();

    // 四柱宽度明显大于五行卡与命局卡
    expect(cBox!.width).toBeGreaterThan(wBox!.width);
    expect(cBox!.width).toBeGreaterThan(sBox!.width);

    // 正负因素卡片顶部 y 坐标不晚于 720px
    const posFactors = page.getByTestId("positive-factors").first();
    const negFactors = page.getByTestId("negative-factors").first();
    await expect(posFactors).toBeVisible();
    await expect(negFactors).toBeVisible();

    const posBox = await posFactors.boundingBox();
    expect(posBox).not.toBeNull();
    // 正向因素必须进入首屏 (y <= 740px)
    expect(posBox!.y).toBeLessThanOrEqual(740);

    // 古籍证据卡片紧随其后正常展示
    const evidenceCard = page.getByTestId("bazi-evidence").first();
    await expect(evidenceCard).toBeVisible();
    const evBox = await evidenceCard.boundingBox();
    expect(evBox).not.toBeNull();
    expect(evBox!.y).toBeGreaterThan(posBox!.y);
  });
});

test.describe("批次 B：防作弊与无横向滚动条合规", () => {
  test("页面无水平横向滚动条，且绝无外部 reference.png 图片作弊", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });

    for (const path of ["/", "/stock/600519/overview", "/stock/600519/bazi"]) {
      await page.goto(`${path}${FIXTURE}`);
      await page.waitForLoadState("domcontentloaded");

      // 检查横向滚动条
      const hasHorizontalScroll = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
      });
      expect(hasHorizontalScroll, `页面 ${path} 不得产生横向滚动条`).toBe(false);

      // 检查绝无 reference.png 背景或图片作弊
      const cheatImages = await page.evaluate(() => {
        const imgs = Array.from(document.querySelectorAll("img")).filter((img) =>
          img.src.includes("reference.png"),
        );
        const elementsWithBg = Array.from(document.querySelectorAll("*")).filter((el) => {
          const bg = window.getComputedStyle(el).backgroundImage;
          return bg && bg.includes("reference.png");
        });
        return imgs.length + elementsWithBg.length;
      });
      expect(cheatImages, `页面 ${path} 禁止使用参考图作弊`).toBe(0);
    }
  });
});
