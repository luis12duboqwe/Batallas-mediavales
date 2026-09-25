import { chromium } from '@playwright/test';
import { hasBinaryAudioExtension } from '../scripts/media-policy.mjs';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const USERNAME = 'g2_browser';
const PASSWORD = 'G2-Browser-Test-2026!';
const failures = [];
const scriptRequests = new Set();
const binaryAudioRequests = new Set();
let failNextScript = false;
let blockedDynamicScript = null;

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  reducedMotion: 'reduce',
});

await context.addInitScript(() => {
  window.__bmAudioContextCount = 0;
  window.__bmOscillatorCount = 0;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) return;
  const OriginalAudioContext = AudioContextCtor;
  class InstrumentedAudioContext extends OriginalAudioContext {
    constructor(...args) {
      super(...args);
      window.__bmAudioContextCount += 1;
    }
  }
  Object.setPrototypeOf(InstrumentedAudioContext, OriginalAudioContext);
  InstrumentedAudioContext.prototype.createOscillator = function patchedCreateOscillator(...args) {
    window.__bmOscillatorCount += 1;
    return OriginalAudioContext.prototype.createOscillator.apply(this, args);
  };
  window.AudioContext = InstrumentedAudioContext;
  if (window.webkitAudioContext) window.webkitAudioContext = InstrumentedAudioContext;
});

const page = await context.newPage();
page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
page.on('request', (request) => {
  const url = request.url();
  if (request.resourceType() === 'script' && /\.js(?:\?|$)/.test(url)) scriptRequests.add(url);
  if (hasBinaryAudioExtension(url)) binaryAudioRequests.add(url);
});
await page.route('**/*.js', async (route) => {
  if (failNextScript) {
    failNextScript = false;
    blockedDynamicScript = route.request().url();
    await route.abort('failed');
    return;
  }
  await route.continue();
});

async function waitForRouteReady() {
  const fallback = page.getByTestId('route-loading');
  if (await fallback.count()) await fallback.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
}

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(200);

  if (await page.getByTestId('intro-animation').count()) failures.push('reduced-motion: intro animation remained mounted');
  if (await page.getByTestId('loading-screen').count()) failures.push('reduced-motion: fake loading animation remained mounted');
  if (await page.evaluate(() => window.__bmAudioContextCount) !== 0) failures.push('audio: AudioContext was created before user interaction');

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

  await page.evaluate(() => {
    localStorage.setItem('bm_sound_settings', JSON.stringify({
      musicEnabled: 'corrupt',
      sfxEnabled: null,
      musicVolume: 'not-a-number',
      sfxVolume: 9,
    }));
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(150);
  if (await page.evaluate(() => window.__bmAudioContextCount) !== 0) failures.push('audio: corrupted settings created audio before a gesture');

  const inputs = page.locator('form input');
  await inputs.nth(0).fill(USERNAME);
  await inputs.nth(1).fill(PASSWORD);
  await page.getByRole('button', { name: /Entrar|Log in|Login/i }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForRouteReady();
  await page.locator('main#main-content').waitFor({ state: 'visible', timeout: 10000 });

  const settingsDetails = page.getByTestId('sound-settings');
  await settingsDetails.locator('summary').click();
  const musicVolume = page.getByTestId('music-volume');
  const sfxVolume = page.getByTestId('sfx-volume');
  const musicToggle = page.getByTestId('sound-music-toggle');
  const sfxToggle = page.getByTestId('sound-sfx-toggle');

  if (Number(await musicVolume.inputValue()) !== 0.45) failures.push('audio: invalid music volume was not normalized to 0.45');
  if (Number(await sfxVolume.inputValue()) !== 1) failures.push('audio: out-of-range SFX volume was not clamped to 1');
  if (await musicToggle.getAttribute('aria-pressed') !== 'false') failures.push('audio: invalid music toggle did not fall back to opt-in false');
  if (await sfxToggle.getAttribute('aria-pressed') !== 'true') failures.push('audio: invalid SFX toggle did not fall back to true');

  const oscillatorsBeforeMusic = await page.evaluate(() => window.__bmOscillatorCount);
  await musicToggle.click();
  await page.waitForTimeout(80);
  const oscillatorsAfterMusic = await page.evaluate(() => window.__bmOscillatorCount);
  if (oscillatorsAfterMusic <= oscillatorsBeforeMusic) failures.push('audio: music opt-in did not start procedural synthesis after a user gesture');

  await musicVolume.fill('0.25');
  await sfxVolume.fill('0.4');
  await sfxToggle.click();
  const persisted = await page.evaluate(() => JSON.parse(localStorage.getItem('bm_sound_settings') || '{}'));
  if (Number(persisted.musicVolume) !== 0.25) failures.push(`audio: music volume did not persist at 0.25 (${persisted.musicVolume})`);
  if (Number(persisted.sfxVolume) !== 0.4) failures.push(`audio: SFX volume did not persist at 0.4 (${persisted.sfxVolume})`);
  if (persisted.sfxEnabled !== false) failures.push('audio: SFX disabled state did not persist');

  const scriptsBeforeMap = new Set(scriptRequests);
  failNextScript = true;
  const mapLink = page.locator('a[href="/map"]:visible').first();
  await mapLink.click();
  await page.waitForURL((url) => url.pathname === '/map', { timeout: 10000 });
  await page.getByTestId('map-grid-panel').waitFor({ state: 'visible', timeout: 15000 });
  await waitForRouteReady();

  if (!blockedDynamicScript) failures.push('lazy-loading: recovery probe did not intercept a deferred JavaScript request');
  if (await page.getByTestId('route-load-error').count()) failures.push('lazy-loading: route remained in error state after one-time chunk recovery reload');
  const lazyScripts = [...scriptRequests].filter((url) => !scriptsBeforeMap.has(url));
  if (lazyScripts.length === 0) failures.push('lazy-loading: navigating to /map did not request a deferred JavaScript chunk');

  const reloadedMusicToggle = page.getByTestId('sound-music-toggle');
  if (await reloadedMusicToggle.getAttribute('aria-pressed') !== 'true') failures.push('audio: music opt-in was not restored after route recovery reload');
  await reloadedMusicToggle.click();
  const oscillatorCountAfterMute = await page.evaluate(() => window.__bmOscillatorCount);
  await page.waitForTimeout(1900);
  const oscillatorCountAfterWait = await page.evaluate(() => window.__bmOscillatorCount);
  if (oscillatorCountAfterWait !== oscillatorCountAfterMute) failures.push('audio: music kept scheduling tones after being disabled');

  if (binaryAudioRequests.size > 0) {
    failures.push(`audio: binary audio requests detected:\n${[...binaryAudioRequests].join('\n')}`);
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log(`G22 BM-0082 passed: reduced motion, normalized/persisted audio controls, one-time lazy chunk recovery, deferred JS and zero binary audio (${lazyScripts.length} new chunk(s))`);
} finally {
  await browser.close();
}
