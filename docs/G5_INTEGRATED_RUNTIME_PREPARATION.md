# G5 — Ensayo combinado de preparación protegida (#174)

**NO-GO para operación real. Sin VPS, despliegue ni reapertura.**

Este ensayo conecta por primera vez en el mismo proyecto Docker desechable
las implementaciones reales de EdgeAdmission, Pg15PersistentFence y
DockerWriterFence a G5Preparation. No reemplaza los tres ensayos focalizados.
La configuración Nginx es la real; servidor HTTP/WebSocket y datos son
sintéticos. El worker ejecuta transacciones reales en PostgreSQL 15.

## Evidencia exigida

- Proyecto y red interna de nombre aleatorio, sin puertos publicados, dos
  réplicas backend, worker, migrate, seed detenido, frontend, Nginx y PG15.
  La única identidad privilegiada utilizada pertenece al fixture. No se
  cargan archivos de entorno ni secretos de despliegue.
- Commit administrativo, commit del worker por TCP y commit de control
  positivo de la identidad app que se volverá a probar después del cierre.
  El worker entra además en una transacción con un INSERT no confirmado.
- HTTP abierto y WebSocket 101 antes de activar. Activación durable y
  cierre de solicitudes nuevas con 503, ping del WebSocket previo,
  barrera SQL persistente, parada de todas las réplicas y desconexión
  del socket anterior. Rechazo SQL explícito al reconectar (no basta
  un fallo arbitrario de Docker o de permisos de INSERT).
- Verificación de las tres barreras antes y después de pg_dump.
  Archivo privado fsync, hash y manifiesto PREPARED durables.
  Restauración del descriptor verificado a otra base desechable:
  contiene exactamente los tres commits, excluye la fila no confirmada
  y la escritura rechazada; conserva grants de tabla y no cambia la fuente.
- Segundo proyecto: reinicio manual de un backend después del dump.
  El coordinador debe rechazar PREPARED; conservan cierre SQL, cierre
  HTTP y activación, y un segundo intento queda bloqueado. No se autoriza
  restaurar por haber obtenido un archivo.
- Limpieza por etiqueta de fixture, contenedores, volúmenes anónimos y red,
  incluso en excepciones. Ningún cambio fuera de CI.

## Pendientes que impiden cerrar P1 #174

El backend HTTP no es el juego ni implementa Socket.IO real. No se prueba
la migración Alembic real con identidad de mantenimiento, ni recuperación
de caída del coordinador/host, ni rollback autorizado de la base fuente,
ni publicación y reapertura. PostgreSQL superusuarios y administradores
Docker pueden saltarse estos controles: se debe demostrar exclusión
de otras rutas privilegiadas y mantener esa exclusión durante todo el
cutover. Un ensayo en CI no certifica RPO=0 en staging o producción.
