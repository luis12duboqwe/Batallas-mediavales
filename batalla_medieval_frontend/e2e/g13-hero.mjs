import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g13_hero';
const PASSWORD = 'G13-Hero-Test-2026!';
const RULES_VERSION = '2026.08.25-bm0068-v1';
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
  // Dashboard hydrates both account and city stores; the App must keep this
  // invariant for direct protected-route navigation as well.
  await page.getByText(/Ciudad de g13_hero/).waitFor({ state: 'visible', timeout: 10000 });
}

async function stateSnapshot() {
  return page.evaluate(async ({ apiUrl }) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };

    const requestJson = async (url, options = {}) => {
      const response = await fetch(url, { ...options, headers: { ...headers, ...(options.headers || {}) } });
      if (!response.ok) throw new Error(`${url} ${response.status}: ${(await response.text()).slice(0, 300)}`);
      return response.json();
    };

    const profile = await requestJson(`${apiUrl}/auth/me`);
    const worldId = profile.world_id;
    const [hero, items, adventures, cities, balance] = await Promise.all([
      requestJson(`${apiUrl}/hero/?world_id=${worldId}`),
      requestJson(`${apiUrl}/hero/items?world_id=${worldId}`),
      requestJson(`${apiUrl}/adventure/?world_id=${worldId}`),
      requestJson(`${apiUrl}/city/?world_id=${worldId}`),
      requestJson(`${apiUrl}/economy/balance_preview`),
    ]);
    const city = cities.find((entry) => Number(entry.id) === Number(hero.city_id));
    if (!city) throw new Error(`Hero city ${hero.city_id} not present in owned city list`);
    return { profile, worldId, hero, items, adventures, city, balance };
  }, { apiUrl: API_URL });
}

const compactState = (snapshot, adventureId) => {
  const adventure = snapshot.adventures.find((entry) => Number(entry.id) === Number(adventureId));
  return {
    hero: {
      id: snapshot.hero.id,
      world_id: snapshot.hero.world_id,
      city_id: snapshot.hero.city_id,
      level: snapshot.hero.level,
      xp: snapshot.hero.xp,
      health: snapshot.hero.health,
      status: snapshot.hero.status,
      attack_points: snapshot.hero.attack_points,
      defense_points: snapshot.hero.defense_points,
      production_points: snapshot.hero.production_points,
    },
    items: snapshot.items
      .map((item) => ({
        id: item.id,
        template_id: item.template_id,
        is_equipped: item.is_equipped,
        name: item.template?.name || item.name || null,
        slot: item.template?.slot || item.slot || null,
      }))
      .sort((a, b) => a.id - b.id),
    resources: {
      wood: snapshot.city.wood,
      stone: snapshot.city.stone,
      iron: snapshot.city.iron,
      gold: snapshot.city.gold,
    },
    adventure: adventure ? {
      id: adventure.id,
      status: adventure.status,
      rules_version: adventure.rules_version,
      outcome_seed: adventure.outcome_seed,
      result: adventure.result,
      completed_at: adventure.completed_at,
    } : null,
  };
};

