# BM-0064 — Validación del combate final reproducible por rondas

## Estado

BM-0064 alcanzó un corte funcional completamente verde en **Validation #419** (`run_id=32730864548`) sobre el HEAD `58e612cc60b20ca410cc54de0f515f5125f56a23`.

Ese corte valida en conjunto el motor autoritativo, la persistencia de informes, la concurrencia de movimientos, el retorno con supervivientes y botín, la UI de auditoría, los recorridos Browser G2–G9 y las imágenes Docker.

El cierre definitivo del PR exige una Validation completa verde adicional sobre el HEAD que contenga **este documento**. Solo ese SHA documental puede marcarse Ready y fusionarse.

Versiones relevantes:

- `COMBAT_ALGORITHM_VERSION = "2026.08.24-bm0064-rounds-v1"`;
- `BALANCE_VERSION = "2026.08.23-bm0063.1"`;
- máximo `8` rondas instantáneas;
- escala de bajas por ronda `0.35`.

BM-0064 no introduce un segundo catálogo militar: consume las estadísticas canónicas cerradas en BM-0063.

## Criterios del plan maestro cubiertos

BM-0064 implementa el criterio de aceptación del plan maestro: combate PvE/PvP con moral, suerte, bajas, botín y retorno reproducibles y resistentes a reintentos.

También preserva las decisiones de producto ya fijadas:

- el servidor es la única autoridad de combate y botín;
- el combate se resuelve instantáneamente por rondas, sin terreno ni obstáculos tácticos;
- las ciudades de jugadores no pueden ser conquistadas;
- únicamente ciudades bárbaras (`owner_id = null`) pueden cambiar de propietario mediante Noble;
- las mutaciones militares deben ser atómicas, idempotentes y resistentes a concurrencia.

## Motor autoritativo

El motor vive en `app/services/combat_rounds.py` y se exporta mediante el import histórico `app.services.combat` para no crear dos rutas de resolución.

Cada ronda:

1. normaliza los ejércitos sobrevivientes;
2. calcula la distribución ofensiva usando el catálogo canónico de BM-0063;
3. calcula la defensa ponderada por tipo atacante;
4. aplica bonus de muralla y modificadores compatibles;
5. recalcula moral según la relación entre defensa y ataque;
6. obtiene suerte desde un RNG local determinista;
7. calcula presión de bajas limitada;
8. distribuye bajas con redondeo fraccional determinista;
9. persiste en el resultado el estado auditable de la ronda;
10. termina por eliminación de un bando o al alcanzar el máximo de rondas.

Resultados posibles:

- `attacker_victory`;
- `defender_victory`;
- `mutual_destruction`;
- `stalemate`.

## Moral y suerte

Los límites continúan definidos en la fuente única `balance.py`:

- moral mínima: `0.30`;
- moral máxima: `1.50`;
- suerte mínima: `-0.25`;
- suerte máxima: `+0.25`.

La moral se recalcula durante la batalla contra la defensa efectiva de la ronda. La suerte no usa el generador global de Python; se obtiene exclusivamente del RNG local creado para la batalla.

Esto evita que otras tareas del proceso alteren el resultado de un combate ya definido.

## Semilla reproducible y auditoría

La semilla es un SHA-256 derivado de una representación JSON canónica del estado precombate, incluyendo como mínimo:

- versión del algoritmo;
- versión de balance;
- tipo de batalla;
- ciudad atacante;
- objetivo defensor;
- ejércitos iniciales ordenados;
- nivel de muralla;
- edificio objetivo cuando aplica;
- progreso relevante de atacante y defensor.

La semilla inicializa una instancia local de `random.Random`.

Consecuencias:

- el mismo estado precombate reproduce las mismas rondas;
- un rollback/reintento antes de confirmar no rerrolea la batalla;
- un combate posterior confirmado puede diferenciarse por el estado/progreso ya modificado;
- la pérdida de lealtad causada por Nobles usa el mismo RNG determinista del combate.

El informe de batalla guarda:

- `algorithm_version`;
- `balance_version`;
- `seed`;
- `round_count`;
- `outcome`;
- historial completo `rounds`.

Los informes PvP de atacante y defensor comparten la misma semilla y el mismo historial de rondas para un único evento autoritativo.

## Bajas, asedio y lealtad

Las bajas se acumulan ronda a ronda sobre los supervivientes efectivos, con redondeo determinista para evitar divergencias por fracciones.

Las estadísticas de ataque/defensa, capacidad de carga y tipos militares siguen proviniendo del catálogo único BM-0063.

La muralla continúa aportando el bonus canónico de `5%` por nivel.

Las unidades de asedio conservan el comportamiento compatible de daño a muralla/edificio cuando corresponde; BM-0064 cambia el motor de resolución, no crea un segundo sistema de asedio.

La reducción de lealtad bárbara por Noble permanece entre `20` y `35` puntos por resolución válida y se obtiene desde el RNG de la batalla.

