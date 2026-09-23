import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const failures = [];

const USERS = {
  general: { username: 'g2_browser', password: 'G2-Browser-Test-2026!' },
  report: { username: 'g9_combat', password: 'G9-Combat-Test-2026!' },
  alliance: { username: 'g14_rival', password: 'G14-Community-Test-2026!' },
};

const recordPageErrors = (page, label) => {
  page.on('pageerror', (error) => failures.push(`${label} pageerror: ${error.message}`));
  page.on('response', (response) => {
    if (response.status() >= 500) failures.push(`${label} HTTP ${response.status()}: ${response.url()}`);
  });
};

async function withIsolatedPage(browser, contextOptions, label, callback) {
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  recordPageErrors(page, label);

  try {
    await callback(page);
  } finally {
    // Each journey gets a fresh context while reusing one Chromium process.
    // A journey-time page/browser closure still rejects the awaited action;
    // teardown only avoids replacing that evidence with a secondary close error.
    await context.close().catch(() => {});
  }
}

async function waitForExperienceReady(page) {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 });
  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 1200 }).catch(() => {});
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 });
}

async function login(page, credentials) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await waitForExperienceReady(page);
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(credentials.username);
  await inputs.nth(1).fill(credentials.password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForExperienceReady(page);
}

async function openGameRoute(page, route) {
  const currentPath = new URL(page.url()).pathname;
  if (currentPath !== route) {
    const link = page.locator(`a[href="${route}"]:visible`).first();
    if (await link.count() !== 1) throw new Error(`No visible SPA navigation link for ${route}`);
    await link.click();
    await page.waitForURL((url) => url.pathname === route, { timeout: 10000 });
  }
  await waitForExperienceReady(page);
  await page.locator('main#main-content').waitFor({ state: 'visible', timeout: 10000 });
}

async function assertNoDocumentOverflow(page, route, label) {
  await openGameRoute(page, route);
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  if (dimensions.scrollWidth > dimensions.clientWidth + 1) {
    failures.push(`${label} ${route}: horizontal document overflow ${dimensions.scrollWidth}px > ${dimensions.clientWidth}px`);
  }
}

async function assertMapInternalScrollReachable(page, label) {
  const panel = page.getByTestId('map-grid-panel');
  const metrics = await panel.evaluate((element) => ({
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }));
  if (metrics.scrollWidth <= metrics.clientWidth + 1) return;

  const firstTile = page.locator('[data-testid^="map-tile-"]').first();
  const lastTile = page.locator('[data-testid^="map-tile-"]').last();

  await panel.evaluate((element) => { element.scrollLeft = 0; });
  const [panelAtStart, firstAtStart] = await Promise.all([panel.boundingBox(), firstTile.boundingBox()]);
  if (!panelAtStart || !firstAtStart || firstAtStart.x < panelAtStart.x - 1) {
    failures.push(`${label}: western map columns are clipped before the scrollable origin`);
  }

  await panel.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
  const [panelAtEnd, lastAtEnd] = await Promise.all([panel.boundingBox(), lastTile.boundingBox()]);
  if (!panelAtEnd || !lastAtEnd || lastAtEnd.x + lastAtEnd.width > panelAtEnd.x + panelAtEnd.width + 1) {
    failures.push(`${label}: eastern map columns are unreachable at the scrollable end`);
  }
}

async function assertWorldDetailsAccessible(page, label) {
  const worldButton = page.locator('[data-testid^="world-selector-"] > button').first();
  await worldButton.waitFor({ state: 'visible', timeout: 10000 });
  const semantics = await worldButton.evaluate((element) => {
    const textForIds = (attribute) => (element.getAttribute(attribute) || '')
      .split(/\s+/)
      .filter(Boolean)
      .map((id) => document.getElementById(id)?.textContent?.trim() || '')
      .join(' ');
    return {
      labelledText: textForIds('aria-labelledby'),
      describedText: textForIds('aria-describedby'),
    };
  });
  if (!/mundo/i.test(semantics.labelledText)) failures.push(`${label}: world selector action/name is not labelled`);
  for (const expected of ['Estado:', 'Velocidad:', 'Recursos:', 'Tamaño mapa:']) {
    if (!semantics.describedText.includes(expected)) failures.push(`${label}: world selector description lost ${expected}`);
  }
}

