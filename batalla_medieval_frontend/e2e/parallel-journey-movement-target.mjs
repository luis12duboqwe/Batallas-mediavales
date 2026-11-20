import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite, tokenFor } from './parallel-journey-helpers.mjs';

// Regression contract: a legitimate battle target must be shown using a public,
// world-scoped target lookup. A 404 from the private /city/:id/status API must
// not make the player's attack/spy form permanently unusable.
assertIsolated();
const run = suite('real-movement-target');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
let token;
let homeCity;
let worldId;
let barbarian;
let enemyCity;
let beforeIds = [];

try {
  await run.check('fixture worlds, accounts and target cities exist', async () => {
    token = await loginUi(page, 'g9_combat', 'G9-Combat-Test-2026!');
    const state = await playerSnapshot(token);
    homeCity = state.cities[0];
    worldId = state.worldId;
    assert.ok(homeCity, 'Missing G9 home city');
    beforeIds = state.movements.map((item) => item.id);
    const map = await call(`/map/tiles?world_id=${worldId}&x=0&y=0&radius=0`, { token });
    barbarian = map.tiles.find((item) => item.city_id && item.owner_id === null);
    assert.ok(barbarian, 'G9 auditable neutral target missing at 0,0');
    const enemy = await tokenFor('g2_browser', 'G2-Browser-Test-2026!');
    const enemyState = await playerSnapshot(enemy, worldId);
    assert.equal(enemyState.worldId, worldId);
    enemyCity = enemyState.cities[0];
    assert.ok(enemyCity?.id && enemyCity.id !== homeCity.id);
  });

  await run.check('positive control: owned city details load on movement page', async () => {
    assert.ok(homeCity);
    await page.goto(`${UI}/send-movement/${homeCity.id}`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('heading', { name: /^Objetivo:/ })
      .waitFor({ state: 'visible', timeout: 12000 });
    assert.equal(await page.getByRole('button', { name: 'Enviar Tropas' }).isEnabled(), true);
  });

  await run.check('owned target UI should show an actual city name instead of an empty label', async () => {
    const title = (await page.getByRole('heading', { name: /^Objetivo:/ }).textContent())?.trim();
    assert.equal(title, `Objetivo: ${homeCity.name}`,
      'CityResourceStatus omits the name; the movement form renders an empty target label');
  });

  await run.check('negative API: neutral city private status must NOT be readable', async () => {
    await call(`/city/${barbarian.city_id}/status?world_id=${worldId}`, {
      token, expected: 404,
    });
  });

  async function assertPublicTargetIsUsable(targetId, expectedName) {
    const attempts = [];
    const collect = (response) => {
      const url = new URL(response.url());
      if (url.pathname.endsWith(`/city/${targetId}/status`)) {
        attempts.push(response.status());
      }
    };
    page.on('response', collect);
    try {
      await page.goto(`${UI}/send-movement/${targetId}`, { waitUntil: 'domcontentloaded' });
      const heading = page.getByRole('heading', { name: `Objetivo: ${expectedName}`, exact: true });
      try {
        await heading.waitFor({ state: 'visible', timeout: 8000 });
      } catch (error) {
        const disabled = await page.getByRole('button', { name: 'Enviar Tropas' }).isDisabled();
        const errors = await page.getByRole('alert').allTextContents();
        throw new Error(`Target ${targetId} not rendered. submitDisabled=${disabled}, privateStatusResponses=${JSON.stringify(attempts)}, alerts=${JSON.stringify(errors)}. ${error.message}`);
      }
      assert.equal(await page.getByRole('button', { name: 'Enviar Tropas' }).isEnabled(), true);
    } finally {
      page.off('response', collect);
    }
  }

  await run.check('barbarian target must display public details and enable real dispatch', async () => {
    await assertPublicTargetIsUsable(barbarian.city_id, barbarian.city_name);
  });

  await run.check('other-player target must display public details and enable dispatch', async () => {
    await assertPublicTargetIsUsable(enemyCity.id, enemyCity.name);
  });

  await run.check('no accidental march was created by visiting a target form', async () => {
    const movements = await call(`/movement/?world_id=${worldId}`, { token });
    assert.deepEqual(movements.map((item) => item.id), beforeIds);
  });
} finally {
  await browser.close();
}
run.finish();
