import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const DATASET_ID = "w4-certified-002561-20120223-20180514-v3-path-risk";
const DIGEST = "5c1537d8ddea505f854ca78e3d01932740d7768a9f90ff19bd7bf7b96cf771cb";

function datasetResponse() {
  return {
    contract_version: "research-api-v2",
    dataset_id: DATASET_ID,
    dataset_digest: DIGEST,
    schema_version: "w4-historical-panel-v1",
    status: "COMPLETE",
    row_count: 20,
    expected_shard_count: 1,
    complete_shard_count: 1,
    failed_shards: [],
    missing_shards: [],
    metadata: {
      research_eligible: false,
      confirmatory_research_eligible: false,
      scope: {
        research_dates: ["2012-02-23", "2012-02-24", "2012-02-27"],
        stock_code: "002561",
        exchange: "SZSE",
        sample_kind: "single-security deterministic engineering replay",
      },
      known_limitations: ["W2 remains COVERAGE_INCOMPLETE", "Benchmark excess return is unavailable"],
    },
    available_versions: [{
      feature_version: "feature-v1",
      pit_version: "stock-fortune-pit-universe-v2",
      birth_profile_version: "birth-v2",
      birth_profile_source_version: "source-v2",
      calendar_version: "calendar-v1",
      engine_versions: { bazi: "engine-v1" },
      rule_versions: { bazi: "rule-v1" },
      config_version: "cfg-test-v1",
      label_version: "labels-v2",
      bar_version: "bars-raw-v1",
      factor_version: "factor-v1",
      price_basis: "raw_times_factor",
    }],
    research_eligible: false,
    confirmatory_research_eligible: false,
    certification_status: "NOT_CERTIFIED",
    certification_reason: "此测试夹具没有证书绑定。",
    certified_stock_code: null,
    certified_security_id: null,
    certified_date_from: null,
    certified_date_to: null,
    scope_certificate_id: null,
    scope_certificate_sha256: null,
  };
}

function historicalResult(request: Record<string, unknown>) {
  const horizon = request.horizon as number;
  const unavailableMetric = (definition: string) => ({ sample_count: 0, missing_count: 1, mean: null, minimum: null, maximum: null, unit: "fraction", definition });
  const stats = {
    sample_count: 1,
    missing_count: 0,
    mean_return: null,
    median_return: null,
    win_rate: null,
    mean_positive_return: null,
    mean_negative_return: null,
    payoff_ratio: null,
    max_return: null,
    max_loss: null,
    return_unit: "fraction",
    metric_summaries: {
      benchmark_return: unavailableMetric("同持有期基准收益"),
      excess_return: unavailableMetric("个股收益减同持有期基准收益"),
      max_favorable_move: unavailableMetric("事件日收盘后至周期末最高价相对事件日收盘价的最大涨幅"),
      max_adverse_move: unavailableMetric("事件日收盘后至周期末最低价相对事件日收盘价的最大跌幅"),
      max_drawdown: unavailableMetric("事件日收盘起峰值至后续谷值的最大非负回撤"),
    },
  };
  return {
    contract_version: "research-api-v2",
    dataset_id: DATASET_ID,
    dataset_digest: DIGEST,
    scope_mode: "dates",
    date_from: "2012-02-23",
    date_to: "2012-02-27",
    target_date: request.target_date ?? null,
    factor_ids: request.factor_ids ?? ["B_DAY_003"],
    activation: request.activation ?? "nonzero",
    ten_god_category: request.ten_god_category ?? null,
    ten_god_layer: request.ten_god_layer ?? null,
    ten_god_position: request.ten_god_position ?? null,
    relation_type: request.relation_type ?? null,
    relation_source_context: request.relation_source_context ?? null,
    relation_source_pillar: request.relation_source_pillar ?? null,
    relation_target_context: request.relation_target_context ?? null,
    relation_target_pillar: request.relation_target_pillar ?? null,
    relation_source_component: request.relation_source_component ?? null,
    relation_target_component: request.relation_target_component ?? null,
    condition_logic: "AND",
    factor_selection_semantics: "per_factor_observation",
    certified_stock_code: "002561",
    certified_date_from: "2012-02-23",
    certified_date_to: "2012-03-21",
    horizon,
    versions: datasetResponse().available_versions[0],
    research_status: "EXPLORATORY_NOT_GATED",
    research_status_reasons: ["数据集未认证；仅返回描述统计。"],
    candidate_observation_count: 3,
    matched_observation_count: 1,
    observation_unit: "security_date_factor",
    candidate_security_date_count: 3,
    matched_security_date_count: 1,
    matched_date_count: 1,
    missing_observation_count: 1,
    missing_by_reason: { benchmark_missing: 1 },
    matched: stats,
    complement: { ...stats, sample_count: 2, missing_count: 1 },
    overall: { ...stats, sample_count: 3, missing_count: 1 },
    matched_date_equal_weighted: stats,
    returned_count: 1,
    limit: 100,
    offset: 0,
    events: [{
      security_id: "security-1",
      stock_code: "002561",
      research_date: "2012-02-23",
      factor_id: "B_DAY_003",
      direction: 0,
      rule_score: null,
      normalized_value: null,
      horizon,
      return_value: null,
      benchmark_return: null,
      excess_return: null,
      max_favorable_move: null,
      max_adverse_move: null,
      max_drawdown: null,
      ten_god_category: request.ten_god_category ?? null,
      relation_evidence: request.relation_type ? { relation_type: request.relation_type, source: { context: "day", pillar: "day", component: "branch" }, target: { context: "natal", pillar: request.relation_target_pillar, component: "branch" } } : null,
      label_available: false,
      missing_reason: "benchmark_missing",
    }],
    warnings: [],
  };
}

