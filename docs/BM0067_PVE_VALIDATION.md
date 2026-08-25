# BM-0067 — Validación de bárbaros y oasis finales

## Estado

BM-0067 alcanzó un corte funcional completamente verde en **Validation #456** (`run_id=32869785762`) sobre el HEAD `73ed0422778559dd03edfbc5928056cdfdeeddc3`.

Ese corte valida conjuntamente generación, dificultad, perfiles de IA/PvE, recompensas, regeneración, versionado por mundo, idempotencia, concurrencia PostgreSQL, exposición API/UI, Browser G12 y construcción de imágenes Docker.

El cierre definitivo del PR exige una Validation completa verde adicional sobre el HEAD que contenga **este documento**. Solo ese SHA documental puede marcarse Ready y fusionarse.

Versiones y esquema:

- `PVE_RULES_VERSION = "2026.08.25-bm0067-v1"`;
- tick PvE: **300 segundos (5 minutos)**;
- población objetivo gestionada de bárbaros: **8**;
- población objetivo de oasis: **20**;
- el schema head continúa en `0009`;
- BM-0067 no añade migración.

## Reglas PvE versionadas por mundo

BM-0067 separa las reglas finales de bárbaros y oasis en un contrato PvE explícito y versionado.

La versión activa se fija en `World.special_rules`, junto con el manifiesto necesario para reconstruir y auditar el mundo. El servidor rehúsa tratar silenciosamente como compatibles unas reglas PvE distintas bajo la misma versión: un cambio material debe publicar una versión nueva.

La reconciliación es idempotente y no utiliza una segunda fuente de verdad para unidades o recursos: perfiles de tropas, recompensas y guardias se apoyan en los catálogos canónicos del juego.

## Generación y dificultad de bárbaros

Un mundo fresco recibe **8 asentamientos bárbaros gestionados** con el patrón de dificultad canónico:

`1, 1, 1, 2, 2, 2, 3, 3`

Cada tier define de forma versionada su perfil de tropas, edificios, recursos y dificultad. Los perfiles solo contienen unidades canónicas del catálogo vigente.

La reconciliación posterior:

- conserva el progreso de los asentamientos ya existentes;
- no resetea arbitrariamente recursos, tropas o edificios del mundo vivo;
- repone la población gestionada cuando un bárbaro es conquistado;
- conserva la ciudad conquistada como propiedad del jugador y crea un reemplazo neutral en una ubicación libre;
- no elimina asentamientos neutrales ajenos/importados solo para forzar un conteo global exacto.

Por eso el contrato de 8 es un **objetivo mínimo gestionado**, no una orden destructiva sobre cualquier ciudad neutral adicional que pueda coexistir en el mundo.

## Oasis finales

El mundo mantiene **20 oasis** con tiers 1–3. Cada oasis salvaje expone y respeta un perfil versionado de:

- guardias;
- dificultad;
- bonus porcentual;
- recompensa de conquista;
- regeneración.

Los guardias usan únicamente unidades canónicas. Los restos legacy como `rat` o `spider` no forman parte del contrato final.

La API del mapa y el detalle de oasis exponen `pve_tier` y `pve_rules_version`, permitiendo que cliente y pruebas comprueben exactamente qué reglas produjeron el estado mostrado.

## Regeneración e IA

La simulación PvE usa buckets deterministas de **5 minutos**.

En cada bucket elegible, el servidor procesa el mundo de forma idempotente y con exclusión de concurrencia:

- los oasis salvajes regeneran gradualmente sus guardias según su tier;
- la regeneración nunca excede el perfil objetivo del oasis;
- los oasis controlados por jugadores no regeneran guardias salvajes;
- la reconciliación de bárbaros mantiene la población gestionada sin borrar progreso válido;
- `barbarian_ai` delega en el ciclo PvE versionado en lugar de mantener una lógica paralela sin versión.

Dos workers que intentan procesar el mismo bucket no deben aplicar el tick dos veces.

## Recompensas de oasis y exactly-once

La recompensa de conquista de oasis es server-authoritative y depende del tier/versionado PvE.

Solo se acredita cuando la batalla realmente conquista el oasis. Dentro de la misma resolución transaccional:

1. se calcula la recompensa teórica del tier;
2. se respeta la capacidad de almacén de la ciudad atacante;
3. se acredita únicamente la parte que cabe;
4. el informe registra tanto `conquest_reward` como `credited_reward`;
5. la versión `PVE_RULES_VERSION` y el tier quedan incluidos en la evidencia de combate.

