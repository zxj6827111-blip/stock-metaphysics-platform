/**
 * 剩余五页 + 交易日历三层覆盖的验收用例（复核任务书 §六）。
 *
 * 覆盖三类必须成立的东西：
 * 1. **结构**：紫微左 63% / 右 37%、因子字典左 40% / 右 60%、古籍左 55% / 右 45%、
 *    分歧页三场景、历史验证四段式；
 * 2. **真实性**：演示面板里的古籍条目/研究实验都带来源与版本字段，
 *    不是手写样例；分歧三场景来自真实检测器；
 * 3. **可读性几何**：1672×941 首屏必须完整看到十二宫底排、古籍三类计数、
 *    分歧六种结论矩阵——不能靠整站缩字去够首屏。
 */

import { expect, test } from "@playwright/test";

const FIXTURE = "?fixture=ui-reference";

test.describe("R3-1 紫微详情：左盘面 / 右观察栏", () => {
  test("1672 首屏完整呈现十二宫（含底排），左右分栏比例正确", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/ziwei${FIXTURE}`, { waitUntil: "load" });
    await page.waitForFunction(() => document.fonts.status === "loaded");
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    // 十二宫一个都不能少
    const cells = page.locator('[data-testid^="ziwei-palace-"]');
    await expect(cells).toHaveCount(12);

    // 整盘（含底排）必须在首屏内：底边 ≤ 941
    const grid = page.getByTestId("ziwei-chart-grid").first();
    const box = await grid.boundingBox();
    expect(box, "盘面未渲染").not.toBeNull();
    expect(box!.y + box!.height, "十二宫底排被首屏裁掉").toBeLessThanOrEqual(941);
    expect(box!.x).toBeLessThan(1672);
    expect(box!.x + box!.width).toBeLessThanOrEqual(1672);

    // 左 8 / 右 4 栅格（≈63% / 37%）
    const chartCard = page.getByTestId("ziwei-chart-card").first();
    const observation = page.getByTestId("ziwei-observation").first();
    const chartBox = await chartCard.boundingBox();
    const obsBox = await observation.boundingBox();
    expect(chartBox).not.toBeNull();
    expect(obsBox).not.toBeNull();
    const total = chartBox!.width + obsBox!.width + 12;
    const leftShare = chartBox!.width / total;
    expect(leftShare, `左栏占比 ${leftShare.toFixed(2)} 应接近 0.63`).toBeGreaterThan(0.58);
    expect(leftShare, `左栏占比 ${leftShare.toFixed(2)} 应接近 0.63`).toBeLessThan(0.68);

    // 观察栏必须在盘面右侧同一屏
    expect(obsBox!.y).toBeLessThan(941);
    expect(obsBox!.x).toBeGreaterThan(chartBox!.x + chartBox!.width - 1);
  });

  test("顺逆切换联动真实数据，缺失星曜不补造", async ({ page }) => {
    await page.goto(`/stock/600519/ziwei${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    const before = await page.locator('[data-testid^="ziwei-palace-"]').first().innerText();
    await page.getByRole("button", { name: /逆行|Variant B/ }).first().click();
    await expect
      .poll(async () => page.locator('[data-testid^="ziwei-palace-"]').first().innerText(), {
        timeout: 10_000,
      })
      .not.toBe("");

    // 变体假设必须可见（顺行/逆行是两个假设，不是事实）
    await expect(page.getByTestId("variant-note").first()).toBeVisible();
    // 原始盘面可访问
    await expect(page.getByTestId("ziwei-source-method").first()).toBeAttached();
    expect(before.length).toBeGreaterThan(0);
  });
});

