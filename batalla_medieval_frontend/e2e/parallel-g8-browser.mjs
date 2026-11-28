import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { firefox, webkit } from '@playwright/test';
import { API, UI, assertIsolated, loginUi, playerSnapshot } from './parallel-journey-helpers.mjs';

assertIsolated();
for (const value of [process.env.VITE_SOCKET_URL, API, UI].filter(Boolean)) {
  const url = new URL(value);
  assert.equal(url.protocol, 'http:');
  assert.equal(url.hostname, '127.0.0.1');
  assert.ok(Number(url.port) >= 1024);
}

const credentials = {
  general: ['g2_browser', 'G2-Browser-Test-2026!'],
  alliance: ['g14_rival', 'G14-Community-Test-2026!'],
};
const timeout = 15000;
const failures = [];
let executed = 0;
const selected = (process.env.G8_ENGINES || 'webkit,firefox').split(',');
assert.ok(selected.length && selected.every((name) => ['webkit', 'firefox'].includes(name)), 'G8_ENGINES: webkit,firefox');

async function open(page, path) {
  await page.locator(`a[href="${path}"]:visible`).first().click();
  await page.waitForURL((url) => url.pathname === path, { timeout });
  await page.locator('main#main-content').waitFor({ state: 'visible', timeout });
}

async function scenario(browser, label, options, work) {
  const context = await browser.newContext({ ...options, reducedMotion: 'reduce', serviceWorkers: 'block' });
  const page = await context.newPage();
  const unexpected = [];
  const consoleChecks = [];
  const expectedStatuses = new Set();
  let expectedConsole = () => false;
  let offline = false;
  let closing = false;
  page.on('pageerror', (error) => unexpected.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const predicate = expectedConsole;
    consoleChecks.push((async () => {
      if (!await predicate(message)) unexpected.push(`console: ${message.text()}`);
    })());
  });
  page.on('response', (response) => {
    if (response.status() >= 400 && !expectedStatuses.has(`${new URL(response.url()).pathname}:${response.status()}`)) {
      unexpected.push(`HTTP ${response.status()}: ${response.url()}`);
    }
  });
  page.on('requestfailed', (request) => {
    if (!offline && !closing) unexpected.push(`requestfailed: ${request.url()} ${request.failure()?.errorText}`);
  });
  const allowed = (url) => url.protocol === 'http:' && url.hostname === '127.0.0.1'
    && [new URL(UI).port, new URL(API).port].includes(url.port);
  await context.route('**/*', async (route) => {
    let url = new URL(route.request().url());
    if (!allowed(url)) {
      unexpected.push(`Blocked external request: ${url.origin}${url.pathname}`);
      return route.abort();
    }
    try {
      for (let redirects = 0; redirects <= 8; redirects += 1) {
        const response = await route.fetch({ url: url.href, maxRedirects: 0 });
        const location = response.headers().location;
        if (![301, 302, 303, 307, 308].includes(response.status()) || !location) {
          return await route.fulfill({ response });
        }
        if (!['GET', 'HEAD'].includes(route.request().method()) || redirects === 8) {
          throw new Error(`Unsupported redirect from ${url.origin}${url.pathname}`);
        }
        url = new URL(location, url);
        if (!allowed(url)) throw new Error(`Blocked external redirect: ${url.origin}${url.pathname}`);
      }
    } catch (error) {
      if (!closing) unexpected.push(`Network guard: ${error.message.split('\n')[0]}`);
      await route.abort().catch(() => {});
    }
  });
  await context.routeWebSocket('**/*', (socket) => {
    const url = new URL(socket.url());
    if (url.protocol === 'ws:' && url.hostname === '127.0.0.1' && [new URL(UI).port, new URL(API).port].includes(url.port)) {
      socket.connectToServer();
    } else {
      unexpected.push(`Blocked external WebSocket: ${url.origin}${url.pathname}`);
      socket.close();
    }
  });
  try {
    await work(page, context, {
      expectedStatuses,
      allowConsole: (predicate) => { expectedConsole = predicate; },
      setOffline: async (value) => { offline = value; await context.setOffline(value); },
    });
  } catch (error) {
    unexpected.push(error.stack || String(error));
  } finally {
    await Promise.all(consoleChecks);
    closing = true;
    await context.close();
  }
  if (unexpected.length) {
    failures.push(`${label}\n${unexpected.join('\n')}`);
    console.error(`FAIL ${label}\n${unexpected.join('\n')}`);
  } else {
    console.log(`PASS ${label}`);
  }
}

