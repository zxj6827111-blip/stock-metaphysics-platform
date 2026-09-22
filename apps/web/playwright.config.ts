import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright 配置。
 *
 * 参考图统一 1672×941，因此项目默认使用该 viewport 做视觉验收；
 * 另设一个 1440×900 项目验证桌面端适配与无横向溢出（uiux_spec §34）。
 *
 * ⚠️ 关于 1440 项目的覆盖范围
 * --------------------------
 * 早期配置用 `testMatch: /layout\.spec\.ts/` 把 1440 限制在单个 spec 上，
 * 于是"配置里存在第二个 project"很容易被误读成"1440 已全覆盖" ——
 * 那时 1440 只检查全局几何溢出，**没有逐页验收**。
 * 现在 1440 项目显式包含：
 *   * `layout.spec.ts`（全局无横向溢出）；
 *   * `viewport-1440-pages.spec.ts`（十页逐页适配 + 关键交互）。
 * 其它页面级 spec 仍只在 1672 跑 —— 同一断言跑两遍只增加时长，不增加信息量。
 */

const BASE_URL = process.env.SMP_WEB_BASE || "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    locale: "zh-CN",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "reference-1672x941",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1672, height: 941 }, deviceScaleFactor: 1 },
      testIgnore: /viewport-1440-pages\.spec\.ts/,
    },
    {
      name: "desktop-1440x900",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
      testMatch: [/layout\.spec\.ts/, /viewport-1440-pages\.spec\.ts/],
    },
  ],
});
