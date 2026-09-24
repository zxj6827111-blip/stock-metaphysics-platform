import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

/**
 * UI Visual Parity R1 的反例验证。
 *
 * 这一份 spec 的每条用例都对应 `docs/UI_INDEPENDENT_REVIEW_2026-09-22.md` §六
 * 里的一条既有缺陷，或本轮 V0 引入的新契约。**它们必须能在缺陷回来时失败** ——
 * 既有测试全绿不代表这些点被覆盖过。
 */

const FIX = "?fixture=ui-reference";

/* ==========================================================================
   V0-1 / V0-2：截图确定性与页面身份
   ========================================================================== */

test.describe("视觉捕获确定性", () => {
  test("生产构建身份 + 图表就绪信号（不得只等 hydration）", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });

    // 正式候选必须是生产构建：dev 指示器与开发浮层不得进像素。
    await expect(page.locator('[data-build-mode="production"]')).toHaveCount(1);
    await expect(page.locator("nextjs-portal")).toHaveCount(0);

    // 图表必须有**明确**的完成信号，而不是"等一会儿"。
    const signal = page.locator("html[data-charts-ready]");
    await expect(signal).toHaveAttribute("data-charts-ready", "true", { timeout: 60_000 });
  });

  test("图表动画已关闭（研究终端不需要入场动画）", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator("html[data-charts-ready]")).toHaveAttribute(
      "data-charts-ready",
      "true",
      { timeout: 60_000 },
    );
    // 同一页面连续两次取图的 SVG 必须逐字节一致：动画没关就做不到。
    const shot = async () =>
      await page.locator('[data-testid="time-window-chart"] svg').first().evaluate((el) => el.outerHTML);
    const a = await shot();
    await page.waitForTimeout(600);
    expect(await shot()).toBe(a);
  });
});

/* ==========================================================================
   V0-B-1：强制重算必须失效**正确**的缓存键
   ========================================================================== */

