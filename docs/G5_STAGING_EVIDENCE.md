# G5 — Comprobación local de declaraciones de evidencia

**G5 sigue NO-GO.** Esta herramienta solo comprueba coherencia de declaraciones
aportadas por una persona; no consulta GitHub, staging, DNS, SMTP, backups ni
servicios externos, no lee secretos y no autentica fuentes ni firmantes. Una
declaración `real` no demuestra que sea real. El revisor debe contrastar los
artefactos originales, identidad, alcance, permisos, integridad y actualidad
por los canales autorizados. No usar la herramienta para habilitar beta, ejecutar
operaciones, resolver incidencias ni aprobar G5.

El contrato se basa en `G5_MONITOR_READINESS.md`, `G5_CHECKPOINT_2026-11-20.md`,
`G5_OPERATIONS_RUNBOOK.md`, `PLAN_MAESTRO_DESARROLLO.md` y #161. El resultado
no reemplaza sus requisitos ni el juicio del propietario. En particular, los
probes acotados no certifican capacidad máxima. Una restauración en una copia
aislada no autoriza restaurar sobre datos administrados; deben respetarse las
barreras y restricciones vigentes del runbook.

## Uso sin conexión

Crear los archivos JSON **localmente y fuera del repositorio** a partir de
evidencia existente, sin recopilarla con esta herramienta:

```sh
python3 ops/g5_staging_evidence.py /ruta/local/evidencia.json
python3 ops/g5_staging_evidence.py /ruta/local/evidencia.json --approval /ruta/local/aprobacion.json
```

No introducir URLs, credenciales, correos, direcciones privadas, logs, datos de
usuarios ni secretos. `reference` es un identificador opaco local, no una URL:
el operador mantiene el mapeo seguro a los artefactos fuera de este archivo.
No se descargan ni se abren las referencias. No inventar resultados: si falta
un dato, dejarlo ausente y obtener `INCOMPLETE`. No subir archivos de evidencia
real al repositorio.

- `INCOMPLETE`: faltan datos o alguna regla falla.
- `SYNTHETIC_ONLY`: declaraciones sintéticas completas, útiles solo para
  probar el formato; no son evidencia de staging.
- `REVIEW_REQUIRED`: declaraciones reales completas **sin verificar**.
- Con aprobación separada, `status` es siempre `NO_GO`;
  `approval_declaration` solo indica `INCOMPLETE` o `REVIEW_REQUIRED`.
- Salida 0 significa únicamente que las declaraciones satisfacen el contrato
  local; 1 indica bloqueos y 2 JSON ilegible/inválido. Ninguna salida es GO.

El reloj de evaluación es UTC actual. Se rechazan fechas futuras o fuera de
ventana: 30 días para CI, 24 horas para health y blockers, siete días para los
demás registros y 24 horas para la aprobación. Son límites conservadores de
esta herramienta, no garantías de vigencia: cambios posteriores pueden
invalidar antes cualquier declaración.

La CLI solo abre archivos locales regulares, de hasta 256 KiB cada uno; rechaza
claves duplicadas, números no finitos, profundidad mayor de 32 y más de 10000
valores. Los campos y registros no documentados **se ignoran**, incluso si
parecen contradecir los conocidos: no son evidencia ni crean nuevas reglas.
El resumen de aprobación sí incluye todos los campos del documento. Nunca
interpretar un campo extra como requisito validado.

## Contrato JSON

El objeto raíz requiere `release_sha` (40 caracteres hexadecimales minúsculos,
identificador de la release), `main_head_sha` (HEAD de main en el corte, igual
al SHA de la release), `environment_id` (identificador opaco del staging),
`origin` (`real` o `synthetic`) y `records` (objeto). Cada registro de la
siguiente tabla es obligatorio y contiene:

- `release_sha`, `environment_id` y `origin`, idénticos a la raíz;
- `reference`, identificador distinto para cada registro;
- `observed_at`, fecha UTC exacta `AAAA-MM-DDThh:mm:ssZ`;
- `result`: `pass`.

Los identificadores contienen solo letras ASCII, números, `_`, `-`, `.`,
empiezan por letra/número y tienen hasta 128 caracteres. Los booleanos deben
ser booleanos JSON, no texto. Las métricas son números finitos no negativos;
los contadores son enteros (no booleanos). `true` a continuación es literal.

