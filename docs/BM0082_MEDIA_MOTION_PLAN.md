# BM-0082 — Sonido, música y animaciones

## Objetivo
Cerrar sonido, música y movimiento sin introducir licencias dudosas, autoplay frágil ni regresiones de rendimiento o accesibilidad.

## Auditoría de entrada
- Los siete MP3 existentes no tenían procedencia/licencia demostrada y `ASSET_LICENSES.md` los marcaba pendientes.
- La música intentaba reproducirse al montar/cambiar ruta, antes de una interacción válida del usuario.
- Los setters de volumen existían en el servicio, pero la UI solo exponía encendido/apagado.
- Intro y pantalla de carga ignoraban `prefers-reduced-motion`; el CSS global tampoco ofrecía reducción de movimiento.
- Línea base de build en `main` `ef80c002`: JS 685.34 kB, CSS 63.95 kB y ~175 kB de audio MP3.

## Decisiones
1. Sustituir grabaciones por síntesis procedural con Web Audio API. No quedan binarios de audio ni solicitudes de medios.
2. Crear/reanudar `AudioContext` únicamente tras `pointerdown` o `keydown`; las rutas solo declaran la música deseada antes de esa activación.
3. Mantener controles independientes de música/SFX y exponer volumen persistente para ambos.
4. Respetar `prefers-reduced-motion` tanto en CSS como en las secuencias JavaScript de intro/carga; si la preferencia cambia en vivo, se detiene la secuencia animada.
5. Mantener el alcance de rendimiento de BM-0082 como presupuesto anti-regresión: cero audio binario, chunk JS máximo 700 kB y CSS máximo 70 kB. El code-splitting estructural corresponde a BM-0085.
6. Añadir G22 para probar movimiento reducido, activación diferida de Web Audio y persistencia de controles.

## Criterio de cierre
- ninguna extensión de audio binario en `src/assets` ni `dist`;
- audio no crea contexto antes de una interacción del usuario y reutiliza un único contexto después;
- volumen/toggles sobreviven a recarga;
- intro/carga no fuerzan animaciones cuando el SO solicita movimiento reducido;
- presupuesto de build pasa en CI;
- G22 y toda Validation quedan verdes en el HEAD exacto.
