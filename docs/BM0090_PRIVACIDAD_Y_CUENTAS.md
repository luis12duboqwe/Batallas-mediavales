# BM-0090 — Privacidad, cuentas y retención

## Estado técnico verificable

**Bloque A: exportación de datos (fusionado y validado en CI).** La ruta autenticada
`GET /auth/me/export` devuelve un JSON con esquema versionado. Usa el usuario
derivado del JWT validado por el servidor, **nunca** un ID de cuenta
proporcionado por el cliente. Su contenido se genera con listas explícitas de
campos, no serializando los modelos de base de datos. Las cabeceras
`Cache-Control: private, no-store`, `Pragma: no-cache` y
`Content-Disposition: attachment` reducen almacenamiento accidental en cachés
y ofrecen un nombre predecible de descarga.

Las categorías exportadas incluyen: perfil y preferencias, pertenencia a
mundos, ciudades, edificios, tropas, colas, ofertas del mercado, héroes,
objetos, aventuras, progreso, notificaciones, mensajes enviados y recibidos,
contenido social redactado por el jugador, tickets abiertos por el jugador y
objetos adquiridos. Los registros de otros usuarios se excluyen salvo los
mensajes que el titular recibió o envió, donde solo se incluyen los
identificadores de las partes y el contenido de la conversación accesible al
titular.

Los hashes de contraseñas, tokens de verificación y recuperación, versión de
autenticación, motivos internos de moderación y datos de otras cuentas no se
exportan. Las pruebas automatizadas cubren usuario no autenticado, JWT
inválido, JWT revocado por `auth_version`, aislamiento entre dos cuentas,
varios mundos, perfil sin ciudades y descarga en navegador.

### Alcances y limitaciones

El JSON es una **exportación de datos de la aplicación**, no una copia íntegra
de base de datos ni un mecanismo de restauración. No certifica todavía que
todos los datos indirectos y derivados (por ejemplo, historiales de combates,
telemetría, logs de infraestructura, copias de seguridad y pagos externos
eventuales) estén cubiertos. El archivo contiene información confidencial y
se entrega directamente al navegador autenticado; el servidor no lo envía
por correo ni almacena un archivo generado.

## Bloque B — Solicitudes de privacidad (revisión manual)

La API autenticada `GET/POST /auth/me/privacy-requests` permite registrar
solicitudes de eliminación, corrección, consulta de retención y otras dudas.
**Registrar una solicitud no elimina, bloquea, modifica ni anonimiza una
cuenta**. Los casos pasan al sistema de soporte ya existente, donde solo
personal autorizado por `support.manage` puede cambiar su estado.

Los identificadores de usuario se obtienen exclusivamente del JWT autenticado.
Cada jugador consulta únicamente sus propios casos. El tipo de caso y el
asunto se fijan por el servidor; el endpoint de soporte general no puede
crear asuntos reservados de privacidad. El sistema rechaza opciones no
reconocidas y campos inesperados, y limita los detalles a 1000 caracteres.
Mientras un caso de la misma categoría permanece abierto o en revisión,
una repetición devuelve el número anterior en lugar de crear uno nuevo.

**Límite:** PostgreSQL serializa solicitudes simultáneas mediante bloqueo
de fila del usuario; en SQLite no existe ese mismo bloqueo de filas y la
deduplicación concurrente es de mejor esfuerzo. No se garantiza tiempo de
respuesta ni conclusión favorable sin política aprobada. No se ejecutan
operaciones destructivas ni migraciones de esquema.

La interfaz del perfil ofrece el formulario, confirmación de recepción
y consulta de estado; la prueba G29 valida el recorrido real, persistencia
e idempotencia secuencial.

### Bloque C — Unicidad transaccional de solicitudes activas

La migración `0019_privacy_active_unique` agrega una restricción
única parcial de `(requester_id, subject)` para las cuatro categorías de
privacidad cuando el estado es `open` o `in_progress`.
Se aplica en SQLite y PostgreSQL. No limita tickets normales ni el historial
resuelto/cerrado. Reabrir un caso histórico mientras otro del mismo tipo está activo devuelve HTTP 409 sin registrar falsos cambios de soporte. El endpoint sigue intentando devolver el caso existente y,
si una solicitud concurrente gana la carrera, revierte la transacción fallida
y consulta el caso ganador. Las pruebas incluyen el índice real en SQLite,
cambios de estado, categorías distintas y dos sesiones en PostgreSQL.

**Migración segura:** antes de crear el índice se detectan duplicados activos.
Si hay alguno, la migración se bloquea **sin eliminar ni cerrar solicitudes**.
Personal autorizado debe revisar y resolver los duplicados, documentar la
decisión y volver a ejecutar la migración. Un CI verde en una base nueva no
certifica la ausencia de duplicados en una base externa.

## Pendientes para cerrar BM-0090

1. **Términos y política de privacidad:** redactar y aprobar los textos
   legales reales, determinar entidad operadora, jurisdicción, edad mínima,
   contacto y categorías de datos. No publicar plantillas como documentos
   legales aprobados.
2. **Consentimiento y aceptación:** almacenar versión de documentos,
   fecha y evidencia de aceptación cuando exista una versión legal aprobada,
   con acceso a versión anterior. El consentimiento opcional debe poder
   retirarse sin bloquear operaciones necesarias del juego.
3. **Eliminación de cuenta:** analizar FKs y retención de evidencias
   anticheat, soporte, mensajería, ganadores de mundos, pagos si se incorporan,
   backups y datos de terceros. Diseñar borrado/anonimización transaccional,
   revocación de sesiones, periodo de recuperación y pruebas adversariales.
   No exponer un borrado irreversible hasta demostrarlo con SQLite,
   PostgreSQL y simulación en staging.
4. **Retención:** establecer periodos fundamentados para operaciones,
   auditoría, comunicaciones, telemetría y backups, con limpieza automática
   verificada y procedimiento de solicitud del titular.
5. **Evaluación jurídica y de seguridad:** revisar jurisdicción aplicable,
   derechos del titular, tratamiento de menores, transporte TLS y divulgación
   de datos a proveedores antes de cualquier lanzamiento real.

**Puerta:** BM-0090 no está cerrado por completar solo la exportación. Nada
en este PR habilita cuentas reales, pagos ni publicación en producción.
