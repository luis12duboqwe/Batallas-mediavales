# BM-0093 / G5 — Primera integración del coordinador de preparación (#174)

**Estado: biblioteca de integración en GitHub, sin adaptador de producción.**
No se ha usado el VPS, no se abre acceso a jugadores, no se ejecuta un
backup/restore real, ni se autoriza despliegue. **G5: NO-GO.**

## Qué quedó conectado

`ops/g5_cutover_prepare.py` ofrece `G5Preparation.prepare(request, port)`
para que una futura implementación certificada ejecute esta secuencia bajo un
único `deploy.lock` y bajo la activación irreversible
`.ops-state/g5-cutover-activated`:

1. Prevalida identidad de release, operación, proyecto, base de datos y rutas.
2. `arm_cutover` publica el bloqueo legacy y lo sincroniza a disco **antes**
   de dar control al adaptador. El bloqueo no se borra, ni siquiera ante fallo.
3. `close_admission()`: debe cerrar **nuevas** peticiones HTTP y Socket.IO.
4. `fence_database_writes()`: debe mantener una barrera persistente contra
   conexiones nuevas y existentes de la cuenta de escritura y otros escritores.
5. `stop_writers()`: debe parar procesos de API, workers, scheduler, migrate
   y seed, prevenir reinicios y cubrir los hosts/instancias externas.
6. `verify_drain()`: requiere `True` booleano exacto. No se acepta una lista
   de blockers no vacía ni un resultado ambiguo; el adaptador certificado debe
   demostrar que la barrera sigue vigente y que no hay sesiones activas,
   transacciones preparadas o vías de entrada alternativas.
7. Solo entonces `capture_snapshot()` puede crear un respaldo. Se repite
   `verify_drain()` **después** de capturarlo.
8. `CutoverStore.prepare` valida en disco la ruta, checksum, contenido,
   identidad, permisos y tamaño del dump y escribe el manifiesto durable
   `PREPARED`.

El éxito es **exclusivamente PREPARED**. No hay métodos de migración,
restauración, publicación de release, reapertura, anulación de la marca o
limpieza automática del estado. Los entrypoints legacy permanecen excluidos.

## Contrato de seguridad

`PreparationPort` es un protocolo sin implementación conectada a Docker ni a
PostgreSQL. **No basta** con devolver `True` desde un adaptador de prueba:
la barrera real debe persistir aunque muera el coordinador. El inspector
`g5_writer_drain_probe.py` observa solo un instante y **no puede** actuar como
única prueba de esa garantía. La marca `g5-cutover-activated` es una
exclusión del flujo legacy, no una barrera SQL.

Para un futuro adaptador se exige demostrar, entre otras cosas:

- Cuenta `DB_URL` distinta de `POSTGRES_USER`, de privilegios mínimos,
  administrada fuera del repositorio; sin roles elevados o permisos
  alternativos que permitan saltarse el bloqueo.
- Bloqueo persistente de nuevos logins/escrituras SQL **antes** de la primera
  instantánea; sesiones existentes efectivamente canceladas y comprobadas.
- Estado real de reinicio Docker no reactivable; inventario completo de
  contenedores, migraciones, workers, tareas programadas y escritores externos.
- Cierre del proxy con HTTP 503 y Socket.IO, más drenaje de sockets existentes.
- Revalidación bajo protección contra nuevas escrituras antes y después de
  `pg_dump`; no aceptar solo dos lecturas puntuales sin bloqueo duradero.
- Snapshot de la base y volumen correctos, inmutable y utilizable mediante
  un FD verificado; no limpiar backups automáticamente durante un incidente.

Toda excepción deja el marcador irreversible. Si el manifiesto PREPARED no
se pudo publicar, no se inventa una fase de éxito ni se ejecuta recuperación
automática. Reconciliación posterior requiere un procedimiento distinto,
revisado manualmente. Una caída de host no deshace transacciones confirmadas.

## Pruebas

`tests/test_g5_cutover_prepare.py` usa archivos sintéticos y adaptadores
falsos, sin red, Docker ni PostgreSQL. Cubre orden obligatorio, marcador
persistido antes de la primera operación, rechazo de segundo intento, bloqueo
por lock, fallos en todas las fases, respuesta ambigua del drenaje, checksum
falso, archivo ausente, ruta ajena, symlink y solicitud inválida. No afirma
que una barrera PostgreSQL real esté implantada.

## Trabajo necesario para completar #174

1. Crear un `PreparationPort` real, auditado y **exclusivo de staging
   controlado**, con una cuenta PostgreSQL de aplicación no privilegiada,
   cierre SQL duradero y cancelación de escritores; validar concurrencia
   multiinstancia con PostgreSQL 15 aislado.
2. Ensayar quiescencia real y snapshot con una transacción confirmada antes
   de cerrar, intentos concurrentes durante el corte, reinicio de contenedores,
   WebSockets y caída del proceso coordinador.
3. Implementar las fases restantes MIGRATING / VERIFIED_READONLY / COMMITTED,
   rollback de aplicación y restore desde FD vinculados al mismo bloqueo,
   sin reapertura antes del commit durable. Ensayar caídas y pérdida de
   respuesta después de cada fase.
4. Añadir observabilidad, RPO/RTO medidos, gate de CI del HEAD, runbook de
   incidentes y autorización separada para staging antes de cualquier VPS.

**No lanzar este módulo en un despliegue real ni usar su éxito sintético como
certificación de RPO=0.**
