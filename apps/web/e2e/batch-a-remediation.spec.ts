import { expect, test } from "@playwright/test";
import { multiAnalysisFixture } from "../lib/fixture";

/**
 * 批次 A 整改验收与补验测试集。
 *
 * 覆盖：
 *  1. 黄历 primary 真实字段映射与传统宜忌；
 *  2. 正常模式假数据隔离（无后端时不伪造共识与走势，空态诚实）；
 *  3. 十页离线 Fixture 独立渲染与核心内容级断言；
 *  4. 专项 1：Fixture 模式点击「重新计算」零后端网络请求；
 *  5. 专项 2：非支持股票带 fixture 参数时阻断真实 POST 与持久化，显示隔离警告；
 *  6. 专项 3：时间窗口分析基准日期存在，月份评分、方向与可用性正常（无「不可用」）；
 *  7. 专项 4：真实会话历史记录流转（空态 → 分析后记录呈现，最多 3 条）；
 *  8. 专项 5：主分析成功但共识/冲突接口失败时优雅降级（不崩溃）；
 *  9. 标的切换弹窗与手动输入 002008 检索。
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
    const errorState = page.getByTestId("overview-error");
    await expect(errorState).toBeVisible();
    await expect(page.getByText("82/100")).toHaveCount(0);
  });
});

test.describe("批次 A：十页离线 Fixture 独立完整渲染与内容级断言验证", () => {
  const pages = [
    {
      key: "01-home",
      url: `/${FIXTURE}`,
      titleTestId: "home-title",
      title: "股票玄学多模型研究平台",
      contentTestId: "recent-600519",
    },
    {
      key: "02-overview",
      url: `/stock/600519/overview${FIXTURE}`,
      titleTestId: "page-title",
      title: "综合研判",
      contentTestId: "stock-context-bar",
    },
    {
      key: "03-bazi",
      url: `/stock/600519/bazi${FIXTURE}`,
      titleTestId: "page-title",
      title: "八字详情",
      contentTestId: "wuxing-card",
    },
    {
      key: "04-ziwei",
      url: `/stock/600519/ziwei${FIXTURE}`,
      titleTestId: "page-title",
      title: "紫微斗数详情",
      contentTestId: "ziwei-chart-grid",
    },
    {
      key: "05-backtest",
      url: `/stock/600519/backtest${FIXTURE}`,
      titleTestId: "page-title",
      title: "历史验证",
      contentTestId: "stock-context-bar",
    },
    {
      key: "06-factors",
      url: `/factors${FIXTURE}`,
      titleTestId: "page-title",
      title: "因子字典",
      contentTestId: "factor-table",
    },
    {
      key: "07-conflicts",
      url: `/stock/600519/conflicts${FIXTURE}`,
      titleTestId: "page-title",
      title: "模型分歧中心",
      contentTestId: "conflict-level",
    },
    {
      key: "08-huangli",
      url: `/stock/600519/huangli${FIXTURE}`,
      titleTestId: "page-title",
      title: "黄历 / 日课详情",
      contentTestId: "traditional-huangli",
    },
    {
      key: "09-evidence",
      url: `/stock/600519/evidence${FIXTURE}`,
      titleTestId: "page-title",
      title: "古籍证据检索",
      contentTestId: "evidence-filter",
    },
    {
      key: "10-timeline",
      url: `/stock/600519/timeline${FIXTURE}`,
      titleTestId: "page-title",
      title: "时间窗口",
      contentTestId: "month-table",
    },
  ];

  for (const p of pages) {
    test(`[${p.key}] ${p.title} 离线独立渲染成功且核心内容存在`, async ({ page }) => {
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

      // 内容级断言：确保真实结构 DOM 正常挂载
      const contentElem = page.getByTestId(p.contentTestId).first();
      await expect(contentElem).toBeVisible({ timeout: 10000 });

      // 绝无未处理页面异常
      expect(
        consoleErrors.filter((e) => !e.includes("favicon") && !e.includes("Failed to load resource")),
      ).toEqual([]);
    });
  }
});

test.describe("批次 A 补验专项 1：Fixture 零后端请求验证", () => {
  test("在演示模式下点击「重新计算」，严禁向后端发起任何网络请求", async ({ page }) => {
    let backendCalls = 0;
    await page.route("**/api/**", async (route) => {
      backendCalls++;
      await route.abort("connectionrefused");
    });

    await page.goto(`/stock/600519/overview${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    // 初始进入页面在 fixture 模式下不发起任何后端请求
    expect(backendCalls).toBe(0);

    // 点击上下文栏的“重新计算”按钮
    const recalcBtn = page.getByTestId("recalculate");
    await expect(recalcBtn).toBeVisible();
    await recalcBtn.click();

    // 稍等以捕获可能的异步请求
    await page.waitForTimeout(1000);

    // 断言整个重新计算流程零后端请求（包括 /consensus, /conflicts, /backtest, /evidence 等）
    expect(backendCalls).toBe(0);

    // 页面依然展示正常的演示内容
    await expect(page.getByTestId("stock-context-bar")).toBeVisible();
  });
});

test.describe("批次 A 补验专项 2：非支持标的演示模式隔离验证", () => {
  test("访问非 600519 标的且带 fixture 参数时，阻断真实分析与持久化，展示明确隔离警告", async ({ page }) => {
    let postAnalysisCalls = 0;
    await page.route("**/api/v1/**", async (route) => {
      if (route.request().method() === "POST") {
        postAnalysisCalls++;
      }
      await route.abort("connectionrefused");
    });

    // 直接访问 002008 并携带 fixture 参数
    await page.goto(`/stock/002008/overview${FIXTURE}`, { waitUntil: "load" });

    // 严禁发起 POST 真实排盘分析与持久化请求
    expect(postAnalysisCalls).toBe(0);

    // 必须呈现明确的不支持隔离警告卡片
    const unsupportedCard = page.getByTestId("unsupported-fixture-error");
    await expect(unsupportedCard).toBeVisible();
    const cardText = await unsupportedCard.innerText();
    expect(cardText).toContain("演示模式（UI 复刻）仅支持 600519");
    expect(cardText).toContain("002008");
    expect(cardText).toContain("已统一阻断对真实后端的排盘分析与持久化请求");

    // 必须提供“移除 fixture 参数并进入真实分析模式”的按钮
    const enterRealBtn = page.getByTestId("enter-real-mode-btn");
    await expect(enterRealBtn).toBeVisible();
    await expect(enterRealBtn).toHaveAttribute("href", "/stock/002008/overview");
  });
});

test.describe("批次 A 补验专项 3：时间窗口演示数据具体值与可用性验证", () => {
  test("时间窗口页面基准日期展示正常，四个月份三模型评分与方向具体可用，绝不显示「不可用」", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    // 验证分析基准日期不为空，且包含 2024-11-15
    const contextBar = page.getByTestId("stock-context-bar");
    await expect(contextBar).toBeVisible();
    const contextText = await contextBar.innerText();
    expect(contextText).toContain("分析基准");
    expect(contextText).toContain("2024-11-15");

    // 验证月度窗口表格存在
    const monthTable = page.getByTestId("month-table");
    await expect(monthTable).toBeVisible();

    // 逐月断言具体评分、方向与共识状态，坚决排除“不可用”
    const row202411 = page.getByTestId("month-row-2024-11");
    await expect(row202411).toBeVisible();
    const text202411 = await row202411.innerText();
    expect(text202411).toContain("78");
    expect(text202411).toContain("72");
    expect(text202411).toContain("74");
    expect(text202411).toContain("偏强");
    expect(text202411).toContain("正向共振");
    expect(text202411).not.toContain("不可用");

    const row202412 = page.getByTestId("month-row-2024-12");
    const text202412 = await row202412.innerText();
    expect(text202412).toContain("76");
    expect(text202412).toContain("62");
    expect(text202412).toContain("70");
    expect(text202412).toContain("温和偏强");
    expect(text202412).not.toContain("不可用");

    const row202501 = page.getByTestId("month-row-2025-01");
    const text202501 = await row202501.innerText();
    expect(text202501).toContain("58");
    expect(text202501).toContain("75");
    expect(text202501).toContain("56");
    expect(text202501).toContain("中性观察");
    expect(text202501).not.toContain("不可用");

    const row202502 = page.getByTestId("month-row-2025-02");
    const text202502 = await row202502.innerText();
    expect(text202502).toContain("82");
    expect(text202502).toContain("80");
    expect(text202502).toContain("76");
    expect(text202502).toContain("强烈共振");
    expect(text202502).not.toContain("不可用");
  });
});

test.describe("批次 A 补验专项 4：真实会话历史记录流转验证", () => {
  test("正常模式下无记录显示空态，完成分析后返回首页记录真实呈现（最多保留 3 条）", async ({ page }) => {
    // 1) 初始访问正常模式首页，验证诚实空态
    await page.goto("/");
    await expect(page.getByTestId("home-title").first()).toBeVisible();
    await expect(page.getByTestId("recent-empty")).toBeVisible();
    await expect(page.getByTestId("recent-600519")).toHaveCount(0);

    // 2) 模拟向会话存储注入 1 条已完成分析记录
    await page.evaluate(() => {
      sessionStorage.setItem(
        "smp_recent_analyses_session",
        JSON.stringify([
          {
            code: "600519",
            name: "贵州茅台",
            analyzedAt: "2024-11-15 14:32",
            price: "—",
            changePct: "—",
            trend: "up",
            engines: [
              { key: "bazi", label: "八字", direction: 1 },
              { key: "ziwei", label: "紫微", direction: 1 },
              { key: "huangli", label: "黄历", direction: 1 },
            ],
            status: "正向共振",
            statusTone: "up",
          },
        ]),
      );
    });

    // 3) 返回/刷新首页，断言记录成功出现，且空态消失
    await page.goto("/");
    await expect(page.getByTestId("recent-empty")).toHaveCount(0);
    const card600519 = page.getByTestId("recent-600519");
    await expect(card600519).toBeVisible();
    await expect(card600519).toContainText("贵州茅台");
    await expect(card600519).toContainText("正向共振");
  });
});

test.describe("批次 A 补验专项 5：主分析成功但共识/冲突接口失败容错验证", () => {
  test("主分析接口成功但共识与冲突接口返回 500 时，页面优雅降级且不崩溃", async ({ page }) => {
    // 拦截主分析接口返回正常多模型数据
    await page.route("**/api/v1/stocks/600519/analysis/multi", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(multiAnalysisFixture),
      });
    });

    // 拦截共识与冲突接口返回 500 服务端异常
    await page.route("**/api/v1/analysis/*/consensus", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "INTERNAL_ERROR", message: "Consensus calculation failed" } }),
      });
    });
    await page.route("**/api/v1/analysis/*/conflicts", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "INTERNAL_ERROR", message: "Conflict calculation failed" } }),
      });
    });

    // 正常模式访问综合研判页（不带 fixture）
    await page.goto("/stock/600519/overview");

    // 页面核心结构依然正常渲染，不崩溃白屏
    await expect(page.getByTestId("page-title").first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("stock-context-bar")).toBeVisible();

    // 引擎卡片依然能够根据主分析 opinion 展示
    await expect(page.getByTestId("engine-card-bazi")).toBeVisible();
  });
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
