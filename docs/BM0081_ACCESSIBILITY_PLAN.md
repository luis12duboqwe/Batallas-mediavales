# BM-0081 — Adaptabilidad y accesibilidad

Estado: implementación completa; pendiente certificación exacta de CI, revisión y merge.

Base certificada: `main` en `3bccf0d13ff09b7751be3751f7684c5783e99ee9` (BM-0080 fusionado; Validation post-merge #779 completamente verde).

## Criterio de aceptación

Los flujos críticos deben funcionar en móvil y escritorio, con teclado y con semántica suficiente para tecnologías de asistencia.

## Hallazgos iniciales

1. No existía enlace para saltar navegación ni destino de foco del contenido principal.
2. Varias superficies interactivas usaban `div` con `onClick`: mapa, mensajes, foro, selector de mundo y reportes.
3. Algunos formularios dependían de `placeholder` o etiquetas visuales no asociadas.
4. Capas modales (ciudad, invitaciones, resultado de aventura) requerían semántica de diálogo, Escape y manejo de foco.
5. G4 cubría móvil y un enlace por teclado, pero no existía un gate específico de accesibilidad/desktop para rutas críticas.
6. Los tablists de Mensajes y Alianza necesitaban roving focus y navegación Arrow/Home/End para que los roles ARIA fueran completos.
7. La navegación HTTP directa entre rutas protegidas hacía G21 susceptible a carreras ajenas al comportamiento SPA real.

## Implementado

- Landmarks, skip-link localizado, foco tras navegación SPA y foco visible consistente.
- Controles click-only reemplazados por elementos nativos; gate estático permanente contra `div`/`span`/`li` con `onClick`.
- Etiquetas asociadas y estados ARIA relevantes en formularios, mapa, mensajes, reportes y selector de mundo.
- Diálogos con `role=dialog`, `aria-modal`, título accesible, foco inicial, trampa Tab/Shift+Tab, Escape y restauración del foco.
- Tablists de Mensajes y Alianza con roving `tabIndex`, ArrowLeft/Right/Up/Down y Home/End.
- Adaptación móvil reforzada en Alianza y Mapa; el panel de detalles del mapa se apila y permanece dentro del viewport móvil.
- G21 navega por los enlaces SPA reales y valida móvil/escritorio, skip-link, foco de ruta, mapa por teclado, tabs, reportes, diálogos y overflow horizontal.
- Eliminado `aria-live` del historial de chat que se refresca periódicamente para evitar anuncios repetitivos innecesarios.
- Revisión adversarial de controles hermanos y regresiones de layout incorporada antes del cierre.

BM-0082 conserva como alcance separado reducción de movimiento, sonido, animaciones y carga diferida.
