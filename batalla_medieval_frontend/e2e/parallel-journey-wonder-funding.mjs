import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite, tokenFor } from './parallel-journey-helpers.mjs';

// Every request below is confined to the current throwaway SQLite database and
// 127.0.0.1 servers. The worker fixture refuses production/staging databases.
assertIsolated();
const checks = suite('wonder-v2-real-browser');
const browser = await chromium.launch({ headless: true });
const ownerPage = await browser.newPage();
const donorPage = await browser.newPage();
const strangerPage = await browser.newPage();
const legacyPage = await browser.newPage();
const pages = [ownerPage, donorPage, strangerPage, legacyPage];
const jsErrors = [];
for (const page of pages) page.on('pageerror', error => jsErrors.push(error.message));

const partial = { wood: 5000, stone: 5000, iron: 5000, gold: 1250 };
let ownerToken, donorToken, strangerToken, enemyToken, legacyToken;
let worldId, legacyWorldId, targetId, donorCityId, poorCityId, enemyCityId, legacyOtherCity;

const fundingPath = (world, city) =>
  '/building/wonder/funding?world_id=' + world + '&city_id=' + city;
const contributionPath = (world) => '/building/wonder/contribute?world_id=' + world;
const contribution = (sourceId, target, values, key) => ({
  target_city_id: target, source_city_id: sourceId, idempotency_key: key,
  wood: 0, stone: 0, iron: 0, gold: 0, ...values,
});
function isolatedBarbarianId(world) {
  const sqlitePath = assertIsolated();
  const script = [
    'import sqlite3, sys',
    'db=sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)',
    'rows=db.execute("SELECT id FROM cities WHERE world_id=? AND name=? AND owner_id IS NULL", (int(sys.argv[2]), "G9 Auditable Barbarian")).fetchall()',
    'assert len(rows)==1, "Expected one isolated G9 barbarian"',
    'print(rows[0][0])',
  ].join('\n');
  const rawId = execFileSync('python3', ['-c', script, sqlitePath, String(world)], {
    cwd: resolve('..'), encoding: 'utf8', timeout: 5000,
  }).trim();
  const id = Number(rawId);
  assert.ok(Number.isSafeInteger(id) && id > 0, 'Bad neutral fixture city');
  return id;
}

const nonzero = (values) => Object.values(values).some(value => Number(value) !== 0);
const resourceKeys = ['wood', 'stone', 'iron', 'gold'];
function assertNoLiquidRefundOrDoubleCharge(before, after, label) {
  for (const resource of resourceKeys) {
    const change = after[resource] - before[resource];
    assert.ok(Math.abs(change) < 20,
      label + ' ' + resource + ': unexpected liquid debit/refund ' + change);
  }
}