test.describe("分析缓存身份", () => {
  test("invalidate 与 read 使用完全相同的 AnalysisKey", async () => {
    // 直接在模块层验证：这是唯一能区分"清掉了这条缓存"和"清掉了另一条"的观测点。
    const posts: { url: string; body: Record<string, unknown> }[] = [];
    (globalThis as { fetch?: unknown }).fetch = async (url: unknown, init?: { body?: string }) => {
      posts.push({ url: String(url), body: init?.body ? JSON.parse(init.body) : {} });
      return new Response(JSON.stringify({ analysis_id: `A${posts.length}`, stock: {}, birth_profile: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };

    const store = await import("../lib/analysisStore");
    const key = {
      code: "600519",
      // 与各研究页 `useAnalysis(code, "forward", …)` 一致
      variant: "forward" as const,
      birthBasis: "ipo_date" as const,
      horizon: "60d",
    };

    await store.loadMultiAnalysis(key);
    expect(posts.length, "首次读取必须发一次请求").toBe(1);

    // 反例守卫：清掉**别的**键，不能影响这一条
    store.invalidateAnalysis({ ...key, horizon: "20d" });
    await store.loadMultiAnalysis(key);
    expect(posts.length, "失效别的窗口不应触发重算（否则缓存形同虚设）").toBe(1);

    // 正例：用同一个键失效，必须真的重算
    store.invalidateAnalysis(key);
    await store.loadMultiAnalysis(key);
    expect(posts.length, "用完整键失效后必须重新发请求").toBe(2);

    // 请求体必须带上完整上下文，而不是只带 variant
    expect(posts[1].body.horizon).toBe("60d");
    expect(posts[1].body.birth_basis).toBe("ipo_date");
  });
});

/* ==========================================================================
   V0-B-2：分析上下文必须贯穿页面
   ========================================================================== */

test.describe("上下文贯穿", () => {
  test("侧栏跳转保留 birthBasis / horizon / asOf", async ({ page }) => {
    await page.goto(
      "/stock/600519/overview?birthBasis=ipo_date&horizon=60d&asOf=2024-11-15T14:32:00",
      { waitUntil: "load" },
    );
    await page.getByTestId("nav-bazi").click();
    await expect(page).toHaveURL(/birthBasis=ipo_date/);
    await expect(page).toHaveURL(/horizon=60d/);
    await expect(page).toHaveURL(/asOf=/);
  });

  test("withAnalysisContext：当前 URL 上下文覆盖链接里冻结的旧值", async () => {
    const mod = await import("../lib/analysisContext");

    // 决定性的那条：链接冻结了 20d，用户此刻在 URL 上选了 60d ⇒ 必须是 60d。
    // 反过来（链接优先）会让用户在 URL 上改的假设在跳转那一刻被静默撤销。
    expect(
      mod.withAnalysisContext("/stock/600519/bazi?horizon=20d", new URLSearchParams({ horizon: "60d" })),
    ).toBe("/stock/600519/bazi?horizon=60d");

    // 缺失的上下文照样补齐
    const params = new URLSearchParams({ fixture: "ui-reference", horizon: "60d" });
    expect(mod.withAnalysisContext("/stock/600519/bazi?fixture=ui-reference", params)).toBe(
      "/stock/600519/bazi?fixture=ui-reference&horizon=60d",
    );
  });

  test("withAnalysisContext：四项逐个覆盖，无关参数既不删也不改", async () => {
    const mod = await import("../lib/analysisContext");
    const current = new URLSearchParams({
      fixture: "ui-reference",
      birthBasis: "ipo_date",
      horizon: "60d",
      asOf: "2024-11-15T14:32:00",
    });
    const out = mod.withAnalysisContext(
      "/stock/600519/bazi?fixture=ui-reference&horizon=20d&birthBasis=listing_open&foo=bar",
      current,
    );
    const [path, query = ""] = out.split("?");
    const q = new URLSearchParams(query);

    expect(path).toBe("/stock/600519/bazi");
    // 三项旧值全部被当前上下文覆盖
    expect(q.get("horizon"), "链接冻结的 20d 必须被当前 60d 覆盖").toBe("60d");
    expect(q.get("birthBasis"), "链接冻结的出生模型必须被当前选择覆盖").toBe("ipo_date");
    expect(q.get("asOf")).toBe("2024-11-15T14:32:00");
    expect(q.get("fixture")).toBe("ui-reference");
    // 与分析上下文无关的参数原样保留
    expect(q.get("foo"), "不得顺手删掉目标链接里的无关参数").toBe("bar");

    // 当前 URL 上没有的那一项，链接自带的值必须留着（补齐≠清空）
    const partial = new URLSearchParams({ horizon: "60d" });
    const q2 = new URLSearchParams(
      mod.withAnalysisContext("/research/date-scan?date=2026-09-22&asOf=2020-01-01", partial).split("?")[1],
    );
    expect(q2.get("asOf")).toBe("2020-01-01");
    expect(q2.get("date")).toBe("2026-09-22");
    expect(q2.get("horizon")).toBe("60d");
    expect(q2.has("fixture"), "URL 上没有 fixture 就不该凭空造一个").toBe(false);
  });

  /**
   * 浏览器级反例：只测 helper 不够 —— 真实页面上渲染的 href 才是用户点到的东西。
   *
   * 夹具的 `detailHref` 冻结了 `horizon=20d`（见 lib/fixture.ts），
   * 当前 URL 是 60d：跳转落地后必须仍然是 60d。
   */
  test("浏览器级：从 overview?…&horizon=60d 点冻结详情链接，落地仍是 60d", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}&horizon=60d`, { waitUntil: "load" });
    await expect(page.locator('[data-testid="engine-detail-bazi"]')).toHaveCount(1);

    // href 本身就已经被当前上下文覆盖，不再是夹具里冻结的 20d
    const href = await page.getByTestId("engine-detail-bazi").getAttribute("href");
    expect(href, `渲染出的 href 未跟随当前上下文：${href}`).toMatch(/horizon=60d/);
    expect(href).not.toMatch(/horizon=20d/);

    await page.getByTestId("engine-detail-bazi").click();
    await expect(page).toHaveURL(/\/stock\/600519\/bazi/);
    await expect(page).toHaveURL(/horizon=60d/);
  });

  test("浏览器级：三项上下文一起穿过跳转", async ({ page }) => {
    await page.goto(
      `/stock/600519/overview${FIX}&horizon=60d&asOf=2024-11-15T14:32:00`,
      { waitUntil: "load" },
    );
    await page.getByTestId("engine-detail-huangli").click();
    await expect(page).toHaveURL(/\/stock\/600519\/huangli/);
    await expect(page).toHaveURL(/horizon=60d/);
    await expect(page).toHaveURL(/asOf=2024-11-15T14%3A32%3A00/);
    await expect(page).toHaveURL(/fixture=ui-reference/);
  });
});

/* ==========================================================================
   V0-B-3：研究窗口的显示 / 请求 / 导出必须是同一个值
   ========================================================================== */

test.describe("研究窗口一致性", () => {
  test("默认上下文：上下文栏显示的是分析结果里的窗口，不再是写死文案", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    const bar = page.getByTestId("stock-context-bar").first();
    await bar.getByTestId("context-details-toggle").click();
    // 冻结样本的 horizon 是 20d，页面必须显示 20 交易日（值来自 analysis.horizon）
    await expect(page.getByTestId("context-birth-fields")).toContainText("预测周期：20 交易日");
  });

  test("切换登记窗口：显示与导出身份跟着变，盘面不变", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    const score20 = await page.getByTestId("engine-score-bazi").first().innerText();

    await page.goto(`/stock/600519/overview${FIX}&horizon=60d`, { waitUntil: "load" });
    const bar = page.getByTestId("stock-context-bar").first();
    await bar.getByTestId("context-details-toggle").click();
    const fields = page.getByTestId("context-birth-fields");
    await expect(fields).toContainText("预测周期：60 交易日");
    expect(await fields.innerText()).not.toMatch(/20\s*交易日/);

    // horizon 只是登记标签：不得因此换一张盘
    expect(await page.getByTestId("engine-score-bazi").first().innerText()).toBe(score20);

    // 导出快照必须带上同一个窗口值
    const [jsonDl] = await Promise.all([
      page.waitForEvent("download"),
      (async () => {
        await page.getByTestId("export-report-btn").first().click();
        await page.getByTestId("export-json").click();
      })(),
    ]);
    const payload = JSON.parse(await readFile(await jsonDl.path()));
    expect(payload.horizon, "导出身份必须与页面显示、请求上下文一致").toBe("60d");
  });
});

/* ==========================================================================
   R1.1-4：数据质量卡不得硬编码"已核对"
   ========================================================================== */

test.describe("数据质量事实性", () => {
  /** 取某一项（label 精确匹配），拿不到就直接失败，避免静默通过。 */
  const item = (dq: { items: { label: string; value: string; state: string }[] }, label: string) => {
    const hit = dq.items.find((i) => i.label === label);
    expect(hit, `数据质量卡缺少项目「${label}」`).toBeDefined();
    return hit!;
  };

  test("缺证据的项必须显示未提供/未验证，而不是绿勾已验证", async () => {
    const { toDataQualityView } = await import("../lib/dataSource");

    // 最空的一份输入：后端什么也没回传
    const bare = toDataQualityView({});
    expect(item(bare, "出生档案推导").value).toBe("未提供");
    expect(item(bare, "出生档案推导").state).toBe("warn");
    expect(item(bare, "古籍来源完整性").value).toBe("未验证");
    expect(item(bare, "古籍来源完整性").state).toBe("warn");
    expect(item(bare, "术数引擎版本").value).toBe("未提供");
    expect(item(bare, "行情/资料完整性").state).not.toBe("ok");
    // 决定性反例：曾经这四项是硬编码的全绿勾。没有任何输入时不得全 ok。
    expect(bare.items.every((i) => i.state === "ok"), "无输入却全部 ok = 回到硬编码").toBe(false);

    // 有出生档案、但推导证据没落地（上市日/首个交易日都为空）
    const noProof = toDataQualityView({
      grade: "A",
      birthProfile: {
        evidence: { listing_date: null, first_trading_day: null },
        data_quality: { grade: "A", score: 0.95, notes: [] },
      } as never,
    });
    expect(item(noProof, "出生档案推导").value).toBe("未验证");
    expect(item(noProof, "出生档案推导").state).toBe("warn");
  });

  test("有依据时按后端等级与许可状态如实分级", async () => {
    const { toDataQualityView } = await import("../lib/dataSource");
    const bp = (grade: string) =>
      ({
        evidence: { listing_date: "2001-08-27", first_trading_day: "2001-08-27" },
        data_quality: { grade, score: 0.9, notes: [] },
      }) as never;

    expect(item(toDataQualityView({ grade: "A", birthProfile: bp("A") }), "出生档案推导").value).toBe(
      "来源确定",
    );
    // B 的官方语义是"完整但存在假设" —— 不得显示成已验证
    const b = item(toDataQualityView({ grade: "B", birthProfile: bp("B") }), "出生档案推导");
    expect(b.value).toBe("含假设");
    expect(b.state).toBe("warn");

    const lic = (license_status: string) => ({ license_status }) as never;
    const allClear = toDataQualityView({ evidenceItems: [lic("public_domain"), lic("verified")] });
    expect(item(allClear, "古籍来源完整性").value).toBe("公版原文 · 2 条");
    expect(item(allClear, "古籍来源完整性").state).toBe("ok");
    // 混进一条未核实 ⇒ 整项不能再说"公版原文"
    const mixed = toDataQualityView({ evidenceItems: [lic("public_domain"), lic("unknown")] });
    expect(item(mixed, "古籍来源完整性").value).toBe("含 1 条未核实");
    expect(item(mixed, "古籍来源完整性").state).toBe("warn");
    // "检索成功但零条"与"接口没成功"语义不同
    expect(item(toDataQualityView({ evidenceItems: [] }), "古籍来源完整性").value).toBe("无检索结果");
  });

  test("质量说明必须逐条保留：首条前置 + 其余可展开", async ({ page }) => {
    const { toDataQualityView } = await import("../lib/dataSource");
    const notes = ["行情来源降级", "存在未闭合的时区假设", "样本含退市标的"];
    const dq = toDataQualityView({ grade: "B", notes });
    expect(dq.riskNote).toBe(notes[0]);
    expect(dq.riskNotes, "riskNotes 必须携带全部说明，不得只留第一条").toEqual(notes);

    // 演示模式下同样不得静默丢失：卡里必须能展开出第二条
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    const risk = page.getByTestId("risk-summary");
    await expect(risk).toBeVisible();
    const more = page.getByTestId("risk-notes-more");
    await expect(more).toHaveCount(1);
    await more.locator("summary").click();
    await expect(more).toContainText("移除 URL 中的 fixture 参数");

    // 演示样本没有真实核对依据，卡面不得出现"已验证 / 公版原文 / 数据完整"式结论
    const card = page.getByTestId("data-quality-card");
    expect(await card.innerText()).toMatch(/未提供|未验证/);
    expect(await card.innerText()).not.toMatch(/已验证|公版原文 · |数据完整 · 来源可靠/);
  });
});

/* ==========================================================================
   V0-B-4：按钮外观必须有真实动作
   ========================================================================== */
test.describe("交互闭环", () => {
  test("综合研判页不再存在无动作的「查看详情」按钮", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });

    // 时间窗口 / 历史验证：现在是真链接，且带当前上下文
    const tw = page.getByTestId("time-window-open-link");
    await expect(tw).toHaveCount(1);
    expect(await tw.getAttribute("href")).toMatch(/\/stock\/600519\/timeline/);
    const bt = page.getByTestId("backtest-detail-link");
    await expect(bt).toHaveCount(1);
    expect(await bt.getAttribute("href")).toMatch(/\/stock\/600519\/backtest/);

    // 数据质量卡：没有目标就不该画出可点样式
    await expect(page.getByTestId("data-quality-card").locator("button")).toHaveCount(0);

    // 组件契约兜底：CardHeader 现在只在真有动作时渲染可点元素，
    // 且真动作一律带 data-testid。卡片头里出现无 testid 的按钮 = 契约被绕过。
    const unlabeled = await page
      .locator(".smp-card-header button")
      .evaluateAll((els) =>
        els.filter((el) => !el.getAttribute("data-testid")).map((el) => el.textContent ?? "(空)"),
      );
    expect(unlabeled, `卡片头里出现无动作标识的按钮：${unlabeled.join(", ")}`).toEqual([]);
  });
});

/* ==========================================================================
   V2-B：黄历首屏必须真的落在首屏内
   ========================================================================== */

test.describe("黄历首屏", () => {
  test.use({ viewport: { width: 1672, height: 941 } });

  test("日期网格与选中日详情都在 941px 内，且首屏看到两行日期卡", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toHaveCount(1);
    await expect(page.locator("html[data-charts-ready]")).toHaveAttribute("data-charts-ready", "true", {
      timeout: 60_000,
    });

    const mainBox = await page.locator("main").boundingBox();
    expect(mainBox).not.toBeNull();

    const grid = page.getByTestId("huangli-day-grid");
    await expect(grid).toBeVisible();
    const gridBox = await grid.boundingBox();
    expect(gridBox, "日期网格未渲染").not.toBeNull();
    expect(gridBox!.y + gridBox!.height, "20 交易日网格底边超出首屏").toBeLessThanOrEqual(941);

    // 两行日期卡：网格 10 列 ⇒ 前 20 张卡至少排 2 行，第 2 行也必须在首屏内
    const cards = page.locator('[data-testid^="huangli-day-"]');
    expect(await cards.count()).toBeGreaterThanOrEqual(20);
    const secondRowBottom = await cards.nth(11).evaluate((el) => {
      const r = el.getBoundingClientRect();
      return r.y + r.height;
    });
    expect(secondRowBottom, "第二行日期卡不在首屏内").toBeLessThanOrEqual(941);

    // 右栏：选中日详情 + 数据状态必须在首屏
    const selected = page.getByTestId("huangli-selected-card");
    await expect(selected).toBeInViewport();
    await expect(page.getByTestId("huangli-data-status")).toBeInViewport();
  });

  test("参考图里有、系统没有的东西一律标不可用，不得伪造", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIX}`, { waitUntil: "load" });

    // 时辰窗口：后端没有逐时辰产出 ⇒ 必须显式不可用
    await expect(page.getByTestId("huangli-hours-unavailable")).toContainText("不可用");

    // 参考图的「交易胜率 / 建议仓位 / 宜交易 / 忌追涨」都不得出现在页面上
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/建议仓位/);
    expect(body).not.toMatch(/交易胜率/);
    expect(body).not.toMatch(/宜交易/);
    expect(body).not.toMatch(/忌追涨/);
    // 通书只有吉/凶两级，不得凭空造出「平」
    expect(await page.getByTestId("huangli-class-2024-11-15").count()).toBeLessThanOrEqual(1);
  });

  test("fixture 与 live 不串数据", async ({ page }) => {
    await page.goto(`/stock/600519/huangli${FIX}`, { waitUntil: "load" });
    await expect(page.getByTestId("fixture-banner")).toBeVisible();
    expect(await page.locator('[data-fixture-mode]').getAttribute("data-fixture-mode")).toBe("fixture");
  });
});

