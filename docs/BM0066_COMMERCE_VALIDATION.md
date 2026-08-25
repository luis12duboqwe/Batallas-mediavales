# BM-0066 — Validación del comercio desde el inicio

## Estado

BM-0066 alcanzó un corte funcional completamente verde en **Validation #446** (`run_id=32803668838`) sobre el HEAD `1f4421a8de0a551a1ed1c1ee19a50965421cfa30`.

Ese corte valida conjuntamente las reglas autoritativas de mercado, transporte económico, capacidad de comerciantes, ofertas públicas y de alianza, intercambio NPC, conservación de recursos, límites de almacenamiento, resistencia a reintentos/concurrencia, UI y Browser G11, además de las imágenes Docker.

El cierre definitivo del PR exige una Validation completa verde adicional sobre el HEAD que contenga **este documento**. Solo ese SHA documental puede marcarse Ready y fusionarse.

Versiones y esquema:

- `COMMERCE_RULES_VERSION = "2026.08.24-bm0066-v1"`;
- `BALANCE_VERSION` permanece en la versión canónica de BM-0063 para no alterar identidades históricas de combate o espionaje;
- el schema head continúa en `0009`;
- BM-0066 no añade migración.

## Reglas económicas cerradas

El comercio queda disponible desde la primera ciudad sin exigir una Plaza Comercial inicial.

Reglas v1.0:

- capacidad comercial base: **500**;
- capacidad adicional: **1000 por nivel** de Plaza Comercial;
- cantidad mínima por lado de una oferta: **10**;
- máximo de ofertas activas por ciudad: **5**;
- ratio `solicitado / ofrecido` permitido: **0.25..4.0**;
- las ofertas pueden ser públicas o exclusivas de alianza;
- la autorización de alianza se vuelve a comprobar en servidor al aceptar, no depende de filtros de UI;
- intercambio NPC: retorno **80%**;
- intercambio NPC por operación: **10..250**;
- los cuatro recursos canónicos siguen siendo `wood`, `stone`, `iron` y `gold`.

La instantánea pública de balance expone el bloque `market` con estas reglas y su `rules_version`. La UI consume esa instantánea en vez de mantener una segunda tabla de números.

## Transporte autoritativo

Los transportes económicos solo pueden nacer en el servicio de mercado.

El camino genérico de movimientos rechaza `movement_type = "transport"`, cerrando el bypass que permitiría evitar capacidad, autorización o reserva económica.

Para un envío válido, el servidor:

1. comprueba mundo, propiedad/destino y que el destino sea una ciudad de jugador;
2. bloquea las ciudades involucradas en orden determinista;
3. recalcula la economía autoritativa de la ciudad de origen;
4. valida saldo y capacidad comercial disponible;
5. reserva los recursos dentro de la misma transacción que crea el transporte;
6. conserva ocupada la capacidad hasta el retorno real del comerciante.

## Entrega todo-o-devuelto

BM-0066 elimina la pérdida silenciosa por almacén lleno.

Al llegar un transporte:

- se bloquean origen y destino;
- el servidor comprueba si el destino puede almacenar **todo** el cargamento;
- si cabe completo, se acredita completo;
- si no cabe completo, no se acredita parcialmente ni se destruye nada;
- el cargamento completo viaja de regreso en `transport_return`;
- si al regresar tampoco cabe completo en el remitente, el retorno permanece `ongoing` y el comerciante continúa ocupado hasta poder devolverlo íntegramente.

Los informes de comercio registran si el envío fue entregado o rechazado y el motivo de retorno.

## Capacidad de comerciantes

La capacidad ocupada considera:

- ofertas activas reservadas;
- transportes salientes `ongoing`;
- retornos de comerciantes `transport_return` todavía `ongoing`.

Aceptar una oferta transforma reservas económicas en transportes sin liberar artificialmente capacidad entre ambos estados.

Cancelar una oferta devuelve su reserva una sola vez.

## Concurrencia y orden de locks

La primera implementación funcional reveló en PostgreSQL una clase de deadlock para transportes opuestos A→B y B→A: un worker podía retener A mientras otro retenía B y ambos intentar crear el retorno referenciando la ciudad contraria.

