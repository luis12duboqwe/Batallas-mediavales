import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

// Manual privacy intake must not perform account deletion.
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (err) => errors.push(err.message));

try {
  const anonymousGet = await context.request.get(API_URL + '/auth/me/privacy-requests');
  const anonymousPost = await context.request.post(API_URL + '/auth/me/privacy-requests', {
    data: { kind: 'erasure' },
  });
  assert.equal(anonymousGet.status(), 401);
  assert.equal(anonymousPost.status(), 401);

  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g2_browser');
  await page.locator('form input').nth(1).fill('G2-Browser-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 15000 });
  await page.goto(BASE_URL + '/profile', { waitUntil: 'domcontentloaded' });

  await page.getByTestId('privacy-kind').selectOption('erasure');
  await page.getByTestId('privacy-details').fill('Solicito revisión manual.');
  const [createdResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/auth/me/privacy-requests') &&
      response.request().method() === 'POST', { timeout: 15000 }),
    page.getByTestId('privacy-submit').click(),
  ]);
  assert.equal(createdResponse.status(), 200);
  const created = await createdResponse.json();
  assert.equal(created.kind, 'erasure');
  assert.equal(created.status, 'open');
  const caseRow = page.getByTestId('privacy-case-' + created.id);
  await caseRow.waitFor({ state: 'visible', timeout: 15000 });
  assert.match(await caseRow.innerText(), /Recibida/);
  assert.match(await page.getByTestId('privacy-success').innerText(), /no se ha eliminado ni modificado/);

  const [repeatedResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/auth/me/privacy-requests') &&
      response.request().method() === 'POST', { timeout: 15000 }),
    page.getByTestId('privacy-submit').click(),
  ]);
  assert.equal((await repeatedResponse.json()).id, created.id);
  assert.equal(await page.locator('[data-testid^="privacy-case-"]').count(), 1);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.getByTestId('privacy-case-' + created.id).waitFor({ timeout: 15000 });
  await page.getByText('g2_browser').first().waitFor();
  assert.equal(await page.getByTestId('privacy-error').count(), 0);
  assert.deepEqual(errors, []);
  console.log('G29 BM-0090 passed: auth, human review intake, dedupe, persistence, account intact');
} finally {
  await browser.close();
}
