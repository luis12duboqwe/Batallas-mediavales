import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));

const openRoute = async (route) => {
  const link = page.locator(`a[href="${route}"]:visible`).first();
  await link.click();
  await page.waitForURL((url) => url.pathname === route, { timeout: 12000 });
};

try {
  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g2_browser');
  await page.locator('form input').nth(1).fill('G2-Browser-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 15000 });
  await page.locator('main#main-content').waitFor({ state: 'visible' });

  let mapRequests = 0;
  let recoverMap = false;
  await page.route('**/map/tiles**', async (route) => {
    mapRequests += 1;
    // Double requests during initial city centering must remain failures.
    if (!recoverMap) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"tiles":[]}' });
    }
  });
  await openRoute('/map');
  const mapError = page.getByTestId('map-load-error');
  const mapIdle = page.locator('[data-testid="map-grid-panel"][aria-busy="false"]');
  const retryMap = page.getByRole('button', { name: 'Reintentar mapa' });
  await mapError.waitFor({ state: 'visible', timeout: 15000 });
  await mapIdle.waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('map-empty').count(), 0, 'Map error must not be reported as empty');

  // First retry also fails. Do not allow the stub to recover before the
  // actual user click: a late city-centering request could otherwise succeed,
  // remove the button, and make Playwright time out on a detached element.
  const requestsBeforeRetry = mapRequests;
  const retryFailure = page.waitForResponse(
    (response) => response.url().includes('/map/tiles') && response.status() === 503,
    { timeout: 15000 },
  );
  await retryMap.click();
  await retryFailure;
  await mapIdle.waitFor({ state: 'visible', timeout: 15000 });
  await mapError.waitFor({ state: 'visible', timeout: 15000 });
  assert.ok(mapRequests > requestsBeforeRetry, 'Failed retry must send another map request');

  // No pending mocked successful response can clear the error before clicking.
  recoverMap = true;
  await retryMap.click();
  await page.getByTestId('map-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await mapError.count(), 0);
  assert.ok(mapRequests >= requestsBeforeRetry + 2, 'Successful retry must send another map request');
  await page.unroute('**/map/tiles**');

  let inboxRequests = 0;
  let recoverInbox = false;
  await page.route('**/message/inbox**', async (route) => {
    inboxRequests += 1;
    if (!recoverInbox) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    }
  });
  await openRoute('/messages');
  await page.getByTestId('messages-load-error').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('messages-empty').count(), 0, 'Inbox failed, not empty');
  recoverInbox = true;
  await page.getByRole('button', { name: 'Reintentar mensajes' }).click();
  await page.getByTestId('messages-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.ok(inboxRequests >= 2);
  await page.unroute('**/message/inbox**');

  let reportRequests = 0;
  let recoverReports = false;
  await page.route('**/report/**', async (route) => {
    reportRequests += 1;
    if (!recoverReports) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    }
  });
  await openRoute('/reports');
  await page.getByTestId('reports-load-error').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('reports-empty').count(), 0, 'Reports failed, not empty');
  recoverReports = true;
  await page.getByRole('button', { name: 'Reintentar reportes' }).click();
  await page.getByTestId('reports-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('reports-loading').count(), 0);
  assert.ok(reportRequests >= 2);
  assert.deepEqual(errors, [], 'Page errors in resilient states journey');
  console.log('BM-0084 G25 passed: map, inbox, reports distinguish loading/error/empty and recover after 503');
} finally {
  await browser.close();
}
