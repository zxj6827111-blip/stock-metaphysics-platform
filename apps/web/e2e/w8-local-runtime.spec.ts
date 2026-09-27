import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const DATASET_ID = "w4-engineering-002561-20120223-asof-v2";
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
  const dataset = await datasetResponse.json() as { dataset_id: string; row_count: number; research_eligible: boolean; confirmatory_research_eligible: boolean };

  const coverage = page.getByTestId("research-data-coverage");
  await expect(coverage).toContainText(versions.market_data_cutoff_date);
  await expect(coverage).toContainText(DATASET_ID);
  await expect(coverage).toContainText("2012-02-23 ～ 2012-03-21");
  await expect(coverage).toContainText("数据集未认证");
  await expect(coverage).toContainText("行情快照截止日与历史数据集范围是两个独立口径");
  expect(dataset).toMatchObject({ dataset_id: DATASET_ID, row_count: 20, research_eligible: false, confirmatory_research_eligible: false });
});

test("真实历史页完成日期与单股 v2 查询，导出与 API 响应一致", async ({ page }) => {
  const datasetPromise = page.waitForResponse((response) =>
    response.url().includes(`/api/backend/api/v2/research/datasets/${DATASET_ID}`),
  );
  await page.goto(`/research/history?scope_mode=dates&date_from=2012-02-23&date_to=2012-03-21&factor_id=B_DAY_003&activation=nonzero`, { waitUntil: "load" });
  expect(new URL(page.url()).searchParams.has("fixture")).toBe(false);
  const datasetResponse = await datasetPromise;
  expect(datasetResponse.status()).toBe(200);
  const dataset = await datasetResponse.json() as { dataset_digest: string; research_eligible: boolean };
  expect(dataset.research_eligible).toBe(false);
  await expect(page.getByTestId("historical-study-controls")).toContainText("研究资格：未认证");

  const runAndRead = async (scopeMode: "dates" | "stock") => {
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
        research_status: "EXPLORATORY_NOT_GATED",
      });
      await expect(page.getByTestId(`historical-result-${result.horizon}`)).toContainText("EXPLORATORY_NOT_GATED");
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
