# BM-0093 / G5 — Inspección de drenaje de escritores (NO-GO #174)

**Estado:** herramienta de solo lectura, no conectada al despliegue. **No es una
barrera de escritura ni una autorización para backup, rollback o restore.** No
se ha activado en el VPS. Complementa las piezas ya integradas en PR #180
(reproducción de pérdida PostgreSQL), #181 (gate HTTP/Socket.IO opt-in) y #182
(manifiesto durable), y las auditorías solicitadas al PR #184.

## Alcance comprobado

`ops/g5_writer_drain_probe.py` observa el estado de un proyecto Compose:

1. Exige inventario **exacto** de servicios y rechaza escritores desconocidos.
2. Rechaza backend, worker, migrate y seed todavía activos o en estados
   intermedios, y políticas de restart que puedan levantarlos automáticamente.
3. Exige PostgreSQL y Nginx activos una sola vez y mounts G5 de solo lectura.
4. Rechaza la presencia del marcador `edge-maintenance/open`, incluso si es
   un enlace colgante; rechaza directorios de mantenimiento enlazados.
5. Ejecuta consultas de solo lectura a `pg_stat_activity` y
   `pg_prepared_xacts`: cero conexiones a la base objetivo y cero transacciones
   preparadas son requisitos para la **observación** (no una garantía futura).
6. Desde el contenedor Nginx **en ejecución**, comprueba HTTP 503 real para
   `/api/health` y para la entrada de Socket.IO (polling). Un fichero de
   configuración correcto por sí solo no prueba el cierre real del proxy.
7. No detiene/arranca servicios, no adquiere locks de escritura, no ejecuta
   migraciones, no hace copias de datos y no toca el marcador.

Ejemplo para un **entorno aislado de ensayo**, con identidad Compose correcta:

```bash
python3 ops/g5_writer_drain_probe.py \
  --env-file .release.env \
  -f docker-compose.deploy.yml -f docker-compose.g5.yml \
  --edge-dir .ops-state/edge-maintenance
```

Salida 2: evidencia ausente, topología inesperada, marcador abierto, sesiones
persistentes o cualquier incertidumbre. Salida 0: observación puntual sin
evidencia de escritores activos **en el instante consultado**.

## Hallazgos actuales que impiden la certificación

- `docker-compose.deploy.yml` deja `backend` y `worker` en
  `restart: unless-stopped`; el overlay G5 actual solo cambia Nginx.
  Detenerlos una vez no demuestra que no reinicien tras un fallo o reboot.
- `ops/deploy_remote.sh` captura el backup antes de detener/drenar los
  escritores; `docker compose up -d --remove-orphans` puede habilitar escritores
  antes de las verificaciones de la candidata.
- El gate Nginx solo bloquea nuevas admisiones por HTTP; WebSockets existentes,
  solicitudes en curso, conexiones directas, scheduler, tareas manuales y
  contenedores extras siguen siendo potenciales escritores.
- `ops/restore_postgres.sh` y el rollback no están integrados con
  `CutoverStore.verify_restore_allowed`; una ejecución del script de restore
  todavía no demuestra un snapshot seguro.
- Una lectura de `pg_stat_activity` no impide nuevas conexiones posteriores.
  Verificar HTTP 503 en el Nginx activo tampoco termina WebSockets ni peticiones
  previas, ni cubre otros accesos a PostgreSQL. **No usar este resultado como
  prueba RPO=0**.

## Siguiente integración obligatoria antes de cerrar #174

El orquestador debe mantener una barrera durable, verificable y compartida
por **todas** las instancias; bloquear nuevos trabajos, drenar los que están en
vuelo, impedir reinicios de escritores, verificar el edge realmente cerrado,
revisar el estado PostgreSQL **bajo protección contra nuevas escrituras**,
capturar el backup entonces y conectar el manifiesto a todos los puntos de
restore. Reabrir escritores solamente después del commit durable de cutover.
Simular caída/reinicio durante cada fase y pérdida de respuesta posterior al
commit con PostgreSQL 15 efímero. Revisar RPO/RTO y ensayar rollback.

**G5 sigue NO-GO.** Tests unitarios de este inspector son necesarios, pero no
sustituyen CI completo, auditoría adversarial del orquestador ni una prueba
controlada de restore en staging.
