import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g10_espionage';
const PASSWORD = 'G10-Espionage-Test-2026!';
const ALGORITHM_VERSION = '2026.08.24-bm0065-v1';
const EXPECTED_REVEALED = ['resources', 'troops', 'buildings'];

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

    const reportsResponse = await fetch(`${apiUrl}/report/?world_id=${profile.world_id}`, { headers });
    if (!reportsResponse.ok) throw new Error(`reports ${reportsResponse.status}`);
    const reports = await reportsResponse.json();

    const movementsResponse = await fetch(`${apiUrl}/movement/?world_id=${profile.world_id}`, { headers });
    if (!movementsResponse.ok) throw new Error(`movements ${movementsResponse.status}`);
    const movements = await movementsResponse.json();

    const balanceResponse = await fetch(`${apiUrl}/economy/balance_preview`);
    if (!balanceResponse.ok) throw new Error(`balance ${balanceResponse.status}`);
    const balance = await balanceResponse.json();

    return { profile, reports, movements, balance };
  }, { apiUrl: API_URL });
}

try {
  await login();
  const snapshot = await apiSnapshot();
  const spyReports = snapshot.reports
    .filter((report) => report.report_type === 'spy')
    .map((report) => {
      try {
        return { report, payload: JSON.parse(report.content) };
      } catch {
        return null;
      }
    })
    .filter((entry) => entry?.payload?.algorithm_version === ALGORITHM_VERSION);

  if (spyReports.length !== 1) {
    throw new Error(`Expected one BM-0065 attacker spy report, got ${spyReports.length}`);
  }

  const { payload } = spyReports[0];
  if (payload.role !== 'attacker') failures.push(`Unexpected report role: ${payload.role}`);
  if (payload.success !== true) failures.push(`Expected successful espionage: ${JSON.stringify(payload)}`);
  if (payload.detected !== false) failures.push(`Expected undetected espionage: ${JSON.stringify(payload)}`);
  if (Number(payload.intel_level) !== 3) failures.push(`Expected intel level 3, got ${payload.intel_level}`);
  if (JSON.stringify(payload.revealed) !== JSON.stringify(EXPECTED_REVEALED)) {
    failures.push(`Unexpected revealed tiers: ${JSON.stringify(payload.revealed)}`);
  }
  if (!/^[0-9a-f]{64}$/i.test(payload.seed || '')) {
    failures.push(`Espionage seed is not SHA-256: ${payload.seed}`);
  }
  const luck = Number(payload.luck);
  if (luck < -0.20 || luck > 0.20) failures.push(`Espionage luck out of bounds: ${luck}`);
  const successChance = Number(payload.success_chance);
  const detectionChance = Number(payload.detection_chance);
  if (successChance < 0.05 || successChance > 0.95) failures.push(`Success chance out of bounds: ${successChance}`);
  if (detectionChance < 0.05 || detectionChance > 0.95) failures.push(`Detection chance out of bounds: ${detectionChance}`);
  if (Number(payload.troops?.archer) !== 9) failures.push(`Expected archer intelligence=9: ${JSON.stringify(payload.troops)}`);
  if (Number(payload.buildings?.wall) !== 3) failures.push(`Expected wall intelligence=3: ${JSON.stringify(payload.buildings)}`);
  for (const resource of ['wood', 'stone', 'iron', 'gold']) {
    if (!Number.isFinite(Number(payload.resources?.[resource]))) {
      failures.push(`Missing ${resource} intelligence: ${JSON.stringify(payload.resources)}`);
    }
  }

  const spyRules = snapshot.balance?.espionage || {};
  if (spyRules.algorithm_version !== ALGORITHM_VERSION) failures.push(`Balance preview algorithm mismatch: ${spyRules.algorithm_version}`);
  if (Number(spyRules.luck_min) !== -0.20 || Number(spyRules.luck_max) !== 0.20) failures.push(`Balance preview luck bounds mismatch: ${JSON.stringify(spyRules)}`);
  if (Number(spyRules.success_chance_min) !== 0.05 || Number(spyRules.success_chance_max) !== 0.95) failures.push(`Balance preview success bounds mismatch: ${JSON.stringify(spyRules)}`);
  if (Number(spyRules.detection_chance_min) !== 0.05 || Number(spyRules.detection_chance_max) !== 0.95) failures.push(`Balance preview detection bounds mismatch: ${JSON.stringify(spyRules)}`);
  if (JSON.stringify(spyRules.intel_levels?.['3']) !== JSON.stringify(EXPECTED_REVEALED)) failures.push(`Balance preview tier-3 mismatch: ${JSON.stringify(spyRules.intel_levels)}`);
  if (spyRules.undetected_creates_defender_report !== false) failures.push('Balance preview must state no defender report for undetected missions');

  const completedSpies = snapshot.movements.filter(
    (movement) => movement.movement_type === 'spy' && movement.status === 'completed',
  );
  const returns = snapshot.movements.filter(
    (movement) => movement.movement_type === 'return' && movement.status === 'ongoing',
  );
  if (completedSpies.length !== 1) failures.push(`Expected one completed spy mission, got ${completedSpies.length}`);
  if (returns.length !== 1) failures.push(`Expected one spy return, got ${returns.length}`);
  if (returns.length === 1 && Number(returns[0].troops?.spy) !== 6) {
    failures.push(`Expected six returning spies: ${JSON.stringify(returns[0].troops)}`);
  }

  await page.goto(`${BASE_URL}/reports`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  const reportHeading = page.getByText('Espionaje en G10 Intelligence Target', { exact: true });
  await reportHeading.waitFor({ state: 'visible', timeout: 10000 });
  await reportHeading.click();

  await page.getByText('¡Espionaje Exitoso!', { exact: true }).waitFor({ state: 'visible', timeout: 5000 });
  for (const label of ['Recursos', 'Tropas', 'Edificios']) {
    await page.getByText(label, { exact: true }).waitFor({ state: 'visible', timeout: 5000 });
  }

  const auditPanel = page.getByTestId('spy-audit');
  await auditPanel.waitFor({ state: 'visible', timeout: 5000 });
  const uiSeed = await auditPanel.getAttribute('data-spy-seed');
  if (uiSeed !== payload.seed) failures.push(`UI spy seed differs from API seed: ui=${uiSeed} api=${payload.seed}`);
  const visibleSeed = ((await page.getByTestId('spy-seed').textContent()) || '').trim();
  if (visibleSeed !== payload.seed) failures.push(`Visible spy seed differs from API seed: ${visibleSeed}`);
  const intelText = ((await page.getByTestId('spy-intel-level').textContent()) || '').trim();
  if (!intelText.includes('nivel 3')) failures.push(`UI intelligence level mismatch: ${intelText}`);

  const reportCard = reportHeading.locator('xpath=ancestor::*[contains(@class,"card")][1]');
  const reportText = (await reportCard.textContent()) || '';
  for (const expected of [
    'Arquero Real',
    '9',
    'wall',
    'Nivel 3',
    'Oculto',
    'Misión no detectada',
    ALGORITHM_VERSION,
    payload.balance_version,
  ]) {
    if (!reportText.includes(expected)) failures.push(`Spy report UI is missing ${expected}: ${reportText}`);
  }
  if (reportText.includes('undefined') || reportText.includes('NaN')) {
    failures.push(`Spy report leaked an invalid hidden value: ${reportText}`);
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

console.log('G10 BM-0065 complete espionage browser journey passed');
