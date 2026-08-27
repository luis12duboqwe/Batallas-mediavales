import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const PASSWORD = 'G16-Lifecycle-Test-2026!';
const ADMIN = 'g16_admin';
const PLAYER = 'g16_player';
const WORLD_NAME = 'G16 Lifecycle World';
const failures = [];

const browser = await chromium.launch({ headless: true });
const adminContext = await browser.newContext();
const playerContext = await browser.newContext();
const adminPage = await adminContext.newPage();
const playerPage = await playerContext.newPage();

for (const [label, page] of [['admin', adminPage], ['player', playerPage]]) {
  page.on('pageerror', (error) => failures.push(`${label} pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') failures.push(`${label} console.error: ${message.text()}`);
  });
  page.on('response', async (response) => {
    // Expected lifecycle denial checks are issued through fetch and asserted
    // explicitly, so do not treat their 404/409 responses as console failures.
    if (response.status() >= 500) {
      failures.push(`${label} HTTP ${response.status()}: ${response.url()}`);
    }
  });
}

async function waitForExperienceReady(page) {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  const loading = page.getByTestId('loading-screen');
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
}

async function login(page, username) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await waitForExperienceReady(page);
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(username);
  await inputs.nth(1).fill(PASSWORD);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForExperienceReady(page);
}

async function api(page, path, options = {}) {
  return page.evaluate(async ({ apiUrl, path, options }) => {
    const token = localStorage.getItem('bm_token');
    const response = await fetch(`${apiUrl}${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    const text = await response.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    return { status: response.status, body };
  }, { apiUrl: API_URL, path, options });
}

async function adminTransition(target, reason) {
  const reasonInput = adminPage.getByTestId('world-lifecycle-reason');
  await reasonInput.fill(reason);
  const button = adminPage.getByTestId(`world-lifecycle-to-${target}`);
  await button.waitFor({ state: 'visible', timeout: 10000 });
  await button.click();
  await adminPage.getByTestId('world-lifecycle-current').getByText(
    new RegExp(`Estado:\\s*${target}`)
  ).waitFor({ state: 'visible', timeout: 10000 });
}

try {
  await login(adminPage, ADMIN);
  await adminPage.goto(`${BASE_URL}/admin`, { waitUntil: 'networkidle' });
  await waitForExperienceReady(adminPage);
  await adminPage.getByTestId('world-lifecycle-admin').waitFor({ state: 'visible', timeout: 10000 });

  const worlds = await api(adminPage, '/worlds/');
  if (worlds.status !== 200) throw new Error(`world catalogue failed: ${worlds.status}`);
  const fixtureWorld = worlds.body.find((world) => world.name === WORLD_NAME);
  if (!fixtureWorld) throw new Error('G16 lifecycle world fixture missing');
  const worldId = fixtureWorld.id;

  await adminPage.getByTestId('world-lifecycle-select').selectOption(String(worldId));
  const initialStatus = await adminPage.getByTestId('world-lifecycle-current').innerText();
  if (!initialStatus.includes('draft')) failures.push(`Expected draft, got: ${initialStatus}`);

  await adminTransition('open', 'G16 abrir mundo');

  await login(playerPage, PLAYER);
  const worldCard = playerPage.getByTestId(`world-selector-${worldId}`);
  await worldCard.waitFor({ state: 'visible', timeout: 10000 });
  const selectorStatus = await playerPage.getByTestId(`world-status-${worldId}`).innerText();
  if (selectorStatus.trim() !== 'open') failures.push(`Selector exposed wrong state: ${selectorStatus}`);

  await worldCard.getByRole('button', { name: 'Unirse' }).click();
  await playerPage.getByText('Mundo activo', { exact: true }).waitFor({ state: 'visible', timeout: 10000 });

  const firstJoin = await api(playerPage, `/worlds/${worldId}/join`, { method: 'POST' });
  if (firstJoin.status !== 200) failures.push(`Open world idempotent join failed: ${firstJoin.status}`);
  const membershipId = firstJoin.body?.id;
  const startingCityId = firstJoin.body?.starting_city_id;
  if (!membershipId || !startingCityId) failures.push(`Join did not persist membership/city: ${JSON.stringify(firstJoin.body)}`);

  await adminTransition('paused', 'G16 pausa controlada');

  await playerPage.reload({ waitUntil: 'networkidle' });
  await waitForExperienceReady(playerPage);
  if (await playerPage.getByTestId(`world-selector-${worldId}`).count()) {
    failures.push('Paused world remained visible as playable in selector');
  }
  const pausedJoin = await api(playerPage, `/worlds/${worldId}/join`, { method: 'POST' });
  if (pausedJoin.status !== 404) failures.push(`Paused world allowed join/select: ${pausedJoin.status}`);

  await adminTransition('open', 'G16 reanudar mundo');
  const resumedJoin = await api(playerPage, `/worlds/${worldId}/join`, { method: 'POST' });
  if (resumedJoin.status !== 200) failures.push(`Reopened world rejected existing membership: ${resumedJoin.status}`);
  if (resumedJoin.body?.id !== membershipId || resumedJoin.body?.starting_city_id !== startingCityId) {
    failures.push(
      `Resume did not preserve membership/city: before=${membershipId}/${startingCityId} after=${resumedJoin.body?.id}/${resumedJoin.body?.starting_city_id}`,
    );
  }

  await adminTransition('closed', 'G16 cerrar mundo');
  const closedJoin = await api(playerPage, `/worlds/${worldId}/join`, { method: 'POST' });
  if (closedJoin.status !== 404) failures.push(`Closed world allowed join/select: ${closedJoin.status}`);

  const closedCatalogue = await api(adminPage, '/worlds/');
  const closedWorld = closedCatalogue.body.find((world) => Number(world.id) === Number(worldId));
  if (closedWorld?.lifecycle_status !== 'closed' || !closedWorld?.ended_at) {
    failures.push(`Close did not persist terminal metadata: ${JSON.stringify(closedWorld)}`);
  }

  await adminTransition('archived', 'G16 archivar histórico');

  const archivedCatalogue = await api(adminPage, '/worlds/');
  const archivedWorld = archivedCatalogue.body.find((world) => Number(world.id) === Number(worldId));
  if (archivedWorld?.lifecycle_status !== 'archived') {
    failures.push(`Archive state not persisted: ${JSON.stringify(archivedWorld)}`);
  }
  if (archivedWorld?.ended_at !== closedWorld?.ended_at) {
    failures.push('Archiving changed ended_at');
  }

  const historicalCities = await api(playerPage, `/city/?world_id=${worldId}`);
  if (historicalCities.status !== 200) {
    failures.push(`Archived historical city read denied: ${historicalCities.status}`);
  } else if (!historicalCities.body.some((city) => Number(city.id) === Number(startingCityId))) {
    failures.push(`Archived world lost starting city ${startingCityId}`);
  }

  const afterArchiveJoin = await api(playerPage, `/worlds/${worldId}/join`, { method: 'POST' });
  if (afterArchiveJoin.status !== 404) failures.push(`Archived world allowed join/select: ${afterArchiveJoin.status}`);
} catch (error) {
  failures.push(`journey-error: ${error.stack || error.message}`);
} finally {
  await adminContext.close();
  await playerContext.close();
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G16 BM-0072 world lifecycle browser journey passed');
