# BM-0040 — Evidencia de fuente única de balance

Estado: **CANDIDATO A CIERRE**  
Fase: 4 — Balance, contenido y retención  
Versión de balance: `2026.08.20-bm0040.4`

> Este documento cubre BM-0040. No declara G4 cerrado: la puerta G4 también exige validar la primera sesión, observabilidad de progreso/abandono y Definition of Done de las funciones visibles.

## Objetivo

Eliminar tablas y fórmulas contradictorias entre servidor, API, interfaz y ayuda sin introducir un rebalance arbitrario del Alpha aceptado en G2/G3.

La autoridad numérica del gameplay live es `batalla_medieval_backend/app/services/balance.py`. Los servicios pueden conservar alias de compatibilidad, pero no mantener otra tabla independiente.

## Superficies centralizadas

- Edificios: catálogo, costes, requisitos, crecimiento, tiempo base y reembolso de colas.
- Producción: tasas base, almacenamiento y recuperación de lealtad.
- Expansión: coste de fundación, lealtad inicial y edificios iniciales.
- Tutorial: recompensa de finalización.
- Unidades: entrenamiento, investigación, población, mantenimiento, velocidad, carga y estadísticas de combate.
- Combate: muralla, moral, suerte, umbral decisivo y conquista bárbara.
- Espionaje: fórmula base, anonimato al fallar y datos revelados.
- Mercado: edificio, capacidad comercial y velocidad de transporte.
- Eventos: modificadores base y plantillas.
- PvE Alpha: recursos/tropas/edificios iniciales de bárbaros y parámetros activos de su IA.

## Correcciones de deriva

1. El coste live de edificios escala con `1.20`, no con el antiguo `1.26` publicado por rutas legacy.
2. El entrenamiento no usa el antiguo multiplicador `1.18 ** nivel`; usa el tiempo del catálogo por cantidad y modificadores de mundo/evento.
3. La muralla canónica es `wall`; el nombre `Muralla de Guardia` solo se acepta como compatibilidad de datos legacy.
4. La UI ya no inventa producción `15/12/10` ni almacenamiento `5000` cuando falta estado: consume el snapshot versionado del servidor.
5. La wiki no anuncia edificios que el gameplay live no ofrece ni conquista PvP.
6. El evento `GLOBAL_TRIBUTE` ahora aplica realmente `loot_modifier` sobre la capacidad efectiva de carga, sin poder retirar más recursos que los disponibles.
7. La ayuda de espionaje coincide con el resolver live: un espionaje exitoso revela recursos, tropas y edificios; se retiró el umbral ficticio de cinco espías.
8. La cola de tropas ahora reserva `population_max` antes de cobrar y cuenta guarnición, tropas temporalmente fuera, retornos y colas pendientes.
9. El mantenimiento queda explícitamente en `0.0/h` en esta versión porque el recurso oro se incorpora en BM-0060; no se simula un cobro inexistente.
10. La IA bárbara recluta usando el mismo coste de `basic_infantry` que el jugador y respeta la capacidad real de almacén.
11. El seed canónico y la IA PvE consumen los mismos valores versionados en vez de mantener otra economía.
12. El simulador de prototipo no estaba ruteado y dependía de endpoints `/simulate/*` inexistentes; se retiraron la página, servicio y componentes exclusivos para no conservar una segunda fuente rota de tropas/reglas.

## Contrato para API/UI

`GET /economy/balance_preview` expone el snapshot del balance con `version` y las secciones de edificios, unidades, producción, expansión, tutorial, PvE Alpha, combate, espionaje, mercado y eventos.

Las rutas públicas de edificios/tropas comparten esa misma versión. El frontend usa el snapshot como fallback de reglas, evitando números de gameplay duplicados en JavaScript.

## Evidencia automatizada

- `tests/test_balance_single_source.py`
  - identidad entre servicios live y objetos canónicos;
  - equivalencia de wrappers legacy;
  - muralla real;
  - snapshot versionado;
  - API pública;
  - wiki derivada del balance.
- `tests/test_economy.py`
  - wrappers económicos contra reglas live.
- `tests/test_population_capacity.py`
  - overflow rechazado sin gasto;
  - población reservada durante movimientos/retornos/colas;
  - disponibilidad de unidades y mantenimiento visible.
- `tests/test_events.py`
  - tablas de eventos canónicas;
  - `loot_modifier` aplicado y acotado.
- `tests/test_seed.py`
  - seed PvE idempotente y enlazado al balance;
  - progreso bárbaro existente no se reinicia.
- `tests/test_barbarian_balance.py`
  - crecimiento respeta almacén;
  - reclutamiento descuenta exactamente el coste canónico.
- Contrato OpenAPI
  - `/economy/balance_preview` registrado.
- Frontend
  - no queda un simulador ruteado o un servicio `/simulate/*` huérfano.
- Gates existentes
  - Backend, PostgreSQL concurrency, Frontend, Browser E2E, dependency audit y Container images.

## Checkpoints CI

- Validation #188 sobre `773d472859f352c0ce121658c945f39c3cd64b8b`: todos los gates verdes después de incorporar la reserva de población.
- El cierre definitivo requiere que una Validation posterior a **este documento y todos los cambios finales** quede completamente verde en el mismo HEAD. El número exacto de esa corrida se registra en el PR #87 al pasar a Ready.

## Simulador

No existe un simulador live habilitado en el corte actual del producto. Los archivos de prototipo que apuntaban a endpoints inexistentes fueron retirados en BM-0040 para no mantener una implementación alternativa rota. Si el simulador vuelve a formar parte del producto, deberá consumir `balance.py`/el snapshot versionado y no podrá introducir tablas propias.

## Qué queda fuera de BM-0040

- Migración a madera/piedra/hierro/oro y mantenimiento económico real: BM-0060.
- Balance final de edificios/unidades: BM-0062/BM-0063.
- Combate final: BM-0064.
- Bárbaros y oasis finales: BM-0067.
- Cierre G4 completo: primera sesión sin bloqueos económicos, métricas de progreso/abandono sin PII y DoD/QA de funciones visibles.
