import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite, tokenFor } from './parallel-journey-helpers.mjs';

assertIsolated();
const checks = suite('wonder-v2-real-browser');
const browser = await chromium.launch({ headless: true });
const ownerPage = await browser.newPage();
const donorPage = await browser.newPage();
const jsErrors = [];
ownerPage.on('pageerror', e => jsErrors.push(e.message));
donorPage.on('pageerror', e => jsErrors.push(e.message));
const partial = { wood: 5000, stone: 5000, iron: 5000, gold: 1250 };
let ownerToken, donorToken, worldId, targetId, donorCityId;

async function fundInBrowser(page, target) {
  await page.goto(UI + '/buildings?targetCityId=' + target, { waitUntil: 'domcontentloaded' });
  const panel = page.getByTestId('wonder-funding-panel');
  await panel.waitFor({ timeout: 20000 });
  await panel.getByText('Nivel 1 de 100', { exact: false }).waitFor({ timeout: 20000 });
  const inputs = panel.locator('input[type="number"]');
  assert.equal(await inputs.count(), 5);
  for (const [i, value] of Object.values(partial).entries()) {
    await inputs.nth(i + 1).fill(String(value));
  }
  await panel.getByRole('button', { name: 'Aportar recursos' }).click();
  await panel.getByText('Aportación registrada.', { exact: false }).waitFor({ timeout: 20000 });
}

try {
  await checks.check('world-pinned finance and separate owner/donor', async () => {
    ownerToken = await tokenFor('g2_browser', 'G2-Browser-Test-2026!');
    donorToken = await tokenFor('g9_combat', 'G9-Combat-Test-2026!');
    const owner = await playerSnapshot(ownerToken);
    const donor = await playerSnapshot(donorToken);
    worldId = owner.worldId;
    assert.equal(donor.worldId, worldId);
    targetId = owner.cities[0].id;
    donorCityId = donor.cities[0].id;
    assert.notEqual(targetId, donorCityId);
    const fund = await call('/building/wonder/funding?world_id=' + worldId + '&city_id=' + targetId, { token: donorToken });
    assert.equal(fund.rules_version, 'alliance-v2');
    assert.deepEqual(fund.cost, { wood: 10000, stone: 10000, iron: 10000, gold: 2500 });
  });
  await checks.check('alliance member contributes through React', async () => {
    await loginUi(donorPage, 'g9_combat', 'G9-Combat-Test-2026!');
    await fundInBrowser(donorPage, targetId);
    const fund = await call('/building/wonder/funding?world_id=' + worldId + '&city_id=' + targetId, { token: donorToken });
    assert.deepEqual(fund.funded, partial);
    assert.equal(fund.status, 'funding');
  });
  await checks.check('owner completes financing through React', async () => {
    await loginUi(ownerPage, 'g2_browser', 'G2-Browser-Test-2026!');
    await fundInBrowser(ownerPage, targetId);
    const funded = await call('/building/wonder/funding?world_id=' + worldId + '&city_id=' + targetId, { token: ownerToken });
    assert.equal(funded.status, 'ready');
    assert.equal(funded.can_queue, true);
    assert.ok(Object.values(funded.remaining).every(x => x === 0));
  });
  await checks.check('real upgrade queues without duplicate debit', async () => {
    await ownerPage.goto(UI + '/buildings', { waitUntil: 'domcontentloaded' });
    // The splash screen must relinquish pointer events on a hard reload.
    await ownerPage.getByTestId('intro-animation').waitFor({ state: 'hidden', timeout: 12000 });
    await ownerPage.getByTestId('loading-screen').waitFor({ state: 'hidden', timeout: 12000 });
    const card = ownerPage.locator('.building-card-world_wonder');
    await card.waitFor({ timeout: 18000 });
    const buildButton = card.getByRole('button', { name: 'Construir' });
    await buildButton.waitFor({ timeout: 18000 });
    assert.equal(await buildButton.isEnabled(), true);
    await buildButton.click();
    await ownerPage.getByText('Mejora añadida a la cola.').waitFor({ timeout: 18000 });
    const funded = await call('/building/wonder/funding?world_id=' + worldId + '&city_id=' + targetId, { token: ownerToken });
    assert.equal(funded.status, 'queued');
    const owner = await playerSnapshot(ownerToken);
    const donor = await playerSnapshot(donorToken);
    const paidOwner = owner.cities.find(c => c.id === targetId);
    const paidDonor = donor.cities.find(c => c.id === donorCityId);
    assert.ok(paidOwner.wood >= 39990 && paidOwner.wood <= 40020);
    assert.ok(paidDonor.wood >= 39990 && paidDonor.wood <= 40020);
  });
  await checks.check('cancel keeps the fund and the browser does not crash', async () => {
    const status = await call('/city/' + targetId + '/status?world_id=' + worldId, { token: ownerToken });
    const queued = (status.building_queue || []).find(x => x.building_type === 'world_wonder');
    assert.ok(queued?.id, 'Wonder building queue was not persisted');
    await call('/building/queue/' + queued.id, { token: ownerToken, method: 'DELETE', expected: 204 });
    const funded = await call('/building/wonder/funding?world_id=' + worldId + '&city_id=' + targetId, { token: donorToken });
    assert.equal(funded.status, 'ready');
    assert.equal(funded.can_queue, true);
    assert.deepEqual(funded.funded, { wood: 10000, stone: 10000, iron: 10000, gold: 2500 });
    assert.deepEqual(jsErrors, []);
  });
} finally {
  await donorPage.close().catch(() => {});
  await ownerPage.close().catch(() => {});
  await browser.close().catch(() => {});
}
checks.finish();