function experimentReport(experimentId: string) {
  return {
    contract_version: "research-api-v2",
    experiment_id: experimentId,
    report_digest: "a".repeat(64),
    report: {
      experiment_id: experimentId,
      title: "冻结实验桩",
      protocol_version: "f5-preregistered-v1",
      protocol_sha256: "b".repeat(64),
      result_digest: "c".repeat(64),
      research_status: "EXPLORATORY_NOT_GATED",
      research_status_reasons: ["W2 数据范围未认证。"],
      dataset: {
        dataset_id: DATASET_ID,
        dataset_digest: DIGEST,
        research_eligible: false,
        confirmatory_research_eligible: false,
        metadata: { known_limitations: ["W2 remains COVERAGE_INCOMPLETE"] },
      },
      scope: {
        date_from: "2012-02-23",
        date_to: "2012-03-21",
        observation_count: 20,
        security_count: 1,
        categories: ["甲", "乙"],
      },
      registration: { pilot_labels_previously_seen: true, confirmatory_eligible: false },
      family_correction: {
        family_id: "f5_exp_001_ten_gods",
        registered_test_count: 60,
        evaluable_p_value_count: 0,
        unavailable_p_value_count: 60,
        fdr_pass_count: 0,
        bonferroni_pass_count: 0,
      },
      frozen_conditions: { horizons: [5, 20], permutation_count: 2000 },
      registered_tests: [{
        hypothesis_id: `${experimentId}:test-1`,
        condition_id: "ten_god_01",
        condition_title: "比肩",
        factor_id: "B_DAY_005",
        partition: "TRAIN",
        horizon: 5,
        candidate_observation_count: 20,
        matched_observation_count: 1,
        complement_observation_count: 19,
        sample_status: "INSUFFICIENT_SAMPLE",
        raw_p_value: null,
        fdr_q_value: null,
        permutation: { status: "NOT_RUN", permutation_count: 0 },
        moving_block_bootstrap: { status: "NOT_RUN", bootstrap_count: 0 },
        negative_control: { random_factor_control: { verdict: "INCONCLUSIVE" } },
      }],
    },
  };
}

test("首页分别显示行情截止日、数据集范围与认证状态", async ({ page }) => {
  await page.route("**/api/backend/api/v1/system/engines*", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ phase: "phase2", engines: [], market_provider: "vendor_parquet", statistics: {} }),
  }));
  await page.route("**/api/backend/api/v1/system/versions*", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ config_version: "cfg-test-v1", market_data_cutoff_date: "2026-08-14", market_data_source: "vendor_parquet", market_data_version: "bars-v1" }),
  }));
  await page.route(`**/api/backend/api/v2/research/datasets/${DATASET_ID}`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(datasetResponse()),
  }));

  await page.goto("/", { waitUntil: "load" });
  const coverage = page.getByTestId("research-data-coverage");
  await expect(coverage).toContainText("2026-08-14");
  await expect(coverage).toContainText("2012-02-23 ～ 2012-02-27");
  await expect(coverage).toContainText("数据集未认证");
  await expect(coverage).toContainText("行情快照截止日与历史数据集范围是两个独立口径");
});

