import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

// Repeatable browser baseline: emulated mid-range mobile viewport and 3x CPU slowdown.
// These are CI guardrails, not certification on a physical target device.
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const MAX_P95_SELECTION_MS = 600;
const MAX_JS_TRANSFER_BYTES = 1500 * 1024;
const MAX_HEAP_GROWTH_BYTES = 12 * 1024 * 1024;

const tiles = [];
for (let y = -7; y <= 7; y += 1) {
  for (let x = -7; x <= 7; x += 1) tiles.push({ x, y, type: 'plain' });
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  reducedMotion: 'reduce',
  deviceScaleFactor: 2,
});
const page = await context.newPage();
const cdp = await context.newCDPSession(page);
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(error.message));

const readHeap = async () => {
  await cdp.send('HeapProfiler.collectGarbage');
  const { metrics } = await cdp.send('Performance.getMetrics');
  const sample = metrics.find((metric) => metric.name === 'JSHeapUsedSize');
  assert.ok(sample, 'Chromium must expose JS heap measurements');
  return sample.value;
};

try {
  await cdp.send('Performance.enable');
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 3 });
  await page.route('**/map/tiles**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ tiles }),
  }));

  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  await page.locator('form input').nth(0).fill('g2_browser');
  await page.locator('form input').nth(1).fill('G2-Browser-Test-2026!');
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 20000 });
  await page.locator('a[href="/map"]:visible').first().click();
  await page.waitForURL((url) => url.pathname === '/map', { timeout: 15000 });
  await page.getByTestId('map-tile--7-7').waitFor({ state: 'visible', timeout: 15000 });
  await page.getByTestId('map-grid-panel').waitFor({ state: 'visible' });

  const mapTiles = page.locator('button[data-testid^="map-tile-"]');
  assert.equal(await mapTiles.count(), 225, 'Map must render 225 tiles for radius 7');
  assert.equal(await mapTiles.first().getAttribute('data-testid'), 'map-tile--7-7', 'Top-left tile ordering');
  assert.equal(await mapTiles.last().getAttribute('data-testid'), 'map-tile-7--7', 'Bottom-right tile ordering');

  // Warm up the selection path before measuring allocations/interaction latency.
  await page.getByTestId('map-tile-0-0').click();
  await page.getByTestId('map-details-panel').getByText('(0, 0)').waitFor();
  const heapBefore = await readHeap();

  const durations = await page.evaluate(async () => {
    const targets = [...document.querySelectorAll('button[data-testid^="map-tile-"]')];
    const panel = document.querySelector('[data-testid="map-grid-panel"]');
    if (!panel) throw new Error('Map scroll container is missing');
    const measurements = [];
    for (let i = 0; i < 24; i += 1) {
      const target = targets[(i * 37 + 11) % targets.length];
      // Scrolling is setup, not part of selection latency. Ensure the tile can
      // actually paint inside both the scroll panel and the mobile viewport.
      target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
      await new Promise((resolve) => requestAnimationFrame(resolve));
      const bounds = target.getBoundingClientRect();
      const panelBounds = panel.getBoundingClientRect();
      const visible = bounds.left >= Math.max(0, panelBounds.left)
        && bounds.right <= Math.min(window.innerWidth, panelBounds.right)
        && bounds.top >= Math.max(0, panelBounds.top)
        && bounds.bottom <= Math.min(window.innerHeight, panelBounds.bottom);
      if (!visible) throw new Error('Map tile was not visible before the measured click');
      const startedAt = performance.now();
      target.click();
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (target.getAttribute('aria-pressed') !== 'true' || !target.classList.contains('ring-2')) {
        throw new Error('Visible map selection did not render its highlighted state');
      }
      measurements.push(performance.now() - startedAt);
    }
    return measurements;
  });

  const heapAfter = await readHeap();
  const sortedDurations = [...durations].sort((a, b) => a - b);
  const p95 = sortedDurations[Math.ceil(sortedDurations.length * 0.95) - 1];
  const heapGrowth = Math.max(0, heapAfter - heapBefore);
  const jsBytes = await page.evaluate(() => performance.getEntriesByType('resource')
    .filter((resource) => /\.js(?:\?|$)/.test(resource.name))
    .reduce((sum, resource) => sum + resource.transferSize, 0));

  assert.ok(p95 <= MAX_P95_SELECTION_MS, 'Map selection p95 ' + p95.toFixed(1) + 'ms exceeds ' + MAX_P95_SELECTION_MS + 'ms');
  assert.ok(jsBytes <= MAX_JS_TRANSFER_BYTES, 'JS transfer ' + jsBytes + 'B exceeds ' + MAX_JS_TRANSFER_BYTES + 'B');
  assert.ok(heapGrowth <= MAX_HEAP_GROWTH_BYTES, 'Map selection heap growth ' + heapGrowth + 'B exceeds ' + MAX_HEAP_GROWTH_BYTES + 'B');
  assert.deepEqual(pageErrors, [], 'Map journey must not throw errors');
  console.log('G26 BM-0085 passed: 225 tiles, mobile viewport, 3x CPU; p95 selection=' +
    p95.toFixed(1) + 'ms; JS transfer=' + (jsBytes / 1024).toFixed(1) +
    'KiB; post-GC selection heap growth=' + (heapGrowth / 1024 / 1024).toFixed(2) + 'MiB');
} finally {
  await browser.close();
}
