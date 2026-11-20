import assert from 'node:assert/strict';
import { readMapTilesResponse, readMessageListResponse, readReportListResponse } from '../src/utils/collectionResponse.js';

assert.deepEqual(readMapTilesResponse({ tiles: [{x: 1, y: 2}] }), [{x: 1, y: 2}]);
assert.deepEqual(readMapTilesResponse({ tiles: [] }), []);
assert.deepEqual(readMessageListResponse([{ id: 1 }]), [{ id: 1 }]);
assert.deepEqual(readMessageListResponse({ messages: [{ id: 2 }] }), [{ id: 2 }]);
assert.deepEqual(readMessageListResponse({ messages: [] }), []);
assert.deepEqual(readReportListResponse([{ id: 3 }]), [{ id: 3 }]);
assert.deepEqual(readReportListResponse({ reports: [{ id: 4 }] }), [{ id: 4 }]);
assert.deepEqual(readReportListResponse({ reports: [] }), []);
for (const invalid of [null, undefined, {}, '<html>maintenance</html>', { detail: 'Service unavailable' }, { tiles: 'none' }, { tiles: {} }]) {
  assert.throws(() => readMapTilesResponse(invalid), /mapa es inválida/);
}
for (const invalid of [null, undefined, {}, '<html>maintenance</html>', { detail: 'Maintenance' }, { messages: 'none' }, { messages: {} }]) {
  assert.throws(() => readMessageListResponse(invalid), /mensajería es inválida/);
}
for (const invalid of [null, undefined, {}, '<html>maintenance</html>', { detail: 'Maintenance' }, { reports: 'none' }, { reports: {} }]) {
  assert.throws(() => readReportListResponse(invalid), /reportes es inválida/);
}
console.log('BM-0084 collection contracts passed: valid lists, empty lists and malformed JSON/HTML');