| Registro | Campos adicionales requeridos |
|---|---|
| `ci_validation`, `ci_journeys` | `completed: true`, `conclusion: "success"` y `jobs` según se detalla abajo; corresponden respectivamente a Validation y Independent player journeys sobre el SHA exacto. |
| `deploy` | `workflow_executed: true`, `immutable: true`, `migration_succeeded: true`, `deployed_sha` igual al SHA raíz, `source_release_sha` y las cuatro identidades de imagen iguales al cutover. |
| `https` | `dns_verified`, `tls_verified`, `hostname_verified`, `https_verified`: `true`. |
| `smtp` | `real_provider`, `test_recipient_only`, `delivery_verified`: `true`; Mailpit no acredita SMTP real. |
| `migration` | `staging_source`, `recoverable_copy`, `upgrade_verified`: `true`; `backup_sha256` igual al snapshot verificado del cutover. Ensayo previo al deploy con copia recuperable del staging exacto. |
| `health_manual`, `health_schedule` | `trigger` respectivamente `"manual"` y `"schedule"`; `repository_url_configured`, `job_executed`, `smoke_executed`, `load_executed`: `true`; `job_conclusion: "success"`; `started_at`, `ended_at` en UTC; `load_duration_seconds >= 10`; `smoke_metrics` y `load_metrics`. Readiness verde sin job ejecutado no cuenta. |
| `soak` | `job_executed`, `load_executed`, `smoke_executed`, `server_metrics_reviewed`, `no_duplicate_effects`: `true`; `job_conclusion: "success"`; `started_at`, `ended_at` en UTC; `planned_duration_seconds >= 900`, `duration_seconds >= planned_duration_seconds`; `capacity_scope` identificador opaco del alcance medido; `load_metrics`, `smoke_metrics`, `api_p95_ms < 300`. El smoke es el posterior al soak. |
| `alerts` | `api`, `worker`, `database`, `failure_visible`, `alert_tested`, `logs_reviewed`: `true`. |
| `backup` | `external_copy`, `checksum_verified`, `retention_verified`: `true`; `sha256` de 64 hexadecimales minúsculos; `captured_at` en UTC. |
| `clone_restore` | `isolated`, `fixture_mutated`, `restore_verified`, `data_verified`: `true`; `backup_sha256` igual al hash anterior; `clone_id` distinto del entorno fuente y tres identidades independientes como se describe abajo. |
| `rollback` | **Solo recuperación ante desastres**: `isolated`, `application_verified`, `database_verified`, `smoke_verified`: `true`; `clone_id` y `backup_sha256` iguales al restore; `recovery_point_at`, `last_commit_at`, `incident_at`, `service_restored_at` en UTC; `rpo_seconds`, `rto_seconds`. No sustituye a `protected_cutover`. |
| `protected_cutover` | Declaración independiente requerida para #174, con RPO=0, snapshot previo al deploy, exclusión continua y matriz de fallos; ver sección siguiente. |
| `blockers` | `inventory_complete: true`, `p0_open: 0`, `p1_open: 0`, `p2_156: "resolved"` o `"accepted"`, `p2_156_reference`: identificador de decisión documentada. Incluye todos los bloqueos aplicables, no solo #149. |
| `policy` | `support`, `privacy`, `terms`, `retention`, `operator_details`: `true`. |

Cada objeto `smoke_metrics` y `load_metrics` requiere `requests`, `errors`,
`server_errors`, `p95_ms`. Smoke exige al menos 20 solicitudes (30 después del
soak), cero errores y p95 ≤750 ms. Carga exige al menos una solicitud, errores
≤0,5 %, cero 5xx y p95 ≤750 ms. El p95 de API jugable <300 ms del Plan Maestro
se declara separadamente en el soak: no confundirlo con el límite de 750 ms
del probe del runbook. No se acepta un presupuesto más laxo automáticamente.
El responsable debe revisar representatividad, tasa, rutas, alcance y duración
de la carga, y capacidad antes de considerar la evidencia suficiente.

CI requiere un objeto `jobs` por workflow, indexado por ID de job; cada job
debe declarar `{"executed": true, "conclusion": "success"}`. Para Validation:
`backend`, `postgres-concurrency`, `frontend`, `browser-e2e`,
`accessibility-e2e`, `dependency-audit`, `g5-operations`, `images`; para
Independent player journeys: `isolated-journeys`. Validation requiere además
`g5_image_steps` con el mismo formato para `actual_migration`,
`role_provisioning`, `full_schema_restore`, `logical_clone`, `actual_reopen`
y `release_transition`. Estos IDs resumen los gates conocidos en
`main@9ccc610a`; el revisor debe contrastar el workflow de la release exacta
y cualquier gate nuevo, pues esta lista no se actualiza automáticamente.
La conclusión verde del workflow no demuestra que todos se ejecutaron.

Las fechas de CI deben preceder al deploy; la migración ensayada y el cutover
protegido deben preceder al deploy. El deploy precede a los demás registros;
health manual debe terminar antes de que comience el programado; backup precede
al restore, que precede al rollback. `captured_at` no puede ser posterior a la
observación del backup. Los intervalos de ejecución de health/soak comienzan
tras el deploy, terminan antes de su observación y abarcan al menos la duración
de carga declarada. La observación de blockers debe ser posterior o igual a
todas las demás. En recuperación de desastres, el punto de recuperación es
exactamente el instante de captura del backup; precede al último commit, que
precede al incidente. El incidente
es posterior al restore en clon y la recuperación del servicio precede a la
observación del rollback. RPO debe ser exactamente `last_commit_at -
recovery_point_at` y no superar 86400 s; RTO debe ser exactamente
`service_restored_at - incident_at` y no superar 14400 s. Estos tiempos son
declaraciones del simulacro, no una garantía de recuperación real.

