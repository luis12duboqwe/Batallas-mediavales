import { mkdir } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const OUTPUT_DIR = process.env.UI_CAPTURE_DIR || 'ui-captures';

const USERS = {
  main: { username: 'g8_upkeep', password: 'G8-Upkeep-Test-2026!' },
  reports: { username: 'g9_combat', password: 'G9-Combat-Test-2026!' },
  market: { username: 'g11_commerce', password: 'G11-Commerce-Test-2026!' },
};

await mkdir(OUTPUT_DIR, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });

async function clearExperience() {
  const skip = page.getByRole('button', { name: 'Saltar intro' });
  if (await skip.count()) {
    await skip.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    if (await skip.isVisible().catch(() => false)) {
      await skip.click();
    }
  }

  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) {
    await intro.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  }

  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 1500 }).catch(() => {});
  if (await loading.count()) {
    await loading.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  }
}

async function login(credentials) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await clearExperience();
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(credentials.username);
  await inputs.nth(1).fill(credentials.password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await page.getByTestId('tutorial-panel').waitFor({ state: 'detached', timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(800);
}

async function switchUser(credentials) {
  await page.evaluate(() => localStorage.clear());
  await login(credentials);
}

async function capture(route, filename) {
  await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' });
  await clearExperience();
  await page.getByTestId('tutorial-panel').waitFor({ state: 'detached', timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${OUTPUT_DIR}/${filename}`, fullPage: true });
  console.log(`captured ${route} -> ${filename}`);
}

try {
  await login(USERS.main);
  await capture('/', '01-ciudad.png');
  await capture('/buildings', '02-edificios.png');
  await capture('/troops', '03-tropas.png');
  await capture('/map', '04-mapa.png');

  await switchUser(USERS.market);
  await capture('/market', '05-mercado.png');

  await switchUser(USERS.reports);
  await capture('/reports', '06-informes.png');

  await switchUser(USERS.main);
  await capture('/alliance', '07-alianza.png');
  await capture('/ranking', '08-ranking.png');
  await capture('/academy', '09-academia.png');
} finally {
  await browser.close();
}
