import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const failures = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  reducedMotion: 'reduce',
});
const page = await context.newPage();
page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));

async function waitForRouteReady() {
  const fallback = page.getByTestId('route-loading');
  if (await fallback.count()) {
    await fallback.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  }
}

async function expectSpanishDocument(stage) {
  const lang = await page.locator('html').getAttribute('lang');
  if (lang !== 'es') failures.push(`${stage}: html lang expected es, got ${lang}`);

  const body = await page.locator('body').innerText();
  const retiredEnglish = [
    'User Profile',
    'Save Changes',
    'Receive email notifications',
    'New password (leave blank',
    'Skip to main content',
    'This screen could not be loaded',
    'Music on',
    'Music off',
    'Sound effects on',
    'Sound effects off',
  ];
  for (const marker of retiredEnglish) {
    if (body.includes(marker)) failures.push(`${stage}: retired English UI marker remained: ${marker}`);
  }
}

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    // Historical browser preference from the retired detector must not be able
    // to reactivate the incomplete English locale in v1.0.
    localStorage.setItem('i18nextLng', 'en');
  });
  await page.reload({ waitUntil: 'domcontentloaded' });

  await expectSpanishDocument('login-hard-reload');
  if (!(await page.getByRole('button', { name: 'Entrar' }).count())) {
    failures.push('login-hard-reload: Spanish Entrar action was not rendered');
  }
  if (await page.getByText('English', { exact: true }).count()) {
    failures.push('login-hard-reload: English language option is still exposed');
  }

  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForRouteReady();
  await page.locator('main#main-content').waitFor({ state: 'visible', timeout: 10000 });
  await expectSpanishDocument('authenticated-home');

  await page.goto(`${BASE_URL}/profile`, { waitUntil: 'domcontentloaded' });
  await waitForRouteReady();
  await page.getByTestId('runtime-language').waitFor({ state: 'visible', timeout: 10000 });
  const runtimeLanguage = (await page.getByTestId('runtime-language').innerText()).trim();
  if (!runtimeLanguage.includes('Español')) {
    failures.push(`profile: runtime language notice is not Spanish-only: ${runtimeLanguage}`);
  }
  if (await page.locator('#profile-language, select[name="language"]').count()) {
    failures.push('profile: retired runtime language selector is still exposed');
  }
  if (await page.getByText('English', { exact: true }).count()) {
    failures.push('profile: English option remains visible');
  }
  await expectSpanishDocument('profile');

  // Repeat the stale preference after authentication. The user profile may
  // still contain a historical language value in persisted backend data; the
  // client runtime must remain pinned to Spanish regardless.
  await page.evaluate(() => localStorage.setItem('i18nextLng', 'en'));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForRouteReady();
  await page.getByTestId('runtime-language').waitFor({ state: 'visible', timeout: 10000 });
  await expectSpanishDocument('profile-stale-preference-reload');

  await page.goto(`${BASE_URL}/messages`, { waitUntil: 'domcontentloaded' });
  await waitForRouteReady();
  await page.getByRole('heading', { name: 'Mensajería' }).waitFor({ state: 'visible', timeout: 10000 });
  await expectSpanishDocument('messages');

  if (failures.length) throw new Error(failures.join('\n'));
  console.log('G23 BM-0083 passed: Spanish-only runtime survives stale locale preferences, profile exposes no English selector, and critical routes remain Spanish');
} finally {
  await browser.close();
}
