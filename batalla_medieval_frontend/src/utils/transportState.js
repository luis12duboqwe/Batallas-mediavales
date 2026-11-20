export const SESSION_EXPIRED_EVENT = 'bm:session-expired';
export const SERVICE_UNAVAILABLE_EVENT = 'bm:service-unavailable';
export const SERVICE_RECOVERED_EVENT = 'bm:service-recovered';

const AUTH_ENTRY_PATH = /\/auth\/(?:token|register|verify-email|forgot-password|reset-password|request-password-reset)(?:\/|$)/;

export const shouldExpireSession = (error, currentToken) => {
  if (error?.response?.status !== 401 || !currentToken) return false;
  const config = error.config;
  if (!config) return false;
  const path = String(config.url || '').split('?')[0];
  if (AUTH_ENTRY_PATH.test(path)) return false;
  const headers = config.headers;
  const authorization = typeof headers?.get === 'function'
    ? headers.get('Authorization')
    : headers?.Authorization ?? headers?.authorization;
  // A delayed 401 from a previous login must not invalidate a newer session.
  return authorization === 'Bearer ' + currentToken;
};

export const isTemporaryServiceFailure = (error) =>
  [502, 503, 504].includes(error?.response?.status);
