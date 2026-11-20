import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from '@playwright/test';

// Run against the seeded G2/G21 game fixture (same login as g21-accessibility.mjs).
// Optional MAP_E2E_SCREENSHOT_DIR writes viewport evidence outside the repository.
const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const CREDENTIALS = { username: 'g2_browser', password: 'G2-Browser-Test-2026!' };

async function waitForExperienceReady(page) {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 });
  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 1200 }).catch(() => {});
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 });
}

async function login(page) {
  await page.goto(BASE_URL + '/login', { waitUntil: 'domcontentloaded' });
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 });
  const loading = page.getByTestId('loading-screen');
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 });
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(CREDENTIALS.username);
  await inputs.nth(1).fill(CREDENTIALS.password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(BASE_URL + '/', { timeout: 15000 });
  await waitForExperienceReady(page);
}

async function openMap(page) {
  const navigation = page.locator('a[href="/map"]:visible').first();
  await navigation.waitFor({ state: 'visible', timeout: 10000 });
  await navigation.click();
  await page.waitForURL((url) => url.pathname === '/map', { timeout: 10000 });
  await waitForExperienceReady(page);
  await page.locator('[data-testid^="map-tile-"]').first().waitFor({ state: 'visible', timeout: 15000 });
  await waitForMap(page);
}

async function waitForMap(page) {
  await page.waitForFunction(
    () => document.querySelector('[data-testid="map-grid-panel"]')?.getAttribute('aria-busy') === 'false',
    null,
    { timeout: 15000 },
  );
}

async function centerOf(page) {
  const text = await page.getByTestId('map-center').textContent();
  const match = text.match(/Centro:\s*\((\d+),\s*(\d+)\)/);
  assert.ok(match, 'Map center is shown to the user');
  return { x: Number(match[1]), y: Number(match[2]) };
}

async function jump(page, x, y) {
  await page.getByRole('spinbutton', { name: 'Coordenada X' }).fill(String(x));
  await page.getByRole('spinbutton', { name: 'Coordenada Y' }).fill(String(y));
  await page.getByRole('button', { name: 'Ir', exact: true }).click();
}

async function snapshotOrder(page) {
  return page.locator('[aria-label="Cuadrícula del mapa"] > div').evaluateAll((rows) => rows.map(
    (row) => Array.from(row.querySelectorAll('button[data-map-coordinate]'), (button) => {
      const [x, y] = button.dataset.mapCoordinate.split(',').map(Number);
      return { x, y };
    }),
  ));
}

function verifyOrder(rows) {
  assert.ok(rows.length > 0 && rows[0].length > 1, 'Seeded map has multiple tiles');
  let lastY = Infinity;
  for (const row of rows) {
    assert.ok(row.length > 0, 'Every rendered row has tiles');
    const y = row[0].y;
    assert.ok(y < lastY, 'Rows are ordered north-to-south (descending Y)');
    lastY = y;
    for (let index = 1; index < row.length; index += 1) {
      assert.equal(row[index].y, y, 'Rows do not mix Y coordinates');
      assert.ok(row[index].x > row[index - 1].x, 'Columns are ordered west-to-east');
    }
  }
}

