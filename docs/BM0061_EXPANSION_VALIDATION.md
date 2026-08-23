# BM-0061 — Ciudades, campamentos y expansión territorial

## Objetivo

BM-0061 implementa la decisión canónica PD-016: la expansión territorial usa **ciudades y campamentos**, y los puntos requeridos son generados por **Iglesia** y **Catedral**. El servidor es autoridad sobre puntos, recursos, coordenadas, tipo de asentamiento y promoción.

La expansión no cambia PD-005: **las ciudades de otros jugadores no son conquistables**. La conquista continúa limitada a ciudades bárbaras neutrales.

## Modelo canónico

### Puntos de expansión

Los puntos viven en `player_world.expansion_points`, por lo que pertenecen a la combinación jugador + mundo y no pueden transferirse entre mundos.

- Iglesia: +1 punto por nivel completado.
- Catedral: +3 puntos por nivel completado.
- Fundar campamento: 2 puntos.
- Fundar ciudad: 5 puntos.
- Promover campamento a ciudad: 3 puntos.

La suma `campamento + promoción` equivale exactamente a la fundación directa de una ciudad: 5 puntos.

Los puntos se acreditan dentro de la misma transacción que completa la cola de construcción. El servicio solo acredita cuando el nivel realmente avanza; reprocesar una cola ya consumida o una cola obsoleta para el mismo nivel no vuelve a generar puntos.

### Costes de recursos

- Ciudad: 800 madera + 800 piedra + 800 hierro.
- Campamento: 300 madera + 300 piedra + 300 hierro.
- Promoción: 500 madera + 500 piedra + 500 hierro.

Por tanto, `campamento + promoción == ciudad directa` también en recursos. No existe arbitraje por fundar barato y convertir gratis.

### Campamentos

Un campamento es un asentamiento logístico deliberadamente limitado:

- 25% de la producción base normal;
- población máxima inicial 50;
- empieza sin recursos propios, evitando crear recursos mediante fundaciones repetidas;
- edificios permitidos: Barracas, Muralla y Gran Depósito;
- no puede construir Iglesia, Catedral, Casa Central ni Maravilla del Mundo;
- no puede fundar otros asentamientos;
- puede recibir recursos mediante los sistemas normales del juego;
- puede promocionarse a ciudad pagando la diferencia exacta de puntos y recursos.

Al promoverse, pasa a `settlement_type=city`, obtiene al menos 100 de población y Casa Central nivel 1.

## Invariantes de seguridad económica

1. Toda expansión adicional exige una membresía `PlayerWorld` válida.
2. El origen de una fundación debe ser una ciudad completa del mismo jugador y mundo.
3. Puntos y recursos se bloquean/consumen dentro de la misma operación.
4. La fila `PlayerWorld` se bloquea para impedir doble gasto concurrente de puntos.
5. La ciudad origen se bloquea para impedir doble gasto concurrente de recursos.
6. El mundo debe estar activo.
7. Las coordenadas deben estar dentro del mapa, no pueden ser agua y no pueden contener ciudad/campamento u oasis.
8. `POST /city/` no crea ciudades; la capital inicial viene de `join_world` y la expansión posterior pasa por `/expansion/found`.
9. La ruta legacy `/conquest/found` no está expuesta en la aplicación. El wrapper interno `conquest.found_city` delega al servicio autoritativo de BM-0061.
10. Los campamentos no pueden convertirse en fábricas recursivas de puntos.

## Migración 0008

La migración añade:

- `cities.settlement_type`, con valor inicial `city` para todas las ciudades existentes;
- `player_world.expansion_points`, con valor inicial `0`.

Esto preserva el significado del progreso anterior: ninguna ciudad existente se convierte accidentalmente en campamento y ningún jugador recibe puntos retroactivos sin una regla explícita.

Prueba dedicada:

```bash
pytest -q tests/test_expansion_migration.py
```

La prueba verifica upgrade desde 0007, valores por defecto y downgrade a 0007.

## Pruebas funcionales

