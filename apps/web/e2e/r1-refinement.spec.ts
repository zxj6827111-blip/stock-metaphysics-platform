import { expect, test } from "@playwright/test";

/**
 * R1 整改验收（docs/UI_REAUDIT_2026-09-21.md）。
 *
 * 为什么单独成文件：这一批问题在整页级断言下**看不见** ——
 * 上下文栏用内部横向滚动藏起按钮时，document 不会有横向滚动条；
 * isFixtureActive() 造成的 SSR/CSR 分支差异也不会让 DOM 断言失败
 * （React 会静默替换成客户端版本）。因此这里直接测：
 *   * 内部 scrollWidth 与按钮相对裁剪容器的边界；
 *   * **服务端 HTML** 与客户端 DOM 是否渲染同一分支；
 *   * 内部状态码是否仍以裸英文/裸标签出现在正文。
 */

const FIXTURE = "?fixture=ui-reference";

const VIEWPORTS = [
  { key: "1672x941", width: 1672, height: 941 },
  { key: "1440x900", width: 1440, height: 900 },
];

test.describe("R1-1 上下文栏：主要操作默认可见，不靠横向滚动", () => {
  for (const vp of VIEWPORTS) {
    test(`综合研判 ${vp.key}：容器内无横向溢出，重新计算与切换股票在可视区`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`/stock/600519/overview${FIXTURE}`, { waitUntil: "load" });

      const bar = page.getByTestId("stock-context-bar").first();
      await expect(bar).toBeVisible();

      // 1) 上下文栏本身不得横向溢出
      const own = await bar.evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      }));
      expect(
        own.scrollWidth,
        `上下文栏内部横向溢出 @ ${vp.key}（${own.scrollWidth} > ${own.clientWidth}）`,
      ).toBeLessThanOrEqual(own.clientWidth + 2);

      // 2) 栏内任何子元素都不得成为"横向滚动裁剪容器"
      const scrollContainers = await bar.evaluate((el) =>
        [...el.querySelectorAll("*")].filter((c) => {
          const s = getComputedStyle(c);
          const scrollable = s.overflowX === "auto" || s.overflowX === "scroll";
          return scrollable && c.scrollWidth > c.clientWidth + 2;
        }).length,
      );
      expect(scrollContainers, `上下文栏内存在横向滚动裁剪容器 @ ${vp.key}`).toBe(0);

      // 3) 主要操作按钮的边界必须落在容器内（不能只靠"自动点击会滚动到它"）
      const barBox = await bar.boundingBox();
      expect(barBox).not.toBeNull();
      for (const testId of ["switch-stock-btn", "recalculate"]) {
        const btn = page.getByTestId(testId).first();
        await expect(btn).toBeVisible();
        const b = await btn.boundingBox();
        expect(b).not.toBeNull();
        expect(b!.x, `${testId} 左缘越界`).toBeGreaterThanOrEqual(barBox!.x - 1);
        expect(b!.x + b!.width, `${testId} 右缘越界（被容器裁掉）`).toBeLessThanOrEqual(
          barBox!.x + barBox!.width + 1,
        );
        expect(b!.y + b!.height, `${testId} 下缘越界`).toBeLessThanOrEqual(
          barBox!.y + barBox!.height + 1,
        );
      }
    });
  }

  test("1440 下次要出生档案字段收进详情，且原始值不丢失", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/stock/600519/overview${FIXTURE}`, { waitUntil: "load" });

    const bar = page.getByTestId("stock-context-bar").first();
    const toggle = page.getByTestId("context-details-toggle").first();
    await expect(toggle).toBeVisible();

    // 默认收起：栏高保持紧凑（不因详情行撑高）
    const collapsed = await bar.boundingBox();
    expect(collapsed!.height).toBeLessThanOrEqual(60);

    // 展开后原始字段齐全（时区 / 预测周期 / 运限假设 / 可追溯推导）
    await toggle.click();
    const fields = page.getByTestId("context-birth-fields").first();
    await expect(fields).toBeVisible();
    await expect(fields).toContainText("listing_open");
    await expect(fields).toContainText("2001-08-27 09:30");
    await expect(fields).toContainText("Asia/Shanghai");
    await expect(fields).toContainText("20 交易日");
    await expect(fields).toContainText("不适用（股票无性别）");

    // 收起后高度恢复
    await toggle.click();
    await expect(page.getByTestId("context-birth-fields")).toHaveCount(0);
    const restored = await bar.boundingBox();
    expect(restored!.height).toBeLessThanOrEqual(60);
  });

  test("1672 与 1440 默认栏高都在既有标准内（<=82px）", async ({ page }) => {
    for (const vp of VIEWPORTS) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      for (const path of ["/stock/600519/overview", "/stock/600519/bazi"]) {
        await page.goto(`${path}${FIXTURE}`, { waitUntil: "load" });
        const bar = page.getByTestId("stock-context-bar").first();
        const box = await bar.boundingBox();
        expect(box, `${path} @ ${vp.key} 未渲染上下文栏`).not.toBeNull();
        expect(box!.height, `${path} @ ${vp.key} 上下文栏高 ${box!.height}px`).toBeLessThanOrEqual(82);
      }
    }
  });
});

test.describe("R1-2 非支持标的演示页：服务端与客户端同分支（无 hydration 差异）", () => {
  test("002008 huangli：服务端 HTML 已渲染隔离卡，客户端一致，零真实请求", async ({ page }) => {
    const errors: string[] = [];
    const apiCalls: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
    page.on("request", (r) => {
      if (r.url().includes("/api/")) apiCalls.push(`${r.method()} ${r.url()}`);
    });

    // 服务端渲染的 HTML 必须已经包含隔离提示（修复前服务端渲染的是"数据正常"分支）
    const serverHtml = await (await page.request.get(`/stock/002008/huangli${FIXTURE}`)).text();
    expect(
      serverHtml.includes("unsupported-fixture-error") || serverHtml.includes("演示模式受限"),
      "服务端 HTML 未渲染演示模式隔离分支 → 客户端必然发生 hydration 分支替换",
    ).toBe(true);

    await page.goto(`/stock/002008/huangli${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("unsupported-fixture-error")).toBeVisible();
    await expect(page.getByTestId("enter-real-mode-btn")).toBeVisible();
    await page.waitForTimeout(1200);

    expect(apiCalls, `演示模式不得发起真实后端请求：${apiCalls.join(" | ")}`).toHaveLength(0);
    const realErrors = errors.filter((e) => !/Failed to load resource/i.test(e));
    expect(realErrors, `控制台错误：${realErrors.join(" | ")}`).toHaveLength(0);
  });

  for (const path of [
    "/stock/600519/overview",
    "/stock/600519/bazi",
    "/stock/600519/conflicts",
    "/stock/600519/timeline",
    "/stock/600519/evidence",
  ]) {
    test(`${path} fixture 页无 console.error / pageerror / 真实请求`, async ({ page }) => {
      const errors: string[] = [];
      const apiCalls: string[] = [];
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(m.text());
      });
      page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
      page.on("request", (r) => {
        if (r.url().includes("/api/")) apiCalls.push(r.url());
      });

      await page.goto(`${path}${FIXTURE}`, { waitUntil: "load" });
      await page.waitForTimeout(1000);
      expect(apiCalls).toHaveLength(0);
      expect(errors, `控制台错误：${errors.join(" | ")}`).toHaveLength(0);
    });
  }

  test("演示模式的加载 / 重算 / 搜索 / 切换弹窗全程零真实请求", async ({ page }) => {
    const apiCalls: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/")) apiCalls.push(`${r.method()} ${r.url()}`);
    });

    await page.goto(`/stock/600519/overview${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();

    // 重算
    await page.getByTestId("recalculate").first().click();
    await page.waitForTimeout(700);

    // 搜索（顶栏入口，输入即触发本地目录建议）
    const search = page.getByTestId("stock-search-input").first();
    await search.click();
    await search.fill("600519");
    await page.waitForTimeout(700);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);

    // 切换股票弹窗（只做交互，不点跳转 —— 跳转会进入不带 fixture 的真实模式）
    await page.getByTestId("switch-stock-btn").first().click();
    await expect(page.getByTestId("stock-switch-modal")).toBeVisible();
    await page.waitForTimeout(500);

    expect(
      apiCalls,
      `演示模式（含重算/搜索/切换弹窗）不得发起真实请求：${apiCalls.join(" | ")}`,
    ).toHaveLength(0);
  });
});

test.describe("R1-2 公共展示：内部状态中文化，裸标签与裸码不进入正文", () => {
  test("模型分歧页：不出现未渲染的 <strong> 字样，冲突级别为中文", async ({ page }) => {
    await page.goto(`/stock/600519/conflicts${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();
    await page.waitForTimeout(400);
    const main = page.locator("main").first();
    const text = await main.innerText();

    expect(text, "正文出现未渲染的 <strong> 标签").not.toContain("<strong>");
    expect(text, "正文出现未渲染的 </strong> 标签").not.toContain("</strong>");

    const level = page.getByTestId("conflict-level").first();
    await expect(level).toContainText("无冲突");

    // 原始状态码仍可追溯（不丢信息），但不在正文裸露
    const source = page.getByTestId("conflict-source-method").first();
    await expect(source).toBeAttached();
    await expect(source).toContainText("historical_conflict_stats.status");
    await expect(level).not.toContainText("none");
  });

  test("时间窗口页：标题数量与覆盖范围来自实际返回，且区分当前周", async ({ page }) => {
    await page.goto(`/stock/600519/timeline${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();
    await page.waitForTimeout(400);
    const main = page.locator("main").first();

    // 固定演示数据是 4 个月 / 3 周，标题不得写死"12"
    await expect(main).toContainText("共 4 个月");
    await expect(main).toContainText("共 3 周");
    await expect(main).not.toContainText("未来 12 个月");
    await expect(main).not.toContainText("未来 12 周");

    // 分析基准日 2024-11-15 落在 2024-11-11~15 这一周内 → 「当前周」而非「下一周」
    await expect(main).toContainText("当前周（含分析基准日）");
    await expect(main).not.toContainText("下一周");
  });

  test("古籍证据页：演示语料身份清晰，不宣称真实引用", async ({ page }) => {
    await page.goto(`/stock/600519/evidence${FIXTURE}`, { waitUntil: "load" });
    await expect(page.getByTestId("page-title").first()).toBeVisible();
    await page.waitForTimeout(400);
    const main = page.locator("main").first();

    await expect(main).toContainText("演示语料");
    expect(
      (await main.innerText()).includes("真实 KnowledgeProvider 返回"),
      "演示模式不得声称数据来自真实知识库检索",
    ).toBe(false);

    const source = page.getByTestId("evidence-source-method").first();
    await expect(source).toBeAttached();
    await expect(source).toContainText("演示语料（fixture=ui-reference 固定样本");
  });

  test("页脚版本全局一致", async ({ page }) => {
    const seen = new Set<string>();
    for (const path of ["/", "/stock/600519/overview", "/factors"]) {
      await page.goto(`${path}${path.includes("?") ? "&" : FIXTURE}`, { waitUntil: "load" });
      const footer = page.getByTestId("footer-left").first();
      await expect(footer).toBeVisible();
      seen.add((await footer.innerText()).trim());
    }
    expect([...seen]).toHaveLength(1);
    expect([...seen][0]).toContain("股票玄学多模型研究平台");
  });
});

test.describe("R1-3 三页收口：首屏几何目标", () => {
  test("综合研判：历史摘要标题 y<=730，风险摘要 y<=820", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/overview${FIXTURE}`, { waitUntil: "load" });

    const title = page.locator('[data-testid="backtest-summary"] h2').first();
    await expect(title).toBeVisible();
    const tBox = await title.boundingBox();
    expect(tBox!.y, `历史摘要标题 y=${tBox!.y} > 730`).toBeLessThanOrEqual(730);

    const risk = page.getByTestId("risk-summary").first();
    await expect(risk).toBeVisible();
    const rBox = await risk.boundingBox();
    expect(rBox!.y, `风险摘要 y=${rBox!.y} > 820`).toBeLessThanOrEqual(820);

    // 首屏摘要必须同时含支持与反证（不能只切前 3 条利多）
    const evidence = page.getByTestId("key-evidence").first();
    await expect(evidence).toContainText("利多");
    await expect(evidence).toContainText("利空");
  });

  test("八字：正负因素 y<=720，古籍证据预览 y<=900", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/stock/600519/bazi${FIXTURE}`, { waitUntil: "load" });

    const pos = page.getByTestId("positive-factors").first();
    await expect(pos).toBeVisible();
    const pBox = await pos.boundingBox();
    expect(pBox!.y, `正负因素 y=${pBox!.y} > 720`).toBeLessThanOrEqual(720);

    const evidence = page.getByTestId("bazi-evidence").first();
    await expect(evidence).toBeVisible();
    const eBox = await evidence.boundingBox();
    expect(eBox!.y, `古籍证据 y=${eBox!.y} > 900`).toBeLessThanOrEqual(900);
  });

  test("首页：主内容与页脚自然占用大部分首屏，不靠缩小组件", async ({ page }) => {
    await page.setViewportSize({ width: 1672, height: 941 });
    await page.goto(`/${FIXTURE}`, { waitUntil: "load" });

    const title = page.getByTestId("home-title").first();
    const fontSize = await title.evaluate((el) => window.getComputedStyle(el).fontSize);
    expect(parseFloat(fontSize)).toBeGreaterThanOrEqual(48);

    const caps = page.getByTestId("capabilities").first();
    const cBox = await caps.boundingBox();
    // 能力卡必须占据足够的视觉重量（不是被压扁的细条）
    expect(cBox!.height, `平台能力卡高度 ${cBox!.height} < 150`).toBeGreaterThanOrEqual(150);

    // 页脚应落在首屏内（有滚动也必须在 941 附近，不留大片空白）
    const footer = page.locator("main footer").first();
    const fBox = await footer.boundingBox();
    expect(fBox, "页脚未渲染").not.toBeNull();
    expect(fBox!.y, `页脚 y=${fBox!.y}（下方留白过大）`).toBeLessThanOrEqual(941);
  });
});