test("日期扫描上下文进入 v2 历史验证，三周期结果可导出原始响应", async ({ page }) => {
  await page.route(`**/api/backend/api/v2/research/datasets/${DATASET_ID}`, (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(datasetResponse()),
  }));
  const requestedHorizons: number[] = [];
  const executedRequests: Record<string, unknown>[] = [];
  await page.route("**/api/backend/api/v2/research/event-study", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    executedRequests.push(body);
    requestedHorizons.push(body.horizon as number);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(historicalResult(body)) });
  });

  await page.goto("/research/history?scope_mode=dates&target_date=2026-09-29&factor_id=B_DAY_003&activation=nonzero&relation_type=%E5%85%AD%E5%90%88&relation_source_context=day&relation_source_pillar=day&relation_target_context=natal&relation_target_pillar=year&relation_source_component=branch&relation_target_component=branch", { waitUntil: "load" });
  await expect(page.getByTestId("historical-relation-prefill")).toContainText("六合");
  await expect(page.getByTestId("historical-factor-id")).toHaveValue("B_DAY_003");
  await expect(page.getByTestId("historical-target-date")).toHaveValue("2026-09-29");
  await expect(page.getByTestId("historical-date-from")).toHaveValue("2012-02-23");
  await expect(page.getByTestId("historical-date-to")).toHaveValue("2012-02-27");
  await page.getByTestId("historical-run").click();
  await expect(page.getByTestId("historical-result-1")).toContainText("EXPLORATORY_NOT_GATED");
  await expect(page.getByTestId("historical-result-5")).toBeVisible();
  await expect(page.getByTestId("historical-result-20")).toBeVisible();
  await expect(page.getByTestId("historical-events-5")).toContainText("benchmark_missing");
  await expect.poll(() => Array.from(new Set(requestedHorizons)).sort((left, right) => left - right).join(",")).toBe("1,5,20");
  await expect(page.getByTestId("historical-executed-conditions-1")).toContainText("day/day/branch → natal/year/branch");
  expect(executedRequests).toHaveLength(3);
  for (const request of executedRequests) {
    expect(request).toMatchObject({
      date_from: "2012-02-23",
      date_to: "2012-02-27",
      target_date: "2026-09-29",
      relation_type: "六合",
      relation_source_context: "day",
      relation_source_pillar: "day",
      relation_target_context: "natal",
      relation_target_pillar: "year",
      relation_source_component: "branch",
      relation_target_component: "branch",
      activation: "nonzero",
    });
  }

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("historical-export-json").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^historical-research-.*\.json$/);
  const exportPath = await download.path();
  if (!exportPath) throw new Error("JSON 报告没有可读取的下载文件");
  const exported = JSON.parse(readFileSync(exportPath, "utf-8")) as {
    requests: Record<string, unknown>[];
    results: Record<string, unknown>[];
  };
  expect(exported.requests[0]).toMatchObject(executedRequests[0]);
  expect(exported.results[0]).toMatchObject({
    target_date: "2026-09-29",
    relation_type: "六合",
    relation_source_pillar: "day",
    relation_target_pillar: "year",
    condition_logic: "AND",
    observation_unit: "security_date_factor",
  });

  const markdownPromise = page.waitForEvent("download");
  await page.getByTestId("historical-export-markdown").click();
  const markdown = await markdownPromise;
  const markdownPath = await markdown.path();
  if (!markdownPath) throw new Error("Markdown 报告没有可读取的下载文件");
  const markdownBody = readFileSync(markdownPath, "utf-8");
  expect(markdownBody).toContain("day/day/branch→natal/year/branch");
  expect(markdownBody).toContain("样本最大收益");
  expect(markdownBody).toContain("max_drawdown");
});

test("研究实验室读取冻结的 v2 报告并展示资格、负对照和逐项结果", async ({ page }) => {
  await page.route("**/api/backend/api/v1/research/experiments?*", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ total: 0, filtered_count: 0, returned_count: 0, query: {}, items: [] }),
  }));
  await page.route("**/api/backend/api/v2/research/experiments/F5-EXP-*", async (route) => {
    const pathParts = new URL(route.request().url()).pathname.split("/");
    const experimentId = pathParts[pathParts.length - 1] || "F5-EXP-001";
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(experimentReport(experimentId)) });
  });

  await page.goto("/research/experiments", { waitUntil: "load" });
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText(DATASET_ID);
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText("INSUFFICIENT_SAMPLE");
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText("INCONCLUSIVE");
  await expect(page.getByTestId("frozen-experiment-reports")).toContainText("探索性，不具确认性资格");
  await page.getByTestId("frozen-experiment-F5-EXP-002").click();
  await expect(page.getByTestId("frozen-experiment-detail")).toContainText("F5-EXP-002");
  await expect(page.getByTestId("frozen-experiment-tests")).toBeVisible();
});

