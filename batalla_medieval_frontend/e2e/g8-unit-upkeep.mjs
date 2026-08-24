import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g8_upkeep';
const PASSWORD = 'G8-Upkeep-Test-2026!';
const UNIT_TYPE = 'noble';
const BLOCKED_AMOUNT = 17;
const TRAIN_AMOUNT = 1;
const RESOURCE_FIELDS = ['wood', 'stone', 'iron', 'gold'];

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

  // LoadingScreen is mounted immediately after IntroAnimation completes. Give
  // React one short window to attach it, then wait for its real completion.
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
  return page.evaluate(async ({ apiUrl, unitType }) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };
    const profileResponse = await fetch(`${apiUrl}/auth/me`, { headers });
    const profile = await profileResponse.json();
    const citiesResponse = await fetch(`${apiUrl}/city/?world_id=${profile.world_id}`, { headers });
    const cities = await citiesResponse.json();
    const city = cities[0];
    if (!city) throw new Error('BM-0063 E2E user has no city');

    const [statusResponse, catalogResponse] = await Promise.all([
      fetch(`${apiUrl}/city/${city.id}/status?world_id=${profile.world_id}`, { headers }),
      fetch(`${apiUrl}/troop/available?city_id=${city.id}&world_id=${profile.world_id}`, { headers }),
    ]);
    const status = await statusResponse.json();
    const catalog = await catalogResponse.json();
    return {
      profile,
      city,
      status,
      unit: catalog.find((item) => item.unit_type === unitType),
    };
  }, { apiUrl: API_URL, unitType: UNIT_TYPE });
}

async function waitForSnapshot(predicate, label, timeoutMs = 10000) {
  const started = Date.now();
  let last = null;
  while (Date.now() - started < timeoutMs) {
    last = await apiSnapshot();
    if (predicate(last)) return last;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`${label} timed out; last=${JSON.stringify(last)}`);
}

