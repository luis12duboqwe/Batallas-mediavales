# BM-0093 / #174 — Cierre de escritores Docker G5

**NO-GO. Sin conexión al despliegue ni ejecución en VPS.**

`DockerWriterFence` implementa el cierre de los contenedores identificados
por proyecto Compose local, incluidos todos los backend/worker, réplicas
y migrate/seed (también los ya terminados). Usa IDs completos e inspección
del runtime, no solamente las políticas del YAML. Verifica un único
database y nginx activos, bloquea topologías desconocidas, aplica
`docker update --restart=no` a todos los escritores antes de detenerlos
y solo entonces ejecuta `docker stop --time 10` por ID. Comprueba el
inventario, los estados y las políticas reales otra vez. Nunca arranca
contenedores, elimina datos o restablece políticas.

El ejecutor se fija al socket Docker local, limita el tiempo de cada
comando y evita imprimir diagnósticos que contengan secretos.

**Límites:** el llamador debe mantener la activación G5 y el lock, cerrar
el edge, y conservar la barrera PostgreSQL. Una política Docker
`no` no prohíbe un inicio manual por un administrador ni nuevos
contenedores, y la observación no cubre escritores fuera de ese
proyecto. El coordinador debe controlar esas rutas. No es una
autorización de snapshot por sí misma ni se ha cableado aún al deploy.

CI prueba la librería con respuestas simuladas y con contenedores
desechables, sin puertos/redes externas/montajes reales. El ensayo
incluye dos réplicas de backend, worker, migrate, seed detenido,
servicios pasivos, un proyecto ajeno y un reinicio manual que debe
detectarse. Ninguna modificación de roles, backups o servicios reales.

La membresía se enumera nuevamente después de cada lote de inspecciones;
una réplica creada dentro de esa ventana impide certificar el cierre.
El fixture etiqueta los contenedores antes de crearlos, recupera los IDs
por etiqueta incluso si se pierde la respuesta del daemon y elimina sus
volúmenes anónimos con comprobación posterior. CI inyecta una creación
real seguida de pérdida de respuesta y exige limpieza completa.
