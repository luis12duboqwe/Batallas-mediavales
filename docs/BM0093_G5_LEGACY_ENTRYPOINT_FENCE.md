# BM-0093 / G5 — Barrera de compatibilidad con operaciones legacy

**Estado: protección pasiva, sin activación en el VPS.** Esta corrección evita que
los entrypoints heredados `ops/deploy_remote.sh`,
`ops/rollback_remote.sh` y `ops/restore_postgres.sh` ignoren un
manifiesto G5 o una señal durable de activación y restauren una copia incompatible
con acciones ya confirmadas.

## Contrato implementado

- Los tres scripts **rechazan con código 2** si existe
  `.ops-state/g5-cutover.json` o `.ops-state/g5-cutover-activated`. Una ruta
  corrupta, directorio, symlink colgante o raíz `.ops-state` enlazada también
  impide continuar. No se considera ausencia de manifiesto como autorización.
- Comprobar el estado **antes** de escribir metadatos transitorios y **otra vez
  bajo `.ops-state/deploy.lock`** reduce la carrera entre el primer chequeo
  y la adquisición del lock. El futuro orquestador G5 deberá usar ese mismo
  lock y crear el marcador de activación antes de iniciar operaciones G5.
- No hay bandera de entorno, argumento ni confirmación CLI para evadir el
  bloqueo. Un restore bajo G5 requiere una entrada nueva que verifique
  `CutoverStore.verify_restore_allowed`, mantenga el FD autorizado y la
  barrera de escritores hasta completar la operación.
- Sin marcadores G5, los scripts retienen su comportamiento anterior; esto
  conserva las pruebas de recuperación antiguas, **pero no los convierte
  en seguros para una actualización de staging que permita escrituras**.

## Límites y riesgo residual

- Esta medida **no** coordina el drenaje real de HTTP, Socket.IO, workers,
  migraciones, tareas manuales o sesiones PostgreSQL. No es una garantía RPO=0.
- Una operación legacy que adquiera el lock **antes** de la activación G5 puede
  continuar. El coordinador nuevo debe verificar la ausencia de operaciones en
  curso antes de activar el cutover y mantener el lock durante toda la barrera.
- Si el manifiesto y el marcador de activación desaparecen, este parche no
  reconstruye por sí solo la evidencia durable. La implementación definitiva
  debe mantener evidencia terminal no reutilizable y una reconciliación
  fail-closed ante pérdida de estado.
- Los scripts anteriores siguen siendo inseguros para upgrades con escritores
  activos mientras no exista un coordinador completo. **Issue #174 y gate G5
  permanecen NO-GO**.

## Pruebas

`tests/test_g5_legacy_state_fence.py` ejecuta los tres entrypoints copiados a
directorios temporales sin Docker, red, VPS ni PostgreSQL real. Comprueba las
variantes positiva/negativa, manifest/Sentinel, archivos/directorios/symlinks
corruptos, estado raíz enlazado, y aparición del marcador justo durante la
adquisición del lock mediante shim de `flock`. Los comandos deben rechazar
antes de iniciar procesos Docker o cambiar punteros de release.
