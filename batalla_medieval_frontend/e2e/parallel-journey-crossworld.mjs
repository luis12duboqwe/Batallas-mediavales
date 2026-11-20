import assert from 'node:assert/strict';
import { assertIsolated, call, playerSnapshot, suite, tokenFor } from './parallel-journey-helpers.mjs';

// API-level negative E2E tests: no synthetic response mocking or production DB writes.
assertIsolated();
const journey = suite('crossworld-mutations');
let token;
let a;
let b;
let cityA;
let cityB;
let beforeStatus;
let beforeMovements;
await journey.check('prepare player A in world A and distinct player capital in world B', async () => {
  token = await tokenFor('g7_research', 'G7-Research-Test-2026!');
  const snapshot = await playerSnapshot(token);
  a = snapshot.worldId;
  cityA = snapshot.cities[0].id;
  beforeStatus = await call(`/city/${cityA}/status?world_id=${a}`, { token });
  beforeMovements = snapshot.movements.map((movement) => movement.id);
  const otherToken = await tokenFor('g2_browser', 'G2-Browser-Test-2026!');
  const otherProfile = await call('/auth/me', { token: otherToken });
  b = otherProfile.world_id;
  assert.ok(a && b && a !== b);
  const other = await call(`/city/?world_id=${b}`, { token: otherToken });
  cityB = other[0].id;
  assert.ok(cityA !== cityB);
});

await journey.check('reject foreign building upgrade, training and research', async () => {
  assert.ok(token && cityA);
  await call(`/building/upgrade?world_id=${b}`, {
    method: 'POST', token, expected: 404, body: { city_id: cityA, building_type: 'woodcutter' },
  });
  await call(`/troop/train?world_id=${b}`, {
    method: 'POST', token, expected: 404, body: { city_id: cityA, troop_type: 'basic_infantry', amount: 1 },
  });
  await call(`/troop/research?world_id=${b}`, {
    method: 'POST', token, expected: 404, body: { city_id: cityA, unit_type: 'archer' },
  });
});

await journey.check('reject reading offers and transporting through world without membership', async () => {
  await call(`/market/offers?world_id=${b}`, { token, expected: 403 });
  await call(`/market/transport?city_id=${cityA}&world_id=${b}`, {
    method: 'POST', token, expected: 403,
    body: { target_city_id: cityB, wood: 1 },
  });
});

await journey.check('reject cross-world transport even with legitimate origin membership', async () => {
  await call(`/market/transport?city_id=${cityA}&world_id=${a}`, {
    method: 'POST', token, expected: 400,
    body: { target_city_id: cityB, wood: 1 },
  });
});

await journey.check('no forbidden mutation created queues, marches or cross-world city access', async () => {
  const status = await call(`/city/${cityA}/status?world_id=${a}`, { token });
  assert.deepEqual(status.building_queue.map((item) => item.id), beforeStatus.building_queue.map((item) => item.id));
  assert.deepEqual(status.troop_queue.map((item) => item.id), beforeStatus.troop_queue.map((item) => item.id));
  assert.deepEqual(status.research_queue.map((item) => item.id), beforeStatus.research_queue.map((item) => item.id));
  assert.deepEqual((await call(`/movement/?world_id=${a}`, { token })).map((movement) => movement.id), beforeMovements);
  assert.deepEqual(await call(`/city/?world_id=${b}`, { token }), []);
});
journey.finish();
