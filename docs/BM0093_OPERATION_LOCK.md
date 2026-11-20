# BM-0093 — Exclusión mutua de operaciones sobre una instalación

## Riesgo evitado

Dos sesiones pueden intentar simultáneamente desplegar una nueva versión y
hacer rollback de otra, modificando los mismos archivos `.release.env`,
`.release-sha` y `.ops-state/recovery-required`. La existencia del marcador de
incidente no es un bloqueo atómico: ambas sesiones podrían comprobar que
todavía no existe y continuar.

## Contrato implementado

`ops/operation_lock.sh` se carga al inicio de `ops/deploy_remote.sh` y
`ops/rollback_remote.sh`. Adquiere un bloqueo exclusivo no bloqueante de
Linux mediante `flock` sobre `.ops-state/operation.lock`, con permisos
privados. El descriptor se mantiene abierto hasta que termina el script.

Si otra sesión mantiene el bloqueo, la operación devuelve código 2 antes de
consultar o mutar metadatos de la release. La ruta del lock no puede ser un
enlace simbólico. No se borran archivos de bloqueo para «liberarlos»: se liberan
automáticamente cuando termina el proceso que retiene el descriptor.

## Pruebas

Los tests de despliegue y rollback adquieren de antemano el mismo lock mediante
`fcntl.flock` y demuestran que la segunda operación no ejecuta Docker,
recuperación ni modificaciones del estado. También se rechaza una ruta de
bloqueo que sea un enlace simbólico.

## Alcance y límites

Se serializan únicamente el despliegue automatizado y el rollback manual
cuando operan desde **esta instalación y el mismo host**. Las copias regulares
pueden seguir ejecutándose concurrentemente (con nombres privados y hashes).
La restauración manual directa requiere una ventana de mantenimiento controlada.
Esto no sustituye locks distribuidos para varias máquinas ni certifica un
simulacro real de desastre en staging. Producción permanece deshabilitada.
