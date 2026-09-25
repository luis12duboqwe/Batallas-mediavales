import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import es from './locales/es.json';

// BM-0083 intentionally ships v1.0 in Spanish only. Historical browser,
// localStorage or profile preferences must not reactivate an incomplete locale.
i18n
  .use(initReactI18next)
  .init({
    lng: 'es',
    supportedLngs: ['es'],
    fallbackLng: 'es',
    resources: {
      es: { translation: es },
    },
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
