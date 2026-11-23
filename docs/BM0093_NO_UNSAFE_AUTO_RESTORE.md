# BM-0093 / G5 — Desactivar restauración automática peligrosa

**Estado:** defensa transitoria del gestor legacy, no un cutover G5 certificado. **P1 #174 / NO-GO para beta externa.** No ejecutar el despliegue sobre el VPS sin ensayos de recuperación y autorización.

## Problema reproducido

El gestor anterior `ops/deploy_remote.sh` ejecutaba `pg_dump` mientras backend y worker seguían aceptando escrituras. Si la nueva versión iniciaba migraciones y después fallaba HTTP, smoke, carga o Docker, el trap restauraba ese snapshot, potencialmente eliminando transacciones **confirmadas después de la copia**. Es la pérdida de datos demostrada sobre PostgreSQL15 aislado en `tests/test_bm0093_write_barrier_postgres.py`.

Un checksum correcto y una copia restaurable **no** garantizan que no haya escrituras nuevas entre el dump y la restauración.

## Política de fallo incorporada

- Antes de iniciar mutaciones de release, se conservan preflight, guardas de identidad, copia verificada y el manejo de errores previos a migración. No se restaura nada si aún no hubo mutación.
- Después de fijar `release_mutation_started=1`, todo fallo abre un incidente fail-closed: intenta `docker compose stop -t 120 backend worker migrate seed`; conserva `.ops-state/recovery-required`, la configuración candidata y el puntero de versión previo para diagnóstico; informa por stderr y retorna el código original.
- **No llama automáticamente a `restore_postgres.sh`**, no inicia la release anterior y no ejecuta el smoke de la release anterior. Un redeploy legacy queda bloqueado por el marcador persistente.
- Si detener escritores falla, conserva el incidente y señala explícitamente que el drain no está verificado.

## Límites operacionales

1. Preservar la base puede implicar **indisponibilidad** e incompatibilidad de esquema y release. Es preferible a borrar escrituras confirmadas. El operador debe inspeccionar versión, esquema, sesiones y contenedores.
2. Detener backend y worker no impide escritores manuales, otras réplicas o conexiones SQL directas, ni asegura políticas `restart=no`. **No demuestra RPO=0.**
3. El camino de **despliegue exitoso** legacy tampoco tiene una barrera universal. Este parche reduce el daño de una restauración insegura, pero **no habilita despliegues con jugadores reales**.
4. El backup se conserva, pero no debe restaurarse salvo con barrera duradera, identidad y FD verificados por `CutoverStore.verify_restore_allowed`, y certeza de que no se descartan escrituras confirmadas.
5. Los valores `BM_*` en las pruebas son fixtures sintéticos, no una excepción operacional.
6. VPS y PostgreSQL del preview no se modificaron: solo GitHub y CI aislado.

## Verificación

Las pruebas de `tests/test_bm0093_deploy_recovery.py` usan Docker simulado. Cubren fallo de startup, timeout HTTPS, ausencia del archivo original, backups más recientes, stop fallido, variables heredadas de restore, **fallo de publicación de `.release.env` antes y después de un rename atómico**, preservación del código original y bloqueo de redeploy. En fallos posteriores a la mutación no se admite `pg_restore --clean` ni recuperación automática.

Para cerrar #174 hace falta un **coordinador G5** que arme el sentinel antes de tocar escritores, cierre nuevas conexiones HTTP/Socket.IO, drene transacciones, impida reinicios y nuevos escritores, tome snapshot bajo protección continua, y recién entonces permita un restore controlado usando FD verificado.
