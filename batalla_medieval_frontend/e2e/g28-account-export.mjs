import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ acceptDownloads: true, reducedMotion: 'reduce' });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));

try {
  // A direct, unauthenticated request cannot reveal an account export.
  const unauthenticated = await context.request.get(API_URL + '/auth/me/export');
  assert.equal(unauthenticated.status(), 401);

  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g2_browser');
  await page.locator('form input').nth(1).fill('G2-Browser-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 15000 });
  await page.goto(BASE_URL + '/profile', { waitUntil: 'domcontentloaded' });
  const exportButton = page.getByTestId('account-export');
  await exportButton.waitFor({ state: 'visible', timeout: 15000 });

  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    exportButton.click(),
  ]);
  assert.equal(download.suggestedFilename(), 'medievol-datos-cuenta.json');
  const payload = JSON.parse(await readFile(await download.path(), 'utf8'));
  assert.equal(payload.schema_version, 1);
  assert.equal(payload.account.username, 'g2_browser');
  assert.ok(Array.isArray(payload.cities));
  assert.ok(Array.isArray(payload.messages));
  assert.ok(Array.isArray(payload.world_memberships));
  const serialized = JSON.stringify(payload);
  for (const sensitiveField of [
    'hashed_password', 'password_reset_token', 'verification_token', 'auth_version',
  ]) assert.ok(!serialized.includes(sensitiveField), 'Secret field leaked: ' + sensitiveField);
  assert.equal(await page.getByTestId('account-export-error').count(), 0);
  assert.deepEqual(errors, []);
  console.log('G28 BM-0090 passed: authenticated download, owned-data format and no credential fields');
} finally {
  await browser.close();
}
