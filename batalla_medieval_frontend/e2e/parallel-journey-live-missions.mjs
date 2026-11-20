import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';
import { assertIsolated, call, loginUi, playerSnapshot, suite, tokenFor, UI } from './parallel-journey-helpers.mjs';

// End-to-end positive control for military server operations. The web form's
// own target lookup currently fails: we deliberately dispatch through the
// real, authenticated HTTP API to distinguish a UI defect from game logic.
// Requires a fresh isolated database, G9 and G10 fixtures and a local API/UI.
assertIsolated();
const python = process.env.PARALLEL_JOURNEY_PYTHON || 'python3';
const backend = resolve(dirname(fileURLToPath(import.meta.url)), '../../batalla_medieval_backend');
const pythonEnv = { ...process.env, PYTHONPATH: backend };
const tests = suite('live-mission-api-to-report');
let worldId;
let attackUser;
let spyUser;
let attacker;
let spyCity;
let targetAttack;
let targetSpy;
let initial = {};
let attack;
let spy;
let attackReport;
let spyReport;

function dbCommand(program, data) {
  return JSON.parse(execFileSync(python, ['-c', program, JSON.stringify(data)], {
    encoding: 'utf8', env: pythonEnv, timeout: 65000,
  }).trim().split('\n').at(-1));
}

await tests.check('authenticate existing separated-world fixtures and identify real targets', async () => {
  attackUser = await tokenFor('g9_combat', 'G9-Combat-Test-2026!');
  spyUser = await tokenFor('g10_espionage', 'G10-Espionage-Test-2026!');
  const [a,b] = await Promise.all([playerSnapshot(attackUser), playerSnapshot(spyUser)]);
  worldId = a.worldId;
  assert.equal(b.worldId, worldId);
  attacker = a.cities[0];
  spyCity = b.cities[0];
  assert.ok(attacker?.id && spyCity?.id && attacker.id !== spyCity.id);
  const barbarian = await call(`/map/tiles?world_id=${worldId}&x=0&y=0&radius=0`, { token: attackUser });
  targetAttack = barbarian.tiles.find((item) => item.city_id && item.owner_id === null)?.city_id;
  targetSpy = b.movements.find((item) =>
    item.movement_type === 'spy' && item.status === 'completed' &&
    item.origin_city_id === spyCity.id)?.target_city_id;
  assert.ok(targetAttack && targetSpy && targetAttack !== attacker.id && targetSpy !== spyCity.id);
  initial.reportIdsA = new Set(a.reports.map((item) => item.id));
  initial.reportIdsB = new Set(b.reports.map((item) => item.id));
  initial.battle = a.reports.filter((item) =>
    item.report_type === 'battle' && item.defender_city_id === targetAttack).length;
  initial.spies = b.reports.filter((item) =>
    item.report_type === 'spy' && item.defender_city_id === targetSpy).length;
  initial.movesA = new Set(a.movements.map((item) => item.id));
  initial.movesB = new Set(b.movements.map((item) => item.id));
  assert.ok(initial.battle >= 1 && initial.spies >= 1, 'G9/G10 baseline audit reports missing');
});

await tests.check('prepare sufficient military units ONLY inside the disposable SQLite fixture', async () => {
  assert.ok(attacker && spyCity && targetAttack && targetSpy);
  const script = `
import json, os, sys
assert os.environ["APP_ENV"] == "test"
assert os.environ["PARALLEL_JOURNEY_ALLOW_MUTATIONS"] == "isolated"
from app import main as _bootstrap
from app import models
from app.database import SessionLocal
p=json.loads(sys.argv[1]); db=SessionLocal()
try:
  counts={}
  for label, city, unit, qty in [
    ("attack", p["attacker"], "heavy_cavalry", 75),
    ("spy", p["spy_city"], "spy", 12),
  ]:
    row=db.query(models.Troop).filter_by(city_id=city, unit_type=unit).one_or_none()
    if row is None:
      row=models.Troop(city_id=city, unit_type=unit, quantity=0)
    row.quantity += qty
    counts[label] = row.quantity
    db.add(row)
  db.commit()
  print(json.dumps(counts))
finally:
  db.close()
`;
  const result = dbCommand(script, { attacker: attacker.id, spy_city: spyCity.id });
  assert.ok(result.attack >= 75 && result.spy >= 12, 'Unable to provision isolated test army');
  initial.attackTroops = result.attack;
  initial.spyTroops = result.spy;
});

