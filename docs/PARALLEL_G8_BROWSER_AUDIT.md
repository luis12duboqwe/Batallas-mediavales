# Auditoría independiente G8 — navegadores y resiliencia

Trabajo anticipado sobre `86adbd83dedc9a3e4c2d89b3adc247b72184d158`. **No certifica G8 ni sustituye G5**: la certificación y el merge quedan pendientes de G5 y de revisión independiente. El PR debe permanecer en borrador.

## Alcance y antecedentes

Se revisaron `g21-accessibility.mjs` (teclado, diálogo y diseño), `g22-media-performance.mjs` (medios y presupuesto), `g23-localization.mjs` (español), `g24-resilience.mjs` (sesión y conectividad) y `g25-states.mjs` (estados y reintentos), además de `parallel-map-navigation.mjs`, `parallel-map-actions-integration.mjs`, `parallel-adventures-flow.mjs` y `docs/PARALLEL_E2E_REPORT.md`. El PR #222 obliga a esperar la ciudad hidratada y su respuesta real antes de probar el mapa: esta auditoría espera la casilla de la ciudad y `aria-busy=false` antes de cambiar coordenadas. No repite sus respuestas vacías ni pretende volver a certificar G21–G25.

`e2e/parallel-g8-browser.mjs` añade cinco escenarios por motor y viewport, cada uno en un contexto nuevo:

1. Abrir la invitación de alianza con teclado, comprobar foco, ciclo Tab/Shift+Tab, Escape y restauración del foco.
2. Con la ciudad real ya cargada, retener un GET de mapa cuya respuesta procede del backend, pedir otra zona y entregar primero la respuesta más reciente. Comprobar carga, ausencia de falso vacío y que la respuesta antigua no sustituya las casillas reales de la última zona.
3. Provocar 503 solo en GET de bandeja y reportes. Recuperar primero reportes y comprobar que el aviso global sigue por la bandeja; recuperar la bandeja con el backend real y comprobar que desaparece el aviso. No se fabrican respuestas exitosas.
4. Cambiar la red del contexto offline/online, notificar ambos eventos al documento y volver a autenticar contra el backend. Después, cargar una ruta protegida con JWT inválido, comprobar el aviso y la eliminación del token y volver a entrar.
5. Rechazar una única petición de inicio de aventura con 503, comprobar que el fixture G13 real sigue disponible y, tras reintento explícito, verificar la respuesta y el estado persistido del backend. A diferencia de `parallel-adventures-flow.mjs`, que usa filas sintéticas para probar recuperación de lectura y resultados de reclamación, este escenario prueba un inicio fallido seguido de una mutación real.

El arnés falla ante excepciones, errores de consola, HTTP >=400 y fallos de red inesperados. Solo admite los 503 de los endpoints inyectados y los 401/errores de consola esperados durante la expiración; inspecciona el error Axios para no ignorar otros errores de aplicación. Para evitar que una redirección escape del guard, el arnés obtiene respuestas reales sin seguir redirecciones automáticamente, comprueba cada destino y solo sigue redirecciones GET/HEAD a los orígenes loopback configurados; otras redirecciones fallan. Bloquea WebSocket externos y service workers. Los WebSocket locales se encaminan mediante el cliente `ws` incluido en Playwright, con redirecciones desactivadas: WebKit sí siguió una redirección de upgrade durante una prueba local y no es seguro usar `connectToServer()` sin esta protección. Usa `assertIsolated`, `loginUi` y fixtures G2/G13/G14 reales. Los 503 son deliberados, no evidencia de disponibilidad del backend.

## Ejecución observada

El 2026-11-28, en Linux con Node 22.23.5 y Playwright 1.55.0, se instalaron Firefox 141.0 (build 1490) y WebKit 26.0 (build 2203), además de sus bibliotecas Linux. Con backend y preview en loopback, SQLite desechable migrada y semillas G2/G14, la versión anterior del test ejecutó **16 escenarios, 0 fallos**:

| Motor | 1440×900 | 390×844 con `hasTouch` |
|---|---:|---:|
| WebKit | 4/4 | 4/4 |
| Firefox | 4/4 | 4/4 |

También pasaron `npm run lint`, `npm run build` y `node --check` del nuevo script. El primer intento del arnés retuvo una preflight CORS y eligió coordenadas fuera del mundo; se corrigió el arnés y se repitió. No es un defecto de producto. La primera clasificación de logs también señaló como inesperados errores deliberados de 503/401; se restringió por endpoint y estado antes de repetir.

