# BM-0093 / G5 — barrera de admisión Nginx (opt-in)

**Estado: preparada, no activada ni certificada para staging/producción.**
La barrera no es una **barrera transaccional** completa: es solo una pieza
de la solución del P1 #174; no sustituye el drenaje
de escritores, la coordinación PostgreSQL ni la máquina de estados de cutover.

## Activación explícita y compatibilidad

`docker-compose.yml` (desarrollo) y `docker-compose.deploy.yml` (protegido)
continúan utilizando el `nginx.conf` normal, sin cambio de comportamiento.
La configuración protegida adicional vive en `nginx.g5.conf`, aplicada
mediante el overlay oficial `docker-compose.g5.yml`. Ningún script actual
de despliegue, rollback o restore incluye ese overlay: **está inactivo**.

Cuando el orquestador G5 esté desarrollado y certificado, será quien seleccione
ambos archivos con `docker compose -f docker-compose.deploy.yml
-f docker-compose.g5.yml`. No activar manualmente este overlay todavía:
el flujo vigente realiza smoke público, no mantiene cerrado el gate durante
migración/backup y no puede garantizar RPO=0. La automatización del overlay
queda bajo #174. No se usa variable de selección de configuración desde la
sesión: evita que el shell prevalezca sobre el env validado.

El workflow de despliegue incluye ambos archivos G5 en el bundle, pero
**no los usa** para iniciar o alterar el stack actual.

## Contrato de admisión

Con overlay activado, el control está en
`./.ops-state/edge-maintenance/open/`, un **directorio vacío y real**
de propiedad del operador, nunca un archivo o un enlace simbólico.

- Directorio `open/` ausente: todas las solicitudes a `/api`,
  `/api/` y `/socket.io` (incluidos polling y upgrade) reciben **HTTP 503**,
  `Retry-After: 60` y `Cache-Control: no-store`.
- Directorio `open/` existente, accesible y sin symlink: la admisión se
  autoriza. El limitador ordinario sigue devolviendo `429` bajo abuso;
  se ejecuta **después** de comprobar el gate.
- Archivo normal, FIFO, socket, enlace simbólico, ruta ilegible o marcador
  ausente: **cerrado**. La condición Nginx comprueba exclusivamente
  directorios con `try_files /open/` y `disable_symlinks on`; un
  `empty_gif` interno devuelve 200 a `auth_request` sin abrir archivos
  especiales que pudieran bloquear el worker.
- `/health` responde 200 solo como liveness del edge, NO como prueba de
  conectividad a PostgreSQL ni autorización para reabrir.
- No hay bypass mediante cabeceras, cookies, IP, query ni ruta sin barra.
  Las redirecciones permitidas preservan los parámetros `$is_args$args` y
  son **relativas** (`absolute_redirect off`), para no degradar HTTPS en Caddy
  al seguir un `308` que conserva método y cuerpo.

El directorio completo se monta `:ro` dentro del contenedor Nginx; solo
el operador en el host puede publicar o retirar la señal. Su directorio
padre debe tener owner controlado, permisos de escritura restringidos y
permiso de traversal para el usuario del Nginx.

## Operación local futura (solo durante ensayo de integración)

**Cerrar admisión** eliminando la señal:
```sh
dir=.ops-state/edge-maintenance
rmdir -- "$dir/open"
```
`rmdir` es atómico para un directorio vacío. Si falla porque falta, ya
está cerrado; si falla por contenido inesperado, abortar la operación y
verificar con peticiones reales 503 antes de tomar backup. No continuar
migraciones hasta confirmar que no entra tráfico.

**Abrir admisión** únicamente cuando el orquestador haya invalidado el
derecho de rollback al dump histórico y validado readiness:
```sh
dir=.ops-state/edge-maintenance
mkdir -p -- "$dir"
chmod 0755 "$dir"
mkdir -- "$dir/open"
chmod 0755 "$dir/open"
```
Con `umask 077` hay que normalizar los permisos para que un worker con
UID diferente pueda atravesar el directorio. **Los permisos no son el
mecanismo de cierre**: un worker con el mismo UID puede acceder antes del
`chmod`. Solo la ausencia de `open/`, comprobada mediante HTTP 503, acredita
el cierre. No se necesita `nginx -s reload`, reinicio de
Compose ni nuevas APIs. No crear el directorio abierto durante un reboot
por defecto.

## Límites y controles de seguridad

- Una solicitud que pasó el gate antes del cierre puede terminar y hacer
  commit después. Una sesión WebSocket establecida también puede permanecer.
  Es obligatorio bloquear nuevas admisiones, drenar solicitudes y parar
  **backend, worker, migrate, seed y escritores externos** antes de capturar
  el backup, verificando ausencia de transacciones pendientes en PostgreSQL.
- Antes de volver a permitir escritores, el sistema debe marcar durablemente
  que el dump anterior **ya no se puede restaurar automáticamente**.
  Si falla después de ese punto, recuperar hacia delante.
- El componente solo ha sido probado en procesos Nginx aislados con
  backends mock y en CI; **no** se desplegó ni se certificó staging.
  Tampoco sustituye monitoreo, ensayos de rollback, SMTP o aprobación G5.

Referencia: issues #174 y #161, PR #180 (reproducción de pérdida de
escrituras) y PR #175 (recuperación protegida existente).
