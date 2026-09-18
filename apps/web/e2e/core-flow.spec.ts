import { expect, test } from "@playwright/test";

/**
 * UI 核心流程 E2E（fixture 模式，不依赖后端）。
 *
 * 验证：
 *  - 三个交付页面都能打开且无控制台错误；
 *  - AppShell（TopBar + Sidebar）在三页复用同一套组件；
 *  - 股票搜索交互可用；
 *  - 四柱盘 / 五行分布 / 因子列表等关键 DOM 结构真实存在；
 *  - 证据抽屉可打开并同时显示支持与反证两个分区；
 *  - "未启用" 状态不被 0 分替代。
 */

const FIXTURE = "?fixture=ui-reference";

test.describe("全局外壳", () => {
  test("TopBar 与 Sidebar 在三个页面都渲染", async ({ page }) => {
    for (const path of ["/", "/stock/600519/overview", "/stock/600519/bazi"]) {
      await page.goto(`${path}${FIXTURE}`);
      await expect(page.getByTestId("brand").first()).toBeVisible();
      await expect(page.getByTestId("stock-search-input").first()).toBeVisible();
      await expect(page.getByTestId("nav-home").first()).toBeVisible();
      await expect(page.getByTestId("nav-overview").first()).toBeVisible();
      await expect(page.getByTestId("nav-bazi").first()).toBeVisible();
    }
  });

  test("未实现模块显示为禁用而不是隐藏", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    const ziwei = page.getByTestId("nav-ziwei").first();
    await expect(ziwei).toBeVisible();
    await expect(ziwei).toHaveAttribute("aria-disabled", "true");
  });

  test("fixture 提示可见（如实标注演示数据）", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    await expect(page.getByTestId("fixture-banner").first()).toBeVisible();
  });
});

test.describe("首页", () => {
  test("关键区块齐备", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    await expect(page.getByTestId("home-title").first()).toHaveText("股票玄学多模型研究平台");
    await expect(page.getByTestId("recent-analysis").first()).toBeVisible();
    await expect(page.getByTestId("system-status").first()).toBeVisible();
    await expect(page.getByTestId("capabilities").first()).toBeVisible();
    await expect(page.getByTestId("recent-600519").first()).toBeVisible();
  });

  test("搜索建议可交互", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    const input = page.getByTestId("stock-search-input").first();
    await input.click();
    await input.fill("300750");
    await expect(page.getByTestId("stock-search-suggestions")).toBeVisible();
    await expect(page.getByText("宁德时代").first()).toBeVisible();
  });

  test("点击建议进入综合研判页", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    const input = page.getByTestId("stock-search-input").first();
    await input.click();
    await input.fill("600519");
    await page.getByTestId("stock-search-suggestions").getByText("贵州茅台").first().click();
    await expect(page).toHaveURL(/\/stock\/600519\/overview/);
  });
});

