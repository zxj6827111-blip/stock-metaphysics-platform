/**
 * 视觉结构测量（anchor measurement）—— pixel diff 之外的第二层验收。
 *
 * 为什么需要它：`visual-diff.mjs` 只给出一个整体比例，深色底占画面大半，
 * 于是"结构差得很远"也能拿到较低的 diff（见 docs/UI_INDEPENDENT_REVIEW_2026-09-22.md §一）。
 * 本脚本把关键矩形量成数字：TopBar / Sidebar / PageHero / StockContextBar /
 * 首个主要内容 Card / 页面主要图表 / 右侧摘要区，逐条记录 x / y / width / height，
 * 并额外给出 `firstFoldVisible`（该矩形是否完整落在 941px 首屏内）——
 * "历史摘要必须首屏可见""首屏完整显示两行日期卡"这类要求只能靠这个判定，
 * 像素差异比例替代不了它。
 *
 * 两侧来源不同，因此**分别标注测量方式**，不假装它们是同一种精度：
 *   * candidate：浏览器 `getBoundingClientRect()`，精确值；
 *   * reference：`e2e/fixtures/reference-anchors.json`，对参考 PNG 做边框色长程
 *     检测后**人工核对并冻结**的值；检测不到的条目就是 null，不做估计。
 *
 * 坐标系：viewport 坐标。页面 `main` 是内部滚动容器，截图不滚动，
 * 因此 viewport 坐标即"首屏内实际可见位置"；脚本会记录并断言 scrollTop === 0，
 * 否则量出来的是滚动后的假几何（见 docs/UI_INDEPENDENT_REVIEW_2026-09-22.md §五）。
 *
 * 输出：test-results/visual-reference/anchors-<label>.json（机器可读）
 *      同时写 anchors.json 作为"最近一次"指针。
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const VIEWPORT = { width: 1672, height: 941 };
const OUT_ROOT = path.resolve(process.cwd(), "test-results", "visual-reference");
const FIXTURE_FILE = path.resolve(process.cwd(), "e2e", "fixtures", "reference-anchors.json");

/**
 * 每个 anchor 给一组**按优先级排列**的选择器：
 * 先试语义化 `data-anchor`（本轮引入），再退回既有 `data-testid` / 结构选择器，
 * 这样同一份脚本既能量改造前的页面，也能量改造后的页面。
 */
const ANCHORS = {
  topbar: ['[data-anchor="topbar"]', "header"],
  sidebar: ['[data-anchor="sidebar"]', "aside"],
  pageHero: ['[data-anchor="page-hero"]', '[data-testid="page-hero"]'],
  stockContextBar: ['[data-anchor="stock-context-bar"]', '[data-testid="stock-context-bar"]'],
  primaryCard: [
    '[data-anchor="primary-card"]',
    '[data-testid="engine-scores"]',
    '[data-testid="traditional-huangli"]',
    "main section.smp-card",
  ],
  rightSummary: [
    '[data-anchor="right-summary"]',
    '[data-testid="key-evidence"]',
    '[data-testid="huangli-selected-day"]',
  ],
};

/** 页面主图表各页不同，单独配置。 */
const PRIMARY_CHART = {
  "01-home": ['[data-anchor="primary-chart"]', '[data-testid="mini-trend"]'],
  "02-overview": ['[data-anchor="primary-chart"]', '[data-testid="time-window-chart"]'],
  "03-bazi": ['[data-anchor="primary-chart"]', '[data-testid="wuxing-distribution"]'],
  "04-ziwei": ['[data-anchor="primary-chart"]', '[data-testid="ziwei-chart"]'],
  "05-backtest": ['[data-anchor="primary-chart"]', "main section.smp-card svg"],
  "06-factors": ['[data-anchor="primary-chart"]'],
  "07-conflicts": ['[data-anchor="primary-chart"]'],
  "08-huangli": ['[data-anchor="primary-chart"]', '[data-testid="huangli-day-grid"]'],
  "09-evidence": ['[data-anchor="primary-chart"]'],
  "10-timeline": ['[data-anchor="primary-chart"]', '[data-testid="time-window-chart"]'],
};

