import { expect, test, type Page } from "@playwright/test";

import type { ApiFortuneMonthCalendarResponse } from "../lib/researchV2";

const LIVE = process.env.SMP_E2E_STOCK_CALENDAR === "1";
const EVIDENCE_DIR = process.env.SMP_E2E_ARTIFACT_DIR;

test.describe("股票公历月、每日十神与首日阴阳真实数据闭环", () => {
  test.skip(!LIVE, "真实验收需启动本机 8100 API、3000 Web，并设置 SMP_E2E_STOCK_CALENDAR=1");
  test.describe.configure({ mode: "serial" });

  test("600519 与 002561 的 2026 年 9 月页面逐项对应真实 v2 API", async ({ page }) => {
    const first = await queryRealMonth(page, "600519");
    await assertMonthMatchesApi(page, first, "600519");
    expect(first.first_day_polarity.status).toBe("available");
    expect(first.first_day_polarity.first_day_yinyang).toBe("阳");
    expect(first.timeline?.stable_context?.luck_cycle_context.availability).toBe("available");
    expect(first.timeline?.stable_context?.luck_cycle_context.direction).toBe("REVERSE");
    expect(first.timeline?.stable_context?.luck_cycle_context.cycle_availability).toBe("available");
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText("user_authoritative_first_day_table");
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText("男命兼容参数（研究假设）");
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText(first.first_day_polarity.visible_at!);
    await expect(page.getByTestId("fortune-luck-cycle-periods").locator("tbody tr").first()).toBeVisible();
    await expect(page.locator('[data-testid="fortune-day-row"][data-date="2026-09-01"]')).toContainText("七杀");
    await expect(page.locator('[data-testid="fortune-month-yongshen"]')).toContainText(first.calendar!.natal.day_master);
    await captureEvidence(page, "600519");

    const second = await queryRealMonth(page, "002561");
    await assertMonthMatchesApi(page, second, "002561");
    expect(second.first_day_polarity.status).toBe("available");
    expect(second.first_day_polarity.first_day_yinyang).toBe("阴");
    expect(second.timeline?.stable_context?.luck_cycle_context.availability).toBe("available");
    expect(second.timeline?.stable_context?.luck_cycle_context.direction).toBe("FORWARD");
    expect(second.timeline?.stable_context?.luck_cycle_context.cycle_availability).toBe("available");
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText("女命兼容参数（研究假设）");
    await expect(page.locator('[data-testid="fortune-day-row"][data-date="2026-09-01"]')).toContainText("伤官");
    await captureEvidence(page, "002561");

    const expectedTradingDays = second.calendar!.days.filter((day) => day.is_trading_day === true).length;
    await page.getByTestId("fortune-month-display-filter").selectOption("trading");
    await expect(page.getByTestId("fortune-day-row")).toHaveCount(expectedTradingDays);

    await page.getByTestId("fortune-month-date-mode").selectOption("custom");
    await page.getByTestId("fortune-month-range-start").fill("2026-09-05");
    await page.getByTestId("fortune-month-range-end").fill("2026-09-06");
    const weekendResponse = page.waitForResponse((response) => isCalendarResponse(response, "002561") && response.ok());
    await page.getByTestId("fortune-month-run").click();
    const weekend = await (await weekendResponse).json() as ApiFortuneMonthCalendarResponse;
    expect(weekend.request.start_date).toBe("2026-09-05");
    expect(weekend.calendar?.natural_day_count).toBe(2);
    expect(weekend.calendar?.days).toHaveLength(2);
    await expect(page.getByTestId("fortune-day-empty")).toBeVisible();
  });

  test("首日阴阳缺失时只降级运限，月日十神仍使用本地出生档案", async ({ page }) => {
    const result = await queryRealMonth(page, "000003");
    await assertMonthMatchesApi(page, result, "000003");
    expect(result.first_day_polarity.status).toBe("unavailable");
    expect(result.timeline?.stable_context?.luck_cycle_context.availability).toBe("unavailable");
    expect(result.calendar?.days).toHaveLength(30);
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText("缺失");
    await expect(page.getByTestId("fortune-month-segment-row").first()).toBeVisible();
    await expect(page.getByTestId("fortune-day-row")).toHaveCount(30);
  });

  test("真实首日来源与交易日证据冲突时保留原值并禁用运限", async ({ page }) => {
    const result = await queryRealMonth(page, "600609");
    await assertMonthMatchesApi(page, result, "600609");
    expect(result.first_day_polarity.status).toBe("conflict");
    expect(result.first_day_polarity.first_day_yinyang).toBe("阳");
    expect(result.first_day_polarity.reason).toContain("非交易日");
    expect(result.timeline?.stable_context?.luck_cycle_context.availability).toBe("unavailable");
    expect(result.calendar?.days).toHaveLength(30);
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText("conflict / 运限 unavailable");
    await expect(page.getByTestId("fortune-polarity-reason")).toContainText("非交易日");
    await expect(page.getByTestId("fortune-day-row")).toHaveCount(30);
    await captureEvidence(page, "600609");
  });

  test("上游月历失败时页面明确报错，股票其它页面不被错误数据替代", async ({ page }) => {
    await page.route("**/api/v2/research/fortune/month-calendar", async (route) => {
      await route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({ error: {
          code: "UPSTREAM_UNAVAILABLE",
          message: "月历上游服务暂不可用",
          detail: "验收注入的月历上游故障",
          retryable: true,
        } }),
      });
    });
    await page.goto("/stock/600519/timeline", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("fortune-month-calendar-v2")).toBeVisible();
    await expect(page.getByTestId("fortune-month-error")).toContainText("月历上游服务暂不可用");
    await expect(page.getByTestId("fortune-month-error")).toContainText("重试本区");
    await expect(page.getByTestId("fortune-timeline-v2")).toBeAttached();
  });
});

