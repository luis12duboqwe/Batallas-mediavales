# BM-0081 — Adaptabilidad y accesibilidad

Estado: activo

Base: `main` en `3bccf0d13ff09b7751be3751f7684c5783e99ee9` (BM-0080 fusionado; certificación post-merge #779 se verifica antes del cierre).

## Criterio de aceptación

Los flujos críticos deben funcionar en móvil y escritorio, con teclado y con semántica suficiente para tecnologías de asistencia.

## Hallazgos iniciales

1. No existía enlace para saltar navegación ni destino de foco del contenido principal.
2. Varias superficies interactivas usaban `div` con `onClick`: mapa, mensajes, foro, selector de mundo y reportes.
3. Algunos formularios dependían de `placeholder` o etiquetas visuales no asociadas.
4. Capas modales (ciudad, invitaciones, resultado de aventura) requieren semántica de diálogo, Escape y manejo de foco.
5. G4 cubre móvil y un enlace por teclado, pero no existe un gate específico de accesibilidad/desktop para rutas críticas.

## Trabajo

- Landmarks, skip-link, foco tras navegación SPA y foco visible consistente.
- Sustituir controles click-only por controles nativos o semántica/teclado equivalente.
- Asociar etiquetas y estados ARIA cuando aporten información real.
- Corregir diálogos: `role=dialog`, `aria-modal`, título accesible, Escape, foco inicial y restauración.
- Mantener adaptación móvil y añadir comprobación de escritorio sin overflow horizontal.
- Añadir G21: teclado, landmarks/nombres accesibles, controles críticos y viewports móvil/escritorio.
- Revisión adversarial de controles hermanos antes de cierre.

BM-0082 conserva como alcance separado reducción de movimiento, sonido, animaciones y carga diferida.
