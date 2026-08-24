import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g11_commerce';
const PASSWORD = 'G11-Commerce-Test-2026!';
const RULES_VERSION = '2026.08.24-bm0066-v1';

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
  return page.evaluate(async ({ apiUrl }) => {
    const token = localStorage.getItem('bm_token');
    const headers = { Authorization: `Bearer ${token}` };

    const profileResponse = await fetch(`${apiUrl}/auth/me`, { headers });
    if (!profileResponse.ok) throw new Error(`profile ${profileResponse.status}`);
    const profile = await profileResponse.json();

    const citiesResponse = await fetch(`${apiUrl}/city/?world_id=${profile.world_id}`, { headers });
    if (!citiesResponse.ok) throw new Error(`cities ${citiesResponse.status}`);
    const cities = await citiesResponse.json();

    const reportsResponse = await fetch(`${apiUrl}/report/?world_id=${profile.world_id}`, { headers });
    if (!reportsResponse.ok) throw new Error(`reports ${reportsResponse.status}`);
    const reports = await reportsResponse.json();

    const movementsResponse = await fetch(`${apiUrl}/movement/?world_id=${profile.world_id}`, { headers });
    if (!movementsResponse.ok) throw new Error(`movements ${movementsResponse.status}`);
    const movements = await movementsResponse.json();

    const balanceResponse = await fetch(`${apiUrl}/economy/balance_preview`);
    if (!balanceResponse.ok) throw new Error(`balance ${balanceResponse.status}`);
    const balance = await balanceResponse.json();

    return { profile, cities, reports, movements, balance };
  }, { apiUrl: API_URL });
}

