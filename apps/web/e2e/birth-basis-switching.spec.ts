import { expect, test } from "@playwright/test";

/**
 * 出生模型切换（研究假设切换）的闭环验收。
 *
 * 为什么它不是"显示选项"：股票的出生时刻是**研究假设**。换基准 → 出生时刻变 →
 * 四柱与紫微盘面变 → 三个模型分数变。因此断言必须落在"结果确实变了"，
 * 只断言"按钮可点/URL 变了"等于没验证。
 *
 * 两条模式分别验证：
 *  * 演示模式（fixture）：样本冻结在默认基准上 → 换基准必须**显式拒绝**，
 *    不得用冻结样本冒充另一种假设；
 *  * 真实模式：换基准 → 真实重新分析（后端 `birth_basis`），
 *    且 `ipo_date` 的 C 级数据质量必须在界面上可见。
 */

const FIX = "?fixture=ui-reference";

test.describe("出生模型切换（演示模式）", () => {
  test("可切换基准可见、不可用基准禁用且给出原因", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();

    await page.getByTestId("context-details-toggle").first().click();
    const switcher = page.getByTestId("birth-model-switcher").first();
    await expect(switcher).toBeVisible();

    // 可用：listing_open / ipo_date
    await expect(page.getByTestId("birth-basis-listing_open")).toBeEnabled();
    await expect(page.getByTestId("birth-basis-ipo_date")).toBeEnabled();

    // 不可用：缺数据源的两种，必须禁用且 title 里说明原因
    for (const b of ["company_foundation", "first_trade"]) {
      const btn = page.getByTestId(`birth-basis-${b}`);
      await expect(btn).toBeVisible();
      await expect(btn).toBeDisabled();
      await expect(btn).toHaveAttribute("data-available", "0");
      const title = await btn.getAttribute("title");
      expect(title, `${b} 的不可用原因必须可读`).toContain("尚未接入");
    }
  });

  test("演示模式下切换基准：显式拒绝而不是拿冻结样本冒充", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await page.getByTestId("context-details-toggle").first().click();
    await page.getByTestId("birth-basis-ipo_date").click();

    // 必须出现"演示模式不提供该出生模型"的说明卡与回到默认基准的入口
    const card = page.getByTestId("fixture-basis-unsupported").first();
    await expect(card).toBeVisible();
    await expect(card).toContainText("上市首日正式开盘");
    await expect(page.getByTestId("reset-birth-basis-btn")).toBeVisible();
    // 不得继续展示 ipo_date 下的"结果"（那会是拿 listing_open 的盘冒充）
    await expect(page.locator("main")).not.toContainText("1682.30");
  });
});