const PAGES = {
  "01-home": "/?fixture=ui-reference",
  "02-overview": "/stock/600519/overview?fixture=ui-reference",
  "03-bazi": "/stock/600519/bazi?fixture=ui-reference",
  "04-ziwei": "/stock/600519/ziwei?fixture=ui-reference",
  "05-backtest": "/stock/600519/backtest?fixture=ui-reference",
  "06-factors": "/factors?fixture=ui-reference",
  "07-conflicts": "/stock/600519/conflicts?fixture=ui-reference",
  "08-huangli": "/stock/600519/huangli?fixture=ui-reference",
  "09-evidence": "/stock/600519/evidence?fixture=ui-reference",
  "10-timeline": "/stock/600519/timeline?fixture=ui-reference",
};

const ANCHOR_ORDER = [
  "topbar",
  "sidebar",
  "pageHero",
  "stockContextBar",
  "primaryCard",
  "primaryChart",
  "rightSummary",
];

function measureInPage(selectorGroups) {
  const out = {};
  for (const [name, selectors] of Object.entries(selectorGroups)) {
    let found = null;
    let via = null;
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      found = r;
      via = sel;
      break;
    }
    out[name] = found
      ? {
          x: Math.round(found.x * 10) / 10,
          y: Math.round(found.y * 10) / 10,
          width: Math.round(found.width * 10) / 10,
          height: Math.round(found.height * 10) / 10,
          via,
        }
      : null;
  }
  const main = document.querySelector("main");
  out.__scroll = main ? { scrollTop: main.scrollTop, scrollLeft: main.scrollLeft } : null;
  return out;
}

async function measureCandidates(baseUrl) {
  const browser = await chromium.launch();
  const results = {};
  try {
    for (const [key, route] of Object.entries(PAGES)) {
      const page = await browser.newPage({
        viewport: VIEWPORT,
        deviceScaleFactor: 1,
        locale: "zh-CN",
      });
      await page.clock.install({ time: new Date("2024-11-15T15:00:27+08:00") });
      await page.goto(`${baseUrl}${route}`, { waitUntil: "load" });
      await page.waitForSelector('[data-app-ready="true"]', { timeout: 60_000 });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForSelector('[data-testid="page-loading"]', { state: "detached", timeout: 60_000 });
      // 图表就绪信号：存在时必须等到 true；不存在则如实记录 absent，
      // 不把它当成"已通过图表等待"。
      const chartSignal = await page.evaluate(() => {
        const el = document.querySelector("[data-charts-ready]");
        return el ? el.getAttribute("data-charts-ready") : "absent";
      });
      if (chartSignal === "false") {
        await page.waitForFunction(
          () => document.querySelector("[data-charts-ready]")?.getAttribute("data-charts-ready") === "true",
          { timeout: 60_000 },
        );
      }

      const groups = { ...ANCHORS, primaryChart: PRIMARY_CHART[key] ?? [] };
      const measured = await page.evaluate(measureInPage, groups);
      results[key] = {
        route,
        chartReadySignal: chartSignal,
        scroll: measured.__scroll,
        anchors: Object.fromEntries(Object.entries(measured).filter(([k]) => k !== "__scroll")),
      };
      await page.close();
    }
  } finally {
    await browser.close();
  }
  return results;
}

/** 把冻结的参考边界换算成矩形；只有顶边没有底边的条目如实给 partial（height=null）。 */
function referenceRects(fixture) {
  const out = {};
  for (const [key, v] of Object.entries(fixture)) {
    if (key.startsWith("_")) continue;
    const top = v.topbarHeight;
    const side = v.sidebarWidth;
    const x = side != null ? side + 14 : null;
    const width = x != null ? 1672 - 8 - x : null;
    const rect = (y0, y1) =>
      y0 != null && y1 != null && y1 > y0 && x != null
        ? { x, y: y0, width, height: y1 - y0 }
        : null;
    out[key] = {
      topbar: top != null ? { x: 0, y: 0, width: 1672, height: top } : null,
      sidebar: top != null && side != null ? { x: 0, y: top, width: side, height: 941 - top } : null,
      pageHero: rect(top, v.pageHeroBottom),
      stockContextBar: rect(v.pageHeroBottom, v.stockContextBarBottom),
      primaryCard: v.primaryCardTop != null && x != null ? { x, y: v.primaryCardTop, width, height: null } : null,
      primaryChart: null,
      rightSummary: null,
    };
  }
  return out;
}

