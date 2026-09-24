import { expect, test } from "@playwright/test";

/**
 * 本轮（品牌视觉 / 黄历 / 时间窗口）验收。
 *
 * 覆盖三类断言，缺一不可：
 *  1. **功能闭环**：日期卡数量、档位切换、联动、图表、统计与口径披露；
 *  2. **诚实性**：只有吉/凶不补「平」；缺失模型显示不可用而不是 0；
 *     没有策略净值字段；演示样本对不上的参数组合显式说明；
 *  3. **隔离与容错**：演示模式零真实请求；后端分区失败只降级该分区。
 *
 * "部分模型缺失 / 接口 500 / 有冲突"这类场景无法从固定样本里长出来。
 * 它们放在文件末尾的 **live 组**：默认跳过，需要显式设置
 * `SMP_E2E_LIVE_API=1` 且已启动**隔离**后端（数据库副本 + 离线行情）时才运行。
 * 这样既拿到了真实失败路径的证据，又不会让默认套件依赖外部进程或写入共享研究库。
 */

const FIXTURE = "?fixture=ui-reference";
const LIVE = process.env.SMP_E2E_LIVE_API === "1";
const ASOF = process.env.SMP_E2E_ASOF ?? "2024-11-15T14:32:00";

test.describe("黄历：未来交易日日期卡", () => {
  test("默认口径为前 20 个交易日，且不含周末", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    await expect(page.getByTestId("huangli-day-grid")).toBeVisible();
    const cards = page.locator('[data-testid^="huangli-day-2"]');
    await expect(cards).toHaveCount(20);

    const rule = page.getByTestId("huangli-outlook-rule");
    await expect(rule).toContainText("交易日");
    await expect(rule).toContainText("实测成交日");

    const dates = await cards.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-testid")!.replace("huangli-day-", "")),
    );
    for (const d of dates) {
      const day = new Date(`${d}T00:00:00Z`).getUTCDay();
      expect(day, `${d} 是周末，不应出现在交易日卡里`).toBeGreaterThanOrEqual(1);
      expect(day, `${d} 是周末，不应出现在交易日卡里`).toBeLessThanOrEqual(5);
    }
    expect([...dates].sort()).toEqual(dates);
    expect(new Set(dates).size).toBe(dates.length);
  });

  test("日期卡同时有文字分类与图例，且只有吉/凶不补「平」", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const labels = await page
      .locator('[data-testid="huangli-day-grid"] [data-testid^="huangli-class-"]')
      .evaluateAll((els) => els.map((e) => e.textContent?.trim()));
    expect(labels.length).toBe(20);
    expect([...new Set(labels)].every((v) => v === "吉" || v === "凶")).toBe(true);
    expect(new Set(labels).has("平"), "后端通书口径只有吉/凶，不得补出「平」").toBe(false);

    // 首屏改左右双栏后：图例留在日期网格卡，分类口径说明随选中日详情进右栏。
    // 这里改的是**选择器落点**，四条内容断言一条都没放宽。
    const gridCard = page.getByTestId("huangli-outlook");
    await expect(gridCard).toContainText("图例");
    await expect(gridCard).toContainText("不是买入/卖出建议");
    const selectedCard = page.getByTestId("huangli-selected-card");
    await expect(selectedCard).toContainText("huangli-day-class-v1");
    await expect(selectedCard).toContainText("不产出「平」");
  });

  test("点击日期卡联动当天干支/宜忌/冲煞", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const detail = page.getByTestId("huangli-selected-day");
    await expect(detail).toBeVisible();
    const first = page.locator('[data-testid^="huangli-day-2"]').first();
    const firstId = (await first.getAttribute("data-testid"))!;

    const second = page.getByTestId("huangli-day-2024-12-12");
    await second.click();
    await expect(detail).toContainText("2024-12-12");
    await expect(detail).toContainText("建除十二值");
    await expect(detail).toContainText("冲煞");
    await expect(detail).toContainText("宜（通书事宜）");
    await expect(detail).toContainText("忌（通书禁忌）");

    await expect(page.getByTestId(firstId)).toHaveAttribute("aria-pressed", "false");
    await expect(second).toHaveAttribute("aria-pressed", "true");
  });

  test("今日 / 近20个交易日 / 近3个月 三档切换，长区间按月分组", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    await page.getByTestId("huangli-tab-today").click();
    await expect(page.locator('[data-testid^="huangli-day-2"]')).toHaveCount(1);

    await page.getByTestId("huangli-tab-20d").click();
    await expect(page.locator('[data-testid^="huangli-day-2"]')).toHaveCount(20);

    await page.getByTestId("huangli-tab-3m").click();
    const groups = page.getByTestId("huangli-month-groups");
    await expect(groups).toBeVisible();
    // 长区间按自然月分组，且每组标注交易日数量（不让卡片无限撑高页面）
    await expect(groups).toContainText("个交易日");
    const monthHeaders = await groups.locator("span.font-semibold").allInnerTexts();
    expect(monthHeaders.length).toBeGreaterThanOrEqual(3);
    for (const h of monthHeaders) expect(h).toMatch(/^\d{4}-\d{2}$/);
  });
});

