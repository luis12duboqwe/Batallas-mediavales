import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g9_combat';
const PASSWORD = 'G9-Combat-Test-2026!';
const ALGORITHM_VERSION = '2026.08.24-bm0064-rounds-v1';
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

    return { profile, reports, movements };
  }, { apiUrl: API_URL });
}

const normalized = (value) => Object.fromEntries(
  Object.entries(value || {}).filter(([, amount]) => Number(amount || 0) !== 0),
);

try {
  await login();
  const snapshot = await apiSnapshot();
  const battleReports = snapshot.reports
    .filter((report) => report.report_type === 'battle')
    .map((report) => {
      try {
        return { report, payload: JSON.parse(report.content) };
      } catch {
        return null;
      }
    })
    .filter((entry) => entry?.payload?.combat?.seed);

  if (battleReports.length !== 1) {
    throw new Error(`Expected one auditable G9 report, got ${battleReports.length}`);
  }

  const { payload } = battleReports[0];
  const combat = payload.combat;
  if (combat.algorithm_version !== ALGORITHM_VERSION) {
    failures.push(`Unexpected algorithm version: ${combat.algorithm_version}`);
  }
  if (!/^[0-9a-f]{64}$/i.test(combat.seed || '')) {
    failures.push(`Combat seed is not an auditable SHA-256 value: ${combat.seed}`);
  }
  if (!Number.isInteger(Number(combat.round_count)) || Number(combat.round_count) < 1 || Number(combat.round_count) > 8) {
    failures.push(`Invalid round count: ${combat.round_count}`);
  }
  if (!Array.isArray(combat.rounds) || combat.rounds.length !== Number(combat.round_count)) {
    failures.push(`Round history does not match round_count: ${JSON.stringify(combat)}`);
  }
  for (const round of combat.rounds || []) {
    const luck = Number(round.luck);
    const moral = Number(round.moral);
    if (luck < -0.25 || luck > 0.25) failures.push(`Round ${round.round} luck out of bounds: ${luck}`);
    if (moral < 0.30 || moral > 1.50) failures.push(`Round ${round.round} moral out of bounds: ${moral}`);
  }

  const returns = snapshot.movements.filter(
    (movement) => movement.movement_type === 'return' && movement.status === 'ongoing',
  );
  const completedAttacks = snapshot.movements.filter(
    (movement) => movement.movement_type === 'attack' && movement.status === 'completed',
  );
  if (completedAttacks.length !== 1) failures.push(`Expected one completed attack, got ${completedAttacks.length}`);
  if (returns.length !== 1) failures.push(`Expected one return march, got ${returns.length}`);

  if (returns.length === 1) {
    const returnMarch = returns[0];
    const survivors = normalized(payload.attacker?.survivors);
    const returnTroops = normalized(returnMarch.troops);
    if (JSON.stringify(returnTroops) !== JSON.stringify(survivors)) {
      failures.push(`Return troops differ from report survivors: return=${JSON.stringify(returnTroops)} report=${JSON.stringify(survivors)}`);
    }
    for (const resource of RESOURCE_FIELDS) {
      const carried = Number(returnMarch.resources?.[resource] || 0);
      const reported = Number(payload.loot?.[resource] || 0);
      if (carried !== reported) {
        failures.push(`Return ${resource} differs from report loot: return=${carried} report=${reported}`);
      }
    }
  }

  await page.goto(`${BASE_URL}/reports`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  const auditPanel = page.getByTestId('combat-audit');
  await auditPanel.waitFor({ state: 'visible', timeout: 10000 });
  const uiSeed = await auditPanel.getAttribute('data-combat-seed');
  if (uiSeed !== combat.seed) failures.push(`UI seed differs from API seed: ui=${uiSeed} api=${combat.seed}`);

  const seedText = ((await page.getByTestId('combat-seed').textContent()) || '').trim();
  if (seedText !== combat.seed) failures.push(`Visible seed differs from API seed: ${seedText}`);
  const uiRounds = await page.getByTestId('combat-round').count();
  if (uiRounds !== Number(combat.round_count)) {
    failures.push(`UI rendered ${uiRounds} rounds, expected ${combat.round_count}`);
  }

  const auditText = (await auditPanel.textContent()) || '';
  for (const expected of [ALGORITHM_VERSION, combat.balance_version, `${combat.round_count} rondas`]) {
    if (!auditText.includes(expected)) failures.push(`Combat audit UI is missing ${expected}: ${auditText}`);
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

console.log('G9 BM-0064 deterministic round combat browser journey passed');
