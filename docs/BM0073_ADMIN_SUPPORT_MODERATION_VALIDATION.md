# BM-0073 — Evidencia de validación

Fecha: 2026-09-07  
Rama: `feature/BM-0073-admin-support-moderation`  
PR: #108  
HEAD funcional validado: `1e5e7ece6af41065bf5845d796c703ae2acbc80f`  
Validation funcional: #744  
Run ID: `34122458628`

## Gates

Todos los gates obligatorios terminaron en `success` sobre el HEAD funcional:

| Gate | Resultado |
| --- | --- |
| Frontend lint + build | success |
| Backend compile + migraciones + seed + tests | success |
| PostgreSQL concurrency | success |
| Dependency and security audit | success |
| G5 operations recovery | success |
| Browser E2E G2–G17 | success |
| Container images backend/frontend | success |

Backend: **282 passed, 32 skipped, 0 failed, 79% coverage**.

Browser E2E confirmó explícitamente:

`G17 BM-0073 administration, support and moderation browser journey passed`

El fixture fue preparado como:

`prepared-g17:world=1:admin=16:player=17:case=1:chat=1`

## Garantías BM-0073 verificadas

- Las operaciones administrativas sensibles usan capacidades explícitas por rol y motivo obligatorio.
- Un valor `admin_role` aislado nunca convierte en administrativo a un usuario que no sea admin; los admins legacy sin rol explícito conservan compatibilidad como `admin`.
- Las correcciones de recursos, edificios, tropas y coordenadas registran estado anterior/posterior y permiten reversión cuando corresponde.
- La reversión usa bloqueo, compare-and-set y semántica exactamente-una-vez; no pisa cambios posteriores.
- Congelar/descongelar cuenta invalida sesiones mediante `auth_version` y queda auditado.
- Los endpoints ordinarios de borrado duro de usuario y ciudad fueron retirados de la superficie administrativa.
- Los casos de soporte quedan aislados para el jugador propietario y pueden ser gestionados por capacidades de soporte.
- La moderación global de chat/foro oculta contenido sin destruirlo, lo excluye de lecturas públicas y permite restauración auditada.
- La revisión anticheat exige capacidad administrativa y motivo; la decisión queda auditada con before/after.
- El cierre de temporada ya no ejecuta borrado global de ciudades, alianzas, tropas, colas, mensajes ni auditoría; conserva el historial y opera de forma no destructiva.
- El AdminBot legacy fue convertido a **report-only**: no elimina usuarios, alianzas, mensajes ni logs y no congela jugadores automáticamente; solo produce diagnósticos agregados y una entrada auditable.
- G17 validó desde navegador que no existen controles de hard delete, que la moderación desaparece de la lectura pública, que `undo` restaura el contenido y que un caso de soporte puede resolverse con auditoría.
- El gate PostgreSQL ejecuta la regresión de concurrencia BM-0073 además de los gates de concurrencia acumulados del proyecto.

## Migraciones

El workflow validó `alembic upgrade head`, seed canónico repetible y `alembic downgrade base`. La migración nueva es `0016_admin_support_moderation` sobre `0015_world_lifecycle`.

## Alcance operativo

La certificación cubre las rutas montadas en `app.main`. `theme.py` contiene endurecimiento por capability pero su router no está montado actualmente; BM-0073 no abre una API nueva únicamente para ampliar alcance.

## Cierre

Este documento registra el candidato funcional. El commit documental posterior debe ejecutar nuevamente Validation y solo puede considerarse HEAD final de BM-0073 si todos los gates permanecen verdes sobre ese SHA exacto.
