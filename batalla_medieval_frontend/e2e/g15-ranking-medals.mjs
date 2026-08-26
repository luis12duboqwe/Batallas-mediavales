import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g15_alpha';
const PASSWORD = 'G15-Ranking-Test-2026!';
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
    try { body = (await response.text()).slice(0, 500); } catch { body = '<unreadable>'; }
    failures.push(`HTTP ${response.status()}: ${response.url()} body=${body}`);
  }
});

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
}

async function snapshot() {
  return page.evaluate(async (apiUrl) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };
    const get = async (url) => {
      const response = await fetch(url, { headers });
      if (!response.ok) throw new Error(`${url} ${response.status}: ${(await response.text()).slice(0, 300)}`);
      return response.json();
    };
    const profile = await get(`${apiUrl}/auth/me`);
    const worldId = profile.world_id;
    const cities = await get(`${apiUrl}/city/?world_id=${worldId}`);
    const city = cities[0];
    const troops = await get(`${apiUrl}/troops/${city.id}`);
    const medals = await get(`${apiUrl}/achievement/list?world_id=${worldId}`);
    return {
      worldId,
      cityId: city.id,
      resources: { wood: city.wood, stone: city.stone, iron: city.iron, gold: city.gold },
      troops: troops.map((row) => ({ unit_type: row.unit_type, quantity: row.quantity })).sort((a, b) => a.unit_type.localeCompare(b.unit_type)),
      medal: medals.find((entry) => entry.achievement.title === 'G15 Honor sin ventaja') || null,
    };
  }, API_URL);
}

try {
  await login();
  const before = await snapshot();
  if (!before.medal) throw new Error('G15 honor medal fixture missing');
  if (before.medal.progress.status !== 'completed') failures.push(`Expected completed medal before claim, got ${before.medal.progress.status}`);

  await page.goto(`${BASE_URL}/ranking`, { waitUntil: 'networkidle' });
  await page.getByTestId('ranking-view').waitFor({ state: 'visible', timeout: 10000 });

  const firstPlayer = page.getByTestId('ranking-row-1');
  await firstPlayer.waitFor({ state: 'visible', timeout: 10000 });
  const firstText = await firstPlayer.innerText();
  if (!firstText.includes('g15_alpha')) failures.push(`Tie-break did not rank g15_alpha first: ${firstText}`);

  await page.getByTestId('ranking-tab-medals').click();
  const medalCard = page.getByTestId(`honor-medal-${before.medal.achievement.id}`);
  await medalCard.waitFor({ state: 'visible', timeout: 10000 });
  const cardText = await medalCard.innerText();
  if (cardText.includes('999999')) failures.push('Legacy reward value leaked into honor-medal UI');
  if (!cardText.includes('no otorga recursos')) failures.push('Honor-only disclaimer missing from medal UI');

  await page.getByTestId(`honor-medal-claim-${before.medal.achievement.id}`).click();
  await page.getByTestId(`honor-medal-claimed-${before.medal.achievement.id}`).waitFor({ state: 'visible', timeout: 10000 });

  const after = await snapshot();
  if (after.medal?.progress.status !== 'claimed') failures.push(`Medal was not persisted as claimed: ${after.medal?.progress.status}`);
  if (JSON.stringify(after.resources) !== JSON.stringify(before.resources)) {
    failures.push(`Claim changed resources: before=${JSON.stringify(before.resources)} after=${JSON.stringify(after.resources)}`);
  }
  if (JSON.stringify(after.troops) !== JSON.stringify(before.troops)) {
    failures.push(`Claim changed troops: before=${JSON.stringify(before.troops)} after=${JSON.stringify(after.troops)}`);
  }
  if ('reward_type' in after.medal.achievement || 'reward_value' in after.medal.achievement) {
    failures.push(`Reward fields leaked through API: ${JSON.stringify(after.medal.achievement)}`);
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
console.log('G15 BM-0071 ranking and honor medals browser journey passed');