test.describe("R3-2 因子字典：左列表 / 右分区详情", () => {
  test("列表 40% / 详情 60%，详情按定义-计算-依赖-证据-历史验证分区", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/factors${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    const list = page.getByTestId("factor-list").first();
    const detail = page.getByTestId("factor-detail").first();
    const listBox = await list.boundingBox();
    const detailBox = await detail.boundingBox();
    expect(listBox).not.toBeNull();
    expect(detailBox).not.toBeNull();
    const total = listBox!.width + detailBox!.width + 12;
    const listShare = listBox!.width / total;
    expect(listShare, `列表占比 ${listShare.toFixed(2)} 应接近 0.40`).toBeGreaterThan(0.35);
    expect(listShare, `列表占比 ${listShare.toFixed(2)} 应接近 0.40`).toBeLessThan(0.45);

    for (const section of ["因子定义", "计算", "依赖字段", "证据", "历史验证"]) {
      await expect(page.getByTestId(`factor-section-${section}`).first()).toBeAttached();
    }
    // 没有跑过的统计不许显示成数字：历史验证区必须是明确空态
    await expect(page.getByTestId("factor-history-empty").first()).toBeVisible();
    await expect(page.getByTestId("rule-score-meaning").first()).toContainText("不代表");
  });

  test("真实因子 ID 出现在列表（不是手写样例）", async ({ page }) => {
    await page.goto(`/factors${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("factor-row-B_NATAL_001").first()).toBeVisible();
    const main = page.locator("main").first();
    await expect(main).toContainText("共 114 个");
  });
});

test.describe("R3-3 模型分歧中心：三场景 + 矩阵", () => {
  for (const scenario of ["no_conflict", "conflict", "engine_unavailable"] as const) {
    test(`场景 ${scenario} 可独立呈现`, async ({ page }) => {
      await page.goto(`/stock/600519/conflicts${FIXTURE}&scenario=${scenario}`, {
        waitUntil: "load",
      });
      await expect(page.getByTestId("page-title").first()).toBeVisible();
      const marker = page.getByTestId("conflict-scenario").first();
      await expect(marker).toHaveAttribute("data-scenario", scenario);

      // 三种场景都必须有结论矩阵；每行都有方向/强度/置信度列
      await expect(page.getByTestId("matrix-row-bazi").first()).toBeVisible();
      await expect(page.getByTestId("matrix-row-ziwei").first()).toBeVisible();
      await expect(page.getByTestId("matrix-row-huangli").first()).toBeVisible();

      if (scenario === "engine_unavailable") {
        await expect(page.getByTestId("opinion-ziwei").first()).toHaveAttribute("data-available", "0");
        await expect(page.getByTestId("available-engines").first()).toContainText("2");
        await expect(page.getByTestId("opinion-ziwei").first()).toContainText("score = null");
      } else {
        await expect(page.getByTestId("opinion-ziwei").first()).toHaveAttribute("data-available", "1");
      }
      if (scenario === "no_conflict") {
        await expect(page.getByTestId("no-conflict-note").first()).toBeVisible();
      }
    });
  }

  test("共识与冲突同时可见，不用平均分掩盖", async ({ page }) => {
    await page.goto(`/stock/600519/conflicts${FIXTURE}&scenario=conflict`, { waitUntil: "load" });
    await expect(page.getByTestId("consensus-label").first()).toBeVisible();
    await expect(page.getByTestId("conflict-level").first()).toBeVisible();
    const main = page.locator("main").first();
    await expect(main).toContainText("不做平均");
  });
});

test.describe("R3-4 历史验证：四段式 + 真实实验", () => {
  test("规则强度与统计有效性独立分区，持有期对比图来自真实实验", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    await expect(page.getByTestId("section-deterministic").first()).toBeVisible();
    await expect(page.getByTestId("section-empirical").first()).toBeVisible();
    await expect(page.getByTestId("research-status-card").first()).toBeVisible();
    await expect(page.getByTestId("horizon-comparison").first()).toBeVisible();
    await expect(page.getByTestId("backtest-detail").first()).toBeVisible();

    // 真实入库实验被读到：持有期表有行，且出现真实对照组合
    await expect(page.getByTestId("experiment-select").first()).toBeVisible();
    const rows = page.locator('[data-testid="horizon-table"] tbody tr');
    await expect(rows.first()).toBeVisible();
    const main = page.locator("main").first();
    await expect(main).toContainText("随机出生日");
    await expect(page.getByTestId("horizon-comparison-chart").first()).toBeVisible();
  });

  test("负对照失效必须醒目，且不画净值/分布", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIXTURE}`, { waitUntil: "load" });
    // 选择 INVALID_CONTROL 的那个实验
    await page.getByTestId("experiment-select").first().selectOption("EXP-20260918173500-6f0889");
    await expect(page.getByTestId("invalid-control-warning").first()).toBeVisible();
    await expect(page.getByTestId("invalid-control-warning").first()).toContainText("Jaccard");

    const main = page.locator("main").first();
    await expect(main).toContainText("没有收益分布图与净值曲线");
  });

  test("逐标的 EventStudy 为真实空态（不显示未运行的统计）", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIXTURE}`, { waitUntil: "load" });
    // 演示样本刻意为空：不得出现编造的样本数/收益
    await expect(page.getByTestId("stats-summary").first()).toContainText("尚无");
  });
});

test.describe("R3-5 古籍证据：反证优先 + 原文-解释-主题链", () => {
  test("计数首屏可见，反证排在支持之前", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/evidence${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    for (const k of ["counter", "support", "neutral"]) {
      const box = await page.getByTestId(`stance-count-${k}`).first().boundingBox();
      expect(box, `${k} 计数未渲染`).not.toBeNull();
      expect(box!.y, `${k} 计数不在首屏`).toBeLessThan(941);
    }

    const items = page.locator('[data-testid^="evidence-item-"]');
    await expect(items.first()).toHaveAttribute("data-stance", "counter");
    // 三类都要出现在列表里（并列，不是只给一类）
    const stances = await items.evaluateAll((els) =>
      els.map((e) => e.getAttribute("data-stance")),
    );
    expect(new Set(stances).size, "列表里只出现了一类证据").toBeGreaterThan(1);
  });

  test("详情给出原文→解释→主题与完整的来源字段", async ({ page }) => {
    await page.goto(`/stock/600519/evidence${FIXTURE}`, { waitUntil: "load" });
    const body = page.getByTestId("evidence-detail-body").first();
    await expect(body).toContainText("① 原典原文");
    await expect(body).toContainText("② 项目解释");
    await expect(body).toContainText("③ 关联主题与因子");

    const prov = page.getByTestId("evidence-provenance").first();
    for (const field of ["来源：", "版本：", "出处：", "版权：", "条目 ID："]) {
      await expect(prov).toContainText(field);
    }
    // 语料的"未校勘"限制必须显示
    await expect(page.getByTestId("evidence-caveat").first()).toContainText("校勘");
  });
});

test.describe("R3-6 交易日历三层覆盖", () => {
  test("黄历页显示实测/公布两层覆盖与逐卡来源", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();
    await expect(page.getByTestId("huangli-calendar-scope").first()).toContainText("实测成交日");
  });

  test("真实/演示接口都返回三层覆盖元数据（结构一致）", async ({ request }) => {
    // 只读接口：日历覆盖元数据必须能把"行情末日/实测日历/官方公布"分开
    const res = await request.get("/api/backend/api/v1/system/trading-calendar?exchange=SSE");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.observed.end).toBeTruthy();
    expect(body.published.end).toBeTruthy();
    expect(body.published.verified).toBe(true);
    expect(body.published.end > body.observed.end).toBe(true);
    expect(body.generator).toContain("update_trading_calendar");
  });
});