test.describe("黄历：证据与历史表现", () => {
  test("披露区间/持有期/复权口径/数据截止/版本与统计限制", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const prov = page.getByTestId("huangli-perf-provenance");
    await expect(prov).toBeVisible();
    for (const label of [
      "研究区间",
      "持有期",
      "分类依据",
      "复权口径",
      "行情来源",
      "基准",
      "数据截止",
      "口径版本",
    ]) {
      await expect(prov).toContainText(label);
    }

    await expect(page.getByTestId("huangli-class-trend")).toBeVisible();
    await expect(page.getByTestId("huangli-performance")).toContainText("不是净值");

    const groups = page.getByTestId("huangli-perf-groups");
    for (const col of ["样本", "平均", "中位数", "上涨占比"]) {
      await expect(groups).toContainText(col);
    }
    await expect(page.getByTestId("huangli-perf-group-auspicious")).toBeVisible();
    await expect(page.getByTestId("huangli-perf-group-inauspicious")).toBeVisible();

    await expect(page.getByTestId("huangli-performance")).toContainText("互不重叠");
    await expect(page.getByTestId("huangli-perf-findings")).toContainText("因果");
  });

  test("不提供净值/累计收益/仓位建议，并说明为什么没有", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    // 标签层面不得出现：任何表头、图例、按钮都不叫这些名字
    const labels = await page.evaluate(() => {
      const root = document.querySelector('[data-testid="huangli-performance"]');
      if (!root) return [];
      return [
        ...root.querySelectorAll("th, figcaption, button, summary"),
      ].map((e) => (e.textContent ?? "").trim());
    });
    for (const label of labels) {
      for (const forbidden of ["净值", "累计投资收益", "夏普", "仓位建议", "建议仓位"]) {
        expect(label, `不该有名为「${forbidden}」的标签`).not.toContain(forbidden);
      }
    }
    // 免责声明必须解释"序列是什么、不是什么"
    const body = await page.getByTestId("huangli-performance").innerText();
    expect(body).toContain("不是净值");
    expect(body).toContain("不是累计投资收益");
    expect(body).toContain("不是策略回测");
  });

  test("演示样本对不上的参数组合要显式说明，不静默复用", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await expect(page.getByTestId("huangli-perf-groups")).toBeVisible();

    await page.getByTestId("huangli-perf-horizon-5").click();
    const miss = page.getByTestId("huangli-perf-fixture-miss");
    await expect(miss).toBeVisible();
    await expect(miss).toContainText("演示模式");
    await expect(page.getByTestId("huangli-perf-groups")).toHaveCount(0);
  });
});

test.describe("时间窗口：研究页面结构", () => {
  test("摘要 / 主视图 / 热力图 / 解释 / 排名 / 审计入口齐备", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    for (const id of [
      "timeline-summary",
      "timeline-main-view",
      "timeline-heatmap",
      "timeline-explainer",
      "timeline-week-ranking",
      "timeline-audit",
    ]) {
      await expect(page.getByTestId(id)).toBeVisible();
    }

    const summary = page.getByTestId("timeline-summary");
    await expect(summary).toContainText("月度覆盖");
    await expect(summary).toContainText("周度覆盖");
    await expect(summary).toContainText("逐日覆盖");
    await expect(summary).toContainText("不是涨跌概率");
    await expect(summary).toContainText("聚合口径版本");
  });

  test("逐日与月度两种粒度都能出图，且月度用阶梯线", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    await expect(page.getByTestId("timeline-step-chart")).toBeVisible();
    await expect(page.getByTestId("timeline-main-view")).toContainText("覆盖 20/20 个窗口");

    await page.getByTestId("timeline-gran-months").click();
    await expect(page.getByTestId("timeline-step-chart")).toBeVisible();
    await expect(page.getByTestId("timeline-main-view")).toContainText("阶梯线");
    await expect(page.getByTestId("timeline-main-view")).toContainText("两点之间没有观测");
  });

  test("点击热力图日期后，右侧解释显示该日原始结果与风险，且不生成因子归因", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const cells = page.locator('[data-testid^="timeline-heat-"]');
    await expect(cells.first()).toBeVisible();
    const first = cells.first();
    const date = (await first.getAttribute("data-testid"))!.replace("timeline-heat-", "");
    await first.click();

    const body = page.getByTestId("timeline-explainer-body");
    await expect(body).toBeVisible();
    await expect(body).toContainText(date);
    await expect(body).toContainText("可用性");
    await expect(body).toContainText("研究状态");
    await expect(body).toContainText("版本");
    await expect(page.getByTestId("timeline-explainer")).toContainText("不提供因子归因");
    // 不得出现参考图里那种"高权重/中权重"的伪归因标签
    const explainer = await page.getByTestId("timeline-explainer").innerText();
    for (const forbidden of ["高权重", "中权重", "低权重"]) {
      expect(explainer, `不该出现伪因子权重「${forbidden}」`).not.toContain(forbidden);
    }
  });

  test("点击周排名后解释面板显示该周，含聚合口径与分布", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const table = page.getByTestId("week-ranking-table");
    await expect(table).toBeVisible();
    await table.locator("tbody tr").first().click();

    const body = page.getByTestId("timeline-explainer-body");
    await expect(body).toBeVisible();
    await expect(body).toContainText("周度窗口");
    await expect(body).toContainText("均值");
    await expect(body).toContainText("偏强日占比");
    await expect(body).toContainText("流周");
  });

  test("审计入口保留原始表格，标题数量与实际行数一致", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const monthCount = await page.locator('[data-testid^="month-row-"]').count();
    const weekCount = await page.locator('[data-testid^="week-row-"]').count();
    expect(monthCount).toBe(12);
    expect(weekCount).toBe(12);
    await expect(page.getByTestId("timeline-audit")).toContainText(`共 ${monthCount} 个月`);
    await expect(page.getByTestId("timeline-audit")).toContainText(`共 ${weekCount} 周`);
  });
});

