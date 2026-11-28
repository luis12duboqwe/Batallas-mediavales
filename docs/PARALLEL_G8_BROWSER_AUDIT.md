# Auditoría independiente G8 — navegadores y resiliencia

Trabajo anticipado sobre `86adbd83dedc9a3e4c2d89b3adc247b72184d158`. **No certifica G8 ni sustituye G5**: la certificación y el merge quedan pendientes de G5 y de revisión independiente. El PR debe permanecer en borrador.

## Alcance y antecedentes

Se revisaron `g21-accessibility.mjs` (teclado, diálogo y diseño), `g22-media-performance.mjs` (medios y presupuesto), `g23-localization.mjs` (español), `g24-resilience.mjs` (sesión y conectividad) y `g25-states.mjs` (estados y reintentos), además de `parallel-map-navigation.mjs`, `parallel-map-actions-integration.mjs`, `parallel-adventures-flow.mjs` y `docs/PARALLEL_E2E_REPORT.md`. El PR #222 obliga a esperar la ciudad hidratada y su respuesta real antes de probar el mapa: esta auditoría espera la casilla de la ciudad y `aria-busy=false` antes de cambiar coordenadas. No repite sus respuestas vacías ni pretende volver a certificar G21–G25.

`e2e/parallel-g8-browser.mjs` añade cuatro escenarios por motor y viewport, cada uno en un contexto nuevo:

1. Abrir la invitación de alianza con teclado, comprobar foco, ciclo Tab/Shift+Tab, Escape y restauración del foco.
2. Con la ciudad real ya cargada, retener un GET de mapa cuya respuesta procede del backend, pedir otra zona y entregar primero la respuesta más reciente. Comprobar carga, ausencia de falso vacío y que la respuesta antigua no sustituya las casillas reales de la última zona.
3. Provocar 503 solo en GET de bandeja y reportes. Recuperar primero reportes y comprobar que el aviso global sigue por la bandeja; recuperar la bandeja con el backend real y comprobar que desaparece el aviso. No se fabrican respuestas exitosas.
4. Cambiar la red del contexto offline/online, notificar ambos eventos al documento y volver a autenticar contra el backend. Después, cargar una ruta protegida con JWT inválido, comprobar el aviso y la eliminación del token y volver a entrar.

El arnés falla ante excepciones, errores de consola, HTTP >=400 y fallos de red inesperados. Solo admite los 503 de los dos endpoints inyectados y los 401/errores de consola esperados durante la expiración; inspecciona el error Axios para no ignorar otros errores de aplicación. Para evitar que una redirección escape del guard, el arnés obtiene respuestas reales sin seguir redirecciones automáticamente, comprueba cada destino y solo sigue redirecciones GET/HEAD a los orígenes loopback configurados; otras redirecciones fallan. Bloquea WebSocket externos y service workers. Usa `assertIsolated`, `loginUi` y `playerSnapshot` existentes, y fixtures G2/G14 reales. El fallo 503 es deliberado, no evidencia de disponibilidad del backend.

## Ejecución observada

El 2026-11-28, en Linux con Node 22.23.5 y Playwright 1.55.0, se instalaron Firefox 141.0 (build 1490) y WebKit 26.0 (build 2203), además de sus bibliotecas Linux. Con backend y preview en loopback, SQLite desechable migrada y semillas G2/G14, la matriz ejecutó **16 escenarios, 0 fallos**:

| Motor | 1440×900 | 390×844 con `hasTouch` |
|---|---:|---:|
| WebKit | 4/4 | 4/4 |
| Firefox | 4/4 | 4/4 |

También pasaron `npm run lint`, `npm run build` y `node --check` del nuevo script. El primer intento del arnés retuvo una preflight CORS y eligió coordenadas fuera del mundo; se corrigió el arnés y se repitió. No es un defecto de producto. La primera clasificación de logs también señaló como inesperados errores deliberados de 503/401; se restringió por endpoint y estado antes de repetir.

**Defectos reproducibles de producto agrupados:** ninguno confirmado en esta matriz. No se propone modificar frontend ajeno al alcance. Los defectos de mapa/militar descritos en la auditoría anterior deben mantenerse y volver a comprobarse por separado; este resultado no los cierra.

## Reproducir

Solo en checkout desechable; nunca contra producción. Instalar las dependencias del repositorio y Playwright **sin modificar los lockfiles**. Se necesitan Python con `batalla_medieval_backend/requirements.txt`, Node y bibliotecas de navegador. Por ejemplo, desde la raíz:

```bash
python -m venv /tmp/medievol-g8-venv
/tmp/medievol-g8-venv/bin/pip install -r batalla_medieval_backend/requirements.txt
npm ci --prefix batalla_medieval_frontend
npm install --prefix batalla_medieval_frontend --no-save --package-lock=false @playwright/test@1.55.0
cd batalla_medieval_frontend
npx playwright install firefox webkit
# Si faltan bibliotecas de sistema y el entorno lo permite:
npx playwright install-deps firefox webkit
cd ..
```

