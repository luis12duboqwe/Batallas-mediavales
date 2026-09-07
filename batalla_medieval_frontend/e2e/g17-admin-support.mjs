import fs from 'node:fs';
import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const TOKEN = fs.readFileSync('/tmp/g17-admin-token', 'utf8').trim();
const CASE_SUBJECT = 'G17 correction request';
const CHAT_CONTENT = 'G17 moderation target';
const failures = [];

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') failures.push(`console.error: ${message.text()}`);
});
page.on('response', (response) => {
  if (response.status() >= 500) failures.push(`HTTP ${response.status()}: ${response.url()}`);
});

async function waitForExperienceReady() {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  const loading = page.getByTestId('loading-screen');
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
}

async function api(path, options = {}) {
  const requestOptions = {
    method: options.method || 'GET',
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
  };
  if (options.data) requestOptions.data = options.data;
  const response = await context.request.fetch(`${API_URL}${path}`, requestOptions);
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  return { status: response.status(), body };
}

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((token) => localStorage.setItem('bm_token', token), TOKEN);
  await page.goto(`${BASE_URL}/admin`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  await page.getByTestId('bm0073-admin-panel').waitFor({ state: 'visible', timeout: 10000 });

  const bodyText = await page.locator('body').innerText();
  if (bodyText.includes('Eliminar Ciudad') || bodyText.includes('Eliminar Usuario')) {
    failures.push('Destructive delete controls are still exposed in BM-0073 admin UI');
  }

  const cases = await api('/support/admin/cases?limit=100');
  if (cases.status !== 200) throw new Error(`support catalogue failed: ${cases.status}`);
  const supportCase = cases.body.find((row) => row.subject === CASE_SUBJECT);
  if (!supportCase) throw new Error('G17 support fixture missing');

  const history = await api('/chat/history/global?limit=100');
  if (history.status !== 200) throw new Error(`chat history failed: ${history.status}`);
  const chatMessage = history.body.find((row) => row.content === CHAT_CONTENT);
  if (!chatMessage) throw new Error('G17 moderation target missing from public history');

  await page.getByTestId('admin-reason').fill('G17 hide abusive content');
  await page.getByTestId('admin-support-case-id').fill(String(supportCase.id));
  const moderation = page.getByTestId('admin-global-moderation');
  await moderation.locator('select').selectOption('chat');
  await moderation.locator('input[type="number"]').fill(String(chatMessage.id));
  await moderation.getByRole('button', { name: 'Ocultar' }).click();
  await page.getByTestId('admin-operation-log').getByText(/Ocultar contenido: operación registrada y auditada/).waitFor({ timeout: 10000 });

  const hiddenTarget = await api(`/admin/moderation/chat/${chatMessage.id}`);
  if (hiddenTarget.status !== 200 || hiddenTarget.body?.is_hidden !== true) {
    failures.push(`Moderation did not persist hidden state: ${JSON.stringify(hiddenTarget.body)}`);
  }
  const hiddenHistory = await api('/chat/history/global?limit=100');
  if (hiddenHistory.body?.some((row) => Number(row.id) === Number(chatMessage.id))) {
    failures.push('Hidden chat message remained visible in public history');
  }

  const auditAfterHide = await api('/admin/logs?limit=100');
  const hideLog = auditAfterHide.body?.find(
    (row) => row.action === 'moderate_chat_message' && row.reason === 'G17 hide abusive content',
  );
  if (!hideLog) {
    failures.push('Moderation audit entry missing');
  } else {
    if (!hideLog.before_state || !hideLog.after_state || !hideLog.reversible) {
      failures.push(`Moderation audit lacks reversible before/after: ${JSON.stringify(hideLog)}`);
    }
    await page.getByTestId('admin-reason').fill('G17 restore moderated content');
    const auditRow = page.getByTestId('admin-audit-log').locator('div.border').filter({ hasText: `#${hideLog.id}` });
    await auditRow.getByRole('button', { name: 'Revertir' }).click();
    await page.getByTestId('admin-operation-log').getByText(new RegExp(`Auditoría #${hideLog.id}: reversión aplicada`)).waitFor({ timeout: 10000 });

    const restoredTarget = await api(`/admin/moderation/chat/${chatMessage.id}`);
    if (restoredTarget.body?.is_hidden !== false) failures.push('Audit undo did not restore moderated content');
    const restoredHistory = await api('/chat/history/global?limit=100');
    if (!restoredHistory.body?.some((row) => Number(row.id) === Number(chatMessage.id))) {
      failures.push('Restored chat message did not return to public history');
    }
  }

  await page.getByTestId('admin-reason').fill('G17 resolve support case');
  const caseRow = page.getByTestId('admin-support-cases').locator('tbody tr').filter({ hasText: CASE_SUBJECT });
  await caseRow.getByRole('button', { name: 'Resolver' }).click();
  await page.getByTestId('admin-operation-log').getByText(new RegExp(`Caso #${supportCase.id}: resolved`)).waitFor({ timeout: 10000 });

  const resolvedCases = await api('/support/admin/cases?limit=100');
  const resolved = resolvedCases.body?.find((row) => Number(row.id) === Number(supportCase.id));
  if (resolved?.status !== 'resolved' || !resolved?.resolution) {
    failures.push(`Support workflow did not persist resolution: ${JSON.stringify(resolved)}`);
  }

  const finalAudit = await api('/admin/logs?limit=100');
  if (!finalAudit.body?.some((row) => row.action === 'revert_admin_action' && row.reason === 'G17 restore moderated content')) {
    failures.push('Reversal audit entry missing');
  }
} catch (error) {
  failures.push(`journey-error: ${error.stack || error.message}`);
} finally {
  await context.close();
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G17 BM-0073 administration, support and moderation browser journey passed');