async function queryRealMonth(page: Page, stockCode: string): Promise<ApiFortuneMonthCalendarResponse> {
  await page.goto(`/stock/${stockCode}/timeline`, { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("fortune-month-calendar-v2")).toBeVisible();
  // 先等页面自动加载的默认月份结束，避免把它的响应误认作按钮触发的月历查询。
  await expect(page.getByTestId("fortune-month-executed-query")).toBeVisible();
  await page.getByTestId("fortune-month-year").selectOption("2026");
  await page.getByTestId("fortune-month-month").selectOption("9");
  const response = page.waitForResponse((candidate) => isCalendarResponse(candidate, stockCode) && candidate.ok());
  await page.getByTestId("fortune-month-run").click();
  const result = await (await response).json() as ApiFortuneMonthCalendarResponse;
  await expect(page.getByTestId("fortune-day-row")).toHaveCount(30);
  return result;
}

async function assertMonthMatchesApi(
  page: Page,
  result: ApiFortuneMonthCalendarResponse,
  stockCode: string,
): Promise<void> {
  expect(result.stock_identity.symbol).toBe(stockCode);
  expect(result.request.start_date).toBe("2026-09-01");
  expect(result.request.end_date).toBe("2026-09-30");
  expect(result.calendar?.days).toHaveLength(30);
  await expect(page.getByTestId("fortune-month-executed-query")).toContainText(stockCode);
  await expect(page.getByTestId("fortune-month-executed-query")).toContainText("2026-09-01 ～ 2026-09-30");
  await expect(page.getByTestId("fortune-day-row")).toHaveCount(30);
  for (const day of result.calendar!.days) {
    const row = page.locator(`[data-testid="fortune-day-row"][data-date="${day.date}"]`);
    await expect(row).toContainText(day.stem_ten_god);
    await expect(row).toContainText(day.ganzhi.text ?? `${day.ganzhi.stem}${day.ganzhi.branch}`);
    for (const hidden of day.branch_hidden_stems) await expect(row).toContainText(`${hidden.stem}·${hidden.ten_god}`);
  }

  const segments = result.calendar!.months.filter((segment) => (
    segment.kind === "month" && segment.end_at.slice(0, 10) >= "2026-09-01" && segment.start_at.slice(0, 10) <= "2026-09-30"
  ));
  expect(segments.length).toBeGreaterThanOrEqual(2);
  const monthRows = page.getByTestId("fortune-month-segment-row");
  await expect(monthRows).toHaveCount(segments.length);
  for (const segment of segments) {
    const row = monthRows
      .filter({ hasText: segment.start_at.replace("T", " ") })
      .filter({ hasText: segment.end_at.replace("T", " ") });
    await expect(row).toContainText(segment.ganzhi.text ?? `${segment.ganzhi.stem}${segment.ganzhi.branch}`);
    await expect(row).toContainText(segment.stem_ten_god);
    await expect(row).toContainText(segment.next_boundary_jieqi);
  }
  await expect(page.getByTestId("fortune-month-yongshen")).toContainText(result.calendar!.natal.day_master);
  await expect(page.getByTestId("fortune-month-segments")).toContainText("不表示财富结果");
  const luck = result.timeline?.stable_context?.luck_cycle_context;
  if (luck) {
    await expect(page.getByTestId("fortune-first-day-polarity")).toContainText(
      `${result.first_day_polarity.status} / 运限 ${luck.availability}`,
    );
  }
}

function isCalendarResponse(
  response: { url(): string; request(): { method(): string; postDataJSON(): unknown } },
  stockCode: string,
): boolean {
  if (!response.url().includes("/api/v2/research/fortune/month-calendar") || response.request().method() !== "POST") return false;
  const body = response.request().postDataJSON() as { stock_code?: string } | null;
  return body?.stock_code === stockCode;
}

async function captureEvidence(page: Page, stockCode: string): Promise<void> {
  if (!EVIDENCE_DIR) return;
  const fs = await import("node:fs/promises");
  await fs.mkdir(EVIDENCE_DIR, { recursive: true });
  await page.getByTestId("fortune-first-day-polarity").screenshot({ path: `${EVIDENCE_DIR}/${stockCode}-polarity-luck-cycle.png` });
  await page.getByTestId("fortune-month-segment-table").screenshot({ path: `${EVIDENCE_DIR}/${stockCode}-month-segments.png` });
  await page.getByTestId("fortune-day-table").screenshot({ path: `${EVIDENCE_DIR}/${stockCode}-daily-ten-gods.png` });
}