Un reintento del worker sobre el mismo movimiento no vuelve a pagar la recompensa ni vuelve a conquistar el oasis.

## API y UI

El mapa presenta la dificultad PvE sin duplicar reglas de balance en el frontend.

Para bárbaros y oasis, la UI muestra:

- tier/dificultad;
- versión de reglas PvE;
- información coherente con la respuesta autoritativa de API.

El cliente puede distinguir un objetivo tier 1, 2 o 3 y verificar que el contenido visible pertenece al mismo contrato que el servidor está ejecutando.

## Evidencia funcional — Validation #456

HEAD funcional: `73ed0422778559dd03edfbc5928056cdfdeeddc3`  
Run: `32869785762`

### Backend

**SUCCESS**

- `241` pruebas recolectadas;
- `220 passed`;
- `21 skipped` por corresponder a garantías ejecutadas en el gate PostgreSQL dedicado;
- `4 warnings`;
- cobertura total: `76%`;
- compilación Python verde;
- Alembic `base -> 0009` y downgrade verdes;
- seed canónico idempotente verde.

La suite cubre, entre otros contratos de BM-0067:

- patrón exacto de tiers de bárbaros en mundo fresco;
- 20 oasis y perfiles por tier;
- reconciliación idempotente sin resetear progreso;
- reposición después de conquista bárbara;
- regeneración gradual de oasis salvajes;
- ausencia de regeneración salvaje en oasis controlados;
- recompensa de conquista con límite de almacén;
- informe auditable y ausencia de doble recompensa en retry.

### PostgreSQL concurrency

**SUCCESS**

- `21 passed`;
- `3 warnings`.

El gate incluye `tests/test_pve_concurrency.py`: dos workers compiten por el mismo bucket PvE y exactamente uno realiza el procesamiento efectivo, evitando doble regeneración o doble reconciliación.

### Frontend

**SUCCESS**

- `npm ci`;
- lint;
- build de producción.

### Dependency and security audit

**SUCCESS**

- auditoría de dependencias Python;
- análisis estático de seguridad;
- auditoría npm al umbral configurado.

### G5 operations recovery

**SUCCESS**

Deployment, backup, restore y load probes continúan verdes.

### Browser E2E

**SUCCESS**

Pasaron G2, G4, G6, G7, G8, G9, G10, G11 y **G12**.

Fixture G12:

`prepared-g12:9:1:barbarian=7@80,75:tier=3:oasis=1@49,55:tier=1:rules=2026.08.25-bm0067-v1:active_barbarians=9`

El valor `active_barbarians=9` es esperado en la base compartida de Browser: G9 crea deliberadamente un objetivo neutral adicional para su combate auditable. BM-0067 preserva ese dato en lugar de borrarlo para forzar artificialmente un conteo global de 8.

G12 comprobó desde fixture, API y navegador:

- versión exacta `2026.08.25-bm0067-v1`;
- bárbaro canónico tier 3 en `(80,75)` con propietario nulo;
- perfil exacto de tropas y edificios de tier 3;
- existencia de 20 oasis gestionados;
- oasis salvaje con tier/version correctos;
- guardias formados solo por unidades canónicas y sin `rat`/`spider`;
- dificultad y versión visibles en la UI del mapa;
- coincidencia entre tier/version de UI y API.

Salida final del journey:

`G12 BM-0067 final PvE browser journey passed`

### Container images

**SUCCESS**

Las imágenes de producción de backend y frontend construyeron correctamente después de todos los gates anteriores.

## Rollout y rollback

BM-0067 no modifica el esquema de base de datos, por lo que el rollout no requiere migración ni ventana de transformación de datos.

El versionado por `World.special_rules` permite identificar qué contrato PvE corresponde a cada mundo y evita reinterpretar silenciosamente un mundo existente con reglas incompatibles.

Rollback:

- revertir BM-0067 no requiere downgrade de schema;
- no debe hacerse un rollback parcial que mezcle el servicio PvE nuevo con wrappers de combate, mapa o seed de otra versión, porque comparten tier, recompensa, regeneración y manifiesto de mundo;
- un cambio futuro de balance PvE debe publicar una versión nueva en vez de mutar `2026.08.25-bm0067-v1`.

## Criterio de cierre

BM-0067 puede considerarse terminado cuando el HEAD que contiene este documento obtiene Validation completa verde, incluidos Backend, PostgreSQL concurrency, Frontend, seguridad, G5, Browser G2–G12 y Container images, sin reviews o hilos bloqueantes pendientes.