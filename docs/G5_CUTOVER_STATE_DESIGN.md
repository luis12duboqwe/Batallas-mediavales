# Manifiesto durable de cutover G5

**#174 sigue en NO-GO.** Este módulo aún no conecta Nginx, backend ni worker y
no activa producción.

El manifiesto persiste en `<host-root>/.ops-state/g5-cutover.json`, en
almacenamiento local del host y fuera de cualquier volumen o árbol que se
restaure con PostgreSQL. Una vez autorizada la apertura de escritores, restaurar
el dump previo al cutover podría eliminar commits posteriores al backup.

| Referencia | Alcance |
| --- | --- |
| PR181 | Gate opt-in en el edge. La barrera completa también debe cubrir backend, WebSocket, workers, tareas programadas y escritores directos de todas las instancias. |
| PR175 | Recuperación actual con el lock del gestor, el marcador de recuperación y una copia validada del dump. |
| PR180 | Prueba aislada de pérdida de una escritura confirmada después del snapshot y comprobación de advisory locks de PostgreSQL. Véase [la reproducción BM0093](BM0093_WRITE_BARRIER_REPRO.md). |
| #174 | Bloqueo de restore del dump pre-cutover cuando pudieron ocurrir escrituras posteriores. Este módulo aporta la decisión persistente. El cierre requiere conectar la barrera y todos los puntos de entrada de restore. |

## Protocolo del gestor

1. Adquirir `.ops-state/deploy.lock` con el protocolo actual del gestor.
   Cerrar la admisión de escrituras, drenar transacciones y detener escritores
   antes de tomar el dump. Usar la preparación de recuperación existente
   para validar la base incluida en el archivo y conservar una copia privada,
   durable e inmutable durante la operación.
2. Invocar explícitamente `prepare` después de verificar la barrera. El
   identificador vincula ambos SHA completos de release, SHA-256 y ruta canónica
   de la copia, proyecto Compose y base de datos. El módulo comprueba los bytes
   del dump y registra `PREPARED`.
3. Registrar `MIGRATING` antes de migrar y `VERIFIED_READONLY` después de
   verificar el candidato con la barrera cerrada y los escritores bloqueados.
4. Confirmar de nuevo la barrera bajo el lock del gestor. Avanzar explícitamente
   a `COMMITTED_WRITERS_ALLOWED` y esperar el éxito de `advance` antes de
   habilitar **cualquier** escritor. El commit es terminal aunque falle la
   reapertura.
5. Para restaurar desde `PREPARED`, `MIGRATING` o `VERIFIED_READONLY`,
   comprobar nuevamente la barrera, su continuidad desde el snapshot y la
   identidad de la operación. Mantener el lock del gestor y la barrera
   durante la verificación, el restore y la reconciliación. Si hay
   incertidumbre sobre escrituras, registrar `RECOVERY_REQUIRED` desde
   la fase previa al commit cuando sea posible y gestionar el incidente
   sin ese restore. El gestor conserva el marcador de recuperación que
   corresponda.

El restore se rechaza si falta el manifiesto, el backup, la identidad coincide
solo en parte, el estado está corrupto o la fase es desconocida o terminal.
Tras un crash, el gestor debe reconciliar los servicios y demostrar que la
barrera se mantuvo cerrada. Una fase previa al commit es insuficiente por sí
sola. Para invocar `prepare`, el gestor debe establecer que la inicialización
es nueva, porque un archivo ausente también puede deberse a pérdida de estado.

El modelo usa un único slot por raíz de releases. Tanto
`RECOVERY_REQUIRED` como `COMMITTED_WRITERS_ALLOWED` son terminales.
`prepare` rechaza un slot ocupado incluso con otro ID. La rotación para
releases sucesivas queda para la integración y debe conservar la evidencia
terminal duradera fuera del slot reemplazable y evitar la reutilización de IDs
o dumps archivados. El gestor debe consultar esa evidencia antes de inicializar o
rotar. Ante pérdida del manifiesto o discrepancia con la evidencia, mantener la
barrera y reconciliar el incidente. Un manifiesto previo válido puede reproducirse
si alguien controla el árbol. El checksum detecta corrupción y no autentica el
historial.

## API y CLI

`CutoverStore(host_root, max_backup_bytes=...)` requiere una ruta absoluta
canónica y un límite entero positivo. El valor por defecto es 1 TiB. Un archivo
que exceda el límite se rechaza antes de leerlo, incluido un archivo disperso.
El hash lee el tamaño inicial en bloques y comprueba un byte adicional para
detectar crecimiento. Un EOF prematuro o cambios observables del archivo también
impiden la entrega del descriptor. El hash mantiene el lock exclusivo. Ajustar
el límite a los dumps esperados y al tiempo de lectura del almacenamiento, ya que
el límite de bytes no impone un plazo de E/S.

