# BM-0072 — Evidencia de validación: ciclo de vida de mundos

Fecha: 2026-08-27  
Rama: `feature/BM-0072-world-lifecycle`  
PR: #107  
HEAD funcional validado: `41e7fd66d9c5f3fc387db9f83a6809db46b5a6a7`  
Validation: #657 / run `33097455698`

## Resultado

El corte funcional de BM-0072 quedó completamente verde antes del cierre documental.

- Frontend: ✅ lint + build.
- Backend: ✅ 270 passed, 30 skipped, 5 warnings; cobertura total 78%.
- Migraciones: ✅ `0015_world_lifecycle` upgrade, seed canónico idempotente, autogenerate check y downgrade.
- PostgreSQL concurrency: ✅, incluidas transiciones compare-and-set y barrera de pausa frente a workers en curso.
- Dependency and security audit: ✅.
- G5 operations recovery: ✅.
- Browser E2E: ✅ G2–G16.
- Container images: ✅ backend/frontend.

## Evidencia G16

El journey `batalla_medieval_frontend/e2e/g16-world-lifecycle.mjs` pasó con:

`G16 BM-0072 world lifecycle browser journey passed`

G16 comprueba con dos sesiones de navegador:

1. administración recorre `draft -> open -> paused -> open -> closed -> archived`;
2. un jugador solo puede unirse cuando el mundo está `open`;
3. un mundo pausado deja de aparecer como jugable;
4. reabrir reutiliza la misma membresía y ciudad inicial;
5. cerrar fija `ended_at`;
6. archivar conserva `ended_at`;
7. la ciudad del jugador continúa disponible como lectura histórica;
8. `closed` y `archived` rechazan nuevos join/select.

## Garantías de dominio

- `lifecycle_status` define los estados `draft/open/paused/closed/archived`.
- Las transiciones válidas están cerradas y auditadas con actor, motivo, estado anterior/nuevo y timestamp.
- `expected_status` implementa compare-and-set: dos transiciones concurrentes desde el mismo estado no pueden confirmar ambas.
- Durante compatibilidad legacy, desacuerdo entre `lifecycle_status` e `is_active` falla cerrado para juego.
- Nuevos mundos nacen `draft` salvo apertura explícita.
- Join, selección jugable y expansión requieren mundo `open`.
- Edificios, tropas, investigación, movimientos, mercado, héroe, aventuras y claim honorífico quedan bloqueados fuera de `open`.
- Alianzas, chat, diplomacia, foro y mensajes privados son de solo lectura histórica fuera de `open`.
- Lecturas históricas no generan progreso/quest side-effects.
- El catálogo público no expone mundos `draft`; administración dispone de catálogo completo.
- `/worlds/active` nunca anuncia un mundo pausado/cerrado/archivado como `current_world_id` jugable.

## Pausa y relojes

- Workers de edificios, investigación, tropas y movimientos ignoran mundos no `open`.
- Producción pasiva no avanza durante `paused`.
- Aventuras no progresan durante `paused`.
- Al reabrir, deadlines pendientes y `last_production` se desplazan por la duración exacta de la pausa.
- La transición a `paused` toma locks de filas con relojes activos; si un worker ya posee una fila, la pausa espera a que la libere antes de confirmar.
- La prueba PostgreSQL dedicada demuestra esa barrera.

## Preservación y cierre

- `closed` fija `ended_at` una sola vez.
- `archived` no borra ciudades, membresías, rankings/reportes ni ganador.
- No existe transición de reapertura desde `closed` o `archived` en v1.0.
- La migración legacy asigna `open` a mundos activos, `closed` a inactivos ya finalizados y `paused` a inactivos no finalizados.

## Nota sobre HEAD final

Este documento y el cambio de estado del plan se versionan después del corte funcional verde. Por política del proyecto, el commit documental resultante también debe pasar Validation completo sobre su SHA exacto antes de quitar Draft/fusionar.
