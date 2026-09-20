# Registro de activos — Batallas Medievales

Este archivo es la fuente de trazabilidad para recursos visuales. No implica que los activos de audio estén aprobados; BM-0082 mantiene esa responsabilidad.

| Activo | Tipo | Origen | Licencia / propiedad | Uso | Estado |
|---|---|---|---|---|---|
| `src/components/GameIcon.jsx` | Vector SVG inline | Creado específicamente dentro del proyecto BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Iconografía de navegación, recursos, mapa y UI del juego | Aprobado |
| Fondos y texturas definidos en `src/index.css` | CSS generado | Creado dentro del proyecto | Obra propia del titular del repositorio | Fondo y superficies medievales sin solicitudes externas | Aprobado |
| `src/assets/intro/castle-silhouette.svg` | SVG | Redibujado específicamente dentro de BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Introducción / autenticación | Aprobado |
| `src/assets/sounds/*.mp3` | Audio | Activos preexistentes | Auditoría de procedencia pendiente BM-0082 | Música y SFX | Fuera del cierre BM-0080; no aprobado aquí |

## Reglas

- Un activo visual nuevo debe añadirse a esta tabla en el mismo PR que lo incorpora.
- No se aceptan imágenes, fuentes o texturas descargadas en runtime desde dominios externos como parte de la UI final.
- Si no puede demostrarse procedencia/licencia de un activo visual preexistente, debe reemplazarse antes de marcar BM-0080 como terminado.
- Los iconos SVG inline de `GameIcon.jsx` son decorativos; el texto accesible pertenece al control o etiqueta que los acompaña.
- `npm run lint:visual-assets` impide reintroducir iconografía emoji provisional o dependencias visuales remotas conocidas.
