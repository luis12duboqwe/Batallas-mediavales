import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USER = { username: 'g2_browser', password: 'G2-Browser-Test-2026!' };
const failures = [];
const audioRequests = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  hasTouch: true,
  reducedMotion: 'reduce',
});

await context.addInitScript(() => {
  window.__bmOscillatorCount = 0;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (AudioContextCtor) {
    const originalCreateOscillator = AudioContextCtor.prototype.createOscillator;
    AudioContextCtor.prototype.createOscillator = function patchedCreateOscillator(...args) {
      window.__bmOscillatorCount += 1;
      return originalCreateOscillator.apply(this, args);
    };
  }
});

const page = await context.newPage();
page.on('request', (request) => {
  if (/\.(mp3|wav|ogg|m4a|aac)(\?|$)/i.test(request.url())) audioRequests.push(request.url());
});
page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));

async function waitForRouteReady() {
  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 600 }).catch(() => {});
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 });
}

await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(150);
if (!await page.evaluate(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)) failures.push('prefers-reduced-motion was not applied');
if (await page.getByTestId('intro-animation').count()) failures.push('intro animation rendered despite reduced motion');
if (await page.evaluate(() => window.__bmOscillatorCount) !== 0) failures.push('audio synthesis started before user interaction');

const inputs = page.locator('form input');
await inputs.nth(0).fill(USER.username);
await inputs.nth(1).fill(USER.password);
await page.locator('form button[type="submit"]').click();
await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
await waitForRouteReady();
await page.waitForTimeout(250);
if (await page.evaluate(() => window.__bmOscillatorCount) === 0) failures.push('procedural music did not start after user gesture');

const settingsDetails = page.getByTestId('sound-settings');
await settingsDetails.locator('summary').click();
const musicVolume = page.getByTestId('music-volume');
const sfxVolume = page.getByTestId('sfx-volume');
await musicVolume.fill('0.25');
await sfxVolume.fill('0.40');
await page.getByTestId('sound-sfx-toggle').click();

const persisted = await page.evaluate(() => JSON.parse(localStorage.getItem('bm_sound_settings') || '{}'));
if (Number(persisted.musicVolume) !== 0.25) failures.push(`music volume did not persist at 0.25: ${persisted.musicVolume}`);
if (Number(persisted.sfxVolume) !== 0.4) failures.push(`SFX volume did not persist at 0.40: ${persisted.sfxVolume}`);
if (persisted.sfxEnabled !== false) failures.push('SFX disabled state did not persist');

await page.reload({ waitUntil: 'domcontentloaded' });
await waitForRouteReady();
await settingsDetails.locator('summary').click();
if (Number(await musicVolume.inputValue()) !== 0.25) failures.push('music volume was not restored after reload');
if (Number(await sfxVolume.inputValue()) !== 0.4) failures.push('SFX volume was not restored after reload');
if (await page.getByTestId('sound-sfx-toggle').getAttribute('aria-pressed') !== 'false') failures.push('SFX mute state was not restored after reload');

await page.waitForTimeout(200);
await page.getByTestId('sound-music-toggle').click();
await page.waitForTimeout(120);
const oscillatorsAfterMute = await page.evaluate(() => window.__bmOscillatorCount);
await page.waitForTimeout(1900);
const oscillatorsAfterWait = await page.evaluate(() => window.__bmOscillatorCount);
if (oscillatorsAfterWait !== oscillatorsAfterMute) failures.push('music kept scheduling tones after being disabled');

const fadeAnimation = await page.locator('.animate-fade-in').first().evaluate((element) => getComputedStyle(element).animationDuration).catch(() => '0s');
if (!['0s', '0.001ms'].includes(fadeAnimation)) failures.push(`reduced-motion fade animation still active: ${fadeAnimation}`);
if (audioRequests.length) failures.push(`binary audio requests detected: ${audioRequests.join(', ')}`);

await context.close();
await browser.close();

if (failures.length) {
  console.error('G22 sound/motion failed:\n' + failures.join('\n'));
  process.exit(1);
}
console.log('G22 sound/motion passed');
