# Medievol — Auditoría E2E independiente del recorrido del jugador

Fecha: 2026-11-20. Rama: `parallel/medievol-e2e-20261120`. Base inspeccionada: `main@281de839102894ae1d3766156e17fc771ba0a9b9`.

## Alcance, seguridad y método

Se utilizó una copia aislada del repositorio, SQLite desechable bajo `/tmp/medievol-journey-*`, backend y frontend locales **únicamente en loopback** (`127.0.0.1:8108` y `127.0.0.1:4273`), `APP_ENV=test` y un secreto explícitamente de pruebas. No se usaron cuentas, contraseñas, SMTP, bases de datos ni servicios productivos. Los scripts nuevos se niegan a mutar datos sin `PARALLEL_JOURNEY_ALLOW_MUTATIONS=isolated`, base SQLite de pruebas y ambos servicios en localhost.

Se reutilizaron `app.seed` y los fixtures `prepare_g2_e2e.py`, `prepare_g7_research_e2e.py`, `prepare_g8_unit_upkeep_e2e.py`, `prepare_g9_combat_e2e.py` y `prepare_g10_espionage_e2e.py`. El script `parallel-journey-fixtures.mjs` agrega **solo** un segundo mundo abierto al SQLite aislado. Registro y verificación se ejecutaron mediante navegador, con token de verificación obtenido únicamente mediante lectura de esa base desechable; **la entrega real de correos no se comprobó**. Los combates y espionajes se resolvieron durante la preparación mediante los fixtures existentes, no mediante lanzamiento completo del navegador.

## Ejecución observada

| Validación | Resultado | Evidencia |
|---|---:|---|
| Sintaxis de 7 scripts `parallel-journey-*.mjs` | 7/7 | `node --check` |
| Frontend lint | OK | `npm run lint` — exit 0 |
| Compilación frontend y presupuesto de JS | OK | `npm run build` — initial 399.3 KiB, mayor chunk 325.6 KiB |
| Pruebas backend focalizadas de auth/mundos/edificios/tropas/movimientos/combate/espionaje | 24/24 | `pytest` — 24 passed, 5 warnings, 51.67s |
| `parallel-journey-onboarding.mjs` | 5/5 | `JOURNEY_SUMMARY onboarding passed=5 failed=0` |
| `parallel-journey-progression.mjs` | 6/6 | `JOURNEY_SUMMARY economy-army-map passed=6 failed=0` |
| `parallel-journey-security.mjs` | 7/7 | `JOURNEY_SUMMARY reports-isolation-recovery passed=7 failed=0` |
| `parallel-journey-crossworld.mjs` | 5/5 | `JOURNEY_SUMMARY crossworld-mutations passed=5 failed=0` |
| `parallel-journey-map-actions.mjs` | **2/5** | `JOURNEY_SUMMARY map-action-adversarial passed=2 failed=3`; exit 1 **intencionalmente preservado** |

**Resultado consolidado de nuevos escenarios: 25 aprobados, 3 fallidos, 28 ejecutados; 89.3% aprobados.** Esto es aprobación de escenarios, **no** porcentaje de producto terminado. Los 3 fallos son defectos reproducibles de producto. Se preservaron las aserciones y el estado de fallo en el PR de pruebas.

## Cobertura del recorrido según sus 8 objetivos

| Etapa | Nivel verificado | Evidencia y límite |
|---|---|---|
| 1. Registro, verificación y sesión | **Parcial** | Registro real y validaciones negativas, enlace de token aislado, verificación de un solo uso, login; no entrega SMTP real |
| 2. Selección de mundo y capital | **Completa en el flujo de prueba** | Selección visual, capital única, unión idempotente, no creación directa, persistencia y segundo mundo |
| 3. Producción y construcción | **Parcial** | Tarifas/almacenamiento y recursos autoritativos, mejora pagada, cola visible y persistente, duplicado rechazado; no tick económico prolongado ni finalización |
| 4. Entrenamiento e investigación | **Parcial** | Inicio en backend, reflejo UI, colas persistentes, ceros y duplicados rechazados; no resolución final de temporizadores |
| 5. Exploración y mapa | **Parcial — 3 fallos** | Mapa y límites, selección bárbara, enlace Atacar positivo; Espiar, Comerciar y Mensaje inoperantes |
| 6. Combate, espionaje e informes | **Parcial** | Fixtures resueltos, semillas/rounds y retorno contrastados con API y vista, informe de espionaje contrastado; sin lanzamiento completo desde UI |
| 7. Desconexión y errores | **Completa en el flujo de prueba** | Aborto de solicitud real de mapa con reintento exitoso, offline/online, JWT inválido, cierre de sesión y reingreso |
| 8. Reglas entre mundos | **Completa en las operaciones comprobadas** | Acceso mapa sin membresía 403, ciudades ajenas 404, ataque/spy prohibidos y sin movimientos, construcción, tropas, investigación, mercado y transporte prohibidos, sin nuevas colas |

**Cobertura efectiva estricta: 3/8 etapas completas en el alcance ensayado = 37.5%; 5/8 parcialmente verificadas = 62.5%; 8/8 con al menos una prueba.** No se realizó un único recorrido **continuo** completo desde alta hasta combate: se encadenaron pruebas con fixtures de cuentas separadas. Por eso no se declara un 100% de recorrido real.

## Hallazgos reproducidos y destino

**P0: ninguno confirmado.**

