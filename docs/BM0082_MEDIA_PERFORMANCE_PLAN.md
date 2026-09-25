# BM-0082 — Sonido, música, animaciones y rendimiento

## Alcance

Cerrar el hito P2/L del Plan Maestro: controles de audio, reducción de movimiento, carga diferida y presupuesto de rendimiento con evidencia reproducible.

## Hallazgos de auditoría

1. Existían siete MP3 versionados sin procedencia/licencia demostrable; `docs/ASSET_LICENSES.md` los marcaba expresamente como no aprobados.
2. La música intentaba reproducirse por ruta y los SFX usaban archivos binarios; el navegador podía bloquear autoplay y el runtime dependía de activos no certificados.
3. No existía manejo de `prefers-reduced-motion`; la intro usa Canvas/requestAnimationFrame durante 2.5 s y la pantalla de carga simula progreso mediante timers.
4. Todas las páginas se importaban estáticamente desde `App.jsx`; el bundle principal anterior rondaba 685 KiB minificado.
5. No existía un presupuesto automático de tamaño de JavaScript ni recuperación ante un chunk lazy obsoleto después de un despliegue.
6. Las preferencias de audio corruptas podían contaminar tipos/volúmenes y apagar/cambiar música no garantizaba detener inmediatamente las voces ya programadas.

## Implementación

- Audio sustituido por Web Audio procedural creado dentro del proyecto; no requiere muestras ni solicitudes de audio externas.
- Música opt-in para jugadores nuevos; SFX y audio context solo se activan después de un gesto real del usuario.
- Preferencias persistentes saneadas por tipo/rango; controles incluyen toggles y volúmenes de música/SFX.
- Cambio/apagado de música detiene voces activas; logout/desactivación suspende el `AudioContext` y la siguiente interacción puede reanudarlo.
- Intro y loading se omiten cuando el sistema solicita reducción de movimiento; CSS reduce animaciones/transiciones globales.
- Rutas pesadas usan `React.lazy` + `Suspense`; fallos de chunk dinámico ejecutan una recarga controlada una sola vez y luego muestran un boundary recuperable en vez de desmontar toda la aplicación.
- `npm run build` ejecuta `check-build-budget.mjs` y falla si el JS inicial supera 500 KiB o cualquier chunk supera 400 KiB.
- `npm run lint:visual-assets` también ejecuta la política de media para `src`, `public` e `index.html` con una lista compartida de formatos binarios de audio.
- `npm run test:sound` prueba de forma determinista normalización, parada de voces, unlock idempotente y suspensión del contexto.
- G22 se ejecuta en el runner G21/G22 y valida reduced-motion, preferencias corruptas, volúmenes/toggles, cero audio binario, carga diferida y recuperación real al fallar una petición de chunk una vez.
- `ASSET_LICENSES.md` registra el sistema de audio procedural como activo propio aprobado y elimina la dependencia de MP3 no trazables.

## Evidencia de rendimiento

Validation #820 sobre `6094d50ac4a436a3ee673533b6535ccec916312f` confirmó el primer baseline con lazy-loading:

- JS inicial: **382.4 KiB** (límite 500 KiB).
- chunk mayor: **322.4 KiB** (límite 400 KiB).
- 31 chunks JavaScript.

Los límites se mantienen como presupuesto de regresión; solo deben modificarse con evidencia de un cambio de arquitectura o de producto, no para hacer pasar CI.

## Criterio de cierre

- Frontend: políticas visual/media/accesibilidad, `test:sound`, lint, build y presupuesto verdes.
- G2–G20 continúan sin regresión; G21 y G22 pasan en navegador.
- Dependencias/seguridad, backend, concurrencia, G5 e imágenes Docker verdes sobre el HEAD exacto.
- Sin activos de audio no trazables ni solicitudes binarias de audio en runtime.
- Lazy chunks recuperan un fallo de despliegue/red controlado sin white-screen.
- Revisión adversarial final sin P1/P2 abiertos.
- Merge a `main` y Validation post-merge verde.
