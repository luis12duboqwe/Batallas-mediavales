# BM-0082 — Sonido, música, animaciones y rendimiento

## Alcance

Cerrar el hito P2/L del Plan Maestro: controles de audio, reducción de movimiento, carga diferida y presupuesto de rendimiento con evidencia reproducible.

## Hallazgos de auditoría

1. Existían siete MP3 versionados sin procedencia/licencia demostrable; `docs/ASSET_LICENSES.md` los marcaba expresamente como no aprobados.
2. La música intentaba reproducirse por ruta y los SFX usaban archivos binarios; el navegador podía bloquear autoplay y el runtime dependía de activos no certificados.
3. No existía manejo de `prefers-reduced-motion`; la intro usa Canvas/requestAnimationFrame durante 2.5 s y la pantalla de carga simula progreso mediante timers.
4. Todas las páginas se importaban estáticamente desde `App.jsx`; el bundle principal anterior rondaba 685 KiB minificado.
5. No existía un presupuesto automático de tamaño de JavaScript.

## Implementación

- Audio sustituido por Web Audio procedural creado dentro del proyecto; no requiere muestras ni solicitudes de audio externas.
- Música desactivada por defecto para jugadores nuevos y activada únicamente mediante interacción del usuario; preferencias existentes continúan persistidas.
- Intro y loading se omiten cuando el sistema solicita reducción de movimiento; CSS reduce animaciones/transiciones globales.
- Rutas y paneles pesados usan `React.lazy` + `Suspense`.
- `npm run build` ejecuta `check-build-budget.mjs` y falla si el JS inicial supera 500 KiB o cualquier chunk supera 400 KiB.
- G22 se ejecuta desde G20 y valida reduced-motion, toggle de música, ausencia de descargas MP3/WAV/OGG/M4A/AAC y carga diferida de `/map`.
- `ASSET_LICENSES.md` registra el sistema de audio procedural como activo propio aprobado y elimina la dependencia de los MP3 no trazables.

## Evidencia inicial

Validation #820 sobre `6094d50ac4a436a3ee673533b6535ccec916312f` confirmó que lint y build pasan con lazy-loading:

- JS inicial: **382.4 KiB** (límite 500 KiB).
- chunk mayor: **322.4 KiB** (límite 400 KiB).
- 31 chunks JavaScript.

## Criterio de cierre

- Frontend lint/build + presupuesto verdes.
- G2–G20 continúan sin regresión y G22 pasa en navegador.
- G21 sigue verde.
- Dependencias/seguridad, backend, concurrencia, G5 e imágenes Docker verdes sobre el HEAD exacto.
- Sin activos de audio no trazables ni solicitudes binarias de audio en runtime.
- Revisión adversarial final sin P1/P2 abiertos.
- Merge a `main` y Validation post-merge verde.
