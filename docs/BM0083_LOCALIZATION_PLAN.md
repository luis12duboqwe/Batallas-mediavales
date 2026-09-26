# BM-0083 — Localización final

## Objetivo

Cumplir el criterio de salida de BM-0083: español completo en producción y, si inglés no está completo, retirarlo sin dejar rutas, selectores o preferencias históricas capaces de reactivarlo.

## Decisión de producto para v1.0

Batallas Medievales v1.0 se publica únicamente en español.

El catálogo inglés existente era parcial y no cumplía el criterio de localización final. En lugar de publicar una experiencia mixta, BM-0083 retira inglés del runtime de producción. Una futura localización adicional deberá volver a incorporarse como un paquete completo, probado y explícitamente habilitado.

## Contrato técnico

- `i18n` usa `es` como idioma, fallback y único `supportedLngs`.
- No se registra `LanguageDetector` ni un catálogo inglés.
- Preferencias antiguas de navegador/localStorage no pueden cambiar el idioma activo.
- El valor histórico `user.language` del backend no puede cambiar el idioma del cliente.
- El perfil no expone un selector de idioma ni envía cambios de idioma.
- `index.html` declara `lang="es"`.
- Las claves estáticas `t('...')` usadas por el frontend deben existir en `es.json`.
- Texto visible conocido que pertenecía al runtime inglés no puede reaparecer.

## Gates

### Estático

`npm run lint:localization` ejecuta `scripts/check-localization.mjs` y falla si:

- reaparece `src/locales/en.json`;
- i18n deja de estar fijado a español;
- reaparece detección/cambio dinámico de idioma;
- el perfil vuelve a exponer selección de idioma;
- el documento deja de declarar español;
- una clave estática `t()` no existe en `es.json`;
- reaparecen marcadores conocidos de UI inglesa retirada.

El script forma parte de `npm run lint`, por lo que es bloqueante en el job Frontend de Validation.

### Runtime

G23 (`e2e/g23-localization.mjs`) valida en navegador que:

- una preferencia histórica `i18nextLng=en` no reactiva inglés;
- login y sesión autenticada siguen en español tras carga dura;
- el perfil muestra español como idioma de esta versión y no expone selector/English;
- una segunda preferencia inglesa inyectada después del login tampoco cambia el runtime;
- mensajería permanece en español;
- no aparecen marcadores críticos de la antigua UI inglesa.

G23 se ejecuta después de G22 en el runner aislado de accesibilidad/media y bloquea `Container images` si falla.

## Alcance

BM-0083 no elimina necesariamente campos históricos de idioma del esquema/backend. Retirarlos sería una migración destructiva sin beneficio para el contrato de v1.0. El requisito es que dichos datos no controlen ni expongan un locale no soportado en el cliente.

## Definición de terminado

- gate estático verde;
- G23 verde;
- lint/build y suites E2E existentes sin regresiones;
- backend, PostgreSQL concurrency, seguridad, G5 e imágenes Docker verdes sobre el HEAD exacto;
- revisión adversarial sin P1/P2 pendientes;
- merge con SHA esperado y Validation de `main` verde.
