/**
 * UI 1:1 复刻截图脚本。
 *
 * 参考图统一尺寸 1672×941（doc/ui-reference/*.png），
 * 因此这里固定 viewport 为 1672×941 并逐页截图，输出到 artifacts/ui-review/<page>/current.png。
 *
 * 用法：
 *   node scripts/capture-screenshots.mjs                 # fixture 模式（复刻验收）
 *   node scripts/capture-screenshots.mjs --live          # 真实 API 模式
 *   node scripts/capture-screenshots.mjs --base http://127.0.0.1:3000
 */

import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const CI = process.argv.includes("--ci");
const LIVE = process.argv.includes("--live");
const baseArgIdx = process.argv.indexOf("--base");
const BASE = baseArgIdx >= 0 ? process.argv[baseArgIdx + 1] : "http://127.0.0.1:3000";

const VIEWPORT = { width: 1672, height: 941 };
const SUFFIX = LIVE ? "" : "?fixture=ui-reference";

const PAGES = [
  { key: "01-home", url: `/${SUFFIX}`, label: "首页" },
  { key: "02-overview", url: `/stock/600519/overview${SUFFIX}`, label: "综合研判" },
  { key: "03-bazi", url: `/stock/600519/bazi${SUFFIX}`, label: "八字详情" },
  // Phase 2：参考图 04–10 对应的七个页面
  { key: "04-ziwei", url: `/stock/600519/ziwei${SUFFIX}`, label: "紫微斗数详情" },
  { key: "05-backtest", url: `/stock/600519/backtest${SUFFIX}`, label: "历史验证" },
  { key: "06-factors", url: `/factors${SUFFIX}`, label: "因子字典" },
  { key: "07-conflicts", url: `/stock/600519/conflicts${SUFFIX}`, label: "模型分歧中心" },
  { key: "08-huangli", url: `/stock/600519/huangli${SUFFIX}`, label: "黄历 / 日课详情" },
  { key: "09-evidence", url: `/stock/600519/evidence${SUFFIX}`, label: "古籍证据检索" },
  { key: "10-timeline", url: `/stock/600519/timeline${SUFFIX}`, label: "时间窗口" },
];

const OUT_ROOT = path.resolve(process.cwd(), "artifacts", "ui-review");
const REF_ROOT = path.resolve(process.cwd(), "..", "..", "doc", "ui-reference");

const REF_MAP = {
  "01-home": "01_home.png",
  "02-overview": "02_integrated_analysis.png",
  "03-bazi": "03_bazi_detail.png",
  "04-ziwei": "04_ziwei_detail.png",
  "05-backtest": "05_backtest_validation.png",
  "06-factors": "06_factor_dictionary.png",
  "07-conflicts": "07_model_conflict_center.png",
  "08-huangli": "08_huangli_detail.png",
  "09-evidence": "09_classics_evidence_search.png",
  "10-timeline": "10_time_window.png",
};

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    locale: "zh-CN",
  });
  const page = await context.newPage();

  const results = [];

  for (const p of PAGES) {
    const dir = path.join(OUT_ROOT, p.key);
    fs.mkdirSync(dir, { recursive: true });

    const url = `${BASE}${p.url}`;
    process.stdout.write(`→ ${p.label} ${url}\n`);

    const errors = [];
    const onConsole = (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    };
    const onPageError = (err) => errors.push(String(err));
    page.on("console", onConsole);
    page.on("pageerror", onPageError);

    await page.goto(url, { waitUntil: "load", timeout: 60000 });
    // 严格等待页面核心标题出现，超时必须失败抛出异常，严禁静默吞掉
    await page.waitForSelector("[data-testid=page-title], [data-testid=home-title]", { timeout: 30000 });
    // 严格等待加载中状态脱离 DOM，超时必须失败
    await page.locator("[data-testid=page-loading]").waitFor({ state: "detached", timeout: 15000 });
    // 等字体与 ECharts 渲染稳定
    await page.waitForTimeout(1400);

    await page.screenshot({ path: path.join(dir, "current.png"), fullPage: false });

    // 参考图同步一份到对比目录，便于人工并排查看
    const refName = REF_MAP[p.key];
    const refSrc = path.join(REF_ROOT, refName);
    if (fs.existsSync(refSrc)) {
      fs.copyFileSync(refSrc, path.join(dir, "reference.png"));
    }

    const title = await page.locator("[data-testid=page-title], [data-testid=home-title]").first().textContent().catch(() => null);
    const fixtureBanner = await page
      .locator("[data-testid=fixture-banner]")
      .count()
      .catch(() => 0);

    results.push({
      page: p.key,
      label: p.label,
      url,
      title: title?.trim() ?? "",
      fixtureBanner: fixtureBanner > 0,
      consoleErrors: errors,
    });

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
  }

  await browser.close();

  fs.writeFileSync(
    path.join(OUT_ROOT, "capture-report.json"),
    JSON.stringify({ viewport: VIEWPORT, mode: LIVE ? "live" : "fixture", base: BASE, results }, null, 2),
    "utf8",
  );

  for (const r of results) {
    const flag = r.consoleErrors.length ? `⚠ ${r.consoleErrors.length} console errors` : "✓";
    process.stdout.write(`  ${flag} ${r.page} title="${r.title}"\n`);
    for (const e of r.consoleErrors.slice(0, 4)) process.stdout.write(`      ${e}\n`);
  }
  process.stdout.write(`\n截图已保存到 ${OUT_ROOT}\n`);
  if (CI && (results.some((r) => r.consoleErrors.length) || results.some((r) => !r.title))) process.exit(1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
