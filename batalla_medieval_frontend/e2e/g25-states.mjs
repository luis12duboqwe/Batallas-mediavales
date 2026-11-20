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
  await page.route('**/map/tiles**', async (route) => {
    mapRequests += 1;
    if (mapRequests === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"tiles":[]}' });
    }
  });
  await openRoute('/map');
  await page.getByTestId('map-load-error').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('map-empty').count(), 0, 'Map error must not be reported as empty');
  await page.getByRole('button', { name: 'Reintentar mapa' }).click();
  await page.getByTestId('map-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('map-load-error').count(), 0);
  assert.ok(mapRequests >= 2, 'Retry must send a new map request');
  await page.unroute('**/map/tiles**');

  let inboxRequests = 0;
  await page.route('**/message/inbox**', async (route) => {
    inboxRequests += 1;
    if (inboxRequests === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    }
  });
  await openRoute('/messages');
  await page.getByTestId('messages-load-error').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('messages-empty').count(), 0, 'Inbox failed, not empty');
  await page.getByRole('button', { name: 'Reintentar mensajes' }).click();
  await page.getByTestId('messages-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.ok(inboxRequests >= 2);
  await page.unroute('**/message/inbox**');

  let reportRequests = 0;
  await page.route('**/report/**', async (route) => {
    reportRequests += 1;
    if (reportRequests === 1) {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    }
  });
  await openRoute('/reports');
  await page.getByTestId('reports-load-error').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('reports-empty').count(), 0, 'Reports failed, not empty');
  await page.getByRole('button', { name: 'Reintentar reportes' }).click();
  await page.getByTestId('reports-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('reports-loading').count(), 0);
  assert.ok(reportRequests >= 2);
  assert.deepEqual(errors, [], 'Page errors in resilient states journey');
  console.log('BM-0084 G25 passed: map, inbox, reports distinguish loading/error/empty and recover after 503');
} finally {
  await browser.close();
}
