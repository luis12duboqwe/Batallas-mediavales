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

  // Resolve the actual seeded city's coordinates instead of accepting an
  // origin (0,0) request while the city store is still hydrating.
  const API = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
  const token = await page.evaluate(() => localStorage.getItem('bm_token'));
  assert.ok(token, 'Authenticated fixture token missing');
  const headers = { Authorization: 'Bearer ' + token };
  const profileResponse = await context.request.get(API + '/auth/me', { headers });
  assert.equal(profileResponse.status(), 200);
  const profile = await profileResponse.json();
  const citiesResponse = await context.request.get(API + '/city/?world_id=' + profile.world_id, { headers });
  assert.equal(citiesResponse.status(), 200);
  const cities = await citiesResponse.json();
  assert.equal(cities.length, 1, 'G25 requires the single-city browser fixture');
  const city = cities[0];
  const isHomeMap = (url) => {
    const parsed = new URL(url);
    return parsed.pathname.endsWith('/map/tiles')
      && parsed.searchParams.get('world_id') === String(profile.world_id)
      && parsed.searchParams.get('x') === String(city.x)
      && parsed.searchParams.get('y') === String(city.y);
  };

  let mapRequests = 0;
  let retryRequests = 0;
  let listenerReady = false;
  // Capture the real button click synchronously in the browser, before
  // React handles it. Do not let an unrelated in-flight request recover
  // the map and detach the button before the user has actually clicked.
  await page.route('**/map/tiles**', async (route) => {
    const home = isHomeMap(route.request().url());
    if (home) mapRequests += 1;
    const clicks = listenerReady
      ? await page.evaluate(() => window.__g25MapRetryClicks)
      : 0;
    if (home && clicks >= 1) retryRequests += 1;
    if (home && clicks >= 2) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"tiles":[]}' });
    } else {
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    }
  });
  const initialFailure = page.waitForResponse(
    (response) => isHomeMap(response.url()) && response.status() === 503,
    { timeout: 15000 },
  );
  await openRoute('/map');
  await initialFailure;
  const mapError = page.getByTestId('map-load-error');
  const mapIdle = page.locator('[data-testid="map-grid-panel"][aria-busy="false"]');
  const retryMap = page.getByRole('button', { name: 'Reintentar mapa' });
  await page.waitForFunction(
    ([x, y]) => document.querySelector('[data-testid="map-center"]')?.textContent
      .includes(`Centro: (${x}, ${y})`), [city.x, city.y], { timeout: 15000 },
  );
  await mapIdle.waitFor({ state: 'visible', timeout: 15000 });
  await mapError.waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByTestId('map-empty').count(), 0, 'Map error must not be reported as empty');

  await page.evaluate(() => {
    window.__g25MapRetryClicks = 0;
    document.addEventListener('click', (event) => {
      if (event.target instanceof Element && event.target.closest('[data-testid="map-load-error"] button')) {
        window.__g25MapRetryClicks += 1;
      }
    }, { capture: true });
  });
  listenerReady = true;
  const requestsBeforeRetry = mapRequests;
  await Promise.all([
    page.waitForResponse((response) => isHomeMap(response.url()) && response.status() === 503,
      { timeout: 15000 }),
    retryMap.click(),
  ]);
  await mapIdle.waitFor({ state: 'visible', timeout: 15000 });
  await mapError.waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.evaluate(() => window.__g25MapRetryClicks), 1);
  assert.ok(retryRequests >= 1 && mapRequests > requestsBeforeRetry,
    'Failed user retry must send another home-map request');
  assert.equal(await page.getByTestId('map-empty').count(), 0);

  const requestsBeforeRecovery = mapRequests;
  await Promise.all([
    page.waitForResponse((response) => isHomeMap(response.url()) && response.status() === 200,
      { timeout: 15000 }),
    retryMap.click(),
  ]);
  await page.getByTestId('map-empty').waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.evaluate(() => window.__g25MapRetryClicks), 2);
  assert.equal(await mapError.count(), 0);
  assert.ok(mapRequests > requestsBeforeRecovery && retryRequests >= 2,
    'Successful user retry must send another home-map request');
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
