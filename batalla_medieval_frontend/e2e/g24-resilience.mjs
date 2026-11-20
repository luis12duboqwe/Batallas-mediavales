import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const errors = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.on('pageerror', (error) => errors.push(error.message));

try {
  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Entrar', exact: true }).waitFor({ state: 'visible' });

  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await page.getByTestId('connection-status').waitFor({ state: 'visible' });
  assert.equal(await page.getByTestId('connection-status').getAttribute('data-state'), 'offline');
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.getByTestId('connection-status').waitFor({ state: 'hidden' });

  await page.evaluate(() => window.dispatchEvent(new CustomEvent('bm:service-unavailable', { detail: { path: '/test-outage' } })));
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('bm:service-unavailable', { detail: { path: '/second-outage' } })));
  await page.getByTestId('connection-status').waitFor({ state: 'visible' });
  assert.equal(await page.getByTestId('connection-status').getAttribute('data-state'), 'service');
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('bm:service-recovered', { detail: { path: '/unrelated' } })));
  assert.equal(await page.getByTestId('connection-status').getAttribute('data-state'), 'service');
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('bm:service-recovered', { detail: { path: '/test-outage' } })));
  assert.equal(await page.getByTestId('connection-status').getAttribute('data-state'), 'service', 'Another endpoint is still unavailable');
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('bm:service-recovered', { detail: { path: '/second-outage' } })));
  await page.getByTestId('connection-status').waitFor({ state: 'hidden' });

  // Reproduce a stored, expired token on a hard reload of a protected route.
  await page.evaluate(() => localStorage.setItem('bm_token', 'invalid.jwt.token'));
  await page.goto(BASE_URL + '/profile', { waitUntil: 'domcontentloaded' });
  await page.waitForURL((url) => url.pathname === '/login', { timeout: 25000 });
  await page.getByTestId('session-expired').waitFor({ state: 'visible' });
  const storedToken = await page.evaluate(() => localStorage.getItem('bm_token'));
  assert.equal(storedToken, null, 'Invalid session token must be purged');
  assert.equal(await page.getByTestId('session-expired').innerText(), 'Tu sesión ha expirado. Vuelve a iniciar sesión.');

  assert.deepEqual(errors, [], 'Browser must not throw during recovery');
  console.log('BM-0084 browser resilience passed: offline/online, service retry signal, stale JWT and Spanish session expiry');
} finally {
  await browser.close();
}
