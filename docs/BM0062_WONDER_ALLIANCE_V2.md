# BM-0062 — Maravilla colaborativa y balance versionado

## Problema y compatibilidad

En las reglas antiguas la Maravilla requiere más recursos de los que
permite el almacén en el nivel 10. La victoria al nivel 100 es materialmente
inalcanzable y el tiempo de obra secuencial supera los 105 días.

Este cambio crea dos contratos. Los mundos históricos mantienen sus
reglas, costos, tiempos, colas y semillas de combate originales:
**legacy-v1**. La migración SQL añade el campo wonder_rules_version con
valor por defecto legacy-v1 para cada mundo ya existente, sin cambiarlo.

Los mundos de nueva creación por administración, generador o semilla
se etiquetan **alliance-v2**. El administrador puede pedir explícitamente
legacy-v1 al crear otro mundo. Ningún endpoint permite convertir mundos
activos y no se modifica BALANCE_VERSION.

## Reglas alliance-v2

- Los demás edificios, tropas, recursos, almacenes y operaciones no cambian.
- Para alcanzar el nivel n de la Maravilla, cada recurso cuesta
  ceil(costo_base * 1.02 ** (n-1)). Los costos base canónicos son madera,
  piedra e hierro 10.000 cada uno, y oro 2.500.
- Tiempo de obra por nivel: 1200 + 180*n segundos. Los 100 niveles suman
  1.029.000 segundos (~11,91 días) solo de construcción.
- Cada nivel dispone de un fondo persistentemente asociado a mundo, ciudad,
  dueño de la ciudad, alianza patrocinadora y nivel objetivo.
- Solo miembros activos de esa misma alianza y mundo pueden aportar,
  exclusivamente desde una ciudad propia en ese mundo. Se exigen los
  prerrequisitos canónicos: Casa Central 20, Depósito 20, Catedral 10.
- Aportaciones positivas en unidades enteras, nunca superiores al saldo
  del donante ni al faltante del fondo. World/ciudad origen/destino y
  proyecto se validan y bloquean en una sola transacción.
- Cada aportación tiene una clave idempotente de 8 a 80 caracteres, única
  por jugador y mundo. Los reintentos idénticos no duplican cargos;
  reutilizar una clave con distinta carga se rechaza.
- Solo cuando se han aportado los cuatro recursos se habilita la cola.
  Esa cola no vuelve a gastar recursos.
- Cancelar una cola financiada devuelve el proyecto al estado financiado,
  **sin devolver liquidez**. Se puede volver a iniciar la obra sin pagar
  otra vez. Abandonar la alianza, perder la ciudad o cerrarse el mundo
  tampoco genera reembolso: los depósitos son irreversibles.
- Los proyectos se vinculan al dueño y alianza del momento de financiar.
  Una ciudad transferida no puede gastar el fondo de su antiguo dueño.
  Una cola sin fondos válidos se bloquea sin cerrar el mundo.
- La alianza ganadora es la patrocinadora fijada en la financiación del
  nivel 100, no una alianza nueva que se unió en el último momento.
- El exportador de datos del jugador incluye únicamente sus fondos propios
  y aportaciones escritas por él. No filtra secretos de otros miembros.

## API e interfaz

GET /building/wonder/funding?world_id=...&city_id=... devuelve estado,
costo, aportado, restante y disponibilidad de la cola. Solo lo pueden leer
integrantes de la alianza de la ciudad.

POST /building/wonder/contribute?world_id=... acepta ciudad origen,
ciudad destino, clave idempotente y cantidad entera por recurso; aplica
autorización real en backend.

Edificios muestra el fondo de los mundos alliance-v2 y permite aportar
desde la ciudad actual a un destino propio o aliado. El mapa dispone de
un acceso contextual a la aportación. Los mundos antiguos no muestran ni
aceptan estos endpoints.

## Migración y seguridad

Alembic 0020 crea tablas de fondo y libro de aportaciones y fija el
contrato legacy-v1 en mundos existentes. Las claves foráneas a ciudades,
usuarios y donaciones **no** tienen borrado en cascada: la política de
eliminación de cuentas necesita revisión específica. Se amplía el
inventario de dependencias BM-0090 y la exportación privada permitida.

No realizar migraciones silenciosas de mundos activos. Cualquier conversión
histórica requiere proceso de producto independiente, política de colas
vigentes, aceptación por jugadores, ensayo de migración y rollback.

## Pruebas y límites

Se prueba el presupuesto de niveles 1/9/10/50/100, intervalos y total,
contribuciones aliadas, aislamiento de mundos, exceso y escasez, replay,
construcción, cancelación, colas fraudulentas, cierre y victoria. El
trabajo PostgreSQL incluye dos donantes concurrentes por SQL real.

La duración real de la temporada depende de producción, velocidad,
economía PvP y tamaño de alianzas; requerirá simulación y aprobación
antes de lanzamiento. Los mundos legados conservan sus limitaciones hasta
una migración explícita. Esta implementación no autoriza producción ni G10.

## Regresión real de navegador en aislamiento

`parallel-journey-wonder-funding.mjs` utiliza dos cuentas distintas, una alianza
real, recursos de ciudades reales en SQLite desechable y llamadas a la API
verdadera. Comprueba financiación en dos aportaciones, cuenta de recursos,
cola de la obra, cancelación sin devolución, y ausencia de errores JS. Se
inyecta mediante `scripts/run_parallel_journey_ci.sh` después de detener el
servidor del escenario anterior, y el script rechaza un backend preexistente
que pudiera responder contra otra base de datos. El panel flotante de
edificios es decorativo y no puede capturar clics. Los callbacks de intro y
carga son estables para que re-renderizados no reinicien timers de ocultación.

**Resultado de la ejecución focalizada sobre test SQLite independiente:**
5 escenarios de navegador aprobados, incluyendo el clic físico de
«Construir» y la devolución a estado financiado tras cancelar.

## Auditoría local de aportaciones

- En una aportación nueva, la respuesta se calcula antes del commit. Antes
  se leía el fondo después de liberar los bloqueos y la respuesta podía
  incorporar una aportación confirmada por otra sesión en ese intervalo.
- Un reintento idempotente válido devuelve el estado del fondo y termina
  su transacción de lectura. Antes retenía los bloqueos hasta el cierre de
  la sesión, aunque el servicio ya había devuelto la respuesta.
- Las regresiones cubren ambos casos y el rechazo de una cola cuando falta
  una sola unidad de oro en los niveles 9, 10 y 50.
