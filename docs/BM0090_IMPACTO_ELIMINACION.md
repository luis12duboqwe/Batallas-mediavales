# BM-0090 — Auditoría de dependencias para eliminación de cuenta

## Diagnóstico

**No es seguro borrar una fila de `users` con `db.delete(user)`.**
El esquema SQLAlchemy contiene referencias directas al usuario desde
mensajería, chat, foros, soporte, registros de administración, anticheat,
alianzas, resultados de mundos y progreso. Además, las ciudades y héroes
son referenciados de manera indirecta por movimientos, informes, aventuras
y otros jugadores.

Esta rama añade una **compuerta de regresión** que enumera todas las
claves foráneas directas a `users.id`. Una relación nueva o modificada
sin clasificación rompe el test y obliga a revisar el diseño de borrado.
Las clasificaciones son provisionales; no determinan por sí solas una
obligación legal de conservar o borrar datos.

## Mapa de riesgos

| Grupo | Impacto | Medida técnica a evaluar |
|---|---|---|
| Propiedad individual | progreso, héroes, objetos, inventario, colas, marcadores, preferencias | borrar o anonimizar tras cortar dependencias indirectas |
| Relaciones con otras cuentas | mensajes privados, chat, autores de foro, invitaciones, soporte | conservar derechos de otras personas y revisar tratamiento de contenido |
| Mundo compartido | ciudades con movimientos, ganadores, líderes de alianza, resultados | evitar borrar referencias históricas compartidas; reatribuir o desasociar |
| Evidencia y moderación | logs, anticheat, soporte y acciones de administradores | aplicar retención mínima justificada y borrar datos personales innecesarios |
| Copias de seguridad y telemetría | fuera de las relaciones ORM | inventariar períodos, controles de acceso y expiración de backups |

## Estrategia propuesta antes de habilitar cualquier operación irreversible

1. Validar identidad reciente y registrar solicitud con idempotencia. Revocar
   sesiones usando `auth_version`, e impedir nuevas operaciones y workers.
2. Definir retención autorizada de soporte, integridad de juego, fraude,
   compras si se habilitan y evidencia administrativa, con fundamento legal.
3. Crear plan de eliminación/anonimización transaccional verificable con
   orden de dependencias y rollback. Resolver primero vínculos cruzados
   `users → cities → movements/reports` y `users → heroes → adventures`.
4. Probar el proceso en DB clonada, con datos de dos jugadores, mensajes
   recibidos/enviados, ciudades de varios mundos, aliados, batallas,
   solicitudes repetidas, errores a mitad de transacción y concurrencia.
5. Ejecutar pruebas de PostgreSQL y recuperación de backup en staging,
   aplicar políticas de backup y preparar auditoría de cumplimiento.
6. Publicar un procedimiento en el perfil **solo** cuando toda la cadena
   de eliminación y retención haya sido aprobada y validada.

## Decisiones aún necesarias

Entidad responsable y jurisdicción; edad mínima; plazos de retención;
período para cancelar una solicitud; tratamiento de mensajes compartidos,
resultados públicos y evidencia de fraude; y canal para reclamaciones.

**No se habilita un botón de borrado**, borrado automático, anonimización
irreversible, ni ningún cambio de datos en producción en este bloque.
BM-0090 sigue abierto.
