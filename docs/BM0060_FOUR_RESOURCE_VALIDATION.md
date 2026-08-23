# BM-0060 — Validación de la economía de cuatro recursos

## Objetivo

BM-0060 migra el contrato vivo de recursos a **wood, stone, iron, gold**. `clay` deja de ser un recurso de runtime: el valor histórico de barro se conserva 1:1 como `stone`, y las ciudades existentes reciben `gold=500` durante la migración 0007.

La definición canónica es `app.services.balance.RESOURCE_FIELDS`. Las pruebas y servicios no deben mantener listas paralelas de recursos salvo que estén verificando explícitamente una migración histórica anterior a 0007.

## Invariantes de aceptación

1. `cities` expone `wood`, `stone`, `iron`, `gold` y no expone `clay` después de 0007.
2. El saldo histórico `clay` se conserva exactamente como `stone`.
3. Una ciudad existente recibe `gold=500` al subir a 0007.
4. Movimientos, colas de edificios/tropas, quests, reportes, ofertas y oasis transforman referencias persistidas `clay -> stone`.
5. Producción, capacidad, comercio, transporte, espionaje y botín recorren el catálogo canónico de cuatro recursos.
6. Un costo que todavía no incluya oro debe dejar el saldo de oro intacto. Los costos/upkeep finales de oro pertenecen a BM-0062/BM-0063.
7. El frontend no debe mostrar ni enviar `clay` en superficies activas.
8. No se permite introducir un alias runtime `clay` para conseguir compatibilidad: eso volvería a crear dos modelos económicos incompatibles.

## Evidencia automatizada

La prueba dedicada `tests/test_four_resource_migration.py` construye una base en 0006 con datos legacy y comprueba el ciclo:

- upgrade `0006 -> head`;
- `clay=432.5` se convierte en `stone=432.5`;
- `gold=500` aparece en la ciudad existente;
- oferta, oasis, movimiento, `building_queue`, `troop_queue`, quest y reporte se reescriben a `stone`;
- downgrade `head -> 0006` restaura `clay` y elimina `stone/gold` del esquema;
- los payloads históricos vuelven a `clay`.

Comando focal:

```bash
pytest -q tests/test_four_resource_migration.py
```

La Validation completa además debe ejecutar, sin excepciones:

```bash
pytest
```

junto con la matriz PostgreSQL de concurrencia definida en `.github/workflows/validation.yml`, lint/build frontend, browser E2E, auditoría de dependencias/seguridad, recuperación G5 y build de imágenes.

## Inventario de contratos legacy

En el checkpoint inicial de BM-0060, Validation encontró 33 fallas de backend concentradas en pruebas que todavía construían `City(clay=...)`, esperaban mapas de tres recursos o usaban `clay` en mercado/producción/unidades. Esos contratos se migraron para:

- usar `stone` en lugar de `clay`;
- incluir `gold` en saldos, producción, botín y fixtures donde corresponde;
- usar `balance.RESOURCE_FIELDS` en aserciones transversales;
- tratar claves ausentes en costos con `cost.get(resource, 0.0)`, porque BM-0060 hace vivo el oro sin adelantar los costos definitivos de BM-0062/BM-0063.

Commits de saneamiento del inventario legacy:

- `be0b5df` — contratos de ciudad, edificios, tutorial, primera sesión, mercado y bárbaros;
- `d131276` — movimientos, multiplayer worker, oasis, producción, unidades y scoping por mundo.

## Ensayo de rollback

### Antes de habilitar tráfico con 0007

1. Poner el despliegue en modo sin escrituras / detener workers que muten economía.
2. Crear y verificar un snapshot completo de la base 0006.
3. Ejecutar:

```bash
alembic -c batalla_medieval_backend/alembic.ini upgrade head
```

4. Verificar una muestra de ciudades: `stone == clay_previo` y `gold == 500` para las ciudades existentes.
5. Verificar que no queden identificadores `clay` en ofertas, oasis ni payloads persistidos activos.
6. Ejecutar smoke tests y solo entonces reabrir escrituras.

### Rollback pre-tráfico

Si 0007 se revierte **antes** de que jugadores o procesos hayan ganado/gastado oro, puede usarse:

```bash
alembic -c batalla_medieval_backend/alembic.ini downgrade 0006
```

Luego se valida que `clay` vuelva con el valor de `stone` y que los identificadores persistidos regresen a `clay`.

### Rollback después de tráfico con oro

**No usar downgrade de esquema como mecanismo de recuperación.** 0006 no tiene representación para `gold`; eliminar la columna perdería el historial económico generado después de 0007.

Procedimiento obligatorio:

1. cerrar escrituras y workers;
2. conservar una copia forense de la base 0007 problemática;
3. restaurar el snapshot pre-0007 verificado;
4. desplegar el código compatible con 0006;
5. ejecutar smoke tests antes de reabrir tráfico.

## Criterio para marcar BM-0060 Ready

- [x] migración 0007 preserva barro como piedra y añade oro;
- [x] referencias persistidas se reescriben en upgrade/downgrade;
- [x] runtime backend usa el catálogo canónico de cuatro recursos;
- [x] pruebas legacy detectadas por la primera Validation fueron migradas;
- [ ] todas las superficies frontend activas quedaron sin `clay`;
- [ ] pruebas negativas/concurrentes específicas de piedra/oro están completas;
- [x] procedimiento de rollback y requisito de snapshot están documentados;
- [ ] Validation completa está verde en un HEAD congelado.

No se debe sacar el PR de Draft hasta cerrar los tres ítems pendientes anteriores.
