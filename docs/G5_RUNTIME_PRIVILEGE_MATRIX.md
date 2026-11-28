# G5 — matriz de privilegios runtime (issue #218)

**Estado: inventario de trabajo, NO-GO; no es una política de grants ni una
certificación de mínimo privilegio.** Alcance: código de base `86adbd8` y
laboratorio inmutable de #219 `6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f`.
Las referencias a código sin otra revisión son relativas a esa base. El
laboratorio no está en esta base: sus referencias se enlazan al SHA exacto.
El inventario read-only de #215 observa vías privilegiadas; no demuestra que
una lista de privilegios de aplicación sea suficiente ni excluye escritores
externos continuamente ([inventario](G5_PRIVILEGED_INVENTORY.md#L3-L29)).
El checker y su prueba PG15 sintética se ejecutaron localmente, según la
evidencia comunicada; no se ha ejecutado aquí el laboratorio #219.

## Identidades, versiones y límites

| Contexto | Qué debe poder hacer | Qué no debe confundirse |
|---|---|---|
| Runtime histórico | Backend y worker de la imagen histórica `eafc5bbd5fdc9caad698db48cbb8ad80df942f0e` sobre `0019_privacy_active_unique`, según el laboratorio. | Su código y esquema son inmutables: no existen las tablas wonder de 0020. |
| Runtime candidato | Backend y worker candidatos sobre `0020_wonder_funding`, incluidas rutas de wonder y exportación. | No requiere DDL para migrar ni seed; compatibilidad con el histórico y todos los caminos sigue por verificar. |
| Mantenimiento | Migración Alembic, seed, backup/restore, inspección y cambios controlados de roles/fence, bajo identidad separada. | No se entrega al rol compartido backend/worker. El overlay de separación es opt-in y no provisiona ni certifica permisos ([diseño](G5_MIGRATION_ROLE_ISOLATION.md#L7-L26)). |

`0020` añade `worlds.wonder_rules_version` con default `legacy-v1` y crea
`wonder_funding` y `wonder_contributions`, índices, FKs, checks y unicidad;
el downgrade elimina esos objetos ([migración](../batalla_medieval_backend/alembic/versions/0020_wonder_funding_rules.py#L16-L72)).
DDL, versión Alembic y seed son mantenimiento, no inferir que el runtime
deba poder realizarlos. El mismo rol SQL sirve a HTTP y worker: las
capacidades admin se autorizan en aplicación, no por identidad SQL. Filtrar
por mundo y usuario sigue siendo obligatorio; los grants de tabla no aíslan
filas ni sustituyen controles de acceso.

## Superficie activa y lecturas que escriben

El inventario parte de `include_router`, no de todos los archivos del árbol:
`auth`, `account_data`, `achievement`, `city`, `building`, `troop`,
`movement`, `alliance`, `forum`, `market`, `hero`, `adventure`, `tutorial`,
`expansion`, `map`, `message`, `ranking`, `report`, `protection`, `premium`,
`chat`, `notification`, `event`, `season`, `quest`, `wiki`, `economy`,
`public_api`, `queue`, `world`, `support`, `admin`, `admin_bot`,
`admin_moderation`, `anticheat` ([registro](../batalla_medieval_backend/app/main.py#L66-L105)).
`conquest`, `icon`, `shop` y `theme` tienen archivos pero no se incluyen como
routers; no eliminar SELECT de datos heredados que usan exportación u otros
servicios por ese motivo. `quest/list` está registrado pero expone el tutorial
compatible, no el catálogo retirado ([quest](../batalla_medieval_backend/app/routers/quest.py#L13-L28)).
También existe Socket.IO alrededor de HTTP
([main](../batalla_medieval_backend/app/main.py#L107-L109)); el cierre de HTTP
por sí solo no demuestra el cierre de ese canal.

GET no equivale a transacción read-only:

* `/city/`, `/{id}` y `/{id}/status` recalculan producción; los dos primeros
  pueden registrar eventos de recursos ([city](../batalla_medieval_backend/app/routers/city.py#L41-L74),
  [detalle/status](../batalla_medieval_backend/app/routers/city.py#L78-L123),
  [producción](../batalla_medieval_backend/app/services/production.py#L184-L299)).
* `/queue/status` procesa **todas** las colas antes de filtrar la respuesta
  ([router](../batalla_medieval_backend/app/routers/queue.py#L14-L22));
  puede resolver combate y escribir fuera de la ciudad del solicitante.
* `/hero/` y `/hero/items` pueden crear héroe; `/adventure/` puede además
  crear aventuras ([hero router](../batalla_medieval_backend/app/routers/hero.py#L40-L47),
  [inventario](../batalla_medieval_backend/app/routers/hero.py#L88-L96),
  [hero](../batalla_medieval_backend/app/services/hero.py#L38-L79),
  [adventure](../batalla_medieval_backend/app/services/adventure.py#L34-L71)).
* `/achievement/list` crea progreso ausente bajo locks; `/premium/status`
  crea o actualiza estado; `/message/{id}` marca leído
  ([achievement](../batalla_medieval_backend/app/services/achievement.py#L26-L66),
  [premium](../batalla_medieval_backend/app/services/premium.py#L23-L59),
  [message](../batalla_medieval_backend/app/routers/message.py#L196-L210)).
* `/wiki/article/{id}` y `/wiki/search` pueden insertar o actualizar ayuda
  incorporada, una vez por proceso
  ([wiki](../batalla_medieval_backend/app/routers/wiki.py#L328-L365),
  [rutas](../batalla_medieval_backend/app/routers/wiki.py#L373-L391)).

Esto enumera efectos identificados, no garantiza que los demás GET sean
inmutables: dependencias, lazy loads y side effects deben comprobarse.

## Matriz por operación

**Clave:** S/I/U/D = SELECT/INSERT/UPDATE/DELETE; L = lock de fila; J =
join/subconsulta o carga relacional; `+` indica efecto condicional. Son
necesidades observadas o potenciales por operación, **no** lista completa de
SQL efectivo ni permisos concedidos. L requiere SELECT y al menos un
privilegio UPDATE de columna apropiado en PostgreSQL, incluso si no se
modifica la fila; los objetos bloqueados en joins importan. Las lecturas de
autenticación/membresía `users`, `player_world`, `worlds`, y las secuencias
de cada INSERT se suman a las indicadas. D por cascada ORM es condicional,
no una afirmación de que exista un endpoint de borrado de cuenta.

| Operación y alcance | Tablas y operaciones identificadas; locks/joins | Evidencia |
|---|---|---|
| Registro/login, unión al mundo y ciudad inicial | `users` S/I/U/L; `worlds` S/L; `player_world` S/I/L; `cities` S/I; `buildings`, `troops` I+; J de membresía y ciudad. | [auth](../batalla_medieval_backend/app/routers/auth.py#L120-L161), [unión](../batalla_medieval_backend/app/services/world_membership.py#L112-L165) |
| Lectura de ciudad/producción y mejora | `cities` S/U/L; `buildings`, `troops`, `heroes`, `research`, `building_queue`, `troop_queue`, `worlds` S; `building_queue` I/D; `achievement_progress`, `logs` I/U+ por eventos. | [producción](../batalla_medieval_backend/app/services/production.py#L101-L114), [mejora](../batalla_medieval_backend/app/services/building.py#L124-L162), [cancelación](../batalla_medieval_backend/app/services/building.py#L435-L460), [city](../batalla_medieval_backend/app/routers/city.py#L69-L72) |
| Investigación y entrenamiento | `research_queue`, `troop_queue` S/I/D/L; `research`, `troops` S/I/U; `cities` S/U/L; `buildings`, `worlds` S; progreso/notificaciones I/U+. | [research](../batalla_medieval_backend/app/services/research.py#L53-L74), [resolución](../batalla_medieval_backend/app/services/research.py#L128-L191), [troops](../batalla_medieval_backend/app/services/troops.py#L71-L87), [resolución](../batalla_medieval_backend/app/services/troops.py#L198-L261) |
| Worker, `/queue/status` | `building_queue`, `research_queue`, `troop_queue` S/D/L `SKIP LOCKED`; `buildings`, `research`, `troops` S/I/U; `cities` S/U/L; `movements` S/I/U/L; `notifications` I; `worlds`, `users` S; wonder, log y progreso según rama. Jobs usan advisory locks de sesión, conexión separada y ORM con commits propios. | [scheduler](../batalla_medieval_backend/app/scheduler.py#L26-L76), [colas](../batalla_medieval_backend/app/services/queue.py#L56-L106), [orquestación](../batalla_medieval_backend/app/services/queue.py#L129-L183) |
| Worker bárbaro/PvE | `worlds`, `cities`, `oases`, `troops`, `buildings` S; crecimiento puede U de mundo, oasis y tropas e I de tropas. No inferir cobertura del tick por la prueba de almacén. | [delegación](../batalla_medieval_backend/app/services/barbarian_ai.py#L8-L17), [PvE](../batalla_medieval_backend/app/services/pve.py#L499-L591) |
| Despacho, combate, espionaje, retorno y transporte | `cities`, `troops`, `heroes` S/U/L; `movements` S/I/U/L; `reports`, `spy_reports` I/S; `oases` S/U+; notificaciones, log y progreso I/U+. J/relaciones para tropas, héroes y ciudades; resolución selecciona movimientos vencidos con `SKIP LOCKED`. Conquista PvP no está permitida. | [reserva](../batalla_medieval_backend/app/services/movement.py#L81-L190), [combate](../batalla_medieval_backend/app/services/movement.py#L424-L542), [resolución](../batalla_medieval_backend/app/services/movement.py#L716-L769), [espionaje](../batalla_medieval_backend/app/services/espionage.py#L381-L402) |
| Mercado: oferta, aceptación, cancelación, NPC, envío | `market_offers` S/I/D/L; `cities` S/U/L; `movements` S/I; `alliance_members`, `alliances`, `users` S/J; anti-cheat `anti_cheat_rate_buckets`, `anti_cheat_flags`, `logs` S/I/U+ y posible progreso. Aceptación reserva recursos, crea transportes y elimina oferta; no basta con probar listado. | [filtros y joins](../batalla_medieval_backend/app/services/market.py#L349-L389), [aceptación](../batalla_medieval_backend/app/services/market.py#L410-L491), [cancelación/transporte](../batalla_medieval_backend/app/services/market.py#L514-L607), [rate limit](../batalla_medieval_backend/app/routers/market.py#L32-L47) |
| Alianza, invitación, cargos, chat, diplomacia | `alliances`, `alliance_members`, `alliance_invitations` S/I/U/D+ y L; `alliance_chat_messages`, `chat_messages`, `messages` S/I; `diplomacy` S/I/U/D/L; `users`, `worlds` S/L; joins por membresía y mundo. | [alianza](../batalla_medieval_backend/app/services/alliance.py#L142-L150), [invitación](../batalla_medieval_backend/app/services/alliance.py#L202-L256), [salida](../batalla_medieval_backend/app/services/alliance.py#L307-L307), [mensajes](../batalla_medieval_backend/app/services/alliance.py#L450-L560), [diplomacia](../batalla_medieval_backend/app/services/diplomacy.py#L21-L98) |
| Foro/chat/bloqueos | `forum_threads`, `forum_posts`, `chat_messages`, `user_blocks`, `messages` S/I/U/D+ según operación; `alliances`, `alliance_members`, `users`, `worlds` S/J; moderación puede U y escribir `logs`. | [foro](../batalla_medieval_backend/app/services/forum.py#L21-L76), [crear/moderar](../batalla_medieval_backend/app/services/forum.py#L112-L210), [chat](../batalla_medieval_backend/app/routers/chat.py#L280-L323), [moderación](../batalla_medieval_backend/app/services/moderation.py#L45-L70) |
| Héroe y equipamiento | `users` S/L; `player_world`, `cities` S; `heroes` S/I/U/L; `hero_items` S/U/L; `item_templates` S **y lock por JOIN actual**; revive también `cities` U/L. | [crear](../batalla_medieval_backend/app/services/hero.py#L38-L79), [revive](../batalla_medieval_backend/app/services/hero.py#L159-L205), [equipar](../batalla_medieval_backend/app/services/hero.py#L246-L288) |
| Aventuras | `heroes` S/U/L; `adventures` S/I/U/L; `cities` S/U/L y `item_templates` S; `hero_items` I si hay botín. | [generación/inicio](../batalla_medieval_backend/app/services/adventure.py#L34-L140), [botín/claim](../batalla_medieval_backend/app/services/adventure.py#L145-L208) |
| Wonder candidata, solo 0020 | `worlds` S; `cities` S/U/L, `buildings` S/L, `building_queue` S/I/D+; `alliance_members` S/L con J a `alliances`; `wonder_funding` S/I/U/L; `wonder_contributions` S/I. Idempotencia y límites de aportes se verifican bajo locks; cancelación/completado actualizan proyecto. | [reglas](../batalla_medieval_backend/app/services/wonder_funding.py#L33-L56), [aportar](../batalla_medieval_backend/app/services/wonder_funding.py#L128-L225), [cancelar/completar](../batalla_medieval_backend/app/services/wonder_funding.py#L233-L264) |
| Logros/tutorial/quests | `achievements` S; `achievement_progress` S/I/U/L; `player_world` S/L; `logs` I+; `users` S/U por tutorial. `quests`/`quest_progress` no son catálogo activo de quest, pero exportación lee progreso histórico. | [logros](../batalla_medieval_backend/app/services/achievement.py#L88-L103), [claim](../batalla_medieval_backend/app/services/achievement.py#L159-L197), [tutorial](../batalla_medieval_backend/app/routers/tutorial.py#L29-L36) |
| Premium, mensajes, notificaciones, wiki | `premium_status` S/I/U/L; `users` S/U/L; `map_bookmarks` S/I; `building_queue` D+; `messages` S/I/U/D; `notifications` S/I/U+; `wiki_articles` S/I/U. `themes`, `user_themes`, `shop_items`, `user_items` pueden ser leídos por relaciones/exportación, no asumir DML de routers no registrados. | [premium](../batalla_medieval_backend/app/services/premium.py#L23-L70), [acciones](../batalla_medieval_backend/app/services/premium.py#L129-L219), [wiki](../batalla_medieval_backend/app/routers/wiki.py#L328-L365), [export](../batalla_medieval_backend/app/services/account_export.py#L182-L226) |
| Soporte y solicitudes de privacidad | `support_cases` S/I/U/L; `users` S/L, `logs` I para cambio administrativo. Reapertura y nueva solicitud serializan sobre usuario; solicitud **no borra** datos. | [intake](../batalla_medieval_backend/app/routers/account_data.py#L99-L139), [actualización](../batalla_medieval_backend/app/services/support.py#L106-L123), [reapertura/auditoría](../batalla_medieval_backend/app/services/support.py#L149-L235) |
| Exportación de cuenta candidata | S de `users`, `player_world`, `cities`, `wonder_funding`, `wonder_contributions`, `buildings`, `troops`, las tres colas, `market_offers`, `heroes`, `hero_items`, `adventures`, `achievement_progress`, `quest_progress`, `notifications`, `messages`, `alliance_members`, `alliance_invitations`, `alliance_chat_messages`, `map_bookmarks`, `premium_status`, `user_themes`, `season_results`, `user_blocks`, `chat_messages`, `forum_threads`, `forum_posts`, `support_cases`, `user_items`. No convierte una solicitud de privacidad en borrado. Las dos tablas wonder son exclusivas de 0020: no proyectar esta dependencia al código histórico. | [endpoint](../batalla_medieval_backend/app/routers/account_data.py#L63-L76), [export 1](../batalla_medieval_backend/app/services/account_export.py#L44-L176), [export 2](../batalla_medieval_backend/app/services/account_export.py#L178-L226) |
| Admin, moderación, anti-cheat | `users`, `cities`, `buildings`, `troops` S/I/U/L; `support_cases` S; `logs` S/I/U y D condicional por cascada; `chat_messages`, `forum_posts` S/U/L; `anti_cheat_flags`, `anti_cheat_rate_buckets` S/I/U/L; `admin_bot_logs` S/I. La reversión y ciclo de mundo pueden tener más efectos. | [admin](../batalla_medieval_backend/app/services/admin.py#L65-L120), [recursos](../batalla_medieval_backend/app/services/admin.py#L172-L229), [bot](../batalla_medieval_backend/app/services/admin_bot.py#L17-L32), [anti-cheat](../batalla_medieval_backend/app/services/anticheat.py#L34-L121), [resolución](../batalla_medieval_backend/app/routers/anticheat.py#L47-L99) |
| Mundo, mapa, temporadas, ranking, eventos y API pública | `worlds`, `player_world`, `cities`, `oases`, `users`, `alliances`, `seasons`, `season_results`, `world_events` S/J; cambios de mundo/temporada/evento pueden I/U, y transición pausa/reanuda relojes en `cities`, `movements`, `adventures` U/L. Examinar también efectos de recompensas antes de reducir permisos. | [world](../batalla_medieval_backend/app/routers/world.py#L13-L75), [lifecycle](../batalla_medieval_backend/app/services/world_lifecycle.py#L51-L105), [season](../batalla_medieval_backend/app/routers/season.py#L58-L107), [map](../batalla_medieval_backend/app/routers/map.py#L28-L28), [API](../batalla_medieval_backend/app/routers/public_api.py#L180-L197) |

La tabla es un mapa de puntos de partida: `+` y las ramas indirectas requieren
trazado SQL real por versión, incluidos errores, reintentos, lazy loads,
autoflush y carreras. No deducir ausencia de D de una celda sin D.

## Cascadas, secuencias y privilegios negativos

El ORM define cascadas `delete-orphan` de usuario a héroes, ciudades, mensajes,
logs, progreso, membresías y otros; ciudad a edificios, tropas, colas, informes,
ofertas e investigación; héroe a objetos
([usuario](../batalla_medieval_backend/app/models/user.py#L50-L97),
[ciudad](../batalla_medieval_backend/app/models/city.py#L34-L58),
[héroe](../batalla_medieval_backend/app/models/hero.py#L38-L38)).
Son DELETE emitidos por ORM si se ejecuta la operación de borrado; una FK
`ON DELETE` del servidor tiene semántica distinta. Hay además `CASCADE` para
`user_blocks` y `messages.world_id`, y `SET NULL` para héroe en movimientos
([bloqueos](../batalla_medieval_backend/app/models/user_block.py#L22-L24),
[mensajes](../batalla_medieval_backend/app/models/message.py#L14-L14),
[movimientos](../batalla_medieval_backend/app/models/movement.py#L18-L18)).
No asumir que un borrado complejo puede completarse: FKs adicionales pueden
restringirlo; la política de privacidad exige revisión manual.

Cada INSERT con ID generado necesita verificar la secuencia real asociada y
sus ACL efectivas, incluidas las nuevas de 0020. El laboratorio concede
`USAGE, SELECT` a secuencias adjuntas, no concesiones generales por nombre
supuesto ([código #219](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L168-L182),
[grants](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L315-L323)).
Auditar también defaults, columnas, objetos no adjuntos, ownership, PUBLIC y
membresías; no dar UPDATE de secuencia ni CREATE de esquema por comodidad.

Negativos a comprobar con conexiones frescas y rol efectivo: sin propiedad
de objetos/base, superuser, CREATEDB, CREATEROLE, BYPASSRLS ni membresías
privilegiadas; sin CREATE de esquema/DDL, TRUNCATE, REFERENCES o TRIGGER
injustificados; sin acceso al ledger `alembic_version`, migración, seed,
catálogos sensibles o funciones de archivos, ALTER SYSTEM ni CONNECT a otras
bases. Incluir grants heredados y PUBLIC, ACL por columna, secuencias,
funciones, parámetros y default ACL. El acceso PG15 stock a `pg_settings`
requiere tratarse según su semántica, no confundirlo con grants adicionales
([#215](G5_PRIVILEGED_INVENTORY.md#L41-L49)). Ni ACL ni inventario read-only
controlan root, Docker, otros secretos, volúmenes o cambios concurrentes.

## Evidencia de #219 y vacíos

En el SHA citado el laboratorio declara una **cota amplia**: CRUD para
muchas tablas de juego; `wiki_articles` S/I/U; `item_templates` S/U; tablas
internas y wonder con operaciones específicas; excluye `alembic_version`
([política](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L118-L142)).
Su script contiene pruebas de registro/login, unión, mejora de almacén,
soporte y privacidad con controles de usuario/administrador
([HTTP](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L361-L446)),
equipar/sustituir/desequipar con objetos sintéticos insertados por mantenimiento
([héroe](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L451-L524)),
y worker real de ambas imágenes completando una cola de almacén con
persistencia SQL ([worker](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L575-L612)).
La candidata consulta conteos de las dos tablas wonder, no ejercita financiar
ni contribuir ([candidata](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L845-L858)).
Hay pruebas negativas selectivas de CREATE ROLE, ALTER SYSTEM, lectura de
archivo/catálogo, CONNECT y escritura del ledger
([denegaciones](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/ops/ci_g5_role_provisioning.py#L339-L358)).
Esto describe pruebas *implementadas*, no un resultado CI verificado para ese
SHA; la nota de ejecución local anterior identifica otra revisión y no prueba
restauración ([#219 doc](https://github.com/luis12duboqwe/Batallas-mediavales/blob/6d27de4e2fa9ae748ec5b83aa37eb739d4768b2f/docs/G5_ROLE_PROVISIONING.md#L70-L87)).

No hay evidencia allí de cobertura integral de combate/espionaje, mercados,
alianzas/diplomacia, aventuras y botín, contribuciones wonder, exportación,
moderación/resolución anti-cheat, todas las colas, PvE, cascadas ni
concurrencia. Tampoco una prueba de mínimo privilegio, restauración real o
exclusión continua de escritores. No extrapolar un SELECT de tabla a todas
sus escrituras ni una prueba SQLite a permisos PostgreSQL.

## Plan para `item_templates` y validación independiente

1. Preservar imagen histórica: `equip_item` hace `HeroItem JOIN ItemTemplate
   FOR UPDATE` sin `OF`; PostgreSQL puede bloquear ambas tablas
   ([código](../batalla_medieval_backend/app/services/hero.py#L274-L283)).
   La cota S/U de `item_templates` de #219 es compatibilidad experimental,
   no evidencia de que se actualice el catálogo ni permiso final deseable.
2. En un cambio **futuro** de candidata únicamente, evaluar
   `with_for_update(of=models.HeroItem)` para esa consulta; conservar el
   lock de héroe y verificar que no cambia la serialización de equipar,
   sustitución de slot y desequipar, incluyendo concurrencia. No modificar la
   imagen histórica. Repetir pruebas reales PG15 con S sin U en catálogo para
   candidata y con la política histórica necesaria durante rollback; verificar
   SQL emitido y denegación de UPDATE/INSERT/DELETE directo de catálogo.
   Considerar si mutación de plantillas por mantenimiento concurrente exige
   coordinación adicional.
3. En clones desechables independientes por revisión, con identidades runtime
   y mantenimiento separadas, capturar SQL y ACL efectivas; ejercitar cada
   fila de esta matriz con datos multi-mundo y casos positivos/negativos,
   bloqueos concurrentes, rollback, secuencias y cascadas. Reducir permisos
   uno por uno, repetir todo y comprobar que revocaciones prohibidas fallan.
   Probar 0019, transición y rollback, 0020 y worker separado; no usar datos
   reales. Comprobar explícitamente los caminos aún no ejercitados arriba.
4. Usar el checker acotado descrito abajo con reglas revisadas por separado
   para cada versión/identidad; contrastar contra pruebas positivas y
   negativas, registrar discrepancias y bloquear aprobación hasta resolverlas.
   Revisar por separado restauración independiente, fence y exclusividad
   externa; este documento no autoriza despliegue, cutover ni RPO=0.

## Checker de privilegios runtime

`ops.g5_runtime_privilege_audit` compara reglas explícitas de relaciones
`public` en una única observación PG15 read-only; **no provisiona ni ejecuta
operaciones de juego**. La identidad de mantenimiento de `Pg15FenceTarget`
debe ser superusuario, y el adaptador `ReadOnlySession.query(database, sql)`
debe ejecutar la consulta en una sesión nueva read-only, cerrar la sesión y
devolver su respuesta escalar como texto. Por ejemplo, con un adaptador
`reader` ya implementado y conectado a un fixture aislado:

```python
from ops.g5_pg15_writer_fence import Pg15FenceTarget
from ops.g5_runtime_privilege_audit import RelationRule, inspect_runtime_privileges

target = Pg15FenceTarget("game_ci", "game_app", "postgres")
rules = (
    RelationRule("hero_items", "table", frozenset({"SELECT", "UPDATE"}), frozenset({"DELETE"})),
    RelationRule("hero_items_id_seq", "sequence", frozenset({"USAGE"}), frozenset({"UPDATE"})),
)
observation = inspect_runtime_privileges(target, reader, rules)
assert not observation.blockers
```

Son reglas ilustrativas, **no** el manifiesto completo ni un conjunto de
grants recomendado. Los nombres, tipos, reglas contradictorias y respuestas
ambiguas se rechazan; `AuditError` no es una observación favorable.
`AuditObservation.blockers` identifica requisitos incumplidos. La
comprobación requiere privilegios positivos a nivel de tabla/secuencia;
las prohibiciones de SELECT/INSERT/UPDATE/REFERENCES en tablas incluyen
ACL de columnas. `has_*_privilege` contempla privilegios efectivos por
PUBLIC y herencia. El checker rechaza **toda membresía directa o transitiva**
del rol runtime, incluso con `NOINHERIT` y posibilidad de `SET ROLE`; también
rechaza propiedad directa o mediante membresía de cada relación declarada.
Comprueba además CREATE del esquema/base y TEMP de base y atributos peligrosos
del rol ([implementación](../ops/g5_runtime_privilege_audit.py#L65-L100)).
La prueba PG15 incluye membresía heredada y el caso `NOINHERIT` con
propiedad indirecta y `SET ROLE`
([test](../tests/test_g5_runtime_privilege_audit_pg15.py#L83-L102)).

Un resultado sin bloqueadores solo se refiere a las reglas y al instante
observado: no cubre el catálogo completo, RLS, triggers, grant options,
propiedad de objetos no declarados, privilegios por operación ni ejecución
de servicios. No reemplaza el inventario privilegiado de #215, pruebas
funcionales bajo el rol real ni control continuo de escritores. Obtener la
lista de reglas de esta matriz y contrastarla independientemente con el
esquema real; no asumir que declarar una tabla controla todas las demás.

Pruebas del checker, desde la raíz y con pytest y Docker disponibles:

```sh
PYTHONDONTWRITEBYTECODE=1 G5_PRIVILEGE_AUDIT_PG15=1 python -m pytest -q -o addopts='' tests/test_g5_runtime_privilege_audit.py tests/test_g5_runtime_privilege_audit_pg15.py
```

La prueba PG15 crea un contenedor sintético sin red y lo elimina al finalizar
([fixture](../tests/test_g5_runtime_privilege_audit_pg15.py#L19-L58)).
La prueba de lock contrasta SQL con `FOR UPDATE` y `FOR UPDATE OF h`;
otra prueba sintética de wonder usa `FOR UPDATE OF` sobre membresía,
funding/contribution, secuencias y verifica rollback al faltar USAGE
([héroe](../tests/test_g5_runtime_privilege_audit_pg15.py#L130-L140),
[wonder](../tests/test_g5_runtime_privilege_audit_pg15.py#L143-L189)).
**No prueban los servicios reales** ni la transición de imágenes. Se ha
comunicado un resultado anterior de 23 pruebas aprobadas; no se ha reproducido
en esta revisión documental ni se atribuye al código actualizado. No implica
cobertura integral ni certificación.
