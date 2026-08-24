# BM-0063 — Validación de catálogo final de unidades y mantenimiento

## Estado

**VALIDADO FUNCIONALMENTE** en el HEAD `a56a4963fca13cce7ac592f74d8152f52a3c4933` mediante **Validation #398** (`run_id=32697399745`).

Este hito cierra el catálogo estático y autoritativo de las nueve unidades de v1.0 y hace efectivo el mantenimiento económico de tropas. La fuente única de balance utilizada por este cierre es `BALANCE_VERSION = "2026.08.23-bm0063.1"`.

BM-0064 conserva estos valores de unidad como catálogo canónico y es responsable de cerrar cómo se resuelven esos valores dentro del combate final por rondas. No debe introducir un segundo catálogo militar.

## Alcance entregado

### Catálogo canónico de nueve unidades

La fuente única `app/services/balance.py` fija para cada unidad:

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

El orden canónico es:

1. Lancero Común (`basic_infantry`);
2. Soldado de Acero (`heavy_infantry`);
3. Arquero Real (`archer`);
4. Jinete Explorador (`fast_cavalry`);
5. Caballero Imperial (`heavy_cavalry`);
6. Infiltrador (`spy`);
7. Quebramuros (`ram`);
8. Tormenta de Piedra (`catapult`);
9. Noble (`noble`).

La investigación continúa usando el contrato temporizado cerrado en BM-0062. BM-0063 fija los valores finales de entrenamiento, población, mantenimiento, movimiento, carga y estadísticas base que acompañan a esas tecnologías.

### Capacidad militar sostenible por mantenimiento

El mantenimiento deja de ser un dato informativo y pasa a ser una restricción autoritativa del servidor.

Para cada ciudad se calculan y exponen, como mínimo:

- capacidad sostenible de mantenimiento en oro por hora;
- mantenimiento usado por tropas existentes;
- mantenimiento reservado por entrenamientos todavía en cola;
- margen de mantenimiento todavía disponible;
- indicador de sostenibilidad.

La producción canónica base de oro es `8.0/h`. La capacidad efectiva utilizada por las reglas se obtiene desde la economía autoritativa de la ciudad, no desde un número enviado por el cliente.

Antes de aceptar un entrenamiento, el servidor comprueba simultáneamente recursos, población, requisitos, slots de entrenamiento y mantenimiento disponible. Una solicitud se rechaza si el nuevo ejército excedería el margen sostenible aunque todavía exista población y recursos suficientes.

Las colas de entrenamiento reservan mantenimiento desde que son aceptadas. Esto evita que varias solicitudes válidas por separado sobrevendan el mismo margen económico.

### Tropas estacionadas, desplegadas y en movimiento

El mantenimiento se calcula sobre la composición militar autoritativa y no desaparece por enviar tropas fuera de la ciudad.

Las transiciones militares respetan una frontera temporal explícita:

1. se liquida producción y mantenimiento de la ciudad bajo lock hasta el instante de la transición;
2. después se modifica la composición militar;
3. el siguiente intervalo usa la nueva composición.

Esto evita cobrar retroactivamente mantenimiento a una tropa recién entrenada y evita dejar de cobrar retroactivamente tropas que existieron durante parte del intervalo.

En refuerzos, la ciudad remitente mantiene el coste hasta la llegada efectiva. Solo después de resolver la llegada puede cambiar la responsabilidad de mantenimiento según el nuevo estado militar.

### Entrenamiento y cancelación

El flujo autoritativo conserva el coste histórico pagado por una cola. Al cancelar un entrenamiento antes de completarse:

- la cola desaparece;
- la reserva de mantenimiento se libera inmediatamente;
- se devuelve el `80%` del coste pagado persistido;
- el cálculo no depende de que el balance futuro conserve exactamente los mismos precios.

### Atomicidad y concurrencia

El cierre BM-0063 protege la capacidad económica bajo concurrencia real de PostgreSQL.

Las solicitudes de entrenamiento bloquean la ciudad antes de decidir si existe margen sostenible. El cálculo incluye tanto tropas activas como mantenimiento reservado por colas existentes.

Una prueba concurrente con slots múltiples hace que dos entrenamientos simultáneos compitan por el mismo margen de oro. La garantía esperada es que únicamente la operación que todavía cabe dentro del límite pueda reservarlo; la segunda no puede sobreasignar capacidad usando una lectura obsoleta.

El worker también respeta el orden de locks existente. Las colas de tropa se procesan con su ciudad antes de las transiciones de movimientos que afectan ciudades, evitando introducir una inversión de locks frente a la cancelación de entrenamiento.

