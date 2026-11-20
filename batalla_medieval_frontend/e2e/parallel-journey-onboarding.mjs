import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { API, UI, assertIsolated, call, loginUi, playerSnapshot, suite, verificationTokenFor } from './parallel-journey-helpers.mjs';

assertIsolated();
const journey = suite('onboarding');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(error.message));
const username = `pj_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
const email = `${username}@example.com`;
const password = 'Journey-Isolated-2026!42';
let accessToken;
let worldId;
let startingCityId;
try {
  await journey.check('register through real browser and block unverified login', async () => {
    await page.goto(`${UI}/register`, { waitUntil: 'domcontentloaded' });
    const fields = page.locator('form input');
    await fields.nth(0).fill(username);
    await fields.nth(1).fill(email);
    await fields.nth(2).fill(password);
    await page.getByRole('button', { name: 'Crear cuenta' }).click();
    await page.getByText('¡Registro Exitoso!').waitFor({ timeout: 15000 });
    await call('/auth/token', {
      method: 'POST', form: true, body: { username, password }, expected: 403,
    });
    await call('/auth/register', {
      method: 'POST', expected: 400, body: { username, email, password },
    });
    await call('/auth/register', {
      method: 'POST', expected: 422, body: {
        username: `bad_${username}`, email: `bad_${email}`, password: 'short',
      },
    });
  });

  await journey.check('verify using the one-use link from isolated test DB', async () => {
    const verificationToken = verificationTokenFor(username);
    await call('/auth/verify-email?token=invalid-test-token', { method: 'POST', expected: 400 });
    await page.goto(`${UI}/verify-email?token=${encodeURIComponent(verificationToken)}`, { waitUntil: 'domcontentloaded' });
    await page.getByText('¡Correo Verificado!').waitFor({ timeout: 15000 });
    await call(`/auth/verify-email?token=${encodeURIComponent(verificationToken)}`, { method: 'POST', expected: 400 });
    await call('/auth/token', {
      method: 'POST', form: true, body: { username, password: 'wrong-password' }, expected: 401,
    });
  });

  await journey.check('login, join world and receive exactly one capital', async () => {
    accessToken = await loginUi(page, username, password);
    const available = await call('/worlds/active', { token: accessToken });
    const world = available.worlds.find((item) => item.lifecycle_status === 'open');
    assert.ok(world, 'Canonical seed has no open world');
    worldId = world.id;
    const selector = page.getByTestId(`world-selector-${worldId}`);
    await selector.waitFor({ state: 'visible', timeout: 15000 });
    await selector.getByRole('button', { name: 'Unirse' }).click();
    await page.waitForFunction((id) => {
      return document.querySelector(`[data-testid="world-selector-${id}"]`)?.getAttribute('aria-current') === 'true';
    }, worldId, { timeout: 15000 });
    const snapshot = await playerSnapshot(accessToken, worldId);
    assert.equal(snapshot.profile.world_id, worldId);
    assert.equal(snapshot.cities.length, 1, 'New player must receive exactly one starting capital');
    assert.equal(snapshot.cities[0].settlement_type, 'city');
    startingCityId = snapshot.cities[0].id;
    const joinedAgain = await call(`/worlds/${worldId}/join`, { method: 'POST', token: accessToken });
    assert.equal(joinedAgain.starting_city_id, startingCityId, 'Rejoin must be idempotent');
    assert.equal((await call(`/city/?world_id=${worldId}`, { token: accessToken })).length, 1);
    await call('/city/', {
      method: 'POST', token: accessToken, expected: 409,
      body: { name: 'Forbidden extra capital', world_id: worldId, x: 0, y: 0 },
    });
    assert.equal((await call(`/city/?world_id=${worldId}`, { token: accessToken })).length, 1);
  });

  await journey.check('persist world, capital, resources and protected navigation across reload', async () => {
    assert.ok(accessToken && startingCityId);
    const initial = await call(`/city/${startingCityId}/status?world_id=${worldId}`, { token: accessToken });
    assert.equal(initial.city_id, startingCityId);
    for (const field of ['wood', 'stone', 'iron', 'gold']) {
      assert.ok(Number.isFinite(Number(initial[field])), `Missing ${field} on capital`);
    }
    assert.equal(typeof initial.production_per_hour, 'object');
    for (const path of ['/buildings', '/troops', '/academy', '/map']) {
      await page.goto(`${UI}${path}`, { waitUntil: 'domcontentloaded' });
      await page.waitForURL((url) => url.pathname === path, { timeout: 12000 });
      assert.equal(await page.getByText('Tu sesión ha expirado.').count(), 0, `Unexpected session expiry on ${path}`);
    }
    await page.goto(`${UI}/`, { waitUntil: 'domcontentloaded' });
    await page.reload({ waitUntil: 'domcontentloaded' });
    const after = await playerSnapshot(accessToken, worldId);
    assert.equal(after.profile.world_id, worldId);
    assert.deepEqual(after.cities.map((city) => city.id), [startingCityId]);
    assert.equal(after.cities[0].world_id, worldId);
  });

  await journey.check('browser runtime remains free of uncaught errors', async () => {
    assert.deepEqual(pageErrors, []);
  });
} finally {
  await browser.close();
}
journey.finish();
console.log(`ONBOARDING_VERIFIED username=${username} world=${worldId} city=${startingCityId} api=${API}`);
