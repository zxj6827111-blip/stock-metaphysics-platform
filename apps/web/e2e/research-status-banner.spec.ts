import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

/**
 * P0-1 验收：合成/降级行情下，综合研判页必须显示显著的
 * "RESEARCH_DATA_UNAVAILABLE" 横幅，而不是一个不显眼的小图标。
 *
 * 测试法：以捕获的真实 API 响应为基座（形状与生产一致），只覆盖
 * ``research_status`` 一个字段，因此对 UI 契约的破坏是精确可控的。
 * 后端语义（合成数据 → NO_REAL_DATA）由
 * ``tests/research/test_synthetic_never_research_evidence.py`` 覆盖。
 *
 * Phase 2 变化：综合研判页的数据源从 `/analysis/bazi` 切换为 `/analysis/multi`
 * （三模型观点 + 正式共识/分歧）。因此这里的桩也必须覆盖 multi 端点。
 */

const ANALYZE_FIXTURE = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures", "analyze.json"), "utf-8"),
);

function stubApis(page: import("@playwright/test").Page, backtestOverride: Record<string, unknown>) {
  const backtestBody = {
    experiment_id: "EXP-STUB",
    factor_ids: ["B_MONTH_001"],
    logic: "any",
    universe_size: 1,
    event_count: 0,
    horizons: [],
    benchmark_code: "000300",
    methodology: "测试桩",
    warnings: [],
    ...backtestOverride,
  };

  // Phase 2：综合研判页读 multi；由捕获的真实 bazi 响应派生，只补必需字段。
  const multiBody = {
    analysis_id: ANALYZE_FIXTURE.analysis_id,
    stock: ANALYZE_FIXTURE.stock,
    birth_profile: ANALYZE_FIXTURE.birth_profile,
    as_of: ANALYZE_FIXTURE.factors?.as_of ?? "2024-11-15T14:32:00",
    variant_mode: "not_applicable",
    bazi_chart: ANALYZE_FIXTURE.chart,
    ziwei_charts: {},
    huangli: ANALYZE_FIXTURE.huangli,
    factors: ANALYZE_FIXTURE.factors,
    opinions: {
      bazi: ANALYZE_FIXTURE.opinion,
      // 紫微不可用时必须是 score:null —— 绝不能用 0 分冒充
      ziwei: {
        engine: "ziwei", engine_version: "", availability: "unavailable",
        direction: 0, score: null, confidence: 0,
        top_positive_reasons: [], top_negative_reasons: [], factor_ids: [],
        note: "紫微斗数引擎本次未启用（variant_mode=not_applicable）。",
      },
      huangli: { ...ANALYZE_FIXTURE.opinion, engine: "huangli" },
    },
    consensus: {
      display_only: false, label: "NEUTRAL", label_cn: "中性",
      participating_engines: ["bazi", "huangli"], unavailable_engines: ["ziwei"],
      directions: { bazi: 0, huangli: 0 }, mean_score: 50,
      agreement_score: 1, available_engine_count: 2,
      research_status: backtestOverride.research_status ?? "NOT_RUN",
      note: "展示层兼容视图",
    },
    conflict: { display_only: false, has_conflict: false, directions: {}, severity: "none", reasons: [], note: "" },
    versions: ANALYZE_FIXTURE.versions,
    warnings: [],
    created_at: ANALYZE_FIXTURE.created_at,
  };

  return Promise.all([
    page.route("**/stocks/600519/analysis/multi", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(multiBody) }),
    ),
    page.route("**/stocks/600519/analysis/bazi", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ANALYZE_FIXTURE) }),
    ),
    page.route("**/analysis/**/backtest*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(backtestBody) }),
    ),
    page.route("**/analysis/**/consensus", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          display_only: true, label: "NEUTRAL", label_cn: "中性",
          participating_engines: ["bazi", "huangli"], unavailable_engines: ["ziwei"],
          directions: { bazi: 0, huangli: 0 }, mean_score: 50, note: "",
        }),
      }),
    ),
    page.route("**/analysis/**/conflicts", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ has_conflict: false, directions: {}, severity: "none", note: "" }),
      }),
    ),
    page.route("**/analysis/**/charts/bazi*", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({ chart_id: "c", chart: ANALYZE_FIXTURE.chart, engine_version: "smx-bazi-native-1.0.0", warnings: [] }),
      }),
    ),
    page.route("**/analysis/**/huangli", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ huangli: ANALYZE_FIXTURE.huangli }) }),
    ),
    page.route("**/analysis/**/factors*", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ANALYZE_FIXTURE.factors) }),
    ),
    page.route("**/analysis/**/evidence*", (route) =>
      route.fulfill({
        status: 200, contentType: "application/json",
        body: JSON.stringify({
          driver_factors: [],
          evidence: { supporting_evidence: [], counter_evidence: [], neutral_evidence: [], retrieval_method: "bm25", note: "" },
        }),
      }),
    ),
  ]);
}

test.describe("研究状态横幅（P0-1）", () => {
  test("NO_REAL_DATA 显示显著横幅", async ({ page }) => {
    await stubApis(page, {
      research_status: "NO_REAL_DATA",
      research_status_reasons: ["当前为合成/降级行情，仅用于系统联调，不构成任何历史有效性证据。"],
      data_source: { is_real: false, degraded_codes: ["synthetic_demo"] },
    });
    await page.goto("/stock/600519/overview");
    const banner = page.getByTestId("synthetic-data-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toContainText("不构成历史研究证据");
  });

  test("正常真实研究状态不显示横幅", async ({ page }) => {
    await stubApis(page, {
      research_status: "SUPPORTED_IN_SAMPLE",
      research_status_reasons: [],
      data_source: { is_real: true },
    });
    await page.goto("/stock/600519/overview");
    await expect(page.getByTestId("engine-scores")).toBeVisible();
    await expect(page.getByTestId("synthetic-data-banner")).toHaveCount(0);
  });

  test("旧后端（无 research_status 字段）不误报且不影响主流程", async ({ page }) => {
    await stubApis(page, { research_status: null });
    await page.goto("/stock/600519/overview");
    await expect(page.getByTestId("engine-scores")).toBeVisible();
    await expect(page.getByTestId("synthetic-data-banner")).toHaveCount(0);
  });
});