async function checkGeneralViewport(browser, viewport, label, mobile) {
  try {
    await withIsolatedPage(browser, { viewport, isMobile: mobile, hasTouch: mobile }, label, async (page) => {
      await login(page, USERS.general);
      await assertWorldDetailsAccessible(page, label);

      const main = page.locator('main#main-content');
      const skipLink = page.locator('a[href="#main-content"]');
      if (await skipLink.count() !== 1) failures.push(`${label}: skip-to-content link missing`);

      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      });
      await page.keyboard.press('Tab');
      const skipFocused = await skipLink.evaluate((element) => document.activeElement === element);
      if (!skipFocused) failures.push(`${label}: first keyboard stop is not the skip-to-content link`);
      await page.keyboard.press('Enter');
      const mainFocusedAfterSkip = await main.evaluate((element) => document.activeElement === element);
      if (!mainFocusedAfterSkip) failures.push(`${label}: skip link did not move focus to main content`);

      const navigation = mobile
        ? page.getByTestId('mobile-navigation')
        : page.locator('aside nav[aria-label]').first();
      if (await navigation.count() !== 1) failures.push(`${label}: labelled primary game navigation missing`);

      const mapLink = page.locator('a[href="/map"]:visible').first();
      await mapLink.focus();
      await page.keyboard.press('Enter');
      await page.waitForURL((url) => url.pathname === '/map', { timeout: 10000 });
      await waitForExperienceReady(page);
      const mainFocusedAfterRoute = await page.locator('main#main-content').evaluate((element) => document.activeElement === element);
      if (!mainFocusedAfterRoute) failures.push(`${label}: SPA route change did not move focus to main content`);

      const firstTile = page.locator('[data-testid^="map-tile-"]').first();
      await firstTile.waitFor({ state: 'visible', timeout: 10000 });
      const tileSemantics = await firstTile.evaluate((element) => ({
        tag: element.tagName,
        label: element.getAttribute('aria-label'),
      }));
      if (tileSemantics.tag !== 'BUTTON' || !tileSemantics.label) failures.push(`${label}: map tile is not an accessible button`);
      await firstTile.focus();
      await page.keyboard.press('Enter');
      if (await firstTile.getAttribute('aria-pressed') !== 'true') failures.push(`${label}: map tile did not activate from keyboard`);

      if (mobile) {
        await assertMapInternalScrollReachable(page, label);
        const details = page.getByTestId('map-details-panel');
        await details.scrollIntoViewIfNeeded();
        const detailsBox = await details.boundingBox();
        if (!detailsBox || detailsBox.x < -1 || detailsBox.x + detailsBox.width > viewport.width + 1) {
          failures.push(`${label}: map details panel is clipped outside the mobile viewport`);
        }
      }

      await openGameRoute(page, '/messages');
      const messageTabs = page.getByRole('tab');
      if (await messageTabs.count() !== 3) failures.push(`${label}: message tab semantics are incomplete`);
      const nonButtons = await messageTabs.evaluateAll((elements) => elements.filter((element) => element.tagName !== 'BUTTON').length);
      if (nonButtons > 0) failures.push(`${label}: message tabs are not native buttons`);

      const inboxTab = page.getByRole('tab', { name: 'Bandeja de Entrada' });
      await inboxTab.focus();
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction(() => document.getElementById('messages-tab-sent')?.getAttribute('aria-selected') === 'true');
      await page.waitForFunction(() => document.activeElement?.id === 'messages-tab-sent');
      await page.keyboard.press('Home');
      await page.waitForFunction(() => document.getElementById('messages-tab-inbox')?.getAttribute('aria-selected') === 'true');
      await page.waitForFunction(() => document.activeElement?.id === 'messages-tab-inbox');

      for (const route of ['/', '/map', '/messages', '/reports', '/alliance']) {
        await assertNoDocumentOverflow(page, route, label);
      }
    });
  } catch (error) {
    failures.push(`${label} journey-error: ${error.stack || error.message}`);
  }
}