### P1 — QA-MAP-01: botón «Espiar» no hace nada

**Propietario:** frontend/mapa (`MapView.jsx`, rama en paralelo del mapa). **Reproducción:** con fixture `g9_combat` dentro del entorno aislado, navegar a `/map`, ir a coordenadas de `G9 Auditable Barbarian` (en el snapshot probado, `(0,0)`), pulsar su casilla, luego «Espiar». **Esperado:** abrir flujo de espionaje o iniciar una acción validable. **Actual:** ninguna navegación, solicitud pertinente, modal ni cambio del detalle. **Evidencia:** `parallel-journey-map-actions.mjs` falla con `Visible map action Espiar produced no navigation, request, or visible change for city id=13`. En el mismo panel «Atacar» sí dirige a `/send-movement/13`, control positivo. `MapView.jsx` contiene botón «Espiar» sin manejador visible al HEAD inspeccionado. **Acción sugerida al coordinador:** asignar a propietaria de rama del mapa, implementar destino apropiado y conservar la regresión.

### P2 — QA-MAP-02 y QA-MAP-03: «Comerciar» y «Mensaje» son controles inertes

**Propietario:** frontend/mapa y rutas de negocio respectivas. **Misma reproducción**, botones «Comerciar» y «Mensaje» en el panel de la ciudad bárbara. Ambos fallan con mensajes `Visible map action Comerciar ... no navigation, request, or visible change` y `Visible map action Mensaje ...`. El carácter de ciudad bárbara puede requerir una restricción funcional: en tal caso **no mostrar** una acción aparentemente habilitada que no hace nada; para jugadores destinatarios válidos, implementar navegación o acción real. Debe definirse la conducta antes de cerrar la incidencia. Tests se mantienen rojos.

### P2 — QA-INFRA-01: nuevos scripts NO se incluyen en el job de Browser E2E

**Propietario:** coordinación/CI. `.github/workflows/validation.yml` lista scripts `g2`, `g4`, etc. por nombre fijo, sin patrón `parallel-journey-*.mjs`. El nuevo PR ejecutará las validaciones existentes, pero **no ejecutará los nuevos escenarios en CI** hasta que se integre una fase de ejecución con base de datos aislada y fixtures apropiados. Cambio del workflow fuera del alcance permitido de esta rama; no simular cobertura verde. Solicitar implementación posterior de un job E2E aislado, manteniendo `PARALLEL_JOURNEY_ALLOW_MUTATIONS=isolated` y sin credenciales reales.

**P3 producto:** ninguno reproducido.

## Problemas de la PRUEBA diferenciados de producto

- El primer arranque de Playwright falló por binario Chromium no correspondiente a la versión 1.55.0. Se corrigió el entorno aislado instalando el headless compatible; las pruebas posteriormente corrieron.
- Un correo de test con dominio `example.test` fue rechazado por el validador de correo (422): dato inválido del test, cambiado a `example.com`; registro y verificación luego pasaron.
- Una aserción de selector tenía una precedencia `await` incorrecta: corregida y repetida, 5/5 onboarding.
- Una selección temprana del mapa se solapaba con la hidratación de la ciudad: el test espera ahora la casilla de la capital antes de saltar a las coordenadas; la selección pasó. Las tres acciones inertes se confirmaron **después** de corregir esta condición y de evitar falsos positivos por textos del reloj en el resto del dashboard.
- Estos problemas de la herramienta **no** se contabilizan como defectos del producto.

## Reproducción controlada

Ejecutar **solo en un checkout desechable**, con variables de entorno explícitas `APP_ENV=test`, `DATABASE_URL=sqlite:////tmp/medievol-journey-...db`, `PARALLEL_JOURNEY_DB=/tmp/medievol-journey-...db`, `PARALLEL_JOURNEY_ALLOW_MUTATIONS=isolated`, `VITE_API_URL=http://127.0.0.1:8108` y `E2E_BASE_URL=http://127.0.0.1:4273`. La DB debe estar migrada y sembrada con los fixtures indicados, después invocar `node e2e/parallel-journey-fixtures.mjs` (desde `batalla_medieval_frontend`, con `PYTHONPATH` / `PARALLEL_JOURNEY_PYTHON` apuntando al backend). Levantar el backend de prueba en 8108 y el preview de Vite compilado hacia esa API en 4273; instalar `@playwright/test@1.55.0` y su Chromium.

Ejecutar, por este orden, `node e2e/parallel-journey-onboarding.mjs`, `node e2e/parallel-journey-progression.mjs`, `node e2e/parallel-journey-security.mjs`, `node e2e/parallel-journey-crossworld.mjs`, `node e2e/parallel-journey-map-actions.mjs`. **Usar una nueva DB para repetir todo** porque los escenarios de onboarding/unión/progreso mutan deliberadamente solo los fixtures; no son independientes de una nueva semilla. El último script debe terminar con exit 1 mientras persistan los tres defectos.

## Entrega y cierre pendiente

- Aceptar el PR **solo como borrador**, sin merge.
- Coordinar QA-MAP-01/02/03 con la responsable de `MapView.jsx`; repetir las tres regresiones tras corrección en su rama, antes de fusionarlas.
- Coordinar un job E2E de CI aislado para estos scripts, fuera de este alcance de escritura.
- Pendiente para recorrido completamente verificado: correo real controlado (sin tocar producción), ticks y completado de colas, despacho UI de ataque/espio, y recorrido integral en una sola cuenta con los mismos datos.
