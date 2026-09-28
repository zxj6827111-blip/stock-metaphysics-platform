import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const DATASET_ID =
  process.env.NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID?.trim() ||
  "w4-engineering-002561-20120223-asof-v2";
const HORIZONS = [1, 5, 20] as const;

test("真实首页通过本机 API 区分行情截止日与未认证 W4 范围", async ({ page }) => {
  const versionsPromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v1/system/versions"),
  );
  const datasetPromise = page.waitForResponse((response) =>
    response.url().includes(`/api/backend/api/v2/research/datasets/${DATASET_ID}`),
  );

  await page.goto("/", { waitUntil: "load" });
  expect(new URL(page.url()).searchParams.has("fixture")).toBe(false);
  const [versionsResponse, datasetResponse] = await Promise.all([versionsPromise, datasetPromise]);
  expect(versionsResponse.status()).toBe(200);
  expect(datasetResponse.status()).toBe(200);
  const versions = await versionsResponse.json() as { market_data_cutoff_date: string };
  const dataset = await datasetResponse.json() as {
    dataset_id: string;
    row_count: number;
    research_eligible: boolean;
    confirmatory_research_eligible: boolean;
    metadata: { scope?: { research_dates?: string[] } };
  };
  const dates = [...(dataset.metadata.scope?.research_dates ?? [])].sort();
  expect(dates.length).toBeGreaterThan(0);

  const coverage = page.getByTestId("research-data-coverage");
  await expect(coverage).toContainText(versions.market_data_cutoff_date);
  await expect(coverage).toContainText(DATASET_ID);
  await expect(coverage).toContainText(`${dates[0]} ～ ${dates[dates.length - 1]}`);
  if (dataset.research_eligible) {
    await expect(coverage).toContainText("数据集可用于研究");
    await expect(coverage).toContainText("当前资格只适用于清单中的限域探索范围；不代表确认性研究资格。");
  } else {
    await expect(coverage).toContainText("数据集未认证");
    await expect(coverage).toContainText("行情快照截止日与历史数据集范围是两个独立口径");
  }
  expect(dataset.dataset_id).toBe(DATASET_ID);
  expect(dataset.row_count).toBeGreaterThan(0);
  expect(dataset.confirmatory_research_eligible).toBe(false);
});