async function keyboardAndDialog(page) {
  await loginUi(page, ...credentials.alliance);
  await open(page, '/alliance');
  const opener = page.getByRole('button', { name: 'Invitar Jugador' });
  await opener.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Invitar Jugador' });
  await dialog.waitFor({ state: 'visible', timeout });
  assert.equal(await dialog.getAttribute('aria-modal'), 'true');
  await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.contains(document.activeElement));
  await dialog.focus();
  await page.keyboard.press('Shift+Tab');
  await page.waitForFunction(() => document.activeElement?.textContent?.trim() === 'Cancelar');
  await page.keyboard.press('Tab');
  await page.waitForFunction(() => document.activeElement?.id === 'alliance-invite-search');
  await page.keyboard.press('Escape');
  await dialog.waitFor({ state: 'detached', timeout });
  await page.waitForFunction(() => document.activeElement?.textContent?.includes('Invitar Jugador'), null, { timeout });
}

async function mapRace(page) {
  const token = await loginUi(page, ...credentials.general);
  const { cities, worldId } = await playerSnapshot(token);
  assert.equal(cities.length, 1);
  const city = cities[0];
  await open(page, '/map');
  await page.waitForFunction(([x, y]) => document.querySelector('[data-testid="map-center"]')?.textContent.includes(`(${x}, ${y})`), [city.x, city.y], { timeout });
  await page.getByTestId(`map-tile-${city.x}-${city.y}`).waitFor({ state: 'visible', timeout });
  await page.locator('[data-testid="map-grid-panel"][aria-busy="false"]').waitFor({ state: 'visible', timeout });

  const first = { x: 10, y: 10 };
  const last = { x: 40, y: 40 };
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let arrived;
  const firstArrived = new Promise((resolve) => { arrived = resolve; });
  const matcher = (url, point) => url.origin === new URL(API).origin && url.pathname === '/map/tiles'
    && url.searchParams.get('world_id') === String(worldId)
    && url.searchParams.get('x') === String(point.x) && url.searchParams.get('y') === String(point.y);
  await page.route('**/map/tiles**', async (route) => {
    if (route.request().method() === 'GET' && matcher(new URL(route.request().url()), first)) {
      const response = await route.fetch({ maxRedirects: 0 });
      assert.equal(response.status(), 200, 'Held map response must be a real successful response, not a redirect');
      arrived();
      await gate;
      await route.fulfill({ response });
    } else {
      await route.fallback();
    }
  });
  const jump = async (point) => {
    await page.getByRole('spinbutton', { name: 'Coordenada X' }).fill(String(point.x));
    await page.getByRole('spinbutton', { name: 'Coordenada Y' }).fill(String(point.y));
    await page.getByRole('button', { name: 'Ir', exact: true }).click();
  };
  try {
    await jump(first);
    let timer;
    try {
      await Promise.race([firstArrived, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('First real map response did not arrive')), timeout);
      })]);
    } finally {
      clearTimeout(timer);
    }
    assert.equal(await page.getByTestId('map-grid-panel').getAttribute('aria-busy'), 'true');
    assert.equal(await page.getByTestId('map-empty').count(), 0);
    const latestResponse = page.waitForResponse((response) => response.request().method() === 'GET' && matcher(new URL(response.url()), last) && response.status() === 200, { timeout });
    await jump(last);
    const response = await latestResponse;
    const payload = await response.json();
    assert.ok(payload.tiles.length > 0, 'Real backend must supply tiles for the final center');
    await page.locator('[data-testid="map-grid-panel"][aria-busy="false"]').waitFor({ state: 'visible', timeout });
    await page.evaluate(() => {
      window.__g8StaleMapProcessed = false;
      const onRecovered = (event) => {
        if (event.detail?.path !== '/map/tiles') return;
        window.__g8StaleMapProcessed = true;
        window.removeEventListener('bm:service-recovered', onRecovered);
      };
      window.addEventListener('bm:service-recovered', onRecovered);
    });
    const staleResponse = page.waitForResponse((res) => res.request().method() === 'GET' && matcher(new URL(res.url()), first), { timeout });
    release();
    await (await staleResponse).finished();
    await page.waitForFunction(() => window.__g8StaleMapProcessed, null, { timeout });
    await page.evaluate(() => new Promise(requestAnimationFrame));
    await page.waitForFunction(([x, y]) => document.querySelector('[data-testid="map-center"]')?.textContent.includes(`(${x}, ${y})`), [last.x, last.y], { timeout });
    const rendered = await page.locator('[data-testid^="map-tile-"]').evaluateAll((nodes) => nodes.map((node) => node.dataset.mapCoordinate).sort());
    assert.deepEqual(rendered, payload.tiles.map((tile) => `${tile.x},${tile.y}`).sort(), 'Late response must not replace the final real map');
    assert.equal(await page.getByTestId('map-load-error').count(), 0);
  } finally {
    release();
    await page.unrouteAll({ behavior: 'wait' });
  }
}

