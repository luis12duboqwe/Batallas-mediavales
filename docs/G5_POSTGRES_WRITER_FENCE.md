# BM-0093/G5 — Fence duradero de escritor PostgreSQL 15 (laboratorio)

**NO-GO.** `ops/g5_pg15_writer_fence.py` contiene la lógica de una **barrera
SQL parcial, unidireccional y sin executor instalado**. No incluye CLI, no
lee credenciales, no se conecta a la base, no modifica contenedores y no
está integrado con `deploy_remote.sh`, `G5Preparation` o `restore_postgres.sh`.

## Propósito

Complementa `ops/g5_writer_drain_probe.py`, que solo observa un instante.
Una copia PG durante una aplicación que confirma transacciones concurrentes
no garantiza RPO=0. Las escrituras deben bloquearse **de manera duradera**
antes de tomar el respaldo, incluso si reinicia un worker o muere el gestor.

## Protocolo exigido al futuro executor certificado

1. Identifica el servicio PostgreSQL 15 auditado, usa una sesión con la cuenta
   administrativa en la base `postgres` y comprueba permisos de superusuario.
2. Comprueba que `DB_URL` corresponde a una cuenta **distinta y no elevada**
   (sin SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS ni membresía
   en privilegios globales peligrosos).
3. Exige la base esperada con `datconnlimit` no bloqueado. Si ya figura
   bloqueada, considera el estado como incidente previo y rechaza rearmar.
4. Ejecuta primero `ALTER DATABASE <base> CONNECTION LIMIT 0` con
   **commit confirmado** y comprueba el valor 0 desde **una conexión nueva**.
   Solo después ejecuta `ALTER ROLE <app> NOLOGIN`, también con commit
   confirmado. Una lectura dentro de la misma transacción no demuestra que
   el bloqueo sea durable y visible para nuevas conexiones. Los cambios de
   catálogo permanecen tras la muerte del coordinador.
5. Termina todas las sesiones conectadas a la base objetivo. Comprueba
   literalmente que no queda **ninguna** sesión ni transacción preparada,
   que `datconnlimit=0` y que la cuenta de aplicación tiene `NOLOGIN`.
6. Cualquier error mantiene las restricciones ya aplicadas. **No existe
   rutina de reapertura automática**. Revertir el estado requiere un protocolo
   supervisado diferente y evidencia de la fase COMMITTED.

La API `Pg15PersistentFence` recibe un `Pg15SqlSession` inyectado de
manera explícita; las pruebas contienen únicamente un executor simulado.
Una futura implementación real debe exigir el `deploy.lock` y la activación
G5 persistente, conservar credenciales fuera de GitHub y fallar ante
ambigüedad de identidad, SQL o sesiones.

## Limitaciones críticas

- PostgreSQL permite que conexiones administrativas privilegiadas ignoren
  restricciones ordinarias de login/conexiones. Un supervisor, DBA u otro
  proceso con permisos equivalentes aún podría escribir. Hay que inventariar
  y bloquear **todas** esas rutas fuera de esta biblioteca.
- `NOLOGIN` no cierra sesiones **ya abiertas**: se requiere terminarlas y
  comprobar que no quedan transacciones preparadas.
- Un `CONNECTION LIMIT 0` afecta a todos los clientes no privilegiados de
  esa base; no se debe habilitar sin un mantenimiento aprobado y un protocolo
  de reactivación/certificación.
- Un fallo tras el primer ALTER puede dejar la base cerrada. Es intencional
  conservar la indisponibilidad, no tratar el fallo como permiso para
  restablecer logins a ciegas.
- La consulta de verificación es una observación, no prueba de ausencia de
  administradores/superusuarios externos. Tampoco sustituye el cierre real de
  HTTP/WebSocket, la parada de workers, el control de Docker ni la captura de
  backup bajo barrera.
- Las regresiones `tests/test_g5_pg15_writer_fence.py` comprueban
  orden, rechazo y ausencia de reversión con un stub aislado. Además,
  `ops/ci_g5_pg15_fence.py` debe ejecutarse obligatoriamente en el job
  `G5 operations recovery` contra **PostgreSQL 15 real** en un contenedor
  sintético `--network none`, sin puertos públicos ni volúmenes reales.
  El ensayo verifica una escritura ya confirmada, una sesión viva antes
  de la barrera, la terminación, la persistencia del bloqueo tras
  construir otro objeto Python y el rechazo de una reconexión. No certifica
  escritores superusuario o multiinstancia ni habilita datos reales.

Referencias de PostgreSQL 15:
- https://www.postgresql.org/docs/15/sql-alterdatabase.html
- https://www.postgresql.org/docs/15/sql-alterrole.html
- https://www.postgresql.org/docs/15/functions-admin.html

## Puertas pendientes para integrar y aprobar #174

- Aprovisionar una cuenta de aplicación de privilegios mínimos y cambiar
  `DB_URL` sin perturbar datos reales, con credenciales gestionadas fuera
  del repositorio.
- Adaptador PostgreSQL15 con conexión privilegiada y respaldo sin salida de
  secretos a logs, con prueba real del corte ante sesiones y reconexiones.
- Descartar la posibilidad de conexiones de superusuario o acceso directo
  por hosts/servicios desconocidos.
- Conectar el adaptador exclusivamente al coordinador bajo activación G5
  duradera, probar snapshot, failover, rollback y recuperación completa.
- Ensayar en PostgreSQL15 efímero y luego staging controlado con aprobación.
  **G5 y P1 #174 continúan NO-GO.**
