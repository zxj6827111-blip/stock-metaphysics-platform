import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const DATASET_ID =
  process.env.NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID?.trim() ||
  "w4-certified-002561-20120223-20180514-v3-path-risk";
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
  const versions = await versionsResponse.json() as { market_data_cutoff_date: string | null };
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
  const marketCutoff = coverage.getByText("行情快照截止日").locator("..");
  await expect(marketCutoff).toContainText(versions.market_data_cutoff_date ?? "不可用");
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
  await page.goto("/research/history?scope_mode=dates&factor_id=B_DAY_005&activation=nonzero", { waitUntil: "load" });
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
    dataset.research_eligible ? "认证：CERTIFIED_LIMITED_SCOPE" : "认证：NOT_CERTIFIED",
  );
  await expect(page.getByTestId("historical-study-controls")).toContainText("确认性资格未具备");
  expect(dataset.confirmatory_research_eligible).toBe(false);

  const executedDateRequests: Record<string, unknown>[] = [];
  const runAndRead = async (scopeMode: "dates" | "stock", factorId = "B_DAY_005") => {
    const factorInput = page.getByTestId("historical-factor-id");
    if (await factorInput.isEnabled()) await factorInput.fill(factorId);
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
        missing_by_reason: Record<string, number>;
        matched: { sample_count: number; mean_return: number | null };
        ten_god_category: string | null;
        events: Array<{ ten_god_category: string | null }>;
      };
      const requestBody = response.request().postDataJSON() as Record<string, unknown>;
      if (scopeMode === "dates" && factorId === "B_DAY_005") executedDateRequests.push(requestBody);
      expect(result).toMatchObject({
        scope_mode: scopeMode,
        horizon: HORIZONS[index],
        dataset_digest: dataset.dataset_digest,
      });
      if (scopeMode === "dates" && factorId === "B_DAY_005") {
        expect(result.ten_god_category).toBe("正财");
        expect(result.events.every((event) => event.ten_god_category === "正财")).toBe(true);
      }
      expect(["EXPLORATORY_NOT_GATED", "INSUFFICIENT_SAMPLE", "DATA_MISSING"]).toContain(result.research_status);
      if (result.research_status === "DATA_MISSING") {
        expect(Object.values(result.missing_by_reason).some((count) => count > 0)).toBe(true);
      }
      await expect(page.getByTestId(`historical-result-${result.horizon}`)).toContainText(result.research_status);
      results.push(result);
    }
    return results;
  };

  await page.getByTestId("historical-ten-god").selectOption("正财");
  const dateResults = await runAndRead("dates");
  expect(dateResults.some((result) => result.matched_observation_count > 0)).toBe(true);
  expect(executedDateRequests).toHaveLength(3);
  expect(executedDateRequests.every((request) =>
    request.activation === "nonzero" && request.ten_god_category === "正财" &&
    request.ten_god_layer === "DAILY" && request.ten_god_position === "day"
  )).toBe(true);
  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("historical-export-json").click();
  const download = await downloadPromise;
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  if (!downloadPath) throw new Error("Playwright did not provide the completed report download path");
  const exported = JSON.parse(readFileSync(downloadPath, "utf8")) as {
    dataset: { dataset_digest: string };
    requests: Array<Record<string, unknown>>;
    results: Array<{ horizon: number; dataset_digest: string; matched_observation_count: number; ten_god_category: string | null }>;
  };
  expect(exported.dataset.dataset_digest).toBe(dataset.dataset_digest);
  expect(exported.requests).toHaveLength(3);
  expect(exported.requests).toEqual(executedDateRequests);
  expect(exported.requests.every((request) => request.scope_mode === "dates" && request.ten_god_category === "正财")).toBe(true);
  expect(exported.results).toHaveLength(dateResults.length);
  expect(exported.results).toEqual(dateResults.map((result) => expect.objectContaining({
    horizon: result.horizon,
    dataset_digest: result.dataset_digest,
    matched_observation_count: result.matched_observation_count,
    ten_god_category: "正财",
  })));

  await page.getByTestId("historical-ten-god").selectOption("");
  const stockResults = await runAndRead("stock");
  expect(stockResults.some((result) => result.matched_observation_count > 0)).toBe(true);

  const noMatchResults = await runAndRead("dates", "W8_NO_MATCH_FACTOR_PROBE");
  expect(noMatchResults.every((result) => result.matched_observation_count === 0)).toBe(true);
  expect(noMatchResults.every((result) => result.research_status === "DATA_MISSING")).toBe(true);
  expect(noMatchResults.every((result) => (result.missing_by_reason.factor_missing ?? 0) > 0)).toBe(true);

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

