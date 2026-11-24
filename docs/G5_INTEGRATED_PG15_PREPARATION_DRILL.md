# BM-0093 / #174 — Ensayo integrado del corte G5 en PostgreSQL 15

**Estado: ensayo CI aislado, no adaptador de despliegue. G5 NO-GO.**
No se ha ejecutado en el VPS. No hay canal, restore ni reapertura de usuarios
en esta implementación.

## Qué prueba realmente

`ops/ci_g5_cutover_prepare_drill.py` es un programa restringido al entorno
GitHub Actions CI. Crea un PostgreSQL 15 efímero por ejecución usando
`docker run --rm --network none`, sin publicar puertos, conectar redes
externas, montar volúmenes reales ni usar secretos reales. Genera directorios
privados y solicitudes G5 sintéticas.

Usa los componentes reales del repositorio, NO copias de sus algoritmos:

- `G5Preparation.prepare` coordina las fases de **preparación exclusivamente**.
- `arm_cutover` mantiene `deploy.lock`, crea y sincroniza
  `.ops-state/g5-cutover-activated` *antes* de llamar al adaptador.
- `Pg15PersistentFence` cambia y comprueba el catálogo de PG15:
  `CONNECTION LIMIT 0` con commit/readback, `NOLOGIN`, terminación
  de sesiones y cero transacciones preparadas.
- `pg_dump --format=custom` obtiene un respaldo del PostgreSQL aislado
  **después** de comprobar la barrera y un intento de escritura rechazado.
  El respaldo se escribe a un archivo privado, se sincroniza con `fsync`,
  y el digest se vincula a `BackupReceipt`.
- `CutoverStore.prepare` verifica realmente el archivo, hash, identidad,
  permisos y ruta; publica el manifiesto duradero `PREPARED`.
- Se restaura una copia del dump en una **base distinta y desechable** para
  demostrar que conserva una transacción identificable confirmada antes
  del corte.

## Ensayos adversariales obligatorios

1. **Éxito:** se concede a `game_success_app` el permiso SQL `INSERT`
   real sobre la tabla auditada y se comprueba que la cuenta confirma una
   escritura antes del corte; también mantiene una sesión activa. La barrera
   termina esa sesión, rechaza nuevos `INSERT` antes y después del dump
   sobre la **misma tabla con permiso de INSERT comprobado**, conserva en
   la restauración tanto la escritura administrativa como la de la propia
   aplicación, publica `PREPARED` y mantiene bloqueados los entrypoints
   legacy mediante el marcador persistente.
2. **Fallo de snapshot:** se inyecta un error después del fence SQL real;
   no existe `PREPARED`, se mantiene la marca irreversible y el login app
   sigue prohibido. Un reintento no puede armar otro corte por accidente.
3. **Recibo falso:** `pg_dump` funciona pero el checksum declarado es
   incorrecto; `CutoverStore` rechaza el respaldo y conserva el cierre.
4. **Escritor privilegiado:** se conecta un superusuario *después* del bloqueo
   de la aplicación, simulando un canal no controlado. La comprobación PG
   detecta la sesión y **se niega a publicar el snapshot**. Esto demuestra
   precisamente por qué limitar `datconnlimit`/login no es una barrera
   universal frente a usuarios administrativos.

Cada caso usa roles y bases nuevas dentro del contenedor aislado. No limpia
incidentes en el host real, no invoca comandos de deploy y no cambia las
reglas de juego.

## Lo que NO certifica

El `PreparationPort` del ensayo **simula** cierre de HTTP/Socket.IO y
parada de procesos Compose; no hay servidor de juego ni contenedores de
`backend`, `worker`, `seed`, `migrate` activos. Tampoco existe todavía
un inventario demostrablemente completo de todas las cuentas superusuario,
conexiones manuales, instancias remotas y procesos programados de producción.

Esto no prueba que un adaptador de producción pueda impedir a todos los
escritores privilegiados reconectarse entre dos observaciones. La barrera
actual no ofrece `MIGRATING`/`VERIFIED_READONLY`/`COMMITTED`, protocolo
seguro de migración/restore/reapertura, ni continuidad post-reinicio/reboot
de Docker/host bajo un coordinador único. RPO=0 en staging y producción
permanece **sin certificar**. No usar como permiso para operar datos reales.

## Trabajo restante para cerrar P1 #174

- Aprovisionamiento seguro y auditable de roles reales de aplicación,
  migración y operaciones, revisando privilegios heredados y rutas
  administrativas antes de un despliegue.
- Adaptador de host en staging aislado que cierre y mantenga HTTP y Socket.IO,
  mate y evite reinicios de todos los procesos de escritura y controle
  conexiones privilegiadas fuera de PostgreSQL.
- Completar fase de migración/verify/commit y recuperación/rollback bajo
  el mismo lock y manifiesto; garantizar respaldo inmutable y que jamás
  se restaure una instantánea anterior a transacciones confirmadas.
- Repetir pruebas de fallo en múltiples instancias y simular terminación
  de coordinador, Docker y host. Medir RPO/RTO y mantenimiento. Aprobación
  explícita para ensayo staging antes de tocar VPS.

**G5 sigue NO-GO. El issue #174 permanece P1 abierto.**