try {
  await login();
  const initial = await apiSnapshot();
  if (!initial.unit) throw new Error('Noble is missing from the final unit catalog');
  if (!initial.unit.researched || !initial.unit.training_requirements_met || !initial.unit.can_train) {
    throw new Error(`Prepared Noble is not trainable: ${JSON.stringify(initial.unit)}`);
  }
  if (initial.status.troop_queue.length !== 0) {
    throw new Error(`Fixture started with troop queue entries: ${JSON.stringify(initial.status.troop_queue)}`);
  }
  if (Math.abs(Number(initial.unit.upkeep_per_hour) - 0.5) > 1e-9) {
    failures.push(`Unexpected Noble upkeep: ${initial.unit.upkeep_per_hour}`);
  }
  if (Number(initial.unit.population_cost) !== 5) {
    failures.push(`Unexpected Noble population: ${initial.unit.population_cost}`);
  }
  if (Math.abs(Number(initial.status.upkeep_capacity_per_hour) - 8.0) > 1e-9) {
    failures.push(`Unexpected stable upkeep capacity: ${initial.status.upkeep_capacity_per_hour}`);
  }
  if (Number(initial.status.upkeep_used_per_hour) !== 0 || Number(initial.status.upkeep_reserved_per_hour) !== 0) {
    failures.push(`Fixture did not start with zero upkeep: ${JSON.stringify(initial.status)}`);
  }

  await page.goto(`${BASE_URL}/troops`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  const card = page.getByTestId(`troop-card-${UNIT_TYPE}`);
  await card.waitFor({ state: 'visible' });
  const statsText = (await page.getByTestId(`troop-stats-${UNIT_TYPE}`).textContent()) || '';
  for (const expected of ['0.50/h', 'Población: 5']) {
    if (!statsText.includes(expected)) failures.push(`Noble card missing ${expected}: ${statsText}`);
  }

  const resourceBar = page.getByTestId('resource-bar');
  const initialBarText = (await resourceBar.textContent()) || '';
  if (!initialBarText.includes('0.00/8.00/h')) {
    failures.push(`Resource bar did not expose zero upkeep against 8/h capacity: ${initialBarText}`);
  }

  const amountInput = card.locator('input[type="number"]');
  const trainAction = page.getByTestId(`train-action-${UNIT_TYPE}`);
  await amountInput.fill(String(BLOCKED_AMOUNT));
  await page.getByTestId(`upkeep-block-${UNIT_TYPE}`).waitFor({ state: 'visible' });
  if (!(await trainAction.isDisabled())) {
    failures.push('Training 17 Nobles was not blocked by sustainable gold upkeep');
  }

  // 17 Nobles use only 85 population but require 8.5 gold/h, proving that this
  // block is economic rather than a population-capacity rejection.
  if (BLOCKED_AMOUNT * Number(initial.unit.population_cost) > Number(initial.unit.population_available)) {
    failures.push('Fixture cannot isolate upkeep because blocked amount also exceeds population');
  }
  if (BLOCKED_AMOUNT * Number(initial.unit.upkeep_per_hour) <= Number(initial.unit.upkeep_available_per_hour)) {
    failures.push('Fixture cannot isolate upkeep because blocked amount fits gold headroom');
  }

  await amountInput.fill(String(TRAIN_AMOUNT));
  if (await trainAction.isDisabled()) {
    failures.push('Training one Noble remained disabled despite valid resources/population/upkeep');
  } else {
    await trainAction.click();
  }

  const queued = await waitForSnapshot(
    (snapshot) => snapshot.status.troop_queue.length === 1,
    'Noble training queue creation',
  );
  const queue = queued.status.troop_queue[0];
  if (queue.troop_type !== UNIT_TYPE || Number(queue.amount) !== TRAIN_AMOUNT) {
    failures.push(`Unexpected troop queue: ${JSON.stringify(queue)}`);
  }
  if (Math.abs(Number(queued.status.upkeep_reserved_per_hour) - 0.5) > 1e-9) {
    failures.push(`Queued Noble did not reserve 0.5 gold/h: ${queued.status.upkeep_reserved_per_hour}`);
  }
  if (Math.abs(Number(queued.status.upkeep_available_per_hour) - 7.5) > 1e-9) {
    failures.push(`Unexpected upkeep headroom after queue: ${queued.status.upkeep_available_per_hour}`);
  }
  if (!queued.status.upkeep_sustainable) {
    failures.push('One queued Noble incorrectly made the city unsustainable');
  }

  for (const resource of RESOURCE_FIELDS) {
    const expected = Number(initial.status[resource]) - Number(initial.unit.training_cost?.[resource] || 0);
    if (Math.abs(Number(queued.status[resource]) - expected) > 2) {
      failures.push(`Unexpected ${resource} training charge: expected≈${expected}, got=${queued.status[resource]}`);
    }
  }

  await page.getByTestId(`cancel-troop-${queue.id}`).click();
  const finalSnapshot = await waitForSnapshot(
    (snapshot) => snapshot.status.troop_queue.length === 0,
    'Noble training cancellation',
  );
  if (Math.abs(Number(finalSnapshot.status.upkeep_reserved_per_hour)) > 1e-9) {
    failures.push(`Cancellation did not release upkeep reservation: ${finalSnapshot.status.upkeep_reserved_per_hour}`);
  }
  if (Math.abs(Number(finalSnapshot.status.upkeep_available_per_hour) - 8.0) > 1e-9) {
    failures.push(`Cancellation did not restore upkeep headroom: ${finalSnapshot.status.upkeep_available_per_hour}`);
  }

  for (const resource of RESOURCE_FIELDS) {
    const cost = Number(initial.unit.training_cost?.[resource] || 0);
    const expected = Number(initial.status[resource]) - cost * 0.2;
    if (Math.abs(Number(finalSnapshot.status[resource]) - expected) > 3) {
      failures.push(`Unexpected ${resource} after 80% training refund: expected≈${expected}, got=${finalSnapshot.status[resource]}`);
    }
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

console.log('G8 BM-0063 unit upkeep browser journey passed');