test.describe("综合研判页", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIXTURE}`);
  });

  test("五个必答问题都有对应区块", async ({ page }) => {
    await expect(page.getByTestId("page-title").first()).toHaveText("综合研判");
    await expect(page.getByTestId("stock-context-bar").first()).toBeVisible();
    await expect(page.getByTestId("engine-card-bazi").first()).toBeVisible();
    await expect(page.getByTestId("engine-card-ziwei").first()).toBeVisible();
    await expect(page.getByTestId("engine-card-huangli").first()).toBeVisible();
    await expect(page.getByTestId("consensus-card").first()).toBeVisible();
    await expect(page.getByTestId("conflict-card").first()).toBeVisible();
    await expect(page.getByTestId("time-window").first()).toBeVisible();
    await expect(page.getByTestId("key-evidence").first()).toBeVisible();
    await expect(page.getByTestId("backtest-summary").first()).toBeVisible();
    await expect(page.getByTestId("data-quality-card").first()).toBeVisible();
  });

  test("上下文栏展示出生模型与出生时刻（可追溯）", async ({ page }) => {
    const bar = page.getByTestId("stock-context-bar").first();
    await expect(bar).toContainText("listing_open");
    await expect(bar).toContainText("2001-08-27 09:30");
    // 参考图的上下文栏展示的是带上时区偏移的时刻；完整时区名放在 title 中
    await expect(bar).toContainText("+08:00");
    const tzTitle = await bar.locator("[title*='Asia/Shanghai']").count();
    expect(tzTitle).toBeGreaterThan(0);
  });

  test("不显示综合总分，共识与历史验证分列", async ({ page }) => {
    await expect(page.getByTestId("consensus-card").first()).toContainText("一致性");
    await expect(page.getByTestId("consensus-card").first()).toContainText("历史验证");
    // 页面上不得存在一个标着“综合总分”的合成分数区块。
    // 注意：说明文案里会出现“不显示「综合总分」”这句话，因此按元素文本匹配而非整页包含判断。
    const offenders = await page
      .locator("text=/^s*综合总分s*[:：]?s*d/")
      .count();
    expect(offenders).toBe(0);
    // 共识与历史验证必须是两个独立标签
    await expect(page.getByTestId("consensus-card").first()).toContainText("共识");
  });

  test("时间窗口图例包含高共识区/高冲突区", async ({ page }) => {
    const card = page.getByTestId("time-window").first();
    await expect(card).toContainText("高共识区");
    await expect(card).toContainText("高冲突区");
  });

  test("关键证据含利多与利空两类", async ({ page }) => {
    const card = page.getByTestId("key-evidence").first();
    await expect(card).toContainText("利多");
    await expect(card).toContainText("利空");
  });

  test("历史验证指标卡齐备", async ({ page }) => {
    for (const key of ["sample", "uprate", "mean", "excess", "dd"]) {
      await expect(page.getByTestId(`metric-${key}`).first()).toBeVisible();
    }
  });
});

test.describe("八字详情页", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/stock/600519/bazi${FIXTURE}`);
  });

  test("四柱盘是真实 DOM 表格", async ({ page }) => {
    await expect(page.getByTestId("page-title").first()).toHaveText("八字详情");
    const chart = page.getByTestId("bazi-chart");
    await expect(chart).toBeVisible();
    await expect(chart.locator("table")).toBeVisible();
    for (const pos of ["year", "month", "day", "hour"]) {
      await expect(page.getByTestId(`pillar-${pos}`)).toBeVisible();
    }
    await expect(chart).toContainText("辛");
    await expect(chart).toContainText("丙");
    await expect(chart).toContainText("戊");
    await expect(chart).toContainText("丁");
    await expect(chart).toContainText("藏干");
    await expect(chart).toContainText("十神");
    await expect(chart).toContainText("纳音");
  });

  test("五行分布与命局摘要", async ({ page }) => {
    await expect(page.getByTestId("wuxing-distribution").first()).toBeVisible();
    const wuxing = await page.getByTestId("wuxing-distribution").first().innerText();
    for (const el of ["木", "火", "土", "金", "水"]) expect(wuxing).toContain(el);
    await expect(page.getByTestId("fate-summary").first()).toContainText("日主");
    await expect(page.getByTestId("fate-summary").first()).toContainText("格局");
    await expect(page.getByTestId("fate-summary").first()).toContainText("用神");
  });

  test("时间结构与股票无性别标注", async ({ page }) => {
    const ts = page.getByTestId("time-structure").first();
    await expect(ts).toContainText("大运");
    await expect(ts).toContainText("流年");
    await expect(ts).toContainText("流月");
    await expect(ts).toContainText("流日");
    await expect(page.getByTestId("variant-mode").first()).toHaveText("not_applicable");
    await expect(ts).toContainText("股票无天然性别");
  });

  test("正负因素列表与因子 ID", async ({ page }) => {
    await expect(page.getByTestId("positive-factors").first()).toContainText("B_MONTH_003");
    await expect(page.getByTestId("negative-factors").first()).toBeVisible();
  });

  test("因子免责声明存在（财星≠上涨）", async ({ page }) => {
    const d = page.getByTestId("factor-disclaimer").first();
    await expect(d).toContainText("不是预期收益率");
    await expect(d).toContainText("财星 ≠ 股票上涨");
  });

  test("页面不包含参考图整页图片（禁止作弊复刻）", async ({ page }) => {
    const imgs = await page.locator("img").count();
    expect(imgs).toBe(0);
    const bg = await page.evaluate(() => {
      const el = document.querySelector("main");
      return el ? getComputedStyle(el).backgroundImage : "";
    });
    expect(bg).not.toContain("reference");
  });
});

test.describe("古籍证据抽屉", () => {
  test("可打开并同时展示支持与反证分区", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIXTURE}`);
    await page.getByTestId("key-evidence").first().getByText("查看更多").click();
    const drawer = page.getByTestId("evidence-drawer").first();
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText("支持当前规则");
    await expect(drawer).toContainText("与当前规则相反");
    await expect(drawer).toContainText("中性背景");
  });

  test("Esc 可关闭", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIXTURE}`);
    await page.getByTestId("key-evidence").first().getByText("查看更多").click();
    await expect(page.getByTestId("evidence-drawer").first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("evidence-drawer").first()).toHaveCount(0);
  });
});

test.describe("无控制台错误", () => {
  test("三个页面均无 console error", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("pageerror", (e) => errors.push(String(e)));

    for (const path of ["/", "/stock/600519/overview", "/stock/600519/bazi"]) {
      await page.goto(`${path}${FIXTURE}`);
      await page.waitForTimeout(900);
    }
    expect(errors, `控制台错误：${errors.join(" | ")}`).toHaveLength(0);
  });
});

test.describe("Phase 2 占位页", () => {
  test("紫微页明确说明未实现且不伪造结果", async ({ page }) => {
    await page.goto("/stock/600519/ziwei");
    // 等待 Suspense 结束、主内容真正可见后再读取文本
    await expect(page.getByTestId("page-title").first()).toBeVisible();
    const main = page.locator("main");
    await expect(main).toContainText("紫微斗数");
    const text = await main.innerText();
    expect(text).toContain("Phase 2");
    expect(text).toContain("不会提供任何伪造的紫微结果");
  });

  for (const [path, title] of [
    ["/stock/600519/huangli", "黄历 / 日课"],
    ["/stock/600519/backtest", "历史验证"],
    ["/stock/600519/evidence", "古籍证据"],
    ["/stock/600519/conflicts", "模型分歧"],
    ["/stock/600519/timeline", "时间窗口"],
    ["/research", "研究实验室"],
    ["/factors", "因子字典"],
    ["/settings", "系统设置"],
  ] as const) {
    test(`${path} 返回可访问页面`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      await expect(page.getByTestId("page-title").first()).toHaveText(title);
    });
  }
});
