import assert from 'node:assert/strict';
import test from 'node:test';
import {
  adventureDeadlineMs,
  applyAdventureResponse,
  canClaimAdventure,
} from '../src/components/parallel-adventures/adventureState.js';

test('UTC datetimes without a timezone are interpreted as UTC, not local time', () => {
  const adventure = {
    status: 'active',
    started_at: '2026-11-20T14:30:00',
    duration: 90,
  };
  assert.equal(adventureDeadlineMs(adventure), Date.UTC(2026, 10, 20, 14, 31, 30));
  assert.equal(canClaimAdventure(adventure, Date.UTC(2026, 10, 20, 14, 31, 29)), false);
  assert.equal(canClaimAdventure(adventure, Date.UTC(2026, 10, 20, 14, 31, 30)), true);
});

test('offsets, Z timestamps and fractional seconds preserve their instants', () => {
  const inputs = [
    '2026-11-20T08:30:00-06:00',
    '2026-11-20T14:30:00Z',
    '2026-11-20 14:30:00',
    '2026-11-20T14:30:00.000',
    '2026-11-20T14:30:00.000+00:00',
  ];
  for (const started_at of inputs) {
    assert.equal(
      adventureDeadlineMs({ started_at, duration: 60 }),
      Date.UTC(2026, 10, 20, 14, 31),
      started_at,
    );
  }
});

test('missing or invalid deadlines never offer a claim', () => {
  const invalid = [
    { started_at: null, duration: 10 },
    { started_at: 'not-a-date', duration: 10 },
    { started_at: '2026-11-20T14:30:00Z', duration: -1 },
    { started_at: '2026-11-20T14:30:00Z', duration: 'NaN' },
  ];
  for (const adventure of invalid) {
    assert.equal(adventureDeadlineMs(adventure), null);
    assert.equal(canClaimAdventure({ ...adventure, status: 'active' }, Infinity), false);
  }
  const zero = { started_at: '2026-11-20T14:30:00Z', duration: 0 };
  assert.equal(canClaimAdventure({ ...zero, status: 'active' }, Date.UTC(2026, 10, 20, 14, 30)), true);
  assert.equal(canClaimAdventure({ ...zero, status: 'available' }, Date.UTC(2026, 10, 20, 14, 31)), false);
  assert.equal(canClaimAdventure({ ...zero, status: 'completed' }, Date.UTC(2026, 10, 20, 14, 31)), false);
  assert.equal(canClaimAdventure({ ...zero, status: 'failed' }, Date.UTC(2026, 10, 20, 14, 31)), false);
});

test('start uses only an acknowledged server state and does not affect other adventures', () => {
  const original = [{ id: 1, status: 'available' }, { id: 2, status: 'available' }];
  const started = applyAdventureResponse(original, '1', 'start', {
    id: 1, status: 'active', started_at: '2026-11-20T14:30:00Z',
    outcome_seed: 'a'.repeat(64),
  });
  assert.equal(started[0].status, 'active');
  assert.equal(started[0].outcome_seed.length, 64);
  assert.strictEqual(started[1], original[1]);
  assert.equal(original[0].status, 'available');
  assert.deepEqual(applyAdventureResponse(original, 1, 'start', { status: 'available' }), original);
});

test('claim reflects only server-returned success/defeat, preserving reward contents', () => {
  const original = [{ id: 3, status: 'active', result: null }, { id: 4, status: 'active', result: null }];
  const success = { status: 'success', xp: 30, damage: 5, loot: { type: 'resource', amount: 50 }, seed: 'abc' };
  const after = applyAdventureResponse(original, 3, 'claim', success);
  assert.equal(after[0].status, 'completed');
  assert.strictEqual(after[0].result, success);
  assert.strictEqual(after[1], original[1]);

  const defeat = { status: 'dead', xp: 0, damage: 200, loot: null, seed: 'def' };
  const dead = applyAdventureResponse(after, 4, 'claim', defeat);
  assert.equal(dead[1].status, 'failed');
  assert.strictEqual(dead[1].result, defeat);
  assert.deepEqual(applyAdventureResponse(original, 3, 'claim', { status: 'pending', loot: { amount: 999 } }), original);
});
