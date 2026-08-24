# BM-0062 — Validación de catálogo de edificios e investigación

## Estado

**VALIDADO FUNCIONALMENTE** en el HEAD `494a9ae89f198d2d55f0f9c0ddc2e0f4d0bdbfe6` mediante **Validation #362** (`run_id=32693460335`).

Este hito cierra el catálogo operativo de edificios y convierte la investigación de unidades en un proceso persistente, temporizado y autoritativo. Los valores finales de entrenamiento, combate y mantenimiento de tropas permanecen expresamente reservados para BM-0063.

## Alcance entregado

### Catálogo canónico de edificios

La fuente única de balance define el orden, nombre, descripción, coste, requisitos, nivel máximo, tiempo base de construcción y efecto de cada edificio:

- Ayuntamiento (`town_hall`)
- Cuartel (`barracks`)
- Establo (`stable`)
- Academia Militar (`academy`)
- Muralla (`wall`)
- Mercado (`market`)
- Hacienda (`farm`)
- Almacén (`warehouse`)
- Herrería (`smithy`)
- Taller (`workshop`)
- Iglesia (`church`)
- Catedral (`cathedral`)
- Maravilla del Mundo (`world_wonder`)

Los efectos relevantes están expuestos de forma machine-readable y utilizados por las reglas autoritativas del servidor: defensa de Muralla, comerciantes de Mercado, capacidad de población de Hacienda, almacenamiento, acceso/slot de Academia, puntos de expansión de Iglesia/Catedral y condición de victoria de Maravilla del Mundo.

La Academia Militar deja de ser una pantalla decorativa: es un edificio real y requisito explícito de las tecnologías investigables.

### Población efectiva

BM-0062 separa dos conceptos para evitar acumulación accidental de bonos:

- `city.population_max`: capacidad base persistida de la ciudad/campamento;
- `population_capacity`: capacidad efectiva calculada por el servidor, incluyendo el efecto de Hacienda.

Hacienda aporta `25` habitantes de capacidad por nivel en ciudad. El API de estado expone población usada y capacidad efectiva, y entrenamiento consume esa capacidad autoritativa.

Se añadió una regresión específica para impedir que los endpoints GET asignen la capacidad efectiva al objeto ORM y la persistan por autoflush, lo que anteriormente podía causar doble conteo del bono.

### Investigación persistente y temporizada

La migración Alembic `0009_research_queue.py` crea `research_queue` con:

- `city_id`;
- `tech_name`;
- `finish_time`;
- `paid_cost` JSON;
- un índice único por ciudad (`ux_research_queue_city`), garantizando un único slot activo;
- un índice único por ciudad/tecnología (`ux_research_queue_city_tech`).

El ciclo autoritativo es:

1. validar tecnología, Academia y demás edificios requeridos;
2. bloquear/recalcular recursos de la ciudad;
3. verificar que no exista otra investigación activa;
4. cobrar el coste exacto de cuatro recursos;
5. persistir ese pago en `paid_cost`;
6. crear la cola con `finish_time`;
7. no desbloquear la tecnología todavía;
8. el worker consume colas vencidas con bloqueo PostgreSQL y crea `Research` exactamente una vez;
9. sincroniza el JSON legado de tecnologías investigadas y elimina la cola.

La cancelación solo puede ocurrir antes del vencimiento y devuelve el `80%` del **pago histórico persistido**, no de un coste recalculado con un balance futuro. El reembolso respeta el límite de almacenamiento.

### API y UI

Contratos principales:

- `POST /troop/research?world_id=...` → `201 Created` con `ResearchQueue`;
- `GET /queue/research?world_id=...` → investigaciones activas del usuario/mundo;
- `DELETE /queue/research/{queue_id}` → `204 No Content` al cancelar correctamente;
- `/troop/available` expone coste, tiempo, requisitos, estado en cola y `finish_time`;
- el estado agregado de ciudad incluye `research_queue`.

La vista Academia:

- muestra costes y duración canónicos;
- muestra la investigación activa y temporizador;
- bloquea un segundo estudio mientras el slot está ocupado;
- permite cancelar antes del vencimiento;
- refresca disponibilidad/cola sin simular una finalización instantánea.

La wiki/ayuda se genera desde el catálogo canónico y deja de documentar el tiempo genérico legado de 420 segundos.

## Evidencia automática

### Backend

Validation #362:

- `183 passed`;
- `17 skipped`;
- `4 warnings`;
- cobertura total: `74%`.

Los 17 skips corresponden a garantías que requieren locks PostgreSQL y se ejecutan separadamente en el job `PostgreSQL concurrency`.

La misma ejecución validó:

- compilación del backend;
- upgrade completo Alembic `0001 -> 0009`;
- seed canónico ejecutado dos veces de forma idempotente;
- downgrade completo `0009 -> base`;
- prueba dedicada `tests/test_research_queue_migration.py`;
- regresiones de edificios, capacidad de población, contratos BM-0062 y límites del mapa.

### PostgreSQL concurrency

Job `PostgreSQL concurrency`: **SUCCESS**.

Incluye `tests/test_unit_concurrency.py`, que verifica como mínimo:

- dos solicitudes concurrentes de la misma investigación producen exactamente una cola y un solo cobro;
- dos workers concurrentes que procesan la misma investigación vencida producen exactamente una fila `Research` y eliminan la cola una sola vez.

