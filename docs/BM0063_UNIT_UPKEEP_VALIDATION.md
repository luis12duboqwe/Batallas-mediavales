# BM-0063 — Validación de catálogo final de unidades y mantenimiento

## Estado

BM-0063 cerró funcionalmente el catálogo militar y el mantenimiento en **Validation #398** (`run_id=32697399745`, HEAD `a56a4963fca13cce7ac592f74d8152f52a3c4933`). Las validaciones de cierre posteriores encontraron y obligaron a corregir una condición de carrera adicional en la autoridad económica: un GET de producción cargado antes de un pago podía terminar después y restaurar recursos obsoletos.

El cierre definitivo exige una Validation completa verde sobre el HEAD que contenga **el catálogo BM-0063, las fronteras de mantenimiento, G8 determinista, la protección contra lost updates y este documento**.

Fuente única de balance: `BALANCE_VERSION = "2026.08.23-bm0063.1"`.

BM-0064 debe conservar estos valores como catálogo canónico y cerrar cómo se resuelven dentro del combate final por rondas; no debe introducir un segundo catálogo militar.

## Alcance entregado

### Catálogo canónico de nueve unidades

`app/services/balance.py` fija para cada unidad:

- coste de entrenamiento en madera, piedra, hierro y oro;
- tiempo de entrenamiento;
- requisitos de edificios;
- población;
- mantenimiento de oro por hora;
- velocidad;
- carga;
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

La investigación continúa usando el contrato temporizado de BM-0062. BM-0063 declara finales para v1.0 los valores de entrenamiento, población, mantenimiento, movimiento, carga y estadísticas base.

### Capacidad militar sostenible

El mantenimiento es una restricción autoritativa, no un dato cosmético.

Cada ciudad calcula y expone:

- capacidad sostenible en oro/h;
- mantenimiento usado por tropas existentes;
- mantenimiento reservado por colas;
- margen disponible;
- estado de sostenibilidad.

La producción canónica base de oro es `8.0/h`. La capacidad efectiva se obtiene de la economía autoritativa de la ciudad.

Antes de aceptar entrenamiento, el servidor comprueba recursos, población, requisitos, slots y mantenimiento. Las colas aceptadas reservan mantenimiento inmediatamente para impedir sobreasignación concurrente.

### Fronteras temporales de mantenimiento

Las transiciones militares siguen esta frontera:

1. liquidar producción y mantenimiento bajo lock hasta el instante de transición;
2. modificar la composición militar;
3. iniciar el siguiente intervalo con la composición nueva.

Esto evita cobrar retroactivamente una tropa recién entrenada, dejar de cobrar tropas antes de desaparecer y transferir el mantenimiento de un refuerzo antes de su llegada.

El worker respeta el orden de locks de colas y movimientos para no introducir deadlocks frente a cancelaciones concurrentes.

### Entrenamiento y cancelación

La cola persiste el coste histórico pagado. Una cancelación válida:

- elimina la cola;
- libera inmediatamente su reserva de mantenimiento;
- devuelve `80%` del coste persistido;
- no depende de precios futuros del catálogo.

### Protección contra lost updates de producción

G8 reveló una carrera que afectaba a la autoridad económica general y no solo a tropas.

Antes de la corrección, rutas de lectura como ciudad, estado y catálogo podían ejecutar `recalculate_resources(..., commit=True)` sobre una entidad `City` cargada previamente. Una secuencia posible era:

1. GET A carga una ciudad con `4000` recursos;
2. POST B bloquea la ciudad, paga un Noble y confirma aproximadamente `3000` de madera/piedra/hierro y `3900` de oro;
3. GET A termina después y confirma su snapshot antiguo de `4000 + producción`;
4. la cola del Noble queda creada, pero el saldo pagado es restaurado accidentalmente.

La solución en `app/services/production.py` conserva `commit=False` para transacciones económicas ya bloqueadas y endurece los ticks que sí hacen commit:

- recarga bajo `FOR UPDATE` cuando la base lo soporta;
- calcula el tick sin mutar primero la entidad ORM;
- confirma mediante compare-and-swap sobre recursos, lealtad y `last_production` observados;
- si otra transacción cambió cualquiera de esos valores, el UPDATE obsoleto afecta cero filas;
- se hace rollback del cálculo viejo, se recarga el estado confirmado y se reintenta;
- PostgreSQL obtiene serialización por row lock y la comprobación adicional protege también el entorno SQLite usado por Browser E2E.