try {
  await login();
  const initial = await stateSnapshot();

  if (initial.hero.rules_version !== RULES_VERSION) {
    failures.push(`Hero API rules mismatch: ${initial.hero.rules_version}`);
  }
  if (Number(initial.hero.world_id) !== Number(initial.worldId)) {
    failures.push(`Hero escaped active world: hero=${initial.hero.world_id} active=${initial.worldId}`);
  }
  if (Number(initial.hero.available_points) !== 4) {
    failures.push(`Expected four level-2 attribute points, got ${initial.hero.available_points}`);
  }
  if (initial.balance?.hero?.rules_version !== RULES_VERSION) {
    failures.push(`Balance hero rules mismatch: ${initial.balance?.hero?.rules_version}`);
  }
  if (Number(initial.balance?.hero?.revive?.cost) !== 250) {
    failures.push(`Hero revive contract mismatch: ${JSON.stringify(initial.balance?.hero?.revive)}`);
  }

  const inventoryItem = initial.items.find((item) => !item.is_equipped && (item.template?.slot || item.slot) === 'weapon');
  if (!inventoryItem) throw new Error(`G13 weapon missing from inventory: ${JSON.stringify(initial.items)}`);
  const fixtureAdventure = initial.adventures.find(
    (entry) => entry.status === 'available' && Number(entry.duration) === 0 && entry.difficulty === 'easy',
  );
  if (!fixtureAdventure) throw new Error(`G13 zero-duration adventure missing: ${JSON.stringify(initial.adventures)}`);

  await page.goto(`${BASE_URL}/hero`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  await page.getByTestId('hero-view').waitFor({ state: 'visible', timeout: 10000 });
  const visibleRules = ((await page.getByTestId('hero-rules-version').textContent()) || '').trim();
  if (!visibleRules.includes(RULES_VERSION)) failures.push(`Hero UI rules mismatch: ${visibleRules}`);

  const itemCard = page.getByTestId(`hero-item-${inventoryItem.id}`);
  await itemCard.waitFor({ state: 'visible', timeout: 5000 });
  await itemCard.getByRole('button', { name: 'Equipar', exact: true }).click();
  const weaponSlot = page.getByTestId('hero-slot-weapon');
  await weaponSlot.getByText('Espada de Madera', { exact: true }).waitFor({ state: 'visible', timeout: 5000 });

  const equipped = await stateSnapshot();
  const equippedItem = equipped.items.find((item) => Number(item.id) === Number(inventoryItem.id));
  if (!equippedItem?.is_equipped) failures.push('UI equip did not persist through hero API');

  await page.goto(`${BASE_URL}/adventures`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  await page.getByTestId('adventures-view').waitFor({ state: 'visible', timeout: 10000 });
  await page.getByTestId(`adventure-start-${fixtureAdventure.id}`).click();

  const adventureCard = page.getByTestId(`adventure-${fixtureAdventure.id}`);
  const seedNode = adventureCard.getByTestId('adventure-seed');
  await seedNode.waitFor({ state: 'visible', timeout: 10000 });
  const seedText = ((await seedNode.textContent()) || '').replace(/^Seed:\s*/, '').trim();
  if (!/^[0-9a-f]{64}$/i.test(seedText)) failures.push(`Started adventure seed is not SHA-256: ${seedText}`);

  const claimButton = page.getByTestId(`adventure-claim-${fixtureAdventure.id}`);
  await claimButton.waitFor({ state: 'visible', timeout: 10000 });
  await claimButton.click();

  const resultModal = page.getByTestId('adventure-result');
  await resultModal.waitFor({ state: 'visible', timeout: 10000 });
  const uiVersion = ((await page.getByTestId('adventure-result-version').textContent()) || '').trim();
  const uiSeed = ((await page.getByTestId('adventure-result-seed').textContent()) || '').trim();
  if (uiVersion !== RULES_VERSION) failures.push(`Adventure result rules mismatch: ${uiVersion}`);
  if (uiSeed !== seedText) failures.push(`Adventure UI seed changed from start to claim: ${seedText} -> ${uiSeed}`);

  const afterUiClaim = await stateSnapshot();
  const afterUiCompact = compactState(afterUiClaim, fixtureAdventure.id);
  if (!afterUiCompact.adventure?.result) failures.push('Adventure result was not persisted after UI claim');
  if (afterUiCompact.adventure?.outcome_seed !== uiSeed) {
    failures.push(`Persisted adventure seed mismatch: ${afterUiCompact.adventure?.outcome_seed}`);
  }
  if (!['completed', 'failed'].includes(afterUiCompact.adventure?.status)) {
    failures.push(`Adventure did not reach terminal state: ${afterUiCompact.adventure?.status}`);
  }
  if (afterUiCompact.hero.status === 'adventure') failures.push('Hero remained busy after terminal adventure');

  const retryResult = await page.evaluate(async ({ apiUrl, worldId, adventureId }) => {
    const token = localStorage.getItem('bm_token');
    const response = await fetch(
      `${apiUrl}/adventure/${adventureId}/claim?world_id=${worldId}`,
      { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
    );
    if (!response.ok) throw new Error(`retry claim ${response.status}: ${(await response.text()).slice(0, 300)}`);
    return response.json();
  }, { apiUrl: API_URL, worldId: initial.worldId, adventureId: fixtureAdventure.id });

  if (JSON.stringify(retryResult) !== JSON.stringify(afterUiCompact.adventure.result)) {
    failures.push(`Retry did not replay stored result: retry=${JSON.stringify(retryResult)} stored=${JSON.stringify(afterUiCompact.adventure.result)}`);
  }

  const afterRetry = await stateSnapshot();
  const afterRetryCompact = compactState(afterRetry, fixtureAdventure.id);
  if (JSON.stringify(afterRetryCompact) !== JSON.stringify(afterUiCompact)) {
    failures.push(
      `Committed claim retry mutated hero/items/resources/adventure:\n` +
      `before=${JSON.stringify(afterUiCompact)}\nafter=${JSON.stringify(afterRetryCompact)}`,
    );
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

console.log('G13 BM-0068 hero items adventures browser journey passed');
