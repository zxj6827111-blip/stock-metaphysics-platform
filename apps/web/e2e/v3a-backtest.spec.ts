import { expect, test, type Page } from "@playwright/test";

import { referenceAnchor, referenceControlColumns } from "./support/referenceAnchors";

/**
 * V3-A.1：05 历史验证首屏几何与真实性门禁。
 *
 * 这一份 spec 的存在理由：R1/R1.2 期间 05 页排着 **6 张「研究卡位」空占位卡**
 * （每张 ~160px，合计 ~960px），把唯一有真实数据的持有期对比推到 y=1255，
 * 于是 `viewport-1440-pages.spec.ts:121` 长期红。空卡位既撑高页面又虚报能力。
 * V3-A 按参考图 05 的实测骨架重排后该门首次真绿（阈值 `<=900` 一字未动）。
 *
 * **V3-A.1 删掉了 V3-A 留下的两条过大 semantic exception**（独立审核结论
 * CHANGES_REQUIRED 第 2 条）：
 *   * `chart.y <= reference.y + 220`（实测 +203.4px）
 *   * `filter.height <= reference.height + 102`（实测 +90px）
 * 它们已经不是"容差"而是"把没对齐登记成已解释"。本轮改为按布局收口后的
 * 真实目标逐项卡死，阈值全部从 `e2e/fixtures/reference-anchors.json` 读，
 * 测试里不抄第二份数字。
 *
 * 本轮几何目标（任务书 §11）：
 *   pageHero          height  ±12
 *   filterBar         top ±12 / height ≤ ref + 24
 *   summaryMetrics    top、height ±16
 *   primaryChart      top ±20 / height ±24
 *   holdingPeriodCard top ±20 / height ±24
 *   controlRow        top ±24 / height ±16
 *   resultTable       top ±24
 */

const FIX = "?fixture=ui-reference";
const PAGE = "05-backtest";

/** 一条几何断言的容差规格；`maxHeightDelta` 用于"允许真实语义变高、但不许失控"的项。 */
interface GeoCase {
  name: string;
  sel: string;
  top?: number;
  height?: number;
  /** 只给上界（语义上允许变高）时用这两个：上界 ref+heightPlus、下界 ref−heightMinus。 */
  heightPlus?: number;
  heightMinus?: number;
  fields?: ("x" | "width")[];
}

const GEO: GeoCase[] = [
  { name: "topbar", sel: '[data-anchor="topbar"]', height: 12, fields: ["x", "width"] },
  { name: "sidebar", sel: '[data-anchor="sidebar"]', height: 12, fields: ["x", "width"] },
  { name: "pageHero", sel: '[data-anchor="page-hero"]', top: 12, height: 12, fields: ["x", "width"] },
  {
    name: "stockContextBar",
    sel: '[data-testid="stock-context-bar"]',
    top: 12,
    height: 12,
    fields: ["x", "width"],
  },
  {
    name: "filterBar",
    sel: '[data-anchor="filter-bar"]',
    top: 12,
    // 本系统这一带要同时放 ① 规则强度与 ② 研究状态/审计字段，
    // 参考图 67px 装不下；上界 ref+24 是**真实语义扩展的上界**，不是 exception。
    heightPlus: 24,
    // V3-B 追加的下界：本轮实测 54px（比参考矮 13）已被独立审核接受。
    // 只有上界的话，未来把它压成极薄的一条也照样绿 —— 那不是回归保护。
    // 取 ref−20（≈47px）：容得下正常措辞波动，拒绝"整带被压扁"。UI 未改。
    heightMinus: 20,
    fields: ["x", "width"],
  },
  {
    name: "summaryMetrics",
    sel: '[data-anchor="summary-metrics"]',
    top: 16,
    height: 16,
  },
  { name: "primaryChart", sel: '[data-anchor="primary-chart"]', top: 20, height: 24, fields: ["x"] },
  {
    name: "holdingPeriodCard",
    sel: '[data-anchor="holding-period-card"]',
    top: 20,
    height: 24,
    fields: ["x"],
  },
  { name: "controlRow", sel: '[data-anchor="control-row"]', top: 24, height: 16, fields: ["x", "width"] },
  { name: "resultTable", sel: '[data-anchor="result-table"]', top: 24, fields: ["x", "width"] },
];

async function boxOf(page: Page, sel: string) {
  const b = await page.locator(sel).first().boundingBox();
  expect(b, `${sel} 未渲染`).not.toBeNull();
  return b!;
}

