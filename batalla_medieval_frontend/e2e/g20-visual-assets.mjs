import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const failures = [];
const externalRequests = new Set();
const allowedOrigins = new Set([new URL(BASE_URL).origin, new URL(API_URL).origin]);
const provisionalSymbols = ['🏰', '🛠️', '⛺', '🎓', '⚔️', '🦸', '🧭', '🗺️', '🥾', '📜', '⚖️', '🏆', '🤝', '✉️', '📚', '🪵', '🪨', '⛓️', '🪙', '🛡️', '⛪', '🕍', '🔒', '👁️', '🎒', '📌', '💎'];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
const page = await context.newPage();

page.on('request', (request) => {
  try {
    const url = new URL(request.url());
    if ((url.protocol === 'http:' || url.protocol === 'https:') && !allowedOrigins.has(url.origin)) {
      externalRequests.add(request.url());
    }
  } catch {
    // Non-URL browser requests are irrelevant to the runtime asset policy.
  }
});
page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));

async function login() {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: /Entrar|Log in|Login/i }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 20000 });
}

async function checkRoute(route) {
  await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' });
  await page.locator('main').waitFor({ state: 'visible', timeout: 15000 });

  const navigation = page.getByTestId('mobile-navigation');
  await navigation.waitFor({ state: 'visible', timeout: 15000 });

  const navSvgCount = await navigation.locator('svg').count();
  if (navSvgCount < 10) failures.push(`${route}: navigation did not render the shared SVG icon system (${navSvgCount} SVGs)`);

  const navigationText = await navigation.innerText();
  for (const symbol of provisionalSymbols) {
    if (navigationText.includes(symbol)) failures.push(`${route}: provisional navigation symbol ${symbol} is still visible`);
  }
}

try {
  await login();
  await checkRoute('/');
  await checkRoute('/buildings');
  await checkRoute('/expansion');
  await checkRoute('/academy');
  await checkRoute('/troops');
  await checkRoute('/map');
  await checkRoute('/movements');
  await checkRoute('/wiki');

  if (externalRequests.size > 0) {
    failures.push(`External runtime requests detected:\n${[...externalRequests].join('\n')}`);
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log('G20 visual assets passed: shared SVG navigation rendered, accepted routes loaded, and no external runtime visual dependencies were requested');
} finally {
  await browser.close();
}

await import('./g22-media-performance.mjs');