test("真实历史页完成日期与单股 v2 查询，导出与 API 响应一致", async ({ page }) => {
  const datasetPromise = page.waitForResponse((response) =>
    response.url().includes(`/api/backend/api/v2/research/datasets/${DATASET_ID}`),
  );
  await page.goto("/research/history?scope_mode=dates&factor_id=B_DAY_005&activation=any", { waitUntil: "load" });
  expect(new URL(page.url()).searchParams.has("fixture")).toBe(false);
  const datasetResponse = await datasetPromise;
  expect(datasetResponse.status()).toBe(200);
  const dataset = await datasetResponse.json() as {
    dataset_digest: string;
    research_eligible: boolean;
    confirmatory_research_eligible: boolean;
    metadata: { scope?: { research_dates?: string[] } };
  };
  const dates = [...(dataset.metadata.scope?.research_dates ?? [])].sort();
  expect(dates.length).toBeGreaterThan(0);
  const dateFrom = dates[0];
  const dateTo = dates[Math.min(dates.length - 1, 250)];
  await expect(page.getByTestId("historical-date-from")).toHaveValue(dateFrom);
  await page.getByTestId("historical-date-from").fill(dateFrom);
  await page.getByTestId("historical-date-to").fill(dateTo);
  await expect(page.getByTestId("historical-study-controls")).toContainText(
    `研究资格：${dataset.research_eligible ? "可用" : "未认证"}`,
  );
  expect(dataset.confirmatory_research_eligible).toBe(false);

  const runAndRead = async (scopeMode: "dates" | "stock", factorId = "B_DAY_005") => {
    await page.getByTestId("historical-factor-id").fill(factorId);
    await page.getByTestId("historical-scope-mode").selectOption(scopeMode);
    if (scopeMode === "stock") {
      await page.getByTestId("historical-stock-code").fill("002561");
    }
    const responsePromises = HORIZONS.map((horizon) => page.waitForResponse((response) => {
      if (!response.url().includes("/api/backend/api/v2/research/event-study")) return false;
      const request = response.request().postDataJSON() as { horizon?: number; scope_mode?: string };
      return request.horizon === horizon && request.scope_mode === scopeMode;
    }));
    await page.getByTestId("historical-run").click();
    const responses = await Promise.all(responsePromises);
    const results = [];
    for (let index = 0; index < responses.length; index += 1) {
      const response = responses[index];
      expect(response.status()).toBe(200);
      const result = await response.json() as {
        scope_mode: string;
        horizon: number;
        dataset_digest: string;
        research_status: string;
        matched_observation_count: number;
        matched: { sample_count: number; mean_return: number | null };
      };
      expect(result).toMatchObject({
        scope_mode: scopeMode,
        horizon: HORIZONS[index],
        dataset_digest: dataset.dataset_digest,
      });
      expect(["EXPLORATORY_NOT_GATED", "INSUFFICIENT_SAMPLE"]).toContain(result.research_status);
      await expect(page.getByTestId(`historical-result-${result.horizon}`)).toContainText(result.research_status);
      results.push(result);
    }
    return results;
  };

  const dateResults = await runAndRead("dates");
  expect(dateResults.some((result) => result.matched_observation_count > 0)).toBe(true);
  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("historical-export-json").click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  if (!downloadPath) throw new Error("Playwright did not provide the completed report download path");
  const exported = JSON.parse(readFileSync(downloadPath, "utf8")) as {
    dataset: { dataset_digest: string };
    requests: Array<{ horizon: number; scope_mode: string }>;
    results: Array<{ horizon: number; dataset_digest: string; matched_observation_count: number }>;
  };
  expect(exported.dataset.dataset_digest).toBe(dataset.dataset_digest);
  expect(exported.requests).toHaveLength(3);
  expect(exported.requests.every((request) => request.scope_mode === "dates")).toBe(true);
  expect(exported.results).toHaveLength(dateResults.length);
  expect(exported.results).toEqual(dateResults.map((result) => expect.objectContaining({
    horizon: result.horizon,
    dataset_digest: result.dataset_digest,
    matched_observation_count: result.matched_observation_count,
  })));

  const stockResults = await runAndRead("stock");
  expect(stockResults.some((result) => result.matched_observation_count > 0)).toBe(true);

  const noMatchResults = await runAndRead("dates", "W8_NO_MATCH_FACTOR_PROBE");
  expect(noMatchResults.every((result) => result.matched_observation_count === 0)).toBe(true);
  expect(noMatchResults.every((result) => result.research_status === "INSUFFICIENT_SAMPLE")).toBe(true);

  await page.route("**/api/backend/api/v2/research/event-study", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "W8 simulated upstream unavailable" }) }),
  );
  const failedResponses = HORIZONS.map((horizon) => page.waitForResponse((response) => {
    if (!response.url().includes("/api/backend/api/v2/research/event-study") || response.status() !== 503) return false;
    const request = response.request().postDataJSON() as { horizon?: number };
    return request.horizon === horizon;
  }));
  await page.getByTestId("historical-factor-id").fill("B_DAY_005");
  await page.getByTestId("historical-run").click();
  const failures = await Promise.all(failedResponses);
  expect(failures).toHaveLength(3);
  for (const horizon of HORIZONS) {
    await expect(page.getByTestId(`historical-error-${horizon}`)).toBeVisible();
  }
  await page.unroute("**/api/backend/api/v2/research/event-study");
});