test.describe("V3-A.1 历史验证首屏层级", () => {
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
    expect(await dist.innerText()).toMatch(/不可用/);
    // 卡头图标本身就是内联 SVG，所以只查卡体里有没有图：没有 ECharts 容器、没有绘图 SVG
    await expect(dist.locator(".smp-card-body svg")).toHaveCount(0);
    await expect(dist.locator(".smp-card-body canvas")).toHaveCount(0);
    // 也不得由高斯密度拼一个"看起来像真实样本"的示意分箱冒充：
    // 判据是**有没有画出图**（上面两条 svg/canvas 计数），不是有没有出现相关字样 ——
    // 卡面上的不可用说明本身就要写出"为什么不用高斯密度生成"，那是披露文字。
    expect(await dist.innerText()).toMatch(/事件研究接口只回传|没有逐样本收益序列/);

    // 年度稳定性与牛熊分组没有对应产出 ⇒ 不可用，且同样不得画图
    for (const id of ["control-yearly", "control-regime"]) {
      const card = page.getByTestId(id);
      await expect(card).toBeVisible();
      expect(await card.innerText()).toMatch(/不可用|未计算/);
      await expect(card.locator(".smp-card-body svg")).toHaveCount(0);
      await expect(card.locator(".smp-card-body canvas")).toHaveCount(0);
    }
  });

  test("首屏顺序：研究条件 → 统计指标 → 图表行 → 对照行 → 明细", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    const top = async (sel: string) => (await boxOf(page, sel)).y;
    const status = await top('[data-testid="research-status-card"]');
    const stats = await top('[data-testid="stats-summary"]');
    const chart = await top('[data-anchor="primary-chart"]');
    const horizon = await top('[data-testid="horizon-comparison"]');
    const control = await top('[data-anchor="control-row"]');
    const detail = await top('[data-testid="backtest-detail"]');

    expect(status).toBeLessThan(stats);
    expect(stats).toBeLessThan(chart);
    // 收益分布与持有期对比同一行（参考图 05 是两栏 708:715）
    expect(Math.abs(chart - horizon), "两卡不在同一行").toBeLessThanOrEqual(2);
    expect(chart).toBeLessThan(control);
    expect(control).toBeLessThan(detail);
  });

  test("几何锚点必须落进本轮目标容差（V3-A 的两条例外已删除）", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    for (const c of GEO) {
      const ref = await referenceAnchor(PAGE, c.name);
      const b = await boxOf(page, c.sel);
      if (typeof ref.y === "number" && c.top !== undefined) {
        expect(
          Math.abs(b.y - ref.y),
          `${c.name}.top：candidate ${b.y.toFixed(1)} vs reference ${ref.y} 超出 ±${c.top}`,
        ).toBeLessThanOrEqual(c.top);
      }
      if (typeof ref.height === "number" && (c.height !== undefined || c.heightPlus !== undefined)) {
        const d = b.height - ref.height;
        if (c.height !== undefined) {
          expect(
            Math.abs(d),
            `${c.name}.height：candidate ${b.height.toFixed(1)} vs reference ${ref.height} 超出 ±${c.height}`,
          ).toBeLessThanOrEqual(c.height);
        } else {
          const limit = c.heightPlus!;
          expect(
            d,
            `${c.name}.height：candidate ${b.height.toFixed(1)} vs reference ${ref.height} 偏差 ${d.toFixed(1)}px，超出 +${limit}`,
          ).toBeLessThanOrEqual(limit);
          if (c.heightMinus !== undefined) {
            expect(
              d,
              `${c.name}.height：candidate ${b.height.toFixed(1)} vs reference ${ref.height} 偏差 ${d.toFixed(1)}px，低于下界 −${c.heightMinus}（整带被压扁）`,
            ).toBeGreaterThanOrEqual(-c.heightMinus);
          }
        }
      }
      for (const f of c.fields ?? []) {
        const rv = ref[f];
        if (typeof rv !== "number") continue;
        const cv = f === "x" ? b.x : b.width;
        expect(
          Math.abs(cv - rv),
          `${c.name}.${f}：candidate ${cv.toFixed(1)} vs reference ${rv} 超出 ±12px`,
        ).toBeLessThanOrEqual(12);
      }
    }
  });

  test("对照行内部结构：四张卡、同一行、近似等宽、顺序与参考一致", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    const cols = await referenceControlColumns(PAGE);
    expect(cols.length, "参考对照行不是四列").toBe(4);

    // 顺序按参考图：年度稳定性 → 牛/熊/震荡分组 → 随机对照 → 出生日期平移对照
    const ids = ["control-yearly", "control-regime", "control-random", "control-shift"];
    const boxes: { id: string; x: number; y: number; width: number; height: number }[] = [];
    for (const id of ids) {
      const el = page.getByTestId(id);
      await expect(el).toBeVisible();
      const b = await el.boundingBox();
      expect(b, `${id} 未渲染`).not.toBeNull();
      boxes.push({ id, ...b! });
    }

    const row = await boxOf(page, '[data-anchor="control-row"]');
    for (const b of boxes) {
      // XL 1672 下四张卡必须在同一行
      expect(Math.abs(b.y - row.y), `${b.id} 与对照行顶边不同行`).toBeLessThanOrEqual(2);
      expect(b.y + b.height).toBeLessThanOrEqual(row.y + row.height + 2);
    }
    // 从左到右的顺序与参考一致
    for (let i = 1; i < boxes.length; i++) {
      expect(boxes[i].x, `${boxes[i].id} 排到了 ${boxes[i - 1].id} 左边`).toBeGreaterThan(
        boxes[i - 1].x,
      );
    }
    // 近似等宽：参考四列 340..366（极差 26px），candidate 必须同样接近等宽
    const widths = boxes.map((b) => b.width);
    expect(
      Math.max(...widths) - Math.min(...widths),
      `四列宽度极差过大：${widths.map((w) => w.toFixed(0)).join("/")}`,
    ).toBeLessThanOrEqual(20);
    // 列边界与参考逐列对齐（±20px：参考自身四列不等宽，不给假精度）
    for (let i = 0; i < cols.length; i++) {
      expect(
        Math.abs(boxes[i].x - cols[i].x),
        `第 ${i + 1} 列（${cols[i].title}）左边界 ${boxes[i].x.toFixed(0)} vs 参考 ${cols[i].x}`,
      ).toBeLessThanOrEqual(20);
      expect(
        Math.abs(boxes[i].width - cols[i].width),
        `第 ${i + 1} 列（${cols[i].title}）宽度 ${boxes[i].width.toFixed(0)} vs 参考 ${cols[i].width}`,
      ).toBeLessThanOrEqual(20);
    }
    // 列间距稳定且为正（不得互相压叠）
    for (let i = 1; i < boxes.length; i++) {
      const gap = boxes[i].x - (boxes[i - 1].x + boxes[i - 1].width);
      expect(gap, `第 ${i} 与第 ${i + 1} 列之间没有稳定间距`).toBeGreaterThanOrEqual(4);
      expect(gap).toBeLessThanOrEqual(20);
    }
  });

  test("对照行只映射真实字段：不可用列不得出现伪造数字，可用列必须给真实判决", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });

    // 没有产出的两列：不得出现任何百分比/Jaccard 数字
    for (const id of ["control-yearly", "control-regime"]) {
      const text = await page.getByTestId(id).innerText();
      expect(text, `${id} 用「不可用/未计算」以外的方式装了数字`).toMatch(/不可用|未计算/);
      expect(text, `${id} 出现了伪造的百分比`).not.toMatch(/\d+(\.\d+)?%/);
      expect(text, `${id} 出现了伪造的 Jaccard`).not.toMatch(/Jaccard\s*0\.\d/);
    }

    // 有产出的两列：逐 variant 取真实 status / Jaccard / verdict（本页不重算）
    const random = page.getByTestId("control-random");
    await expect(random.getByTestId("control-random-random_birth_date")).toBeVisible();
    await expect(random.getByTestId("control-random-random_factor")).toBeVisible();
    const shift = page.getByTestId("control-shift");
    await expect(shift.getByTestId("control-shift-shift_plus_7d")).toBeVisible();
    await expect(shift.getByTestId("control-shift-shift_minus_7d")).toBeVisible();
    // 演示样本里这四组对照的 Jaccard 都 > 0.9 ⇒ 必须判为对照失效，且不许藏起来
    const jaccard = await random.getByTestId("control-random-random_birth_date").innerText();
    expect(jaccard).toMatch(/J\s*0\.9\d\d/);
    await expect(page.getByTestId("invalid-control-warning")).toContainText("Jaccard");
    await expect(page.getByTestId("invalid-control-warning-shift")).toContainText("Jaccard");
    // 「随机对照」列不许出现平移 variant，反之亦然：字段映射不能串列
    expect(await random.innerText()).not.toMatch(/平移/);
    expect(await shift.innerText()).not.toMatch(/随机因子/);
  });

  test("研究纪律信息不因压缩而丢失", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    // 研究状态与数据源标记常驻
    await expect(page.getByTestId("data-source-chip")).toBeVisible();
    const statusText = await page.getByTestId("research-status-card").innerText();
    expect(statusText).toMatch(
      /NOT_RUN|NO_SIGNAL|WEAK_EVIDENCE|INCONCLUSIVE|INVALID_CONTROL|SUPPORTED/,
    );
    // 分区语义仍在（① / ② 标签可见），且 ① 不再单独占一条整宽横条
    await expect(page.getByTestId("section-deterministic")).toBeVisible();
    await expect(page.getByTestId("section-empirical")).toBeVisible();
    const rows = await page.locator('[data-testid="research-status-card"] > * > *').all();
    expect(rows.length, "研究条件卡内部不再是两行紧凑结构").toBeGreaterThanOrEqual(2);
    // ① 的规则强度信息一行读完：分数/不可用 + 方向，置信度进 details
    const strength = page.getByTestId("rule-strength");
    await expect(strength).toBeVisible();
    expect(await strength.innerText()).toMatch(/八字/);
    expect(await strength.innerText()).toMatch(/不可用|\/100/);
    await expect(page.getByTestId("rule-strength-detail")).toBeVisible();
    // 负对照与逐行判决仍在，且不做一句话汇总
    await expect(page.getByTestId("negative-control")).toContainText("负对照");
    await expect(page.getByTestId("horizon-table")).toBeVisible();
    // 口径解释折叠但不删除
    expect(statusText).toMatch(/NO_SIGNAL/);
  });

  test("统计九宫格在无数据时照排，且不以 0 冒充不可用", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    const tiles = page.locator('[data-anchor="summary-metrics"] > *');
    await expect(tiles).toHaveCount(9);
    const text = await page.getByTestId("stats-summary").innerText();
    // 九个槽位名一个都不能因为"没数据"而消失
    for (const label of [
      "样本数",
      "上涨率",
      "平均收益",
      "中位数收益",
      "超额收益",
      "最大回撤",
      "IC",
      "稳定性",
      "样本外表现",
    ]) {
      expect(text, `统计槽位 ${label} 消失了`).toContain(label);
    }
    // §2.4：没有数据只能显示 — / 未验证 / 不可用，不许填 0 或 0.00%
    expect(text).toMatch(/不可用/);
    expect(text).toMatch(/未验证/);
    expect(text).not.toMatch(/0\.00%/);
    // 警告是一行紧凑状态，详细解释在 details 里
    await expect(page.getByTestId("small-sample-warning")).toBeVisible();
    expect(await page.getByTestId("stats-summary-note").innerText()).toMatch(/不触发|不显示|不以 0/);
  });
});

