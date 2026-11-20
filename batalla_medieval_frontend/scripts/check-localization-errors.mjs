import assert from 'node:assert/strict';
import { localizeApiErrorDetail, localizeAxiosError } from '../src/utils/apiError.js';

const generic = 'No se pudo completar la operación.';
assert.equal(localizeApiErrorDetail('Incorrect username or password'), 'Usuario o contraseña incorrectos.');
assert.equal(localizeApiErrorDetail('Email not verified'), 'Debes verificar tu correo electrónico antes de iniciar sesión.');
assert.equal(localizeApiErrorDetail('User already exists'), 'Ya existe una cuenta con esos datos.');
assert.equal(localizeApiErrorDetail('Verification email could not be delivered'), 'No se pudo enviar el correo de verificación. Inténtalo de nuevo más tarde.');
assert.equal(localizeApiErrorDetail('Invalid or expired verification token'), 'El enlace de verificación no es válido o ha expirado.');
assert.equal(localizeApiErrorDetail('Account frozen'), 'Cuenta suspendida. Contacta con soporte.');
assert.equal(localizeApiErrorDetail('Account frozen: Contact an admin'), 'Cuenta suspendida. Contacta con soporte para conocer el motivo.');
assert.equal(localizeApiErrorDetail('Account frozen: No cumplió las reglas'), 'Cuenta suspendida. Motivo: No cumplió las reglas.');
assert.equal(localizeApiErrorDetail('Account frozen: Automated violation'), 'Cuenta suspendida. Contacta con soporte para conocer el motivo.');
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