La corrección final bloquea **todas las ciudades tocadas por un transporte en orden ascendente de ID**. De esa forma los dos sentidos compiten siempre por el mismo primer lock y no forman un ciclo.

Validation #446 demuestra esta corrección mediante el gate PostgreSQL completo, incluido el escenario G3 de 24 horas con dos workers y transportes recíprocos.

También existe una regresión específica de dos transportes concurrentes hacia un mismo almacén casi lleno: como máximo el cargamento que cabe se entrega; el otro regresa íntegro. El almacén no puede sobrepasar su capacidad ni desaparecer recursos.

## UTC y telemetría antiabuso

Durante la preparación de G11 se detectó una diferencia entre `datetime` legacy sin zona y timestamps UTC conscientes dentro de telemetría anti-cheat.

BM-0066 normaliza esos timestamps antes de compararlos. La telemetría deja de generar excepciones por naive/aware datetime y continúa siendo un efecto posterior que no puede invalidar una transacción económica ya confirmada.

## UI del mercado

`MarketView` muestra y utiliza las reglas publicadas por el servidor:

- comercio disponible desde el inicio;
- capacidad base y crecimiento por Plaza Comercial;
- límites de ofertas y ratio;
- política todo-o-devuelto;
- ofertas solo alianza;
- retorno NPC del 80% y límites 10..250;
- preview real de conversión, por ejemplo 100 → 80.

La pantalla también inicializa su propio `cityStore` cuando se abre directamente en `/market`. Así no depende de haber visitado previamente el dashboard para disponer de la ciudad activa.

Se retiró la copia legacy que anunciaba un intercambio NPC ilimitado 1:1.

## Evidencia funcional — Validation #446

HEAD funcional: `1f4421a8de0a551a1ed1c1ee19a50965421cfa30`  
Run: `32803668838`

### Backend

**SUCCESS**

- `234` pruebas recolectadas;
- `214 passed`;
- `20 skipped` por corresponder a garantías ejecutadas en el gate PostgreSQL dedicado;
- `4 warnings`;
- cobertura total: `75%`;
- compilación Python verde;
- Alembic `base -> 0009` y downgrade verdes;
- seed canónico idempotente verde.

### PostgreSQL concurrency

**SUCCESS**

El gate de concurrencia pasó completamente, incluyendo:

- reservas económicas concurrentes;
- ofertas/aceptaciones concurrentes;
- movimientos exactly-once;
- dos entregas al mismo almacén casi lleno;
- simulación G3 de 24 horas con dos workers;
- transportes recíprocos A→B/B→A sin deadlock después del orden determinista de locks.

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

Pasaron G2, G4, G6, G7, G8, G9, G10 y **G11**.

Fixture G11:

`prepared-g11:7:1:17:18:rules=2026.08.24-bm0066-v1:outbound=5:return=6:capacity=500`

G11 comprobó desde API y navegador:

- versión exacta de reglas;
- comercio sin edificio Mercado inicial;
- capacidad 500 + 1000/nivel;
- límites de ofertas y ratio;
- oferta solo alianza visible;
- transporte rechazado conservado íntegramente;
- retorno de comerciante único;
- ausencia de la copia legacy 1:1;
- preview NPC 100→80;
- ejecución real de `POST /market/npc_trade` con respuesta 200 y mensaje UI coherente.

### Container images

**SUCCESS**

Las imágenes de producción de backend y frontend construyeron correctamente después de todos los gates anteriores.

## Rollout y rollback

BM-0066 no modifica el esquema de base de datos, por lo que el rollout no requiere migración ni ventana de transformación de datos.

Rollback:

- revertir el código de BM-0066 restaura el comportamiento anterior sin downgrade de esquema;
- no debe mezclarse un rollback parcial del worker con el servicio Market nuevo, porque ambos comparten la semántica de `transport_return` y capacidad ocupada;
- `COMMERCE_RULES_VERSION` permite identificar qué contrato produjo un estado o una evidencia de UI.

## Criterio de cierre

BM-0066 puede considerarse terminado cuando el HEAD que contiene este documento obtiene Validation completa verde, incluidos Backend, PostgreSQL concurrency, Frontend, seguridad, G5, Browser G2–G11 y Container images, sin reviews o hilos bloqueantes pendientes.