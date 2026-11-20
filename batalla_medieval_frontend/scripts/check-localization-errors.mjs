import assert from 'node:assert/strict';
import { localizeApiErrorDetail, localizeAxiosError } from '../src/utils/apiError.js';

const generic = 'No se pudo completar la operación.';
assert.equal(localizeApiErrorDetail('Incorrect username or password'), 'Usuario o contraseña incorrectos.');
assert.equal(localizeApiErrorDetail('No active world'), generic);
assert.equal(localizeApiErrorDetail('Unknown server failure'), generic);
assert.equal(localizeApiErrorDetail([{ msg: 'invalid value' }]), generic);
assert.equal(localizeApiErrorDetail(null), generic);
assert.equal(localizeApiErrorDetail('No tienes recursos suficientes.'), 'No tienes recursos suficientes.');

const error = { response: { status: 401, data: { detail: 'Incorrect username or password', trace_id: 'trace-1' } } };
assert.strictEqual(localizeAxiosError(error), error);
assert.equal(error.bmOriginalDetail, 'Incorrect username or password');
assert.equal(error.response.data.detail, 'Usuario o contraseña incorrectos.');
assert.equal(error.response.data.trace_id, 'trace-1');
assert.equal(error.response.status, 401);
assert.equal(localizeAxiosError(new Error('Network Error')).message, 'Network Error');

console.log('BM-0083 API error localization passed');