try {
  await login();
  const snapshot = await apiSnapshot();
  const rules = snapshot.balance?.market || {};

  if (rules.rules_version !== RULES_VERSION) failures.push(`Commerce rules version mismatch: ${rules.rules_version}`);
  if (rules.available_from_start !== true) failures.push('Commerce must be available from start');
  if (Number(rules.base_merchant_capacity) !== 500) failures.push(`Base merchant capacity mismatch: ${rules.base_merchant_capacity}`);
  if (Number(rules.merchant_capacity_per_level) !== 1000) failures.push(`Market capacity per level mismatch: ${rules.merchant_capacity_per_level}`);
  if (rules.merchant_capacity_released_on_return !== true) failures.push('Merchant capacity must release on return');
  if (rules.overflow_returns_to_sender !== true) failures.push('Overflow must return to sender');
  if (Number(rules.max_active_offers) !== 5) failures.push(`Max active offers mismatch: ${rules.max_active_offers}`);
  if (Number(rules.market_ratio_min) !== 0.25 || Number(rules.market_ratio_max) !== 4) {
    failures.push(`Market ratio bounds mismatch: ${JSON.stringify(rules)}`);
  }
  if (Number(rules.npc_trade_rate) !== 0.8) failures.push(`NPC rate mismatch: ${rules.npc_trade_rate}`);
  if (Number(rules.npc_trade_min_amount) !== 10 || Number(rules.npc_trade_max_amount) !== 250) {
    failures.push(`NPC amount bounds mismatch: ${JSON.stringify(rules)}`);
  }

  const activeCity = snapshot.cities[0];
  if (!activeCity) throw new Error('G11 user has no active city');
  if ((activeCity.buildings || []).some((building) => building.name === 'market')) {
    failures.push('G11 start city unexpectedly has a market building');
  }

  const parsedTradeReports = snapshot.reports
    .filter((report) => report.report_type === 'trade')
    .map((report) => {
      try {
        return JSON.parse(report.content);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
  const rejected = parsedTradeReports.filter(
    (payload) => payload.return_reason === 'insufficient_storage' && payload.delivered === false,
  );
  const returned = parsedTradeReports.filter((payload) => payload.type === 'transport_return');
  if (rejected.length !== 1) failures.push(`Expected one rejected transport audit report, got ${rejected.length}`);
  if (returned.length !== 1) failures.push(`Expected one completed cargo return report, got ${returned.length}`);
  if (rejected.length === 1 && Number(rejected[0].resources?.wood) !== 100) {
    failures.push(`Rejected audit cargo mismatch: ${JSON.stringify(rejected[0])}`);
  }
  if (returned.length === 1 && Number(returned[0].resources?.wood) !== 100) {
    failures.push(`Return audit cargo mismatch: ${JSON.stringify(returned[0])}`);
  }

  const completedOutbound = snapshot.movements.filter(
    (movement) => movement.movement_type === 'transport'
      && movement.status === 'completed'
      && Number(movement.resources?.wood) === 100,
  );
  const completedReturns = snapshot.movements.filter(
    (movement) => movement.movement_type === 'transport_return'
      && movement.status === 'completed'
      && Number(movement.resources?.capacity) === 100
      && Number(movement.resources?.wood) === 100,
  );
  if (completedOutbound.length !== 1) failures.push(`Expected one completed G11 outbound transport, got ${completedOutbound.length}`);
  if (completedReturns.length !== 1) failures.push(`Expected one completed G11 merchant return, got ${completedReturns.length}`);

  await page.goto(`${BASE_URL}/market`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();

  const rulesPanel = page.getByTestId('commerce-rules');
  await rulesPanel.waitFor({ state: 'visible', timeout: 10000 });
  const uiRulesVersion = await rulesPanel.getAttribute('data-rules-version');
  if (uiRulesVersion !== RULES_VERSION) failures.push(`UI commerce version mismatch: ${uiRulesVersion}`);
  const rulesText = (await rulesPanel.textContent()) || '';
  for (const expected of ['500', '1000', '5', '0.25', '4']) {
    if (!rulesText.includes(expected)) failures.push(`Commerce rules UI is missing ${expected}: ${rulesText}`);
  }
  if (!rulesText.includes('disponible desde el inicio')) failures.push(`Commerce start-access copy missing: ${rulesText}`);
  if (!rulesText.includes('vuelven al remitente') && !rulesText.includes('vuelve al remitente')) {
    failures.push(`Lossless return copy missing: ${rulesText}`);
  }

  const wholeMarketText = (await page.locator('body').textContent()) || '';
  if (wholeMarketText.includes('Ratio 1:1') || wholeMarketText.includes('(1:1)')) {
    failures.push('Legacy NPC 1:1 copy is still visible');
  }

  await page.getByRole('tab', { name: 'Mis Ofertas' }).click();
  const allianceOnly = page.getByText('Solo miembros de mi alianza pueden aceptar esta oferta', { exact: true });
  await allianceOnly.waitFor({ state: 'visible', timeout: 5000 });
  const offerAmount = page.locator('#market-offer-amount');
  if (await offerAmount.getAttribute('min') !== '10') failures.push(`Offer minimum UI mismatch: ${await offerAmount.getAttribute('min')}`);

  await page.getByRole('tab', { name: 'Comerciante NPC' }).click();
  await page.getByRole('heading', { name: /Comerciante NPC \(80% de retorno\)/ }).waitFor({ state: 'visible', timeout: 5000 });
  const npcAmount = page.locator('#market-npc-amount');
  if (await npcAmount.getAttribute('min') !== '10') failures.push(`NPC min UI mismatch: ${await npcAmount.getAttribute('min')}`);
  if (await npcAmount.getAttribute('max') !== '250') failures.push(`NPC max UI mismatch: ${await npcAmount.getAttribute('max')}`);
  await npcAmount.fill('100');
  const preview = page.getByTestId('market-npc-received');
  await preview.waitFor({ state: 'visible', timeout: 5000 });
  if (await preview.inputValue() !== '80') failures.push(`NPC 100→80 preview mismatch: ${await preview.inputValue()}`);

  await page.getByRole('button', { name: 'Intercambiar', exact: true }).click();
  const success = page.getByText('Intercambio NPC: entregaste 100 Madera y recibiste 80 Piedra.', { exact: true });
  await success.waitFor({ state: 'visible', timeout: 10000 });
} catch (error) {
  failures.push(`journey-error: ${error.stack || error.message}`);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G11 BM-0066 commerce-from-start browser journey passed');