En una misma shell Bash, crear una DB nueva y compilar con las mismas URL que usarán los servicios y el test:

```bash
export PATH="/tmp/medievol-g8-venv/bin:$PATH"
export APP_ENV=test PARALLEL_JOURNEY_ALLOW_MUTATIONS=isolated
export PARALLEL_JOURNEY_DB="/tmp/medievol-journey-g8-$(date +%s)-$$.db"
export DATABASE_URL="sqlite:///$PARALLEL_JOURNEY_DB"
export PYTHONPATH="$PWD/batalla_medieval_backend"
export VITE_API_URL=http://127.0.0.1:18318 VITE_SOCKET_URL=http://127.0.0.1:18318
export E2E_BASE_URL=http://127.0.0.1:14318 CORS_ORIGINS=http://127.0.0.1:14318 FRONTEND_URL=http://127.0.0.1:14318
export SECRET_KEY=isolated-test-key-g8-not-production
test ! -e "$PARALLEL_JOURNEY_DB"
alembic -c batalla_medieval_backend/alembic.ini upgrade head
python -m app.seed
python scripts/prepare_g2_e2e.py
python scripts/prepare_g14_community_e2e.py
(cd batalla_medieval_frontend && npm run build)
```

Iniciar y verificar los servicios **desde esa shell**. Este bloque requiere `ss` y `curl`: falla si un puerto ya está ocupado, si un proceso muere o si el listener no pertenece al PID iniciado. La trampa limpia servicios y DB incluso al fallar:

```bash
set -e
test -z "$(ss -H -ltn 'sport = :18318')"
test -z "$(ss -H -ltn 'sport = :14318')"
API_PID=
UI_PID=
cleanup() {
  if [ -n "$API_PID" ]; then kill "$API_PID" 2>/dev/null || true; wait "$API_PID" 2>/dev/null || true; fi
  if [ -n "$UI_PID" ]; then kill "$UI_PID" 2>/dev/null || true; wait "$UI_PID" 2>/dev/null || true; fi
  rm -f "$PARALLEL_JOURNEY_DB"
}
trap cleanup EXIT
python -m uvicorn app.main:socket_app --app-dir batalla_medieval_backend --host 127.0.0.1 --port 18318 &
API_PID=$!
(cd batalla_medieval_frontend && exec ./node_modules/.bin/vite preview --host 127.0.0.1 --port 14318 --strictPort) &
UI_PID=$!
ready=false
for attempt in $(seq 1 60); do
  kill -0 "$API_PID" "$UI_PID"
  if ss -H -ltnp 'sport = :18318' | grep -Fq "pid=$API_PID," &&
     ss -H -ltnp 'sport = :14318' | grep -Fq "pid=$UI_PID," &&
     curl -fsS http://127.0.0.1:18318/health >/dev/null &&
     curl -fsS http://127.0.0.1:14318/login >/dev/null; then
    ready=true
    break
  fi
  sleep 1
done
test "$ready" = true
(cd batalla_medieval_frontend && node e2e/parallel-g8-browser.mjs)
cleanup
trap - EXIT
```

No reutilizar un servidor ajeno que ya ocupe el puerto: el guard de variables no demuestra por sí solo qué DB usa ese proceso ni con qué URL se compiló Vite. Conservar los logs ante fallos. `G8_ENGINES=webkit` o `G8_ENGINES=firefox` permite aislar un motor; por defecto se intentan ambos. Si falta el ejecutable, se imprime `SKIP` con su ruta; si no se ejecuta ninguno, o falla el arranque u otro escenario, el proceso termina con código no cero. Un `SKIP` no es PASS.

## Límites

- Viewport/touch emulados en Linux no equivalen a Safari/iOS, Firefox móvil, lectores de pantalla o dispositivos físicos. No se verificaron Chromium ni otros navegadores en esta matriz.
- Firefox de Playwright no produjo el evento offline en el primer intento usando únicamente `setOffline`; por eso se inyectan explícitamente los eventos de plataforma, además de cambiar el estado de red. El guard usa `route.fetch`, que no demuestra que las solicitudes de la aplicación fallen durante la desconexión. No demuestra detección automática del SO ni reconexión Socket.IO tras una interrupción de larga duración.
- Se prueba un JWT inválido, no el vencimiento por reloj real ni todas las carreras entre sesiones. Las respuestas deliberadamente retenidas o 503 no miden latencia, recuperación bajo carga ni una caída real del servidor.
- No cubre todas las interacciones, traducciones, medios ni estados de G21–G25; tampoco sustituye las auditorías de aventuras, mapa o las pruebas existentes. No se han ejecutado staging, CI de este nuevo script, G5 ni certificación G8.
