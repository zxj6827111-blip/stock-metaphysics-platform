// 验收辅助：验证合成/降级行情下的显著横幅（P0-1 / §十三）
import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1672, height: 941 } });
await page.goto('http://127.0.0.1:3000/stock/600519/overview', { waitUntil: 'networkidle' });
await page.waitForTimeout(2500);
const banner = page.locator('[data-testid="synthetic-data-banner"]');
const visible = await banner.isVisible().catch(() => false);
const text = visible ? (await banner.innerText()).slice(0, 160) : '';
console.log(JSON.stringify({ bannerVisible: visible, text }, null, 2));
await page.screenshot({ path: '../../artifacts/acceptance/ui_overview_synthetic_banner.png', fullPage: false });
await browser.close();
