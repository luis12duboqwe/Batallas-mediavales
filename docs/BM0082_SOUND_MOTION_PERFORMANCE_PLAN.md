# BM-0082 — Sonido, música y animaciones

Estado: implementación activa.

Base certificada: `main` `ef80c002218c308293f014a2f933cfc881a0887d` (BM-0081 fusionado; Validation post-merge #807 completamente verde).

## Criterio de aceptación

Los controles de sonido, la reducción de movimiento, la carga diferida y un presupuesto explícito de rendimiento deben pasar QA sin introducir activos sin trazabilidad ni depender de autoplay no permitido por el navegador.

## Hallazgos iniciales

1. Música y SFX existían y sus preferencias se persistían, pero la UI solo permitía encender/apagar y los MP3 no tenían procedencia demostrable.
2. `playMusic()` intentaba reproducir al cambiar de ruta y silenciaba el rechazo de autoplay.
3. No existía tratamiento de `prefers-reduced-motion`; intro y loading mantenían animaciones temporizadas.
4. Todas las páginas entraban en el bundle inicial mediante imports estáticos.
5. No existía gate de presupuesto para JS/CSS/audio ni prueba E2E dedicada a sonido/reduced-motion.

## Estrategia implementada

- retirar los siete MP3 sin procedencia y sustituirlos por música/SFX procedurales Web Audio originales del proyecto;
- no crear ni iniciar síntesis hasta un gesto real; la ruta solo deja preparada la música pendiente;
- mantener preferencias persistentes, toggles y controles accesibles de volumen;
- respetar `prefers-reduced-motion` en intro, loading y CSS global;
- cargar las páginas con `React.lazy`/`Suspense` para sacar vistas completas del entry chunk;
- añadir G22 para reduced-motion, persistencia de audio, ausencia de audio binario y detención efectiva de música;
- añadir un gate post-build de rendimiento.

## Presupuesto de CI

- entry JS minificado: <= 500 KiB;
- cualquier chunk JS minificado: <= 500 KiB;
- cada CSS generado: <= 120 KiB;
- audio binario en `dist`: 0 bytes (la experiencia final usa síntesis procedural).

Los límites son puertas de CI. Si se superan, se corrige la causa o se modifica el presupuesto con evidencia; no se silencia el gate.

## QA pendiente

- lint/build + gates visuales/accesibles existentes;
- `npm run check:performance` post-build;
- G22 en Chromium con `prefers-reduced-motion: reduce`;
- G2–G21 completos;
- auditoría de dependencias, concurrencia, G5 y Docker;
- revisión adversarial antes de merge.