test("真实未来日期扫描只呈现关系并提供独立的 W4 历史验证入口", async ({ page }) => {
  test.setTimeout(180_000);
  const targetDate = "2026-09-29";
  const catalogPromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v1/research/relation-catalog"),
  );
  const scanPromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v1/research/date-scan") && response.request().method() === "POST",
  );
  await page.goto(`/research/date-scan?date=${targetDate}`, { waitUntil: "load" });
  expect(new URL(page.url()).searchParams.has("fixture")).toBe(false);
  const [catalogResponse, scanResponse] = await Promise.all([catalogPromise, scanPromise]);
  expect(catalogResponse.status()).toBe(200);
  expect(scanResponse.status()).toBe(200);
  const scan = await scanResponse.json() as {
    target_date: string;
    stock_total: number;
    relation_type_counts: Record<string, number>;
    query: { date: string };
  };
  expect(scan.target_date).toBe(targetDate);
  expect(scan.query.date).toBe(targetDate);
  expect(scan.stock_total).toBeGreaterThan(0);

  const relation = (["六合", "六冲", "相害"] as const).find((item) => (scan.relation_type_counts[item] ?? 0) > 0);
  if (!relation) throw new Error("实际全市场扫描没有命中 W7 已登记的三种历史因子映射关系");
  const relationResponsePromise = page.waitForResponse((response) => {
    if (!response.url().includes("/api/backend/api/v1/research/date-scan") || response.request().method() !== "POST") return false;
    const request = response.request().postDataJSON() as { relation_type?: string };
    return request.relation_type === relation;
  });
  await page.getByTestId(`relation-filter-${relation}`).click();
  const relationResponse = await relationResponsePromise;
  expect(relationResponse.status()).toBe(200);
  await expect(page.getByTestId("date-scan-date")).toHaveValue(targetDate);
  const studyLink = page.getByTestId("date-scan-v2-study-link");
  await expect(studyLink).toBeVisible();
  const href = await studyLink.getAttribute("href");
  if (!href) throw new Error("日期扫描没有生成 W4 历史研究入口");
  const params = new URL(href, "http://127.0.0.1").searchParams;
  const expectedFactor = { 六合: "B_DAY_003", 六冲: "B_DAY_002", 相害: "B_DAY_008" }[relation];
  expect(params.get("scope_mode")).toBe("dates");
  expect(params.get("date_from")).toBe(targetDate);
  expect(params.get("date_to")).toBe(targetDate);
  expect(params.get("relation_type")).toBe(relation);
  expect(params.get("factor_id")).toBe(expectedFactor);
});

test("真实实验室加载冻结 v2 报告，时间轴调用本机 Fortune 服务", async ({ page }) => {
  const experimentPromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v2/research/experiments/F5-EXP-001"),
  );
  await page.goto("/research/experiments", { waitUntil: "load" });
  const experimentResponse = await experimentPromise;
  expect(experimentResponse.status()).toBe(200);
  const experiment = await experimentResponse.json() as { report_digest: string; report: { research_status: string } };
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText(experiment.report_digest);
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText("EXPLORATORY_NOT_GATED");
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText("INSUFFICIENT_SAMPLE");
  expect(experiment.report.research_status).toBe("EXPLORATORY_NOT_GATED");

  if (DATASET_ID.includes("limited")) {
    const limitedReportId = "F5-EXP-001-002561-LIMITED-V1";
    const limitedReportPromise = page.waitForResponse((response) =>
      response.url().includes(`/api/backend/api/v2/research/experiments/${limitedReportId}`),
    );
    await page.getByTestId(`frozen-experiment-${limitedReportId}`).click();
    const limitedReportResponse = await limitedReportPromise;
    expect(limitedReportResponse.status()).toBe(200);
    const limitedReport = await limitedReportResponse.json() as {
      report_digest: string;
      report: {
        report_id: string;
        protocol_version: string;
        dataset: { dataset_id: string; research_eligible: boolean; confirmatory_research_eligible: boolean };
      };
    };
    expect(limitedReport.report.report_id).toBe(limitedReportId);
    expect(limitedReport.report.protocol_version).toBe("f5-preregistered-limited-v1");
    expect(limitedReport.report.dataset).toMatchObject({
      dataset_id: DATASET_ID,
      research_eligible: true,
      confirmatory_research_eligible: false,
    });
    await expect(page.getByTestId("frozen-experiment-detail")).toContainText(limitedReport.report_digest);
    await expect(page.getByTestId("frozen-experiment-detail")).toContainText(DATASET_ID);
    await expect(page.getByTestId("frozen-experiment-detail")).toContainText("INSUFFICIENT_SAMPLE");
  }

  const fortunePromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v2/research/fortune/timeline") && response.request().method() === "POST",
  );
  await page.goto("/stock/002561/timeline?as_of=2026-09-28", { waitUntil: "load" });
  const fortuneResponse = await fortunePromise;
  expect(fortuneResponse.status()).toBe(200);
  const fortune = await fortuneResponse.json() as { timeline: { availability: string; birth_context: { birth_time_precision: string; assumptions: Array<{ reason: string }> } } };
  expect(fortune.timeline.birth_context.birth_time_precision).toBe("INFERRED");
  await expect(page.getByTestId("fortune-birth-profile")).toContainText("INFERRED");
  await expect(page.getByTestId("fortune-assumptions")).toBeVisible();
});
