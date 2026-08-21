# Beta cerrada — privacidad, retención y términos operativos

Estado: **BORRADOR OPERATIVO PARA BETA CERRADA**

Este documento fija la política de producto que debe reflejarse en los textos públicos antes de invitar usuarios externos. No sustituye revisión jurídica para la jurisdicción donde se publique el juego ni para una futura monetización.

## 1. Alcance de la beta

Batalla Medieval se ofrece durante esta etapa como software en beta cerrada. Puede contener errores, cambios de balance, reinicios planificados y periodos de mantenimiento. El acceso puede limitarse por oleadas y retirarse cuando exista abuso, riesgo de seguridad o necesidad operativa.

La beta no promete disponibilidad continua ni conservación perpetua de progreso. Cualquier reinicio/migración que afecte progreso debe anunciarse de forma clara a los participantes antes de ejecutarse, salvo emergencia de seguridad o integridad de datos.

## 2. Datos que el servicio necesita

Categorías previstas por el producto actual:

- datos de cuenta: nombre de usuario, correo y estado de verificación;
- credenciales protegidas: hash de contraseña y metadatos de sesión/autenticación;
- datos del juego: mundos, ciudades, recursos, edificios, unidades, movimientos, alianzas, mensajes e informes;
- preferencias: idioma y ajustes disponibles;
- seguridad/operación: eventos administrativos, moderación, anti-cheat, errores y registros técnicos necesarios para investigar incidentes;
- métricas de onboarding: solo agregados para medir progreso/abandono, sin usernames, emails, IPs ni IDs en la respuesta de métricas G4.

No se debe registrar en logs el texto de contraseñas, tokens, secretos de infraestructura ni credenciales SMTP/DB.

## 3. Finalidades

Los datos se usan únicamente para:

- crear y proteger la cuenta;
- prestar las funciones del juego;
- sincronizar estado entre dispositivos/sesiones;
- prevenir abuso, fraude y trampas;
- investigar errores e incidentes;
- ofrecer soporte;
- medir de forma agregada la salud del onboarding y la beta;
- cumplir obligaciones legales aplicables.

No se contempla vender datos personales ni usar datos privados de mensajes para publicidad dirigida durante la beta.

## 4. Mensajería y contenido generado por usuarios

Mensajes, chat, nombres y contenido social pueden ser moderados cuando exista reporte, señal anti-abuso o investigación de seguridad. El acceso administrativo a este contenido debe limitarse a casos necesarios y quedar sujeto a auditoría cuando la herramienta lo permita.

Los usuarios no deben publicar datos personales de terceros, amenazas, acoso, contenido ilegal ni intentar evadir controles técnicos.

## 5. Retención objetivo de beta

La política inicial propuesta es:

| Categoría | Retención objetivo |
| --- | --- |
| Cuenta y progreso activo | mientras la cuenta participe en la beta |
| Backup operacional | 14 días por defecto, configurable por `BACKUP_RETENTION_DAYS` |
| Logs técnicos de aplicación/proxy | 30 días salvo investigación activa |
| Auditoría administrativa/seguridad | 90 días o mientras exista investigación activa |
| Tickets de soporte | 90 días después del cierre |
| Cuenta retirada de la beta | eliminación/anominización operativa dentro de 30 días, salvo obligación legal o investigación de seguridad |

Antes de prometer estos periodos públicamente debe verificarse que la infraestructura elegida puede aplicarlos. Si un proveedor mantiene copias de seguridad internas por más tiempo, ese plazo debe reflejarse en la política pública.

## 6. Solicitudes de privacidad

Durante la beta cerrada, las solicitudes de acceso, corrección o eliminación se procesarán manualmente a través del canal de soporte definido antes de abrir invitaciones.

Antes de aceptar una solicitud sensible se debe verificar que la persona controla la cuenta/correo correspondiente. No se debe enviar un volcado de datos a una dirección no verificada.

## 7. Seguridad

Controles mínimos requeridos por G5:

- HTTPS en la URL pública;
- secretos fuera del repositorio;
- imágenes inmutables por SHA;
- PostgreSQL en staging/producción;
- CORS explícito;
- autenticación de HTTP, Socket.IO y WebSocket según los gates anteriores;
- backups con checksum y restore probado;
- auditoría de dependencias;
- rollback de aplicación y base;
- congelar expansión de beta con cualquier P0/P1 abierto.

Ningún sistema puede garantizar riesgo cero. Un incidente que pueda afectar datos personales se debe tratar como P0 hasta determinar alcance.

## 8. Términos de uso de beta

Al participar, el usuario debe aceptar como mínimo:

1. el servicio está en beta y puede cambiar;
2. el acceso es personal y la cuenta no debe compartirse para evadir sanciones;
3. no se permite explotar vulnerabilidades, automatizar abuso, hacer trampas ni intentar acceder a datos de otros usuarios/mundos fuera de las reglas del juego;
4. no se permite acoso, spam, suplantación ni contenido ilegal;
5. los objetos, recursos, medallas y progreso del juego no representan dinero real ni propiedad financiera;
6. el operador puede corregir balances, revertir errores de integridad y suspender cuentas por abuso con trazabilidad administrativa;
7. una beta cerrada puede terminar o reiniciar bajo un plan anunciado;
8. el usuario debe cumplir la edad mínima y requisitos de consentimiento aplicables en su jurisdicción;
9. cualquier pago futuro requiere términos de compra/reembolso separados antes de habilitarse;
10. la participación puede terminar a solicitud del usuario o por incumplimiento grave de estas reglas.

## 9. Monetización durante G5

La preparación G5 no autoriza por sí sola monetización, RMT ni ventajas de combate/economía. Cualquier sistema de pago debe pasar revisión técnica, legal, privacidad, reembolso y antifraude antes de estar visible.

## 10. Cambios de política

Los cambios materiales durante la beta deben versionarse y comunicarse antes de aplicarse cuando sea posible. Cambios urgentes por seguridad pueden aplicarse primero y notificarse después con una explicación breve del motivo.

## 11. Condiciones para publicar estos textos

Antes de abrir la beta a usuarios externos se debe sustituir cualquier placeholder y confirmar:

- identidad/nombre del operador que aparecerá públicamente;
- país/jurisdicción aplicable;
- canal real de soporte/privacidad;
- proveedor de hosting y sus plazos de retención relevantes;
- si existen analíticas externas;
- si existirán pagos;
- edad mínima aplicable;
- procedimiento real de eliminación/exportación de datos.

Hasta completar esos datos, este archivo sirve como baseline técnico-operativo, no como aviso legal final para producción.
