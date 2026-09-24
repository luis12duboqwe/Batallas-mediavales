# Registro de activos — Batallas Medievales

Este archivo es la fuente de trazabilidad de los recursos visuales y de audio que forman parte del cliente final.

| Activo | Tipo | Origen | Licencia / propiedad | Uso | Estado |
|---|---|---|---|---|---|
| `src/components/GameIcon.jsx` | Vector SVG inline | Creado específicamente dentro del proyecto BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Iconografía de navegación, recursos, mapa y UI del juego | Aprobado |
| Fondos y texturas definidos en `src/index.css` | CSS generado | Creado dentro del proyecto | Obra propia del titular del repositorio | Fondo y superficies medievales sin solicitudes externas | Aprobado |
| `src/assets/intro/castle-silhouette.svg` | SVG | Redibujado específicamente dentro de BM-0080 | Obra propia del titular del repositorio; sin licencia externa requerida | Introducción / autenticación | Aprobado |
| `src/services/sound.js` | Audio procedural Web Audio | Síntesis implementada dentro de BM-0082; no usa grabaciones ni archivos musicales externos | Código y composición procedural propios del proyecto; sin activo binario externo | Música ambiental y efectos de interfaz/notificaciones | Aprobado |

## Reglas

- Un activo visual o sonoro nuevo debe añadirse a esta tabla en el mismo PR que lo incorpora.
- No se aceptan imágenes, fuentes, texturas o audio descargados en runtime desde dominios externos como parte de la UI final.
- No se aceptan binarios de audio sin procedencia y licencia demostrables; BM-0082 elimina los MP3 preexistentes cuya procedencia no estaba documentada.
- Los iconos SVG inline de `GameIcon.jsx` son decorativos; el texto accesible pertenece al control o etiqueta que los acompaña.
- `npm run lint:visual-assets` impide reintroducir iconografía emoji provisional o dependencias visuales remotas conocidas.
- El gate de presupuesto de BM-0082 impide reintroducir binarios de audio y controla el tamaño máximo de los bundles generados.