async function checkReportKeyboard(browser) {
  try {
    await withIsolatedPage(browser, { viewport: { width: 1440, height: 900 } }, 'report', async (page) => {
      await login(page, USERS.report);
      await openGameRoute(page, '/reports');
      const toggle = page.locator('[data-testid^="report-toggle-"]').first();
      await toggle.waitFor({ state: 'visible', timeout: 10000 });
      if (await toggle.evaluate((element) => element.tagName) !== 'BUTTON') failures.push('report: expandable report header is not a native button');
      if (await toggle.getAttribute('aria-expanded') !== 'false') failures.push('report: initial aria-expanded state is invalid');
      const detailsId = await toggle.getAttribute('aria-controls');
      if (!detailsId) failures.push('report: aria-controls missing');
      await toggle.focus();
      await page.keyboard.press('Enter');
      if (await toggle.getAttribute('aria-expanded') !== 'true') failures.push('report: Enter did not expand report');
      if (detailsId && !await page.locator(`#${detailsId}`).isVisible()) failures.push('report: controlled details region did not become visible');
    });
  } catch (error) {
    failures.push(`report journey-error: ${error.stack || error.message}`);
  }
}

async function checkDialogKeyboard(browser) {
  try {
    await withIsolatedPage(browser, { viewport: { width: 1440, height: 900 } }, 'dialog', async (page) => {
      await login(page, USERS.alliance);
      await openGameRoute(page, '/alliance');

      const generalTab = page.getByRole('tab', { name: 'General' });
      await generalTab.focus();
      await page.keyboard.press('ArrowRight');
      await page.waitForFunction(() => document.getElementById('alliance-tab-members')?.getAttribute('aria-selected') === 'true');
      await page.waitForFunction(() => document.activeElement?.id === 'alliance-tab-members');
      await page.keyboard.press('Home');
      await page.waitForFunction(() => document.getElementById('alliance-tab-general')?.getAttribute('aria-selected') === 'true');
      await page.waitForFunction(() => document.activeElement?.id === 'alliance-tab-general');

      const opener = page.getByRole('button', { name: 'Invitar Jugador' });
      await opener.waitFor({ state: 'visible', timeout: 10000 });
      await opener.focus();
      await page.keyboard.press('Enter');
      const dialog = page.getByRole('dialog', { name: 'Invitar Jugador' });
      await dialog.waitFor({ state: 'visible', timeout: 5000 });
      const focusInside = await dialog.evaluate((element) => element.contains(document.activeElement));
      if (!focusInside) failures.push('dialog: initial focus did not move inside modal');
      if (await dialog.getAttribute('aria-modal') !== 'true') failures.push('dialog: aria-modal is missing');

      const cancel = dialog.getByRole('button', { name: 'Cancelar' });
      await dialog.focus();
      await page.keyboard.press('Shift+Tab');
      await page.waitForFunction(() => document.activeElement?.textContent?.trim() === 'Cancelar');
      await page.keyboard.press('Tab');
      await page.waitForFunction(() => document.activeElement?.id === 'alliance-invite-search');

      await page.locator('main#main-content').focus();
      await page.waitForFunction(() => document.querySelector('[role="dialog"]')?.contains(document.activeElement));

      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'detached', timeout: 5000 });
      await page.waitForTimeout(50);
      const focusRestored = await opener.evaluate((element) => document.activeElement === element);
      if (!focusRestored) failures.push('dialog: focus was not restored to opener after Escape');
    });
  } catch (error) {
    failures.push(`dialog journey-error: ${error.stack || error.message}`);
  }
}

const browser = await chromium.launch({ headless: true });
try {
  await checkGeneralViewport(browser, { width: 1440, height: 900 }, 'desktop', false);
  await checkGeneralViewport(browser, { width: 390, height: 844 }, 'mobile', true);
  await checkReportKeyboard(browser);
  await checkDialogKeyboard(browser);
} finally {
  await browser.close().catch(() => {});
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G21 BM-0081 accessibility passed: mobile/desktop layout, world descriptions, internal map scrolling, SPA navigation, keyboard tabs, reports and modal focus trap');
