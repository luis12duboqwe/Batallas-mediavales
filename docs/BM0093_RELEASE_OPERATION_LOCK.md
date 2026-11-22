# BM-0093 — Exclusión mutua de despliegue, restore y rollback

`ops/deploy_remote.sh` y `ops/rollback_remote.sh` modifican
`.release.env`, `.release-sha`, manifiestos y servicios compartidos.
Dos ejecuciones simultáneas pueden intercalar esos cambios y perder
trazabilidad sobre la versión activa.

Ambos scripts abren `.ops-state/deploy.lock` con permisos restringidos
y adquieren un `flock -n` **antes** de leer o modificar metadatos activos.
El bloqueo permanece abierto durante toda la operación. Si está ocupado,
se rechaza la segunda acción sin acceder a Docker o a la base de datos.

`ops/restore_postgres.sh` también adquiere este lock cuando se ejecuta
directamente, antes del preflight y de cualquier operación Docker. Cuando
deploy o rollback lo invocan como subproceso, hereda el descriptor ya bloqueado
para conservar la exclusión mutua sin bloquearse a sí mismo. Comprueba el lock
con un descriptor independiente antes de confiar en el descriptor heredado,
para que un descriptor abierto pero desbloqueado no se confunda con un restore
anidado.
El script copia el dump a un directorio privado y verifica el hash de la
copia. La comprobación de identidad y el restore destructivo leen el mismo
inodo a través de un descriptor abierto.

Antes de detener escritores, todo restore real necesita un marcador de
recuperación regular, no vacío y del usuario que ejecuta la operación.
Cuando falta, el restore lo publica de forma exclusiva, incluso con un
descriptor de lock heredado. El operador debe certificar la recuperación para
retirar ese marcador. Deploy bloquea cualquier entrada en la ruta del
marcador, incluidos los enlaces simbólicos colgantes. Restore y rollback
rechazan los enlaces y demás tipos no regulares.

El rollback manual reserva un directorio privado bajo el lock y solicita
preparación con `PREPARE:<base>`, `RESTORE_PREPARE_ONLY=1` y
`RESTORE_START_SERVICES=0`. La preparación comprueba el checksum y la identidad
de la base antes de publicar un marcador nuevo, y devuelve el digest SHA-256
y la identidad del archivo. El padre pasa esos valores a la fase
`RESTORE:<base>`, que verifica la misma copia sin crear una segunda. El
directorio que creó el padre es la única ruta que usa para limpiar la copia.

En un despliegue con una versión activa, PostgreSQL debe estar disponible
para la consulta de esquema y el backup. Deploy usa la configuración anterior
para consultar el esquema y preparar el dump, con el lock y el marcador ya
activos. Solo el primer despliegue puede arrancar PostgreSQL durante esta fase.
Deploy conserva `.release.env` apuntando a la versión anterior hasta verificar
la copia privada con `PREPARE:<base>` y descargar las imágenes candidatas.
Si falta espacio en `.ops-state`, falla la copia o la verificación, o el recibo
es inválido, el despliegue termina antes de ejecutar `compose up`, migrar,
sembrar datos o restaurar. El puntero anterior ya está en su sitio y se retira
el marcador si el estado del esquema es conocido.

Si falla el despliegue después de iniciar el candidato, el rollback automático
pasa a `RESTORE:<base>` la misma ruta privada y el recibo SHA-256, dispositivo e
inodo que devolvió la preparación. Restore verifica la copia privada y la usa
sin volver a leer ni copiar el dump original. Si fallan el restore, el smoke
o la publicación del entorno recuperado, el marcador se conserva. Al salir,
deploy limpia sus temporales, incluida la copia privada. El manifiesto del
despliegue exitoso conserva la ruta del backup original para el rollback manual.

El archivo del lock no es un marcador de incidente: se conserva entre
ejecuciones y el kernel libera el bloqueo al terminar el proceso. No es
necesario borrar el archivo después de un error ni en un reinicio.

## Validación

Pruebas de regresión retienen una cerradura POSIX sobre el archivo de lock
en un proceso de pruebas, intentan un despliegue y un rollback aislados,
comprueban el rechazo sin cambios y vuelven a intentarlos después de liberar
el bloqueo. La regresión de restore comprueba que una invocación directa no
llega a Docker si deploy mantiene el lock, y que un restore anidado acepta el
descriptor del proceso propietario lanzado mediante Bash. También cubre un FD
heredado sin lock, sustitución atómica del pathname y el rechazo read-only de
snapshots con checksum o identidad incorrectos antes del marcador. Las pruebas
de despliegue simulan ENOSPC durante la copia, comprueban el orden de
preparación y arranque, y ejecutan el script de restore con Docker y smoke
simulados para comprobar que el rollback usa una sola copia incluso si
desaparece el dump original.

## Límites

Este contrato se aplica a los comandos de gestión de releases y al script de
restore, no a acciones manuales por fuera de ellos (por ejemplo, un
`pg_restore` directo o cambios de Docker hechos por SSH). Estas acciones deben
coordinarse operacionalmente y documentarse para el ensayo de staging. Un
bloqueo local no coordina dos servidores diferentes ni sustituye un
orquestador.