## API, estado y UI

`GET /troop/available` expone desde la fuente canónica los valores necesarios para mostrar y validar cada unidad, incluyendo:

- coste y tiempo de entrenamiento;
- requisitos;
- población por unidad;
- mantenimiento por hora;
- estadísticas base de combate;
- velocidad y carga;
- población disponible;
- margen de mantenimiento disponible;
- si la unidad puede entrenarse en el estado actual.

El estado agregado de ciudad expone la capacidad militar económica junto con recursos y colas. La barra de recursos puede mostrar mantenimiento usado frente a capacidad sostenible.

Las tarjetas de tropas muestran los valores canónicos y deshabilitan el entrenamiento cuando la cantidad solicitada no cabe por población o mantenimiento. Esta validación de UI es solo una ayuda: la decisión final siempre pertenece al servidor.

Los overlays decorativos de las tarjetas no interceptan los controles. El recorrido E2E espera correctamente las pantallas reales de introducción/carga y usa clics normales, sin `force` ni bypass del comportamiento del jugador.

La wiki/ayuda consume el mismo catálogo para publicar población, mantenimiento, movimiento, carga y estadísticas; no conserva un segundo juego de números manuales.

## Evidencia automática

### Backend

Validation #398 (`run_id=32697399745`):

- `196 passed`;
- `18 skipped`;
- `4 warnings`;
- cobertura total: `74%`.

La ejecución recolectó `214` pruebas. Permanecieron verdes, entre otras:

- `tests/test_bm0063_unit_balance.py`;
- las `9` pruebas de `tests/test_unit_upkeep.py`;
- lifecycle de unidades;
- población;
- producción autoritativa;
- movimientos y worker multiplayer;
- contratos de fuente única de balance.

Los 18 skips del job Backend corresponden a garantías que requieren locks PostgreSQL y se ejecutan en el job dedicado de concurrencia.

La misma Validation confirmó:

- compilación del backend;
- upgrade completo Alembic `0001 -> 0009`;
- seed canónico ejecutado dos veces de forma idempotente;
- downgrade completo `0009 -> base`.

BM-0063 **no agrega una migración de esquema**: el head de base continúa siendo `0009`.

### PostgreSQL concurrency

Job `PostgreSQL concurrency`: **SUCCESS**.

Resultado exacto:

- `18 passed`;
- `3 warnings`;
- `28.28s`.

El job ejecuta las garantías concurrentes de economía, onboarding, construcción, unidades, movimientos, mercado, expansión, simulación G3 y tutorial.

Para BM-0063 esto prueba que:

- una reserva de mantenimiento no puede ser sobrevendida por solicitudes simultáneas;
- el lock de ciudad protege el cálculo de capacidad sostenible;
- el nuevo orden de liquidación de entrenamiento/movimiento no introdujo deadlocks en la matriz concurrente existente.

### Frontend

Job `Frontend`: **SUCCESS**.

- instalación reproducible con `npm ci`;
- lint;
- build de producción.

### Dependencias y seguridad

Job `Dependency and security audit`: **SUCCESS**.

- auditoría Python;
- análisis estático de seguridad;
- auditoría de dependencias frontend según el gate del proyecto.

### Operaciones

Job `G5 operations recovery`: **SUCCESS**.

Permanecen verdes las verificaciones de deployment, backup, restore y probes operativos.

### Browser E2E

Job `Browser E2E`: **SUCCESS**.

Resultado exacto de los recorridos aceptados:

- `Browser smoke passed: durable session and authenticated realtime are stable, no console errors or HTTP 4xx/5xx`;
- `G4 UX smoke passed: all visible routes at 390x844, keyboard focus, 250ms API delay and persisted es/en switching`;
- `G6 expansion browser journey passed`;
- `G7 research browser journey passed`;
- `G8 BM-0063 unit upkeep browser journey passed`.

Fixture G8 confirmado por el mismo run:

`prepared-g8:3:1:12:unit=noble:population=5:upkeep=0.5:capacity=8`

G8 demuestra de extremo a extremo que:

1. Noble publica `5` de población y `0.5` oro/h de mantenimiento;
2. la ciudad preparada tiene capacidad sostenible de `8` oro/h;
3. solicitar `17` Nobles usa solo `85` de población, pero exige `8.5` oro/h, por lo que el bloqueo observado es específicamente económico;
4. entrenar `1` Noble sí es válido;
5. la cola reserva `0.5` oro/h y reduce el margen a `7.5` oro/h;
6. el coste de cuatro recursos se descuenta;
7. `DELETE /troop/queue/1` devuelve `204`;
8. la cancelación libera la reserva y restaura el margen sostenible a `8.0` oro/h;
9. se aplica el reembolso del `80%` del coste pagado.

