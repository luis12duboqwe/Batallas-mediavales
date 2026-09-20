# BM-0080 — Sistema visual y arte final

Estado: activo  
Rama: `feature/BM-0080-visual-system-final-art`  
Base certificada: `479d2cf8b5f917ec0c17dd2a91cda95f869f290c` (BM-0075)

## Contrato de aceptación

BM-0080 se considera terminado cuando la interfaz visible deja de depender de recursos provisionales y cada activo visual tiene origen, licencia/propiedad y uso documentados. Este hito no absorbe BM-0081–BM-0085: accesibilidad avanzada, sonido/animación, localización final, resiliencia UX y presupuestos de rendimiento conservan sus propios gates.

## Hallazgos iniciales

1. Navegación, mapa, ciudad, edificios, tropas y movimientos usan emoji como iconografía de producción.
2. `src/assets/icons/` no contiene un catálogo final; solo conserva placeholders `.gitkeep`.
3. `index.css` solicita Google Fonts y una textura de `transparenttextures.com` en runtime.
4. No existe un registro de procedencia/licencias de activos visuales.
5. `castle-silhouette.svg` existe como activo local previo, pero necesita trazabilidad explícita antes del cierre.
6. Los archivos de sonido se auditarán y cerrarán en BM-0082; BM-0080 solo registra esa frontera para no fingir una licencia no verificada.

## Estrategia

- Introducir un sistema único de iconos vectoriales locales, sin dependencias externas y con trazos coherentes.
- Sustituir emojis visibles por `GameIcon` empezando por navegación y flujos críticos, luego barrer el resto del frontend.
- Eliminar fuentes/texturas remotas del runtime; usar tipografías del sistema y texturas CSS hasta que exista un activo local con procedencia comprobable.
- Mantener un inventario `ASSET_LICENSES.md` que distinga activos propios, activos terceros aprobados y activos todavía provisionales.
- Añadir un gate automatizado que detecte URLs de medios remotos y emojis de UI prohibidos antes de cerrar BM-0080.
- Validar lint/build, E2E existente y una comprobación visual dedicada antes del merge.

## Secuencia de trabajo

1. Fundación visual: iconos propios, tokens y eliminación de dependencias remotas.
2. Navegación/recursos/ciudad/mapa/tarjetas de edificios, tropas y movimientos.
3. Barrido de pantallas restantes y recursos provisionales.
4. Registro final de activos y gate automático de trazabilidad.
5. E2E/QA visual, revisión adversarial, CI completo, merge y certificación en `main`.
