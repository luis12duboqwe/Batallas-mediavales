import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const failures = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const page = await context.newPage();

page.on('console', (message) => {
  if (message.type() === 'error') failures.push(`console.error: ${message.text()}`);
});
page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  const submit = page.getByRole('button', { name: /Entrar|Log in|Login/i });
  await submit.click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 20000 });
}

try {
  await login();

  const helpLink = page.getByTestId('mobile-navigation').getByRole('link', { name: /Help|Ayuda/i });
  await helpLink.waitFor({ state: 'visible', timeout: 15000 });
  await helpLink.click();
  await page.waitForURL(`${BASE_URL}/wiki`, { timeout: 15000 });

  await page.getByRole('heading', { name: 'Enciclopedia' }).waitFor({ timeout: 15000 });
  const economyArticle = page.getByRole('button', { name: /Economía y producción/i });
  await economyArticle.waitFor({ state: 'visible', timeout: 15000 });
  await economyArticle.click();
  await page.getByRole('heading', { name: 'Economía y producción' }).waitFor();

  const articleText = await page.locator('main').innerText();
  if (!articleText.includes('Versión de balance')) {
    failures.push('Help article does not expose its server-authoritative balance version');
  }

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  if (overflow.scrollWidth > overflow.clientWidth + 1) {
    failures.push(`Help route overflows mobile viewport: ${JSON.stringify(overflow)}`);
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log('G19 tutorial/help passed: Help is navigable, balance-backed and mobile-safe');
} finally {
  await browser.close();
}
