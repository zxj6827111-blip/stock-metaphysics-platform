import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright 配置。
 *
 * 参考图统一 1672×941，因此项目默认使用该 viewport 做视觉验收；
 * 另设一个 1440×900 项目验证桌面端无横向溢出（uiux_spec §34）。
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
      use: { ...devices["Desktop Chrome"], viewport: { width: 1672, height: 941 } },
    },
    {
      name: "desktop-1440x900",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
      testMatch: /layout\.spec\.ts/,
    },
  ],
});
