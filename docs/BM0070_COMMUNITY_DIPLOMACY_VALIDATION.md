# BM-0070 — Comunidad y diplomacia completas — evidencia de validación

Fecha: 2026-08-26

## Corte validado

- PR: #105 — `feat(BM-0070): comunidad y diplomacia completas`
- Rama: `feature/BM-0070-community-diplomacy-final`
- Base validada: `653770133a313d4a6636f44d6746973949570e1b`
- HEAD funcional validado: `c5756f5544f9aa7a33b80ad051847ae9ba3ab334`
- GitHub Actions: Validation #554 (`32999615859`)
- Resultado funcional: todos los gates obligatorios verdes.

Este documento registra el cierre funcional de BM-0070. El commit que incorpora esta evidencia genera deliberadamente un HEAD documental distinto; ese nuevo HEAD debe pasar de nuevo la Validation completa antes de marcar el PR Ready o fusionarlo.

## Alcance validado

BM-0070 cierra el paquete social obligatorio de v1.0 sobre la implementación existente, sin mantener fuentes de verdad paralelas:

- alianzas y membresía aisladas por mundo;
- rangos Member / General / Leader expresados mediante capacidades de dominio;
- invitaciones y aceptación segura bajo concurrencia;
- promoción, degradación, expulsión y transferencia explícita de liderazgo;
- diplomacia con máquina de estados, autorización y par canónico entre alianzas;
- chat de alianza consolidado sobre `ChatMessage`, compartido por HTTP y WebSocket;
- mensajes privados persistentes acotados al mundo social activo;
- bloqueo social por mundo y revocación de nuevas interacciones privadas;
- foro de alianza con creación atómica, paginación, pin, cierre/reapertura y permisos de moderación;
- UI de administración de miembros usando el ID real de `AllianceMember`;
- Browser G14 multijugador como gate obligatorio;
- garantías de concurrencia BM-0070 ejecutadas específicamente sobre PostgreSQL.

## Correcciones realizadas durante el cierre

1. Se sustituyeron comparaciones sensibles basadas en números mágicos por capacidades nominales de comunidad.
2. La transferencia de liderazgo se convirtió en una operación atómica que bloquea alianza y membresías, actualiza `alliance.leader_id`, promueve al nuevo líder y normaliza cualquier rango Leader duplicado legado.
3. La aceptación de invitaciones bloquea al usuario para impedir que dos alianzas creen simultáneamente dos membresías en el mismo mundo.
4. Diplomacia usa orden estable de locks y un par canónico para impedir duplicados `(A,B)` / `(B,A)` y deadlocks por orden inverso.
5. El chat HTTP de alianza dejó de persistir en una tabla/historial paralelo y usa la misma fuente `ChatMessage` que WebSocket.
6. Se añadieron límites, normalización, filtro y rate limit al chat, con comprobación de membresía en cada acceso.
7. Se implementó bloqueo social por mundo mediante `UserBlock` y migración Alembic `0012_community_privacy`.
8. Los mensajes persistentes se aislaron por `world_id` mediante migración `0013_message_world_scope`; una sesión legacy con un único mundo unido puede resolverse sin ambigüedad, pero varios mundos exigen selección explícita.
9. Los mensajes masivos de alianza quedaron ligados al `world_id` de la alianza y con límites explícitos de asunto/contenido.
10. Se reparó una firma legacy obsoleta del servicio de notificaciones descubierta al probar mensajes masivos, manteniendo compatibilidad y un tipo de notificación seguro por defecto.
11. `GET /alliance/{id}/members` expone ahora el ID real de membresía, evitando asumir incorrectamente que `user_id == membership_id`.
12. La UI conecta ascenso, descenso, expulsión y transferencia de liderazgo a los endpoints autoritativos, ocultando acciones que el rango actual no puede ejecutar.
13. El foro crea hilo + primer post como una sola operación de dominio, bloquea respuestas contra un hilo cerrado y ofrece moderación reversible.
14. Se añadió G14 para comprobar el flujo multijugador completo visible y las revocaciones inmediatas tras cambios de membresía.

## Evidencia de gates — Validation #554

| Gate | Resultado | Evidencia relevante |
| --- | --- | --- |
| Backend | ✅ | Compilación, cadena Alembic upgrade/seed idempotente/downgrade y `pytest`: **256 passed, 27 skipped**, 283 recolectados. |
| PostgreSQL concurrency | ✅ | Suite de concurrencia completa incluyendo `tests/test_community_concurrency.py`. |
| Frontend | ✅ | `npm ci`, lint y build. |
| Browser E2E | ✅ | Fixtures y journeys aceptados G2, G4, G6–G14; G14 completó el paquete social. |
| Dependency and security audit | ✅ | `pip-audit`, Bandit y `npm audit --audit-level=high`. |
| G5 operations recovery | ✅ | Verificación de deployment, backup, restore y load probes. |
| Container images | ✅ | Build de imágenes backend y frontend. |

## Concurrencia BM-0070 verificada en PostgreSQL

El gate PostgreSQL no se considera evidencia indirecta: ejecuta pruebas específicas del paquete social.

- **Invitaciones competidoras:** dos alianzas distintas intentan aceptar simultáneamente sus respectivas invitaciones para el mismo jugador. Solo una operación puede crear la membresía del jugador en ese mundo; la otra queda rechazada y no aparecen dos membresías.
- **Diplomacia inversa:** dos alianzas solicitan simultáneamente A→B y B→A. El lock ordering y el par canónico producen una sola relación pendiente, sin duplicado inverso.

Las mismas pruebas aparecen como `skipped` en el Backend SQLite porque su garantía requiere los locks reales de PostgreSQL; se ejecutan y pasan en el gate PostgreSQL dedicado.

## Browser G14 — aceptación multijugador

El journey `g14-community.mjs` usa tres actores deterministas —líder, miembro y líder rival— y valida, entre otros, estos comportamientos:

1. un Member no puede iniciar diplomacia;
2. el líder publica en el chat HTTP de alianza y el mensaje aparece en el historial canónico `ChatMessage`;
3. se crea un hilo de foro y un rango autorizado lo fija y lo cierra desde UI;
4. un hilo cerrado deja de ofrecer respuesta;
5. la transferencia de liderazgo se ejecuta desde UI usando el `membership_id` real;
6. se verifican los nuevos rangos y el `alliance.leader_id` canónico;
7. el nuevo líder solicita una alianza diplomática y el rival la acepta;
8. un bloqueo por mundo impide un nuevo mensaje privado persistente;
9. el nuevo líder expulsa al antiguo líder;
10. el expulsado pierde inmediatamente acceso al chat y al foro de la alianza.

## Migraciones y compatibilidad

La Validation #554 recorrió exitosamente sobre SQLite la cadena completa:

- `upgrade` desde base hasta `0012_community_privacy` y `0013_message_world_scope`;
- seed canónico ejecutado dos veces para comprobar idempotencia;
- `downgrade base` completo.

La concurrencia crítica se validó adicionalmente en PostgreSQL, donde los locks usados por BM-0070 tienen semántica real.

## Estado de cierre

El HEAD funcional `c5756f5544f9aa7a33b80ad051847ae9ba3ab334` queda aceptado por Validation #554 con todos los gates verdes.

El siguiente y último requisito de cierre es validar nuevamente, de punta a punta, el HEAD documental que contiene este archivo. Solo si ese HEAD exacto conserva Backend, PostgreSQL concurrency, Frontend, Browser E2E G2–G14, seguridad, G5 e imágenes verdes podrá el PR #105 pasar de Draft a Ready y ser candidato de merge.
