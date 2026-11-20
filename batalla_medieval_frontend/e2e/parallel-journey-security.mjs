import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite, tokenFor } from './parallel-journey-helpers.mjs';

assertIsolated();
const journey = suite('reports-isolation-recovery');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const exceptions = [];
page.on('pageerror', (error) => exceptions.push(error.message));
let token;
let worldA;
let worldB;
let cityA;
let cityB;
try {
  await journey.check('resolve combat fixture: battle audit, losses and return march survive browser navigation', async () => {
    const combatToken = await loginUi(page, 'g9_combat', 'G9-Combat-Test-2026!');
    const snapshot = await playerSnapshot(combatToken);
    const battle = snapshot.reports.filter((report) => report.report_type === 'battle')
      .map((report) => { try { return JSON.parse(report.content); } catch { return null; } })
      .find((payload) => payload?.combat?.seed);
    assert.ok(battle, 'Prepared combat fixture lacks an auditable report');
    assert.match(battle.combat.seed, /^[a-f0-9]{64}$/i);
    assert.ok(battle.combat.round_count >= 1);
    assert.equal(battle.combat.rounds.length, battle.combat.round_count);
    assert.ok(snapshot.movements.some((item) => item.movement_type === 'attack' && item.status === 'completed'));
    assert.ok(snapshot.movements.some((item) => item.movement_type === 'return'));
    await page.goto(`${UI}/reports`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('combat-audit').waitFor({ timeout: 15000 });
    assert.equal(await page.getByTestId('combat-audit').getAttribute('data-combat-seed'), battle.combat.seed);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByTestId('combat-audit').waitFor({ timeout: 15000 });
  });

  await journey.check('resolve espionage fixture: authoritative intel agrees with reports UI', async () => {
    const spyToken = await loginUi(page, 'g10_espionage', 'G10-Espionage-Test-2026!');
    const snapshot = await playerSnapshot(spyToken);
    const spy = snapshot.reports.filter((report) => report.report_type === 'spy')
      .map((report) => { try { return JSON.parse(report.content); } catch { return null; } })
      .find((payload) => payload?.algorithm_version && payload?.seed);
    assert.ok(spy, 'Prepared espionage fixture lacks an auditable report');
    assert.match(spy.seed, /^[a-f0-9]{64}$/i);
    assert.ok(snapshot.movements.some((item) => item.movement_type === 'spy' && item.status === 'completed'));
    await page.goto(`${UI}/reports`, { waitUntil: 'domcontentloaded' });
    const heading = page.getByText('Espionaje en G10 Intelligence Target', { exact: true });
    await heading.waitFor({ timeout: 15000 });
    await heading.click();
    const report = heading.locator('xpath=ancestor::*[contains(@class,"card")][1]');
    const audit = report.getByTestId('spy-audit');
    await audit.waitFor({ timeout: 10000 });
    assert.equal(await audit.getAttribute('data-spy-seed'), spy.seed);
  });

  await journey.check('deny unaffiliated access to other-world map before membership', async () => {
    token = await tokenFor('g2_browser', 'G2-Browser-Test-2026!');
    const me = await call('/auth/me', { token });
    worldA = me.world_id;
    assert.ok(worldA);
    const worlds = await call('/worlds/active', { token });
    worldB = worlds.worlds.find((item) => item.name === 'Parallel Journey World B')?.id;
    assert.ok(worldB && worldB !== worldA, 'Second isolated world fixture missing');
    const first = await playerSnapshot(token, worldA);
    cityA = first.cities[0]?.id;
    assert.ok(cityA);
    await call(`/map/tiles?world_id=${worldB}&x=1&y=1&radius=1`, { token, expected: 403 });
    await call(`/building/available?city_id=${cityA}&world_id=${worldB}`, { token, expected: 404 });
    await call(`/troop/available?city_id=${cityA}&world_id=${worldB}`, { token, expected: 404 });
    assert.deepEqual(await call(`/city/?world_id=${worldB}`, { token }), []);
    assert.deepEqual(await call(`/report/?world_id=${worldB}`, { token }), []);
  });

  await journey.check('join second world, preserve distinct capitals, and reject mixed-world attack and spy', async () => {
    assert.ok(token && cityA && worldA && worldB);
    const before = await playerSnapshot(token, worldA);
    const membership = await call(`/worlds/${worldB}/join`, { token, method: 'POST' });
    cityB = membership.starting_city_id;
    assert.ok(cityB && cityB !== cityA);
    const second = await playerSnapshot(token, worldB);
    assert.equal(second.cities.length, 1);
    assert.equal(second.cities[0].id, cityB);
    const beforeA = before.movements.map((move) => move.id);
    const beforeB = second.movements.map((move) => move.id);
    await call(`/city/${cityA}?world_id=${worldB}`, { token, expected: 404 });
    await call(`/city/${cityB}?world_id=${worldA}`, { token, expected: 404 });
    await call('/movement/', {
      method: 'POST', token, expected: 404,
      body: { origin_city_id: cityA, target_city_id: cityB, world_id: worldA,
        movement_type: 'attack', troops: { basic_infantry: 1 } },
    });
    await call('/movement/', {
      method: 'POST', token, expected: 404,
      body: { origin_city_id: cityA, target_city_id: cityB, world_id: worldB,
        movement_type: 'spy', spy_count: 1 },
    });
    assert.deepEqual((await call(`/movement/?world_id=${worldA}`, { token })).map((move) => move.id), beforeA);
    assert.deepEqual((await call(`/movement/?world_id=${worldB}`, { token })).map((move) => move.id), beforeB);
    assert.equal((await call(`/city/?world_id=${worldA}`, { token })).find((city) => city.id === cityA)?.id, cityA);
    assert.equal((await call(`/city/?world_id=${worldB}`, { token })).find((city) => city.id === cityB)?.id, cityB);
  });

  await journey.check('simulate map request failure and verify explicit retry', async () => {
    await loginUi(page, 'g2_browser', 'G2-Browser-Test-2026!');
    let intercepted = 0;
    const reject = (route) => { intercepted += 1; route.abort('failed'); };
    await page.route(/\/map\/tiles\?/, reject);
    await page.goto(`${UI}/map`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('map-load-error').waitFor({ timeout: 15000 });
    assert.ok(intercepted >= 1, 'Fault injection did not intercept a map request');
    await page.unroute(/\/map\/tiles\?/, reject);
    await page.getByRole('button', { name: 'Reintentar mapa' }).click();
    await page.getByTestId('map-load-error').waitFor({ state: 'hidden', timeout: 15000 });
    await page.getByTestId('map-grid-content').waitFor({ state: 'visible', timeout: 15000 });
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));
    await page.getByTestId('connection-status').waitFor({ state: 'visible', timeout: 8000 });
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await page.getByTestId('connection-status').waitFor({ state: 'hidden', timeout: 8000 });
  });

  await journey.check('reject expired browser token, purge storage and show relogin', async () => {
    await page.evaluate(() => localStorage.setItem('bm_token', 'invalid.jwt.token'));
    await page.goto(`${UI}/profile`, { waitUntil: 'domcontentloaded' });
    await page.waitForURL((url) => url.pathname === '/login', { timeout: 25000 });
    await page.getByTestId('session-expired').waitFor({ timeout: 8000 });
    assert.equal(await page.evaluate(() => localStorage.getItem('bm_token')), null);
    await loginUi(page, 'g2_browser', 'G2-Browser-Test-2026!');
    const me = await call('/auth/me', { token: await tokenFor('g2_browser', 'G2-Browser-Test-2026!') });
    assert.equal(me.world_id, worldB);
  });

  await journey.check('uncaught page errors', () => assert.deepEqual(exceptions, []));
} finally {
  await browser.close();
}
journey.finish();
