# G3 — Alpha multijugador

Estado: **EN VALIDACIÓN**

Este documento registra evidencia reproducible para la puerta G3 del Plan Maestro. No sustituye el plan canónico.

## Alcance de este PR

- BM-0030: permisos y aislamiento de movimientos multijugador.
- BM-0031: protección de novatos y prohibición de conquista PvP.
- BM-0032: mercado/transporte atómico y resistente a fallos.
- Base de aislamiento para BM-0033: acceso explícito por membresía a mapa, ranking y mercado.

## Invariantes

- Toda interacción jugable sucede dentro de un único `world_id`.
- Un usuario no puede leer mapa, ranking, mercado u oasis de un mundo que no ha unido.
- Ataque y espionaje PvP respetan la protección de atacante y defensor.
- PvE contra ciudades bárbaras (`owner_id = null`) sigue disponible durante protección.
- Ninguna ruta de conquista puede transferir una ciudad perteneciente a otro jugador.
- Un transporte descuenta recursos exactamente una vez.
- Aceptar una oferta consume la oferta, cobra al comprador y crea ambos transportes en una sola transacción.
- Un fallo al preparar cualquiera de los dos transportes revierte toda la aceptación.

## Evidencia automatizada añadida

- `tests/test_world_isolation.py`
- `tests/test_market_atomicity.py`
- `tests/test_pvp_protection_and_conquest.py`

## Pendiente antes de cerrar G3

- Matriz completa de ataque, espionaje, refuerzo, transporte y retorno entre dos jugadores.
- Pruebas PostgreSQL concurrentes específicas del mercado.
- Aislamiento y permisos mínimos de alianza/diplomacia.
- Simulación acordada equivalente a 24 horas sin duplicaciones ni recursos negativos.
- Validation completo en verde.
