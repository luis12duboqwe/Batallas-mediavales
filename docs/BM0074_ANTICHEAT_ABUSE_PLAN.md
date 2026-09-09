# BM-0074 — Anti-cheat y protección contra abuso

## Estado

Activo. Rama: `feature/BM-0074-anticheat-abuse-protection`.
Base certificada: `main` en `3401688390ed868f74e19a6ca8b60c437694b435` (Validation #753 verde).

## Objetivo

Reducir automatización, abuso de API y señales de fraude sin convertir heurísticas en sanciones automáticas. La detección genera evidencia; una sanción que afecte el acceso del jugador requiere una decisión administrativa explícita, motivo y auditoría.

## Auditoría inicial

La base ya dispone de flags anti-cheat, detección de velocidad/imposibilidad de movimientos, señales de multi-cuenta, patrones repetitivos, revisión administrativa y rate limits parciales en chat/API pública.

Brechas a cerrar:

1. `flag_violation()` congela automáticamente cuentas cuando la severidad es `critical`;
2. una heurística puede por tanto invalidar sesiones sin revisión humana;
3. el rate limit de acciones jugables depende de `last_action_at` y no modela ventanas por tipo de acción;
4. la revisión de flags acepta estados arbitrarios y el cliente controla `reviewed_by_admin`;
5. falta persistir fecha y motivo de revisión directamente en el flag;
6. los endpoints de consulta de flags necesitan filtros operativos y límites;
7. detecciones repetidas pueden generar ruido sin una política clara de deduplicación;
8. faltan pruebas de concurrencia y E2E de abuso/revisión/sanción humana.

## Contrato de seguridad

- Una detección nunca congela, elimina ni degrada automáticamente una cuenta.
- `critical` significa prioridad de revisión, no culpabilidad.
- Los flags nacen en estado `pending` y sin revisor.
- Estados de revisión permitidos: `resolved`, `confirmed`, `false_positive`, `monitoring`, `dismissed`.
- Resolver/reclasificar exige `admin.manage`, motivo no vacío, revisor y timestamp del servidor.
- Congelar/descongelar continúa únicamente por la superficie administrativa BM-0073, que revoca sesiones, exige motivo y deja auditoría before/after.
- Los rate limits autoritativos son persistentes y seguros con múltiples workers; al excederse devuelven 429 y generan evidencia, pero no sancionan.
- Las heurísticas de IP compartida son señales; no prueban multi-cuenta por sí solas.

## Trabajo

1. Separar detección de sanción automática.
2. Tipar estados de revisión y persistir `reviewed_at` + `resolution_reason`.
3. Añadir rate buckets persistentes por usuario/acción con serialización por fila.
4. Aplicar límites razonables a movimientos y mutaciones de mercado antes de la transacción de negocio.
5. Añadir filtros/paginación a la cola administrativa de flags.
6. Evitar inundación de flags repetidos dentro de una ventana corta.
7. Añadir regresiones API/unitarias/PostgreSQL.
8. Añadir Browser E2E G18 para detección → revisión humana → sanción manual.
9. Validar migración upgrade/downgrade, Backend, Frontend, PostgreSQL, seguridad, G5, G2–G18 e imágenes.

## Criterios de aceptación

- Una detección `critical` no cambia `is_frozen`, `freeze_reason` ni `auth_version`.
- Una cuenta solo se congela mediante una acción administrativa explícita y auditable.
- Un burst que exceda el límite recibe 429 de forma determinista y genera un flag sin congelar la cuenta.
- Dos workers no pueden saltarse el límite por carrera.
- Tipos de acción independientes no comparten accidentalmente el mismo bucket.
- El cliente no puede marcar un flag como revisado sin que el servidor registre revisor, fecha y motivo.
- Estados inválidos de resolución son rechazados.
- Señales de IP/patrones no producen sanciones automáticas.
- Todos los gates obligatorios pasan sobre el HEAD exacto antes del merge.
