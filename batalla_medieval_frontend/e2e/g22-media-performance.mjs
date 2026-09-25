import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const failures = [];
const scriptRequests = new Set();
const binaryAudioRequests = new Set();

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  reducedMotion: 'reduce',
});
const page = await context.newPage();

page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
page.on('request', (request) => {
  const url = request.url();
  if (request.resourceType() === 'script' && /\.js(?:\?|$)/.test(url)) scriptRequests.add(url);
  if (/\.(?:mp3|wav|ogg|m4a|aac)(?:\?|$)/i.test(url)) binaryAudioRequests.add(url);
});

async function waitForRouteReady() {
  const fallback = page.getByTestId('route-loading');
  if (await fallback.count()) await fallback.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
}

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(350);

  if (await page.getByTestId('intro-animation').count()) failures.push('reduced-motion: intro animation remained mounted');
  if (await page.getByTestId('loading-screen').count()) failures.push('reduced-motion: fake loading animation remained mounted');

  const reducedDurations = await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'animate-fade-in transition duration-700';
    document.body.appendChild(probe);
    const style = getComputedStyle(probe);
    const parseDuration = (value) => value.split(',').reduce((max, item) => {
      const text = item.trim();
      const amount = Number.parseFloat(text) || 0;
      return Math.max(max, text.endsWith('ms') ? amount : amount * 1000);
    }, 0);
    const result = {
      animationMs: parseDuration(style.animationDuration),
      transitionMs: parseDuration(style.transitionDuration),
    };
    probe.remove();
    return result;
  });
  if (reducedDurations.animationMs > 1 || reducedDurations.transitionMs > 1) {
    failures.push(`reduced-motion: animation/transition durations remain ${JSON.stringify(reducedDurations)}`);
  }

  await waitForRouteReady();
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: /Entrar|Log in|Login/i }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForRouteReady();
  await page.locator('main#main-content').waitFor({ state: 'visible', timeout: 10000 });

  const soundControls = page.locator('div[aria-label="Controles de sonido"], div[aria-label="Sound controls"]').first();
  await soundControls.waitFor({ state: 'visible', timeout: 10000 });
  const musicButton = soundControls.locator('button').first();
  const musicBefore = await musicButton.getAttribute('aria-pressed');
  await musicButton.click();
  const musicAfter = await musicButton.getAttribute('aria-pressed');
  if (musicBefore === musicAfter) failures.push('audio: music toggle did not change aria-pressed state');

  const scriptsBeforeMap = new Set(scriptRequests);
  const mapLink = page.locator('a[href="/map"]:visible').first();
  await mapLink.click();
  await page.waitForURL((url) => url.pathname === '/map', { timeout: 10000 });
  await waitForRouteReady();
  await page.getByTestId('map-grid-panel').waitFor({ state: 'visible', timeout: 10000 });

  const lazyScripts = [...scriptRequests].filter((url) => !scriptsBeforeMap.has(url));
  if (lazyScripts.length === 0) failures.push('lazy-loading: navigating to /map did not request a deferred JavaScript chunk');
  if (binaryAudioRequests.size > 0) {
    failures.push(`audio: binary audio requests detected:\n${[...binaryAudioRequests].join('\n')}`);
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log(`G22 BM-0082 media/performance passed: reduced motion honored, audio controls work without binary media, and /map loaded ${lazyScripts.length} deferred JS chunk(s)`);
} finally {
  await browser.close();
}
