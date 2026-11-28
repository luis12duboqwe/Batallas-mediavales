# QA adversarial independiente — comunidad y ciclo de mundos

## Alcance y estado

Trabajo anticipado para BM-0070–0074 y G16–G18; **no es certificación G7 ni declara G7 cerrado**. Esta rama se sincronizó con `main` hasta `e06cd1b1841f8e4618e5d4bb64393cb35c6053d0`.

El alcance de corrección incluye los servicios de alianza/diplomacia/comunidad, los routers de mensajes privados, alianzas y chat, y el módulo adversarial nuevo `tests/test_parallel_g7_adversarial_community.py`. No se modificaron otros servicios, pruebas existentes, workflows ni configuración.

## Hallazgos corregidos y comportamiento cubierto

| Grupo | Cambio y regresión |
| --- | --- |
| Diplomacia | Cancelar relaciones requiere el lock del mundo abierto. La cancelación en pausa devuelve HTTP 409 y conserva la relación. |
| Alianzas | Creación, invitaciones, aceptación, mensajes masivos y cambios de membresía/rango exigen mundo abierto. La creación y transferencia de liderazgo toman el lock de mundo antes de bloquear usuario/alianza/membresías y vuelven a validar el estado canónico. |
| WebSocket de chat | Cada mensaje toma el lock del mundo antes de los locks de participantes y revalida sesión/cuenta, mundo activo seleccionado, membresía, receptor y privacidad antes de escribir. Una pausa rechaza mensajes de sockets ya abiertos; el mismo socket puede enviar de nuevo tras reabrir el mundo. Mundos cerrados/archivados y receptores que dejan el mundo no reciben escrituras. Errores liberan/rollback la transacción antes de cualquier `await`. |
| Mensaje privado | Normalización ocurre antes de mutar. El estado premium se consulta sin crearlo; un envío inválido, rechazado por pausa o que pierde la carrera de pausa no genera filas premium. El límite de bandeja se aplica por mundo/destinatario/nivel premium, retirando los mensajes más antiguos necesarios incluso si una bandeja heredada ya excedía el límite. Evicción, mensaje y notificación se guardan en una única transacción. |
| Notificaciones | Los payloads se preparan antes del commit y la notificación realtime es best-effort posterior. Una falla de dispatch no convierte una entrega ya confirmada en una respuesta engañosa de error. |
| Invitaciones duplicadas | La restricción única existente, el lock de destinatario y el savepoint evitan duplicados; la colisión se traduce a HTTP 400 sin persistencia parcial. |

### Límites de política de mensajes grupales

Mensajes masivos siguen siendo comunicación de alianza: llegan a todos los miembros actuales, incluido el remitente. El bloqueo social está definido para interacción privada entre dos jugadores; por eso un bloqueo individual no oculta ni filtra el anuncio autorizado al grupo. Las pruebas verifican esta separación explícitamente. Se normalizan asunto/cuerpo, se respetan los límites de longitud existentes y se aplican los topes de bandeja base/premium. El prefijo `[ALLIANCE] ` cuenta dentro del límite de asunto persistido.

La lectura de historial privado existente permanece visible a sus participantes después de bloquearse; el bloqueo previene nuevos mensajes privados, no borra el historial. Esta es la semántica actual y se deja como decisión de producto, no se cambió por inferencia. Del mismo modo, logros/quests tras aceptar una invitación permanecen como efectos de una acción ya confirmada; este cambio no introduce gates nuevos sobre progreso posterior al commit.

## Evidencia PostgreSQL 15

Se usó PostgreSQL **15.20**. El módulo adversarial y suites sociales enfocadas en esta iteración: **43 passed, 0 skipped**. Todas las suites de concurrencia PostgreSQL más el módulo adversarial: **60 passed**.

La cobertura específica incluye:

- Carrera entre pausa y transferencia de liderazgo: una transferencia que espera al lock ve la pausa y devuelve HTTP 409 sin cambiar líder/rangos.
- La creación de alianza adquiere el lock de mundo antes del lock del usuario fundador, consistente con el orden de los envíos sociales y sin inversión de locks.
- Carrera entre pausa y mensaje privado: la solicitud que pierde el lock se rechaza y no crea filas de estado premium, mensajes ni notificaciones.
- Carrera entre pausa y WebSocket/mensajería existente, inbox lleno y duplicación de invitaciones.
- Dos envíos simultáneos a una bandeja llena conservan el límite y ambas entregas; entrega completa revierte mensaje y expulsión si falla el commit.
- Un socket existente no persiste chat durante pausa/cierre/archivo y vuelve a escribir después de reabrir el mundo.

## Pruebas ejecutadas

- Módulo adversarial más suites de chat, alianza y mensajes en SQLite: **37 passed, 6 skipped**; los skips requieren locks PostgreSQL.
- El mismo conjunto en PostgreSQL 15.20: **43 passed**.
- Suites de concurrencia PostgreSQL (`tests/test_*concurrency*.py`) más el módulo adversarial: **60 passed**.
- Suite backend completa en SQLite: **1573 passed, 49 skipped, 74 subtests passed**.
- Suite backend completa en PostgreSQL 15.20: **1618 passed, 2 skipped, 2 deselected, 74 subtests passed**. Se excluyeron dos casos cuyo contrato es específicamente SQLite: la CLI exige un archivo SQLite y el test de movimiento fuerza una violación de FK que SQLite tolera.
- Los gates browser no se ejecutaron.

No se declara G7 certificado/cerrado. El PR debe permanecer Draft hasta la validación y triage de mantenimiento.
