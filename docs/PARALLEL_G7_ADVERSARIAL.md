# QA adversarial independiente — comunidad y ciclo de mundos

## Alcance y estado

Trabajo anticipado para BM-0070–0074 y G16–G18; **no es certificación G7 ni declara G7 cerrado**. El árbol revisado tenía `b265eb02b754090b84f477d78bba61bdd7cfaf4d`, sobre la base `86adbd83dedc9a3e4c2d89b3adc247b72184d158`. La rama se sincronizó con `main` en `9ccc610a2974315a83223847457337439ed8a60d`; ese commit añadió archivos G5 ajenos a este cambio.

Los cambios de aplicación se limitan a `batalla_medieval_backend/app/services/diplomacy.py`, `batalla_medieval_backend/app/services/alliance.py` y `batalla_medieval_backend/app/routers/message.py`. Las regresiones están en el módulo nuevo `tests/test_parallel_g7_adversarial_community.py`.

## Hallazgos corregidos y evidencia

Las cuatro reproducciones P2 iniciales ahora pasan sus expectativas:

| Grupo | Corrección y prueba |
| --- | --- |
| Diplomacia | `cancel_relation()` adquiere el lock del mundo abierto y no elimina relaciones durante pausa. `test_diplomacy_cannot_be_cancelled_after_world_is_paused`. |
| Invitaciones | `invite_member()` exige mundo abierto bajo lock y serializa por el usuario invitado. `test_alliance_invitation_is_rejected_when_world_is_paused`. |
| Mensajes masivos | `send_mass_message()` verifica mundo abierto y persiste todos los mensajes y notificaciones en una sola transacción antes de emitir notificaciones realtime. `test_alliance_mass_message_is_rejected_when_world_is_paused`. |
| Bandeja privada | Asunto/contenido se normalizan antes de cualquier mutación. La expulsión del más antiguo, inserción nueva y notificación se comprometen juntas; el usuario receptor se bloquea para serializar envíos concurrentes. Hay casos de rollback, asunto/contenido en blanco y reemplazo válido que verifica aislamiento por mundo y destinatario. |

También se añadió el gate de mundo abierto a la creación de alianzas y se reordenó la aceptación de invitación para obtener el lock de mundo antes de bloquear la invitación/usuario. Las demás mutaciones en `alliance.py` ya conservaban el lock de mundo hasta su commit. Las lecturas históricas de mensajes siguen disponibles durante pausa; los recibos de lectura no mutan allí y borrar mensajes queda bloqueado.

La restricción única existente de invitación `(alliance_id, invited_user_id)` se protege con una fila de usuario serializada y un `SAVEPOINT` alrededor del `flush`. Un conflicto único se convierte a HTTP 400; no filtra un 500 ni deja persistencia parcial. Hay prueba de reinvitación a una invitación ya procesada y prueba de solicitudes duplicadas concurrentes.

### PostgreSQL 15

Se ejecutó el módulo completo contra PostgreSQL **15.20** en contenedor temporal:

- **11 passed, 0 skipped**.
- La carrera de invitaciones duplicadas terminó con un éxito, un conflicto HTTP 400 y una única fila.
- La prueba de pausa confirmó que una escritura que llega al lock después de la transición se rechaza con HTTP 409.
- Dos envíos simultáneos a una bandeja llena conservaron el límite de 50 y persistieron ambos envíos.
- La inyección de fallo durante la notificación revirtió tanto la expulsión como la inserción.

## Hallazgos hermanos fuera del scope autorizado

No se modificaron otros servicios o routers. La revisión de rutas identificó estas escrituras que parecen poder continuar en mundos pausados/cerrados; se notifican para triage separado:

1. **Transferencia de liderazgo:** `batalla_medieval_backend/app/routers/alliance.py`, `transfer_leadership()`, delega a `services/community.py::transfer_leadership()`. El router requiere membresía y capacidad, pero el servicio no exige el lock de mundo abierto antes de cambiar rangos y `leader_id`.
2. **Chat WebSocket:** `batalla_medieval_backend/app/routers/chat.py`, `websocket_chat()`, valida sesión/membresía, pero el loop persiste `ChatMessage` y hace `commit()` sin comprobar ni bloquear lifecycle del mundo antes de cada escritura.

Estos dos puntos se identificaron por inspección estática del flujo, no se presentan como reproducciones runtime de esta suite. Quedan fuera de los archivos permitidos para la corrección solicitada; requieren seguimiento en sus archivos responsables. Los handlers de escritura de foro revisados sí llaman `require_world_open_http()`.

## Pruebas ejecutadas

- Módulo adversarial en SQLite: **8 passed, 3 skipped**; los skips son únicamente pruebas que requieren PostgreSQL.
- Módulo adversarial en PostgreSQL 15.20: **11 passed**.
- Suite relevante SQLite (alianzas, diplomacia, foro, mensajería, chat, lifecycle y casos nuevos): **51 passed, 6 skipped**.
- Suites PostgreSQL de concurrencia social/lifecycle/anti-cheat más el módulo nuevo: **17 passed**.
- Suite backend completa: **1530 passed, 45 skipped, 74 subtests passed**, con `umask 022` y un `basetemp` privado. La primera ejecución en el sandbox heredó una umask `002` que hizo que las pruebas G5 operativas rechazaran directorios escribibles por grupo; con el entorno temporal corregido, el conjunto completo pasó.

Los gates browser no se ejecutaron. No se afirma que G7 esté certificado; los dos hallazgos hermanos arriba permanecen pendientes y el PR debe seguir Draft.
