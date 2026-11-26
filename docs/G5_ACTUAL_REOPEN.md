# G5 — reapertura real: implementación incompleta

**NO-GO.** No hay ensayo ejecutable de reapertura ni autorización para
staging o producción. `python -m ops.ci_g5_actual_reopen` termina con código
2 sin modificar servicios; no se ha integrado en workflows.

El módulo contiene únicamente controles preparatorios: validación de
identidad y parámetros originales PG15, captura de la configuración Docker
inspeccionada y de la política completa (incluyendo `MaximumRetryCount`),
comparación con el contenedor cerrado (estado `created` o `exited`, sin
ejecución, pausa ni reinicio) y comprobación del recibo exacto COMMITTED.
No consulta SQL ni Docker, no conserva esos datos de manera
durable y no restaura nada. El control de recibo requiere que quien lo llame
ya tenga el bloqueo exclusivo `hold_phase` y la lease de activación. No
debe tratarse como autorización independiente.

## Evidencia de esta sesión CI

- Los 22 tests focalizados de `tests/test_g5_actual_reopen_guards.py`
  pasaron dentro de `medievol-g5-backend:ci` (pytest 9.1.1). Son tests
  unitarios, no una prueba de reapertura.
- El ensayo existente `python -m ops.ci_g5_actual_migration` falló al
  ejecutar la primera migración por fallo de resolución Docker del alias
  `database` en la red interna. Una prueba independiente de
  `socket.getaddrinfo("database", 5432)` también falló.
- Una repetición diagnóstica **en memoria**, sin editar el ensayo existente,
  añadió `--add-host` con la IP del contenedor PostgreSQL inspeccionado.
  Esa repetición del ensayo existente pasó: Alembic 0019→0020, seed y
  bloqueo del rol app. No inició el backend ni el worker, no abrió Nginx
  y no probó la reapertura.
- Ambas ejecuciones limpiaron sus recursos etiquetados. No se usaron puertos
  publicados ni datos o credenciales de despliegue.

## Trabajo pendiente

Falta implementar el adaptador real de `G5Lifecycle` con las tres barreras,
captura y comprobación efectiva de identidades SQL y Docker, migración y
publicación durables, reapertura de backend/worker por ID y restauración
exacta de parámetros y políticas originales. Faltan la verificación
independiente de imagen y esquema, HTTP y Socket.IO reales, registro de
jugador y finalización de cola por `app.worker`, y todos los adversarios
de fallo anterior y posterior a COMMITTED (incluidos salud, pérdida de
respuesta y deriva). Un fallo posterior al commit debe cerrar admisión y
restringir escritores sin restaurar el snapshot anterior. También falta
ejecutar el ensayo completo con limpieza verificada y luego integrarlo en CI.

Este avance no demuestra recuperación automática tras un crash, exclusión
de administradores privilegiados fuera del fixture ni RPO=0. La restauración
de #206 sigue siendo independiente; no se cierra #174.