await tests.check('real HTTP attack reserves troops and exposes server-authoritative travel', async () => {
  assert.ok(initial.attackTroops > 0);
  attack = await call('/movement/', { method: 'POST', token: attackUser,
    body: { origin_city_id: attacker.id, target_city_id: targetAttack,
      world_id: worldId, movement_type: 'attack', troops: { heavy_cavalry: 50 } } });
  assert.ok(attack.id && !initial.movesA.has(attack.id));
  assert.equal(attack.movement_type, 'attack');
  assert.equal(attack.status, 'ongoing');
  const fresh = await call(`/city/?world_id=${worldId}`, { token: attackUser });
  assert.equal(fresh.find((item) => item.id === attacker.id)
    .troops.find((item) => item.unit_type === 'heavy_cavalry').quantity,
    initial.attackTroops - 50);
  assert.ok((await call(`/movement/?world_id=${worldId}`, { token: attackUser }))
    .some((item) => item.id === attack.id));
});

await tests.check('oversubscription is rejected and does not launch a second march', async () => {
  assert.ok(attack?.id);
  await call('/movement/', { method: 'POST', token: attackUser, expected: 400,
    body: { origin_city_id: attacker.id, target_city_id: targetAttack,
      world_id: worldId, movement_type: 'attack', troops: { heavy_cavalry: initial.attackTroops } } });
  const moves = await call(`/movement/?world_id=${worldId}`, { token: attackUser });
  assert.equal(moves.filter((item) => !initial.movesA.has(item.id)).length, 1);
});

await tests.check('real HTTP spy dispatch reserves spies without exposing target intel', async () => {
  spy = await call('/movement/', { method: 'POST', token: spyUser,
    body: { origin_city_id: spyCity.id, target_city_id: targetSpy, world_id: worldId,
      movement_type: 'spy', troops: {}, spy_count: 7 } });
  assert.ok(spy.id && !initial.movesB.has(spy.id));
  assert.equal(spy.movement_type, 'spy');
  assert.equal(spy.status, 'ongoing');
  assert.equal(spy.spy_count, 7);
  const fresh = await call(`/city/?world_id=${worldId}`, { token: spyUser });
  assert.equal(fresh.find((item) => item.id === spyCity.id)
    .troops.find((item) => item.unit_type === 'spy').quantity,
    initial.spyTroops - 7);
});

await tests.check('isolated worker executes both real dispatches with deadlines advanced ONLY in test DB', async () => {
  assert.ok(attack?.id && spy?.id);
  const script = `
import json, os, sys
from datetime import timedelta
assert os.environ["APP_ENV"] == "test"
assert os.environ["PARALLEL_JOURNEY_ALLOW_MUTATIONS"] == "isolated"
from app import main as _bootstrap
from app import models
from app.database import SessionLocal
from app.services import queue as worker
from app.utils import utc_now
p=json.loads(sys.argv[1]); db=SessionLocal()
try:
  ids=[]
  for key,origin,kind in [("attack",p["attacker"],"attack"),("spy",p["spy_city"],"spy")]:
    row=db.get(models.Movement, p[key])
    assert row and row.origin_city_id==origin and row.world_id==p["world_id"]
    assert row.movement_type==kind and row.status=="ongoing"
    row.arrival_time = utc_now() - timedelta(seconds=3)
    db.add(row)
    ids.append(row.id)
  db.commit()
  finished=worker.process_all_queues(db)
  for movement_id in ids:
    assert db.get(models.Movement,movement_id).status == "completed"
  print(json.dumps({"ids":ids,"result":finished},default=str))
finally:
  db.close()
`;
  const result = dbCommand(script, { attack: attack.id, spy: spy.id,
    attacker: attacker.id, spy_city: spyCity.id, world_id: worldId });
  assert.deepEqual(result.ids, [attack.id, spy.id]);
});