async function outages(page, context, monitor) {
  await loginUi(page, ...credentials.general);
  for (const path of ['/message/inbox', '/report/']) monitor.expectedStatuses.add(`${path}:503`);
  monitor.allowConsole(async (message) => {
    const text = message.text();
    if (/Failed to load resource.*503|server responded with a status of 503/i.test(text)) return true;
    const args = message.args();
    for (const arg of args) {
      const info = await arg.evaluate((value) => ({
        status: value?.response?.status,
        path: value?.config?.url,
      })).catch(() => null);
      if (info?.status === 503 && ['/message/inbox', '/report/'].includes(info.path)) return true;
    }
    return false;
  });
  const failed = new Set(['/message/inbox', '/report/']);
  await page.route('**/*', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (new URL(route.request().url()).origin === new URL(API).origin && route.request().method() === 'GET' && failed.has(path)) {
      await route.fulfill({ status: 503, headers: { 'access-control-allow-origin': UI, 'access-control-allow-credentials': 'true' }, contentType: 'application/json', body: '{"detail":"Service unavailable"}' });
    } else {
      await route.fallback();
    }
  });
  await open(page, '/messages');
  await page.getByTestId('messages-load-error').waitFor({ state: 'visible', timeout });
  assert.equal(await page.getByTestId('messages-empty').count(), 0);
  await open(page, '/reports');
  await page.getByTestId('reports-load-error').waitFor({ state: 'visible', timeout });
  assert.equal(await page.getByTestId('reports-empty').count(), 0);
  assert.equal(await page.getByTestId('connection-status').getAttribute('data-state'), 'service');
  failed.delete('/report/');
  await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'GET' && new URL(response.url()).pathname === '/report/' && response.status() === 200, { timeout }),
    page.getByRole('button', { name: 'Reintentar reportes' }).click(),
  ]);
  await page.getByTestId('reports-load-error').waitFor({ state: 'detached', timeout });
  await page.getByTestId('reports-loading').waitFor({ state: 'detached', timeout });
  assert.equal(await page.getByTestId('connection-status').getAttribute('data-state'), 'service', 'Inbox outage remains after reports recover');
  failed.delete('/message/inbox');
  const inboxRecovery = page.waitForResponse((response) => response.request().method() === 'GET' && new URL(response.url()).pathname === '/message/inbox' && response.status() === 200, { timeout });
  await open(page, '/messages');
  await inboxRecovery;
  await page.getByTestId('connection-status').waitFor({ state: 'hidden', timeout });
}

async function sessionAndReconnect(page, context, monitor) {
  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Entrar', exact: true }).waitFor({ state: 'visible', timeout });
  await page.waitForLoadState('networkidle');
  await monitor.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await page.waitForFunction(() => document.querySelector('[data-testid="connection-status"]')?.dataset.state === 'offline', null, { timeout });
  await monitor.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.waitForFunction(() => document.querySelector('[data-testid="connection-status"]')?.dataset.state !== 'offline', null, { timeout });
  await loginUi(page, ...credentials.general);
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => localStorage.setItem('bm_token', 'invalid.jwt.token'));
  monitor.expectedStatuses.add('/auth/me:401');
  monitor.expectedStatuses.add('/tutorial/status:401');
  monitor.allowConsole((message) => /Failed to load resource.*401|server responded with a status of 401|Socket connection error:.*authentication failed/i.test(message.text()));
  await page.goto(`${UI}/profile`, { waitUntil: 'domcontentloaded' });
  await page.waitForURL((url) => url.pathname === '/login', { timeout });
  await page.getByTestId('session-expired').waitFor({ state: 'visible', timeout });
  assert.equal(await page.evaluate(() => localStorage.getItem('bm_token')), null);
  await loginUi(page, ...credentials.general);
  assert.equal(await page.getByTestId('session-expired').count(), 0);
}

for (const name of selected) {
  const type = { webkit, firefox }[name];
  if (!existsSync(type.executablePath())) {
    console.log(`SKIP ${name}: executable missing at ${type.executablePath()}`);
    continue;
  }
  let browser;
  try {
    browser = await type.launch({ headless: true });
  } catch (error) {
    failures.push(`${name} launch failed: ${error.message}`);
    continue;
  }
  try {
    for (const [view, options] of [
      ['desktop', { viewport: { width: 1440, height: 900 } }],
      ['mobile', { viewport: { width: 390, height: 844 }, hasTouch: true }],
    ]) {
      for (const [scenarioName, work] of Object.entries({ keyboardAndDialog, mapRace, outages, sessionAndReconnect })) {
        executed += 1;
        await scenario(browser, `${name}/${view}/${scenarioName}`, options, work);
      }
    }
  } finally {
    await browser.close();
  }
}
console.log(`G8_SUMMARY executed=${executed} failed=${failures.length}`);
if (!executed || failures.length) process.exitCode = 1;
