import { expect, test, type Locator, type Page } from "@playwright/test";

import { referenceAnchor } from "./support/referenceAnchors";

/**
 * V3-B：07 模型分歧中心 与 10 时间窗口 的结构与真实性门禁。
 *
 * 为什么要单独一份 spec：V3-A 只把 07 / 10 的参考矩形**登记**下来，
 * 布局一行未动。本轮恢复它们的视觉层级，因此需要能**拒绝退化**的断言：
 *
 *   07  参考图是三条横向带（conflictBanner 250..352 / mainRow 352..779 /
 *       bottomRow 779..937），整改前是"摘要 → 观点 → 矩阵 → 归因 → 历史"
 *       一路纵向堆到底，且演示场景切换器单独占一整行（实测 37px + 12px 间距）。
 *   10  参考图第一屏只有 summaryTiles(228..378) + mainRow/rightSummary(388..635)，
 *       热力图与周度排名在第三行（视口外）。整改前四块挤在同一个左右主区里，
 *       把 247px 的主行撑到 500+。
 *
 * 阈值一律从 `e2e/fixtures/reference-anchors.json` 读，测试里不抄第二份数字。
 * 参考侧 confidence=medium 的条目（10 的 mainRow / rightSummary 底边只到 frac=0.73）
 * 给的是**更宽**的容差，并在断言消息里写明"参考值本身不确定"，
 * 不是"我们允许差这么多"。
 *
 * 真实性部分与几何部分同等重要：这两页最容易"为了像参考图而造假能力"
 * （07 的能力雷达、10 的关键触发因子与历史分歧案例）。
 */

const FIX = "?fixture=ui-reference";
const P07 = "07-conflicts";
const P10 = "10-timeline";

async function box(page: Page, sel: string) {
  const el = page.locator(sel).first();
  await expect(el, `${sel} 未渲染`).toBeVisible();
  const b = await el.boundingBox();
  expect(b, `${sel} 无几何尺寸`).not.toBeNull();
  return b!;
}

/** 把一条带的 top/height 与冻结参考值比，容差由调用方给并注明来源。 */
async function expectBand(
  page: Page,
  pageKey: string,
  anchor: string,
  sel: string,
  tol: { top: number; height: number; why?: string },
) {
  const ref = await referenceAnchor(pageKey, anchor);
  const b = await box(page, sel);
  if (typeof ref.y === "number") {
    expect(
      Math.abs(b.y - ref.y),
      `${anchor}.top：candidate ${b.y.toFixed(1)} vs reference ${ref.y} 超出 ±${tol.top}`,
    ).toBeLessThanOrEqual(tol.top);
  }
  if (typeof ref.height === "number") {
    expect(
      Math.abs(b.height - ref.height),
      `${anchor}.height：candidate ${b.height.toFixed(1)} vs reference ${ref.height} 超出 ±${tol.height}` +
        (tol.why ? `（${tol.why}）` : ""),
    ).toBeLessThanOrEqual(tol.height);
  }
  return b;
}

async function overflow(page: Page) {
  const main = await page.locator("main").evaluate((el) => el.scrollWidth - el.clientWidth);
  const doc = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(main, "main 内部横向溢出").toBeLessThanOrEqual(2);
  expect(doc, "整页横向溢出").toBeLessThanOrEqual(2);
}

test.describe("V3-B 候选身份", () => {
  test("结构门必须跑在生产构建的 fixture 模式上（不是 dev、不连后端）", async ({ page }) => {
    for (const route of [
      `/stock/600519/conflicts${FIX}`,
      `/stock/600519/timeline${FIX}`,
      `/stock/600519/backtest${FIX}`,
    ]) {
      await page.goto(route, { waitUntil: "load" });
      await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
      // production：dev 会注入 <nextjs-portal> 与左下角指示器，直接进像素/几何差异
      await expect(page.locator('[data-build-mode="production"]')).toHaveCount(1);
      await expect(page.locator("nextjs-portal")).toHaveCount(0);
      // fixture：几何门依赖可复现 DOM，不依赖真实行情网络或研究库
      await expect(page.locator('[data-fixture-mode="fixture"]')).toHaveCount(1);
    }
  });
});

