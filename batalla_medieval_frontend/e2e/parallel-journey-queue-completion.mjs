import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertIsolated, call, tokenFor, suite, UI, loginUi } from './parallel-journey-helpers.mjs';

// Run after parallel-journey-progression on a disposable SQLite database.
// This deliberately advances ONLY the three identified fixture queue deadlines,
// then invokes the real worker service once (no production clocks or schedulers).
const db = assertIsolated();
const run = suite('queue-completion');
const backend = resolve(dirname(fileURLToPath(import.meta.url)), '../../batalla_medieval_backend');
const python = process.env.PARALLEL_JOURNEY_PYTHON || 'python3';
const pyEnv = { ...process.env, PYTHONPATH: backend };
const user7 = await tokenFor('g7_research', 'G7-Research-Test-2026!');
const user8 = await tokenFor('g8_upkeep', 'G8-Upkeep-Test-2026!');
let a;
let b;
let before;
let initialTroops;
let workerFinished = false;

async function status(token, city) {
  return call(`/city/${city.id}/status?world_id=${city.world_id}`, { token });
}

await run.check('all three genuine queues were created before worker simulation', async () => {
  const worldA = (await call('/auth/me', { token: user7 })).world_id;
  const worldB = (await call('/auth/me', { token: user8 })).world_id;
  a = (await call(`/city/?world_id=${worldA}`, { token: user7 }))[0];
  b = (await call(`/city/?world_id=${worldB}`, { token: user8 }))[0];
  assert.ok(a && b && a.id !== b.id);
  const [aStatus, bStatus] = await Promise.all([status(user7, a), status(user8, b)]);
  before = {
    build: aStatus.building_queue[0],
    research: aStatus.research_queue[0],
    train: bStatus.troop_queue[0],
  };
  for (const [key, entry] of Object.entries(before)) {
    assert.ok(entry?.id, `Missing expected ${key} queue. Run progression test first on a fresh isolated database.`);
  }
  initialTroops = b.troops.find((troop) => troop.unit_type === before.train.troop_type)?.quantity || 0;
});

await run.check('complete precisely selected queues through production worker on test SQLite', async () => {
  assert.ok(before?.build?.id && before?.research?.id && before?.train?.id);
  const payload = {
    ids: { build: before.build.id, research: before.research.id, train: before.train.id },
    owners: { a: a.id, b: b.id },
  };
  const program = `
import json, os, sys
from datetime import timedelta
from app.database import SessionLocal
from app import models
from app import main as _application_bootstrap
from app.services import queue as worker_queue
from app.utils import utc_now
assert os.environ["APP_ENV"] == "test"
assert os.environ["PARALLEL_JOURNEY_ALLOW_MUTATIONS"] == "isolated"
payload = json.loads(sys.argv[1])
db = SessionLocal()
try:
    due = utc_now() - timedelta(seconds=2)
    for key, model, city in [
       ("build", models.BuildingQueue, payload["owners"]["a"]),
       ("research", models.ResearchQueue, payload["owners"]["a"]),
       ("train", models.TroopQueue, payload["owners"]["b"]),
    ]:
       item = db.get(model, payload["ids"][key])
       assert item is not None and item.city_id == city, (key, "fixture ownership mismatch")
       item.finish_time = due
       db.add(item)
    db.commit()
    result = worker_queue.process_all_queues(db)
    print(json.dumps(result, default=str))
finally:
    db.close()
`;
  const output = execFileSync(python, ['-c', program, JSON.stringify(payload)], {
    env: pyEnv, encoding: 'utf8', timeout: 50000,
  });
  assert.ok(output.includes('building') && output.includes('troop'), `Unexpected worker result: ${output.slice(0, 500)}`);
  workerFinished = true;
});

if (!workerFinished) run.finish(); // Preserve the worker failure without manufacturing dependent defects.

await run.check('worker consumes queues exactly once and persists building/research/troop progress', async () => {
  const [aStatus, bStatus, aCities, bCities] = await Promise.all([
    status(user7, a), status(user8, b),
    call(`/city/?world_id=${a.world_id}`, { token: user7 }),
    call(`/city/?world_id=${b.world_id}`, { token: user8 }),
  ]);
  assert.ok(!aStatus.building_queue.some((entry) => entry.id === before.build.id), 'Finished construction queue still present');
  assert.ok(!aStatus.research_queue.some((entry) => entry.id === before.research.id), 'Finished research queue still present');
  assert.ok(!bStatus.troop_queue.some((entry) => entry.id === before.train.id), 'Finished troop queue still present');
  const afterA = aCities.find((city) => city.id === a.id);
  const afterB = bCities.find((city) => city.id === b.id);
  assert.ok(afterA.buildings.some((entry) =>
    entry.name === before.build.building_type && entry.level >= before.build.target_level),
    'Building level never became durable');
  assert.ok(afterA.researched_units.includes(before.research.tech_name), 'Research not unlocked after completion');
  const afterCount = afterB.troops.find((entry) => entry.unit_type === before.train.troop_type)?.quantity || 0;
  assert.equal(afterCount, initialTroops + before.train.amount, 'Trained units do not match the reserved quantity');
});

await run.check('completed queues reject stale cancellation without reversing progress', async () => {
  await call(`/building/queue/${before.build.id}`, { method: 'DELETE', token: user7, expected: 404 });
  await call(`/troop/queue/${before.train.id}`, { method: 'DELETE', token: user8, expected: 404 });
  const first = await call(`/city/?world_id=${a.world_id}`, { token: user7 });
  assert.ok(first[0].researched_units.includes(before.research.tech_name));
});

await run.check('buildings, academy and troop views reload after real worker completion', async () => {
  const { chromium } = await import('@playwright/test');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  try {
    await loginUi(page, 'g7_research', 'G7-Research-Test-2026!');
    for (const route of ['/buildings', '/academy']) {
      await page.goto(`${UI}${route}`, { waitUntil: 'domcontentloaded' });
      await page.waitForURL((url) => url.pathname === route, { timeout: 15000 });
    }
    await page.getByTestId(`research-card-${before.research.tech_name}`)
      .getByRole('button', { name: 'Tecnología Dominada' }).waitFor({ state: 'visible', timeout: 15000 });
    await loginUi(page, 'g8_upkeep', 'G8-Upkeep-Test-2026!');
    await page.goto(`${UI}/troops`, { waitUntil: 'domcontentloaded' });
    await page.getByText('Cola de entrenamiento').waitFor({ timeout: 15000 });
    assert.equal(await page.getByTestId(`troop-queue-${before.train.id}`).count(), 0);
  } finally {
    await browser.close();
  }
});
run.finish();
