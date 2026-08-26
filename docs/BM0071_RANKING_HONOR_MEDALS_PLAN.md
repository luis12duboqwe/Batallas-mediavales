# BM-0071 — Ranking y medallas de honor

## Estado

Cerrado funcionalmente. Rama: `feature/BM-0071-ranking-honor-medals`.

Evidencia previa al cierre documental: Validation #591 completamente verde sobre `296a2c152a83c80937b5b0dc2bc5fa9950d8dca0`. El HEAD documental final debe volver a pasar CI completo antes de fusionar.

## Objetivo

Cerrar el ranking por mundo y convertir el sistema visible de logros en medallas de honor compatibles con PD-015: reconocimiento sin bonos de recursos, combate, producción, velocidad o capacidad.

## Auditoría inicial

La base ya dispone de ranking de jugadores/alianzas y de achievements/progreso, pero no cumple todavía el contrato final de v1.0:

1. El ranking ordena solo por puntos totales y no expone posición ni una regla de desempate estable.
2. `attacker_points` y `defender_points` se leen directamente del usuario, aunque el ranking está aislado por `world_id`; esos datos deben ser world-scoped o no exponerse como puntuación competitiva por mundo.
3. El ranking recalcula jugador por jugador, generando consultas N+1 innecesarias para una superficie que crecerá con el mundo.
4. El ranking de alianzas debe definir desempate estable y datos públicos mínimos.
5. El sistema `Achievement` conserva campos `reward_type/reward_value` y el flujo `claim`, semántica heredada incompatible con medallas sin ventajas si se presenta como recompensa.
6. Debe quedar probado que obtener/reclamar una medalla no modifica recursos, tropas, capacidad, tiempos ni estadísticas de combate.
7. Falta un contrato E2E que compruebe ranking, desempate, privacidad y medallas desde UI/API.

## Decisiones de implementación

- El ranking será siempre por mundo y toda entrada incluirá `rank` explícito.
- Desempate de jugadores: `points DESC`, luego `username` case-insensitive ASC, luego `user_id ASC`.
- Desempate de alianzas: `points DESC`, luego `name` case-insensitive ASC, luego `alliance_id ASC`.
- No se expondrán datos globales como si fueran métricas por mundo. Cualquier estadística militar mostrada debe provenir de datos scoped al mundo; si el modelo actual no puede garantizarlo, se retira del contrato de ranking hasta tener fuente correcta.
- Las medallas son reconocimiento. `claim` puede marcar una medalla como reconocida/vista, pero nunca otorgará recursos ni ventaja jugable.
- Compatibilidad de datos: los campos legacy pueden mantenerse internamente si una migración destructiva no aporta valor, pero API/UI no deben prometer recompensas económicas o militares.
- Toda mutación y lectura mantiene aislamiento `world_id` y autorización existente.

## Trabajo

1. Endurecer schemas de ranking con posición y contrato público mínimo.
2. Refactorizar cálculo para agregación eficiente y desempate determinista.
3. Corregir/retirar estadísticas no world-scoped del ranking.
4. Definir catálogo canónico de medallas y semántica sin recompensa jugable.
5. Endurecer servicio de progreso/claim para impedir efectos económicos o militares.
6. Alinear API y UI: terminología “Medallas de honor”, progreso, estado y sin textos de recompensa.
7. Añadir pruebas de ranking, desempate, aislamiento, privacidad y medallas sin ventajas.
8. Añadir Browser E2E para ranking + medallas.
9. Ejecutar suite completa, PostgreSQL cuando aplique, frontend, seguridad, Browser E2E e imágenes.
10. Versionar evidencia exacta y fusionar solo con HEAD verde.

## Criterios de aceptación

- Dos jugadores empatados producen el mismo orden en ejecuciones repetidas y en SQLite/PostgreSQL.
- El mismo usuario puede tener estados distintos entre mundos sin contaminación del ranking.
- Ningún endpoint de ranking filtra correo, identidad privada, configuración de cuenta u otros datos sensibles.
- Las alianzas solo agregan miembros pertenecientes a la alianza del mundo consultado.
- Una medalla completada/claimed no cambia madera, piedra, hierro, oro, tropas, capacidad, producción, tiempos, atacante/defensor ni cualquier otra ventaja jugable.
- UI y API no presentan una medalla como premio económico/militar.
- Español visible final; cualquier traducción inglesa expuesta debe ser completa o retirarse según BM-0083.
- Tests unitarios/API/E2E y CI completo verdes.

## Gate BM-0071

BM-0071 se considera terminado únicamente cuando ranking y medallas cumplen el criterio maestro: cálculo, desempate y privacidad correctos; medallas sin ventajas, con evidencia reproducible ligada al HEAD exacto.