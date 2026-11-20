import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

// Browser regression for the page's state machine. The real login fixture is
// reused from G27; all adventure GET/POST requests are intercepted and NEVER
// award real rewards. Run with a seeded G2 test backend and Vite preview.
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  reducedMotion: 'reduce',
  timezoneId: 'America/Tegucigalpa',
});
const pageErrors = [];

const seed = 'a'.repeat(64);
const result = (status) => ({
  status,
  damage: status === 'dead' ? 100 : 5,
  xp: status === 'dead' ? 0 : 25,
  loot: status === 'dead' ? null : { type: 'resource', resource: 'wood', amount: 10 },
  seed,
  rules_version: '2026.08.25-bm0068-v1',
});
const startedAt = new Date(Date.now() - 30_000).toISOString().replace(/Z$/, '');
const rows = [
  { id: 99101, difficulty: 'easy', duration: 120, status: 'available', rules_version: 'test' },
  { id: 99102, difficulty: 'easy', duration: 1, status: 'active', started_at: startedAt, outcome_seed: seed, rules_version: 'test' },
  { id: 99103, difficulty: 'medium', duration: 100, status: 'completed', result: result('success'), rules_version: 'test' },
  { id: 99104, difficulty: 'hard', duration: 1, status: 'active', started_at: startedAt, outcome_seed: seed, rules_version: 'test' },
];
let initialGetFails = true;
let getAfterSuccessfulClaimFails = false;
let startRequests = 0;
const claims = new Map();
page.on('pageerror', (error) => pageErrors.push(error.message));

try {
  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g2_browser');
  await page.locator('form input').nth(1).fill('G2-Browser-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 15000 });

  await page.route('**/adventure/**', async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const method = request.method();
    if (method === 'GET') {
      if (initialGetFails) {
        initialGetFails = false;
        return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Unavailable"}' });
      }
      if (getAfterSuccessfulClaimFails) {
        getAfterSuccessfulClaimFails = false;
        return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Temporary error"}' });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(rows) });
    }

    const id = Number(pathname.match(/\/(\d+)\/(start|claim)$/)?.[1]);
    const action = pathname.match(/\/(start|claim)$/)?.[1];
    const row = rows.find((adventure) => adventure.id === id);
    if (!row || !action) return route.fulfill({ status: 404, body: 'Unknown adventure' });

    if (action === 'start') {
      startRequests += 1;
      await new Promise((resolve) => setTimeout(resolve, 350));
      Object.assign(row, { status: 'active', started_at: new Date().toISOString(), outcome_seed: seed });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(row) });
    }

    claims.set(id, (claims.get(id) || 0) + 1);
    if (id === 99104) await new Promise((resolve) => setTimeout(resolve, 300));
    row.status = id === 99104 ? 'failed' : 'completed';
    row.result = result(id === 99104 ? 'dead' : 'success');
    if (id === 99102) {
      // The POST committed on the server, but the response was lost.
      return route.abort('failed');
    }
    getAfterSuccessfulClaimFails = true;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(row.result) });
  });

  await page.goto(BASE_URL + '/adventures', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('adventures-view').waitFor({ state: 'visible', timeout: 15000 });
  await page.getByRole('alert').waitFor({ state: 'visible' });
  assert.equal(await page.getByTestId('adventure-refresh').isDisabled(), false,
    'A failed first load must leave an enabled refresh action');
  await page.getByTestId('adventure-refresh').click();
  await page.getByTestId('adventure-start-99101').waitFor({ state: 'visible' });
  await page.getByTestId('adventure-claim-99102').waitFor({ state: 'visible' });
  assert.equal(await page.getByRole('alert').count(), 0);

  await page.getByTestId('adventure-start-99101').evaluate((button) => {
    button.click();
    button.click(); // two DOM events before React has rendered disabled
  });
  await page.getByTestId('adventure-start-99101').waitFor({ state: 'detached', timeout: 10000 });
  assert.equal(startRequests, 1, 'The same adventure must not start twice');

  await page.getByTestId('adventure-claim-99102').click();
  await page.getByTestId('adventure-result').waitFor({ state: 'visible', timeout: 10000 });
  assert.equal(claims.get(99102), 1, 'Lost POST response must not trigger a second claim');
  assert.equal(await page.getByTestId('adventure-claim-99102').count(), 0);
  await page.getByTestId('adventure-result').getByRole('button', { name: 'Continuar' }).click();
  await page.waitForFunction(() => document.activeElement?.id === 'main-content');
  await page.getByTestId('adventure-result-99102').click();
  await page.getByTestId('adventure-result').waitFor({ state: 'visible' });
  await page.getByTestId('adventure-result').getByRole('button', { name: 'Continuar' }).click();
  await page.waitForFunction(() => document.activeElement?.getAttribute('data-testid') === 'adventure-result-99102');

  await page.getByTestId('adventure-claim-99104').evaluate((button) => {
    button.click();
    button.click();
  });
  await page.getByTestId('adventure-result').waitFor({ state: 'visible' });
  assert.equal(claims.get(99104), 1);
  assert.equal(await page.getByTestId('adventure-claim-99104').count(), 0,
    'A successful claim must remain terminal even if the following GET fails');
  await page.getByTestId('adventure-result').getByText(/derrota/).waitFor();
  await page.getByTestId('adventure-result').getByRole('button', { name: 'Continuar' }).click();
  await page.getByTestId('adventure-refresh').click();
  await page.getByTestId('adventure-result-99104').waitFor({ state: 'visible' });
  assert.equal(await page.getByRole('alert').count(), 0);
  assert.deepEqual(pageErrors, []);
  console.log('Parallel adventures browser flow passed: load retry, duplicate click, lost response and terminal reward');
} finally {
  await browser.close();
}
