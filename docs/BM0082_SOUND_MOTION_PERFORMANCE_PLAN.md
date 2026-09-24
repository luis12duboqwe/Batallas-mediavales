# BM-0082 — Sonido, música y animaciones

Estado: implementación activa.

Base certificada: `main` `ef80c002218c308293f014a2f933cfc881a0887d` (BM-0081 fusionado; Validation post-merge #807 completamente verde).

## Criterio de aceptación

Los controles de sonido, la reducción de movimiento, la carga diferida y un presupuesto explícito de rendimiento deben pasar QA sin introducir activos sin trazabilidad ni depender de autoplay no permitido por el navegador.

## Hallazgos iniciales

1. Música y SFX existen y sus preferencias ya se persisten, pero la UI solo permite encender/apagar; no expone volumen.
2. `playMusic()` intenta reproducir al cambiar de ruta. Si el navegador bloquea autoplay, el rechazo se silencia y no existe una reanudación robusta tras el primer gesto del usuario.
3. Los objetos `Audio` se crean al solicitar reproducción y no existe contrato explícito de `preload=none`, desbloqueo ni caché controlada.
4. No existe tratamiento de `prefers-reduced-motion`; la intro ejecuta canvas/RAF durante 2.5 s y el CSS mantiene animaciones/transiciones.
5. No existe gate de presupuesto para JS/CSS/audio ni una prueba E2E dedicada a sonido/reduced-motion.
6. `docs/ASSET_LICENSES.md` declara correctamente `src/assets/sounds/*.mp3` como no aprobados. El historial solo demuestra que eran activos preexistentes; no demuestra licencia ni procedencia.

## Estrategia

- sustituir los MP3 sin procedencia por audio original generado específicamente para BM-0082 y registrar su trazabilidad;
- mantener música y SFX separados, con preferencias persistentes, volúmenes accesibles y estados observables;
- no crear/reproducir audio hasta que exista intención del usuario; instalar un desbloqueo por gesto y reintentar música pendiente sin esconder errores funcionales;
- reutilizar/cerrar correctamente instancias de música y crear SFX bajo demanda con `preload=none`;
- respetar `prefers-reduced-motion` tanto en la intro canvas como en animaciones/transiciones CSS;
- añadir G22 para reduced-motion, controles persistentes y comportamiento de carga de audio;
- añadir un gate de rendimiento que falle si los assets o bundles superan límites documentados.

## Presupuesto inicial

- música individual: <= 256 KiB;
- SFX individual: <= 64 KiB;
- audio total: <= 768 KiB;
- JS inicial minificado (archivo principal mayor): <= 800 KiB;
- CSS inicial minificado (archivo principal mayor): <= 100 KiB.

Los límites son de CI, no objetivos de optimización final. Si el build supera uno, se corrige la causa o se modifica el presupuesto con evidencia, nunca se silencia el gate.

## QA

- lint/build + gates visuales/accesibles existentes;
- gate de rendimiento post-build;
- G22 en Chromium con `prefers-reduced-motion: reduce` y viewport móvil/escritorio según corresponda;
- regresión de persistencia de mute/volumen;
- verificación de que no se solicita audio antes de una interacción del usuario;
- verificación de que la música pendiente puede iniciar después del gesto y que deshabilitarla la detiene;
- suite completa y Docker antes de merge.