test("个股时间窗口调用 Fortune v2 并保留出生时间精度与显式假设", async ({ page }) => {
  const analyze = JSON.parse(readFileSync(path.join(__dirname, "fixtures", "analyze.json"), "utf8")) as Record<string, unknown>;
  const stock = { stock_code: "600519", wind_code: "600519.SH", name: "贵州茅台", exchange: "SSE", board: "主板", industry: "白酒", listing_date: "2001-08-27", data_quality: { grade: "A", score: 1, notes: [] } };
  const multi = {
    analysis_id: "W7-STUB", stock, birth_profile: analyze.birth_profile,
    as_of: "2026-09-28", variant_mode: "not_applicable", horizon: "20d",
    bazi_chart: null, ziwei_charts: {}, huangli: null, factors: { stock_code: "600519", as_of: "2026-09-28", observations: [] },
    opinions: {}, consensus: null, conflict: null, versions: {}, warnings: [], created_at: "2026-09-28T00:00:00",
  };
  const loadJson = (file: string) => JSON.parse(readFileSync(path.join(__dirname, "..", "lib", "fixtures", file), "utf8")) as Record<string, unknown>;
  const [months, weeks, days] = await Promise.all([loadJson("timeline-months-12.json"), loadJson("timeline-weeks-12.json"), loadJson("timeline-days-20.json")]);
  await page.route("**/api/backend/api/v1/stocks/600519/analysis/multi", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(multi) }));
  await page.route("**/api/backend/api/v1/analysis/W7-STUB/timeline/months*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(months) }));
  await page.route("**/api/backend/api/v1/analysis/W7-STUB/timeline/weeks*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(weeks) }));
  await page.route("**/api/backend/api/v1/analysis/W7-STUB/timeline/days*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(days) }));
  await page.route("**/api/backend/api/v1/system/versions*", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ config_version: "cfg-test-v1", market_data_cutoff_date: null, market_data_source: "test-source", market_data_version: "bars-v1" }) }));
  await page.route("**/api/backend/api/v1/research/relation-catalog", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ relation_rule_version: "relation-v1", relation_matrix_schema_version: "matrix-v1", aggregate_scope: "external_day_row", groups: [{ label: "地支", items: ["六合", "六冲"] }], factors: {} }),
  }));
  let fortuneRequest: Record<string, unknown> | null = null;
  await page.route("**/api/backend/api/v2/research/fortune/timeline", async (route) => {
    fortuneRequest = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract_version: "research-api-v2",
        resolved_versions: { config_version: "cfg-test-v1", market_data_version: "bars-v1" },
        timeline: {
          stock_identity: { symbol: "600519", exchange: "SSE", name: "贵州茅台", source_version: "bars-v1" },
          birth_context: {
            symbol: "600519", exchange: "SSE", listing_date: "2001-08-27", first_trade_datetime: null,
            first_trade_date: "2001-08-27", first_trade_resolution: "daily_bar", birth_basis: "market_first_trade",
            birth_datetime: "2001-08-27T15:00:00+08:00", birth_datetime_status: "inferred", timezone: "Asia/Shanghai",
            birth_time_precision: "INFERRED", source: { source: "market-provider:test" }, source_version: "bars-v1",
            confidence: 0.7, birth_profile_version: "birth-v2", rule_version: "birth-rule-v1", config_version: "cfg-test-v1",
            market_session_version: "a-share-session-v1", assumptions: [{ key: "daily_bar_anchor", value: "15:00", reason: "日线只有日期精度", impact: "出生时刻为假设" }],
            data_quality: { grade: "B", score: 0.7, notes: ["以日线收盘锚点推定"] },
          },
          start_date: "2026-09-28", end_date: "2026-10-18", timezone: "Asia/Shanghai",
          date_mode: "ALL_CALENDAR_DAYS", anchor_mode: "EXACT_LOCAL_TIME", ten_god_filters: [], relation_filters: [],
          include_relation_events: true, include_month_segments: true, include_ten_god_index: true,
          points: [{ date: "2026-09-28", evaluation_datetime: "2026-09-28T12:00:00+08:00", trading_day: null, trading_calendar_source: "unavailable", annual_pillar: { stem: "丙", branch: "午" }, monthly_pillar: null, daily_pillar: { stem: "甲", branch: "子" }, availability: "available" }],
          availability: "available", rule_versions: {}, provenance: [], warnings: [], assumptions: [], rule_version: "fortune-timeline-v1",
        },
      }),
    });
  });

  await page.goto("/stock/600519/timeline", { waitUntil: "load" });
  await expect(page.getByTestId("fortune-birth-profile")).toContainText("INFERRED");
  await expect(page.getByTestId("fortune-assumptions")).toContainText("出生时刻为假设");
  await expect(page.getByTestId("fortune-v2-points")).toContainText("甲子");
  await expect.poll(() => fortuneRequest?.config_version).toBe("cfg-test-v1");
  const expectedStart = String(months.as_of).slice(0, 10);
  const [year, month, day] = expectedStart.split("-").map(Number);
  const expectedEnd = new Date(Date.UTC(year, month - 1, day + 20)).toISOString().slice(0, 10);
  await expect.poll(() => fortuneRequest?.start_date).toBe(expectedStart);
  await expect.poll(() => fortuneRequest?.end_date).toBe(expectedEnd);
});