test("真实冷缓存日期扫描将精确关系条件传入 W4 历史验证并可导出", async ({ page }) => {
  test.setTimeout(180_000);
  const targetDate = "2026-09-29";
  const catalogPromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v1/research/relation-catalog"),
  );
  const scanPromise = page.waitForResponse((response) =>
    response.url().includes("/api/backend/api/v1/research/date-scan") && response.request().method() === "POST",
  );
  const coldScanStartedAt = Date.now();
  await page.goto(`/research/date-scan?date=${targetDate}`, { waitUntil: "load" });
  expect(new URL(page.url()).searchParams.has("fixture")).toBe(false);
  const [catalogResponse, scanResponse] = await Promise.all([catalogPromise, scanPromise]);
  const coldScanElapsedMs = Date.now() - coldScanStartedAt;
  expect(catalogResponse.status()).toBe(200);
  expect(scanResponse.status()).toBe(200);
  expect(coldScanElapsedMs).toBeLessThan(30_000);
  console.log(`cold_date_scan_ms=${coldScanElapsedMs}`);
  const scan = await scanResponse.json() as {
    target_date: string;
    stock_total: number;
    relation_type_counts: Record<string, number>;
    query: { date: string };
    cache: { hit: boolean };
    warnings: Array<{ code: string }>;
  };
  expect(scan.target_date).toBe(targetDate);
  expect(scan.query.date).toBe(targetDate);
  expect(scan.stock_total).toBeGreaterThan(0);
  expect(scan.cache.hit).toBe(false);
  expect(scan.warnings.some((warning) => warning.code === "RELATION_SCAN_NATAL_FALLBACK")).toBe(false);

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
  const studyLink = page.getByTestId("date-scan-v2-study-link-year");
  await expect(studyLink).toBeVisible();
  const href = await studyLink.getAttribute("href");
  if (!href) throw new Error("日期扫描没有生成 W4 历史研究入口");
  const params = new URL(href, "http://127.0.0.1").searchParams;
  const expectedFactor = { 六合: "B_DAY_003", 六冲: "B_DAY_002", 相害: "B_DAY_008" }[relation];
  expect(params.get("scope_mode")).toBe("dates");
  expect(params.get("target_date")).toBe(targetDate);
  expect(params.has("date_from")).toBe(false);
  expect(params.has("date_to")).toBe(false);
  expect(params.get("dataset_id")).toBe("w4-certified-002561-20120223-20180514-v3-path-risk");
  expect(params.get("relation_type")).toBe(relation);
  expect(params.get("factor_id")).toBe(expectedFactor);
  expect(params.get("activation")).toBe("nonzero");
  expect(params.get("relation_source_context")).toBe("day");
  expect(params.get("relation_source_pillar")).toBe("day");
  expect(params.get("relation_target_context")).toBe("natal");
  expect(params.get("relation_target_pillar")).toBe("year");
  expect(params.get("relation_source_component")).toBe("branch");
  expect(params.get("relation_target_component")).toBe("branch");
  await expect(page.getByTestId("date-scan-v2-study-link-month")).toBeVisible();
  await expect(page.getByTestId("date-scan-v2-study-link-day")).toBeVisible();

  const datasetId = "w4-certified-002561-20120223-20180514-v3-path-risk";
  const historyDatasetPromise = page.waitForResponse((response) =>
    response.url().includes(`/api/backend/api/v2/research/datasets/${datasetId}`),
  );
  await studyLink.click();
  const historyDatasetResponse = await historyDatasetPromise;
  expect(historyDatasetResponse.status()).toBe(200);
  const historyDataset = await historyDatasetResponse.json() as {
    metadata: { scope?: { research_dates?: string[] } };
  };
  const certifiedDates = [...(historyDataset.metadata.scope?.research_dates ?? [])].sort();
  expect(certifiedDates.length).toBeGreaterThan(0);
  await expect(page.getByTestId("historical-relation-prefill")).toContainText(relation);
  await expect(page.getByTestId("historical-factor-id")).toHaveValue(expectedFactor);
  await expect(page.getByTestId("historical-activation")).toHaveValue("nonzero");
  await expect(page.getByTestId("historical-target-date")).toHaveValue(targetDate);
  await expect(page.getByTestId("historical-date-from")).toHaveValue(certifiedDates[0]);
  await expect(page.getByTestId("historical-date-to")).toHaveValue(certifiedDates[certifiedDates.length - 1]);

  const relationResponsesPromise = Promise.all(HORIZONS.map((horizon) => page.waitForResponse((item) => {
    if (!item.url().includes("/api/backend/api/v2/research/event-study")) return false;
    const body = item.request().postDataJSON() as { relation_type?: string; horizon?: number };
    return body.relation_type === relation && body.horizon === horizon;
  })));
  await page.getByTestId("historical-run").click();
  const relationResponses = await relationResponsesPromise;
  const executedRelationRequests = relationResponses.map((response) => response.request().postDataJSON() as Record<string, unknown>);
  const relationResults = await Promise.all(relationResponses.map(async (response) => {
    expect(response.status()).toBe(200);
    return await response.json() as {
      target_date: string | null;
      date_from: string;
      date_to: string;
      factor_ids: string[];
      activation: string;
      relation_type: string | null;
      relation_source_context: string | null;
      relation_source_pillar: string | null;
      relation_target_context: string | null;
      relation_target_pillar: string | null;
      relation_source_component: string | null;
      relation_target_component: string | null;
      condition_logic: string;
      matched_observation_count: number;
      events: Array<{ relation_evidence: { relation_type: string; source: { context: string; pillar: string; component: string }; target: { context: string; pillar: string; component: string } } }>;
    };
  }));
  for (const result of relationResults) {
    expect(result).toMatchObject({
      target_date: targetDate,
      date_from: certifiedDates[0],
      date_to: certifiedDates[certifiedDates.length - 1],
      factor_ids: [expectedFactor],
      activation: "nonzero",
      relation_type: relation,
      relation_source_context: "day",
      relation_source_pillar: "day",
      relation_target_context: "natal",
      relation_target_pillar: "year",
      relation_source_component: "branch",
      relation_target_component: "branch",
      condition_logic: "AND",
    });
    expect(result.matched_observation_count).toBeGreaterThan(0);
    expect(result.events.length).toBeGreaterThan(0);
    expect(result.events.every((event) => event.relation_evidence.relation_type === relation)).toBe(true);
    expect(result.events.every((event) => event.relation_evidence.source.context === "day" && event.relation_evidence.source.pillar === "day" && event.relation_evidence.source.component === "branch")).toBe(true);
    expect(result.events.every((event) => event.relation_evidence.target.context === "natal" && event.relation_evidence.target.pillar === "year" && event.relation_evidence.target.component === "branch")).toBe(true);
  }

  const relationDownloadPromise = page.waitForEvent("download");
  await page.getByTestId("historical-export-json").click();
  const relationDownload = await relationDownloadPromise;
  const relationExportPath = await relationDownload.path();
  if (!relationExportPath) throw new Error("六合研究 JSON 报告没有可读取的下载文件");
  const relationExport = JSON.parse(readFileSync(relationExportPath, "utf8")) as {
    requests: Array<Record<string, unknown>>;
    results: Array<{ relation_type: string | null; relation_source_pillar: string | null; relation_target_pillar: string | null; condition_logic: string; matched_observation_count: number }>;
  };
  expect(relationExport.requests).toEqual(executedRelationRequests);
  expect(relationExport.results).toHaveLength(HORIZONS.length);
  expect(relationExport.results.every((result) =>
    result.relation_type === relation && result.relation_source_pillar === "day" &&
    result.relation_target_pillar === "year" && result.condition_logic === "AND" &&
    result.matched_observation_count > 0
  )).toBe(true);
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
  const fortune = await fortuneResponse.json() as {
    timeline: {
      availability: string;
      start_date: string;
      end_date: string;
      ten_god_filters: Array<{ layer: string; ten_god: string }>;
      relation_filters: Array<{ relation_type: string; source_context: string; source_pillar: string; target_context: string; target_pillar: string; source_component: string; target_component: string }>;
      birth_context: {
        birth_time_precision: string;
        birth_datetime: string | null;
        first_trade_datetime: string | null;
        first_trade_date: string | null;
        assumptions: Array<{ reason: string; impact: string }>;
      };
      warnings: Array<{ code: string }>;
    };
  };
  const birth = fortune.timeline.birth_context;
  expect(["UNKNOWN", "DATE_ONLY", "INFERRED", "MINUTE", "EXACT"]).toContain(birth.birth_time_precision);
  if (birth.birth_time_precision === "UNKNOWN") {
    expect(birth.first_trade_date).toBeNull();
    expect(birth.first_trade_datetime).toBeNull();
    expect(birth.birth_datetime).toBeNull();
    expect(birth.assumptions.some((item) => item.impact.includes("不从 listing_date"))).toBe(true);
    expect(fortune.timeline.warnings.some((warning) => warning.code === "FORTUNE_NATAL_BIRTH_TIME_UNAVAILABLE")).toBe(true);
    await expect(page.getByTestId("fortune-birth-profile")).toContainText("UNKNOWN");
    await expect(page.getByTestId("fortune-birth-profile")).toContainText("不可用");
    await expect(page.getByTestId("fortune-v2-warnings")).toContainText("FORTUNE_NATAL_BIRTH_TIME_UNAVAILABLE");
  } else {
    expect(birth.first_trade_date).not.toBeNull();
    expect(birth.assumptions.length).toBeGreaterThan(0);
    if (["DATE_ONLY", "INFERRED"].includes(birth.birth_time_precision)) {
      expect(birth.first_trade_datetime).toBeNull();
    }
    if (["INFERRED", "MINUTE", "EXACT"].includes(birth.birth_time_precision)) {
      expect(birth.birth_datetime).not.toBeNull();
    }
    await expect(page.getByTestId("fortune-birth-profile")).toContainText(birth.birth_time_precision);
    await expect(page.getByTestId("fortune-assumptions")).toBeVisible();
  }

  await page.getByTestId("fortune-range-start").fill("2026-10-01");
  await page.getByTestId("fortune-range-end").fill("2026-10-21");
  await page.getByTestId("fortune-ten-god-filter").selectOption("正财");
  await page.getByTestId("fortune-relation-filter").selectOption("六合");
  const filteredTimelinePromise = page.waitForResponse((response) => {
    if (!response.url().includes("/api/backend/api/v2/research/fortune/timeline") || response.request().method() !== "POST") return false;
    const body = response.request().postDataJSON() as {
      start_date?: string;
      end_date?: string;
      ten_god_filters?: Array<{ layer?: string; ten_god?: string }>;
      relation_filters?: Array<{ relation_type?: string; source_context?: string; source_pillar?: string; target_context?: string; target_pillar?: string }>;
    };
    return body.start_date === "2026-10-01" && body.end_date === "2026-10-21" &&
      body.ten_god_filters?.[0]?.layer === "day" && body.ten_god_filters[0]?.ten_god === "正财" &&
      body.relation_filters?.[0]?.relation_type === "六合" && body.relation_filters[0]?.source_pillar === "day" && body.relation_filters[0]?.target_pillar === "year";
  });
  await page.getByTestId("fortune-run").click();
  const filteredTimelineResponse = await filteredTimelinePromise;
  expect(filteredTimelineResponse.status()).toBe(200);
  const filteredTimeline = await filteredTimelineResponse.json() as {
    timeline: {
      start_date: string;
      end_date: string;
      ten_god_filters: Array<{ layer: string; ten_god: string }>;
      relation_filters: Array<{ relation_type: string; source_context: string; source_pillar: string; target_context: string; target_pillar: string; source_component: string; target_component: string }>;
    };
  };
  expect(filteredTimeline.timeline).toMatchObject({
    start_date: "2026-10-01",
    end_date: "2026-10-21",
    ten_god_filters: [{ layer: "day", ten_god: "正财" }],
    relation_filters: [{
      relation_type: "六合",
      source_context: "day",
      source_pillar: "day",
      target_context: "natal",
      target_pillar: "year",
      source_component: "branch",
      target_component: "branch",
    }],
  });
  await expect(page.getByTestId("fortune-executed-query")).toContainText("2026-10-01 ～ 2026-10-21");
  await expect(page.getByTestId("fortune-executed-query")).toContainText("正财");
  await expect(page.getByTestId("fortune-executed-query")).toContainText("六合");
  await expect(page.getByTestId("fortune-executed-query")).toContainText("AND");
});
