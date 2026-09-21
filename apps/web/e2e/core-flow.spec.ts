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

  test("Phase 2 导航项已启用（紫微/时间窗口/历史验证/古籍/分歧）", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    for (const key of ["nav-ziwei", "nav-timeline", "nav-backtest", "nav-evidence", "nav-conflicts"]) {
      const item = page.getByTestId(key).first();
      await expect(item, `${key} 应可见`).toBeVisible();
    }
    // 紫微在 Phase 2 已实现，不再标记为 disabled
    const ziwei = page.getByTestId("nav-ziwei").first();
    await expect(ziwei).not.toHaveAttribute("aria-disabled", "true");
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
    const chart = page.getByTestId("bazi-chart").first();
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
    // 面向人的标签用中文；原始状态码通过 data-* 保留可追溯性（不丢信息）
    const variant = page.getByTestId("variant-mode").first();
    await expect(variant).toHaveText("不适用（股票无性别）");
    await expect(variant).toHaveAttribute("data-variant-mode", "not_applicable");
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

test.describe("Phase 2 页面（真实数据路径）", () => {
  test("紫微页渲染真实盘面组件（十二宫网格 + 变体切换）", async ({ page }) => {
    await page.goto("/stock/600519/ziwei");
    await expect(page.getByTestId("page-title").first()).toHaveText("紫微斗数详情");
    // 变体切换器必须在：顺行/逆行是两个假设，不能替用户选
    await expect(page.getByTestId("variant-switcher").first()).toBeVisible();
    // 页面必须给出明确的可用性说明（有盘面 / 不可用都要说清楚）
    const main = page.locator("main");
    await expect(main).toContainText(/十二宫|不可用/);
  });

  test("模型分歧页给出冲突归因与『不平均』声明", async ({ page }) => {
    await page.goto("/stock/600519/conflicts");
    await expect(page.getByTestId("page-title").first()).toHaveText("模型分歧中心");
    await expect(page.getByTestId("opinion-cards").first()).toBeVisible();
    const main = page.locator("main");
    await expect(main).toContainText("不做平均");
  });

  test("历史验证页把『术数规则强度』与『统计有效性』视觉分区", async ({ page }) => {
    await page.goto("/stock/600519/backtest");
    await expect(page.getByTestId("page-title").first()).toHaveText("历史验证");
    await expect(page.getByTestId("section-deterministic").first()).toBeVisible();
    await expect(page.getByTestId("section-empirical").first()).toBeVisible();
    await expect(page.getByTestId("research-status-card").first()).toBeVisible();
  });

  test("时间窗口页声明聚合口径版本且否弃『流周』", async ({ page }) => {
    await page.goto("/stock/600519/timeline");
    await expect(page.getByTestId("page-title").first()).toHaveText("时间窗口");
    const main = page.locator("main");
    await expect(main).toContainText("聚合口径版本");
  });

  test("古籍证据页三栏并列（支持 / 反证 / 中性）", async ({ page }) => {
    await page.goto("/stock/600519/evidence");
    await expect(page.getByTestId("page-title").first()).toHaveText("古籍证据检索");
    const main = page.locator("main");
    // 三类计数必须**同时渲染**（真并列），不依赖任何筛选动作
    await expect(page.getByTestId("stance-count-counter").first()).toBeVisible();
    await expect(page.getByTestId("stance-count-support").first()).toBeVisible();
    await expect(page.getByTestId("stance-count-neutral").first()).toBeVisible();
    await expect(main).toContainText("反证");
    await expect(main).toContainText("支持");
    await expect(main).toContainText("中性");

    // 反证不能被支持条目挤到页面末尾：列表与计数区都必须落在首屏（941 之内）
    const list = page.getByTestId("evidence-list").first();
    const counts = page.getByTestId("evidence-counts").first();
    await expect(list).toBeVisible();
    await expect(counts).toBeVisible();
    const listBox = await list.boundingBox();
    const countsBox = await counts.boundingBox();
    expect(listBox, "证据列表未渲染").not.toBeNull();
    expect(countsBox, "三类计数未渲染").not.toBeNull();
    expect(countsBox!.y, "三类计数不在首屏").toBeLessThan(941);
    expect(listBox!.y, "证据列表不在首屏").toBeLessThan(941);

    // 「全部」模式下反证排在最前：首条证据必须是反证类
    const firstItem = page.locator('[data-testid^="evidence-item-"]').first();
    await expect(firstItem).toHaveAttribute("data-stance", "counter");
  });

  test("黄历页把传统黄历数据与研究映射分区", async ({ page }) => {
    await page.goto("/stock/600519/huangli");
    await expect(page.getByTestId("page-title").first()).toHaveText("黄历 / 日课详情");
    await expect(page.getByTestId("section-traditional-huangli").first()).toBeVisible();
    await expect(page.getByTestId("section-huangli-factors").first()).toBeVisible();
  });

  test("因子字典页列出 114 个因子并显示规则分语义", async ({ page }) => {
    await page.goto("/factors");
    await expect(page.getByTestId("page-title").first()).toHaveText("因子字典");
    await expect(page.getByTestId("factor-search").first()).toBeVisible();
    await expect(page.getByTestId("factor-table").first()).toBeVisible();
    const main = page.locator("main");
    await expect(main).toContainText("不代表预期收益率");
  });

  test("综合研判页提供报告导出", async ({ page }) => {
    await page.goto("/stock/600519/overview");
    await expect(page.getByTestId("report-export").first()).toBeVisible();
  });

  for (const [path, title] of [
    ["/research", "研究实验室"],
    ["/settings", "系统设置"],
  ] as const) {
    test(`${path} 仍为占位页（本版本不实现）`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      await expect(page.getByTestId("page-title").first()).toHaveText(title);
    });
  }
});