Evidencia HTTP relevante del mismo run:

- `POST /troop/train?world_id=1` → `200`;
- lecturas de `/city/{id}/status` y `/troop/available` → `200`;
- `DELETE /troop/queue/1` → `204`.

### Imágenes Docker

Job `Container images`: **SUCCESS**.

- imagen backend construida correctamente;
- imagen frontend construida correctamente.

## Rollout operativo

BM-0063 no requiere una migración Alembic nueva, pero sí cambia reglas de balance y mantenimiento. El despliegue debe tratarse como un cambio de reglas del mundo, no como un simple cambio cosmético.

Procedimiento recomendado:

1. realizar snapshot/backup de base de datos;
2. identificar qué mundos pueden recibir `2026.08.23-bm0063.1` según la política de balance versionado;
3. desplegar API, frontend y worker compatibles entre sí;
4. no ejecutar una migración adicional: el esquema esperado continúa en `0009`;
5. verificar health/readiness y `/economy/balance_preview`;
6. verificar `/troop/available` y `/city/{id}/status` en una ciudad de control;
7. comprobar creación/cancelación de una cola y su reserva de mantenimiento;
8. observar errores, bloqueos y tiempos del worker antes de ampliar tráfico.

PD-009 exige que un cambio de balance no altere silenciosamente mundos ya iniciados. La operación debe respetar la versión de reglas asignada a cada mundo cuando ese mecanismo quede activado para producción.

## Rollback

El rollback de BM-0063 es **compatible con el esquema actual** porque no existe una migración nueva que revertir.

Aun así, un rollback de código durante tráfico real puede cambiar la interpretación de colas o de mantenimiento. Antes de volver a una versión anterior:

1. detener temporalmente nuevas solicitudes de entrenamiento;
2. pausar el worker si la versión anterior interpreta de forma distinta las transiciones militares;
3. sacar snapshot/backup;
4. inspeccionar colas de tropa activas y movimientos próximos a resolverse;
5. procesar o cancelar explícitamente las operaciones cuyo comportamiento pudiera cambiar entre versiones;
6. desplegar API/frontend/worker de la versión anterior como conjunto compatible;
7. verificar economía, colas, movimientos y mantenimiento antes de reabrir tráfico.

El coste histórico de una cola permite conservar el reembolso exacto aunque cambien los precios, pero no se debe asumir que una versión anterior aplicará la misma regla de mantenimiento a una cola ya creada bajo BM-0063.

No se requiere ni se recomienda hacer `alembic downgrade` para revertir únicamente BM-0063.

## Hallazgos corregidos durante BM-0063

1. **Mantenimiento legado nulo**: un contrato antiguo todavía asumía `0.0` para la infantería básica; el catálogo final fija mantenimiento positivo y la prueba fue actualizada.
2. **Mantenimiento solo informativo**: ahora limita autoritativamente cuánto ejército sostenible puede entrenarse.
3. **Sobreasignación por colas concurrentes**: las reservas activas forman parte del cálculo bajo lock y PostgreSQL prueba la garantía.
4. **Cobro retroactivo al completar entrenamiento**: el worker liquida el intervalo económico antes de incorporar la nueva tropa.
5. **Transferencia temporal incorrecta en movimientos/refuerzos**: el intervalo previo a la llegada se liquida con la composición anterior; la responsabilidad cambia únicamente después de la transición.
6. **Interferencia de capas visuales en G8**: las capas puramente decorativas no capturan puntero y el E2E espera las pantallas reales de arranque antes de interactuar.

## Límite deliberado hacia BM-0064

BM-0063 declara final el **catálogo estático de unidades** y las restricciones de entrenamiento/población/mantenimiento.

BM-0064 debe cerrar el sistema de combate por rondas utilizando estos valores canónicos, incluyendo:

- PvE y PvP;
- moral;
- suerte limitada/auditable;
- bajas;
- botín;
- retorno;
- reproducibilidad desde semilla/estado auditable;
- resistencia a reintentos y doble resolución.

BM-0064 puede definir cómo se combinan ataque y defensas dentro de cada ronda, pero no debe duplicar ni volver a definir silenciosamente las estadísticas base de las unidades.

## Criterio de cierre

BM-0063 puede considerarse funcionalmente cerrado cuando **este documento**, como último cambio de cierre, obtenga una nueva Validation completa verde sobre su propio HEAD.

Solo ese SHA documental final será válido para marcar PR #96 como Ready y fusionarlo.