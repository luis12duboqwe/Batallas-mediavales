# BM-0090 — Privacidad, cuentas y retención

## Estado técnico verificable

**Bloque A: exportación de datos (PR en revisión).** La ruta autenticada
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
