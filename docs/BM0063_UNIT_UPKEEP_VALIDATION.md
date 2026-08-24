# BM-0063 — Validación de catálogo final de unidades y mantenimiento

## Estado

**VALIDADO FUNCIONALMENTE** en el HEAD `a56a4963fca13cce7ac592f74d8152f52a3c4933` mediante **Validation #398** (`run_id=32697399745`).

Después de documentar el cierre, **Validation #399** volvió a confirmar Backend, PostgreSQL, Frontend, seguridad y operaciones, pero expuso una aserción temporalmente inestable de G8: el E2E comparaba el coste/reembolso contra un snapshot de recursos tomado demasiado pronto mientras la economía seguía produciendo. Los endpoints reales de entrenamiento y cancelación respondieron correctamente. El recorrido se endureció para serializar las lecturas que recalculan economía y comparar contra snapshots tomados inmediatamente antes de cada escritura autoritativa.

El cierre definitivo requiere una Validation completa verde sobre el HEAD que contenga **este documento y esa estabilización determinista de G8**.

La fuente única de balance de este hito es `BALANCE_VERSION = "2026.08.23-bm0063.1"`.

BM-0064 debe conservar estos valores como catálogo canónico y cerrar cómo se resuelven dentro del combate final por rondas; no debe introducir un segundo catálogo militar.

## Alcance entregado

### Catálogo canónico de nueve unidades

`app/services/balance.py` fija, para cada unidad:

- coste de entrenamiento en madera, piedra, hierro y oro;
- tiempo de entrenamiento;
- requisitos de edificios;
- coste de población;
- mantenimiento de oro por hora;
- velocidad de movimiento;
- capacidad de carga;
- ataque base;
- defensa contra infantería;
- defensa contra caballería;
- defensa contra asedio.

Orden canónico:

1. Lancero Común (`basic_infantry`);
2. Soldado de Acero (`heavy_infantry`);
3. Arquero Real (`archer`);
4. Jinete Explorador (`fast_cavalry`);
5. Caballero Imperial (`heavy_cavalry`);
6. Infiltrador (`spy`);
7. Quebramuros (`ram`);
8. Tormenta de Piedra (`catapult`);
9. Noble (`noble`).

La investigación continúa usando el contrato temporizado cerrado en BM-0062. BM-0063 declara finales para v1.0 los valores de entrenamiento, población, mantenimiento, movimiento, carga y estadísticas base que acompañan a esas tecnologías.

### Capacidad militar sostenible por mantenimiento

El mantenimiento deja de ser informativo y pasa a ser una restricción autoritativa del servidor.

Cada ciudad calcula y expone:

- capacidad sostenible de mantenimiento en oro/h;
- mantenimiento usado por tropas existentes;
- mantenimiento reservado por entrenamientos en cola;
- margen de mantenimiento disponible;
- indicador de sostenibilidad.

La producción canónica base de oro es `8.0/h`. La capacidad efectiva se obtiene desde la economía autoritativa de la ciudad, nunca desde un número enviado por el cliente.

Antes de aceptar un entrenamiento, el servidor comprueba simultáneamente recursos, población, requisitos, slots y margen de mantenimiento. La solicitud se rechaza si el nuevo ejército excedería la capacidad sostenible aunque todavía sobren población y recursos.

Las colas aceptadas reservan mantenimiento inmediatamente, evitando que varias solicitudes concurrentes sobrevendan el mismo margen económico.

### Fronteras temporales de mantenimiento

El mantenimiento se calcula sobre la composición militar autoritativa y no desaparece al enviar tropas fuera de la ciudad.

Las transiciones militares respetan esta frontera:

1. liquidar producción y mantenimiento bajo lock hasta el instante de transición;
2. modificar la composición militar;
3. iniciar el siguiente intervalo con la composición nueva.

Esto evita:

- cobrar retroactivamente mantenimiento a una tropa recién entrenada;
- dejar de cobrar retroactivamente tropas que existieron durante parte del intervalo;
- transferir mantenimiento de un refuerzo antes de su llegada efectiva.

El worker respeta el orden de locks existente: las colas de tropa se procesan con su ciudad antes de las transiciones de movimientos que afectan ciudades, evitando invertir el orden frente a la cancelación de entrenamiento.

### Entrenamiento y cancelación

El flujo persiste el coste histórico pagado por la cola. Si se cancela antes de completarse:

- desaparece la cola;
- se libera inmediatamente la reserva de mantenimiento;
- se devuelve el `80%` del coste pagado persistido;
- el reembolso no depende de que un balance futuro conserve los mismos precios.

### Atomicidad y concurrencia

Las solicitudes de entrenamiento bloquean la ciudad antes de decidir si existe margen sostenible. El cálculo incluye tropas activas y mantenimiento reservado por colas existentes.

