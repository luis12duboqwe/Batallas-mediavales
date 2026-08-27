# BM-0071 — Evidencia de validación: ranking y medallas de honor

Fecha: 2026-08-26  
Rama: `feature/BM-0071-ranking-honor-medals`  
PR: #106  
HEAD funcional validado: `296a2c152a83c80937b5b0dc2bc5fa9950d8dca0`  
Validation: #591 (`33011430531`)

## Resultado

El corte funcional de BM-0071 quedó completamente verde antes del commit documental final.

- Frontend: ✅ lint + build.
- Backend: ✅ 263 passed, 28 skipped, 5 warnings; cobertura total 78%.
- Migraciones: ✅ `0014_achievement_progress_world_scope` upgrade, seed canónico idempotente y downgrade.
- PostgreSQL concurrency: ✅, incluida la carrera concurrente de progreso de medallas.
- Dependency and security audit: ✅.
- G5 operations recovery: ✅.
- Browser E2E: ✅ G2–G15.
- Container images: ✅ backend/frontend.

## Evidencia G15

El journey `batalla_medieval_frontend/e2e/g15-ranking-medals.mjs` pasó con:

`G15 BM-0071 ranking and honor medals browser journey passed`

G15 comprueba en navegador real:

1. ranking por mundo con `rank` autoritativo;
2. desempate determinista de jugadores;
3. UI de “Medallas de honor”;
4. ausencia de campos/recompensas legacy visibles;
5. claim persistente de la medalla;
6. recursos idénticos antes/después del claim;
7. población/capacidad idénticas antes/después del claim.

## Garantías de dominio

- Progreso de medallas aislado por `(user_id, world_id)`.
- Migración legacy conserva progreso cuando existe un mundo activo/membresía inequívoca y no copia progreso a múltiples mundos.
- `claim` es honorífico: no aplica `reward_type` ni `reward_value`.
- Productores de progreso de edificios, producción, tropas, combate y alianzas pasan `world_id` explícito.
- Combate `win_battles` usa el mundo del movimiento.
- `join_alliance` usa el mundo de la alianza.
- Pruebas multi-mundo negativas verifican que combate y alianza no contaminan otro servidor.
- Progreso concurrente se serializa sobre `PlayerWorld` y conserva incrementos sin duplicar filas.

## Ranking

- Jugadores: `points DESC`, `username` case-insensitive ASC, `user_id ASC`.
- Alianzas: `points DESC`, `name` case-insensitive ASC, `alliance_id ASC`.
- El contrato público no expone métricas globales no world-scoped como si pertenecieran al mundo consultado.
- La UI consume `rank` del backend en lugar de calcular posición con `index + 1`.

## Nota sobre HEAD final

Este documento y el cambio de estado del plan se versionan después del corte funcional verde. Por política del proyecto, el commit documental resultante también debe pasar Validation completo sobre su SHA exacto antes de quitar Draft/fusionar.
