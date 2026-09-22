import { expect, test } from "@playwright/test";

/**
 * 择日关系扫描 v3 端到端验收（需要确定性种子库后端）。
 *
 * 依赖：
 *   * 隔离后端使用 `scripts/ci_seed_date_scan.py` 写入的 4 只固定标的
 *     （000001 / 600519 / 600036 / 300750），不访问真实行情网络；
 *   * `SMP_E2E_SEEDED=1` 显式开启（本地默认套件不跑，避免依赖未种子化的后端）。
 *
 * 覆盖：关系优先入口 → 后端 catalog 驱动的关系按钮 → 命中股票表
 * （流日十神 / 流日喜忌，不再有「十神 / 喜用」错列）→ 详情 3×3 矩阵
 * （含行级 relation_types）→ day_stem_verdict → 口径卡 aggregate_scope。
 */

const SEEDED = process.env.SMP_E2E_SEEDED === "1";

test.describe("择日关系扫描 v3（确定性种子库）", () => {
  test.skip(!SEEDED, "需要 SMP_E2E_SEEDED=1 与 scripts/ci_seed_date_scan.py 种子化的隔离后端");

  test("关系优先 → 命中股票 → 3×3 矩阵与流日判定", async ({ page }) => {
    await page.goto("/research/date-scan");
    await expect(page.getByTestId("date-scan-controls")).toBeVisible();

    // 口径卡：矩阵 3×3、聚合只看流日行、喜用基于完整四柱、标准时点
    const scope = page.getByTestId("date-scan-scope");
    await expect(scope).toBeVisible({ timeout: 90_000 });
    await expect(scope).toContainText("3×3");
    await expect(scope).toContainText("股票时柱不参与");
    await expect(scope).toContainText("external_day_row");
    await expect(scope).toContainText("full_four_pillars");
    await expect(scope).toContainText("Asia/Shanghai 12:00:00");
    await expect(scope).toContainText("bazi-relation-v3");

    // 关系按钮来自后端 catalog（不是前端硬编码清单）
    const buttons = page.locator('[data-testid^="relation-filter-"]');
    await expect(buttons.first()).toBeVisible({ timeout: 60_000 });
    const count = await buttons.count();
    expect(count, "关系目录按钮数量应覆盖后端 catalog（22 项）").toBeGreaterThanOrEqual(22);

    // 选择当前日期命中股票最多的关系（数值来自后端 relation_type_counts）
    let bestTestId = "";
    let bestHits = -1;
    for (let index = 0; index < count; index += 1) {
      const button = buttons.nth(index);
      const hits = Number((await button.getAttribute("data-count")) ?? "-1");
      if (hits > bestHits) {
        bestHits = hits;
        bestTestId = (await button.getAttribute("data-testid")) ?? "";
      }
    }
    expect(bestHits, "种子库在默认日期上必须至少有一种关系命中").toBeGreaterThan(0);
    await page.getByTestId(bestTestId).click();

    // 命中股票表：列语义必须是「流日十神 / 流日喜忌」
    const table = page.getByTestId("relation-stock-table");
    await expect(table).toBeVisible({ timeout: 60_000 });
    await expect(table).toContainText("流日十神");
    await expect(table).toContainText("流日喜忌");
    await expect(table).not.toContainText("十神 / 喜用");
    await expect(table).toContainText("股票三柱");
    const firstRow = table.locator("tbody tr").first();
    await expect(firstRow).toBeVisible();

    await firstRow.click();

    // 详情：3×3 矩阵（3 行 × 3 格，无股票时柱列）
    const drawer = page.getByTestId("relation-detail-drawer");
    await expect(drawer).toBeVisible({ timeout: 60_000 });
    await expect(drawer).toContainText("流年/流月/流日 × 股票年/月/日");
    await expect(drawer.getByTestId("relation-matrix-row-year")).toBeVisible();
    await expect(drawer.getByTestId("relation-matrix-row-month")).toBeVisible();
    await expect(drawer.getByTestId("relation-matrix-row-day")).toBeVisible();
    await expect(drawer.locator('[data-testid^="relation-matrix-cell-"]')).toHaveCount(9);
    await expect(drawer.getByTestId("relation-matrix-table")).not.toContainText("股票时柱");
    // 行级 relation_types（后端直接给出，前端不重算）
    await expect(drawer.getByTestId("relation-matrix-row-types-day")).toContainText("行内关系");

    // 流日判定：十神 + 三态 verdict + 完整 reason（十神与五行角色分开陈述）
    const verdict = drawer.getByTestId("relation-day-verdict");
    await expect(verdict).toBeVisible();
    const verdictText = await verdict.innerText();
    expect(verdictText).toContain("十神");
    expect(verdictText).toMatch(/匹配|不匹配|未知/);
    // 旧版把关系类型（天干五合等）当喜用展示的问题不得复现
    expect(verdictText).not.toContain("天干五合");
    const reason = await drawer.getByTestId("relation-day-verdict-reason").innerText();
    expect(reason).toContain("十神");
    expect(reason).toContain("五行");

    await page.screenshot({ path: "test-results/date-scan-v3-detail.png" });
  });

  test("关系研究：无股票且未确认时禁止启动全市场", async ({ page }) => {
    await page.goto("/research/relation-study");
    const controls = page.getByTestId("relation-study-controls");
    await expect(controls).toBeVisible({ timeout: 90_000 });
    await page.getByTestId("relation-study-stocks").fill("");
    await expect(page.getByTestId("relation-study-run")).toBeDisabled();
    await expect(controls).toContainText("必须显式勾选全市场确认");
    await page.getByTestId("relation-study-full-universe").check();
    await expect(page.getByTestId("relation-study-run")).toBeEnabled();
    await page.screenshot({ path: "test-results/relation-study-full-universe-guard.png" });
  });
});