`tests/test_expansion_settlements.py` cubre:

- Iglesia + Catedral acreditan puntos una sola vez;
- un segundo worker pass no duplica puntos;
- una cola obsoleta para un nivel ya alcanzado tampoco duplica puntos;
- fundación de campamento consume recursos/puntos y no acuña recursos;
- producción reducida del campamento;
- edificios prohibidos en campamentos;
- promoción con coste diferencial exacto;
- equivalencia matemática entre ciudad directa y campamento + promoción;
- prohibición de expansión recursiva desde campamento;
- estado de expansión aislado por mundo.

`tests/test_expansion_api.py` cubre:

- cierre del endpoint gratuito `/city/`;
- status/fundación/promoción por API;
- rechazo de tipos de asentamiento desconocidos;
- ruta legacy de fundación no expuesta.

## Concurrencia PostgreSQL

`tests/test_expansion_concurrency.py` forma parte del job `PostgreSQL concurrency` y comprueba:

1. Dos solicitudes simultáneas intentan fundar campamentos cuando solo existen puntos para uno. Debe existir exactamente un ganador, un campamento, un solo cargo y ningún saldo negativo.
2. Dos ciudades del mismo jugador acreditan simultáneamente puntos de Iglesia. El bloqueo de `PlayerWorld` debe conservar ambas acreditaciones sin actualización perdida.

## Browser E2E

La jornada `batalla_medieval_frontend/e2e/g6-expansion.mjs` usa la interfaz real:

1. inicia sesión con el fixture de navegador;
2. entra a `/expansion` con 5 puntos;
3. promueve un campamento preparado y verifica que quedan 2 puntos;
4. consulta el mapa para encontrar una casilla libre/no acuática;
5. funda un nuevo campamento desde la interfaz;
6. verifica persistencia: 0 puntos, el campamento promovido es ciudad y el nuevo asentamiento es campamento.

El fixture se prepara con `scripts/prepare_g6_expansion_e2e.py` después del onboarding G2.

## Despliegue y rollback

### Antes del despliegue

1. detener escrituras/workers durante la migración;
2. crear y verificar snapshot de base en 0007;
3. ejecutar `alembic upgrade head`;
4. comprobar que todas las ciudades existentes tienen `settlement_type='city'`;
5. comprobar que membresías existentes tienen `expansion_points=0`;
6. ejecutar smoke tests y Validation antes de reabrir tráfico.

### Downgrade antes de usar BM-0061

Si todavía no se han generado puntos, creado campamentos ni realizado promociones, puede ejecutarse:

```bash
alembic -c batalla_medieval_backend/alembic.ini downgrade 0007
```

### Rollback después de tráfico de expansión

**No usar downgrade destructivo como recuperación después de tráfico BM-0061.** El esquema 0007 no puede representar:

- puntos de expansión acumulados;
- la diferencia entre ciudad y campamento.

Eliminar las columnas convertiría la información territorial en datos ambiguos. El procedimiento correcto es:

1. cerrar escrituras y workers;
2. conservar copia forense de la base BM-0061;
3. restaurar el snapshot verificado pre-0008;
4. desplegar el código compatible con 0007;
5. ejecutar smoke tests antes de reabrir tráfico.

## Criterio de cierre BM-0061

- [x] migración 0008 y downgrade definidos;
- [x] puntos por jugador+mundo;
- [x] Iglesia/Catedral generan puntos de forma idempotente;
- [x] ciudad/campamento y promoción usan costes autoritativos;
- [x] campamento limitado para evitar expansión recursiva/acuñación de recursos;
- [x] bypass de creación gratuita cerrado;
- [x] mapa y API exponen el tipo de asentamiento;
- [x] UI de expansión disponible;
- [x] pruebas funcionales, de migración y concurrencia añadidas;
- [x] jornada browser de fundación/promoción añadida;
- [x] procedimiento de rollback documentado;
- [ ] Validation completa verde sobre HEAD final congelado.

El PR no debe salir de Draft hasta completar el último punto.
