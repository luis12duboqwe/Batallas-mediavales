import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';

const failures = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

page.on('console', (message) => {
  if (message.type() === 'error') {
    failures.push(`console.error: ${message.text()}`);
  }
});
page.on('pageerror', (error) => {
  failures.push(`pageerror: ${error.message}`);
});
page.on('response', (response) => {
  if (response.status() >= 500) {
    failures.push(`HTTP ${response.status()}: ${response.url()}`);
  }
});

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });

  const acceptedRoutes = [
    '/',
    '/buildings',
    '/academy',
    '/troops',
    '/map',
    '/movements',
    '/reports',
  ];
  for (const route of acceptedRoutes) {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' });
    if (page.url().includes('/login')) {
      failures.push(`Unexpected logout while opening ${route}`);
    }
  }

  // Modules explicitly postponed beyond the MVP must not be routable.
  await page.goto(`${BASE_URL}/hero`, { waitUntil: 'networkidle' });
  if (new URL(page.url()).pathname !== '/') {
    failures.push(`Postponed route /hero did not redirect to /: ${page.url()}`);
  }

  const visibleText = await page.locator('body').innerText();
  for (const forbidden of ['Hero', 'Aventuras', 'Tienda', 'Simulador']) {
    if (visibleText.includes(forbidden)) {
      failures.push(`Postponed navigation leaked into MVP UI: ${forbidden}`);
    }
  }

  if (failures.length > 0) {
    throw new Error(failures.join('\n'));
  }
  console.log('G2 browser smoke passed without console errors or HTTP 5xx');
} finally {
  await browser.close();
}
