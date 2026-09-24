import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const failures = [];

const recordErrors = (page, label) => {
  page.on('pageerror', (error) => failures.push(`${label} pageerror: ${error.message}`));
  page.on('response', (response) => {
    if (response.status() >= 500) failures.push(`${label} HTTP ${response.status()}: ${response.url()}`);
  });
};

const installAudioContextCounter = async (context) => {
  await context.addInitScript(() => {
    window.__bmAudioContextCount = 0;
    for (const name of ['AudioContext', 'webkitAudioContext']) {
      const Original = window[name];
      if (typeof Original !== 'function') continue;
      const Wrapped = new Proxy(Original, {
        construct(target, args, newTarget) {
          window.__bmAudioContextCount += 1;
          return Reflect.construct(target, args, newTarget);
        },
      });
      Object.defineProperty(window, name, { configurable: true, writable: true, value: Wrapped });
    }
  });
};

async function waitForExperienceReady(page) {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 });
  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 500 }).catch(() => {});
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 });
}

const browser = await chromium.launch({ headless: true });
try {
  const reducedContext = await browser.newContext({ reducedMotion: 'reduce' });
  await installAudioContextCounter(reducedContext);
  const reducedPage = await reducedContext.newPage();
  recordErrors(reducedPage, 'reduced-motion');
  const reducedStarted = Date.now();
  await reducedPage.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await reducedPage.locator('form').waitFor({ state: 'visible', timeout: 1500 });
  await reducedPage.waitForFunction(() => (
    !document.querySelector('[data-testid="intro-animation"]')
    && !document.querySelector('[data-testid="loading-screen"]')
  ), null, { timeout: 1500 });
  const reducedElapsed = Date.now() - reducedStarted;
  if (reducedElapsed > 1200) failures.push(`Reduced-motion shell took ${reducedElapsed}ms; expected <=1200ms`);

  const motionStyles = await reducedPage.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'animate-fade-in transition-all duration-700';
    document.body.appendChild(probe);
    const style = getComputedStyle(probe);
    const result = { animationDuration: style.animationDuration, transitionDuration: style.transitionDuration };
    probe.remove();
    return result;
  });
  const seconds = (value) => value.split(',').map((part) => parseFloat(part) || 0);
  if (seconds(motionStyles.animationDuration).some((value) => value > 0.01)) {
    failures.push(`Reduced-motion animation duration not suppressed: ${motionStyles.animationDuration}`);
  }
  if (seconds(motionStyles.transitionDuration).some((value) => value > 0.01)) {
    failures.push(`Reduced-motion transition duration not suppressed: ${motionStyles.transitionDuration}`);
  }
  const reducedAudioContexts = await reducedPage.evaluate(() => window.__bmAudioContextCount);
  if (reducedAudioContexts !== 0) failures.push(`AudioContext created without user gesture: ${reducedAudioContexts}`);
  await reducedContext.close();

  // Changing the OS preference while the canvas intro is already running must
  // cancel the animation and finish the shell instead of leaving it stuck.
  const liveContext = await browser.newContext({ reducedMotion: 'no-preference' });
  await installAudioContextCounter(liveContext);
  const livePage = await liveContext.newPage();
  recordErrors(livePage, 'live-reduced-motion');
  await livePage.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await livePage.getByTestId('intro-animation').waitFor({ state: 'visible', timeout: 1000 });
  const liveStarted = Date.now();
  await livePage.emulateMedia({ reducedMotion: 'reduce' });
  await livePage.locator('form').waitFor({ state: 'visible', timeout: 1500 });
  await livePage.waitForFunction(() => (
    !document.querySelector('[data-testid="intro-animation"]')
    && !document.querySelector('[data-testid="loading-screen"]')
  ), null, { timeout: 1500 });
  const liveElapsed = Date.now() - liveStarted;
  if (liveElapsed > 1200) failures.push(`Live reduced-motion switch took ${liveElapsed}ms; expected <=1200ms`);
  const liveAudioContexts = await livePage.evaluate(() => window.__bmAudioContextCount);
  if (liveAudioContexts !== 0) failures.push(`Live motion preference switch created AudioContext without gesture: ${liveAudioContexts}`);
  await liveContext.close();

  const context = await browser.newContext({ reducedMotion: 'reduce' });
  await installAudioContextCounter(context);
  const page = await context.newPage();
  recordErrors(page, 'sound-controls');
  const binaryAudioRequests = [];
  page.on('request', (request) => {
    if (/\.(mp3|wav|ogg|m4a|aac|flac|opus)(?:\?|$)/i.test(request.url())) binaryAudioRequests.push(request.url());
  });

  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await waitForExperienceReady(page);
  const beforeGesture = await page.evaluate(() => window.__bmAudioContextCount);
  if (beforeGesture !== 0) failures.push(`AudioContext created before first interaction: ${beforeGesture}`);

  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForExperienceReady(page);
  await page.waitForFunction(() => window.__bmAudioContextCount === 1, null, { timeout: 3000 });

  const settings = page.getByTestId('sound-settings');
  await settings.locator('summary').click();
  await page.getByTestId('music-volume').fill('0.35');
  await page.getByTestId('sfx-volume').fill('0.25');
  await page.getByTestId('sfx-toggle').click();

  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem('bm_sound_settings') || '{}'));
  if (stored.musicVolume !== 0.35) failures.push(`Music volume did not persist: ${JSON.stringify(stored)}`);
  if (stored.sfxVolume !== 0.25) failures.push(`SFX volume did not persist: ${JSON.stringify(stored)}`);
  if (stored.sfxEnabled !== false) failures.push(`SFX toggle did not persist: ${JSON.stringify(stored)}`);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await waitForExperienceReady(page);
  if (await page.getByTestId('music-volume').inputValue() !== '0.35') failures.push('Music volume was not restored after reload');
  if (await page.getByTestId('sfx-volume').inputValue() !== '0.25') failures.push('SFX volume was not restored after reload');
  if (await page.getByTestId('sfx-toggle').getAttribute('aria-pressed') !== 'false') failures.push('SFX disabled state was not restored after reload');

  const mapLink = page.locator('a[href="/map"]:visible').first();
  await mapLink.click();
  await page.waitForURL((url) => url.pathname === '/map', { timeout: 10000 });
  const afterRouteChange = await page.evaluate(() => window.__bmAudioContextCount);
  if (afterRouteChange !== 1) failures.push(`Route change created extra AudioContext instances: ${afterRouteChange}`);
  if (binaryAudioRequests.length) failures.push(`Binary audio requests detected: ${binaryAudioRequests.join(', ')}`);

  await context.close();
  if (failures.length) throw new Error(failures.join('\n'));
  console.log('G22 passed: reduced motion, gesture-gated procedural audio and persistent sound controls are stable');
} finally {
  await browser.close();
}
