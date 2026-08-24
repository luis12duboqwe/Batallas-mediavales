import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const PROMOTION_CAMP = 'G6 Promotion Camp';
const NEW_CAMP = 'G6 Founded Camp';

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

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
}

async function apiSnapshot() {
  return page.evaluate(async (apiUrl) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };
    const profileResponse = await fetch(`${apiUrl}/auth/me`, { headers });
    const profile = await profileResponse.json();
    const citiesResponse = await fetch(`${apiUrl}/city/?world_id=${profile.world_id}`, { headers });
    const cities = await citiesResponse.json();
    const statusResponse = await fetch(`${apiUrl}/expansion/status?world_id=${profile.world_id}`, { headers });
    const status = await statusResponse.json();
    return { profile, cities, status };
  }, API_URL);
}

async function findFreeTile(snapshot) {
  const capital = snapshot.cities.find((city) => city.settlement_type === 'city');
  if (!capital) throw new Error('No full city available for expansion E2E');

  return page.evaluate(async ({ apiUrl, worldId, x, y }) => {
    const token = localStorage.getItem('bm_token');
    const response = await fetch(
      `${apiUrl}/map/tiles?world_id=${worldId}&x=${x}&y=${y}&radius=8`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!response.ok) throw new Error(`Map lookup failed: ${response.status}`);
    const payload = await response.json();
    const tile = payload.tiles.find(
      (item) => item.type !== 'water' && !item.city_id && !item.oasis_id,
    );
    if (!tile) throw new Error('No free tile found in E2E map window');
    return { x: tile.x, y: tile.y };
  }, { apiUrl: API_URL, worldId: snapshot.profile.world_id, x: capital.x, y: capital.y });
}

try {
  await login();
  const initial = await apiSnapshot();
  if (initial.status.expansion_points !== 5) {
    failures.push(`Expected 5 initial expansion points, got ${initial.status.expansion_points}`);
  }
  const preparedCamp = initial.cities.find(
    (city) => city.name === PROMOTION_CAMP && city.settlement_type === 'camp',
  );
  if (!preparedCamp) {
    throw new Error('Prepared promotion camp is missing');
  }

  await page.goto(`${BASE_URL}/expansion`, { waitUntil: 'networkidle' });
  await page.getByTestId('expansion-view').waitFor({ state: 'visible' });

  // Target the durable fixture identity rather than presentation text. The card
  // intentionally decorates the name with a camp emoji, so exact visible text
  // is not a stable selector for this accepted journey.
  const campCard = page.getByTestId(`camp-${preparedCamp.id}`);
  await campCard.waitFor({ state: 'visible' });
  const renderedCampText = await campCard.textContent();
  if (!renderedCampText?.includes(PROMOTION_CAMP)) {
    failures.push(`Promotion camp card rendered unexpected text: ${renderedCampText}`);
  }
  await campCard.getByRole('button', { name: 'Promover' }).click();
  await page.getByText('Campamento promovido a ciudad.', { exact: true }).waitFor({ state: 'visible' });

  const afterPromotion = await apiSnapshot();
  if (afterPromotion.status.expansion_points !== 2) {
    failures.push(`Promotion should leave 2 points, got ${afterPromotion.status.expansion_points}`);
  }
  const promoted = afterPromotion.cities.find((city) => city.name === PROMOTION_CAMP);
  if (!promoted || promoted.settlement_type !== 'city') {
    failures.push(`Camp promotion was not durable: ${JSON.stringify(promoted)}`);
  }

  const freeTile = await findFreeTile(afterPromotion);
  await page.getByTestId('settlement-type').selectOption('camp');
  await page.getByTestId('settlement-name').fill(NEW_CAMP);
  await page.getByTestId('settlement-x').fill(String(freeTile.x));
  await page.getByTestId('settlement-y').fill(String(freeTile.y));
  await page.getByTestId('found-settlement-submit').click();
  await page.getByText('Campamento fundado correctamente.', { exact: true }).waitFor({ state: 'visible' });

  const finalSnapshot = await apiSnapshot();
  if (finalSnapshot.status.expansion_points !== 0) {
    failures.push(`Founding should consume remaining points, got ${finalSnapshot.status.expansion_points}`);
  }
  const founded = finalSnapshot.cities.find((city) => city.name === NEW_CAMP);
  if (!founded || founded.settlement_type !== 'camp') {
    failures.push(`Founded camp missing or wrong type: ${JSON.stringify(founded)}`);
  }
  if (finalSnapshot.status.city_count < 2 || finalSnapshot.status.camp_count < 1) {
    failures.push(`Unexpected territorial counts: ${JSON.stringify(finalSnapshot.status)}`);
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

console.log('G6 expansion browser journey passed');
