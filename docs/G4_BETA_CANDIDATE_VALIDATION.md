# G4 — Validación de candidato a beta

| Campo | Valor |
|---|---|
| Puerta | G4 — Candidato a beta |
| Estado | CANDIDATO A APROBACIÓN FINAL |
| Plan canónico | `docs/PLAN_MAESTRO_DESARROLLO.md` v2.0 |
| Balance canónico | `2026.08.20-bm0040.4` |
| PR de cierre | #88 |
| Checkpoint funcional | Validation #243 |
| HEAD del checkpoint | `aabe26db336cabfaec1466b8124529313b406ae3` |

## 1. Alcance

Esta evidencia cierra los criterios de salida de la Fase 4 sobre el corte visible del MVP. No habilita por anticipado héroes, aventuras, tienda, temas, temporadas, API pública, pagos ni otras funciones que el Plan Maestro mantiene pospuestas para fases posteriores.

La aprobación definitiva de G4 exige una Validation completa y verde sobre el HEAD que contiene este documento. El número de esa ejecución final se registra en el PR #88 para no crear un ciclo infinito de commits de evidencia.

## 2. Criterio G4-1 — Sin fórmulas contradictorias entre API, UI y documentación

**Resultado: CUMPLIDO.**

La fuente única de balance ya fue cerrada por BM-0040 y está documentada en `docs/BM0040_BALANCE_VALIDATION.md`. El frontend consume el snapshot versionado del servidor para edificios, unidades, costes, producción, almacenamiento, tiempos y objetivos válidos de catapulta.

Durante el cierre G4 se eliminaron además derivas visibles que todavía podían contradecir el contrato canónico:

- se retiraron textos de producción que atribuían recursos a edificios inexistentes;
- `Ladrillo` se normalizó a `Barro` para el corte actual de tres recursos;
- se eliminó el fallback local de capacidad de almacén;
- edificios y tropas dejaron de depender de tablas locales duplicadas para sus nombres/datos de balance;
- el envío de refuerzos usa `reinforce`, no el valor legacy `support`;
- espionaje envía el `spy_count` exigido por el backend;
- objetivos de catapulta provienen del balance del servidor;
- mercado dejó de anunciar oro antes de la migración prevista por el plan;
- el selector de temas se retiró de la superficie visible mientras esa función siga pospuesta.

## 3. Criterio G4-2 — Primera sesión clara y sin bloqueos económicos

**Resultado: CUMPLIDO.**

`tests/test_g4_first_session.py` reproduce una primera sesión contra el seed canónico sin inyectar recursos, tropas, edificios ni progreso administrativo:

1. el jugador entra al mundo y recibe la economía inicial normal `500/500/500`;
2. paga un Cuartel nivel 1 con costes canónicos;
3. paga y entrena una infantería básica;
4. ataca una ciudad bárbara creada por el seed real;
5. el flujo tolera una derrota total sin supervivientes ni botín;
6. el tutorial reconoce que, en ese caso, no debe existir una marcha de retorno;
7. el tutorial completa el primer ciclo y concede su recompensa una sola vez;
8. ningún recurso queda negativo.

El servicio de tutorial conserva la espera normal cuando sí existen supervivientes o botín que deben retornar. La corrección no oculta movimientos pendientes reales.

## 4. Criterio G4-3 — Progreso y abandono observables sin datos personales

**Resultado: CUMPLIDO.**

Se añadió el endpoint administrativo `GET /admin/metrics/onboarding` y su servicio asociado. La salida es agregada y permite observar avance, actividad e inactividad del onboarding sin exponer usernames, emails, direcciones IP ni identificadores individuales.

Evidencia automatizada:

- `tests/test_onboarding_metrics.py`;
- contrato OpenAPI/API actualizado;
- acceso restringido a administración.

## 5. Criterio G4-4 — Toda función visible cumple Definition of Done

**Resultado: CUMPLIDO PARA EL CORTE VISIBLE DEL MVP.**

La superficie visible validada incluye:

- ciudad;
- edificios;
- academia/investigación;
- tropas;
- mapa;
- movimientos;
- informes;
- mercado;
- ranking;
- alianza;
- mensajes;
- perfil.

### Correcciones de Definition of Done realizadas

- navegación móvil real para funciones que antes solo eran alcanzables desde escritorio;
- foco y activación por teclado en navegación y controles críticos;
- etiquetas asociadas a inputs/selects y botones con semántica correcta;
- tutorial informativo que no bloquea clics/taps sobre la interfaz;
- refresco autoritativo después de construir, entrenar, cancelar, enviar movimientos y operar mercado;
- mercado ya no puede mostrar un fallo local después de que el servidor haya ejecutado con éxito la operación;
- pestañas del mercado convertidas a controles accesibles;
- movimientos clasificados por entrada/salida según ciudades realmente poseídas;
- transporte y retornos visibles;
- tarjetas de movimiento adaptadas al contrato API actual (`movement_type`, `arrival_time`, `origin_city_id`, `target_city_id`/`target_oasis_id`);
- idioma del perfil sincronizado realmente con `i18next` y persistente tras recarga.

## 6. QA de móvil, teclado, latencia y traducción

`batalla_medieval_frontend/e2e/g4-ux.mjs` forma parte del gate Browser E2E y ejecuta Chromium con:

- viewport `390x844`;
- contexto móvil/táctil;
- navegación mediante teclado;
- `250 ms` de retraso artificial en cada llamada HTTP a la API;
- detección de `console.error`, `pageerror` y cualquier respuesta HTTP `>= 400`;
- comprobación de overflow horizontal;
- recorrido de todas las rutas visibles del MVP;
- cambio English → Español, persistencia tras reload y restauración Español → English.

El smoke G2 sigue ejecutándose en el mismo job y conserva la comprobación de sesión durable y Socket.IO autenticado.

## 7. Checkpoint reproducible previo al documento

Validation **#243** sobre HEAD `aabe26db336cabfaec1466b8124529313b406ae3` quedó completamente verde:

| Gate | Resultado |
|---|---|
| Backend | PASS — suite completa; 150 passed, 13 skipped en SQLite y locks cubiertos en gate PostgreSQL |
| PostgreSQL concurrency | PASS |
| Frontend lint + build | PASS |
| Dependency audit | PASS |
| Browser E2E G2 + G4 | PASS |
| Container image backend | PASS |
| Container image frontend | PASS |

Los skips de la suite SQLite corresponden a garantías que requieren bloqueos PostgreSQL y se ejecutan en el gate dedicado de concurrencia.

## 8. Condición de aprobación final

G4 se considera **APROBADO** cuando el PR #88 cumpla simultáneamente:

1. este documento esté presente en el HEAD;
2. Backend, PostgreSQL concurrency, Frontend, Dependency audit, Browser E2E y Container images estén verdes en una sola Validation de ese HEAD;
3. el PR permanezca mergeable y sin hilos de revisión pendientes;
4. el merge se realice con el SHA exacto validado.

Después del merge, `main` debe volver a pasar Validation antes de iniciar la Fase 5.