test.describe("V3-A.1 历史验证 1440 首屏", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("持有期对比卡顶进入 900px 首屏，且无横向溢出、风险状态不丢", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    const horizon = page.getByTestId("horizon-comparison");
    await expect(horizon).toBeVisible();
    const hb = await horizon.boundingBox();
    expect(hb, "持有期对比卡未渲染").not.toBeNull();
    // 这是 V3-A 起的硬门：阈值沿用 viewport-1440-pages 的 900，未放宽
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

  test("1440 下研究状态、持有期图与四张对照卡都可见且内容未被裁切", async ({ page }) => {
    await page.goto(`/stock/600519/backtest${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    // 研究状态徽标在 1440 仍读得到原始状态码
    const badge = page.getByTestId("research-status-badge");
    await expect(badge).toBeVisible();
    expect(await badge.innerText()).toMatch(/研究状态/);

    // 持有期图本体（canvas/svg）必须真的画出来，而不是只剩卡壳
    const chart = page.getByTestId("horizon-comparison-chart");
    await expect(chart).toBeVisible();
    expect(
      await chart.locator("svg").count(),
      "1440 下持有期对比图没有渲染",
    ).toBeGreaterThan(0);

    // 四张对照卡：允许响应式换行，但每张卡的内容不许被裁掉
    const ids = ["control-yearly", "control-regime", "control-random", "control-shift"];
    for (const id of ids) {
      const el = page.getByTestId(id);
      await expect(el, `${id} 在 1440 不可见`).toBeVisible();
      const body = el.locator(".smp-card-body");
      const clipped = await body.evaluate((node) => node.scrollWidth - node.clientWidth);
      expect(clipped, `${id} 卡体内容横向被裁`).toBeLessThanOrEqual(2);
      const clippedY = await body.evaluate((node) => node.scrollHeight - node.clientHeight);
      expect(clippedY, `${id} 卡体内容纵向被裁`).toBeLessThanOrEqual(2);
    }
    // 对照行在 1440 仍然是四列（参考 viewport 是 1672，但 1440 不许塌成两列后丢卡）
    const row = await boxOf(page, '[data-anchor="control-row"]');
    const first = await page.getByTestId("control-yearly").boundingBox();
    const fourth = await page.getByTestId("control-shift").boundingBox();
    expect(first!.y, "对照卡与对照行顶边不同行").toBeLessThanOrEqual(row.y + 2);
    expect(fourth!.y, "第四张对照卡换行了").toBeLessThanOrEqual(row.y + 2);
    expect(fourth!.x + fourth!.width).toBeLessThanOrEqual(row.x + row.width + 2);
  });
});