`tests/test_production_authority.py` contiene una regresión que conserva deliberadamente un snapshot pre-pago en una sesión, paga desde otra sesión y luego intenta ejecutar el tick atrasado. El resultado esperado mantiene el pago más la producción legítima; nunca vuelve al saldo pre-pago.

## API, UI y wiki

`GET /troop/available` expone desde la fuente canónica coste/tiempo, requisitos, población, mantenimiento, estadísticas, velocidad, carga y capacidad disponible.

El estado de ciudad expone la capacidad militar económica junto con recursos y colas. Las tarjetas deshabilitan cantidades que no caben por población o mantenimiento, pero la decisión final siempre pertenece al servidor.

Las capas decorativas no interceptan puntero. G8 espera intro/loading reales y usa clics normales, sin `force`.

La wiki consume el mismo catálogo y no mantiene un segundo juego de números militares.

## Evidencia funcional — Validation #398

HEAD: `a56a4963fca13cce7ac592f74d8152f52a3c4933`  
Run: `32697399745`

### Backend

**SUCCESS**

- `214` pruebas recolectadas;
- `196 passed`;
- `18 skipped`;
- `4 warnings`;
- cobertura `74%`.

Incluyó `tests/test_bm0063_unit_balance.py`, las 9 pruebas de `tests/test_unit_upkeep.py`, lifecycle, población, producción, movimientos y contratos de fuente única.

También quedaron verdes compilación, Alembic `0001 -> 0009`, seed idempotente y downgrade `0009 -> base`.

BM-0063 no agrega migración: el schema head continúa en `0009`.

### PostgreSQL concurrency

**SUCCESS**

- `18 passed`;
- `3 warnings`;
- `28.28s`.

Prueba que una reserva de mantenimiento no puede sobreasignarse y que el orden de locks no introduce deadlocks en la matriz concurrente existente.

### Frontend, seguridad y operaciones

**SUCCESS**

- Frontend: `npm ci`, lint y build;
- dependency/security audit;
- G5 deployment, backup, restore y probes.

### Browser E2E

**SUCCESS** en #398:

- G2 sesión/realtime;
- G4 UX responsive/accesibilidad/i18n;
- G6 expansión;
- G7 investigación;
- G8 mantenimiento.

Fixture G8:

`prepared-g8:3:1:12:unit=noble:population=5:upkeep=0.5:capacity=8`

G8 comprueba que:

1. Noble usa población `5` y mantenimiento `0.5` oro/h;
2. la ciudad dispone de `8` oro/h sostenibles;
3. 17 Nobles usan 85 población pero exigen 8.5 oro/h y son bloqueados específicamente por mantenimiento;
4. 1 Noble sí puede entrar en cola;
5. la cola reserva 0.5 oro/h y deja 7.5 oro/h;
6. el coste se descuenta;
7. cancelar devuelve `204`;
8. la reserva vuelve a cero y el margen a 8.0 oro/h;
9. el reembolso es 80% del coste persistido.

### Imágenes Docker

**SUCCESS** para backend y frontend.

## Validation #399 — primera inestabilidad de G8

HEAD: `1d370063f4f1fd3ef4371ceb6d8ed4dff6bd7e19`  
Run: `32698194318`

Backend, PostgreSQL, Frontend, seguridad, G5, G2, G4, G6 y G7 quedaron verdes. G8 completó POST de entrenamiento y DELETE de cancelación, pero sus comparaciones de recursos usaban un snapshot demasiado temprano mientras la economía seguía produciendo.

Se endureció G8 para:

- serializar lecturas de catálogo/estado;
- tomar `beforeTraining` justo antes del POST;
- congelar el coste de ese instante;
- tomar `beforeCancel` justo antes del DELETE;
- comparar contra esos snapshots cercanos a cada escritura.

## Validation #401 — causa raíz: lost update real

HEAD: `08d1340a2c5aa05072b02fb6038fbbdb89ad3ff3`  
Run: `32698625993`

