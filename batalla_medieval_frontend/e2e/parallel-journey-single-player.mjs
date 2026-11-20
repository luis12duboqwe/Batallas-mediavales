import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { UI, assertIsolated, call, loginUi, playerSnapshot, suite, verificationTokenFor } from './parallel-journey-helpers.mjs';

assertIsolated();
const run = suite('single-player-onboarding-to-first-battle');
const user = `pj1_${Date.now()}`;
const password = 'TestJourney-2026!42';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
let token, worldId, city, buildingQueue, troopQueue, targetId, mission, reportSeed;
const python = process.env.PARALLEL_JOURNEY_PYTHON || 'python3';
const backend = resolve(dirname(fileURLToPath(import.meta.url)), '../../batalla_medieval_backend');
function completeDue(model, queueId, ownerCityId, kind) {
  const script = [
    'import os,sys,json',
    'from datetime import timedelta',
    'assert os.environ["APP_ENV"]=="test" and os.environ["PARALLEL_JOURNEY_ALLOW_MUTATIONS"]=="isolated"',
    'from app import main as _bootstrap',
    'from app import models',
    'from app.database import SessionLocal',
    'from app.services import queue as worker',
    'from app.utils import utc_now',
    'db=SessionLocal()',
    'cls=getattr(models,sys.argv[1])',
    'row=db.get(cls,int(sys.argv[2]))',
    'assert row is not None',
    'owner=row.origin_city_id if sys.argv[4]=="Movement" else row.city_id',
    'assert owner==int(sys.argv[3])',
    'if sys.argv[4]=="Movement": row.arrival_time=utc_now()-timedelta(seconds=3)',
    'else: row.finish_time=utc_now()-timedelta(seconds=3)',
    'db.add(row);db.commit()',
    'worker.process_all_queues(db)',
    'print(json.dumps({"status":"ok"}));db.close()',
  ].join('\n');
  const output = execFileSync(python, ['-c', script, model, String(queueId), String(ownerCityId), kind],
    { encoding: 'utf8', env: { ...process.env, PYTHONPATH: backend }, timeout: 65000 });
  assert.equal(JSON.parse(output.trim().split('\n').at(-1)).status, 'ok');
}
try {
  await run.check('register, verify and log in as a new player using browser screens', async () => {
    await page.goto(`${UI}/register`);
    const fields = page.locator('form input');
    await fields.nth(0).fill(user);
    await fields.nth(1).fill(`${user}@example.com`);
    await fields.nth(2).fill(password);
    await page.getByRole('button', { name: 'Crear cuenta' }).click();
    await page.getByText('¡Registro Exitoso!').waitFor();
    await call('/auth/token', { method: 'POST', expected: 403, form: true, body: { username: user, password } });
    const verification = verificationTokenFor(user);
    await page.goto(`${UI}/verify-email?token=${encodeURIComponent(verification)}`);
    await page.getByText('¡Correo Verificado!').waitFor();
    token = await loginUi(page, user, password);
  });
  await run.check('join the active world and create precisely one persistent capital', async () => {
    const worlds = await call('/worlds/active', { token });
    worldId = worlds.worlds.find((item) => item.lifecycle_status === 'open')?.id;
    assert.ok(worldId);
    await page.getByTestId(`world-selector-${worldId}`).getByRole('button', { name: 'Unirse' }).click();
    const player = await playerSnapshot(token, worldId);
    assert.equal(player.cities.length, 1);
    city = player.cities[0];
    assert.equal(city.name, `Capital de ${user}`);
    assert.equal((await call(`/worlds/${worldId}/join`, { method: 'POST', token })).starting_city_id, city.id);
  });
  await run.check('queue first barracks from starting resources, including duplicate rejection', async () => {
    const before = await call(`/building/available?city_id=${city.id}&world_id=${worldId}`, { token });
    assert.ok(before.some((entry) => entry.name === 'barracks' && entry.can_upgrade));
    const q = await call(`/building/upgrade?world_id=${worldId}`, { method: 'POST', token,
      body: { city_id: city.id, building_type: 'barracks' } });
    buildingQueue = q.id;
    assert.ok(buildingQueue);
    await call(`/building/upgrade?world_id=${worldId}`, { method: 'POST', token, expected: 400,
      body: { city_id: city.id, building_type: 'barracks' } });
    const state = await call(`/city/${city.id}/status?world_id=${worldId}`, { token });
    assert.ok(state.building_queue.some((item) => item.id === buildingQueue));
  });
  await run.check('worker completes first barracks and its level persists', async () => {
    completeDue('BuildingQueue', buildingQueue, city.id, 'BuildingQueue');
    const fresh = (await playerSnapshot(token, worldId)).cities[0];
    assert.ok(fresh.buildings.some((item) => item.name === 'barracks' && item.level >= 1));
  });
  await run.check('train first infantry using real unlocked barracks', async () => {
    const units = await call(`/troop/available?city_id=${city.id}&world_id=${worldId}`, { token });
    const basic = units.find((item) => item.unit_type === 'basic_infantry');
    assert.ok(basic && basic.can_train, `First barracks did not unlock infantry: ${JSON.stringify(basic)}`);
    const q = await call(`/troop/train?world_id=${worldId}`, { method: 'POST', token,
      body: { city_id: city.id, troop_type: 'basic_infantry', amount: 2 } });
    troopQueue = q.id;
    assert.ok(troopQueue);
  });
  await run.check('worker completes actual troop queue, preserving quantities', async () => {
    completeDue('TroopQueue', troopQueue, city.id, 'TroopQueue');
    const fresh = (await playerSnapshot(token, worldId)).cities[0];
    assert.ok(fresh.troops.some((item) => item.unit_type === 'basic_infantry' && item.quantity >= 2));
  });
  await run.check('find a neutral enemy through world-scoped map and dispatch real first attack', async () => {
    const tiles = await call(`/map/tiles?world_id=${worldId}&x=20&y=15&radius=0`, { token });
    targetId = tiles.tiles.find((item) => item.city_id && item.owner_id === null)?.city_id;
    assert.ok(targetId && targetId !== city.id);
    mission = await call('/movement/', { method: 'POST', token,
      body: { origin_city_id: city.id, target_city_id: targetId, world_id: worldId,
        movement_type: 'attack', troops: { basic_infantry: 2 } } });
    assert.ok(mission.id && mission.status === 'ongoing');
  });
  await run.check('real worker resolves first attack, writing an auditable report exactly once', async () => {
    completeDue('Movement', mission.id, city.id, 'Movement');
    const before = await playerSnapshot(token, worldId);
    assert.equal(before.movements.find((item) => item.id === mission.id)?.status, 'completed');
    const reports = before.reports.filter((item) => item.report_type === 'battle');
    assert.equal(reports.length, 1);
    const audit = JSON.parse(reports[0].content).combat;
    assert.match(audit.seed, /^[a-f0-9]{64}$/i);
    reportSeed = audit.seed;
    completeDue('Movement', mission.id, city.id, 'Movement');
    assert.equal((await playerSnapshot(token, worldId)).reports.filter((item) => item.report_type === 'battle').length, 1);
  });
  await run.check('newly registered account sees its battle report in the browser after reload', async () => {
    assert.ok(reportSeed);
    await page.goto(`${UI}/reports`);
    await page.locator(`[data-testid="combat-audit"][data-combat-seed="${reportSeed}"]`).waitFor({ timeout: 16000 });
    await page.reload();
    await page.locator(`[data-testid="combat-audit"][data-combat-seed="${reportSeed}"]`).waitFor({ timeout: 16000 });
  });
} finally { await browser.close(); }
run.finish();
