import { chromium } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';
const API_URL = process.env.VITE_API_URL || 'http://127.0.0.1:8000';
const PASSWORD = 'G14-Community-Test-2026!';
const USERS = {
  leader: 'g14_leader',
  member: 'g14_member',
  rival: 'g14_rival',
};
const failures = [];

async function tokenFor(username) {
  const body = new URLSearchParams({ username, password: PASSWORD });
  const response = await fetch(`${API_URL}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!response.ok) throw new Error(`login ${username} ${response.status}: ${(await response.text()).slice(0, 300)}`);
  return (await response.json()).access_token;
}

async function api(token, path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  return { response, data };
}

async function requireOk(token, path, options = {}) {
  const result = await api(token, path, options);
  if (!result.response.ok) {
    throw new Error(`${path} ${result.response.status}: ${JSON.stringify(result.data).slice(0, 400)}`);
  }
  return result.data;
}

async function profile(token) {
  return requireOk(token, '/auth/me');
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
page.on('console', (message) => {
  if (message.type() === 'error') failures.push(`console.error: ${message.text()}`);
});
page.on('response', async (response) => {
  if (response.status() >= 500) {
    let body = '';
    try { body = (await response.text()).slice(0, 500); } catch { body = '<unreadable>'; }
    failures.push(`HTTP ${response.status()}: ${response.url()} body=${body}`);
  }
});

async function waitForExperienceReady() {
  const intro = page.getByTestId('intro-animation');
  if (await intro.count()) await intro.waitFor({ state: 'detached', timeout: 10000 });
  const loading = page.getByTestId('loading-screen');
  await loading.waitFor({ state: 'attached', timeout: 1500 }).catch(() => {});
  if (await loading.count()) await loading.waitFor({ state: 'detached', timeout: 10000 });
}

async function browserLogin(username) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  const inputs = page.locator('form input');
  await inputs.nth(0).fill(username);
  await inputs.nth(1).fill(PASSWORD);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 15000 });
  await waitForExperienceReady();
}

async function useToken(token) {
  await page.evaluate((value) => localStorage.setItem('bm_token', value), token);
  await page.goto(`${BASE_URL}/alliance`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  await page.getByTestId('alliance-community-view').waitFor({ state: 'visible', timeout: 10000 });
}

try {
  const [leaderToken, memberToken, rivalToken] = await Promise.all([
    tokenFor(USERS.leader),
    tokenFor(USERS.member),
    tokenFor(USERS.rival),
  ]);
  const [leaderProfile, memberProfile, rivalProfile] = await Promise.all([
    profile(leaderToken),
    profile(memberToken),
    profile(rivalToken),
  ]);
  const worldId = Number(leaderProfile.world_id);
  if (!worldId || Number(memberProfile.world_id) !== worldId || Number(rivalProfile.world_id) !== worldId) {
    throw new Error(`G14 users are not in one active world: ${JSON.stringify({ leaderProfile, memberProfile, rivalProfile })}`);
  }

  const leaderAlliance = await requireOk(leaderToken, `/alliance/?world_id=${worldId}`);
  const rivalAlliance = await requireOk(rivalToken, `/alliance/?world_id=${worldId}`);
  if (!leaderAlliance?.id || !rivalAlliance?.id || Number(leaderAlliance.id) === Number(rivalAlliance.id)) {
    throw new Error(`G14 alliance fixture mismatch: ${JSON.stringify({ leaderAlliance, rivalAlliance })}`);
  }

  const initialMembers = await requireOk(leaderToken, `/alliance/${leaderAlliance.id}/members`);
  const target = initialMembers.find((entry) => Number(entry.user_id) === Number(memberProfile.id));
  if (!target?.id) throw new Error(`Canonical membership id missing from member API: ${JSON.stringify(initialMembers)}`);
  if (Number(target.rank) !== 1) throw new Error(`G14 target must start as Member: ${JSON.stringify(target)}`);

  const deniedDiplomacy = await api(memberToken, `/alliance/${leaderAlliance.id}/diplomacy`, {
    method: 'POST',
    body: JSON.stringify({ alliance_target_id: rivalAlliance.id, status: 'ally' }),
  });
  if (deniedDiplomacy.response.status !== 403) {
    failures.push(`Member diplomacy should be 403, got ${deniedDiplomacy.response.status}`);
  }

  await browserLogin(USERS.leader);
  await page.goto(`${BASE_URL}/alliance`, { waitUntil: 'networkidle' });
  await waitForExperienceReady();
  await page.getByTestId('alliance-community-view').waitFor({ state: 'visible', timeout: 10000 });

  const chatText = 'G14 chat canónico visible';
  await page.getByTestId('alliance-chat-input').fill(chatText);
  await page.getByTestId('alliance-chat-send').click();
  await page.getByTestId('alliance-chat-history').getByText(chatText, { exact: true }).waitFor({ state: 'visible', timeout: 7000 });
  const canonicalHistory = await requireOk(leaderToken, `/chat/history/alliance?limit=100`);
  if (!canonicalHistory.some((entry) => entry.content === chatText && Number(entry.alliance_id) === Number(leaderAlliance.id))) {
    failures.push(`HTTP alliance chat did not land in canonical ChatMessage history: ${JSON.stringify(canonicalHistory)}`);
  }

  await page.getByTestId('alliance-forum-tab').click();
  await page.getByTestId('alliance-forum').waitFor({ state: 'visible', timeout: 5000 });
  await page.getByTestId('forum-new-thread').click();
  await page.getByTestId('forum-thread-title').fill('G14 Estrategia');
  await page.getByTestId('forum-thread-content').fill('Coordinación comunitaria G14');
  await page.getByTestId('forum-thread-submit').click();
  await page.getByText('G14 Estrategia', { exact: true }).waitFor({ state: 'visible', timeout: 5000 });
  await page.getByText('G14 Estrategia', { exact: true }).click();
  await page.getByTestId('forum-moderation-controls').waitFor({ state: 'visible', timeout: 5000 });
  await page.getByTestId('forum-toggle-pin').click();
  await page.getByTestId('forum-thread-status').getByText(/Fijado/).waitFor({ state: 'visible', timeout: 5000 });
  await page.getByTestId('forum-toggle-lock').click();
  await page.getByTestId('forum-thread-status').getByText(/Cerrado/).waitFor({ state: 'visible', timeout: 5000 });
  if (await page.getByTestId('forum-reply-submit').count()) failures.push('Locked forum thread still exposed reply action');

  await page.getByTestId('alliance-members-tab').click();
  await page.getByTestId(`alliance-member-${memberProfile.id}`).waitFor({ state: 'visible', timeout: 5000 });
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByTestId(`transfer-leadership-${memberProfile.id}`).click();
  await page.getByTestId(`alliance-member-${memberProfile.id}`).getByText('Líder', { exact: true }).waitFor({ state: 'visible', timeout: 7000 });

  const afterTransfer = await requireOk(memberToken, `/alliance/${leaderAlliance.id}/members`);
  const newLeader = afterTransfer.find((entry) => Number(entry.user_id) === Number(memberProfile.id));
  const oldLeader = afterTransfer.find((entry) => Number(entry.user_id) === Number(leaderProfile.id));
  if (Number(newLeader?.rank) !== 3 || Number(oldLeader?.rank) !== 2) {
    failures.push(`Leadership transfer ranks invalid: ${JSON.stringify(afterTransfer)}`);
  }
  const canonicalAlliance = await requireOk(memberToken, `/alliance/?world_id=${worldId}`);
  if (Number(canonicalAlliance.leader_id) !== Number(memberProfile.id)) {
    failures.push(`Alliance leader_id did not move to new leader: ${JSON.stringify(canonicalAlliance)}`);
  }

  const relation = await requireOk(memberToken, `/alliance/${leaderAlliance.id}/diplomacy`, {
    method: 'POST',
    body: JSON.stringify({ alliance_target_id: rivalAlliance.id, status: 'ally' }),
  });
  const accepted = await requireOk(rivalToken, `/alliance/${rivalAlliance.id}/diplomacy/${relation.id}/accept`, { method: 'POST' });
  if (accepted.status !== 'ally') failures.push(`Diplomacy did not become ally: ${JSON.stringify(accepted)}`);

  await requireOk(memberToken, '/chat/blocks', {
    method: 'POST',
    body: JSON.stringify({ user_id: rivalProfile.id, world_id: worldId }),
  });
  const blockedMessage = await api(rivalToken, '/message/send', {
    method: 'POST',
    body: JSON.stringify({ receiver_id: memberProfile.id, subject: 'Bloqueado', content: 'No debe entrar' }),
  });
  if (blockedMessage.response.status !== 403) {
    failures.push(`Blocked persistent message should be 403, got ${blockedMessage.response.status}`);
  }

  await useToken(memberToken);
  await page.getByTestId('alliance-members-tab').click();
  await page.getByTestId(`alliance-member-${leaderProfile.id}`).waitFor({ state: 'visible', timeout: 5000 });
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByTestId(`kick-member-${leaderProfile.id}`).click();
  await page.getByTestId(`alliance-member-${leaderProfile.id}`).waitFor({ state: 'detached', timeout: 7000 });

  const revokedChat = await api(leaderToken, `/alliance/${leaderAlliance.id}/chat`);
  if (revokedChat.response.status !== 403) {
    failures.push(`Expelled member retained alliance chat access: ${revokedChat.response.status}`);
  }
  const revokedForum = await api(leaderToken, `/forum/alliance/${leaderAlliance.id}/threads`);
  if (revokedForum.response.status !== 403) {
    failures.push(`Expelled member retained alliance forum access: ${revokedForum.response.status}`);
  }
} catch (error) {
  failures.push(`journey-error: ${error.stack || error.message}`);
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}

console.log('G14 BM-0070 community diplomacy browser journey passed');
