# Registro de activos — Batallas Medievales

Este archivo es la fuente de trazabilidad para recursos visuales y de audio aprobados para producción.

| Activo | Tipo | Origen | Licencia / propiedad | Uso | Estado |
|---|---|---|---|---|---|
| `src/components/GameIcon.jsx` | Vector SVG inline | Creado específicamente dentro del proyecto BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Iconografía de navegación, recursos, mapa y UI del juego | Aprobado |
| Fondos y texturas definidos en `src/index.css` | CSS generado | Creado dentro del proyecto | Obra propia del titular del repositorio | Fondo y superficies medievales sin solicitudes externas | Aprobado |
| `src/assets/intro/castle-silhouette.svg` | SVG | Redibujado específicamente dentro de BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Introducción / autenticación | Aprobado |
| `src/services/sound.js` | Web Audio procedural | Sintetizado en tiempo real por código creado en BM-0082 | Obra propia del titular del repositorio; no usa muestras externas | Música ambiental y efectos UI/eventos | Aprobado |

## Reglas

- Todo activo visual o de audio nuevo debe añadirse a esta tabla en el mismo PR que lo incorpora.
- No se aceptan imágenes, fuentes, texturas o audio descargados en runtime desde dominios externos como parte de la experiencia final.
- Si no puede demostrarse procedencia/licencia de un activo preexistente, debe reemplazarse antes de marcar su hito como terminado.
- Los iconos SVG inline de `GameIcon.jsx` son decorativos; el texto accesible pertenece al control o etiqueta que los acompaña.
- `npm run lint:visual-assets` impide reintroducir iconografía emoji provisional o dependencias visuales remotas conocidas.