También permanecen verdes los demás contratos concurrentes del juego: economía, onboarding, construcción, movimientos, mercado, expansión, tutorial y simulación G3.

### Frontend

Job `Frontend`: **SUCCESS**.

- `npm ci`;
- lint;
- build de producción.

### Dependencias y seguridad

Job `Dependency and security audit`: **SUCCESS**.

- auditoría de dependencias Python;
- análisis estático Bandit;
- auditoría de dependencias frontend bloqueadas por el proyecto.

### Operaciones

Job `G5 operations recovery`: **SUCCESS**.

Se mantienen verdes las verificaciones de deployment, backup, restore y probes operativos.

### Browser E2E

Job `Browser E2E`: **SUCCESS**.

Resultado exacto de los recorridos aceptados:

- `Browser smoke passed: durable session and authenticated realtime are stable, no console errors or HTTP 4xx/5xx`;
- `G4 UX smoke passed: all visible routes at 390x844, keyboard focus, 250ms API delay and persisted es/en switching`;
- `G6 expansion browser journey passed`;
- `G7 research browser journey passed`.

Evidencia HTTP relevante observada en el mismo run:

- promoción de campamento: `POST /expansion/camps/10/promote` → `200`;
- fundación territorial: `POST /expansion/found` → `200`;
- inicio de investigación: `POST /troop/research?world_id=1` → `201`;
- lectura de cola/estado/disponibilidad → `200`;
- cancelación de investigación: `DELETE /queue/research/1` → `204`.

G7 valida además que:

- dos tecnologías preparadas son inicialmente elegibles;
- tras iniciar una, la cola persiste y no existe desbloqueo anticipado;
- la segunda queda deshabilitada por ocupación del slot;
- el cobro corresponde al coste canónico;
- al cancelar, la cola desaparece, la tecnología sigue sin investigar y se aplica el reembolso del 80%;
- el segundo estudio vuelve a quedar habilitado.

### Imágenes Docker

Job `Container images`: **SUCCESS**.

- imagen backend construida correctamente;
- imagen frontend construida correctamente.

## Migración 0009: rollout

Procedimiento recomendado:

1. realizar snapshot/backup de base de datos;
2. desplegar código compatible con BM-0062;
3. ejecutar `alembic upgrade head` para crear `research_queue`;
4. arrancar/reiniciar API y worker;
5. verificar health/readiness;
6. comprobar `POST /troop/research`, `GET /queue/research` y procesamiento del worker;
7. observar logs/errores antes de ampliar tráfico.

La migración es aditiva: las investigaciones ya completadas en `research` permanecen intactas.

## Rollback de 0009

La prueba dedicada demuestra que `0009 -> 0008` elimina `research_queue` y **preserva las investigaciones ya completadas** en `research`.

Sin embargo, un downgrade después de recibir tráfico real **es destructivo para investigaciones activas**: al eliminar `research_queue` se pierden `finish_time` y `paid_cost`, por lo que ya no existiría información suficiente para completar o reembolsar esas operaciones correctamente.

Antes de hacer downgrade en un entorno con tráfico:

1. detener nuevas escrituras de investigación y detener el worker;
2. sacar snapshot/backup de la base;
3. exportar las filas activas de `research_queue` y su `paid_cost`;
4. procesar las colas ya vencidas o, para las aún activas, cancelarlas/reembolsarlas explícitamente usando el `paid_cost` persistido;
5. confirmar `research_queue` vacío;
6. ejecutar `alembic downgrade 0008`;
7. desplegar la versión anterior compatible.

No se considera seguro ejecutar un downgrade destructivo de `0009` después de tráfico real sin manejar primero las colas activas.

## Hallazgos corregidos durante BM-0062

1. **Investigación instantánea heredada**: sustituida por cola persistente y temporizada.
2. **Academia decorativa**: convertida en edificio real con requisitos canónicos.
3. **Capacidad de población/autoflush**: se evitó persistir el bono efectivo de Hacienda dentro de `population_max`.
4. **E2E dependiente del idioma**: G7 dejó de depender de una cadena localizada exacta y valida estado durable/API.
5. **Mapa fuera de límites**: `/map/tiles` podía devolver coordenadas negativas o superiores a `map_size` cuando el radio tocaba un borde. El router ahora limita la ventana al mundo válido y `tests/test_expansion_api.py` verifica ambos extremos.

## Límite deliberado hacia BM-0063

BM-0062 fija el catálogo de edificios y el **coste/requisito/duración de investigación** de unidades, pero no declara cerrados los números finales de tropas.

BM-0063 es responsable de cerrar:

- catálogo final de tropas;
- coste final de entrenamiento;
- tiempo final de entrenamiento;
- mantenimiento/upkeep;
- consumo/capacidad;
- estadísticas y números finales de combate.

Esto evita mezclar en BM-0062 dos dimensiones de balance distintas y mantiene trazabilidad entre progresión de ciudad e identidad militar.

## Criterio de cierre

BM-0062 puede considerarse funcionalmente cerrado cuando este documento, como último cambio documental, obtenga una nueva Validation completa verde sobre su propio HEAD. Solo ese SHA final será válido para marcar PR #95 como Ready y fusionarlo.