/* ==========================================================================
   公共壳层几何（1672×941 验收尺寸）
   ========================================================================== */

test.describe("壳层几何", () => {
  test.use({ viewport: { width: 1672, height: 941 } });

  for (const [route, name] of [
    [`/stock/600519/overview${FIX}`, "综合研判"],
    [`/stock/600519/huangli${FIX}`, "黄历"],
  ] as const) {
    test(`${name}：顶栏/侧栏尺寸与无横向溢出`, async ({ page }) => {
      await page.goto(route, { waitUntil: "load" });
      await expect(page.locator('[data-anchor="topbar"]')).toHaveCount(1);
      await expect(page.locator('[data-anchor="sidebar"]')).toHaveCount(1);

      const topbar = await page.locator('[data-anchor="topbar"]').boundingBox();
      const sidebar = await page.locator('[data-anchor="sidebar"]').boundingBox();
      expect(topbar!.height, "顶栏高度应贴近参考图 60–68px").toBeLessThanOrEqual(70);
      expect(sidebar!.width, "侧栏宽度应贴近参考图 221–235px").toBeGreaterThanOrEqual(220);
      expect(sidebar!.width).toBeLessThanOrEqual(236);

      const main = page.locator("main");
      const overflow = await main.evaluate((el) => el.scrollWidth - el.clientWidth);
      expect(overflow, "main 内部横向溢出").toBeLessThanOrEqual(2);
      const docOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(docOverflow, "整页横向溢出").toBeLessThanOrEqual(2);
    });
  }
});
