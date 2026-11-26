# BM-0093 / G5 — Coordinador de ciclo de vida bajo una sola concesión

**NO-GO para producción. No invocar sobre datos reales.**

El coordinador G5Lifecycle retiene deploy.lock desde antes del cierre de
admisión hasta después de la última acción. Comparte la preparación real
existente y vuelve a validar el marcador (incluido su contenido vía
identidad y metadatos de modificación), lock, directorio y fase antes de
las transiciones sensibles. No ofrece CLI, resume, borrado de incidentes ni
adaptador de despliegue. Los scripts legacy siguen bloqueados.

Secuencia: PREPARED (snapshot verificado) -> MIGRATING (solo ejecutor de
mantenimiento) -> VERIFIED_READONLY (verificación del candidato sin
escritores) -> publicación de metadatos -> COMMITTED_WRITERS_ALLOWED
durable -> reapertura. El adaptador tiene que acreditar exclusión
**continua**, no solo observación puntual, incluyendo rutas privilegiadas.
Una confirmación de estado diferente de True literal no autoriza continuar.

Solo MigrationRejected emitida por el ejecutor de migración ante un fallo
conocido y su salida confirmada permite intentar recuperación bajo el mismo
lock, antes de publicar candidato, con exclusión continua y el descriptor
del archivo verificado por CutoverStore. El restore debe conservar identidad
de base, barrera SQL y metadatos; no se permite recrear la base o volver a
abrir el archivo por nombre. Incluso una recuperación correcta termina en
RECOVERY_REQUIRED, sin reapertura automática. Timeout, señal, pérdida de
respuesta, deriva de barrera, fallo de verificación/publicación o restore
incierto bloquean nuevas acciones y requieren reconciliación manual.
Después de COMMITTED nunca se retrocede ni restaura el snapshot, aun si
falla la reapertura. SIGKILL deja el marcador y la última fase persistida;
no se intenta recuperar desde otro proceso sin un protocolo certificado.

## Validación

Pruebas unitarias: orden, lock en cada acción, fase previa a migración y
reapertura, rechazo conocido, recuperación por FD, rechazo sin continuidad,
archivo alterado, interrupción, error de restauración/verificación/
publicación, metadatos alterados, deriva postcommit y fallo al reabrir.

El ensayo obligatorio combinado añade dos proyectos internos desechables:
- Cambio real de esquema y datos PG15, verificación, metadata fsync,
  COMMITTED, y solo entonces reapertura controlada de rol SQL app y
  confirmación de una escritura posterior. Se comprueba rechazo de restore
  del snapshot previo. HTTP y contenedores permanecen cerrados en este caso.
- Cambio de esquema/datos confirmado seguido de error SQL conocido,
  restauración real en la misma base desde FD (sin reemplazarla), verificación
  de filas, esquema y grants anteriores, RECOVERY_REQUIRED y barreras
  cerradas. Este restore aplica solo al esquema sintético del fixture.

## Pendientes

No es todavía la migración real Alembic/seed, ni una restauración completa
de un esquema arbitrario con objetos nuevos, ni un despliegue con el
backend/Socket.IO real. Falta la exclusión de rutas privilegiadas en host
real, inventario y preservación durable de parámetros originales para
reapertura, publicación de metadatos real, reinicio/recuperación desde
crash y pruebas controladas de staging. No declarar RPO=0 ni cerrar #174.

## Exclusión de carreras de fase

El acceso al FD exige fase exacta (PREPARED para verificación inicial,
MIGRATING para restore) bajo el lock del manifiesto. Migración, publicación
y reapertura también retienen el lock exclusivo durante todo el callback;
una transición competidora anterior al lock impide ejecutar el callback.
Los adaptadores no deben adquirir recursivamente locks de CutoverStore.
El ensayo de reapertura verifica directamente la identidad y checksum del
recibo durable de COMMITTED mientras ese lock está en posesión del
coordinador. Se añaden regresiones de las dos ventanas de carrera, escrituras
concurrentes durante acciones y salida del contexto en un proceso hijo
forked (no puede desbloquear la concesión del padre).

## Clasificación de rechazo y guardas

Solo una excepción `MigrationRejected` originada directamente en `port.migrate`
puede habilitar la ruta de restore. El coordinador comprueba además la salida
correcta de las guardas de fase y lease antes de usar esa clasificación. Una
excepción del mismo tipo en continuidad, entrada o salida del lock constituye
incertidumbre: RECOVERY_REQUIRED, sin restore ni reapertura. Las regresiones
incluyen el rechazo legítimo seguido de un fallo de guarda.