Volvieron a quedar verdes:

- Backend;
- PostgreSQL concurrency;
- Frontend;
- Dependency/security;
- G5 operations;
- G2;
- G4;
- G6;
- G7.

G8 volvió a completar las operaciones reales:

- `POST /troop/train?world_id=1` → `200`;
- `DELETE /troop/queue/1` → `204`.

La comparación just-in-time eliminó la hipótesis de snapshot antiguo del test. Antes del POST la ciudad tenía aproximadamente 4000 recursos; después de crear una cola con coste Noble de `1000/1000/1000/100`, el siguiente estado volvía a mostrar aproximadamente 4000. La diferencia coincidía exactamente con el coste que debía permanecer descontado.

La revisión del código y el interleaving de requests identificaron la causa: recálculos de producción iniciados desde GET podían confirmar una entidad `City` cargada antes del POST y sobrescribir el pago ya confirmado. El fallo de Browser era por tanto una detección válida de integridad económica.

Corrección posterior a #401:

- ticks con commit protegidos por reload/row lock;
- cálculo separado de la mutación ORM;
- compare-and-swap de `wood`, `stone`, `iron`, `gold`, `loyalty` y `last_production`;
- retry desde estado confirmado cuando existe conflicto;
- regresión explícita con una sesión de lectura obsoleta y una sesión de pago concurrente.

## Rollout operativo

BM-0063 no agrega migración, pero cambia balance, mantenimiento y endurece el commit de producción. Tratar como cambio de reglas y de integridad económica.

1. snapshot/backup;
2. respetar PD-009 para mundos ya iniciados;
3. desplegar API, frontend y worker compatibles como conjunto;
4. mantener schema `0009`;
5. verificar health/readiness y `/economy/balance_preview`;
6. verificar `/troop/available` y `/city/{id}/status`;
7. probar creación/cancelación de cola y reserva de mantenimiento;
8. comprobar que lecturas concurrentes no restauran un saldo gastado;
9. observar conflictos/retries y tiempos del worker antes de ampliar tráfico.

## Rollback

No se requiere `alembic downgrade` para revertir únicamente BM-0063.

Antes de rollback de código con tráfico real:

1. detener nuevas mutaciones económicas/entrenamientos;
2. pausar worker si cambia la interpretación de transiciones militares;
3. snapshot/backup;
4. inspeccionar colas y movimientos próximos;
5. procesar o cancelar explícitamente operaciones sensibles;
6. desplegar API/frontend/worker anteriores como conjunto compatible;
7. verificar saldos, colas, movimientos y mantenimiento antes de reabrir tráfico.

## Hallazgos corregidos durante BM-0063

1. mantenimiento legado nulo en un contrato antiguo;
2. mantenimiento antes solo informativo;
3. sobreasignación concurrente de capacidad sostenible;
4. cobro retroactivo al completar entrenamiento;
5. transferencia temporal incorrecta de mantenimiento en movimientos/refuerzos;
6. capas visuales que podían interceptar G8;
7. snapshots E2E demasiado alejados de las escrituras;
8. **lost update real** donde un GET de producción atrasado podía restaurar recursos gastados por un POST concurrente.

## Límite deliberado hacia BM-0064

BM-0063 declara final el catálogo estático de unidades y las restricciones de entrenamiento/población/mantenimiento.

BM-0064 debe cerrar el combate por rondas usando estos valores canónicos, incluyendo PvE/PvP, moral, suerte limitada/auditable, bajas, botín, retorno, reproducibilidad y resistencia a reintentos/doble resolución.

La inspección previa confirma que el combate actual todavía usa aleatoriedad global (`random.uniform`/`random.randint`), por lo que no puede reproducirse exactamente desde una semilla auditable. La resolución de movimientos ya protege contra doble procesamiento concurrente; BM-0064 debe extender esa transición existente, no crear un resolver paralelo.

## Criterio de cierre

BM-0063 solo puede cerrarse cuando el **HEAD que contiene esta corrección de integridad económica, su regresión y este documento** obtenga Validation completa verde, incluyendo Browser E2E e imágenes Docker.

Solo ese SHA será válido para marcar PR #96 como Ready y hacer squash merge.