import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';

const failures = [];
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

page.on('console', (message) => {
  if (message.type() === 'error') {
    failures.push(`console.error: ${message.text()}`);
  }
});
page.on('pageerror', (error) => {
  failures.push(`pageerror: ${error.message}`);
});
page.on('response', async (response) => {
  if (response.status() >= 400) {
    let body = '';
    try {
      body = (await response.text()).slice(0, 1000);
    } catch {
      body = '<unreadable>';
    }
    const diagnostic = `HTTP ${response.status()}: ${response.url()} body=${body}`;
    console.log(diagnostic);
    if (response.status() >= 500) {
      failures.push(diagnostic);
    }
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

async function durableSnapshot() {
  return page.evaluate(async (apiUrl) => {
    const token = localStorage.getItem('bm_token');
    if (!token) throw new Error('Missing bm_token after authenticated navigation');
    const headers = { Authorization: `Bearer ${token}` };
    const profileResponse = await fetch(`${apiUrl}/auth/me`, { headers });
    if (!profileResponse.ok) {
      throw new Error(`Profile snapshot failed: ${profileResponse.status}`);
    }
    const profile = await profileResponse.json();
    const citiesResponse = await fetch(`${apiUrl}/city/?world_id=${profile.world_id}`, { headers });
    if (!citiesResponse.ok) {
      throw new Error(`City snapshot failed: ${citiesResponse.status}`);
    }
    const cities = await citiesResponse.json();
    return {
      userId: profile.id,
      worldId: profile.world_id,
      cityIds: cities.map((city) => city.id).sort((a, b) => a - b),
    };
  }, API_URL);
}

try {
  await login();
  const initialSnapshot = await durableSnapshot();
  if (!initialSnapshot.worldId || initialSnapshot.cityIds.length === 0) {
    failures.push(`Authenticated fixture has no durable world/city progress: ${JSON.stringify(initialSnapshot)}`);
  }

  await page.getByTestId('logout-button').click();
  await page.waitForURL(`${BASE_URL}/login`, { timeout: 10000 });
  await login();
  const reloggedSnapshot = await durableSnapshot();
  if (JSON.stringify(reloggedSnapshot) !== JSON.stringify(initialSnapshot)) {
    failures.push(`Re-login changed durable progress: ${JSON.stringify({ initialSnapshot, reloggedSnapshot })}`);
  }

  await page.reload({ waitUntil: 'networkidle' });
  if (new URL(page.url()).pathname !== '/') {
    failures.push(`Reload did not preserve the game route: ${page.url()}`);
  }
  const reloadedSnapshot = await durableSnapshot();
  if (JSON.stringify(reloadedSnapshot) !== JSON.stringify(initialSnapshot)) {
    failures.push(`Reload changed durable progress: ${JSON.stringify({ initialSnapshot, reloadedSnapshot })}`);
  }

  const acceptedRoutes = [
    '/',
    '/buildings',
    '/academy',
    '/troops',
    '/map',
    '/movements',
    '/reports',
  ];
  for (const route of acceptedRoutes) {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' });
    if (page.url().includes('/login')) {
      failures.push(`Unexpected logout while opening ${route}`);
    }
  }

  await page.goto(`${BASE_URL}/hero`, { waitUntil: 'networkidle' });
  if (new URL(page.url()).pathname !== '/') {
    failures.push(`Postponed route /hero did not redirect to /: ${page.url()}`);
  }

  const visibleText = await page.locator('body').innerText();
  for (const forbidden of ['Hero', 'Aventuras', 'Tienda', 'Simulador']) {
    if (visibleText.includes(forbidden)) {
      failures.push(`Postponed navigation leaked into MVP UI: ${forbidden}`);
    }
  }

  if (failures.length > 0) {
    throw new Error(failures.join('\n'));
  }
  console.log('G2 browser smoke passed: logout/re-login and reload are stable, no console errors or HTTP 5xx');
} finally {
  await browser.close();
}
