import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

export const UI = process.env.E2E_BASE_URL || 'http://127.0.0.1:4273';
export const API = process.env.VITE_API_URL || 'http://127.0.0.1:8108';

export function assertIsolated() {
  assert.equal(process.env.APP_ENV, 'test', 'Refusing E2E mutations outside APP_ENV=test');
  assert.equal(process.env.PARALLEL_JOURNEY_ALLOW_MUTATIONS, 'isolated', 'Explicit isolated test opt-in is required');
  for (const value of [UI, API]) {
    const url = new URL(value);
    assert.equal(url.protocol, 'http:', 'Use local HTTP only');
    assert.equal(url.hostname, '127.0.0.1', 'E2E must not contact external or production services');
    assert.ok(Number(url.port) >= 1024, 'E2E uses unprivileged dedicated ports');
  }
  const database = process.env.PARALLEL_JOURNEY_DB;
  assert.ok(database && resolve(database).startsWith('/tmp/medievol-journey-'), 'Use an explicit disposable SQLite database under /tmp/medievol-journey-*');
  assert.equal(process.env.DATABASE_URL, `sqlite:///${resolve(database)}`, 'App and tests must point to the same isolated SQLite database');
  return resolve(database);
}

export async function call(path, { method = 'GET', token, body, expected = 200, form = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = form ? 'application/x-www-form-urlencoded' : 'application/json';
  const response = await fetch(new URL(path, API), {
    method, headers,
    body: body === undefined ? undefined : (form ? new URLSearchParams(body).toString() : JSON.stringify(body)),
    signal: AbortSignal.timeout(12000),
  });
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  assert.equal(response.status, expected,
    `${method} ${path}: expected ${expected}, got ${response.status}; ${String(text).slice(0, 500)}`);
  return data;
}

export async function tokenFor(username, password) {
  const result = await call('/auth/token', {
    method: 'POST', form: true, body: { username, password }, expected: 200,
  });
  assert.ok(result.access_token, 'Authentication did not return an access token');
  return result.access_token;
}

export function verificationTokenFor(username) {
  const db = assertIsolated();
  assert.match(username, /^[a-z0-9_]{3,50}$/);
  const script = [
    'import sqlite3,sys',
    'db=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True)',
    'row=db.execute("select verification_token from users where username=?",(sys.argv[2],)).fetchone()',
    'if not row or not row[0]: sys.exit(2)',
    'print(row[0])',
  ].join('\n');
  // Read ONLY from the disposable test database. Never query SMTP or external inboxes.
  return execFileSync('python3', ['-c', script, db, username], { encoding: 'utf8', timeout: 5000 }).trim();
}

export async function loginUi(page, username, password) {
  await page.goto(`${UI}/login`, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Entrar', exact: true }).waitFor({ state: 'visible', timeout: 15000 });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(username);
  await inputs.nth(1).fill(password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((url) => url.pathname === '/', { timeout: 20000 });
  await page.getByText(`Ciudad de ${username}`).waitFor({ state: 'visible', timeout: 15000 });
  const storedToken = await page.evaluate(() => localStorage.getItem('bm_token'));
  assert.ok(storedToken, 'UI login did not persist access token');
  return storedToken;
}

export async function playerSnapshot(token, worldId) {
  const profile = await call('/auth/me', { token });
  const selected = worldId ?? profile.world_id;
  assert.ok(selected, 'No selected world in authenticated profile');
  const cities = await call(`/city/?world_id=${selected}`, { token });
  const movements = await call(`/movement/?world_id=${selected}`, { token });
  const reports = await call(`/report/?world_id=${selected}`, { token });
  return { profile, cities, movements, reports, worldId: selected };
}

export function suite(name) {
  const results = [];
  return {
    async check(label, work) {
      try {
        await work();
        results.push({ label, status: 'PASS' });
        console.log(`PASS ${name} / ${label}`);
      } catch (error) {
        results.push({ label, status: 'FAIL', error: error.stack || String(error) });
        console.error(`FAIL ${name} / ${label}: ${error.stack || error}`);
      }
    },
    finish() {
      const count = results.filter((result) => result.status === 'PASS').length;
      const failed = results.filter((result) => result.status === 'FAIL');
      console.log(`JOURNEY_SUMMARY ${JSON.stringify({ name, passed: count, failed: failed.length, results })}`);
      assert.equal(failed.length, 0, `${name} has ${failed.length} failing cases (see above)`);
    },
  };
}