await tests.check('new battle and spy reports are durable, auditable and visible only to their player', async () => {
  const [a,b] = await Promise.all([playerSnapshot(attackUser), playerSnapshot(spyUser)]);
  assert.equal(a.movements.find((item) => item.id === attack.id)?.status, 'completed');
  assert.equal(b.movements.find((item) => item.id === spy.id)?.status, 'completed');
  const battles = a.reports.filter((item) => item.report_type === 'battle' && item.defender_city_id === targetAttack);
  const spies = b.reports.filter((item) => item.report_type === 'spy' && item.defender_city_id === targetSpy);
  assert.equal(battles.length, initial.battle + 1);
  assert.equal(spies.length, initial.spies + 1);
  attackReport = battles.find((item) => !initial.reportIdsA.has(item.id));
  spyReport = spies.find((item) => !initial.reportIdsB.has(item.id));
  assert.ok(attackReport && spyReport, 'New reports were not found');
  const combat = JSON.parse(attackReport.content).combat;
  const espionage = JSON.parse(spyReport.content);
  assert.match(combat.seed, /^[a-f\d]{64}$/i);
  assert.equal(combat.rounds.length, combat.round_count);
  assert.ok(combat.round_count >= 1);
  assert.match(espionage.seed, /^[a-f\d]{64}$/i);
  assert.ok(!JSON.stringify(b.reports).includes(combat.seed), 'Spy player received attacker combat intel');
  assert.ok(!JSON.stringify(a.reports).includes(espionage.seed), 'Combat player received spy intel');
  initial.combatSeed = combat.seed;
  initial.spySeed = espionage.seed;
});

await tests.check('retrying the worker does not reroll or duplicate combat/spy reports', async () => {
  assert.ok(initial.combatSeed && initial.spySeed);
  const script = `
import json, os
from app import main as _bootstrap
from app.database import SessionLocal
from app.services import queue as worker
db=SessionLocal()
try:
  completed=worker.process_all_queues(db)
  print(json.dumps(completed,default=str))
finally:
  db.close()
`;
  dbCommand(script, {});
  const [a,b] = await Promise.all([playerSnapshot(attackUser), playerSnapshot(spyUser)]);
  assert.equal(a.reports.filter((item) => item.report_type === 'battle' &&
    item.defender_city_id === targetAttack).length, initial.battle + 1);
  assert.equal(b.reports.filter((item) => item.report_type === 'spy' &&
    item.defender_city_id === targetSpy).length, initial.spies + 1);
  assert.equal(JSON.parse(a.reports.find((item) => item.id === attackReport.id).content).combat.seed, initial.combatSeed);
  assert.equal(JSON.parse(b.reports.find((item) => item.id === spyReport.id).content).seed, initial.spySeed);
});

await tests.check('browser shows newly resolved audit report after reload and reauthentication', async () => {
  assert.ok(initial.combatSeed && initial.spySeed);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await loginUi(page, 'g9_combat', 'G9-Combat-Test-2026!');
    await page.goto(`${UI}/reports`, { waitUntil: 'domcontentloaded' });
    await page.locator(`[data-testid="combat-audit"][data-combat-seed="${initial.combatSeed}"]`)
      .waitFor({ state: 'visible', timeout: 18000 });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator(`[data-testid="combat-audit"][data-combat-seed="${initial.combatSeed}"]`)
      .waitFor({ state: 'visible', timeout: 18000 });
    await loginUi(page, 'g10_espionage', 'G10-Espionage-Test-2026!');
    await page.goto(`${UI}/reports`, { waitUntil: 'domcontentloaded' });
    const headings = page.getByText('Espionaje en G10 Intelligence Target', { exact: true });
    await headings.first().waitFor({ state: 'visible', timeout: 16000 });
    let found = false;
    for (const heading of await headings.all()) {
      await heading.click();
      const panel = heading.locator('xpath=ancestor::*[contains(@class,"card")][1]').getByTestId('spy-audit');
      if (await panel.count() && (await panel.getAttribute('data-spy-seed')) === initial.spySeed) {
        found = true;
        break;
      }
    }
    assert.ok(found, 'UI did not display the new server-authoritative espionage audit');
  } finally {
    await browser.close();
  }
});
tests.finish();