## Declaración independiente de cutover protegido #174

`protected_cutover` es distinto de `backup`/`clone_restore`/`rollback` de
desastres. Un RPO de hasta 24 h es inadmisible para el cutover: aquí se exige
`rpo_seconds: 0`, sin pérdida de escrituras confirmadas. Todos estos datos son
declaraciones no autenticadas, no certificación #174; #174 sigue abierto.

Requiere `source_release_sha` (SHA completo diferente de la release candidata),
`target_release_sha` igual a `release_sha`, y `source_backend_image`,
`source_frontend_image`, `target_backend_image`, `target_frontend_image`
con formato `sha256:` seguido de 64 hexadecimales minúsculos. El deploy declara
las mismas identidades exactas. Requiere `snapshot_sha256`, igual a
`clone_backup_sha256` y a `migration.backup_sha256`. El snapshot externo y
verificado es anterior al ensayo de migración y al deploy. La copia de
recuperación de desastres posterior al deploy es un registro separado.

Los siguientes campos deben ser `true`: `isolated_rehearsal`,
`sql_exclusion_continuous`, `edge_exclusion_continuous`,
`docker_exclusion_continuous`, `privileged_exclusion_continuous`,
`external_writers_excluded`, `snapshot_external`, `snapshot_verified`,
`logical_clone_verified`, `no_lost_commits`, `no_stale_restore`,
`committed_writes_preserved`, `concurrent_write_blocked`, `no_early_reopen` y
`restore_forbidden_after_commit`. Cubren backend/worker, HTTP/WebSocket,
escritores SQL y privilegiados, reinicio/recreación Docker y acceso externo
durante la barrera, no una mera observación puntual.

Tanto `protected_cutover` como `clone_restore` requieren objetos
`source_identity`, `clone_identity`, `witness_identity`, cada uno con
`cluster`, `container`, `network`, `volume` (identificadores opacos). Los tres
valores de cada campo deben diferir: OID de base no identifica un clúster.
Testigo y clon independientes corresponden al contraste de #221; este no
demuestra por sí solo ni equivalencia semántica completa ni backup externo.
#219 es un laboratorio de grants, no prueba de mínimo privilegio.

Todos los tiempos siguientes son UTC. La secuencia de la preparación exige
`barrier_started_at <= snapshot_captured_at <= snapshot_verified_at <=
clone_verified_at <= migration.observed_at <= committed_at <=
barrier_ended_at <= protected_cutover.observed_at <= deploy.observed_at`.
La barrera cubre continuamente el snapshot, la migración y el commit del ensayo
aislado; no autoriza reabrir el entorno real ni restaurar un snapshot obsoleto.

`failure_matrix` es un objeto con una declaración independiente para cada
escenario real ensayado: `stop_writers`, `backup`, `pull`, `migration`, `up`,
`https_timeout`, `smoke`, `load`, `recovery`, `before_commit` (fase
`"precommit"`), y `after_commit`, `reopen`, `lost_response` (fase
`"postcommit"`). Cada entrada requiere `phase`, `reference` único, los mismos
`source_release_sha`, `target_release_sha` y cuatro campos de imagen, y
`barrier_started_at <= failure_at <= barrier_ended_at <=
protected_cutover.observed_at`. Debe declarar `failure_injected`, `isolated`,
`sql_exclusion_continuous`, `edge_exclusion_continuous`,
`docker_exclusion_continuous`, `privileged_exclusion_continuous`,
`no_lost_commits`, `no_stale_restore`, `recovery_required` como `true`.
Cada caso precommit exige `commit_not_recorded: true`; cada caso postcommit
exige `committed_at` entre inicio de barrera y fallo, y
`restore_forbidden_after_commit: true`. Se exige conservación segura del
incidente; una reanudación anterior autorizada no se infiere automáticamente.
Referencias y tiempos de cada caso identifican ensayos separados, no un único
fallo imaginario. Los ensayos sintéticos o de CI no sustituyen evidencia real.

## Aprobación independiente

El archivo de aprobación es otro objeto JSON: `release_sha`, `environment_id`,
`origin: "real"`, `decision: "approve"`, `owner_id`, `reference`, `approved_at`
y `evidence_sha256`. `owner_id` y `reference` son identificadores opacos; la
referencia debe ser distinta de las de evidencia. La aprobación debe ser
posterior a todos los registros y se exige evidencia real completa.
`evidence_sha256` vincula la declaración al contenido exacto del documento,
no autentica al firmante ni firma el archivo. Calcularlo localmente con el JSON
definitivo:

```sh
python3 -c 'import hashlib,json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print(hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode("utf-8")).hexdigest())' /ruta/local/evidencia.json
```

Ante cambios del documento se requiere una nueva revisión y declaración de
aprobación. La persona responsable verifica por separado la autorización real
del propietario y cualquier requisito adicional antes de una decisión humana.
