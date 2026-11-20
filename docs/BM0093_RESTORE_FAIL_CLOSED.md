# BM-0093 — Restauración segura ante fallos

La restauración PostgreSQL debe rechazar operaciones peligrosas antes de
detener escritores, terminar sesiones o reemplazar la base.

**Correcciones:** el checksum se compara ahora con el archivo seleccionado
para restaurar, no con otra ruta indicada dentro del fichero `.sha256`.
Si `docker compose stop backend worker` falla, se cancela el procedimiento
en lugar de ignorar el error y continuar con `pg_restore`.

**Pruebas de regresión:** el CI G5 crea una copia alterada acompañada de un
checksum de otra copia válida, y simula un fallo del comando Docker de
detención. Comprueba que ambas operaciones se rechacen y que la base conserve
su marcador antes de efectuar una restauración real controlada en el entorno
efímero del propio CI.

**Límites:** no se ha restaurado ningún sistema productivo. Antes de cerrar
BM-0093 deben verificarse backups externos, procedimientos de recuperación
en staging, tiempos RPO/RTO y la recuperación ante pérdida de servidor.

**Aislamiento de backups:** cada ejecución usa un directorio temporal privado y un
identificador único, además de la marca de tiempo. Dos respaldos creados en el
mismo segundo no comparten archivo temporal ni sobrescriben el anterior. Se
publican mediante enlaces atómicos únicamente archivos completos con checksum;
si falla la verificación se retira la pareja creada por esa ejecución. La
prueba G5 fija artificialmente la misma hora para dos exportaciones y verifica
que ambas permanecen legibles e íntegramente verificadas. Esto no sustituye los
respaldos externos ni una restauración ensayada en staging.