La matriz PostgreSQL incluye un caso con slots múltiples donde dos entrenamientos simultáneos compiten por el mismo margen de oro. Solo la operación que todavía cabe puede reservarlo; la segunda no puede usar una lectura obsoleta para sobreasignar capacidad.

## API, estado, UI y wiki

`GET /troop/available` expone desde la fuente canónica:

- coste/tiempo de entrenamiento;
- requisitos;
- población por unidad;
- mantenimiento/h;
- estadísticas base;
- velocidad/carga;
- población disponible;
- margen de mantenimiento disponible;
- posibilidad real de entrenar en el estado actual.

El estado agregado de ciudad publica la capacidad militar económica junto con recursos y colas. La barra de recursos muestra mantenimiento usado frente a capacidad sostenible.

Las tarjetas de tropas muestran los valores canónicos y deshabilitan la cantidad cuando no cabe por población o mantenimiento. La UI es ayuda; la decisión final sigue siendo del servidor.

Las capas puramente decorativas de las tarjetas no interceptan puntero. G8 espera las pantallas reales de intro/carga y usa clics normales, sin `force` ni bypass.

La wiki consume el mismo catálogo para población, mantenimiento, movimiento, carga y estadísticas; no mantiene números militares duplicados.

## Evidencia automática funcional — Validation #398

HEAD funcional: `a56a4963fca13cce7ac592f74d8152f52a3c4933`  
Run: `32697399745`

### Backend

**SUCCESS**

- `214` pruebas recolectadas;
- `196 passed`;
- `18 skipped`;
- `4 warnings`;
- cobertura total `74%`.

Incluye:

- `tests/test_bm0063_unit_balance.py`;
- las `9` pruebas de `tests/test_unit_upkeep.py`;
- lifecycle de unidades;
- población;
- producción autoritativa;
- movimientos/worker multiplayer;
- contratos de fuente única.

Los 18 skips requieren locks PostgreSQL y se ejecutan en el job dedicado.

También quedaron verdes:

- compilación backend;
- Alembic `0001 -> 0009`;
- seed canónico idempotente;
- downgrade `0009 -> base`.

BM-0063 **no agrega migración**: el schema head sigue siendo `0009`.

### PostgreSQL concurrency

**SUCCESS**

- `18 passed`;
- `3 warnings`;
- `28.28s`.

Esto prueba, entre otras garantías, que una reserva de mantenimiento no puede sobreasignarse por solicitudes simultáneas y que el nuevo orden de liquidación/locks no introduce deadlocks en la matriz concurrente existente.

### Frontend

**SUCCESS**

- `npm ci`;
- lint;
- build de producción.

### Dependencias y seguridad

**SUCCESS**

- auditoría Python;
- análisis estático de seguridad;
- auditoría frontend según el gate del proyecto.

### G5 operaciones

**SUCCESS**

Permanecen verdes deployment, backup, restore y probes operativos.

### Browser E2E

**SUCCESS** en #398:

- `Browser smoke passed: durable session and authenticated realtime are stable, no console errors or HTTP 4xx/5xx`;
- `G4 UX smoke passed: all visible routes at 390x844, keyboard focus, 250ms API delay and persisted es/en switching`;
- `G6 expansion browser journey passed`;
- `G7 research browser journey passed`;
- `G8 BM-0063 unit upkeep browser journey passed`.

Fixture G8:

`prepared-g8:3:1:12:unit=noble:population=5:upkeep=0.5:capacity=8`

G8 demuestra de extremo a extremo:

1. Noble publica población `5` y mantenimiento `0.5` oro/h;
2. la ciudad tiene capacidad sostenible `8` oro/h;
3. `17` Nobles usan `85` población pero exigen `8.5` oro/h, por lo que el bloqueo es específicamente económico;
4. `1` Noble sí puede entrenarse;
5. la cola reserva `0.5` oro/h y deja `7.5` oro/h libres;
6. el coste de cuatro recursos se descuenta;
7. `DELETE /troop/queue/{id}` devuelve `204`;
8. cancelar libera la reserva y restaura `8.0` oro/h;
9. el reembolso es `80%` del coste persistido.

### Imágenes Docker

**SUCCESS**

- imagen backend;
- imagen frontend.

## Validation #399 — hallazgo de calidad del E2E

HEAD: `1d370063f4f1fd3ef4371ceb6d8ed4dff6bd7e19`  
Run: `32698194318`

Volvieron a quedar verdes:

- Backend: `196 passed`, `18 skipped`, cobertura `74%`;
- PostgreSQL concurrency;
- Frontend;
- Dependency/security;
- G5 operations;
- G2;
- G4;
- G6;
- G7.

G8 completó las operaciones reales:

- `POST /troop/train?world_id=1` → `200`;
- lecturas de estado/catálogo → `200`;
- `DELETE /troop/queue/1` → `204`.

