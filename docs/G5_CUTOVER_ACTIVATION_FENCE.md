# BM-0093 / G5 — Activación irreversible de la barrera de despliegue

**Estado:** biblioteca sin llamadas desde el despliegue actual. No habilita
staging ni beta y no permite backup/restore. El P1 #174 permanece **NO-GO**.

## Motivación

La protección de los tres entrypoints heredados (PR #187) solo los bloquea
si existe `.ops-state/g5-cutover.json` o
`.ops-state/g5-cutover-activated`. El manifiesto `CutoverStore.prepare`
se crea **después** del snapshot, por lo que una operación G5 futura debe
bloquear operaciones legacy **antes** de cerrar admisión y antes de cualquier
copia de PostgreSQL. Sin esto, un deploy legacy puede arrancar mientras el
gestor aún no publicó manifiesto ni guardó datos de rollback.

## Contrato de `ops/g5_activation_fence.py`

`with arm_cutover(host_root, operation_id): ...`

- Importar biblioteca stdlib-only; **no** existe CLI para activar producción.
- Exigir la raíz autorizada y `.ops-state` privadas (mismos requisitos de
  `CutoverStore`), ID simple de operación, y lock `deploy.lock` regular
  privado 0600, del propietario y sin hard links/symlinks.
- Adquirir `flock(LOCK_EX|LOCK_NB)` **sobre el mismo archivo** que emplean
  los scripts heredados de deploy/rollback/restore. Rechazar operaciones
  concurrentes y raíces/metadatos inseguros.
- Rechazar manifiesto previo, marca G5 anterior o incidente
  `recovery-required`, incluso si son directorios o symlinks rotos.
- Crear `g5-cutover-activated` con `O_EXCL|O_NOFOLLOW` y permisos 0600;
  escribir ID de operación; hacer `fsync` de archivo y directorio **antes
  de ceder el control al futuro coordinador**. Verificar inode y permiso.
- Mantener el lock mientras el coordinador usa el contexto; revisar que la
  marca y el directorio sigan siendo los mismos al finalizar.
- **Nunca borrar el marcador**, tampoco en errores o excepciones. Un fallo
  de `fsync` deja evidencia incierta pero bloqueante; el operador debe
  reconciliarla explícitamente. No existe opción `--force` o limpieza
  automática.

Esto fuerza fail-closed de los scripts legacy **desde el principio del
cutover**. También evita que dos activaciones que usen el mismo lock se
superpongan. La activación está diseñada para ser *una sola vez* mientras
no exista un runbook supervisado de reconciliación. No utilizarla
directamente para operar un preview con datos reales.

## Límites críticos

1. **No es un write barrier:** ni SIGTERM de worker ni Nginx 503 garantizan
   que transacciones ya iniciadas hayan terminado. Es necesario cerrar
   admisión, detener y drenar realmente procesos HTTP y workers,
   controlar WebSockets, tareas manuales, conexiones y políticas de restart
   reales (PR #189) y evitar nuevas conexiones escritoras.
2. El lock de `CutoverStore` es otro lock (inode del directorio), por lo
   que el futuro coordinador debe conservar ambos contratos. El simple uso
   aislado del manifiesto **no** prueba exclusividad con deploy legacy.
3. El marcador persiste tras la salida del contexto. Esto no mantiene por sí
   solo PostgreSQL en modo solo lectura, ni impide comandos Docker hechos
   manualmente o desde otro host sin el lock; la barrera universal sigue
   pendiente.
4. No hay todavía una operación automática de rollback/restore segura. Para
   esos casos debe verificarse `CutoverStore.verify_restore_allowed`, usar
   FD inmutable de snapshot y documentar la continuidad de la barrera entre
   copia y restauración. No se puede afirmar RPO=0.

## Pruebas

`tests/test_g5_activation_fence.py`: datos sintéticos y directorios
temporales sin Docker, red, datos reales o VPS. Valida caso correcto, error
del usuario, reactivación prohibida, sesiones simultáneas, lock legacy
ocupado, permisos 0700/0600, ataques de symlinks/hardlinks, corrupción de
estado, eliminación de marcador e incidente tras fallo de sincronización.
Cada caso de error exige no reabrir operaciones automáticamente.

## Próximo paso para #174

Implementar un **único coordinador** que retenga `deploy.lock` desde
`arm_cutover`, mantenga los procesos escritores bloqueados, verifique el
drenaje actual bajo Docker y PostgreSQL15 aislados, haga snapshot y
prepare el manifiesto en fases, y solo permita recuperación desde FD
autorizado mientras el bloqueo sigue vigente. Exigir pruebas que inyecten
fallos durante cada transición (incluidos reinicios y escritores externos).
**Hasta entonces no ejecutar el mecanismo nuevo en staging.**
