# PARALLEL_BALANCE_AUDIT — Auditoría económica aislada

**Corte auditado:** `main@281de839102894ae1d3766156e17fc771ba0a9b9` (20-11-2026).
**Rama de trabajo:** `parallel/medievol-economy-20261120`.
**Autoridad:** Plan Maestro PD-002, PD-009, PD-010, PD-013, PD-016 y BM-0040.
**Versiones intactas:** `BALANCE_VERSION=2026.08.23-bm0063.1`, `COMMERCE_RULES_VERSION=2026.08.24-bm0066-v1`.

## Lectura inicial y fronteras

Se revisaron el Plan Maestro, `docs/BM0040_BALANCE_VALIDATION.md`, el catálogo actual de `balance.py`, las pruebas `tests/test_balance_single_source.py`, `tests/test_economy.py`, `tests/test_bm0063_unit_balance.py`, y las llamadas de construcción, producción y mantenimiento, sin modificar esas áreas. En el corte inicial había un PR abierto (#140, arranque del worker/scheduler), sin cambios propuestos para `balance.py`.

BM-0040 establece una sola fuente numérica. BM-0060 incorpora madera/piedra/hierro/oro y mantenimiento real. BM-0061 fija ciudades, campamentos y puntos; BM-0062/0063 fijan progresión de edificios, investigación y tropas. Esta auditoría no rebalancea las reglas, no cambia mundos persistentes ni añade otro catálogo.

## Correcciones de seguridad de entrada

1. **Niveles de construcción no enteros.** `get_building_cost` aceptaba `1.5`, `1.0` y `True`; el primero generaba cotizaciones para niveles inexistentes (exponente fraccionario) y `get_building_build_time` producía tiempos no canónicos. Ambos rechazan tipos que no sean enteros genuinos, antes de calcular; los límites 1..máximo y las fórmulas legítimas no cambian.
2. **Capacidades con coerción silenciosa.** `get_storage_capacity` y la población de ciudades truncaban `2.9` a nivel 2 o aceptaban textos numéricos y booleanos; ahora rechazan esos tipos. El suelo histórico `max(nivel, 0)` para enteros negativos se mantiene para no alterar una recuperación de datos legacy.
3. **Tipos de asentamiento desconocidos.** `get_population_capacity` trataba un tipo inválido como `city`. Ahora acepta solo `city` y `camp`; no modifica los límites de ninguno. Los campamentos siguen sin recibir bonificación por granjas.

No hay cambios en costos, tiempos, factores de crecimiento, producción, mantenimiento, requisitos, límites máximos, identificadores de unidades/edificios, eventos, snapshots o versión de balance.

## Cobertura automatizada añadida

`tests/test_parallel_balance_contract.py` cubre:

- Perfil explícito de los cuatro recursos, tasas, capacidad y versiones del catálogo.
- Coincidencia de órdenes/tablas, ausencia de claves militares duplicadas, integridad de requisitos y equivalencia de alias legacy.
- Todos los edificios, con niveles inicial, 2, intermedio y máximo (incluido nivel 100 de la Maravilla); valores de costo no redondeados, crecimiento 1.20 y tiempo lineal.
- Fuera de rango, fraccionarios, textos, `None`, booleanos, `Decimal`, `NaN` e infinito.
- Almacenamiento y población en niveles 0, 1, 2, 10, 20, enteros negativos y asentamientos no canónicos.
- Coste de campamento + promoción equivalente a ciudad directa, en recursos y puntos; producción reducida y mantenimiento de tropas en oro.
- Snapshot desacoplado por copia profunda y alias militares sin mutación de la autoridad.

**Ejecutar:** `cd batalla_medieval_backend/.. && PYTHONPATH=batalla_medieval_backend pytest -q tests/test_parallel_balance_contract.py tests/test_balance_single_source.py tests/test_economy.py tests/test_bm0063_unit_balance.py`. Validar además la suite completa y CI del HEAD final antes de aprobar merge. El PR no se fusiona ni se despliega desde este hilo.

## Bloqueo de producto detectado, sin corregir (coordinación)

**P1 — La Maravilla del Mundo no puede alcanzar el nivel de victoria con el almacén máximo canónico.**

- Almacén máximo permitido por `BUILDING_MAX_LEVELS["warehouse"] == 20`: `5000 + 2000 * 20 = 45000` unidades **por recurso**.
- Maravilla: costo base de madera/piedra/hierro `10000`, crecimiento por nivel `1.20 ** (nivel - 1)`; nivel 9 = `42998.17` por recurso (por debajo del límite), nivel 10 = `51597.80` por recurso (**supera 45000**).
- El objetivo `BUILDING_MAX_LEVELS["world_wonder"] == 100` cuesta aproximadamente `690149787683.45` por cada uno de los tres materiales al nivel final. Si se aplican esos límites en el gasto canónico, no puede completarse el nivel 10 y, por ende, la condición de victoria.
- Confirmación arquitectónica: `production.get_storage_limit` llama a `balance.get_storage_capacity` en función del nivel almacenado. El límite de almacenamiento no aumenta por la propia Maravilla.

**Acción para el chat coordinador:** decidir y versionar explícitamente la política de construcción de la Maravilla (costos por nivel, almacenamiento, entregas por etapas u otra solución). Evaluar migración/compatibilidad por mundo antes de cualquier cambio. Esta rama **no** cambia valores aprobados ni el modelo de la victoria.

## Riesgos fuera de alcance

- **Balance ya persistido por mundo (PD-009):** el módulo exporta un catálogo live global; esta auditoría no demuestra por sí sola cómo se inmovilizan las reglas para mundos históricos. Requiere revisión de los servicios/modelos de mundo por el coordinador.
- **Atomicidad e idempotencia (PD-010):** precios calculados correctamente no prueban bloqueos de filas ni doble gasto. Los servicios de construcción, mercado, producción y mantenimiento deben validarse en sus propias ramas.
- **Representación numérica:** precios y producción siguen usando `float` y pueden generar fracciones. La auditoría conserva el redondeo histórico, incluido el reembolso del 80%; cualquier política monetaria nueva exige decisión de producto y compatibilidad de datos.
- **Integridad de constantes en memoria:** ciertos servicios usan alias compartidos del catálogo por compatibilidad BM-0040. Los snapshots públicos son copias independientes; no se introducen copias paralelas mutables.
