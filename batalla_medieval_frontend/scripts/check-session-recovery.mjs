import assert from 'node:assert/strict';
import { shouldExpireSession, isTemporaryServiceFailure } from '../src/utils/transportState.js';

const errorFor = (status, url = '/auth/me', token = 'current', headers = null) => ({
  response: { status },
  config: { url, headers: headers || { Authorization: 'Bearer ' + token } },
});

assert.equal(shouldExpireSession(errorFor(401), 'current'), true);
assert.equal(shouldExpireSession(errorFor(401, '/city/?world_id=2'), 'current'), true);
assert.equal(shouldExpireSession(errorFor(403), 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/token'), 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/token?lang=es'), 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/register'), 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/verify-email'), 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/me', 'old'), 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/me', 'old'), null), false);
assert.equal(shouldExpireSession({ response: { status: 401 } }, 'current'), false);
assert.equal(shouldExpireSession({ config: { url: '/auth/me' } }, 'current'), false);
assert.equal(shouldExpireSession(errorFor(401, '/auth/me', 'current', { get: (key) => key === 'Authorization' ? 'Bearer current' : null }), 'current'), true);
for (const status of [502, 503, 504]) assert.equal(isTemporaryServiceFailure(errorFor(status)), true);
for (const status of [400, 401, 403, 404, 500]) assert.equal(isTemporaryServiceFailure(errorFor(status)), false);
assert.equal(isTemporaryServiceFailure(new Error('Network Error')), false);
console.log('BM-0084 session recovery contract passed: active/stale credentials, public auth routes, transient service responses');
