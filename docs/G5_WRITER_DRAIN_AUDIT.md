# G5 / BM-0093 — Inventario adversarial de escritores (#183)

**Estado: auditoría aislada, NO-GO para G5 y #174.** No toca deploy, rollback,
restore, Nginx, worker, scheduler, base de datos ni VPS. Complementa los PR
#180 (reproducción de pérdida), #181 (edge G5), #182 (manifiesto),
#185 (inspección de punto en el tiempo) y #187 (protección legacy).

## Matriz de rutas de escritura

| Escritor | Entrada y proceso | Riesgo tras cierre HTTP | Evidencia / compuerta pendiente |
| --- | --- | --- | --- |
| FastAPI rutas POST/PATCH/DELETE | Contenedores `backend`; cada réplica | Peticiones en curso que pasaron Nginx; clientes internos sin proxy | Retirar admisión, detener backend sin SIGKILL antes de snapshot, verificar conexiones/commits |
| FastAPI GET con efecto lateral | `GET /message/{message_id}` en `app/routers/message.py:read_message` | Marca mensaje leído con `db.commit()`; un filtro solo por método HTTP deja pasar escrituras | Bloquear **todas** las rutas API; incorporar registro de handlers con efectos secundarios |
| Socket.IO | `socket_manager.sio`, transporte polling/upgrade y conexiones existentes en `backend` | El proxy solo bloquea nuevas solicitudes: WebSockets establecidos pueden seguir activos | Cerrar nuevas conexiones, terminar las existentes, drenar handlers y comprobar conexiones DB |
| Trabajador de colas | `python -m app.worker` / APScheduler `queue_processing` cada 5 s | Un job ya iniciado puede hacer commit tras SIGTERM | Detener programación, esperar jobs en vuelo, verificar cero sesiones DB y proteger contra reinicios |
| Crecimiento bárbaro | Mismo worker, `barbarian_ai` cada 5 min | Lock advisory **distinto** al de colas; ambos pueden correr y escribir en paralelo | Barrera compartida transaccional o parada completa de todas las réplicas del worker |
| Migraciones | Servicio efímero `migrate` en `docker-compose.deploy.yml` | `docker compose up` puede reejecutar Alembic durante un rollback | No arrancar `migrate` antes de fijar la barrera/cutover; secuenciar migración bajo lock |
| Seed de mundo | Servicio `seed`, encadenado a `migrate` | `depends_on` puede provocar nuevas escrituras de inicialización | Tratarlo como escritor incluso si no hay backend/worker |
| Consola, scripts y otras réplicas | `ops/`, scripts manuales, tareas de administración, acceso directo a PostgreSQL | No pasan por el gate Nginx ni por locks de jobs | Inventario de identidades/credenciales, conexiones y permisos de escritura; negar cambios fuera del coordinador |
| PostgreSQL | Sesiones activas, prepared transactions, roles y conexiones futuras | Cero sesiones en un instante **no** impide que se abra otra | Bloquear admisión al DB de manera duradera, drenar transacciones, comprobar snapshot bajo protección |

## Evidencia automatizada agregada

`tests/test_g5_writer_drain_adversarial.py` prueba sin Docker/red/VPS:

- Señal SIGTERM durante job activo, esperando su finalización antes de terminar.
- Reproducción controlada: la función real `_run_database_job` puede hacer
  `db.commit()` **después** de que el worker haya recibido SIGTERM si el
  callback estaba activo. El test **pasa porque demuestra el peligro**, no
  porque certifique una barrera.
- Rechazo de job con lock ocupado sin abrir sesión; rollback y cierre de sesión
  tras excepción; convivencia de locks de nombres diferentes.
- Registro real de intervalos de los dos jobs y llamada
  `shutdown(wait=True)`, que no tiene plazo máximo propio.
- Evidencia AST de `db.commit()` en el GET de lectura de mensajes.
- Separación entre la aplicación HTTP y el scheduler.

Los dos jobs son escritores diferentes aunque compartan proceso. Los locks
advisory por job protegen duplicidad entre réplicas, **no** un cutover global.

## Fallos pendientes y casos hermanos

1. **P1 #174 — RPO=0 no probado.** No existe una barrera duradera y universal
   antes de `pg_dump`. El deploy legacy toma snapshot con escrituras admitidas
   y restaura ante fallo; no habilitar G5 hasta implementar bloqueo coordinado.
2. **P1 — Escritores ajenos al edge.** `restart: unless-stopped` de backend y
   worker, sesiones nuevas y tareas manuales pueden volver a escribir. El
   orquestador debe mantener la compuerta tras reinicio/crash y permitir
   reconciliación, no solo ejecutar `docker compose stop` una vez.
3. **P2 — Drain sin deadline controlado.** `shutdown(wait=True)` espera
   indefinidamente si un callback queda bloqueado; SIGKILL ante un timeout puede
   dejar transacción incierta. Se requiere límite, evidencia verificable y
   `RECOVERY_REQUIRED` si no se puede certificar.
4. **P2 — Orden de arranque.** `migrate` y `seed` son prerrequisitos de
   `backend/worker`; no deben relanzarse durante un restore ni usarse para
   recuperar un fallo pre-migración.
5. **Cobertura externa pendiente.** No hay prueba integrada de RPO=0 con
   PostgreSQL15 efímero, nuevas conexiones hostiles, caída del proxy,
   WebSocket activo, dos réplicas, reinicio Docker ni recuperación durante
   cada fase del cutover. Son condiciones para cerrar #174, no para esta
   auditoría de solo lectura.

## Criterios para la siguiente implementación

Mantener el lock del gestor de despliegues; bloquear admisión HTTP y WebSocket
con confirmación 503 real; inhibir **todas** las fuentes de escritura y sus
reinicios; esperar trabajos existentes con evidencia de ausencia de sesiones
activas/preparadas y garantía contra nuevas sesiones; capturar dump y
`CutoverStore.prepare` bajo la misma protección; migrar/verificar
sin escritores; registrar el commit terminal antes de reabrir; en fallos antes
del commit solo restaurar si la barrera se mantuvo sin interrupción y el
manifiesto/backup coinciden. En cualquier incertidumbre mantener marcador
`RECOVERY_REQUIRED` y realizar recuperación manual controlada.

**Este documento no cambia contratos del juego, no habilita beta y no asegura
RPO=0.** Se debe conectar el protocolo real al despliegue en otro PR y
validar su HEAD con pruebas PostgreSQL/Docker reales antes de staging.
