# BM-0073 — Administración, soporte y moderación

## Estado

**Cerrado funcionalmente; pendiente únicamente de certificar el HEAD documental final y fusionar el PR #108.**  
Rama: `feature/BM-0073-admin-support-moderation`.  
Base: `main` en `8cc52e541b2903a0fe4abb8f57e2bcdf5ed952f0`.  
Candidato funcional validado: `1e5e7ece6af41065bf5845d796c703ae2acbc80f`.  
Validation funcional: **#744**, run `34122458628`, todos los gates verdes.  
Evidencia: `docs/BM0073_ADMIN_SUPPORT_MODERATION_VALIDATION.md`.

## Objetivo

Cerrar la superficie operativa de administración, soporte y moderación para v1.0. Toda acción sensible debe requerir capacidad explícita, motivo, auditoría before/after y una ruta segura de reversión cuando sea técnicamente reversible.

## Auditoría inicial

La base inicial ya disponía de:
- autenticación administrativa mediante `is_admin`;
- logs genéricos;
- congelación/descongelación de cuentas;
- métricas de onboarding;
- herramientas para recursos, edificios, tropas, coordenadas y creación de ciudad;
- controles de ciclo de vida de mundos;
- moderación comunitaria parcial por rangos de alianza.

Brechas detectadas y resueltas en BM-0073:
1. mutaciones admin sin motivo obligatorio;
2. logs que guardaban principalmente el valor nuevo, no estado anterior y posterior;
3. ausencia de procedimiento genérico de reversión;
4. borrado administrativo destructivo de usuario/ciudad;
5. `is_admin` sin separación de soporte, moderación y operaciones;
6. ausencia de modelo de caso de soporte;
7. contenido moderado sin ocultar/restaurar trazable;
8. operaciones sensibles sin bloqueo de fila;
9. superficies administrativas auxiliares que seguían dependiendo solo de `is_admin`;
10. AdminBot legacy con limpieza destructiva y sanción automática;
11. cierre de temporada legacy con borrado global de datos.

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

Operaciones reversibles cubiertas:
- recursos;
- nivel de edificio;
- cantidades de tropas;
- coordenadas;
- freeze/unfreeze;
- ocultar/restaurar contenido.

## Operaciones destructivas

Los endpoints administrativos de borrado duro de usuario/ciudad dejaron de formar parte de la superficie operativa ordinaria.

- Cuenta: soporte/moderación usa freeze; eliminación de cuenta pertenece a BM-0090 (privacidad/retención).
- Ciudad: una corrección operacional no borra ciudades; cualquier eliminación excepcional queda fuera de BM-0073 y requiere procedimiento de datos/retención explícito.
- AdminBot: funciona en modo `report_only`; no elimina usuarios, alianzas, mensajes ni evidencia de auditoría y no congela cuentas automáticamente.
- Temporadas: el cierre conserva el estado histórico y no ejecuta borrados globales de datos del juego.

## Casos de soporte

Modelo implementado:
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
- vincular acciones administrativas a un caso.

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

## Trabajo completado

1. Migración versionada de rol administrativo, auditoría estructurada, casos y flags de moderación.
2. Capability map y dependencias FastAPI reutilizables.
3. Servicio estructurado de acciones admin con snapshots y locks.
4. Freeze y correcciones de ciudad migrados al contrato reason/before/after.
5. Reversión compare-and-set implementada y probada.
6. Borrado duro de usuario/ciudad retirado de la superficie admin ordinaria.
7. Casos de soporte jugador/admin implementados.
8. Ocultar/restaurar chat/foro implementado.
9. AdminPanel ajustado para motivo obligatorio, casos, auditoría y undo.
10. Pruebas API/unitarias/PostgreSQL de permisos, reversión y carreras añadidas.
11. Browser E2E G17 añadido.
12. Superficies auxiliares alcanzables endurecidas por capabilities/reason/audit; AdminBot convertido a report-only y cierre de temporada hecho no destructivo.
13. Upgrade/downgrade, Backend, Frontend, PostgreSQL, seguridad, G5, G2–G17 e imágenes validados en #744.
14. Evidencia versionada; resta certificar mediante CI este HEAD documental exacto.

## Criterios de aceptación

- [x] Ninguna acción sensible cubierta funciona sin capacidad adecuada.
- [x] Ninguna acción sensible cubierta funciona sin motivo no vacío.
- [x] Auditoría registra before/after sin secretos.
- [x] Revertir dos veces no aplica dos veces.
- [x] Revertir no pisa cambios posteriores.
- [x] Freeze/unfreeze revoca sesiones cuando corresponde.
- [x] Recursos/edificios/tropas/coordenadas se pueden restaurar exactamente.
- [x] Borrado duro no está disponible desde la UI/API admin ordinaria.
- [x] Casos de soporte están aislados por propietario para jugadores.
- [x] Moderación oculta contenido sin destruirlo y permite restauración auditada.
- [x] Soporte no obtiene capacidades de operator/admin.
- [x] AdminBot no realiza mantenimiento destructivo ni sanciones automáticas.
- [x] Cierre de temporada no borra estado global.
- [x] Todos los gates obligatorios pasan sobre el candidato funcional.
- [ ] El HEAD documental final debe repetir todos los gates en verde antes de sacar el PR de Draft.

## Gate BM-0073

BM-0073 queda cerrado funcionalmente porque administración, soporte y moderación operan mediante capacidades explícitas, motivo, auditoría estructurada y reversión probada, sin herramientas destructivas ordinarias. El cierre de integración requiere ahora únicamente que el commit documental final conserve todos los gates verdes y que PR #108 sea fusionado a `main`.