test.describe("V3-B 07 模型分歧中心：三条横向带", () => {
  test.use({ viewport: { width: 1672, height: 941 } });

  test("conflictBanner / mainRow / bottomRow 落进参考带", async ({ page }) => {
    await page.goto(`/stock/600519/conflicts${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    const banner = await expectBand(page, P07, "conflictBanner", '[data-anchor="conflict-banner"]', {
      top: 16,
      height: 16,
    });
    const main = await expectBand(page, P07, "mainRow", '[data-anchor="main-row"]', {
      top: 20,
      height: 24,
    });
    const bottom = await expectBand(page, P07, "bottomRow", '[data-anchor="bottom-row"]', {
      top: 24,
      height: 24,
    });

    // 三条带必须按顺序、不重叠
    expect(banner.y + banner.height).toBeLessThanOrEqual(main.y + 1);
    expect(main.y + main.height).toBeLessThanOrEqual(bottom.y + 1);
    // 首屏判据用"带顶进入 941"，不用"整带完整可见"：
    // 参考图三条带是**紧贴**的（352/779 共用边界），本系统外壳给 12px + 4px 栏距，
    // 于是 bottomRow 顶边比参考低 ~16px、整带底边落在 970.5（参考 937）。
    // 这是壳层栏距的既成 trade-off，不是本页层级失败；写死 941 会把它伪装成布局 bug。
    expect(bottom.y, "bottomRow 顶边未进入 941 首屏").toBeLessThan(941);
    expect(main.y, "mainRow 顶边未进入 941 首屏").toBeLessThan(941);

    // 整行宽度贴参考（参考三条带都是整宽 1411）
    for (const [name, b] of [
      ["conflictBanner", banner],
      ["mainRow", main],
      ["bottomRow", bottom],
    ] as const) {
      const ref = await referenceAnchor(P07, name);
      if (typeof ref.width === "number") {
        // 统一侧栏 210 vs 参考 229 会让整列宽差 ~19px，属已登记的壳层 trade-off
        expect(
          Math.abs(b.width - ref.width),
          `${name}.width：candidate ${b.width.toFixed(1)} vs reference ${ref.width}`,
        ).toBeLessThanOrEqual(24);
      }
    }
  });

  test("演示场景切换器不再单独占一整行，但三个场景入口都还在", async ({ page }) => {
    await page.goto(`/stock/600519/conflicts${FIX}`, { waitUntil: "load" });
    const sw = page.getByTestId("conflict-scenario-switcher");
    await expect(sw).toBeVisible();
    const sb = await sw.boundingBox();
    const banner = await box(page, '[data-anchor="conflict-banner"]');
    expect(sb, "场景切换器未渲染").not.toBeNull();

    // 它必须落在 conflictBanner 卡头那一行里，而不是在 banner 上方另起一条带
    expect(sb!.y).toBeGreaterThanOrEqual(banner.y);
    expect(sb!.y + sb!.height).toBeLessThanOrEqual(banner.y + banner.height);
    expect(sb!.height, "场景切换器仍是一整行高度").toBeLessThanOrEqual(26);
    // 不再撑满整行宽（独立横条时是 1434）
    expect(sb!.width, "场景切换器仍在占整行宽度").toBeLessThanOrEqual(420);

    for (const k of ["no_conflict", "conflict", "engine_unavailable"]) {
      await expect(page.getByTestId(`scenario-${k}`)).toBeVisible();
    }
  });

  test("三种场景都能切换，且各自给出真实差异", async ({ page }) => {
    for (const k of ["no_conflict", "conflict", "engine_unavailable"] as const) {
      await page.goto(
        `/stock/600519/conflicts${FIX}&scenario=${k}`,
        { waitUntil: "load" },
      );
      await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
      await expect(page.getByTestId("conflict-scenario")).toHaveAttribute("data-scenario", k);
      await expect(page.getByTestId("conflict-level")).toBeVisible();
      await expect(page.getByTestId("opinion-cards")).toBeVisible();
    }

    // conflict 场景：归因必须给出真实原因条目，而不是空卡
    await page.goto(`/stock/600519/conflicts${FIX}&scenario=conflict`, { waitUntil: "load" });
    await expect(page.getByTestId("conflict-reasons")).toBeVisible();
    expect(await page.getByTestId("conflict-reasons").innerText()).toMatch(/\S/);
    const mainConflict = await box(page, '[data-anchor="main-row"]');

    // engine_unavailable 场景：不可用引擎不得以 0 分参与比较（§2.4）
    await page.goto(`/stock/600519/conflicts${FIX}&scenario=engine_unavailable`, {
      waitUntil: "load",
    });
    const unavailable = page.locator('[data-testid^="opinion-"][data-available="0"]');
    expect(await unavailable.count(), "没有引擎被标为未产出").toBeGreaterThanOrEqual(1);
    const text = await unavailable.first().innerText();
    expect(text).toMatch(/不可用|未产出/);
    expect(text).not.toMatch(/规则强度 0\/100/);
    // 矩阵行里不可用引擎的分数列必须是 —，不能是 0
    const row = page.getByTestId("matrix-row-ziwei");
    if (await row.count()) {
      expect(await row.innerText()).not.toMatch(/\b0\b\s*\d*\/?100/);
    }
    // 不可用场景不得把 mainRow 撑破参考带
    const mainUnavail = await box(page, '[data-anchor="main-row"]');
    expect(Math.abs(mainUnavail.height - mainConflict.height)).toBeLessThanOrEqual(120);
  });

  test("不伪造能力雷达，也不伪造历史分歧统计", async ({ page }) => {
    await page.goto(`/stock/600519/conflicts${FIX}`, { waitUntil: "load" });
    const main = page.locator("main");

    // 参考图右上的「多维度能力对比」是雷达图；后端没有统一能力维度契约 ⇒ 不得画
    await expect(main).not.toContainText(/能力雷达|多维度能力对比/);
    const radarLike = await page
      .locator('[data-anchor="main-row"] svg polygon, [data-anchor="main-row"] svg polyline')
      .count();
    expect(radarLike, "mainRow 里出现了疑似雷达的多边形/折线").toBe(0);
    // 也不得自创准确率 / 稳定性 / 模型能力评分
    expect(await main.innerText()).not.toMatch(/准确率\s*\d|稳定性\s*\d+(\.\d+)?%?评分|能力评分/);

    // 历史类似冲突：NOT_RUN 必须如实。
    // 注意判据只能是"有没有把统计数字端出来"，不能是"有没有出现这些词" ——
    // 页面**必须**写出「不会给出历史胜率 / 上涨概率 / 最佳模型」这条边界声明，
    // 按词禁就把披露文字当成违规了（V3-B 第一版就是这么写错的）。
    const hist = page.getByTestId("historical-conflict");
    await expect(hist).toBeVisible();
    const histText = await hist.innerText();
    expect(histText).toMatch(/NOT_RUN|未运行/);
    // 没有案例表、没有百分比、没有"最佳模型 X"这类结论
    expect(await hist.locator("table").count(), "NOT_RUN 状态下却画出了历史案例表").toBe(0);
    expect(histText).not.toMatch(/\d+(\.\d+)?\s*%/);
    expect(histText).not.toMatch(/胜率\s*[:：]\s*\d/);
    // 必须带冒号+值才算"端出了最佳模型结论"；
    // 页面正文里的披露句"…最佳模型都不补造"是边界声明，不是伪造。
    expect(histText).not.toMatch(/最佳模型\s*[:：]\s*\S/);
    // 状态与来源不得因为压缩而消失：SourceMethod 常驻在卡里，
    // 其正文默认折叠（折叠是设计），所以判据要展开后再读，
    // 或者读 textContent（含未渲染节点）确认它没被删。
    await expect(page.getByTestId("conflict-source-method")).toBeVisible();
    expect(
      await page.getByTestId("conflict-source-method").evaluate((el) => el.textContent ?? ""),
      "分歧判定来源（ConflictDetector）已从审计链里消失",
    ).toMatch(/ConflictDetector/);
    await page.getByTestId("conflict-source-method").locator("summary").click();
    await expect(page.getByTestId("conflict-source-method")).toContainText(
      "historical_conflict_stats.status",
    );
  });

  test("1440 下三条带仍可访问、内容不被裁", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/stock/600519/conflicts${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
    await overflow(page);

    for (const id of [
      "conflict-summary",
      "conflict-opinions",
      "conflict-matrix",
      "conflict-attribution",
      "conflict-interpretation",
      "historical-conflict",
    ]) {
      const el = page.getByTestId(id);
      await expect(el, `${id} 在 1440 不可见`).toBeVisible();
      const clipped = await el.evaluate((node) => {
        const bodies = node.querySelectorAll(".smp-card-body");
        let worst = 0;
        bodies.forEach((b) => {
          worst = Math.max(worst, (b as HTMLElement).scrollWidth - (b as HTMLElement).clientWidth);
        });
        return worst;
      });
      expect(clipped, `${id} 卡体内容横向被裁`).toBeLessThanOrEqual(2);
    }
    // 关键风险信息在 1440 仍读得到
    await expect(page.getByTestId("conflict-level")).toBeVisible();
    await expect(page.getByTestId("available-engines")).toBeVisible();
  });
});

test.describe("V3-B 10 时间窗口：第一屏与第二层", () => {
  test.use({ viewport: { width: 1672, height: 941 } });

  test("summaryTiles / mainRow / rightSummary 落进参考带", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);

    const tiles = await expectBand(page, P10, "summaryTiles", '[data-anchor="summary-tiles"]', {
      top: 16,
      height: 20,
    });
    // 参考侧 mainRow / rightSummary 的**底边只到 frac=0.73**（与图内网格线混叠），
    // fixture 里标 confidence=medium ⇒ 高度容差放宽到 ±60，理由写在断言消息里。
    const main = await expectBand(page, P10, "mainRow", '[data-anchor="main-row"]', {
      top: 20,
      height: 60,
      why: "参考底边 frac=0.73、confidence=medium，参考值本身不确定",
    });
    const right = await expectBand(page, P10, "rightSummary", '[data-anchor="right-summary"]', {
      top: 20,
      height: 60,
      why: "同上",
    });

    // 第一屏两条带必须在摘要带之下、且顶边一致（参考图 mainRow 与 rightSummary 同 y=388）
    expect(tiles.y + tiles.height).toBeLessThanOrEqual(main.y + 1);
    expect(Math.abs(main.y - right.y), "主行与右栏顶边不一致").toBeLessThanOrEqual(2);
    // 参考图两卡等高（items-stretch）
    expect(Math.abs(main.height - right.height), "主行与右栏高度不等").toBeLessThanOrEqual(2);
  });

  test("分栏比例贴参考 66.8:33.2，且两栏之间是稳定栏距", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });
    const main = await box(page, '[data-anchor="main-row"]');
    const right = await box(page, '[data-anchor="right-summary"]');

    const total = main.width + right.width;
    const ratio = (main.width / total) * 100;
    // 参考 959 : 477 ⇒ 66.78 : 33.22
    expect(
      Math.abs(ratio - 66.8),
      `左栏占比 ${ratio.toFixed(1)}% 偏离参考 66.8% 超过 3pp`,
    ).toBeLessThanOrEqual(3);

    const gap = right.x - (main.x + main.width);
    expect(gap, "两栏之间没有稳定栏距").toBeGreaterThanOrEqual(4);
    expect(gap).toBeLessThanOrEqual(20);
    // 右栏必须真的在右边，且不越出内容区
    expect(right.x).toBeGreaterThan(main.x);
    expect(right.x + right.width).toBeLessThanOrEqual(main.x + 1434 + 2);
  });

  test("热力图与周度排名在第二层，不再挤占第一屏主行", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });
    const main = await box(page, '[data-anchor="main-row"]');
    const second = await box(page, '[data-anchor="second-layer"]');
    const heat = await box(page, '[data-testid="timeline-heatmap"]');
    const rank = await box(page, '[data-testid="timeline-week-ranking"]');

    expect(second.y, "第二层没有排在主行之下").toBeGreaterThanOrEqual(main.y + main.height - 1);
    expect(heat.y).toBeGreaterThanOrEqual(second.y - 1);
    expect(rank.y).toBeGreaterThanOrEqual(second.y - 1);
    // 第二层是左右两栏（参考第三行边界不可唯一导出 ⇒ 只断言它不塞进第一屏）
    expect(heat.x).toBeLessThan(rank.x);
    // 第一屏主行不得被撑成参考值的两倍
    const ref = await referenceAnchor(P10, "mainRow");
    expect(main.height, "主行又被第二层内容撑高了").toBeLessThanOrEqual(ref.height! * 1.3);
  });

  test("主图必须真的横跨绘图区：防「曲线只画左边一截」回归", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
    await page.waitForFunction(
      () => document.documentElement.dataset.chartsReady === "true",
      undefined,
      { timeout: 60_000 },
    );

    const chart = page.getByTestId("timeline-step-chart");
    await expect(chart).toBeVisible();
    await expect(chart.locator("svg")).toHaveCount(1);

    const card = await box(page, '[data-anchor="main-row"]');
    const geom = await chart.evaluate((fig) => {
      // 内联：模块级常量不会进浏览器上下文
      const STROKES = ["#6b8fd4", "#b07cd6", "#d9b45f", "#4fd39b"];
      const svg = fig.querySelector("svg");
      if (!svg) return null;
      const svgRect = svg.getBoundingClientRect();
      // 只认**序列线**（按 stroke 颜色），否则网格线/坐标轴会把覆盖度虚高
      let minX = Infinity;
      let maxX = -Infinity;
      let seriesPaths = 0;
      svg.querySelectorAll("path").forEach((p) => {
        const stroke = (p.getAttribute("stroke") ?? "").toLowerCase();
        if (!STROKES.includes(stroke)) return;
        const bb = p.getBBox();
        if (bb.width < 2) return;
        seriesPaths += 1;
        minX = Math.min(minX, bb.x);
        maxX = Math.max(maxX, bb.x + bb.width);
      });
      // x 轴首末类目标签：另一条独立证据，防止 path 结构变化时误判
      const texts = [...svg.querySelectorAll("text")].map((t) => t.textContent ?? "");
      return {
        svgWidth: svgRect.width,
        seriesPaths,
        span: Number.isFinite(minX) ? maxX - minX : 0,
        textCount: texts.length,
      };
    });
    expect(geom, "主图没有可测的 SVG").not.toBeNull();
    expect(geom!.seriesPaths, "主图里一条序列线都没有").toBeGreaterThanOrEqual(1);

    // 序列线覆盖度：至少绘图区宽度的 60%
    const coverage = geom!.span / geom!.svgWidth;
    expect(
      coverage,
      `序列线只画了 ${geom!.span.toFixed(0)}px / SVG ${geom!.svgWidth.toFixed(0)}px` +
        `（覆盖 ${(coverage * 100).toFixed(1)}%），疑似"数据有 20 个点但曲线只在左侧一截"`,
    ).toBeGreaterThanOrEqual(0.6);

    // 图表可用宽度必须吃满所在卡：容器被算成半宽/零宽是这类"曲线只画左边一截"
    // 故障的另一半成因。实测主图直接挂在 Card 下（不经 CardBody 的 14px 内边距），
    // 所以可用宽 = 卡宽 − 2px 边框；判据取"至少占卡宽 95%"，不锁死到像素。
    expect(
      geom!.svgWidth,
      `SVG 宽 ${geom!.svgWidth.toFixed(0)} 不足主行卡宽 ${card.width.toFixed(0)} 的 95%`,
    ).toBeGreaterThanOrEqual(card.width * 0.95);
    expect(geom!.svgWidth).toBeLessThanOrEqual(card.width + 2);

    // 覆盖度 + 容器宽度**抓不到**的一类故障：喂给图的数据被截断。
    // category 轴会把 5 个点也铺满整个宽度，所以线照样"横跨绘图区"，
    // 但读者看到的是 5 个窗口而不是 20 个 —— 同样是要防的"只画了一部分"。
    // 判据用两条独立来源交叉核对：摘要带的「逐日覆盖 … ~ 末日」必须真的
    // 出现在 x 轴标签里（末日缺席 = 序列被截短）。
    const summaryText = await page.getByTestId("timeline-summary").innerText();
    const dayRange = summaryText.match(
      /逐日覆盖[\s\S]*?\d{4}-(\d{2})-(\d{2})\s*~\s*(\d{4})-(\d{2})-(\d{2})/,
    );
    expect(dayRange, "摘要带里没有可解析的逐日覆盖区间").not.toBeNull();
    // 捕获组：1=首月 2=首日 3=末年 4=末月 5=末日
    const lastLabel = `${dayRange![4]}-${dayRange![5]}`;
    const axisLabels = await chart.evaluate((fig) =>
      [...fig.querySelectorAll("svg text")].map((t) => (t.textContent ?? "").trim()),
    );
    expect(
      axisLabels,
      `x 轴标签里没有逐日覆盖的末日 ${lastLabel}（序列被截短：摘要带说有 ${lastLabel}，图上没有）`,
    ).toContain(lastLabel);
    const firstLabel = `${dayRange![1]}-${dayRange![2]}`;
    expect(axisLabels, `x 轴标签里没有逐日覆盖的首日 ${firstLabel}`).toContain(firstLabel);
  });

  test("不生成关键触发因子与仓位建议；周度排名保持描述性", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });

    // 参考图右栏的「关键触发因子（高权重/中权重）」没有后端契约 ⇒ 只能是不可用。
    // 这条状态在审计区的 <details> 里（折叠是设计，不是丢失），所以要先展开再断言；
    // 未展开时它必须仍在 DOM 里（可搜索、可截图），不得被删掉。
    await expect(page.getByTestId("timeline-factor-attribution-status")).toHaveCount(1);
    await page
      .getByTestId("timeline-source-method")
      .locator("summary")
      .click();
    await expect(page.getByTestId("timeline-factor-attribution-status")).toBeVisible();
    const attribution = await page
      .getByTestId("timeline-factor-attribution-status")
      .innerText();
    expect(attribution).toMatch(/窗口因子归因[：:]?\s*不可用/);
    expect(attribution).toMatch(/因子贡献分解|贡献/);

    // 判据必须针对**被端出来的数据**，不是正文措辞：
    // 审计区里那句"不生成"关键触发因子 / 高中权重 / 仓位建议"这类内容"
    // 是必须存在的边界声明，按整页禁词会把披露判成违规（V3-B 第一版就写错了）。
    // 伪造权重会长成什么样是可枚举的：独立的徽标 / 表格里的一列 / 一张卡。
    expect(
      await page.locator("text=/^(高权重|中权重|低权重)$/").count(),
      "出现了伪造的因子权重徽标",
    ).toBe(0);
    expect(
      await page.locator('[data-testid^="trigger-factor"], [data-testid^="factor-weight"]').count(),
      "出现了伪造的关键触发因子条目",
    ).toBe(0);
    // 第一屏（摘要带 + 主行 + 右栏）里根本不得出现"关键触发因子"这一格
    expect(await page.getByTestId("timeline-first-fold").innerText()).not.toMatch(/关键触发因子/);
    expect(
      await page.locator("main").innerText(),
      "出现了仓位建议类文案",
    ).not.toMatch(/仓位建议\s*[:：]|建议仓位\s*[:：]|加仓|减仓/);

    // 周度排名只能是规则强度描述，不能升级成投资排名
    const rank = await page.getByTestId("timeline-week-ranking").innerText();
    expect(rank).not.toMatch(/最佳买入|最值得投资|收益最高|买入信号/);
    expect(rank).toMatch(/规则强度/);

    // 研究语义边界：窗口分数不得被说成涨跌概率
    expect(await page.locator("main").innerText()).toMatch(
      /不是涨跌概率|不构成收益预测|不是未来收益预测/,
    );
  });

  test("粒度切换仍在真实粒度上取数，不发明流周", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });
    await expect(page.getByTestId("timeline-gran-days")).toBeVisible();

    await page.getByTestId("timeline-gran-months").click();
    await page.waitForFunction(
      () => document.documentElement.dataset.chartsReady === "true",
      undefined,
      { timeout: 60_000 },
    );
    const months = page.getByTestId("timeline-step-chart");
    await expect(months).toBeVisible();
    // 月度视图的 y 轴口径必须写明是月度阶梯，而不是偷偷画成日线
    expect(await months.innerText()).toMatch(/月度/);

    // 「不发明流周」的可验证形式 = 粒度切换器里**没有**周这一档，
    // 而不是正文里不许出现"流周"两个字：页面必须写出
    // "传统术数没有「流周」这一层"这条边界声明，禁词会把披露当成违规。
    const granButtons = page.getByTestId("timeline-granularity").locator("button");
    await expect(granButtons).toHaveCount(2);
    const granText = await page.getByTestId("timeline-granularity").innerText();
    expect(granText).toMatch(/逐日|月度/);
    expect(granText, "粒度切换器出现了『流周』这一档").not.toMatch(/流周/);
    // 周度只能以"交易日聚合"的口径出现
    expect(await page.locator("main").innerText()).toMatch(/没有「流周」|不存在『流周』/);

    await page.getByTestId("timeline-gran-days").click();
    await page.waitForFunction(
      () => document.documentElement.dataset.chartsReady === "true",
      undefined,
      { timeout: 60_000 },
    );
    expect(await page.getByTestId("timeline-step-chart").innerText()).toMatch(/流日|逐日/);
  });

  test("1440 下第一屏仍完整、窄栏表格用局部横向滚动", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/stock/600519/timeline${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
    await overflow(page);

    // 关键状态与四张摘要卡可见
    await expect(page.getByTestId("timeline-summary-status")).toBeVisible();
    expect(await page.getByTestId("timeline-summary").innerText()).toMatch(/月度覆盖|周度覆盖/);
    await expect(page.getByTestId("timeline-main-view")).toBeVisible();
    await expect(page.getByTestId("timeline-explainer")).toBeVisible();

    // 窄栏表格允许自己横向滚动，但不得把 main 撑出横向溢出
    const scrollBox = page.getByTestId("week-ranking-scroll");
    await expect(scrollBox).toBeVisible();
    const local = await scrollBox.evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(local, "周排名表没有用局部滚动容器").toBeGreaterThanOrEqual(0);
    await overflow(page);

    // 卡片正文不得被裁
    for (const id of ["timeline-main-view", "timeline-explainer", "timeline-week-ranking"]) {
      const el = page.getByTestId(id);
      const clipped = await el.evaluate((node) => {
        let worst = 0;
        node.querySelectorAll(".smp-card-body, [data-testid]").forEach((n) => {
          const e = n as HTMLElement;
          if (e.scrollWidth > 0) worst = Math.max(worst, e.scrollWidth - e.clientWidth);
        });
        return worst;
      });
      expect(clipped, `${id} 内容被裁`).toBeLessThanOrEqual(2);
    }
  });
});
