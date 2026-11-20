import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite } from './parallel-journey-helpers.mjs';

// These tests deliberately fail if a visible action is a no-op. Do not weaken the
// assertions to obtain green CI. Only production owners can repair MapView.
assertIsolated();
const journey = suite('map-action-adversarial');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
let token;
let worldId;
let target;
try {
  await journey.check('select a real barbarian on the map', async () => {
    token = await loginUi(page, 'g9_combat', 'G9-Combat-Test-2026!');
    const snapshot = await playerSnapshot(token);
    worldId = snapshot.worldId;
    const data = await call(`/map/tiles?world_id=${worldId}&x=0&y=0&radius=20`, { token });
    target = data.tiles.find((tile) => tile.city_id && !tile.owner_id);
    assert.ok(target, 'Prepared G9 barbarian not visible in initial viewport');
    await page.goto(`${UI}/map`, { waitUntil: 'domcontentloaded' });
    const capital = snapshot.cities[0];
    await page.getByTestId(`map-tile-${capital.x}-${capital.y}`).waitFor({ state: 'visible', timeout: 15000 });
    await page.getByRole('spinbutton', { name: 'Coordenada X' }).fill(String(target.x));
    await page.getByRole('spinbutton', { name: 'Coordenada Y' }).fill(String(target.y));
    await page.getByRole('button', { name: 'Ir', exact: true }).click();
    const tile = page.getByTestId(`map-tile-${target.x}-${target.y}`);
    await tile.waitFor({ state: 'visible', timeout: 15000 });
    await tile.click();
    assert.equal(await tile.getAttribute('aria-pressed'), 'true');
    const panel = page.getByTestId('map-details-panel');
    await panel.getByText(target.city_name).waitFor({ timeout: 8000 });
    assert.ok((await panel.innerText()).includes(`(${target.x}, ${target.y})`));
  });

  for (const action of ['Espiar', 'Comerciar', 'Mensaje']) {
    await journey.check(`visible ${action} button must initiate navigation, request or meaningful UI state`, async () => {
      assert.ok(token && target);
      const button = page.getByTestId('map-details-panel').getByRole('button', { name: action, exact: true });
      await button.waitFor({ state: 'visible', timeout: 10000 });
      const panel = page.getByTestId('map-details-panel');
      const before = { url: page.url(), detail: await panel.innerText(), dialogs: await page.getByRole('dialog').count() };
      const requests = [];
      const monitor = (request) => {
        if (request.method() !== 'GET' && /\/(movement|market|message|chat)(\/|$)/.test(new URL(request.url()).pathname)) {
          requests.push(request.url());
        }
      };
      page.on('request', monitor);
      await button.click();
      await page.waitForTimeout(500);
      page.off('request', monitor);
      const after = { url: page.url(), detail: await panel.innerText(), dialogs: await page.getByRole('dialog').count() };
      assert.ok(
        before.url !== after.url || before.detail !== after.detail || after.dialogs > before.dialogs || requests.length > 0,
        `Visible map action ${action} produced no navigation, request, or visible change for city id=${target.city_id}. Assign to MapView owner.`,
      );
    });
  }
  await journey.check('existing Atacar action navigates to the selected target', async () => {
    assert.ok(target);
    await page.getByTestId('map-details-panel').getByRole('button', { name: 'Atacar', exact: true }).click();
    await page.waitForURL((url) => url.pathname === `/send-movement/${target.city_id}`, { timeout: 10000 });
  });
} finally {
  await browser.close();
}
journey.finish();
