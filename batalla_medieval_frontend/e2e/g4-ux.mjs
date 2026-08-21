import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const API_DELAY_MS = 250;

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

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 20000 });
  await page.waitForLoadState('networkidle');
}

try {
  await login();

  const mobileNavigation = page.getByTestId('mobile-navigation');
  if (!(await mobileNavigation.isVisible())) {
    failures.push('Mobile navigation is not visible at 390x844');
  }

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  if (overflow.scrollWidth > overflow.clientWidth + 1) {
    failures.push(`Page overflows viewport horizontally: ${JSON.stringify(overflow)}`);
  }

  // The user profile defaults to English in the E2E fixture; App must apply it
  // after the authenticated profile is loaded instead of leaving detector text.
  await page.waitForFunction(() => document.body.innerText.includes('City'));
  if (!(await mobileNavigation.getByRole('link', { name: 'Buildings' }).isVisible())) {
    failures.push('Translated Buildings link is not reachable in mobile navigation');
  }
  if (!(await mobileNavigation.getByRole('link', { name: 'Market' }).isVisible())) {
    failures.push('Market is not reachable in mobile navigation');
  }

  // Keyboard focus and activation must work even though this browser context
  // also advertises touch support.
  const mapLink = mobileNavigation.getByRole('link', { name: 'Map' });
  await mapLink.focus();
  const focused = await mapLink.evaluate((element) => element === document.activeElement);
  if (!focused) failures.push('Mobile navigation link could not receive keyboard focus');
  await page.keyboard.press('Enter');
  await page.waitForURL(`${BASE_URL}/map`, { timeout: 15000 });

  // All API calls are delayed by 250 ms in this test. Opening another data-heavy
  // route proves the visible shell remains functional under slow responses.
  await mobileNavigation.getByRole('link', { name: 'Buildings' }).click();
  await page.waitForURL(`${BASE_URL}/buildings`, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  if (page.url().includes('/login')) {
    failures.push('Slow API responses caused an unexpected logout');
  }

  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'User Profile' }).waitFor();

  const languageSelect = page.getByLabel('Language');
  await languageSelect.selectOption('es');
  await page.getByRole('button', { name: 'Save Changes' }).click();
  await page.getByRole('heading', { name: 'Perfil de Usuario' }).waitFor();
  if (!(await mobileNavigation.getByRole('link', { name: 'Ciudad' }).isVisible())) {
    failures.push('Spanish language change did not update visible navigation');
  }

  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: 'Perfil de Usuario' }).waitFor();
  if (!(await page.getByLabel('Idioma').isVisible())) {
    failures.push('Saved Spanish language did not persist after reload');
  }

  // Restore the deterministic fixture preference while also proving reverse
  // switching works without a new login.
  await page.getByLabel('Idioma').selectOption('en');
  await page.getByRole('button', { name: 'Guardar Cambios' }).click();
  await page.getByRole('heading', { name: 'User Profile' }).waitFor();

  if (failures.length > 0) {
    throw new Error(failures.join('\n'));
  }

  console.log(`G4 UX smoke passed: 390x844 mobile navigation, keyboard focus, ${API_DELAY_MS}ms API delay and persisted es/en switching`);
} finally {
  await browser.close();
}
