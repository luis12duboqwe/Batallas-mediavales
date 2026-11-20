# BM-0093 — Procedencia exacta de backup y detección segura del esquema

## Problemas evitados

1. Un fallo de conexión, autenticación o ejecución de la consulta PostgreSQL **no** es evidencia de una base vacía. La inspección de `public.users` debe terminar correctamente y devolver exclusivamente `t` o `f`.
2. Una versión instalada previamente nunca puede continuar por la vía de **primera instalación** si de pronto falta `public.users`; debe investigarse la integridad del esquema.
3. Seleccionar el archivo más reciente de `BACKUP_DIR` es inseguro cuando un cron, otra sesión o una prueba concurrente crean un respaldo. El rollback debe usar **exactamente la copia verificada creada para ese despliegue**, sin deducirla de marcas de tiempo ni del orden de los archivos.

## Contrato de resultado del backup

El script `ops/backup_postgres.sh` permite un parámetro de entorno opcional `BACKUP_RECEIPT_FILE` que apunta a un archivo normal preexistente. Solo después de publicar el dump, comprobar su checksum y completar retención escribe en él la ruta exacta de su propio archivo de respaldo. Las ejecuciones habituales (cron/operación manual) no necesitan pasar este parámetro.

`ops/deploy_remote.sh` crea un recibo privado dentro de `.ops-state`, invoca el backup con ese recibo y comprueba que su contenido es un dump nuevo, regular y no vacío en el `BACKUP_DIR` configurado, acompañado de checksum. El archivo recibido se trata como **candidato**: solo se asigna como snapshot de rollback después de superar todas las validaciones. El directorio de destino y el directorio del archivo se comparan como rutas normalizadas, incluidas barras finales. Si no existe o no es válido, la operación aborta y no utiliza el archivo rechazado para restaurar. Un backup de otra ejecución no puede sustituir silenciosamente el del despliegue. El recibo temporal se elimina tras utilizarse y durante cualquier rollback por error.

## Errores antes y después de las migraciones

Mientras la nueva release **no** haya iniciado `docker compose up`, el rollback
no puede arrancar servicios mediante `compose up` porque sus dependencias
ejecutarían migraciones y seed. Los fallos previos restauran únicamente el
archivo de configuración anterior, sin arrancar dependencias.

Si un entorno con release previa pierde `public.users`, la consulta falla
o devuelve un valor inesperado, se conserva `.ops-state/recovery-required`
para investigación humana incluso cuando la configuración se recupere.
No se intenta regenerar el esquema mediante migraciones automáticas.

Una vez iniciado el despliegue de servicios, el rollback controlado puede
utilizar únicamente el snapshot validado y vinculado a esa ejecución.

## Validación

- Pruebas con dobles locales: fallo de sondeo, resultado inesperado, desaparición del esquema en una release existente, primera instalación confirmada, recibo ausente o extraño, y presencia de un backup ajeno que parece más nuevo.
- En CI G5, se comprueba con PostgreSQL real el recibo generado por `pg_dump` y se restaura la copia identificada por ese recibo incluso después de generar backups concurrentes adicionales.
- No se ejecuta restauración sobre servidores externos ni se interpreta la aprobación de CI como certificación de recuperación de producción.

## Riesgos restantes

La recuperación completa ante caída del host, aislamiento frente a ejecuciones de despliegue simultáneas, retención externa, observabilidad y RPO/RTO reales deben validarse en staging antes de abrir beta.
