const KNOWN_ERROR_TRANSLATIONS = new Map([
  ['incorrect username or password', 'Usuario o contraseña incorrectos.'],
  ['could not validate credentials', 'La sesión no es válida. Vuelve a iniciar sesión.'],
  ['not authenticated', 'Debes iniciar sesión para continuar.'],
  ['inactive user', 'La cuenta está inactiva.'],
  ['user not found', 'No se encontró el usuario.'],
  ['email already registered', 'El correo electrónico ya está registrado.'],
  ['username already registered', 'El nombre de usuario ya está registrado.'],
  ['invalid or expired token', 'El enlace no es válido o ha expirado.'],
  ['invalid token', 'El enlace no es válido o ha expirado.'],
  ['forbidden', 'No tienes permiso para realizar esta acción.'],
  ['not found', 'No se encontró el recurso solicitado.'],
  ['world not found', 'No se encontró el mundo solicitado.'],
  ['city not found', 'No se encontró la ciudad solicitada.'],
  ['alliance not found', 'No se encontró la alianza solicitada.'],
  ['insufficient resources', 'No tienes recursos suficientes.'],
  ['not enough resources', 'No tienes recursos suficientes.'],
]);

const SPANISH_SIGNAL = /[áéíóúüñ¿¡]|\b(?:no|se|puede|pudo|debes|debe|tienes|usuario|contraseña|cuenta|correo|ciudad|mundo|alianza|recursos|permiso|sesión|acción|solicitad[oa]|encontró|válid[oa]|expirado)\b/i;
const ENGLISH_SIGNAL = /\b(?:a|an|the|is|are|was|were|not|invalid|incorrect|could|cannot|can't|must|user|username|password|email|account|world|city|alliance|resource|resources|forbidden|found|expired|token|credentials|already|registered|enough|permission|required|failed|error)\b/i;

const extractDetailText = (detail) => {
  if (typeof detail === 'string') return detail.trim();
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message.trim();
  }
  return '';
};

export const localizeApiErrorDetail = (detail) => {
  const text = extractDetailText(detail);
  if (!text) return 'No se pudo completar la operación.';

  const translated = KNOWN_ERROR_TRANSLATIONS.get(text.toLowerCase());
  if (translated) return translated;

  if (SPANISH_SIGNAL.test(text)) return text;
  if (ENGLISH_SIGNAL.test(text)) return 'No se pudo completar la operación.';

  // Neutral identifiers/codes are not useful as player-facing copy. Keep the
  // v1.0 UI deterministic and Spanish instead of leaking an unknown contract.
  return 'No se pudo completar la operación.';
};

export const localizeAxiosError = (error) => {
  const data = error?.response?.data;
  if (!data || !Object.prototype.hasOwnProperty.call(data, 'detail')) return error;

  const originalDetail = data.detail;
  const localizedDetail = localizeApiErrorDetail(originalDetail);

  // Clone the response/data seen by UI consumers. Successful responses and
  // the backend JSON contract are untouched; the original detail remains
  // available on the error for diagnostics without being rendered to players.
  error.bmOriginalDetail = originalDetail;
  error.response = {
    ...error.response,
    data: {
      ...data,
      detail: localizedDetail,
    },
  };
  return error;
};
