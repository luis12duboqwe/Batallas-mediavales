# Registro de activos — Batallas Medievales

Este archivo es la fuente de trazabilidad de recursos visuales y sonoros incluidos en producción.

| Activo | Tipo | Origen | Licencia / propiedad | Uso | Estado |
|---|---|---|---|---|---|
| `src/components/GameIcon.jsx` | Vector SVG inline | Creado específicamente dentro del proyecto BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Iconografía de navegación, recursos, mapa y UI del juego | Aprobado |
| Fondos y texturas definidos en `src/index.css` | CSS generado | Creado dentro del proyecto | Obra propia del titular del repositorio | Fondo y superficies medievales sin solicitudes externas | Aprobado |
| `src/assets/intro/castle-silhouette.svg` | SVG | Redibujado específicamente dentro de BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Introducción / autenticación | Aprobado |
| Patrones procedurales en `src/services/sound.js` | Web Audio generado en runtime | Compuestos específicamente dentro de BM-0082 con osciladores y envolventes propias | Obra propia del titular del repositorio; sin activo binario o licencia externa | Música ambiental y SFX | Aprobado |

## Reglas

- Todo activo nuevo debe añadirse a esta tabla en el mismo PR que lo incorpora.
- No se aceptan imágenes, fuentes, texturas o sonidos descargados en runtime desde dominios externos como parte de la experiencia final.
- Si no puede demostrarse procedencia/licencia de un activo preexistente, debe reemplazarse antes de certificar su hito.
- Los iconos SVG inline de `GameIcon.jsx` son decorativos; el texto accesible pertenece al control o etiqueta que los acompaña.
- `npm run lint:visual-assets` impide reintroducir iconografía emoji provisional o dependencias visuales remotas conocidas.
- BM-0082 retiró los MP3 preexistentes sin procedencia demostrable; el build final debe contener 0 bytes de audio binario y `npm run check:performance` lo hace cumplir.