test.describe("出生模型切换（真实模式）", () => {
  test.skip(process.env.SMP_E2E_LIVE_API !== "1", "需要 SMP_E2E_LIVE_API=1 与隔离后端");

  const REAL_BASE = process.env.SMP_E2E_REAL_BASE ?? "http://127.0.0.1:3111";

  test("切换基准 → 真实重新分析，出生时刻与盘面随之改变", async ({ page }) => {
    const apiCalls: { url: string; method: string; body: string }[] = [];
    page.on("request", (r) => {
      if (/\/analysis\/multi/.test(r.url())) {
        apiCalls.push({ url: r.url(), method: r.method(), body: r.postData() ?? "" });
      }
    });

    await page.goto(`${REAL_BASE}/stock/600519/overview`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    await page.getByTestId("context-details-toggle").first().click();

    // 默认基准：上市首日正式开盘 09:30，质量 A
    await expect(page.getByTestId("context-birth-fields")).toContainText("上市首日正式开盘");
    await expect(page.getByTestId("context-birth-fields")).toContainText("09:30");
    await expect(page.getByTestId("birth-basis-quality-note")).toHaveCount(0);

    // 切到 ipo_date
    await page.getByTestId("birth-basis-ipo_date").click();
    await expect(page).toHaveURL(/birthBasis=ipo_date/);

    // 请求体必须真的带上 birth_basis（而不是前端自行换算）
    await expect
      .poll(() => apiCalls.some((c) => c.body.includes('"birth_basis":"ipo_date"')), {
        timeout: 60_000,
      })
      .toBe(true);

    // 结果必须变：出生时刻从 09:30 变到 00:00
    await expect(page.getByTestId("context-birth-fields")).toContainText("00:00", {
      timeout: 60_000,
    });
    // C 级数据质量必须可见（ipo_date 以上市日近似发行日）
    const note = page.getByTestId("birth-basis-quality-note");
    await expect(note).toBeVisible();
    await expect(note).toContainText("C");
    await expect(note).toContainText("不得作为正式研究结论");
  });

  test("切回默认基准后结果恢复，且两次结果可区分", async ({ page }) => {
    await page.goto(`${REAL_BASE}/stock/600519/ziwei?birthBasis=ipo_date`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached({ timeout: 60_000 });
    const ipoIdentity = await page.getByTestId("ziwei-center-identity").first().innerText();

    await page.getByTestId("context-details-toggle").first().click();
    await page.getByTestId("birth-basis-listing_open").click();
    await expect(page).toHaveURL(/birthBasis=listing_open/);
    await expect
      .poll(async () => await page.getByTestId("ziwei-center-identity").first().innerText(), {
        timeout: 60_000,
      })
      .not.toBe(ipoIdentity);

    // 默认基准下不显示质量降级说明
    await expect(page.getByTestId("birth-basis-quality-note")).toHaveCount(0);
  });
});

test.describe("研究窗口（登记）切换", () => {
  test("演示模式：窗口可切换，并写明「不改变分数」的语义", async ({ page }) => {
    await page.goto(`/stock/600519/overview${FIX}`, { waitUntil: "load" });
    await expect(page.locator('[data-app-ready="true"]')).toBeAttached();
    await page.getByTestId("context-details-toggle").first().click();

    const sw = page.getByTestId("horizon-switcher").first();
    await expect(sw).toBeVisible();
    await expect(sw).toContainText("不改变");
    await expect(page.getByTestId("horizon-20d")).toHaveAttribute("aria-pressed", "true");

    await page.getByTestId("horizon-60d").click();
    await expect(page).toHaveURL(/horizon=60d/);
    await expect(page.getByTestId("horizon-60d")).toHaveAttribute("aria-pressed", "true");
  });

  test("真实模式：窗口值被登记进 analysis_run 并回传", async ({ request }) => {
    test.skip(process.env.SMP_E2E_LIVE_API !== "1", "需要隔离后端");
    const res = await request.post("http://127.0.0.1:8101/api/v1/stocks/600519/analysis/multi", {
      headers: { "Content-Type": "application/json" },
      data: { variant_mode: "forward", horizon: "60d", persist: true },
    });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.horizon, "响应必须回传登记的窗口值").toBe("60d");

    // 与运行记录一致
    const run = await request.get(`http://127.0.0.1:8101/api/v1/analysis/${body.analysis_id}`);
    expect((await run.json()).horizon).toBe("60d");
  });

  test("真实模式：窗口切换不改变三个模型的分数（不是「预测周期」）", async ({ request }) => {
    test.skip(process.env.SMP_E2E_LIVE_API !== "1", "需要隔离后端");
    const call = async (horizon: string) => {
      const r = await request.post("http://127.0.0.1:8101/api/v1/stocks/600519/analysis/multi", {
        headers: { "Content-Type": "application/json" },
        data: { variant_mode: "forward", horizon, as_of: "2026-09-18T14:32:00", persist: false },
      });
      const j = await r.json();
      return Object.fromEntries(
        Object.entries(j.opinions ?? {}).map(([k, v]) => [k, (v as { score: number | null }).score]),
      );
    };
    const a = await call("20d");
    const b = await call("60d");
    expect(a, "同一基准日下换窗口标签不得改变分数（否则就是隐藏的计算口径变化）").toEqual(b);
  });
});
