# BM-0093 — Exclusión mutua de despliegue y rollback manual

`ops/deploy_remote.sh` y `ops/rollback_remote.sh` modifican
`.release.env`, `.release-sha`, manifiestos y servicios compartidos.
Dos ejecuciones simultáneas pueden intercalar esos cambios y perder
trazabilidad sobre la versión activa.

Ambos scripts abren `.ops-state/deploy.lock` con permisos restringidos
y adquieren un `flock -n` **antes** de leer o modificar metadatos activos.
El bloqueo permanece abierto durante toda la operación. Si está ocupado,
se rechaza la segunda acción sin acceder a Docker o a la base de datos.

El archivo del lock no es un marcador de incidente: se conserva entre
ejecuciones y el kernel libera el bloqueo al terminar el proceso. No es
necesario borrar el archivo después de un error ni en un reinicio.

## Validación

Pruebas de regresión retienen una cerradura POSIX sobre el archivo de lock
en un proceso de pruebas, intentan un despliegue y un rollback aislados,
comprueban el rechazo sin cambios y vuelven a intentarlos después de liberar
el bloqueo. Docker, restore y smoke siguen siendo dobles locales.

## Límites

Este contrato se aplica a los dos comandos de gestión de releases, no a
acciones manuales por fuera de ellos (por ejemplo, un `pg_restore` directo
o cambios de Docker hechos por SSH). Estas acciones deben coordinarse
operacionalmente y documentarse para el ensayo de staging. Un bloqueo
local no coordina dos servidores diferentes ni sustituye un orquestador.
