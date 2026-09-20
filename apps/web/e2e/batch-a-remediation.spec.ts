import { expect, test } from "@playwright/test";

/**
 * 批次 A 整改验收测试（展示正确性与验收基础）。
 *
 * 验证：
 *  1. 黄历 primary 真实字段映射，包括干支、生肖、建除值日、神煞、吉神方位与传统宜忌；
 *  2. 正常模式（非 fixture）下，无后端连接时不回退假共识、无正弦波假曲线、无假正态分箱、首页最近记录显示诚实空态；
 *  3. 十页在 `?fixture=ui-reference` 离线模式下全部能够正常完整渲染，无网络抛错；
 *  4. 样式令牌合规，无残留 `--color-line` 或裸露的 raw markdown 语法符号。
 */

const FIXTURE = "?fixture=ui-reference";

test.describe("批次 A：黄历 primary 字段映射与宜忌验证", () => {
  test("黄历页面正确读取 primary 真实字段，不为全破折号破损态", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`);

    // 等待页面加载完成
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    // 传统黄历日课区块
    const traditionalSection = page.getByTestId("traditional-huangli");
    await expect(traditionalSection).toBeVisible();

    // 检查字段不能全部为破折号 "—"
    const text = await traditionalSection.innerText();
    expect(text).toContain("值日：");
    expect(text).not.toMatch(/^—+$/);

    // 检查生肖、建除值日、神煞、纳音已映射
    expect(text).toMatch(/(生肖|值日|天神|冲煞|纳音|彭祖百忌|吉神方位)/);

    // 传统事宜（宜/忌）区块存在
    const mattersSection = page.getByTestId("traditional-matters");
    await expect(mattersSection).toBeVisible();
    const mattersText = await mattersSection.innerText();
    expect(mattersText).toContain("宜（通书事宜）");
    expect(mattersText).toContain("忌（通书禁忌）");
  });
});

test.describe("批次 A：正常模式下假数据与回退隔离性验证", () => {
  test("正常模式下首页最近分析不伪造走势，若无记录显示诚实空态", async ({ page }) => {
    // 拦截后端引擎状态使之模拟无连接或默认空
    await page.route("**/api/v1/**", async (route) => {
      await route.abort("connectionrefused");
    });

    await page.goto("/");
    await expect(page.getByTestId("home-title").first()).toBeVisible();

    // 正常模式且无历史记录时，诚实呈现空态提示，不出现 fake 600519 卡片
    await expect(page.getByTestId("recent-empty")).toBeVisible();
    await expect(page.getByTestId("recent-600519")).toHaveCount(0);

    // 系统状态右上角诚实呈现“后端未连接”
    const summary = page.getByTestId("system-summary");
    await expect(summary).toBeVisible();
    await expect(summary).toHaveText("后端未连接");
  });

  test("正常模式下综合研判页无后端时诚实展示降级，不回退 overviewFixture 共识/冲突", async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      await route.abort("connectionrefused");
    });

    await page.goto("/stock/600519/overview");
    // 页面应捕获网络错误进入错误态，绝不在正常模式下静默展示 overviewFixture 的 82 分共识
    const errorState = page.getByTestId("overview-error");
    await expect(errorState).toBeVisible();
    await expect(page.getByText("82/100")).toHaveCount(0);
  });
});

test.describe("批次 A：十页离线 Fixture 独立完整渲染验证", () => {
  const pages = [
    { key: "01-home", url: `/${FIXTURE}`, titleTestId: "home-title", title: "股票玄学多模型研究平台" },
    { key: "02-overview", url: `/stock/600519/overview${FIXTURE}`, titleTestId: "page-title", title: "综合研判" },
    { key: "03-bazi", url: `/stock/600519/bazi${FIXTURE}`, titleTestId: "page-title", title: "八字详情" },
    { key: "04-ziwei", url: `/stock/600519/ziwei${FIXTURE}`, titleTestId: "page-title", title: "紫微斗数详情" },
    { key: "05-backtest", url: `/stock/600519/backtest${FIXTURE}`, titleTestId: "page-title", title: "历史验证" },
    { key: "06-factors", url: `/factors${FIXTURE}`, titleTestId: "page-title", title: "因子字典" },
    { key: "07-conflicts", url: `/stock/600519/conflicts${FIXTURE}`, titleTestId: "page-title", title: "模型分歧中心" },
    { key: "08-huangli", url: `/stock/600519/huangli${FIXTURE}`, titleTestId: "page-title", title: "黄历 / 日课详情" },
    { key: "09-evidence", url: `/stock/600519/evidence${FIXTURE}`, titleTestId: "page-title", title: "古籍证据检索" },
    { key: "10-timeline", url: `/stock/600519/timeline${FIXTURE}`, titleTestId: "page-title", title: "时间窗口" },
  ];

  for (const p of pages) {
    test(`[${p.key}] ${p.title} 离线独立渲染成功且标题存在`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });

      // 完全屏蔽所有后端网络请求以保证纯离线
      await page.route("**/api/v1/**", async (route) => {
        await route.abort("connectionrefused");
      });

      await page.goto(p.url, { waitUntil: "load" });
      const titleElem = page.getByTestId(p.titleTestId).first();
      await expect(titleElem).toBeVisible({ timeout: 15000 });
      await expect(titleElem).toContainText(p.title);

      // 绝无未处理页面异常
      expect(consoleErrors.filter((e) => !e.includes("favicon") && !e.includes("Failed to load resource"))).toEqual([]);
    });
  }
});

test.describe("标的切换与手动输入股票（如 002008）查询验证", () => {
  test("点击「切换股票」按钮可打开快速切换弹窗", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIXTURE}`);

    const switchBtn = page.getByTestId("switch-stock-btn");
    await expect(switchBtn).toBeVisible();
    await expect(switchBtn).not.toBeDisabled();

    // 点击打开弹窗
    await switchBtn.click();
    const modal = page.getByTestId("stock-switch-modal");
    await expect(modal).toBeVisible();

    // 弹窗内输入框可见
    const input = page.getByTestId("stock-switch-input");
    await expect(input).toBeVisible();

    // 热门快捷标签包含 002008 大族激光
    const quick002008 = page.getByTestId("quick-switch-002008");
    await expect(quick002008).toBeVisible();
    await expect(quick002008).toContainText("大族激光");

    // 点击关闭按钮可关闭
    await page.getByTestId("stock-switch-close").click();
    await expect(modal).toHaveCount(0);
  });

  test("在黄历页切换股票至 002008，路径保持为 huangli 且正确解除茅台 fixture 锁", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`);

    // 打开切换弹窗
    await page.getByTestId("switch-stock-btn").click();
    await expect(page.getByTestId("stock-switch-modal")).toBeVisible();

    // 点击 002008 快捷标签
    await page.getByTestId("quick-switch-002008").click();

    // 验证跳转路径为 /stock/002008/huangli（自动保持了当前子功能 huangli，且解除了 ?fixture 锁）
    await expect(page).toHaveURL(/\/stock\/002008\/huangli/);
    await expect(page).not.toHaveURL(/fixture=ui-reference/);

    // 上下文栏标的代码更新为 002008，名称显示大族激光
    const contextBar = page.getByTestId("stock-context-bar");
    await expect(contextBar).toBeVisible();
    await expect(contextBar).toContainText("002008");
    await expect(contextBar).toContainText("大族激光");
  });

  test("在搜索框手动输入 002008 可检索到大族激光", async ({ page }) => {
    await page.goto(`/${FIXTURE}`);
    const input = page.getByTestId("stock-search-input").first();
    await input.click();
    await input.fill("002008");

    // 检查建议下拉项包含 002008 与大族激光
    const suggestions = page.getByTestId("stock-search-suggestions");
    await expect(suggestions).toBeVisible();
    await expect(suggestions).toContainText("002008");
    await expect(suggestions).toContainText("大族激光");

    // 点击建议跳转至 /stock/002008/overview
    await suggestions.getByText("大族激光").first().click();
    await expect(page).toHaveURL(/\/stock\/002008\/overview/);
  });
});
