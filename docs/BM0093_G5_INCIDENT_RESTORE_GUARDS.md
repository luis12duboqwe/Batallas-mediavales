# BM-0093 / G5 — Guardas de restauración heredada frente a incidentes

**Estado:** protección parcial; no certifica #174, G5 continúa **NO-GO**.

## Riesgo

Tras el PR #191, un fallo posterior al inicio de una nueva release conserva
`.ops-state/recovery-required` sin restaurar automáticamente un dump viejo.
Sin embargo, una ejecución directa de `ops/restore_postgres.sh` o un rollback
manual podía hacer un restore y descartar las transacciones confirmadas tras
ese backup. Un marcador de incidente no es prueba de aislamiento de escritores.

## Reglas fail-closed

- `ops/restore_postgres.sh` rechaza **RESTORE directo** cuando encuentra
  `.release-sha` / `.release.env` o un marcador
  `.ops-state/recovery-required` preexistente. También detecta enlaces
  simbólicos (incluidos colgantes) en esas entradas. Se niega **antes**
  de consultas, parada de servicios o `pg_restore --clean`.
- El modo `RESTORE_PREPARE_ONLY=1` sigue siendo preparatorio: verifica backup,
  checksum, identidad y copia del archivo, **sin reemplazar la base**.
- Las restauraciones anidadas realizadas desde un proceso que ya posee el
  `deploy.lock` mantienen por ahora la lógica heredada para no romper
  los ensayos existentes; **no están certificadas** como barrera integral.
- `ops/rollback_remote.sh` **rechaza** un rollback —también si solo
  reemplazaría imágenes— cuando ya existe un incidente de recuperación,
  en lugar de reinterpretar el incidente como autorización para continuar.
  No limpia ni reemplaza el marcador.

## Evidencia y límites

Las pruebas aisladas verifican casos de release administrada, metadatos
parciales, enlaces simbólicos, incidentes de distintos orígenes y rechazo de
rollback de aplicación sin operaciones Docker ni cambios de versión. No
ejecutan restores sobre VPS ni datos de jugadores.

**Pendiente P1 #174:** un rollback manual sin incidente preexistente y una
restauración anidada bajo lock legacy pueden todavía recuperar un backup
sin demostrar una barrera de escritura mantenida desde su captura. Además,
un restore directo sobre una base no administrada sin marcador tampoco queda
protegido por una barrera universal. Estas rutas **no deben usarse sobre datos
reales** hasta implementar el único coordinador G5, con validación de
sesiones, permisos, admisión, identidad y manifiesto duradero.

La decisión de bloqueo de estos casos es intencional: mayor indisponibilidad
temporal es preferible a borrar commits confirmados por accidente.