El fallo fue únicamente la comparación de recursos: el test reutilizaba `initial.status` tomado mucho antes de entrenar/cancelar, mientras los recursos se recalculaban durante el recorrido. Además, `apiSnapshot()` pedía estado y catálogo en paralelo, aunque ambos pueden recalcular economía; eso hacía que el propio snapshot fuera sensible al timing sobre SQLite.

Corrección aplicada después de #399:

- lecturas de catálogo y estado serializadas dentro de `apiSnapshot()`;
- `beforeTraining` tomado inmediatamente antes del `POST`;
- coste congelado desde el catálogo de ese instante;
- `beforeCancel` tomado inmediatamente antes del `DELETE`;
- aserción de cargo = `beforeTraining - coste`;
- aserción de reembolso = `beforeCancel + 80% del coste`;
- tolerancia pequeña únicamente para producción real transcurrida entre el snapshot y la escritura.

Esto conserva una prueba estricta del cargo/reembolso sin confundir producción pasiva legítima con un error de negocio.

## Rollout operativo

BM-0063 no requiere migración Alembic nueva, pero sí cambia reglas de balance/mantenimiento. Tratarlo como cambio de reglas del mundo.

Procedimiento:

1. snapshot/backup de base;
2. identificar mundos que pueden recibir `2026.08.23-bm0063.1` según PD-009;
3. desplegar API, frontend y worker compatibles como conjunto;
4. mantener schema `0009`;
5. verificar health/readiness y `/economy/balance_preview`;
6. verificar `/troop/available` y `/city/{id}/status`;
7. probar creación/cancelación de cola y reserva de mantenimiento;
8. observar errores, locks y tiempos del worker antes de ampliar tráfico.

PD-009 exige no alterar silenciosamente mundos ya iniciados. Cuando el versionado por mundo esté activado, debe respetarse la versión asignada a cada mundo.

## Rollback

El rollback es compatible con el schema actual porque BM-0063 no agrega migración.

Antes de volver código en tráfico real:

1. detener nuevas solicitudes de entrenamiento;
2. pausar worker si la versión anterior interpreta distinto transiciones militares;
3. snapshot/backup;
4. inspeccionar colas activas y movimientos próximos;
5. procesar/cancelar explícitamente operaciones cuyo comportamiento pudiera cambiar;
6. desplegar API/frontend/worker anteriores como conjunto compatible;
7. verificar economía, colas, movimientos y mantenimiento antes de reabrir tráfico.

No se requiere ni se recomienda `alembic downgrade` para revertir únicamente BM-0063.

## Hallazgos corregidos durante BM-0063

1. **Mantenimiento legado nulo**: un contrato antiguo todavía asumía `0.0` para infantería básica; el catálogo final fija mantenimiento positivo.
2. **Mantenimiento solo informativo**: ahora limita autoritativamente el ejército sostenible.
3. **Sobreasignación concurrente**: reservas activas forman parte del cálculo bajo lock y PostgreSQL prueba la garantía.
4. **Cobro retroactivo al completar entrenamiento**: el worker liquida el intervalo antes de incorporar la nueva tropa.
5. **Transferencia temporal incorrecta en movimientos/refuerzos**: la composición anterior paga hasta la transición efectiva.
6. **Interferencia visual en G8**: capas decorativas no capturan puntero y el E2E espera intro/loading reales.
7. **Snapshot E2E temporalmente inestable**: #399 mostró que comparar contra recursos del inicio confundía producción pasiva con coste/reembolso; G8 ahora usa lecturas serializadas y snapshots justo antes de las escrituras.

## Límite deliberado hacia BM-0064

BM-0063 declara final el **catálogo estático de unidades** y las restricciones de entrenamiento/población/mantenimiento.

BM-0064 debe cerrar el combate por rondas usando estos valores canónicos, incluyendo:

- PvE y PvP;
- moral;
- suerte limitada y auditable;
- bajas;
- botín;
- retorno;
- reproducibilidad desde semilla/estado auditable;
- resistencia a reintentos y doble resolución.

La inspección previa ya confirma una deuda a resolver en BM-0064: el combate actual usa aleatoriedad global (`random.uniform`/`random.randint`), por lo que todavía no puede reproducirse exactamente desde una semilla auditable.

BM-0064 puede definir cómo se combinan ataque y defensas por ronda, pero no debe duplicar ni redefinir silenciosamente las estadísticas base de BM-0063.

## Criterio de cierre

BM-0063 puede considerarse cerrado únicamente cuando el **HEAD de cierre que contiene este documento y la estabilización determinista de G8** obtenga una Validation completa verde, incluyendo Browser E2E e imágenes Docker.

Solo ese SHA final será válido para marcar PR #96 como Ready y fusionarlo.