async function loginFixture(page, username, password) {
  await page.goto(UI + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill(username);
  await page.locator('form input').nth(1).fill(password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(url => url.pathname === '/', { timeout: 20000 });
  const token = await page.evaluate(() => localStorage.getItem('bm_token'));
  assert.ok(token, 'Fixture login did not persist its session');
  return token;
}

async function fundingPanel(page, target) {
  await page.goto(UI + '/buildings?targetCityId=' + target, { waitUntil: 'domcontentloaded' });
  const panel = page.getByTestId('wonder-funding-panel');
  await panel.waitFor({ timeout: 20000 });
  await panel.getByText('Nivel 1 de 100', { exact: false }).waitFor({ timeout: 20000 });
  return panel;
}

async function fillAmounts(panel, values) {
  const inputs = panel.locator('input[type="number"]');
  assert.equal(await inputs.count(), 5);
  for (const [index, value] of Object.values(values).entries()) {
    await inputs.nth(index + 1).fill(String(value));
  }
}

async function fundInBrowser(page, target, values = partial) {
  const panel = await fundingPanel(page, target);
  await fillAmounts(panel, values);
  await panel.getByRole('button', { name: 'Aportar recursos' }).click();
  await panel.getByText('Aportación registrada.', { exact: false }).waitFor({ timeout: 20000 });
}

async function selectCityFromMap(page, city) {
  await page.goto(UI + '/map', { waitUntil: 'domcontentloaded' });
  await page.getByRole('spinbutton', { name: 'Coordenada X' }).fill(String(city.x));
  await page.getByRole('spinbutton', { name: 'Coordenada Y' }).fill(String(city.y));
  await page.getByRole('button', { name: 'Ir', exact: true }).click();
  const tile = page.getByTestId('map-tile-' + city.x + '-' + city.y);
  await tile.waitFor({ state: 'visible', timeout: 20000 });
  await tile.click();
  return page.getByTestId('map-details-panel');
}

async function waitForBuildingsReady(page) {
  await page.getByRole('heading', { name: 'Edificios', exact: false }).waitFor({ timeout: 20000 });
  await page.getByTestId('loading-screen').waitFor({ state: 'hidden', timeout: 15000 });
}

try {
  await checks.check('fixture worlds, alliances, sources and membership are distinct', async () => {
    ownerToken = await tokenFor('g2_browser', 'G2-Browser-Test-2026!');
    donorToken = await tokenFor('g9_combat', 'G9-Combat-Test-2026!');
    strangerToken = await tokenFor('wonder_stranger', 'Wonder-Stranger-Test-2026!');
    enemyToken = await tokenFor('wonder_enemy', 'Wonder-Enemy-Test-2026!');
    legacyToken = await tokenFor('wonder_legacy', 'Wonder-Legacy-Test-2026!');
    const [owner, donor, outsider, enemy, legacy, legacyAlly] = await Promise.all([
      playerSnapshot(ownerToken), playerSnapshot(donorToken),
      playerSnapshot(strangerToken), playerSnapshot(enemyToken),
      playerSnapshot(legacyToken),
      playerSnapshot(await tokenFor('wonder_legacy_ally', 'Wonder-Legacy-Ally-Test-2026!')),
    ]);
    worldId = owner.worldId;
    legacyWorldId = legacy.worldId;
    assert.equal(donor.worldId, worldId);
    assert.equal(outsider.worldId, worldId);
    assert.equal(enemy.worldId, worldId);
    assert.notEqual(legacyWorldId, worldId);
    assert.equal(legacyAlly.worldId, legacyWorldId);
    targetId = owner.cities[0].id;
    donorCityId = donor.cities.find(city => city.name !== 'Wonder Empty Test City')?.id;
    poorCityId = donor.cities.find(city => city.name === 'Wonder Empty Test City')?.id;
    enemyCityId = enemy.cities[0].id;
    legacyOtherCity = legacyAlly.cities[0];
    assert.ok(targetId && donorCityId && poorCityId && enemyCityId && legacyOtherCity?.id);
    assert.notEqual(targetId, donorCityId);
    const fund = await call(fundingPath(worldId, targetId), { token: donorToken });
    assert.equal(fund.rules_version, 'alliance-v2');
    assert.deepEqual(fund.cost, { wood: 10000, stone: 10000, iron: 10000, gold: 2500 });
    assert.deepEqual(fund.funded, { wood: 0, stone: 0, iron: 0, gold: 0 });
  });

  await checks.check('backend denies outsider, rival, other worlds and neutral targets', async () => {
    await call(fundingPath(worldId, targetId), { token: strangerToken, expected: 403 });
    await call(fundingPath(worldId, enemyCityId), { token: donorToken, expected: 403 });
    await call(fundingPath(legacyWorldId, legacyOtherCity.id), { token: legacyToken, expected: 403 });
    await call(contributionPath(worldId), {
      token: enemyToken, method: 'POST', expected: 400,
      body: contribution(enemyCityId, targetId, { wood: 100 }, 'rival-denied-e2e-001'),
    });
    await call(contributionPath(worldId), {
      token: donorToken, method: 'POST', expected: 400,
      body: contribution(donorCityId, legacyOtherCity.id, { wood: 100 }, 'foreign-city-e2e-01'),
    });
    await call(contributionPath(legacyWorldId), {
      token: legacyToken, method: 'POST', expected: 400,
      body: contribution(legacyOtherCity.id, legacyOtherCity.id, { wood: 100 }, 'legacy-denied-e2e-01'),
    });
    // Spawn coordinates are randomized; query the named neutral fixture
    // read-only instead of assuming it always appears near map (0, 0).
    const barbarianCityId = isolatedBarbarianId(worldId);
    await call(contributionPath(worldId), {
      token: donorToken, method: 'POST', expected: 400,
      body: contribution(donorCityId, barbarianCityId, { wood: 100 }, 'barbarian-denied-01'),
    });
    await call(contributionPath(worldId), {
      token: donorToken, method: 'POST', expected: 400,
      body: contribution(poorCityId, targetId, { wood: 500 }, 'no-resource-e2e-001'),
    });
    for (const [invalid, key] of [
      [{ wood: 10001 }, 'overpay-e2e-001'],
      [{ wood: -1 }, 'negative-e2e-001'],
      [{ wood: 1.5 }, 'fraction-e2e-001'],
      [{}, 'zero-e2e-0001'],
    ]) {
      await call(contributionPath(worldId), {
        token: donorToken, method: 'POST',
        expected: invalid.wood === 10001 || !nonzero(invalid) ? 400 : 422,
        body: contribution(donorCityId, targetId, invalid, key),
      });
    }
    const after = await call(fundingPath(worldId, targetId), { token: ownerToken });
    assert.equal(after.status, 'funding');
    assert.deepEqual(after.funded, { wood: 0, stone: 0, iron: 0, gold: 0 });
  });

  await checks.check('outsider UI does not fetch protected funding', async () => {
    const requested = [];
    strangerPage.on('request', request => {
      if (request.url().includes('/building/wonder/funding')) requested.push(request.url());
    });
    await loginFixture(strangerPage, 'wonder_stranger', 'Wonder-Stranger-Test-2026!');
    await strangerPage.goto(UI + '/buildings', { waitUntil: 'domcontentloaded' });
    await waitForBuildingsReady(strangerPage);
    // Wait for the asynchronous world/alliance permission decision, not just
    // the page heading; otherwise an absent panel could be a loading state.
    await strangerPage.getByTestId('wonder-funding-unavailable').waitFor({ state: 'attached', timeout: 20000 });
    assert.equal(await strangerPage.getByTestId('wonder-funding-panel').count(), 0);
    assert.deepEqual(requested, []);
  });

  await checks.check('legacy world never exposes finance in buildings or mobile map', async () => {
    const forbiddenGets = [];
    legacyPage.on('request', request => {
      if (request.url().includes('/building/wonder/funding')) forbiddenGets.push(request.url());
    });
    await loginFixture(legacyPage, 'wonder_legacy', 'Wonder-Legacy-Test-2026!');
    await legacyPage.goto(UI + '/buildings', { waitUntil: 'domcontentloaded' });
    await waitForBuildingsReady(legacyPage);
    await legacyPage.getByTestId('wonder-funding-unavailable').waitFor({ state: 'attached', timeout: 20000 });
    assert.equal(await legacyPage.getByTestId('wonder-funding-panel').count(), 0);
    assert.deepEqual(forbiddenGets, []);
    await legacyPage.setViewportSize({ width: 390, height: 844 });
    const details = await selectCityFromMap(legacyPage, legacyOtherCity);
    await details.getByText('Wonder Legacy E2E Alliance', { exact: false }).waitFor({ timeout: 15000 });
    assert.equal(await details.getByRole('button', { name: 'Aportar a Maravilla' }).count(), 0);
    assert.deepEqual(forbiddenGets, [], 'Legacy page must not fetch funding after map navigation');
  });

  await checks.check('alliance member replays accepted POST after lost response, with one debit', async () => {
    await loginUi(donorPage, 'g9_combat', 'G9-Combat-Test-2026!');
    const panel = await fundingPanel(donorPage, targetId);
    await fillAmounts(panel, partial);
    const posted = [];
    const capture = request => {
      if (request.method() === 'POST' && request.url().includes('/building/wonder/contribute')) {
        posted.push(request.postDataJSON());
      }
    };
    donorPage.on('request', capture);
    let dropped = false;
    const dropAcceptedResponse = async route => {
      if (!dropped) {
        dropped = true;
        const response = await route.fetch();
        assert.equal(response.status(), 200, 'Backend must accept before simulated disconnect');
        await route.abort('failed');
      } else {
        await route.continue();
      }
    };
    await donorPage.route('**/building/wonder/contribute?*', dropAcceptedResponse);
    try {
      await panel.getByRole('button', { name: 'Aportar recursos' }).click();
      await panel.getByRole('alert').waitFor({ timeout: 20000 });
      const accepted = await call(fundingPath(worldId, targetId), { token: donorToken });
      assert.deepEqual(accepted.funded, partial, 'First request committed despite lost reply');
      await panel.getByRole('button', { name: 'Aportar recursos' }).click();
      await panel.getByText('Aportación registrada.', { exact: false }).waitFor({ timeout: 20000 });
    } finally {
      await donorPage.unroute('**/building/wonder/contribute?*', dropAcceptedResponse);
      donorPage.off('request', capture);
    }
    assert.equal(dropped, true);
    assert.equal(posted.length, 2, 'Expected first POST plus exactly one retry');
    assert.ok(posted[0].idempotency_key);
    assert.equal(posted[0].idempotency_key, posted[1].idempotency_key);
    assert.deepEqual(posted[0], posted[1]);
    const current = await call(fundingPath(worldId, targetId), { token: donorToken });
    assert.deepEqual(current.funded, partial);
    const donor = await playerSnapshot(donorToken);
    const paidDonor = donor.cities.find(city => city.id === donorCityId);
    assert.ok(paidDonor.wood >= 39990 && paidDonor.wood <= 40020, 'Single donor debit only');
    await donorPage.reload({ waitUntil: 'domcontentloaded' });
    const persistedFund = donorPage.getByTestId('wonder-funding-panel')
      .getByText('5000/10000', { exact: false });
    await persistedFund.first().waitFor({ timeout: 20000 });
    assert.equal(await persistedFund.count(), 3, 'Wood, stone and iron all persist after reload');
  });

  await checks.check('allied map offers finance action on desktop and mobile', async () => {
    const owner = await playerSnapshot(ownerToken);
    const city = owner.cities.find(entry => entry.id === targetId);
    for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
      await donorPage.setViewportSize(viewport);
      const details = await selectCityFromMap(donorPage, city);
      const action = details.getByRole('button', { name: 'Aportar a Maravilla' });
      await action.waitFor({ state: 'visible', timeout: 15000 });
      assert.equal(await action.isEnabled(), true);
    }
    await donorPage.setViewportSize({ width: 1280, height: 720 });
  });

  await checks.check('owner completes financing through the real React form', async () => {
    await loginUi(ownerPage, 'g2_browser', 'G2-Browser-Test-2026!');
    await fundInBrowser(ownerPage, targetId);
    const funded = await call(fundingPath(worldId, targetId), { token: ownerToken });
    assert.equal(funded.status, 'ready');
    assert.equal(funded.can_queue, true);
    assert.ok(Object.values(funded.remaining).every(value => value === 0));
    await ownerPage.reload({ waitUntil: 'domcontentloaded' });
    await ownerPage.getByTestId('wonder-funding-panel')
      .getByText('Financiación completa.', { exact: false }).waitFor({ timeout: 20000 });
  });

  await checks.check('real building button queues without duplicate payment', async () => {
    await ownerPage.goto(UI + '/buildings', { waitUntil: 'domcontentloaded' });
    await ownerPage.getByTestId('intro-animation').waitFor({ state: 'hidden', timeout: 12000 });
    await ownerPage.getByTestId('loading-screen').waitFor({ state: 'hidden', timeout: 12000 });
    const card = ownerPage.locator('.building-card-world_wonder');
    await card.waitFor({ timeout: 18000 });
    const buildButton = card.getByRole('button', { name: 'Construir' });
    await buildButton.waitFor({ timeout: 18000 });
    assert.equal(await buildButton.isEnabled(), true);
    await buildButton.click();
    await ownerPage.getByText('Mejora añadida a la cola.').waitFor({ timeout: 18000 });
    const funded = await call(fundingPath(worldId, targetId), { token: ownerToken });
    assert.equal(funded.status, 'queued');
    const owner = await playerSnapshot(ownerToken);
    const donor = await playerSnapshot(donorToken);
    const paidOwner = owner.cities.find(city => city.id === targetId);
    const paidDonor = donor.cities.find(city => city.id === donorCityId);
    assert.ok(paidOwner.wood >= 39990 && paidOwner.wood <= 40020);
    assert.ok(paidDonor.wood >= 39990 && paidDonor.wood <= 40020);
  });

  await checks.check('cancel, re-queue from UI, worker completion and persistence', async () => {
    const ownerBeforeCancel = (await playerSnapshot(ownerToken)).cities.find(city => city.id === targetId);
    const donorBeforeCancel = (await playerSnapshot(donorToken)).cities.find(city => city.id === donorCityId);
    const status = await call('/city/' + targetId + '/status?world_id=' + worldId, { token: ownerToken });
    const queued = (status.building_queue || []).find(item => item.building_type === 'world_wonder');
    assert.ok(queued?.id, 'Wonder building queue was not persisted');
    await call('/building/queue/' + queued.id, { token: ownerToken, method: 'DELETE', expected: 204 });
    const restored = await call(fundingPath(worldId, targetId), { token: donorToken });
    assert.equal(restored.status, 'ready');
    assert.equal(restored.can_queue, true);
    assert.deepEqual(restored.funded, { wood: 10000, stone: 10000, iron: 10000, gold: 2500 });
    const ownerAfterCancel = (await playerSnapshot(ownerToken)).cities.find(city => city.id === targetId);
    const donorAfterCancel = (await playerSnapshot(donorToken)).cities.find(city => city.id === donorCityId);
    assertNoLiquidRefundOrDoubleCharge(ownerBeforeCancel, ownerAfterCancel, 'Owner cancel');
    assertNoLiquidRefundOrDoubleCharge(donorBeforeCancel, donorAfterCancel, 'Donor cancel');
    await ownerPage.goto(UI + '/buildings', { waitUntil: 'domcontentloaded' });
    await ownerPage.getByTestId('intro-animation').waitFor({ state: 'hidden', timeout: 12000 });
    await ownerPage.getByTestId('loading-screen').waitFor({ state: 'hidden', timeout: 12000 });
    const button = ownerPage.locator('.building-card-world_wonder')
      .getByRole('button', { name: 'Construir' });
    await button.waitFor({ state: 'visible', timeout: 18000 });
    await button.click();
    await ownerPage.getByText('Mejora añadida a la cola.').waitFor({ timeout: 18000 });
    const ownerAfterRequeue = (await playerSnapshot(ownerToken)).cities.find(city => city.id === targetId);
    const donorAfterRequeue = (await playerSnapshot(donorToken)).cities.find(city => city.id === donorCityId);
    assertNoLiquidRefundOrDoubleCharge(ownerBeforeCancel, ownerAfterRequeue, 'Owner requeue');
    assertNoLiquidRefundOrDoubleCharge(donorBeforeCancel, donorAfterRequeue, 'Donor requeue');
    assert.equal((await call(fundingPath(worldId, targetId), { token: ownerToken })).status, 'queued');

    const workerResult = execFileSync(
      process.env.PARALLEL_JOURNEY_PYTHON || 'python',
      ['scripts/complete_wonder_funding_e2e.py', String(targetId)],
      { cwd: resolve('..'), encoding: 'utf8', timeout: 30000 },
    );
    assert.match(workerResult, /WONDER_ISOLATED_WORKER_COMPLETE level=1 status=completed/);
    const next = await call(fundingPath(worldId, targetId), { token: ownerToken });
    assert.equal(next.target_level, 2);
    assert.equal(next.status, 'funding');
    assert.deepEqual(next.funded, { wood: 0, stone: 0, iron: 0, gold: 0 });
    await ownerPage.reload({ waitUntil: 'domcontentloaded' });
    await ownerPage.getByTestId('wonder-funding-panel')
      .getByText('Nivel 2 de 100', { exact: false }).waitFor({ timeout: 20000 });
    assert.deepEqual(jsErrors, []);
  });
} finally {
  await Promise.all(pages.map(page => page.close().catch(() => {})));
  await browser.close().catch(() => {});
}
checks.finish();
