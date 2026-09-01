# BM-0072 — Ciclo de vida de mundos

## Estado

Cerrado funcionalmente. Rama: `feature/BM-0072-world-lifecycle`.

Evidencia funcional vigente tras review: Validation #666 completamente verde sobre `630e0fa2c690d72e686e4049f97a25bda79f4240`. El HEAD documental final debe volver a pasar CI completo antes de fusionar.
Base: `main` en `422125bde8b7e62d115ea17d8c142f150acba11d`.

## Objetivo

Cerrar el ciclo de vida completo de un mundo: crear, abrir, pausar, cerrar y archivar sin perder datos, sin permitir mutaciones fuera de estado y con reglas públicas coherentes para jugadores y administración.

## Auditoría inicial

La base actual tiene únicamente `World.is_active` y `ended_at`. Ese booleano mezcla varias decisiones distintas:

1. si el mundo aparece como disponible;
2. si un jugador nuevo puede unirse;
3. si un miembro existente puede seleccionarlo;
4. si acciones de juego deben seguir ejecutándose;
5. si workers deben resolver colas/movimientos;
6. si el mundo está terminado pero consultable;
7. si debe conservarse como histórico archivado.

No existe máquina de estados explícita ni transición auditada. Tampoco hay una política final para movimientos/colas ya en curso al pausar/cerrar.

## Estados canónicos

- `draft`: creado por administración; no visible como mundo jugable ni admite joins.
- `open`: admite jugadores nuevos y juego normal.
- `paused`: no admite nuevas mutaciones de juego ni joins; conserva acceso de lectura a miembros existentes.
- `closed`: mundo finalizado; no admite mutaciones ni joins; rankings/reportes/histórico permanecen consultables.
- `archived`: histórico de solo lectura, fuera del selector activo ordinario; datos preservados.

## Transiciones permitidas

- `draft -> open`
- `open -> paused`
- `paused -> open`
- `open -> closed`
- `paused -> closed`
- `closed -> archived`

No se permite reabrir `closed` o `archived` en v1.0.

Toda transición sensible:
- exige administrador;
- lleva motivo no vacío;
- bloquea la fila del mundo;
- registra estado anterior/nuevo, actor y tiempo;
- es idempotente solo cuando la repetición expresa el mismo estado final permitido;
- nunca borra datos del mundo.

## Compatibilidad

- La migración convierte mundos legacy `is_active=true` a `open`.
- Mundos legacy `is_active=false` con `ended_at != null` pasan a `closed`.
- Mundos legacy `is_active=false` sin `ended_at` pasan a `paused`.
- `is_active` puede conservarse temporalmente como campo derivado/compatibilidad mientras routers legacy se migran, pero la autoridad final será `lifecycle_status`.

## Contrato de acceso

### Join
Solo `open` permite crear nueva membresía/ciudad inicial.

### Selección
- `open`: miembros y nuevos jugadores mediante join.
- `paused`: solo miembros existentes pueden seleccionar/leer.
- `closed`/`archived`: solo lectura histórica; no se activa como mundo jugable normal.

### Mutaciones
Las rutas que cambian estado del juego deben requerir mundo `open`. Esto incluye al menos:
- edificios/colas;
- tropas;
- movimientos/ataques/espionaje/refuerzos;
- mercado/transporte;
- héroe/equipamiento/aventuras;
- alianza/diplomacia/chat/foro cuando impliquen mutación del estado del mundo.

### Lecturas
Lecturas históricas permitidas para miembros según privacidad: reportes, rankings finales, ciudades/mapa cuando corresponda y ganador.

## Workers y pausa

`paused` congela el tiempo lógico del mundo para colas/movimientos/producción. No se deben resolver efectos mientras está pausado.

Para evitar “salto de tiempo” al reabrir, BM-0072 debe persistir el inicio de pausa y desplazar tiempos pendientes por la duración pausada o usar un reloj lógico equivalente probado.

`closed` finaliza definitivamente la ejecución de workers para ese mundo. No se crean efectos nuevos después del cierre.

## Cierre y ganador

Cerrar un mundo puede registrar `winner_id` o `winner_alliance_id` según regla administrativa explícita, pero no se inventa ganador automáticamente si no existe contrato de victoria vigente.

`ended_at` se fija una sola vez al entrar en `closed`.

## Trabajo

1. Añadir estado lifecycle y metadatos necesarios mediante migración versionada.
2. Crear servicio autoritativo de transiciones con locks, validación y auditoría.
3. Endurecer creación de mundo: nuevo mundo nace `draft` salvo decisión explícita soportada.
4. Separar join/selección/lectura histórica.
5. Crear guards reutilizables de `require_world_open` y acceso de lectura.
6. Integrar guards en mutaciones críticas.
7. Congelar workers y tiempos durante pausa; impedir resolución después de cierre.
8. Ajustar API/admin y selector UI para mostrar estado correcto.
9. Añadir pruebas unitarias/API/PostgreSQL de transición, concurrencia y preservación.
10. Añadir Browser E2E G16 para lifecycle.
11. Validar migración upgrade/downgrade, backend, frontend, seguridad, G5, PostgreSQL, Browser G2–G16 e imágenes.
12. Versionar evidencia final y fusionar únicamente el HEAD documental exacto verde.

## Criterios de aceptación

- Un mundo `draft` no admite join.
- Un mundo `open` funciona normalmente.
- Pausar impide mutaciones y no consume tiempos pendientes.
- Reabrir conserva exactamente el progreso y desplaza correctamente deadlines.
- Cerrar conserva datos, fija `ended_at` y bloquea toda mutación posterior.
- Archivar no borra ciudades, reportes, ranking, membresías ni ganador.
- Dos transiciones concurrentes incompatibles no pueden ambas confirmar.
- Jugadores sin membresía no obtienen datos privados de mundos pausados/cerrados.
- La UI no presenta `paused/closed/archived` como mundo jugable normal.
- Todos los gates obligatorios pasan sobre el HEAD exacto.

## Gate BM-0072

BM-0072 se considera terminado únicamente cuando el ciclo completo `draft -> open -> paused -> open -> closed -> archived` está probado, auditado, preserva datos y no permite mutaciones fuera de estado.
