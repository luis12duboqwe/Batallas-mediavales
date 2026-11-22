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

## Identidad de Compose y recuperación de base detenida

El preflight de una release gestionada compara también `COMPOSE_PROJECT_NAME`
entre configuración activa y candidata, además de la identidad PostgreSQL.
Dos proyectos Compose pueden tener el mismo nombre y credenciales de base
pero volúmenes y datos distintos. No se permite cruzar ese límite mediante
un despliegue normal: requiere una adopción o migración autorizada.

Antes del backup, el gestor inicia **únicamente** el servicio PostgreSQL con
la configuración de la release anterior. Esto permite recuperarlo de una
parada ordinaria sin ejecutar dependencias de migración/seed. Si falla, el
despliegue termina antes de mutar la release y conserva la configuración
anterior; una vez corregida la disponibilidad de la base, puede reintentarse.

Se rechaza antes de instalar traps de limpieza un fichero de entrada que
coincida con `.release.env.next`, así como un enlace simbólico en esa ruta.
Esto impide que la limpieza de una operación fallida borre el fichero
proporcionado por el operador. Las regresiones cubren proyecto cambiado,
fallo y reintento de PostgreSQL detenido y archivo de entrada coincidente.

## Blindaje adicional de interpolación y disponibilidad inicial

La identidad `COMPOSE_PROJECT_NAME` entre una release administrada y la nueva
debe ser un **literal** compatible con los nombres de proyecto Compose
(minúsculas, números, guiones y guiones bajos). Se rechazan referencias
`${VARIABLE}` incluso si los dos archivos contienen la misma expresión:
Compose podría resolverla desde variables externas diferentes y apuntar a
volúmenes PostgreSQL distintos. Toda adopción entre proyectos requiere un
procedimiento de migración separado y ensayado.

El arranque limitado al servicio `database` usa `docker compose up -d
--wait --wait-timeout 120 database` para esperar el estado saludable antes de
consultar el esquema. Si no alcanza health, aborta antes de ejecutar
migraciones o seed. El fallo de arranque de una base gestionada es reintentable
sin modificar los punteros de release; una consulta SQL fallida **después**
de confirmar health sigue tratándose como incidente de integridad.

Las referencias dinámicas en los campos de identidad de PostgreSQL se
rechazan cuando Compose las interpolaría. En cambio, las contraseñas que
contienen `$` entre comillas simples o con `$$` como escape son valores
literales válidos: no se confunden con variables externas. Las pruebas
protegen ambas variantes y la negativa para `${DB_SECRET}` sin protección.

En una **primera instalación**, un error de arranque o health de la base
anterior a migraciones conserva intencionalmente el marcador
`recovery-required`: no hay release anterior certificada a la que volver y
un volumen parcialmente inicializado no debe adoptarse automáticamente.
Antes de reintentar, un operador debe comprobar que la base no contiene datos
y completar el procedimiento de adopción/limpieza controlada.