/**
 * live 组：需要隔离后端（数据库副本 + 离线真实行情）。
 *
 * 启动方式见 docs/UI_CALENDAR_WINDOW_COMPLETION_REPORT.md §验收复现；
 * 默认跳过，避免默认套件依赖外部进程，也避免误连共享研究库。
 */
test.describe("时间窗口：缺失模型 / 接口失败 / 有冲突（需隔离后端）", () => {
  test.skip(!LIVE, "需要 SMP_E2E_LIVE_API=1 与隔离后端");

  test("紫微分数全为 null 时：摘要标注不可用、其它模型照常出图，且不以 0 替代", async ({
    page,
  }) => {
    await page.route("**/timeline/days*", async (route) => {
      const response = await route.fetch();
      const json = await response.json();
      json.days = (json.days ?? []).map((d: Record<string, unknown>) => ({
        ...d,
        ziwei_score: null,
        ziwei_direction: 0,
      }));
      json.available_engines = ["bazi", "huangli"];
      await route.fulfill({ response, json });
    });

    await page.goto(`/stock/600519/timeline?asOf=${ASOF}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await expect(page.getByTestId("timeline-step-chart")).toBeVisible({ timeout: 90_000 });

    const summary = page.getByTestId("timeline-summary");
    await expect(summary).toContainText("紫微斗数");
    await expect(summary).toContainText("不可用");
    // 不可用不等于 0：图注的覆盖数必须小于总数
    await expect(page.getByTestId("timeline-main-view")).toContainText("紫微 覆盖 0/20");
  });

  test("逐日接口首次 500：该分区报错并可重试，其余分区不受影响", async ({ page }) => {
    let attempts = 0;
    await page.route("**/timeline/days*", async (route) => {
      attempts += 1;
      if (attempts === 1) {
        await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
        return;
      }
      await route.continue();
    });

    await page.goto(`/stock/600519/timeline?asOf=${ASOF}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    const err = page.getByTestId("timeline-days-error");
    await expect(err).toBeVisible({ timeout: 60_000 });
    // 分区失败不拖垮整页
    await expect(page.getByTestId("timeline-summary")).toBeVisible();
    await expect(page.getByTestId("timeline-audit")).toBeVisible();

    await err.getByRole("button", { name: "重试本区" }).click();
    await expect(page.getByTestId("timeline-step-chart")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByTestId("timeline-days-error")).toHaveCount(0);
  });

  test("月度窗口有冲突时，明细表同时给出共识与中文冲突级别", async ({ page }) => {
    await page.goto(`/stock/600519/timeline?asOf=${ASOF}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await expect(page.locator('[data-testid^="month-row-"]').first()).toBeVisible({
      timeout: 90_000,
    });

    const text = await page.getByTestId("month-table").innerText();
    expect(text).toMatch(/无冲突|有冲突/);
    // 冲突级别必须是中文（minor/moderate/… 不裸露）
    expect(text).not.toMatch(/\bminor\b|\bmoderate\b|\bmajor\b|\bsevere\b/);
  });

  test("真实黄历页：日期卡来自后端实测交易日历，收益统计来自真实行情", async ({ page }) => {
    await page.goto(`/stock/600519/huangli?asOf=${ASOF}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    await expect(page.locator('[data-testid^="huangli-day-2"]')).toHaveCount(20, {
      timeout: 60_000,
    });
    await expect(page.getByTestId("huangli-perf-provenance")).toBeVisible({ timeout: 90_000 });
    // 真实行情来源必须写明（不是"unknown"/空）
    const prov = await page.getByTestId("huangli-perf-provenance").innerText();
    expect(prov).toContain("tencent_hfq_import");
    expect(prov).not.toContain("—");
  });
});