async function runJourney(browser, label, viewport, touch) {
  const context = await browser.newContext({ viewport, hasTouch: touch });
  const page = await context.newPage();
  const pageErrors = [];
  let mapRequests = 0;
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.endsWith('/map/tiles')) mapRequests += 1;
  });

  try {
    await login(page);
    await openMap(page);
    const panel = page.getByTestId('map-grid-panel');
    const startingCenter = await centerOf(page);
    const initialOrder = await snapshotOrder(page);
    verifyOrder(initialOrder);
    // G12/BM-0067 locates barbarian/oasis tiles by the legacy title format.
    // Preserve it while using richer aria-label text for screen readers.
    const centerTile = page.getByTestId('map-tile-' + startingCenter.x + '-' + startingCenter.y);
    assert.match(
      await centerTile.getAttribute('title'),
      new RegExp('^\\(' + startingCenter.x + ', ' + startingCenter.y + '\\) '),
      'Legacy G12 coordinate title remains compatible',
    );
    assert.match(await centerTile.getAttribute('aria-label'), /Casilla /, 'Accessible tile label is independent of title');

    const sizing = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
    }));
    assert.ok(sizing.documentWidth <= sizing.viewportWidth + 1, label + ': no document-level horizontal overflow');
    assert.equal(await page.locator('[aria-label="Cuadrícula del mapa"] button[tabindex="0"]').count(), 1, 'One tab stop inside the tile group');
    const arrows = page.locator('[data-testid="map-grid-content"] > button[aria-label^="Mover mapa"]');
    assert.equal(await arrows.count(), 4, 'Four accessible directional controls');
    for (const arrow of await arrows.all()) {
      const bounds = await arrow.boundingBox();
      assert.ok(bounds && bounds.width >= 40 && bounds.height >= 40, 'Pan controls have touch-sized targets');
    }

    if (touch) {
      const scroll = await panel.evaluate((element) => ({ width: element.scrollWidth, viewport: element.clientWidth }));
      assert.ok(scroll.width > scroll.viewport, 'Mobile map uses internal horizontal scrolling');
      const first = page.locator('[data-testid^="map-tile-"]').first();
      const last = page.locator('[data-testid^="map-tile-"]').last();
      await panel.evaluate((element) => { element.scrollLeft = 0; });
      const [begin, firstBox] = await Promise.all([panel.boundingBox(), first.boundingBox()]);
      assert.ok(firstBox.x >= begin.x - 1, 'Western columns are reachable');
      await panel.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
      const [end, lastBox] = await Promise.all([panel.boundingBox(), last.boundingBox()]);
      assert.ok(lastBox.x + lastBox.width <= end.x + end.width + 1, 'Eastern columns are reachable');
      await panel.evaluate((element) => { element.scrollLeft = (element.scrollWidth - element.clientWidth) / 2; });
    }

    if (process.env.MAP_E2E_SCREENSHOT_DIR) {
      await mkdir(process.env.MAP_E2E_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({
        path: path.join(process.env.MAP_E2E_SCREENSHOT_DIR, 'medievol-map-' + label + '.png'),
        fullPage: true,
      });
    }

    // Roving focus, native activation, and stable React keys/DOM order.
    const firstButton = page.locator('[data-testid^="map-tile-"]').first();
    const secondCoordinate = initialOrder[0][1];
    await firstButton.focus();
    await page.keyboard.press('ArrowRight');
    const focusedCoordinate = await page.evaluate(() => document.activeElement?.dataset.mapCoordinate);
    assert.equal(focusedCoordinate, secondCoordinate.x + ',' + secondCoordinate.y, 'ArrowRight moves focus to east neighbor');
    await page.keyboard.press('Enter');
    const selectedButton = page.getByTestId('map-tile-' + secondCoordinate.x + '-' + secondCoordinate.y);
    assert.equal(await selectedButton.getAttribute('aria-pressed'), 'true', 'Keyboard selects focused tile');
    assert.equal(await page.locator('[aria-label="Cuadrícula del mapa"] button[tabindex="0"]').count(), 1, 'Roving focus retains one tab stop');
    assert.deepEqual(await snapshotOrder(page), initialOrder, 'Selection does not reorder or recreate tile positions');

    await page.keyboard.press('End');
    assert.equal(
      await page.evaluate(() => document.activeElement?.dataset.mapCoordinate),
      initialOrder[0].at(-1).x + ',' + initialOrder[0].at(-1).y,
      'End moves to last tile on same row',
    );
    await page.keyboard.press('Control+Home');
    assert.equal(
      await page.evaluate(() => document.activeElement?.dataset.mapCoordinate),
      initialOrder[0][0].x + ',' + initialOrder[0][0].y,
      'Control+Home moves to first tile of grid',
    );

    // Bad coordinates must never send an API request or mutate the center.
    for (const invalidX of ['', '1.5', '-1', '9007199254740992']) {
      const before = mapRequests;
      await jump(page, invalidX, '0');
      assert.equal(await page.getByRole('alert').filter({ hasText: 'coordenadas X e Y' }).count(), 1, 'Invalid jump reports a readable error');
      assert.equal(mapRequests, before, 'Invalid coordinates do not generate a map request');
      assert.deepEqual(await centerOf(page), startingCenter, 'Invalid coordinates do not move the map');
    }
    await jump(page, startingCenter.x, startingCenter.y);
    assert.equal(await page.getByRole('alert').filter({ hasText: 'coordenadas X e Y' }).count(), 0, 'Valid jump clears form error');

    // Form editing and a nearby pan retain the selected tile while it is in range.
    const cityTile = page.getByTestId('map-tile-' + startingCenter.x + '-' + startingCenter.y);
    await cityTile.click();
    await page.getByRole('spinbutton', { name: 'Coordenada X' }).fill(String(startingCenter.x));
    assert.equal(await cityTile.getAttribute('aria-pressed'), 'true', 'Editing the jump form does not discard selection');
    const nextX = startingCenter.x + 5;
    const response = page.waitForResponse((res) =>
      new URL(res.url()).pathname.endsWith('/map/tiles')
      && new URL(res.url()).searchParams.get('x') === String(nextX), { timeout: 15000 });
    await page.getByRole('button', { name: 'Mover mapa hacia la derecha' }).click();
    await response;
    await waitForMap(page);
    assert.deepEqual(await centerOf(page), { x: nextX, y: startingCenter.y }, 'Pan moves center exactly five tiles');
    assert.equal(await page.getByTestId('map-tile-' + startingCenter.x + '-' + startingCenter.y).getAttribute('aria-pressed'), 'true', 'Overlapping tile stays selected after pan');
    verifyOrder(await snapshotOrder(page));

    // The coordinate system never pans outside the nonnegative map domain.
    const originResponse = page.waitForResponse((res) =>
      new URL(res.url()).pathname.endsWith('/map/tiles')
      && new URL(res.url()).searchParams.get('x') === '0'
      && new URL(res.url()).searchParams.get('y') === '0', { timeout: 15000 });
    await jump(page, 0, 0);
    await originResponse;
    await waitForMap(page);
    const requestsBeforeBoundary = mapRequests;
    await page.getByRole('button', { name: 'Mover mapa hacia la izquierda' }).click();
    await page.getByRole('button', { name: 'Mover mapa hacia abajo' }).click();
    assert.deepEqual(await centerOf(page), { x: 0, y: 0 }, 'Panning is clamped at zero');
    assert.equal(mapRequests, requestsBeforeBoundary, 'Clamped pan does not refetch unchanged center');

    // A transient failed request must show a retry affordance and recover.
    let failOnce = true;
    await page.route((url) => url.pathname.endsWith('/map/tiles'), async (route) => {
      if (failOnce) {
        failOnce = false;
        await route.abort('failed');
      } else {
        await route.continue();
      }
    });
    await jump(page, 1, 0);
    const error = page.getByTestId('map-load-error');
    await error.waitFor({ state: 'visible', timeout: 15000 });
    assert.equal(await page.getByRole('button', { name: 'Reintentar mapa' }).count(), 1);
    await page.getByRole('button', { name: 'Reintentar mapa' }).click();
    await page.locator('[data-testid^="map-tile-"]').first().waitFor({ state: 'visible', timeout: 15000 });
    await waitForMap(page);
    assert.equal(await error.count(), 0, 'Retry removes error and restores tiles');
    assert.deepEqual(pageErrors, [], 'No uncaught JavaScript errors on map journey');

    console.log(label + ': map layout, keyboard, selection, sorting, validation, boundaries and recovery passed');
  } finally {
    await context.close().catch(() => {});
  }
}

const browser = await chromium.launch({ headless: true });
try {
  await runJourney(browser, 'desktop', { width: 1440, height: 900 }, false);
  await runJourney(browser, 'mobile', { width: 390, height: 844 }, true);
} finally {
  await browser.close().catch(() => {});
}
