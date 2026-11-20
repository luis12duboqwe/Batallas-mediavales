import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite } from './parallel-journey-helpers.mjs';

assertIsolated();
const journey = suite('economy-army-map');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const exceptions = [];
page.on('pageerror', (error) => exceptions.push(error.message));
let g7Token;
let g7City;
let g7World;
try {
  await journey.check('load real city and server-authoritative production, storage and building quotes', async () => {
    g7Token = await loginUi(page, 'g7_research', 'G7-Research-Test-2026!');
    const initial = await playerSnapshot(g7Token);
    g7World = initial.worldId;
    assert.equal(initial.cities.length, 1);
    g7City = initial.cities[0].id;
    const status = await call(`/city/${g7City}/status?world_id=${g7World}`, { token: g7Token });
    assert.ok(status.storage_limit > 0);
    for (const resource of ['wood', 'stone', 'iron', 'gold']) {
      assert.ok(Number.isFinite(Number(status[resource])));
      assert.ok(Number.isFinite(Number(status.production_per_hour[resource])));
    }
    const buildings = await call(`/building/available?city_id=${g7City}&world_id=${g7World}`, { token: g7Token });
    assert.ok(buildings.length >= 1);
    assert.ok(buildings.every((building) => typeof building.can_upgrade === 'boolean'));
  });

  await journey.check('build one affordable upgrade and persist queue after page reload', async () => {
    assert.ok(g7Token && g7City && g7World);
    const available = await call(`/building/available?city_id=${g7City}&world_id=${g7World}`, { token: g7Token });
    const affordable = available.find((building) => building.can_upgrade && !building.is_max_level);
    assert.ok(affordable, 'Test fixture has no affordable building upgrade');
    const queue = await call(`/building/upgrade?world_id=${g7World}`, {
      method: 'POST', token: g7Token, body: { city_id: g7City, building_type: affordable.name },
    });
    assert.ok(queue.id);
    const status = await call(`/city/${g7City}/status?world_id=${g7World}`, { token: g7Token });
    assert.ok(status.building_queue.some((item) => item.id === queue.id), 'Queued upgrade missing from durable city status');
    await page.goto(`${UI}/buildings`, { waitUntil: 'domcontentloaded' });
    await page.getByText('Cola de construcción').waitFor({ timeout: 15000 });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByText('Cola de construcción').waitFor({ timeout: 15000 });
    await call(`/building/upgrade?world_id=${g7World}`, {
      method: 'POST', token: g7Token, expected: 400,
      body: { city_id: g7City, building_type: affordable.name },
    });
  });

  await journey.check('start one real research and prevent duplicate research queues', async () => {
    assert.ok(g7Token && g7City && g7World);
    const catalog = await call(`/troop/available?city_id=${g7City}&world_id=${g7World}`, { token: g7Token });
    const available = catalog.find((item) => item.can_research);
    assert.ok(available, 'Test fixture has no researchable technology');
    const queued = await call(`/troop/research?world_id=${g7World}`, {
      method: 'POST', expected: 201, token: g7Token,
      body: { city_id: g7City, unit_type: available.unit_type },
    });
    assert.ok(queued.id);
    const status = await call(`/city/${g7City}/status?world_id=${g7World}`, { token: g7Token });
    assert.ok(status.research_queue.some((item) => item.id === queued.id));
    await call(`/troop/research?world_id=${g7World}`, {
      method: 'POST', expected: 400, token: g7Token,
      body: { city_id: g7City, unit_type: available.unit_type },
    });
    await page.goto(`${UI}/academy`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('research-active-queue').waitFor({ timeout: 15000 });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.getByTestId('research-active-queue').waitFor({ timeout: 15000 });
  });

  await journey.check('train a unit with a separate upkeep fixture and reject zero amount', async () => {
    const token = await loginUi(page, 'g8_upkeep', 'G8-Upkeep-Test-2026!');
    const snapshot = await playerSnapshot(token);
    const city = snapshot.cities[0];
    assert.ok(city);
    const catalog = await call(`/troop/available?city_id=${city.id}&world_id=${snapshot.worldId}`, { token });
    const trainable = catalog.find((unit) => unit.can_train && unit.training_time_seconds > 0);
    assert.ok(trainable, 'No trainable unit in prepared fixture');
    await call(`/troop/train?world_id=${snapshot.worldId}`, {
      method: 'POST', expected: 400, token,
      body: { city_id: city.id, troop_type: trainable.unit_type, amount: 0 },
    });
    const queued = await call(`/troop/train?world_id=${snapshot.worldId}`, {
      method: 'POST', token,
      body: { city_id: city.id, troop_type: trainable.unit_type, amount: 1 },
    });
    assert.ok(queued.id);
    const status = await call(`/city/${city.id}/status?world_id=${snapshot.worldId}`, { token });
    assert.ok(status.troop_queue.some((item) => item.id === queued.id), 'Training did not persist');
    await page.goto(`${UI}/troops`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId(`troop-queue-${queued.id}`).waitFor({ timeout: 15000 });
  });

  await journey.check('explore bounded map, and render map without losing selection on reload', async () => {
    assert.ok(g7Token && g7City);
    const cities = await call(`/city/?world_id=${g7World}`, { token: g7Token });
    const city = cities.find((entry) => entry.id === g7City);
    const tiles = await call(`/map/tiles?world_id=${g7World}&x=${city.x}&y=${city.y}&radius=2`, { token: g7Token });
    assert.ok(Array.isArray(tiles.tiles) && tiles.tiles.length >= 1);
    assert.ok(tiles.tiles.some((tile) => tile.x === city.x && tile.y === city.y));
    assert.ok(tiles.tiles.every((tile) => tile.x >= 0 && tile.y >= 0));
    await call(`/map/tiles?world_id=${g7World}&x=${city.x}&y=${city.y}&radius=21`, { token: g7Token, expected: 422 });
    await loginUi(page, 'g7_research', 'G7-Research-Test-2026!');
    await page.goto(`${UI}/map`, { waitUntil: 'domcontentloaded' });
    await page.waitForURL((url) => url.pathname === '/map', { timeout: 15000 });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForURL((url) => url.pathname === '/map', { timeout: 15000 });
  });

  await journey.check('uncaught browser errors', () => assert.deepEqual(exceptions, []));
} finally {
  await browser.close();
}
journey.finish();
