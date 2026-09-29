import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const API_DELAY_MS = 250;
const UI_READY_TIMEOUT_MS = 15000;

const failures = [];
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
});
const page = await context.newPage();

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

await page.route('**/*', async (route) => {
  const url = route.request().url();
  if (url.startsWith(API_URL) && !url.includes('/socket.io')) {
    await delay(API_DELAY_MS);
  }
  await route.continue();
});

page.on('console', (message) => {
  if (message.type() === 'error') failures.push(`mobile console.error: ${message.text()}`);
});
page.on('pageerror', (error) => failures.push(`mobile pageerror: ${error.message}`));
page.on('response', async (response) => {
  if (response.status() >= 400) {
    let body = '';
    try {
      body = (await response.text()).slice(0, 1000);
    } catch {
      body = '<unreadable>';
    }
    failures.push(`mobile HTTP ${response.status()}: ${response.url()} body=${body}`);
  }
});

async function waitForMobileNavigation(route) {
  const navigation = page.getByTestId('mobile-navigation');
  try {
    await navigation.waitFor({ state: 'visible', timeout: UI_READY_TIMEOUT_MS });
    return navigation;
  } catch {
    failures.push(`Mobile navigation did not become visible on ${route} within ${UI_READY_TIMEOUT_MS}ms`);
    return navigation;
  }
}

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 20000 });
  await page.waitForLoadState('networkidle');
}

async function assertViewport(route) {
  await waitForMobileNavigation(route);
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  if (overflow.scrollWidth > overflow.clientWidth + 1) {
    failures.push(`${route} overflows viewport horizontally: ${JSON.stringify(overflow)}`);
  }
  if (page.url().includes('/login')) {
    failures.push(`Slow API responses caused an unexpected logout on ${route}`);
  }
}

try {
  // Simulate an old browser preference before login. Production must ignore it
  // because BM-0083 intentionally ships Spanish as the only supported locale.
  await page.addInitScript(() => localStorage.setItem('i18nextLng', 'en'));
  await login();

  const mobileNavigation = await waitForMobileNavigation('/');
  await assertViewport('/');

  await page.waitForFunction(() => document.body.innerText.includes('Ciudad'));
  if (!(await mobileNavigation.getByRole('link', { name: 'Edificios' }).isVisible())) {
    failures.push('Spanish Buildings link is not reachable in mobile navigation');
  }
  if (!(await mobileNavigation.getByRole('link', { name: 'Mercado' }).isVisible())) {
    failures.push('Spanish Market link is not reachable in mobile navigation');
  }

  const mapLink = mobileNavigation.getByRole('link', { name: 'Mapa' });
  await mapLink.focus();
  const focused = await mapLink.evaluate((element) => element === document.activeElement);
  if (!focused) failures.push('Mobile navigation link could not receive keyboard focus');
  await page.keyboard.press('Enter');
  await page.waitForURL(`${BASE_URL}/map`, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await assertViewport('/map');

  const visibleRoutes = [
    '/buildings',
    '/academy',
    '/troops',
    '/map',
    '/movements',
    '/reports',
    '/market',
    '/ranking',
    '/alliance',
    '/messages',
  ];
  for (const route of visibleRoutes) {
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' });
    await assertViewport(route);
  }

  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Perfil de Usuario' }).waitFor();
  await assertViewport('/profile');

  const languageDisplay = page.getByTestId('profile-language');
  if ((await languageDisplay.textContent())?.trim() !== 'Español') {
    failures.push('Profile does not expose Spanish as the production language');
  }
  if (await page.locator('select[name="language"]').count()) {
    failures.push('Profile still exposes a selectable language control');
  }
  if (await page.locator('option[value="en"]').count()) {
    failures.push('English is still selectable in production');
  }

  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Perfil de Usuario' }).waitFor();
  if (!(await page.getByTestId('profile-language').isVisible())) {
    failures.push('Spanish-only profile state did not persist after reload');
  }
  if (!(await page.getByTestId('mobile-navigation').getByRole('link', { name: 'Ciudad' }).isVisible())) {
    failures.push('Legacy English browser preference changed UI after reload');
  }
  await assertViewport('/profile');

  if (failures.length > 0) throw new Error(failures.join('\n'));

  console.log(`G4 UX smoke passed: mobile routes, keyboard focus, ${API_DELAY_MS}ms API delay and Spanish-only localization policy`);
} finally {
  await browser.close();
}
