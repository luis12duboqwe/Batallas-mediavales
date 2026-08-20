# G3 — Alpha multijugador

Estado: **EN VALIDACIÓN FINAL**

Este documento registra evidencia reproducible para la puerta G3 del Plan Maestro. No sustituye el plan canónico.

## Alcance completado en este PR

- **BM-0030 — Movimientos multijugador:** ataque, espionaje, refuerzo, transporte y retorno con permisos, aislamiento y resolución worker-only.
- **BM-0031 — Protección y conquista:** protección PvP para ataque/espionaje, PvE bárbaro permitido y conquista de ciudades de jugadores imposible.
- **BM-0032 — Mercado atómico:** reserva, aceptación, cancelación y transportes resistentes a concurrencia, rollback y doble gasto.
- **BM-0033 — Alianzas y diplomacia:** membresía por mundo, invitaciones, rangos, chat de alianza y relaciones diplomáticas aisladas por mundo.
- **BM-0034 — Mensajes, notificaciones y tiempo real:** mensajería solo entre jugadores con mundo compartido, privacidad de lectura/borrado, notificaciones privadas, chat realtime aislado y Socket.IO autenticado desde navegador.
- **Moderación G3:** banderas anti-cheat restringidas a admin, resolución auditada, freeze/unfreeze con revocación de sesiones, bitácora administrativa consultable y operaciones de ciudad protegidas por `world_id`.

## Invariantes verificadas

### Aislamiento por mundo

- Toda entidad y consulta jugable con `world_id` exige membresía durable en `PlayerWorld`.
- Mapa, ranking, mercado, oasis, movimientos, alianzas, diplomacia y chat no exponen datos de mundos no unidos.
- Ataque, espionaje, refuerzo y transporte no pueden apuntar a otro mundo.
- Mensajería privada REST exige que remitente y receptor compartan al menos un mundo.
- Chat `global` significa global **dentro del mundo activo**; nunca distribuye mensajes a sockets de otro mundo.
- Historial privado y chat privado exigen que ambos usuarios pertenezcan al mundo activo.

### Combate y protección

- Ataque y espionaje PvP respetan la protección tanto del atacante como del defensor.
- Un jugador protegido puede atacar bárbaros para continuar el tutorial/PvE.
- Un jugador no puede atacar ni espiar otra ciudad de su propiedad.
- Ninguna ruta de conquista puede transferir una ciudad perteneciente a otro jugador.
- La conquista de ciudades bárbaras usa el motor canónico de combate y bloquea atacante/objetivo en orden determinista.

### Movimientos y worker

- Ataque, espionaje, refuerzo y transporte reservan su payload una sola vez.
- La resolución corresponde al worker; las lecturas HTTP no procesan el mundo.
- Ataque y espionaje generan retornos server-side cuando corresponde.
- Retornos y transport returns se procesan exactamente una vez.

### Mercado

- Crear una oferta reserva recursos del vendedor una sola vez.
- Aceptar una oferta bloquea la oferta y ambas ciudades, cobra al comprador y crea los dos transportes dentro de una sola transacción.
- Un fallo al preparar cualquiera de los transportes revierte pago, consumo de oferta y movimientos.
- Dos compradores concurrentes no pueden consumir la misma oferta.
- Aceptar y cancelar simultáneamente no produce doble reembolso ni medio intercambio.
- Transportes directos A→B y B→A bloquean ambas ciudades en orden de ID para evitar deadlocks de claves foráneas en PostgreSQL.

### Alianzas y diplomacia

- Un jugador puede pertenecer a una alianza distinta en cada mundo, pero no a dos alianzas del mismo mundo.
- Invitaciones solo pueden dirigirse a jugadores que hayan unido el mismo mundo.
- La aceptación se serializa para impedir membresías dobles concurrentes.
- Listado de miembros, chat y acciones de rango requieren autenticación y permisos.
- No se pueden crear relaciones diplomáticas entre alianzas de mundos distintos.

### Mensajes, notificaciones y realtime

- Inbox, sent, lectura y borrado están limitados a los participantes del mensaje.
- Un tercero no puede leer, borrar ni marcar la notificación de otro usuario.
- La entrega de mensaje genera una notificación persistente para el receptor.
- Socket.IO valida firma, propósito y versión del JWT, verificación de correo y estado de congelamiento.
- El cliente obtiene la URL de Socket.IO del origen del backend y envía el JWT en `auth`.
- El Browser E2E exige observar una conexión Socket.IO autenticada y falla ante `console.error`, errores de página o HTTP 4xx/5xx.
- El entrypoint Browser/Docker es `app.main:socket_app`, por lo que HTTP y Socket.IO se prueban sobre el mismo runtime de producción.

### Ranking y moderación

- Ranking por mundo solo devuelve campos públicos (`id/username/puntos/world_id`); no expone correo, premium ni estado de moderación.
- Banderas anti-cheat solo son visibles/resolubles por administradores.
- Resolver una bandera deja una entrada en `Log` con administrador, objetivo y decisión.
- Freeze/unfreeze exige administrador, registra motivo y revoca sesiones existentes mediante `auth_version`.
- `/admin/logs` es admin-only y permite revisar la bitácora reciente.
- Crear/teletransportar ciudades desde admin respeta mundo, membresía del propietario y coordenadas únicas.

## Evidencia automatizada

- `tests/test_world_isolation.py`
- `tests/test_multiplayer_movement_matrix.py`
- `tests/test_multiplayer_worker_lifecycle.py`
- `tests/test_pvp_protection_and_conquest.py`
- `tests/test_market_atomicity.py`
- `tests/test_market_concurrency.py`
- `tests/test_alliance_world_isolation.py`
- `tests/test_g3_24h_simulation.py`
- `tests/test_g3_social_moderation.py`
- `tests/test_message_notification_lifecycle.py`
- `tests/test_admin_world_safety.py`
- `tests/test_chat_world_isolation.py`
- `tests/test_socket_auth.py`
- `batalla_medieval_frontend/e2e/g2-alpha.mjs` (sesión durable + conexión realtime autenticada)

## Simulación concurrente equivalente a 24 horas

La puerta PostgreSQL ejecuta 24 ciclos con dos jugadores, envíos simultáneos en ambos sentidos y dos workers compitiendo por procesar llegadas/retornos. La aceptación exige:

- 48 transportes originales y 48 retornos;
- todos completados exactamente una vez;
- cero movimientos fantasma pendientes;
- cero recursos negativos;
- cero excepciones de dispatch/worker, incluidos deadlocks.

## Puerta automática requerida para aprobación

El HEAD final del PR debe tener en verde, sin exclusiones manuales:

- Backend (compilación, migraciones, seed idempotente y suite completa).
- PostgreSQL concurrency (incluida la simulación G3 de 24 horas).
- Frontend (lint + build).
- Browser E2E (sesión durable + Socket.IO autenticado + cero errores aceptados).
- Dependency audit Python/Node.
- Container images backend/frontend.

Una vez que todas estas puertas queden verdes en el mismo HEAD, G3 puede marcarse **APROBADO** y el PR puede fusionarse a `main`.
