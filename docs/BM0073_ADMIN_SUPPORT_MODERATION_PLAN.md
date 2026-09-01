# BM-0073 — Administración, soporte y moderación

## Estado

Activo. Rama: `feature/BM-0073-admin-support-moderation`.  
Base: `main` en `8cc52e541b2903a0fe4abb8f57e2bcdf5ed952f0`.

## Objetivo

Cerrar la superficie operativa de administración, soporte y moderación para v1.0. Toda acción sensible debe requerir capacidad explícita, motivo, auditoría before/after y una ruta segura de reversión cuando sea técnicamente reversible.

## Auditoría inicial

La base actual ya dispone de:
- autenticación administrativa mediante `is_admin`;
- logs genéricos;
- congelación/descongelación de cuentas;
- métricas de onboarding;
- herramientas para recursos, edificios, tropas, coordenadas y creación de ciudad;
- controles de ciclo de vida de mundos;
- moderación comunitaria parcial por rangos de alianza.

Brechas detectadas:
1. casi todas las mutaciones admin carecen de motivo obligatorio;
2. los logs guardan principalmente el valor nuevo, no estado anterior y posterior;
3. no existe procedimiento genérico de reversión;
4. borrar usuario/ciudad es destructivo e irreversible;
5. `is_admin` no diferencia soporte, moderación y operaciones;
6. no existe un modelo de caso de soporte;
7. contenido moderado no dispone de ocultar/restaurar con trazabilidad;
8. varias operaciones sensibles no bloquean la fila objetivo antes de editarla.

## Roles y capacidades

Se añade un rol administrativo opcional y capacidades servidor-autoritativas.

- `support`: consultar casos, usuarios y auditoría necesaria; gestionar casos y congelación/descongelación de cuenta.
- `moderator`: capacidades de support + ocultar/restaurar contenido comunitario.
- `operator`: capacidades anteriores + correcciones de estado de juego (recursos, edificios, tropas, coordenadas, ciudad).
- `admin`: todas las capacidades, incluidos lifecycle y asignación de roles administrativos.

Compatibilidad: un usuario legacy con `is_admin=true` y sin rol explícito se trata como `admin`. Un usuario no admin nunca obtiene capacidades por el valor del rol aislado.

## Auditoría estructurada

Se extiende el registro administrativo existente para que las acciones sensibles almacenen:
- actor;
- acción;
- target_type / target_id;
- motivo obligatorio;
- estado `before`;
- estado `after`;
- si es reversible;
- estado de reversión;
- actor y fecha de reversión;
- referencia al caso de soporte cuando exista.

Los snapshots contienen únicamente datos operativos necesarios, nunca contraseñas, tokens ni secretos.

## Reversión

Endpoint autoritativo de reversión sobre una acción auditable:
- bloquea el registro y el target;
- exige capacidad equivalente a la acción original;
- solo acepta acciones marcadas reversibles;
- exige motivo de reversión;
- verifica compare-and-set: el estado actual debe seguir igual al `after` original;
- restaura `before`;
- es exactamente-una-vez;
- registra una nueva acción de reversión y marca la original como revertida.

Operaciones inicialmente reversibles:
- recursos;
- nivel de edificio;
- cantidades de tropas;
- coordenadas;
- freeze/unfreeze;
- ocultar/restaurar contenido.

## Operaciones destructivas

Los endpoints administrativos de borrado duro de usuario/ciudad dejan de formar parte de la superficie operativa ordinaria.

- Cuenta: soporte/moderación usa freeze; eliminación de cuenta pertenece a BM-0090 (privacidad/retención).
- Ciudad: una corrección operacional no borra ciudades; cualquier eliminación excepcional queda fuera de BM-0073 y requiere procedimiento de datos/retención explícito.

## Casos de soporte

Modelo mínimo:
- solicitante;
- mundo opcional;
- asunto y descripción;
- estado `open/in_progress/resolved/closed`;
- prioridad;
- asignado a operador opcional;
- resolución;
- timestamps.

Jugador:
- crear caso propio;
- listar/ver sus casos.

Administración:
- listar/filtrar casos;
- asignar;
- cambiar estado/prioridad;
- resolver/cerrar con motivo;
- las acciones administrativas pueden vincularse a un caso.

## Moderación de contenido

Contenido comunitario moderable se oculta, no se borra:
- chat persistente;
- posts de foro.

Metadatos:
- `is_hidden`;
- motivo;
- moderador;
- fecha.

Ocultar/restaurar exige capacidad de moderación, motivo y auditoría reversible. Las APIs públicas omiten contenido oculto; administración puede verlo para soporte/auditoría.

## Trabajo

1. Migración versionada de rol administrativo, auditoría estructurada, casos y flags de moderación.
2. Capability map y dependencias FastAPI reutilizables.
3. Servicio estructurado de acciones admin con snapshots y locks.
4. Migrar freeze y correcciones de ciudad al contrato reason/before/after.
5. Implementar reversión compare-and-set.
6. Retirar borrado duro de usuario/ciudad de la superficie admin.
7. Implementar casos de soporte jugador/admin.
8. Implementar ocultar/restaurar chat/foro.
9. Ajustar AdminPanel para motivo obligatorio, casos, auditoría y undo.
10. Añadir pruebas API/unitarias/PostgreSQL de permisos, reversión y carreras.
11. Añadir Browser E2E G17.
12. Validar upgrade/downgrade, Backend, Frontend, PostgreSQL, seguridad, G5, G2–G17 e imágenes.
13. Versionar evidencia y fusionar solo HEAD exacto verde sin hilos pendientes.

## Criterios de aceptación

- Ninguna acción sensible funciona sin capacidad adecuada.
- Ninguna acción sensible funciona sin motivo no vacío.
- Auditoría registra before/after sin secretos.
- Revertir dos veces no aplica dos veces.
- Revertir no pisa cambios posteriores.
- Freeze/unfreeze revoca sesiones cuando corresponde.
- Recursos/edificios/tropas/coordenadas se pueden restaurar exactamente.
- Borrado duro no está disponible desde la UI/API admin ordinaria.
- Casos de soporte están aislados por propietario para jugadores.
- Moderación oculta contenido sin destruirlo y permite restauración auditada.
- Soporte no obtiene capacidades de operator/admin.
- Todos los gates obligatorios pasan sobre el HEAD exacto.

## Gate BM-0073

BM-0073 se considera cerrado cuando administración, soporte y moderación operan mediante capacidades explícitas, motivo, auditoría estructurada y reversión probada, sin herramientas destructivas ordinarias.