Una conquista solo puede ocurrir si:

1. gana el atacante;
2. sobrevive al menos un Noble;
3. el defensor es una ciudad bárbara sin propietario.

Una ciudad de otro jugador nunca cumple el tercer requisito, por lo que el combate PvP no puede transferir su propiedad.

## Botín y retorno

El motor calcula el botín en servidor usando la capacidad de carga de los supervivientes y los modificadores de evento aplicables.

La integración con `movement.py` conserva la frontera económica correcta:

1. el combate calcula/deduce el botín del defensor;
2. la capa de movimiento restaura el snapshot del atacante para impedir acreditar el botín de inmediato;
3. se crea **un único movimiento de retorno** con supervivientes y botín;
4. los recursos se acreditan a la ciudad atacante cuando ese retorno llega.

Por tanto, el mismo botín no puede quedar simultáneamente acreditado en la ciudad y transportado en marcha.

G9 compara recurso por recurso `wood`, `stone`, `iron` y `gold` del informe contra la carga real del retorno y compara también las tropas del retorno contra los supervivientes reportados.

## Exactly-once, reintentos y concurrencia

BM-0064 extiende el worker de movimientos existente; no introduce un resolver paralelo.

La transición sigue protegida por los locks y estados existentes de `Movement`:

- una llegada se procesa una sola vez;
- una resolución confirmada cambia el movimiento de ataque a `completed`;
- se crea un solo conjunto de informes correspondiente al evento;
- se crea un solo retorno;
- un retry posterior no vuelve a resolver ni rerrolea el combate.

Las pruebas PostgreSQL incluyen el ciclo de movimientos dentro de la matriz concurrente real, y las pruebas de lifecycle verifican semilla/historial compartidos en los informes y ausencia de retornos duplicados.

## PvE, PvP y oasis

### PvE

Las ciudades bárbaras usan el nuevo motor por rondas. La conquista con Noble queda limitada a estos objetivos.

### PvP

Los ataques entre jugadores usan el mismo motor, generan informes auditables para ambos participantes y mantienen la prohibición absoluta de conquista de ciudad de jugador.

### Oasis

El resolver de oasis consume el mismo motor determinista con moral neutralizada en `1.0` y sin muralla de ciudad. La conquista del oasis sigue requiriendo héroe superviviente.

La capa de compatibilidad conserva el comportamiento histórico de puntuación de oasis para que BM-0064 no cambie accidentalmente rankings mientras cambia la resolución militar.

## API y UI de auditoría

`GET /report/?world_id=...` devuelve la lista autoritativa de reportes.

`ReportsView` detecta informes de tipo `battle`, parsea su contenido y, cuando existe un bloque `combat`, muestra:

- resultado;
- versión del algoritmo;
- versión de balance;
- semilla SHA-256 completa;
- número de rondas;
- moral por ronda;
- suerte por ronda;
- bajas de atacante y defensor;
- ataque efectivo;
- defensa efectiva.

Durante G9 se detectaron dos defectos de integración frontend que quedaron corregidos:

1. `cityStore.loadReports()` asumía un wrapper `{ reports: [...] }` aunque el backend devuelve una lista directa;
2. una entrada directa a `/reports` podía ejecutar `loadReports()` antes de que `cityStore.currentCity` estuviera inicializada y no volvía a intentar la carga.

La solución normaliza ambos formatos compatibles y hace que `loadReports()` cargue primero la ciudad cuando sea necesario. Esto hace estable la pantalla tanto por navegación interna como por refresh/URL directa.

## Evidencia funcional — Validation #419

HEAD funcional: `58e612cc60b20ca410cc54de0f515f5125f56a23`  
Run: `32730864548`

### Backend

**SUCCESS**

- `219` pruebas recolectadas;
- `201 passed`;
- `18 skipped` por requerir el gate PostgreSQL dedicado;
- `4 warnings`;
- cobertura total `75%`;
- `combat.py`: `100%`;
- `combat_rounds.py`: `86%`.

También quedaron verdes:

- compilación Python;
- Alembic `base -> 0009`;
- seed canónico idempotente;
- downgrade `0009 -> base`.

BM-0064 no agrega migración; el schema head continúa en `0009`.

### PostgreSQL concurrency

**SUCCESS**

- `18 passed`;
- `3 warnings`;
- `15.78s`.

Incluye la matriz de concurrencia económica, onboarding, edificios, unidades, movimientos, mercado, expansión, simulación y tutorial. Los casos de movimiento cubren la garantía exactly-once utilizada por BM-0064.

### Frontend

**SUCCESS**

- instalación reproducible;
- lint;
- build de producción.

### Dependency/security

**SUCCESS**

- auditoría Python;
- análisis estático de seguridad;
- auditoría frontend.

### G5 operations

**SUCCESS**

- deployment probes;
- backup;
- restore;
- recovery/load probes.

