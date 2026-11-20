import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { assertIsolated } from './parallel-journey-helpers.mjs';

// Regression runs only against a disposable local game, never production.
const UI = process.env.E2E_BASE_URL || 'http://127.0.0.1:4308';
const API = process.env.VITE_API_URL || 'http://127.0.0.1:8308';
assert.equal(process.env.APP_ENV, 'test');
assert.equal(process.env.PARALLEL_JOURNEY_ALLOW_MUTATIONS, 'isolated');
for (const uri of [UI, API]) {
  const url = new URL(uri);
  assert.equal(url.protocol, 'http:');
  assert.equal(url.hostname, '127.0.0.1');
}

async function read(path, token) {
  const response = await fetch(API + path, { headers: { Authorization: 'Bearer ' + token } });
  assert.equal(response.status, 200, path + ' returned ' + response.status);
  return response.json();
}
async function loginToken(username, password) {
  const response = await fetch(API + '/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  });
  assert.equal(response.status, 200);
  return (await response.json()).access_token;
}

assertIsolated();
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(error.message));
try {
  await page.goto(UI + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g9_combat');
  await page.locator('form input').nth(1).fill('G9-Combat-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL((url) => url.pathname === '/', { timeout: 15000 });
  const token = await page.evaluate(() => localStorage.getItem('bm_token'));
  assert.ok(token);

  const profile = await read('/auth/me', token);
  const worldId = profile.world_id;
  const ownCities = await read('/city/?world_id=' + worldId, token);
  const beforeMovements = (await read('/movement/?world_id=' + worldId, token)).map((item) => item.id);
  const beforeMessages = (await read('/message/sent', token)).map((item) => item.id);
  const map = await read('/map/tiles?world_id=' + worldId + '&x=0&y=0&radius=0', token);
  const barbarian = map.tiles.find((tile) => tile.city_id && !tile.owner_id);
  assert.ok(barbarian, 'G9 barbarian fixture missing');

  const enemyToken = await loginToken('g2_browser', 'G2-Browser-Test-2026!');
  const enemyCities = await read('/city/?world_id=' + worldId, enemyToken);
  const enemy = enemyCities[0];
  assert.ok(enemy?.id && enemy.id !== ownCities[0].id, 'Other-player fixture missing');

  async function selectCity(tile) {
    await page.goto(UI + '/map', { waitUntil: 'domcontentloaded' });
    await page.getByTestId('map-tile-' + ownCities[0].x + '-' + ownCities[0].y)
      .waitFor({ state: 'visible', timeout: 15000 });
    await page.getByRole('spinbutton', { name: 'Coordenada X' }).fill(String(tile.x));
    await page.getByRole('spinbutton', { name: 'Coordenada Y' }).fill(String(tile.y));
    await page.getByRole('button', { name: 'Ir', exact: true }).click();
    const button = page.getByTestId('map-tile-' + tile.x + '-' + tile.y);
    await button.waitFor({ state: 'visible', timeout: 15000 });
    await button.click();
    return page.getByTestId('map-details-panel');
  }

  const neutralPanel = await selectCity(barbarian);
  assert.equal(await neutralPanel.getByRole('button', { name: 'Espiar' }).isEnabled(), true);
  assert.equal(await neutralPanel.getByRole('button', { name: 'Comerciar' }).count(), 0);
  assert.equal(await neutralPanel.getByRole('button', { name: 'Mensaje' }).count(), 0);
  assert.match(await neutralPanel.innerText(), /bárbaros no pueden comerciar/i);
  await neutralPanel.getByRole('button', { name: 'Espiar' }).click();
  await page.waitForURL((url) => url.pathname === '/send-movement/' + barbarian.city_id && url.searchParams.get('mission') === 'spy', { timeout: 12000 });
  await page.getByRole('heading', { name: 'Objetivo: ' + barbarian.city_name }).waitFor({ state: 'visible', timeout: 15000 });
  assert.equal(await page.getByRole('radio', { name: 'Espionaje' }).isChecked(), true);
  console.log('PASS barbarian espionage target; no inappropriate social actions');

  const playerPanel = await selectCity(enemy);
  for (const label of ['Atacar', 'Espiar', 'Comerciar', 'Mensaje']) {
    assert.equal(await playerPanel.getByRole('button', { name: label }).isEnabled(), true);
  }
  await playerPanel.getByRole('button', { name: 'Comerciar' }).click();
  await page.waitForURL((url) => url.pathname === '/market', { timeout: 12000 });
  await page.getByText('Destino seleccionado: ' + enemy.name).waitFor({ state: 'visible', timeout: 12000 });
  assert.equal(await page.locator('#market-target-city').inputValue(), String(enemy.id));
  console.log('PASS commerce destination selected from same-world city');

  const messagePanel = await selectCity(enemy);
  await messagePanel.getByRole('button', { name: 'Mensaje' }).click();
  await page.waitForURL((url) => url.pathname === '/messages', { timeout: 12000 });
  await page.getByRole('heading', { name: 'Nuevo Mensaje' }).waitFor({ state: 'visible', timeout: 12000 });
  await page.waitForFunction((username) => document.querySelector('#message-recipient')?.value === username, enemyToken ? 'g2_browser' : '');
  assert.equal(await page.getByRole('button', { name: 'Enviar', exact: true }).isDisabled(), true);
  await page.locator('#message-recipient').fill('usuario_distinto');
  assert.equal(await page.getByRole('button', { name: 'Enviar', exact: true }).isDisabled(), true);
  console.log('PASS message recipient validated; manual editing invalidates recipient selection');

  await page.goto(UI + '/market?targetCityId=' + enemy.id + '&worldId=' + (worldId + 987), { waitUntil: 'domcontentloaded' });
  await page.getByRole('alert').getByText('El destino no corresponde al mundo activo.').waitFor({ state: 'visible', timeout: 12000 });
  assert.equal(await page.locator('#market-target-city').inputValue(), '');
  await page.goto(UI + '/messages?targetCityId=' + enemy.id + '&worldId=' + (worldId + 987), { waitUntil: 'domcontentloaded' });
  await page.getByRole('alert').getByText('El destinatario no pertenece al mundo activo.').waitFor({ state: 'visible', timeout: 12000 });
  console.log('PASS cross-world deep links rejected');

  assert.deepEqual((await read('/movement/?world_id=' + worldId, token)).map((item) => item.id), beforeMovements);
  assert.deepEqual((await read('/message/sent', token)).map((item) => item.id), beforeMessages);
  assert.deepEqual(pageErrors, []);
  console.log('JOURNEY_SUMMARY map-actions-verified: barbarian espionage, enemy player commerce, messaging, world isolation PASS');
} finally {
  await browser.close();
}