Ejecutar `python3 ops/g5_cutover_state.py <comando> --host-root <ruta>`.
`prepare` y `advance` requieren `--operation-id`, `--previous-sha`,
`--candidate-sha`, `--backup-sha256`, `--backup-path`,
`--compose-project` y `--postgres-db`. `prepare` requiere también
`--backup-root`. `advance` requiere `--expected` y `--to` para comparar la
fase y avanzar en una sola operación. `show` imprime el manifiesto validado
para inspección. La CLI devuelve 0 en éxito, 1 ante rechazo operativo y 2 ante
un error de sintaxis de argumentos.

**Nunca usar un código de salida 0 de la CLI para autorizar un restore.**
La única API de autorización es el gestor de contexto Python
`verify_restore_allowed`. El gestor debe consumir el `backup_fd` directamente
dentro del contexto y mantenerlo abierto junto con el lock del módulo, su
propio lock y la barrera hasta que termine el restore. Integrar el restore en
el mismo proceso del gestor permite conservar el contexto durante todo el
consumo. No reabrir la ruta ni usar el descriptor fuera del contexto.

La raíz configurada del backup debe ser privada, de modo `0700` y del
usuario efectivo. El módulo exige un archivo regular no vacío del mismo dueño,
con un solo enlace y modo `0400` o `0600`. Antes de congelar la copia el
gestor debe comprobar que se cerraron todos los descriptores de escritura,
aunque vaya a cambiar el modo a `0400`. Para admitir `0600`, el gestor
también debe controlar quién puede volver a abrirla para escritura hasta
finalizar el consumo. Si no puede demostrar ese control, debe aprovisionar
una copia privada bajo control exclusivo antes de verificarla y consumirla.
El módulo revisa la ruta, el inode y sus metadatos antes de entregar el FD
y al salir normalmente. Un cambio detectado al salir exige reconciliar el
restore. Un FD abierto para lectura no congela sus bytes y ninguna de estas
comprobaciones garantiza inmutabilidad frente a root del host o a un proceso
con acceso de escritura al inode.

## Exclusión y durabilidad

El módulo toma un `flock` no bloqueante sobre el descriptor del directorio
`.ops-state`. La mutación y la comprobación de restore toman el lock
exclusivo. `show` toma el lock compartido. El bloqueo del directorio
es independiente del archivo `deploy.lock`. El orden de adquisición es
siempre `deploy.lock` del gestor y después el lock del módulo. El módulo
carece de flags que acrediten la barrera. Corresponde al gestor verificarla
y mantener su propio lock. Se deben evitar llamadas anidadas al módulo
dentro del contexto de restore.

El árbol de control debe permanecer estable, protegido y separado de los
reemplazos de releases o restores. La raíz del host pertenece al usuario
efectivo y carece de permisos de escritura para grupo y otros. Su hijo
`.ops-state` pertenece al usuario efectivo y requiere modo `0700`.
Los componentes se abren sin seguir symlinks. Los ancestros deben pertenecer
a root o al usuario efectivo y estar protegidos contra sustitución por otros
usuarios. Se admiten ancestros compartidos con sticky bit como `/tmp` cuando
los componentes protegidos que contienen tienen un dueño de confianza.
Se compara el directorio bloqueado con una nueva apertura de su ruta antes
y después de la operación y se revisan las entradas durante lectura y
publicación. Si alguien con permisos sobre el árbol lo sustituye durante
el uso, dos procesos pueden alcanzar inodes distintos antes de detectar el
cambio. La exclusión y el historial dependen de que el gestor preserve el
árbol y la evidencia terminal.

El proceso propietario libera explícitamente el `flock` al salir del contexto,
incluso si un hijo todavía conserva el descriptor. No hacer `fork` con el
lock activo. Los hijos no heredan autorización y deben descartar el contexto,
los descriptores y la instancia heredados.

El módulo escribe un temporal exclusivo
`0600` en el mismo directorio, sincroniza el archivo, lo publica con
`os.replace` y sincroniza el directorio antes de devolver éxito. La
secuencia requiere un filesystem local que ofrezca esas garantías.
Un crash antes del replace deja vigente el último manifiesto y cualquier
temporal huérfano se ignora. Un fallo al sincronizar el directorio después
del replace deja la publicación incierta. Un commit visible bloquea
restore y una invocación fallida impide habilitar escritores. La verificación
de restore también exige que se pueda sincronizar el directorio.

Los scripts actuales siguen el protocolo de recuperación de PR175. La
conexión de este componente con Nginx, backend, worker y el gestor de releases,
y la prueba de extremo a extremo de la barrera, quedan pendientes para #174.
