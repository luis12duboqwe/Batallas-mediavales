# BM-0083 — Localización final

## Decisión de producto

La auditoría del frontend encontró que inglés solo cubría el catálogo parcial de `src/locales/en.json`, mientras varias pantallas finales seguían conteniendo texto visible y nombres accesibles directamente en español. Mantener el selector inglés habría publicado una experiencia mixta e incumplido el criterio de BM-0083.

Para v1.0 se adopta **español como único idioma de producción**. El archivo inglés puede permanecer en el repositorio como material de trabajo futuro, pero no se importa, no se anuncia como soportado y no puede seleccionarse desde UI/API.

## Contrato

- `es` es el único idioma retornado por `available_languages()`.
- preferencias legacy como `en`, `en-US` u otro idioma se normalizan a `es` para conservar compatibilidad con clientes y cuentas antiguas;
- la migración `0018_spanish_only_language` normaliza usuarios persistidos;
- frontend arranca y cae siempre a `es`, sin detector de navegador ni import de `en.json`;
- Perfil muestra español como estado informativo y no ofrece selector de idioma;
- G4 prueba que una preferencia legacy de navegador en inglés no cambia la UI y que el estado español sobrevive a recarga;
- `check-localization-policy.mjs` evita reintroducir inglés accidentalmente en el runtime.

## Evidencia de cierre requerida

- migraciones upgrade/downgrade válidas;
- tests backend y prueba focalizada BM-0083 verdes;
- gate de localización, lint y build frontend verdes;
- Browser E2E completo, incluido G4 actualizado;
- seguridad, concurrencia, imágenes Docker y revisión final del HEAD exacto verdes antes del merge.
