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
  if (message.type() === 'error') {
    failures.push(`mobile console.error: ${message.text()}`);
  }
});
page.on('pageerror', (error) => {
  failures.push(`mobile pageerror: ${error.message}`);
});
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
  await login();

  const mobileNavigation = await waitForMobileNavigation('/');
  await assertViewport('/');

  // BM-0083 ships v1.0 in Spanish only. Historical user/browser language
  // preferences must not switch the authenticated runtime back to English.
  await page.waitForFunction(() => document.body.innerText.includes('Ciudad'));
  if (!(await mobileNavigation.getByRole('link', { name: 'Edificios' }).isVisible())) {
    failures.push('El enlace Edificios no es accesible en la navegación móvil');
  }
  if (!(await mobileNavigation.getByRole('link', { name: 'Mercado' }).isVisible())) {
    failures.push('El enlace Mercado no es accesible en la navegación móvil');
  }

  // Keyboard focus and activation must work even though this browser context
  // also advertises touch support.
  const mapLink = mobileNavigation.getByRole('link', { name: 'Mapa' });
  await mapLink.focus();
  const focused = await mapLink.evaluate((element) => element === document.activeElement);
  if (!focused) failures.push('Mobile navigation link could not receive keyboard focus');
  await page.keyboard.press('Enter');
  await page.waitForURL(`${BASE_URL}/map`, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await assertViewport('/map');

  // Every visible MVP route must remain usable while API responses are delayed.
  // This turns mobile/latency regressions and hidden 4xx/5xx calls into a CI gate.
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

  const runtimeLanguage = page.getByTestId('runtime-language');
  await runtimeLanguage.waitFor({ state: 'visible' });
  if (!(await runtimeLanguage.innerText()).includes('Español')) {
    failures.push('El perfil no informa que el idioma de v1.0 es Español');
  }
  if (await page.locator('#profile-language, select[name="language"]').count()) {
    failures.push('El selector de idioma retirado sigue visible en el perfil');
  }

  // A stale preference from the old detector must not reactivate the retired
  // English catalog after a hard reload.
  await page.evaluate(() => localStorage.setItem('i18nextLng', 'en'));
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Perfil de Usuario' }).waitFor();
  if (await page.locator('#profile-language, select[name="language"]').count()) {
    failures.push('Una preferencia antigua reactivó el selector de idioma');
  }
  if (!(await page.getByTestId('mobile-navigation').getByRole('link', { name: 'Ciudad' }).isVisible())) {
    failures.push('Una preferencia antigua de inglés cambió la navegación fuera de español');
  }
  if (await page.getByText('English', { exact: true }).count()) {
    failures.push('La opción English reapareció tras recargar el perfil');
  }
  await assertViewport('/profile?runtime=es');

  if (failures.length > 0) {
    throw new Error(failures.join('\n'));
  }

  console.log(`G4 UX smoke passed: all visible routes at 390x844, keyboard focus, ${API_DELAY_MS}ms API delay and Spanish-only locale persistence`);
} finally {
  await browser.close();
}
