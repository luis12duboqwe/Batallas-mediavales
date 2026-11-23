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
   Comprueba **dos niveles**: la política deseada de Compose y, para cada
   contenedor de escritor existente (incluido detenido), el valor real de
   `HostConfig.RestartPolicy.Name` obtenido mediante `docker inspect`.
   Un overlay que declare `restart: no` no basta si Docker aún conserva
   `always` o `unless-stopped` en un contenedor anterior.
3. Exige PostgreSQL y Nginx activos una sola vez y mounts G5 de solo lectura.
4. Rechaza la presencia del marcador `edge-maintenance/open`, incluso si es
   un enlace colgante; rechaza directorios de mantenimiento enlazados.
5. Antes de declarar quiescencia, analiza la identidad del usuario
   de la aplicación en `DB_URL` y la compara con el usuario de mantenimiento
   `POSTGRES_USER`. Si coinciden, la observación **falla**: no es seguro
   basar una futura barrera en bloquear permisos de una cuenta que también
   administra PostgreSQL. Consulta `pg_roles` (solo lectura) y exige
   `LOGIN`, sin `SUPERUSER`, `CREATEDB`, `CREATEROLE`,
   `REPLICATION`, `BYPASSRLS` ni pertenencia a cuentas superusuario.
   También exige que `DB_URL` apunte exactamente al servicio Compose
   `database` (puerto 5432) y a `POSTGRES_DB`; rechaza redirecciones
   por URL, parámetros de conexión que alteren el destino, credenciales
   de aplicación vacías y destinos alternativos. No debe confundirse la
   cuenta inspeccionada con otro clúster PostgreSQL.
   La herramienta **no imprime** la contraseña ni modifica roles.
6. Ejecuta consultas de solo lectura a `pg_stat_activity` y
   `pg_prepared_xacts`: cero conexiones a la base objetivo y cero transacciones
   preparadas son requisitos para la **observación** (no una garantía futura).
7. Desde el contenedor Nginx **en ejecución**, comprueba HTTP 503 real para
   `/api/health` y para la entrada de Socket.IO (polling). Un fichero de
   configuración correcto por sí solo no prueba el cierre real del proxy.
8. No detiene/arranca servicios, no adquiere locks de escritura, no ejecuta
   migraciones, no hace copias de datos, no revoca privilegios y no toca
   el marcador.

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

- La configuración de referencia de despliegue utiliza habitualmente
  las credenciales de `POSTGRES_USER` en `DB_URL`. Ese usuario se crea con
  privilegios elevados por la imagen oficial de PostgreSQL; **no se puede
  certificar una barrera revocable** hasta migrar la aplicación a un rol
  propio de mínimo privilegio, con credenciales administradas fuera de GitHub
  y comprobación de permisos efectiva en PostgreSQL 15 aislado. Esta rama
  **solo audita**; no altera credenciales, roles ni despliegues existentes.
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
- La separación de privilegios es una **condición necesaria, no suficiente**:
  un usuario `LOGIN` con permisos ordinarios todavía puede escribir mientras
  conserve acceso y sesiones abiertas. Esta inspección no revoca `CONNECT`,
  no cambia `LOGIN` y no bloquea futuras conexiones; el coordinador debe
  aportar una barrera permanente mientras dure el corte.
- Una lectura de `pg_stat_activity` no impide nuevas conexiones posteriores.
  Verificar HTTP 503 en el Nginx activo tampoco termina WebSockets ni peticiones
  previas, ni cubre otros accesos a PostgreSQL. Verificar la política de reinicio
  real de Docker tampoco impide `docker compose up` manual o fuera del lock.
  **No usar este resultado como prueba RPO=0**.

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
