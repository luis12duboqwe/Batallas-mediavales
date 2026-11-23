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

**Avance posterior:** `ops/rollback_remote.sh` rechaza ahora todo
`rollback_backup` no vacío **antes** de preflight, copias, comandos Docker,
marcadores, smoke o actualización de `.release-sha`/`.release.env`, incluso
sin un incidente preexistente y aunque el snapshot esté íntegro. El rollback
solo de aplicación conserva las validaciones de metadatos y de incidentes.
El rechazo no ofrece una variable de entorno de excepción: un operador no
puede convertir un checksum correcto en permiso para descartar escrituras.
- En rollback exclusivamente de aplicación, `docker compose up --no-deps`
  impide que las dependencias `backend → seed → migrate` ejecuten SQL
  inadvertidamente. Requiere que la base de datos existente esté disponible;
  si no lo está, falla el smoke y conserva el incidente, sin sembrar ni migrar.
- La salida fallida posterior a solicitar `docker compose up --no-deps`
  intenta `docker compose stop -t 120 backend worker migrate seed`, antes
  de borrar archivos temporales. Esto cubre fallos de arranque parcial,
  smoke y publicación final de metadatos. El marcador de recuperación no
  se elimina por error y el código de salida original se conserva aunque
  falle el stop; en ese caso emite alerta crítica para inspección.
- El arranque Compose se espera como hijo supervisado; `SIGTERM`/
  `SIGINT` dirigidos al shell deben esperar a que termine el arranque antes
  del stop final, para que el stop no ocurra antes de que un escritor aparezca.
  Un `SIGKILL` o caída total de host no es recuperable con traps de shell.
- Si el marcador de incidente cambia o desaparece justo antes de dar éxito,
  el rollback falla y también intenta cerrar escritores, en vez de publicar
  éxito silenciosamente. Si desaparece, intenta recuperar el hardlink original
  o crear un incidente nuevo con creación exclusiva (`O_EXCL`), fsync del
  archivo y del directorio; nunca sobrescribe un incidente ajeno. Si no puede
  certificar la persistencia, conserva el archivo de evidencia original
  cuando existe y emite un error crítico. No se deshacen escrituras ya confirmadas.

**Pendiente P1 #174:** la restauración anidada bajo lock en
`restore_postgres.sh` y el restore directo en instalaciones no administradas
siguen sin demostrar una barrera de escritura mantenida desde la captura;
el futuro coordinador G5 debe sustituir estas rutas, no reutilizar la vía
legacy para datos con actividad. Estas rutas **no deben usarse sobre datos
reales** hasta implementar el único coordinador G5, con validación de
sesiones, permisos, admisión, identidad y manifiesto duradero.

La decisión de bloqueo de estos casos es intencional: mayor indisponibilidad
temporal es preferible a borrar commits confirmados por accidente.
