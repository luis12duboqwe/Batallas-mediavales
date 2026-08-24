import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g7_research';
const PASSWORD = 'G7-Research-Test-2026!';
const PRIMARY_TECH = 'heavy_infantry';
const SECONDARY_TECH = 'archer';
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

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
}

async function apiSnapshot() {
  return page.evaluate(async ({ apiUrl, primaryTech, secondaryTech }) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };
    const profileResponse = await fetch(`${apiUrl}/auth/me`, { headers });
    const profile = await profileResponse.json();
    const citiesResponse = await fetch(`${apiUrl}/city/?world_id=${profile.world_id}`, { headers });
    const cities = await citiesResponse.json();
    const city = cities[0];
    if (!city) throw new Error('Research E2E user has no city');

    const [statusResponse, catalogResponse, queueResponse] = await Promise.all([
      fetch(`${apiUrl}/city/${city.id}/status?world_id=${profile.world_id}`, { headers }),
      fetch(`${apiUrl}/troop/available?city_id=${city.id}&world_id=${profile.world_id}`, { headers }),
      fetch(`${apiUrl}/queue/research?world_id=${profile.world_id}`, { headers }),
    ]);
    const status = await statusResponse.json();
    const catalog = await catalogResponse.json();
    const queues = await queueResponse.json();
    return {
      profile,
      city,
      status,
      queues,
      primary: catalog.find((item) => item.unit_type === primaryTech),
      secondary: catalog.find((item) => item.unit_type === secondaryTech),
    };
  }, { apiUrl: API_URL, primaryTech: PRIMARY_TECH, secondaryTech: SECONDARY_TECH });
}

try {
  await login();
  const initial = await apiSnapshot();
  if (!initial.primary?.can_research || !initial.secondary?.can_research) {
    throw new Error(`Prepared technologies are not both researchable: ${JSON.stringify({ primary: initial.primary, secondary: initial.secondary })}`);
  }
  if (initial.queues.length !== 0) {
    throw new Error(`Research fixture started with an occupied queue: ${JSON.stringify(initial.queues)}`);
  }

  await page.goto(`${BASE_URL}/academy`, { waitUntil: 'networkidle' });
  await page.getByTestId('academy-view').waitFor({ state: 'visible' });

  const primaryCard = page.getByTestId(`research-card-${PRIMARY_TECH}`);
  await primaryCard.waitFor({ state: 'visible' });
  await primaryCard.getByTestId(`research-action-${PRIMARY_TECH}`).click();
  await page.getByText('Investigación de Soldado de Acero iniciada', { exact: true }).waitFor({ state: 'visible' });
  await page.getByTestId('research-active-queue').waitFor({ state: 'visible' });

  const activeText = await page.getByTestId('research-active-tech').textContent();
  if (!activeText?.includes('Soldado de Acero')) {
    failures.push(`Unexpected active research text: ${activeText}`);
  }

  const secondaryAction = page.getByTestId(`research-action-${SECONDARY_TECH}`);
  await secondaryAction.waitFor({ state: 'visible' });
  const secondaryLabel = await secondaryAction.textContent();
  if (!secondaryLabel?.includes('Cola de investigación ocupada')) {
    failures.push(`Second eligible technology was not blocked by queue: ${secondaryLabel}`);
  }
  if (!(await secondaryAction.isDisabled())) {
    failures.push('Second eligible research action remained enabled while queue was occupied');
  }

  const queued = await apiSnapshot();
  if (queued.queues.length !== 1 || queued.queues[0].tech_name !== PRIMARY_TECH) {
    failures.push(`Research queue was not durable: ${JSON.stringify(queued.queues)}`);
  }
  if (queued.primary.researched || !queued.primary.research_queued) {
    failures.push(`Queued research unlocked too early: ${JSON.stringify(queued.primary)}`);
  }

  for (const resource of RESOURCE_FIELDS) {
    const expected = initial.status[resource] - Number(initial.primary.research_cost?.[resource] || 0);
    if (Math.abs(queued.status[resource] - expected) > 2) {
      failures.push(`Unexpected ${resource} charge: expected≈${expected}, got=${queued.status[resource]}`);
    }
  }

  await page.getByTestId('cancel-research').click();
  await page.getByText(
    'Investigación cancelada; se aplicó el reembolso correspondiente.',
    { exact: true },
  ).waitFor({ state: 'visible' });
  await page.getByTestId('research-active-queue').waitFor({ state: 'detached' });

  const finalSnapshot = await apiSnapshot();
  if (finalSnapshot.queues.length !== 0) {
    failures.push(`Research queue persisted after cancellation: ${JSON.stringify(finalSnapshot.queues)}`);
  }
  if (finalSnapshot.primary.researched || finalSnapshot.primary.research_queued) {
    failures.push(`Cancelled research changed unlock state: ${JSON.stringify(finalSnapshot.primary)}`);
  }

  for (const resource of RESOURCE_FIELDS) {
    const cost = Number(initial.primary.research_cost?.[resource] || 0);
    const expected = initial.status[resource] - cost * 0.2;
    if (Math.abs(finalSnapshot.status[resource] - expected) > 3) {
      failures.push(`Unexpected ${resource} after 80% refund: expected≈${expected}, got=${finalSnapshot.status[resource]}`);
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

console.log('G7 research browser journey passed');
