# BM-0075 — Tutorial y ayuda final

## Objetivo

Cumplir PD-015: el tutorial server-authoritative es el único sistema obligatorio de misiones y la ayuda visible deriva reglas y números del balance vigente.

## Contrato

- `app.services.tutorial` es la única autoridad de progreso del tutorial.
- El catálogo legacy de quests no crea progreso ni entrega recompensas nuevas.
- `/quest/list` permanece temporalmente por compatibilidad, devuelve catálogo vacío y toma `tutorial_completed` del tutorial canónico.
- `/quest/claim/*` responde `410 Gone`; filas históricas se conservan para no introducir una migración destructiva innecesaria.
- La Wiki/Ayuda existente se expone desde la navegación principal y sigue construyendo artículos desde `services.balance` y servicios server-authoritative.
- Un E2E móvil valida que Ayuda sea navegable y muestre la versión de balance.

## Validación requerida

- regresiones backend para no crear quests/progreso ni otorgar recompensas legacy;
- artículo de economía verificado contra `BALANCE_VERSION` y fórmulas live;
- lint/build frontend;
- Browser E2E G19;
- suite completa, seguridad, concurrencia e imágenes antes de merge.