En la continuación, el arnés aislado ejecutó el commit limpio `70574b00e3d99ce2993fbcfbcc68b507313efdce`: **20/20** escenarios (cinco por motor y viewport), `npm ci` con SHA-256 del lockfile `491412b84fd1f1bcceb6945913f0bc91b898dd36fa8a618cc33ec1f83fb78634`, Vite 8.3.8, WebKit y Firefox. Se comprobó el rechazo de HEAD incorrecto y checkout sucio y la limpieza tras SIGTERM. Una prueba local separada mostró que WebKit sigue una redirección de upgrade; el cliente sin redirecciones rechazó el 302 sin conectar al destino. Esta evidencia corresponde a ese commit, no implica que otro HEAD o CI hayan pasado.

**Defectos reproducibles de producto agrupados:** ninguno confirmado en esta matriz. No se propone modificar frontend ajeno al alcance. Los defectos de mapa/militar descritos en la auditoría anterior deben mantenerse y volver a comprobarse por separado; este resultado no los cierra.

## Reproducir

### Arnés CI aislado

El arnés `e2e/parallel-g8-ci.mjs` requiere Linux con `/proc` accesible. Exige el SHA completo y un checkout limpio, exporta **ese commit** con `git archive` a un directorio temporal, instala únicamente el lockfile frontend con `npm ci`, migra y siembra una SQLite desechable, compila y arranca servicios loopback propios con puertos efímeros. Espera el anuncio de arranque de cada proceso y falla si alguno termina. Ejecuta obligatoriamente ambos motores y ambos tamaños. Al fallar o recibir SIGINT/SIGTERM, rastrea grupos descendientes —incluidos los navegadores separados de Playwright— y elimina procesos, DB y export; SIGKILL del propio arnés o una caída del sistema impiden esa limpieza. No instala ni actualiza paquetes en el checkout.

Playwright no está incluido en el lockfile del frontend: el arnés exige una instalación externa de `@playwright/test` **1.55.0** ya preparada (como en CI existente), y comprueba su versión; no ejecuta `npm install` sobre el frontend ni altera su grafo fijado. El intérprete Python debe estar previamente preparado con `batalla_medieval_backend/requirements.txt`; sus dependencias transitivas no tienen lockfile y no se afirma reproducibilidad bit a bit. Instalar antes los navegadores y bibliotecas de sistema según la plataforma. Los únicos argumentos externos son rutas locales y el SHA; las URL y la configuración de test las fija el arnés.

Por ejemplo, preparar las herramientas fuera del checkout, con acceso al registro y permisos adecuados para las bibliotecas de sistema:

```bash
python -m venv /tmp/medievol-g8-python
/tmp/medievol-g8-python/bin/pip install -r batalla_medieval_backend/requirements.txt
npm install --prefix /tmp/medievol-g8-tools --no-save --package-lock=false @playwright/test@1.55.0
/tmp/medievol-g8-tools/node_modules/.bin/playwright install firefox webkit
/tmp/medievol-g8-tools/node_modules/.bin/playwright install-deps firefox webkit
```

```bash
export G8_EXPECTED_HEAD="$(git rev-parse HEAD)"
export G8_PYTHON=/ruta/absoluta/venv/bin/python
export G8_PLAYWRIGHT_MODULE=/ruta/absoluta/node_modules/@playwright/test/index.js
node batalla_medieval_frontend/e2e/parallel-g8-ci.mjs
```

Un motor ausente o que no arranque es **fallo** en el arnés CI. No usar `G8_ENGINES` para el arnés: siempre ejecuta ambos. Mantener el checkout sin archivos modificados ni no rastreados; no usar la fuente de trabajo como evidencia de otro commit. `npm ci` puede necesitar acceso al registro de paquetes; el navegador solo accede a los servicios locales. No se integra ningún workflow ni se convierte esta ejecución en una puerta obligatoria.

## Límites

- Viewport/touch emulados en Linux no equivalen a Safari/iOS, Firefox móvil, lectores de pantalla o dispositivos físicos. No se verificaron Chromium ni otros navegadores en esta matriz.
- Firefox de Playwright no produjo el evento offline en el primer intento usando únicamente `setOffline`; por eso se inyectan explícitamente los eventos de plataforma, además de cambiar el estado de red. El guard usa `route.fetch`, que no demuestra que las solicitudes de la aplicación fallen durante la desconexión. No demuestra detección automática del SO ni reconexión Socket.IO tras una interrupción de larga duración.
- Se prueba un JWT inválido, no el vencimiento por reloj real ni todas las carreras entre sesiones. Las respuestas deliberadamente retenidas o 503 no miden latencia, recuperación bajo carga ni una caída real del servidor.
- No cubre todas las interacciones, traducciones, medios ni estados de G21–G25; tampoco sustituye las auditorías de aventuras, mapa o las pruebas existentes. No se han ejecutado staging, CI de este nuevo script, G5 ni certificación G8.
