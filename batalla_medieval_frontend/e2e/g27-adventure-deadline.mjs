import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

// Regression: reward claim becomes available at the deadline without relying
// on unrelated resource-bar updates or an unsupported Timer callback prop.
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ reducedMotion: 'reduce' });
const errors = [];
let adventureRequests = 0;
page.on('pageerror', (error) => errors.push(error.message));

try {
  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g2_browser');
  await page.locator('form input').nth(1).fill('G2-Browser-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 15000 });

  await page.route('**/adventure/**', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    adventureRequests += 1;
    const startedAt = new Date().toISOString();
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        { id: 99001, status: 'active', difficulty: 'easy', started_at: startedAt, duration: 6 },
        { id: 99002, status: 'active', difficulty: 'medium', started_at: new Date(Date.now() - 10000).toISOString(), duration: 1 },
        { id: 99003, status: 'active', difficulty: 'hard', started_at: startedAt, duration: 3600 },
      ]),
    });
  });

  await page.goto(BASE_URL + '/adventures', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('adventures-view').waitFor({ state: 'visible', timeout: 15000 });
  await page.getByTestId('adventure-99001').waitFor();
  assert.equal(await page.getByTestId('adventure-claim-99001').count(), 0,
    'Reward cannot be claimed before deadline');
  await page.getByTestId('adventure-99001').getByText(/\d{2}:\d{2}:\d{2}/).waitFor({ timeout: 5000 });
  await page.getByTestId('adventure-claim-99002').waitFor({ state: 'visible', timeout: 5000 });
  assert.equal(await page.getByTestId('adventure-claim-99003').count(), 0,
    'Future adventure must remain unclaimable');

  await page.getByTestId('adventure-claim-99001').waitFor({ state: 'visible', timeout: 12000 });
  assert.equal(await page.getByTestId('adventure-claim-99003').count(), 0,
    'Another upcoming adventure must remain unclaimable after the first expires');
  assert.ok(adventureRequests >= 1);
  assert.deepEqual(errors, []);
  console.log('G27 BM-0085 passed: countdown, already-expired, future and deadline transition without resource tick');
} finally {
  await browser.close();
}