function delta(candidate, reference) {
  if (!candidate || !reference) return null;
  const d = {};
  for (const k of ["x", "y", "width", "height"]) {
    d[k] =
      typeof candidate[k] === "number" && typeof reference[k] === "number"
        ? Math.round((candidate[k] - reference[k]) * 10) / 10
        : null;
  }
  return d;
}

async function main() {
  const baseUrl = process.env.SMP_WEB_BASE || "http://127.0.0.1:3000";
  const label = process.env.ANCHOR_LABEL || "current";
  const candidates = await measureCandidates(baseUrl);
  const refs = referenceRects(JSON.parse(fs.readFileSync(FIXTURE_FILE, "utf8")));

  const pages = {};
  for (const [key, c] of Object.entries(candidates)) {
    const ref = refs[key] ?? {};
    const rows = {};
    for (const name of ANCHOR_ORDER) {
      const cv = c.anchors[name] ?? null;
      const rv = ref[name] ?? null;
      rows[name] = {
        candidate: cv,
        reference: rv,
        delta: delta(cv, rv),
        firstFoldVisible:
          cv != null ? Math.round((cv.y + cv.height) * 10) / 10 <= VIEWPORT.height : null,
        measured: { candidate: !!cv, reference: !!rv },
      };
    }
    pages[key] = {
      route: c.route,
      chartReadySignal: c.chartReadySignal,
      scroll: c.scroll,
      anchors: rows,
      candidateAnchorsMissing: Object.entries(rows).filter(([, v]) => !v.measured.candidate).map(([k]) => k),
      referenceAnchorsMissing: Object.entries(rows).filter(([, v]) => !v.measured.reference).map(([k]) => k),
      belowFold: Object.entries(rows)
        .filter(([, v]) => v.measured.candidate && !v.firstFoldVisible)
        .map(([k, v]) => `${k}@y=${v.candidate.y}+h=${v.candidate.height}`),
    };
  }

  const doc = {
    schema: "smp-visual-anchors-v1",
    label,
    viewport: VIEWPORT,
    candidateMeasurement: "getBoundingClientRect on production build, main unscrolled",
    referenceMeasurement:
      "frozen manual read-off of doc/ui-reference PNGs (e2e/fixtures/reference-anchors.json); null = not derivable, never estimated",
    pages,
  };
  fs.mkdirSync(OUT_ROOT, { recursive: true });
  const outFile = path.join(OUT_ROOT, `anchors-${label}.json`);
  fs.writeFileSync(outFile, JSON.stringify(doc, null, 2), "utf8");
  fs.writeFileSync(path.join(OUT_ROOT, "anchors.json"), JSON.stringify(doc, null, 2), "utf8");

  console.log(`\n== anchor measurement (${label}) ==`);
  for (const [key, p] of Object.entries(pages)) {
    console.log(`${key}  charts-ready=${p.chartReadySignal}  scroll=${JSON.stringify(p.scroll)}`);
    for (const name of ANCHOR_ORDER) {
      const a = p.anchors[name];
      const c = a.candidate;
      const r = a.reference;
      const cs = c ? `${String(c.x).padStart(7)},${String(c.y).padStart(6)} ${String(c.width).padStart(7)}x${String(c.height).padStart(6)}` : "      — not measured";
      const rs = r ? `${String(r.x).padStart(7)},${String(r.y).padStart(6)} ${String(r.width).padStart(7)}x${String(r.height ?? "—")}` : "      — ref not derivable";
      console.log(`  ${name.padEnd(16)} cand ${cs}   ref ${rs}   fold=${a.firstFoldVisible === null ? "—" : a.firstFoldVisible ? "yes" : "NO"}`);
    }
    if (p.belowFold.length) console.log(`  ⚠ below 941px fold: ${p.belowFold.join(", ")}`);
  }
  console.log(`\nwrote ${outFile}`);
}

await main();
