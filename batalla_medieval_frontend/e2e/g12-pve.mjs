import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g12_pve';
const PASSWORD = 'G12-PvE-Test-2026!';
const RULES_VERSION = '2026.08.25-bm0067-v1';
const BARBARIAN = { x: 80, y: 75, tier: 3 };
const CANONICAL_GUARDS = new Set([
  'basic_infantry',
  'heavy_infantry',
  'archer',
  'fast_cavalry',
  'heavy_cavalry',
  'spy',
  'ram',
  'catapult',
  'noble',
]);

const failures = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') failures.push(`console.error: ${message.text()}`);
});
page.on('response', async (response) => {
  if (response.status() >= 400) {
    let body = '';
    try {
      body = (await response.text()).slice(0, 700);
    } catch {
      body = '<unreadable>';
    }
    failures.push(`HTTP ${response.status()}: ${response.url()} body=${body}`);
  }
});

async function waitForExperienceReady() {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) {
    await intro.waitFor({ state: 'detached', timeout: 10000 });
  }
  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 2000 }).catch(() => {});
  if (await loading.count()) {
    await loading.waitFor({ state: 'detached', timeout: 10000 });
  }
}

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
}

async function apiSnapshot() {
  return page.evaluate(async ({ apiUrl, barbarian, rulesVersion }) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };

    const profileResponse = await fetch(`${apiUrl}/auth/me`, { headers });
    if (!profileResponse.ok) throw new Error(`profile ${profileResponse.status}`);
    const profile = await profileResponse.json();

    const barbarianResponse = await fetch(
      `${apiUrl}/map/tiles?world_id=${profile.world_id}&x=${barbarian.x}&y=${barbarian.y}&radius=0`,
      { headers },
    );
    if (!barbarianResponse.ok) throw new Error(`barbarian map ${barbarianResponse.status}`);
    const barbarianTiles = (await barbarianResponse.json()).tiles || [];
    if (barbarianTiles.length !== 1) throw new Error(`barbarian tile count ${barbarianTiles.length}`);

    let oasisTile = null;
    const centers = [20, 50, 80];
    for (const x of centers) {
      for (const y of centers) {
        const response = await fetch(
          `${apiUrl}/map/tiles?world_id=${profile.world_id}&x=${x}&y=${y}&radius=20`,
          { headers },
        );
        if (!response.ok) throw new Error(`oasis scan ${response.status}`);
        const tiles = (await response.json()).tiles || [];
        oasisTile = tiles.find(
          (tile) => tile.oasis_id && !tile.is_conquered && tile.pve_rules_version === rulesVersion,
        );
        if (oasisTile) break;
      }
      if (oasisTile) break;
    }
    if (!oasisTile) throw new Error('No wild BM-0067 oasis found through map API');

    const oasisResponse = await fetch(`${apiUrl}/map/oasis/${oasisTile.oasis_id}`, { headers });
    if (!oasisResponse.ok) throw new Error(`oasis detail ${oasisResponse.status}`);
    const oasis = await oasisResponse.json();

    return { profile, barbarian: barbarianTiles[0], oasisTile, oasis };
  }, { apiUrl: API_URL, barbarian: BARBARIAN, rulesVersion: RULES_VERSION });
}

async function jumpAndOpen(x, y) {
  const xInput = page.locator('input[placeholder="X"]');
  const yInput = page.locator('input[placeholder="Y"]');
  await xInput.fill(String(x));
  await yInput.fill(String(y));
  await page.getByRole('button', { name: 'Ir', exact: true }).click();
  const tile = page.locator(`[title^="(${x}, ${y}) "]`);
  await tile.waitFor({ state: 'visible', timeout: 10000 });
  await tile.click();
}

try {
  await login();
  const snapshot = await apiSnapshot();

  const barbarian = snapshot.barbarian;
  if (!barbarian.city_id || barbarian.owner_id !== null) {
    failures.push(`Expected wild barbarian city: ${JSON.stringify(barbarian)}`);
  }
  if (Number(barbarian.pve_tier) !== BARBARIAN.tier) {
    failures.push(`Expected tier-3 barbarian: ${JSON.stringify(barbarian)}`);
  }
  if (barbarian.pve_rules_version !== RULES_VERSION) {
    failures.push(`Barbarian rules version mismatch: ${barbarian.pve_rules_version}`);
  }

  const oasis = snapshot.oasis;
  if (oasis.pve_rules_version !== RULES_VERSION) {
    failures.push(`Oasis rules version mismatch: ${oasis.pve_rules_version}`);
  }
  if (Number(oasis.pve_tier) !== Number(snapshot.oasisTile.pve_tier)) {
    failures.push(`Oasis tier differs between tile/detail: ${JSON.stringify(snapshot)}`);
  }
  if (![1, 2, 3].includes(Number(oasis.pve_tier))) {
    failures.push(`Invalid oasis tier: ${oasis.pve_tier}`);
  }
  const guardEntries = Object.entries(oasis.troops || {});
  if (!guardEntries.length) failures.push('Wild oasis has no guards');
  for (const [unit, amount] of guardEntries) {
    if (!CANONICAL_GUARDS.has(unit) || Number(amount) <= 0) {
      failures.push(`Invalid oasis guard ${unit}=${amount}`);
    }
  }
  if ('rat' in (oasis.troops || {}) || 'spider' in (oasis.troops || {})) {
    failures.push(`Legacy zero-defense oasis guards leaked: ${JSON.stringify(oasis.troops)}`);
  }

  await page.goto(`${BASE_URL}/map`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();

  await jumpAndOpen(BARBARIAN.x, BARBARIAN.y);
  let panel = page.getByTestId('pve-difficulty');
  await panel.waitFor({ state: 'visible', timeout: 10000 });
  if (Number(await panel.getAttribute('data-pve-tier')) !== BARBARIAN.tier) {
    failures.push('UI barbarian difficulty does not match API');
  }
  if ((await panel.getAttribute('data-pve-rules-version')) !== RULES_VERSION) {
    failures.push('UI barbarian rules version does not match API');
  }

  await jumpAndOpen(snapshot.oasisTile.x, snapshot.oasisTile.y);
  panel = page.getByTestId('pve-difficulty');
  await panel.waitFor({ state: 'visible', timeout: 10000 });
  if (Number(await panel.getAttribute('data-pve-tier')) !== Number(snapshot.oasis.pve_tier)) {
    failures.push('UI oasis difficulty does not match API');
  }
  if ((await panel.getAttribute('data-pve-rules-version')) !== RULES_VERSION) {
    failures.push('UI oasis rules version does not match API');
  }
} catch (error) {
  failures.push(`journey-error: ${error.stack || error.message}`);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G12 BM-0067 final PvE browser journey passed');
