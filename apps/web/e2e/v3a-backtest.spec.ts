import { expect, test } from "@playwright/test";

import { referenceAnchor } from "./support/referenceAnchors";

/**
 * V3-A：05 历史验证首屏层级与参考锚点收口。
 *
 * 这一份 spec 的存在理由：R1/R1.2 期间 05 页排着 **6 张「研究卡位」空占位卡**
 * （每张 ~160px，合计 ~960px），把唯一有真实数据的持有期对比推到 y=1255，
 * 于是 `viewport-1440-pages.spec.ts:121` 长期红。空卡位既撑高页面又虚报能力。
 * 本轮按参考图 05 的实测结构重排：研究条件 → 统计指标 → 收益分布|持有期对比 →
 * 对照行 → 明细（第二屏）。
 *
 * 阈值一律从 `e2e/fixtures/reference-anchors.json` 读，测试里不抄第二份数字。
 * 达不到 ±12 的项**显式声明为 semantic exception 并写下界**，不静默放宽。
 */

const FIX = "?fixture=ui-reference";
const PAGE = "05-backtest";

test.describe("V3-A 历史验证首屏层级", () => {
  test.use({ viewport: { width: 1672, height: 941 } });

  test("六张空占位卡不得回来；没有真实数据的槽位如实标不可用", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    // 占位卡的指纹：卡头右侧的「研究卡位」标记 + 固定空高度
    await expect(page.getByText("研究卡位")).toHaveCount(0);
    await expect(page.getByTestId("backtest-reference-panels")).toHaveCount(0);

    // 收益分布没有真实逐样本序列 ⇒ 必须显式不可用，且不得画任何图
    const dist = page.getByTestId("distribution-panel");
    await expect(dist).toBeVisible();
    expect(await dist.innerText()).toMatch(/不可用|没有对应数据/);
    // 卡头图标本身就是内联 SVG，所以只查卡体里有没有图：没有 ECharts 容器、没有绘图 SVG
    await expect(dist.locator(".smp-card-body svg")).toHaveCount(0);
    await expect(dist.locator(".smp-card-body canvas")).toHaveCount(0);
    // 也不得由高斯密度拼一个"看起来像真实样本"的示意分箱冒充：
    // 判据是**有没有画出图**（上面两条 svg/canvas 计数），不是有没有出现相关字样 ——
    // 卡面上的不可用说明本身就要写出"为什么不用高斯密度生成"，那是披露文字。
    expect(await dist.innerText()).toMatch(/事件研究接口只回传|没有逐样本收益序列/);

    const grouping = page.getByTestId("grouping-panel");
    await expect(grouping).toBeVisible();
    expect(await grouping.innerText()).toMatch(/不可用|没有对应产出/);
  });

  test("首屏顺序：研究条件 → 统计指标 → 图表行 → 对照行 → 明细", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    const top = async (sel: string) => {
      const el = page.locator(sel).first();
      await expect(el).toBeVisible();
      const b = await el.boundingBox();
      expect(b, `${sel} 未渲染`).not.toBeNull();
      return b!.y;
    };
    const status = await top('[data-testid="research-status-card"]');
    const stats = await top('[data-testid="stats-summary"]');
    const chart = await top('[data-testid="distribution-panel"]');
    const horizon = await top('[data-testid="horizon-comparison"]');
    const control = await top('[data-testid="negative-control"]');
    const detail = await top('[data-testid="backtest-detail"]');

    expect(status).toBeLessThan(stats);
    expect(stats).toBeLessThan(chart);
    // 收益分布与持有期对比同一行（参考图 05 是两栏 708:715）
    expect(Math.abs(chart - horizon), "两卡不在同一行").toBeLessThanOrEqual(2);
    expect(chart).toBeLessThan(control);
    expect(control).toBeLessThan(detail);
  });

  test("可对齐的锚点必须落在 reference ±12px 内", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    const box = async (sel: string) => {
      const b = await page.locator(sel).first().boundingBox();
      expect(b, `${sel} 未渲染`).not.toBeNull();
      return b!;
    };

    const cases: [string, string, ("x" | "y" | "width" | "height")[]][] = [
      ["topbar", '[data-anchor="topbar"]', ["height"]],
      ["sidebar", '[data-anchor="sidebar"]', ["width", "height"]],
      ["pageHero", '[data-anchor="page-hero"]', ["x", "width"]],
      ["stockContextBar", '[data-testid="stock-context-bar"]', ["x", "width"]],
      ["primaryChart", '[data-anchor="primary-chart"]', ["x", "width"]],
      ["holdingPeriodCard", '[data-anchor="holding-period-card"]', ["x", "width"]],
      ["controlRow", '[data-anchor="control-row"]', ["x", "width", "height"]],
      ["resultTable", '[data-anchor="result-table"]', ["x", "width"]],
    ];

    for (const [name, sel, fields] of cases) {
      const ref = await referenceAnchor(PAGE, name);
      const b = await box(sel);
      for (const f of fields) {
        const rv = ref[f];
        if (typeof rv !== "number") continue;
        const cv = f === "x" ? b.x : f === "y" ? b.y : f === "width" ? b.width : b.height;
        expect(
          Math.abs(cv - rv),
          `${name}.${f}：candidate ${cv.toFixed(1)} vs reference ${rv} 超出 ±12px`,
        ).toBeLessThanOrEqual(12);
      }
    }
  });

  test("已声明的 semantic exception：纵向累计偏移与条件卡高度有上界", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    const refChart = await referenceAnchor(PAGE, "primaryChart");
    const refFilter = await referenceAnchor(PAGE, "filterBar");
    const chart = await page.locator('[data-anchor="primary-chart"]').first().boundingBox();
    const filter = await page.locator('[data-anchor="filter-bar"]').first().boundingBox();
    expect(chart).not.toBeNull();
    expect(filter).not.toBeNull();

    // 例外 1：filterBar 高度。参考图这一带是 67px 的一行筛选条；本系统同一承载位
    // 必须放研究状态徽标 + 数据源标记 + 四项条件（AGENTS §9.10 每张数据卡给 source/version、
    // §7 关键失败状态必须可见），压不进 67px。上界按本轮实测 157px 再加 12px 容差钉住，
    // 只防"再次长回去"，不代表对齐。
    expect(
      filter!.height,
      `研究条件卡高 ${filter!.height.toFixed(1)}px 超过已声明上界 169px`,
    ).toBeLessThanOrEqual(refFilter.height! + 102);

    // 例外 2：图表行顶边的纵向累计偏移。来源逐项可查：统一 Hero token +28
    // （R1.2 已批准，02 参考 Hero 124 / 08 109 / 05 94，取 122 是折中）、
    // 条件卡 +90、统计卡空态 +50。上界 = 参考 395 + 220，防回退不追对齐。
    expect(
      chart!.y,
      `图表行顶边 ${chart!.y.toFixed(1)} 超过已声明上界（参考 ${refChart.y} + 220）`,
    ).toBeLessThanOrEqual(refChart.y! + 220);
    // 同时必须比整改前显著上移：整改前实测 776.6（占位卡未删时）
    expect(chart!.y).toBeLessThan(700);
  });

  test("研究纪律信息不因压缩而丢失", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    // 研究状态与数据源标记常驻
    await expect(page.getByTestId("data-source-chip")).toBeVisible();
    const statusText = await page.getByTestId("research-status-card").innerText();
    expect(statusText).toMatch(/NOT_RUN|NO_SIGNAL|WEAK_EVIDENCE|INCONCLUSIVE|INVALID_CONTROL|SUPPORTED/);
    // 分区语义仍在（① / ② 标签可见）
    await expect(page.getByTestId("section-deterministic")).toBeVisible();
    await expect(page.getByTestId("section-empirical")).toBeVisible();
    // 负对照与逐行判决仍在，且不做一句话汇总
    const control = page.getByTestId("negative-control");
    await expect(control).toContainText("负对照");
    await expect(page.getByTestId("horizon-table")).toBeVisible();
    // 口径解释折叠但不删除
    const note = page.getByTestId("research-status-card");
    expect(await note.innerText()).toMatch(/NO_SIGNAL/);
  });
});

test.describe("V3-A 历史验证 1440 首屏", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("持有期对比卡顶进入 900px 首屏，且无横向溢出、风险状态不丢", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    const horizon = page.getByTestId("horizon-comparison");
    await expect(horizon).toBeVisible();
    const hb = await horizon.boundingBox();
    expect(hb, "持有期对比卡未渲染").not.toBeNull();
    // 这是 V3-A 硬门：阈值沿用 viewport-1440-pages 的 900，未放宽
    expect(hb!.y, `持有期对比卡顶 y=${hb!.y} 未进入 900px 首屏`).toBeLessThanOrEqual(900);

    const overflow = await page.locator("main").evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(overflow, "main 内部横向溢出").toBeLessThanOrEqual(2);
    const docOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(docOverflow, "整页横向溢出").toBeLessThanOrEqual(2);

    // 关键状态与文案在 1440 下仍可读、未被裁切
    await expect(page.getByTestId("data-source-chip")).toBeVisible();
    await expect(page.getByTestId("section-empirical")).toBeVisible();
    const stats = await page.getByTestId("stats-summary").innerText();
    expect(stats).toMatch(/尚无|样本数/);
    expect(stats).not.toMatch(/undefined|NaN/);
  });
});