### Browser E2E

**SUCCESS**

Pasaron en secuencia:

- G2 sesión/realtime;
- G4 UX responsive, teclado e i18n;
- G6 expansión;
- G7 investigación;
- G8 catálogo/mantenimiento militar;
- **G9 combate determinista por rondas**.

Fixture G9 del corte funcional:

`prepared-g9:4:1:13:14:seed=64d08c40616ff98544d6ee4248d6b039e6295223386348a1758e975df4cc6c99:rounds=8:outcome=attacker_victory:return=2`

G9 prueba end-to-end que:

1. existe exactamente un informe de batalla auditable;
2. la versión del algoritmo es la esperada;
3. la semilla tiene 64 caracteres hexadecimales SHA-256;
4. `round_count` está entre 1 y 8 y coincide con el historial;
5. cada suerte está dentro de `[-0.25, 0.25]`;
6. cada moral está dentro de `[0.30, 1.50]`;
7. hay exactamente un ataque completado;
8. hay exactamente un retorno pendiente;
9. tropas del retorno = supervivientes del informe;
10. recursos del retorno = botín del informe;
11. `/reports` muestra la misma semilla que la API;
12. la UI pinta exactamente el mismo número de rondas;
13. la UI muestra las versiones del algoritmo y balance.

El fixture resuelve el ataque mediante el worker real antes de arrancar el navegador y vuelve a invocar el worker para verificar que el retry no procesa otro movimiento ni duplica informe/retorno.

### Imágenes Docker

**SUCCESS**

- backend image;
- frontend image.

## Rollout operativo

BM-0064 no cambia schema, pero **sí cambia la semántica final de combate**. Debe tratarse como cambio de reglas de mundo.

Para un mundo ya iniciado, respetar PD-009 y aplicar una ventana controlada:

1. detener temporalmente nuevas mutaciones militares si se cambia la regla en un mundo activo;
2. pausar el worker de movimientos;
3. tomar snapshot/backup;
4. inspeccionar ataques próximos a vencer;
5. desplegar API, worker y frontend como conjunto compatible;
6. conservar schema `0009`;
7. verificar health/readiness;
8. ejecutar una batalla canaria PvE y comprobar seed/rondas/retorno;
9. ejecutar una batalla PvP canaria y comprobar que no cambia propiedad;
10. reanudar worker;
11. observar errores, tiempos de resolución, reports y retornos antes de ampliar tráfico.

No es seguro mezclar durante una misma ventana workers con algoritmo antiguo y nuevo, aunque el schema sea compatible, porque dos procesos podrían interpretar de forma distinta un movimiento pendiente.

## Rollback

No se requiere `alembic downgrade` para revertir únicamente BM-0064.

Rollback recomendado:

1. pausar nuevas órdenes militares y worker;
2. tomar snapshot/backup;
3. identificar movimientos de ataque todavía `ongoing`;
4. no reabrir tráfico hasta que todos los workers ejecuten la misma versión;
5. desplegar API, worker y frontend anteriores como conjunto;
6. verificar que movimientos ya `completed` no se reprocesan;
7. verificar retornos existentes e informes ya persistidos;
8. reanudar worker y luego tráfico.

Los informes BM-0064 ya confirmados conservan su bloque de auditoría como dato histórico; el rollback de código no debe intentar rerresolverlos.

## Hallazgos corregidos durante BM-0064

1. resolver legado de una sola comparación global en lugar de rondas;
2. uso de `random` global, incompatible con reproducción exacta;
3. pérdida de lealtad Noble no ligada a la semilla de la batalla;
4. falta de seed/historial de rondas en informes;
5. falta de representación UI de la auditoría;
6. prueba legacy que parcheaba `combat.random.randint` y ocultaba el contrato antiguo;
7. riesgo de cambiar accidentalmente la puntuación de oasis al adoptar el nuevo resolver;
8. fixture G9 que comparaba ID contra objetos `Movement`;
9. frontend de reportes que esperaba un wrapper de API inexistente;
10. condición de carrera de inicialización al entrar directamente a `/reports`.

## Límite deliberado hacia BM-0065

BM-0064 cierra el motor de batalla de v1.0 y su integración con movimientos, botín, retorno e informes.

BM-0065 debe cerrar **espionaje completo** sobre esta base, sin reabrir las reglas de combate ya versionadas. El espionaje deberá definir con precisión éxito/fracaso, información revelada, suerte/modificadores, informes y resistencia a reintentos usando la misma disciplina de autoridad de servidor y auditabilidad.

## Criterio de cierre

Validation #419 demuestra el corte funcional.

El PR #97 solo puede cerrarse cuando el **HEAD que contiene este documento** obtenga Validation completa verde, incluyendo Backend, PostgreSQL, Frontend, seguridad, G5, Browser G2–G9 e imágenes Docker.

Solo ese SHA será válido para marcar el PR Ready y hacer squash merge.