import fs from 'node:fs';
import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const ADMIN_TOKEN = fs.readFileSync('/tmp/g18-admin-token', 'utf8').trim();
const PLAYER_TOKEN = fs.readFileSync('/tmp/g18-player-token', 'utf8').trim();
const VIOLATION_TYPE = 'rate_limit:g18.browser';
const failures = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') failures.push(`console.error: ${message.text()}`);
});
page.on('response', (response) => {
  if (response.status() >= 500) failures.push(`HTTP ${response.status()}: ${response.url()}`);
});

async function waitForExperienceReady() {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  const loading = page.getByTestId('loading-screen');
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
}

async function api(path, options = {}) {
  const headers = {
    Authorization: `Bearer ${options.token || ADMIN_TOKEN}`,
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  const requestOptions = { method: options.method || 'GET', headers };
  if (options.data) requestOptions.data = options.data;
  const response = await context.request.fetch(`${API_URL}${path}`, requestOptions);
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  return { status: response.status(), body };
}

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((token) => localStorage.setItem('bm_token', token), ADMIN_TOKEN);
  await page.goto(`${BASE_URL}/admin`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  await page.getByTestId('bm0073-admin-panel').waitFor({ state: 'visible', timeout: 10000 });

  const flags = await api(`/anticheat/flags?violation_type=${encodeURIComponent(VIOLATION_TYPE)}&limit=10`);
  if (flags.status !== 200) throw new Error(`flag catalogue failed: ${flags.status}`);
  const flag = flags.body?.find((row) => row.type_of_violation === VIOLATION_TYPE);
  if (!flag) throw new Error('G18 anti-cheat flag missing');
  if (flag.resolved_status !== 'pending' || flag.reviewed_by_admin !== false) {
    failures.push(`Detection was not pending human review: ${JSON.stringify(flag)}`);
  }

  const playerBefore = await api('/auth/me', { token: PLAYER_TOKEN });
  if (playerBefore.status !== 200 || playerBefore.body?.is_frozen !== false) {
    failures.push(`Detection sanctioned player automatically: ${JSON.stringify(playerBefore.body)}`);
  }

  const reviewReason = 'G18 confirmed automated abuse test';
  const reviewed = await api(`/anticheat/resolve/${flag.id}`, {
    method: 'PATCH',
    headers: { 'X-Admin-Reason': reviewReason },
    data: { resolved_status: 'confirmed' },
  });
  if (reviewed.status !== 200) throw new Error(`flag review failed: ${reviewed.status}`);
  if (
    reviewed.body?.resolved_status !== 'confirmed'
    || reviewed.body?.reviewed_by_admin !== true
    || !reviewed.body?.reviewed_at
    || reviewed.body?.resolution_reason !== reviewReason
  ) {
    failures.push(`Human review metadata incomplete: ${JSON.stringify(reviewed.body)}`);
  }

  const playerAfterReview = await api('/auth/me', { token: PLAYER_TOKEN });
  if (playerAfterReview.status !== 200 || playerAfterReview.body?.is_frozen !== false) {
    failures.push('Review alone changed account access');
  }

  const sanctionReason = 'G18 manual sanction after confirmed review';
  const frozen = await api(`/admin/user/${flag.user_id}/freeze`, {
    method: 'PATCH',
    data: { is_frozen: true, reason: sanctionReason },
  });
  if (frozen.status !== 200 || frozen.body?.is_frozen !== true) {
    failures.push(`Manual sanction failed: ${JSON.stringify(frozen.body)}`);
  }

  const revoked = await api('/auth/me', { token: PLAYER_TOKEN });
  if (revoked.status !== 401) {
    failures.push(`Pre-sanction player session was not revoked: ${revoked.status}`);
  }

  const audit = await api('/admin/logs?limit=100');
  if (!audit.body?.some((row) => row.action === 'resolve_anticheat_flag' && row.reason === reviewReason)) {
    failures.push('Anti-cheat review audit entry missing');
  }
  if (!audit.body?.some((row) => row.action === 'set_user_freeze' && row.reason === sanctionReason)) {
    failures.push('Manual sanction audit entry missing');
  }

  const cleanup = await api(`/admin/user/${flag.user_id}/freeze`, {
    method: 'PATCH',
    data: { is_frozen: false, reason: 'G18 cleanup after manual sanction test' },
  });
  if (cleanup.status !== 200 || cleanup.body?.is_frozen !== false) {
    failures.push(`G18 cleanup failed: ${JSON.stringify(cleanup.body)}`);
  }
} catch (error) {
  failures.push(`journey-error: ${error.stack || error.message}`);
} finally {
  await context.close();
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G18 BM-0074 anti-cheat abuse protection browser journey passed');
